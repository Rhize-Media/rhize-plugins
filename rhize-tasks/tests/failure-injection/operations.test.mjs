import assert from 'node:assert/strict';
import {mkdtemp, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import test from 'node:test';

import {operationKey} from '../../service/src/domain.mjs';
import {openDatabase, operationRepository, planRepository, taskRepository} from '../../service/src/storage/database.mjs';
import {applyApprovedOperations, previewOperations} from '../../service/src/reconciliation/operations.mjs';
import {reconcileExternalRevision} from '../../service/src/reconciliation/drift.mjs';

function operation(overrides = {}) {
  const base = {
    schemaVersion: 1, id: 'operation-1', planRevision: 3, kind: 'reminder_upsert', targetSystem: 'reminders', targetId: 'task-1',
    payload: {listId: 'tasks', title: 'Persist state', dueAt: null, notes: '', externalId: 'reminder-1'},
    approval: 'approved', preconditionRevision: '17', retryState: 'pending', createdAt: '2026-08-14T09:00:00Z',
  };
  const value = {...base, ...overrides};
  return {...value, idempotencyKey: overrides.idempotencyKey ?? operationKey(value.planRevision, value.kind, value.targetId, value.payload)};
}

async function withRepository(run) {
  const directory = await mkdtemp(join(tmpdir(), 'rhize-tasks-operations-'));
  try {
    const db = openDatabase(join(directory, 'state.sqlite'));
    planRepository(db).save({schemaVersion: 1, planRevision: 3, planningDate: '2026-08-14', generatedAt: '2026-08-14T09:00:00Z', status: 'preview', blocks: []});
    await run(operationRepository(db), taskRepository(db), db);
    db.close();
  } finally { await rm(directory, {recursive: true, force: true}); }
}

test('preview validates a plan-bound snapshot deterministically and applies only approved operations at the current revision', async () => {
  await withRepository(async repository => {
    const approved = operation();
    const unapproved = operation({id: 'operation-2', approval: 'required', payload: {...approved.payload, externalId: 'reminder-2'}});
    assert.deepEqual(previewOperations({planRevision: 3}, {sourceRevision: '17', proposedOperations: [approved, unapproved]}), {planRevision: 3, sourceRevision: '17', operations: [approved, unapproved], approvalsRequired: ['operation-2']});
    repository.save(approved);
    repository.save(unapproved);
    const connector = {calls: 0, async findByExternalId() { return {revision: '17'}; }, async applyOperation() { this.calls += 1; return {externalId: 'reminder-1', revision: '18'}; }};
    const result = await applyApprovedOperations({repository, connectors: {reminders: connector}, currentRevision: 3}, [approved, unapproved]);
    assert.deepEqual(result.map(item => item.state), ['applied', 'skipped_unapproved']);
    assert.equal(connector.calls, 1);
    assert.equal(repository.wasApplied(approved.idempotencyKey), true);
    const second = await applyApprovedOperations({repository, connectors: {reminders: connector}, currentRevision: 3}, [approved]);
    assert.deepEqual(second, [{operationId: approved.id, state: 'skipped_applied'}]);
    assert.equal(connector.calls, 1);
  });
});

test('ambiguous timeout is not retried and requires reconciliation', async () => {
  await withRepository(async repository => {
    const connector = {calls: 0, async findByExternalId() { return {revision: '17'}; }, async applyOperation() { this.calls += 1; throw {kind: 'timeout', retryable: true, ambiguous: true}; }};
    const item = operation(); repository.save(item);
    const result = await applyApprovedOperations({repository, connectors: {reminders: connector}, currentRevision: 3}, [item]);
    assert.equal(result[0].state, 'reconciliation_required');
    assert.equal(connector.calls, 1);
  });
});

test('external revision drift locks a resolvable task without calling the connector write', async () => {
  await withRepository(async (repository, tasks) => {
    const item = operation();
    tasks.upsert({schemaVersion: 1, id: 'task-1', sourceType: 'jira', lane: 'owned', title: 'Task', projectKey: 'RHIZE', issueType: 'Task', assigneeAccountId: null, priority: 'normal', dueDate: null, status: 'Open', terminal: false, blocked: false, dependencyRisk: 0, remainingMinutes: null, explicitEstimateMinutes: null, competencies: [], manualLock: false, carryoverCount: 0, createdAt: '2026-08-14T09:00:00Z', reserved: false, sourceRevision: '17', jiraKey: 'RHIZE-1'});
    repository.save(item);
    const connector = {writes: 0, async findByExternalId() { return {revision: '18'}; }, async applyOperation() { this.writes += 1; }};
    const result = await applyApprovedOperations({repository, connectors: {reminders: connector}, currentRevision: 3}, [item]);
    assert.deepEqual(result, [{operationId: item.id, state: 'reconciliation_required', reason: 'revision_drift'}]);
    assert.equal(connector.writes, 0);
    assert.equal(tasks.get('task-1').manualLock, true);
  });
});

test('only connector-proven safe errors retry, and revision drift creates a manual lock proposal', async () => {
  await withRepository(async (repository, tasks, db) => {
    const retried = operation();
    const connector = {calls: 0, async findByExternalId() { return {revision: '17'}; }, async applyOperation() { this.calls += 1; if (this.calls === 1) throw {kind: 'timeout', retryable: true, ambiguous: false}; return {externalId: 'reminder-1', revision: '18'}; }};
    repository.save(retried);
    const result = await applyApprovedOperations({repository, connectors: {reminders: connector}, currentRevision: 3}, [retried]);
    assert.equal(result[0].state, 'applied');
    assert.equal(connector.calls, 2);
    await assert.rejects(applyApprovedOperations({repository, connectors: {reminders: connector}, currentRevision: 4}, [operation({id: 'stale'})]), /plan revision/);
    tasks.upsert({schemaVersion: 1, id: 'task-1', sourceType: 'jira', lane: 'owned', title: 'Task', projectKey: 'RHIZE', issueType: 'Task', assigneeAccountId: null, priority: 'normal', dueDate: null, status: 'Open', terminal: false, blocked: false, dependencyRisk: 0, remainingMinutes: null, explicitEstimateMinutes: null, competencies: [], manualLock: false, carryoverCount: 0, createdAt: '2026-08-14T09:00:00Z', reserved: false, sourceRevision: '17', jiraKey: 'RHIZE-1'});
    const proposal = reconcileExternalRevision({repository, taskId: 'task-1', expectedRevision: '17', observedRevision: '18', operation: retried});
    assert.deepEqual(proposal, {taskId: 'task-1', state: 'manual_lock', expectedRevision: '17', observedRevision: '18', operationId: 'operation-1'});
    assert.equal(db.prepare("select count(*) as count from audit_log where event = 'external_revision_drift'").get().count, 1);
  });
});
