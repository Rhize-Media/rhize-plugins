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
    assert.deepEqual(second, [{operationId: approved.id, state: 'applied', reason: null}]);
    assert.equal(connector.calls, 1);
  });
});

test('persisted immutable identity and approval are authoritative over caller copies', async () => {
  await withRepository(async repository => {
    const persisted = operation({approval: 'required'});
    repository.save(persisted);
    const connector = {calls: 0, async applyOperation() { this.calls += 1; return {externalId: 'reminder-1', revision: '18'}; }};
    const bypass = {...persisted, approval: 'approved'};
    assert.deepEqual(await applyApprovedOperations({repository, connectors: {reminders: connector}, currentRevision: 3}, [bypass]), [{operationId: persisted.id, state: 'skipped_unapproved'}]);
    assert.equal(connector.calls, 0);
    await assert.rejects(applyApprovedOperations({repository, connectors: {reminders: connector}, currentRevision: 3}, [{...persisted, payload: {...persisted.payload, title: 'Substituted'}}]), /immutable/);
    assert.equal(connector.calls, 0);
  });
});

test('terminal failure and reconciliation states replay without connector calls', async () => {
  await withRepository(async repository => {
    const failed = operation(); repository.save(failed);
    const failing = {calls: 0, async findByExternalId() { return {revision: '17'}; }, async applyOperation() { this.calls += 1; throw {kind: 'validation', retryable: false, ambiguous: false}; }};
    assert.equal((await applyApprovedOperations({repository, connectors: {reminders: failing}, currentRevision: 3}, [failed]))[0].state, 'failed');
    assert.equal((await applyApprovedOperations({repository, connectors: {reminders: failing}, currentRevision: 3}, [failed]))[0].state, 'failed');
    assert.equal(failing.calls, 1);
    const ambiguous = operation({id: 'ambiguous', payload: {...failed.payload, externalId: 'reminder-2'}}); repository.save(ambiguous);
    const uncertain = {calls: 0, async findByExternalId() { return {revision: '17'}; }, async applyOperation() { this.calls += 1; throw {kind: 'timeout', retryable: true, ambiguous: true}; }};
    await applyApprovedOperations({repository, connectors: {reminders: uncertain}, currentRevision: 3}, [ambiguous]);
    assert.equal((await applyApprovedOperations({repository, connectors: {reminders: uncertain}, currentRevision: 3}, [ambiguous]))[0].state, 'reconciliation_required');
    assert.equal(uncertain.calls, 1);
  });
});

test('safe retries have one persisted lifetime budget across invocations', async () => {
  await withRepository(async repository => {
    const item = operation(); repository.save(item);
    repository.beginAttempt(item.id);
    repository.markState(item.id, 'safe_retry', {error: {kind: 'timeout'}});
    const connector = {calls: 0, async findByExternalId() { return {revision: '17'}; }, async applyOperation() { this.calls += 1; throw {kind: 'timeout', retryable: true, ambiguous: false}; }};
    assert.equal((await applyApprovedOperations({repository, connectors: {reminders: connector}, currentRevision: 3}, [item]))[0].state, 'failed');
    assert.equal(connector.calls, 1);
    assert.equal(repository.execution(item.id).attemptCount, 2);
  });
});

test('post-call persistence faults and malformed success reconcile without repeating writes', async () => {
  await withRepository(async repository => {
    const item = operation(); repository.save(item);
    let failApplied = true;
    const flaky = {...repository, markState(id, state, result) { if (state === 'applied' && failApplied) { failApplied = false; throw new Error('disk full'); } return repository.markState(id, state, result); }};
    const connector = {calls: 0, async findByExternalId() { return {revision: '17'}; }, async applyOperation() { this.calls += 1; return {externalId: 'reminder-1', revision: '18'}; }};
    assert.equal((await applyApprovedOperations({repository: flaky, connectors: {reminders: connector}, currentRevision: 3}, [item]))[0].state, 'reconciliation_required');
    assert.equal((await applyApprovedOperations({repository: flaky, connectors: {reminders: connector}, currentRevision: 3}, [item]))[0].state, 'reconciliation_required');
    assert.equal(connector.calls, 1);
    const malformed = operation({id: 'malformed', payload: {...item.payload, externalId: 'reminder-2'}}); repository.save(malformed);
    const malformedConnector = {calls: 0, async findByExternalId() { return {revision: '17'}; }, async applyOperation() { this.calls += 1; return {}; }};
    assert.equal((await applyApprovedOperations({repository, connectors: {reminders: malformedConnector}, currentRevision: 3}, [malformed]))[0].state, 'reconciliation_required');
    assert.equal(malformedConnector.calls, 1);
  });
});

test('ambiguous preconditions reconcile and missing connector methods fail explicitly while later operations continue', async () => {
  await withRepository(async repository => {
    const first = operation(); const second = operation({id: 'second', payload: {...operation().payload, externalId: 'reminder-2'}});
    repository.save(first); repository.save(second);
    const ambiguousRead = {calls: 0, async findByExternalId() { throw {kind: 'timeout', retryable: true, ambiguous: true}; }, async applyOperation() { this.calls += 1; }};
    assert.equal((await applyApprovedOperations({repository, connectors: {reminders: ambiguousRead}, currentRevision: 3}, [first]))[0].state, 'reconciliation_required');
    assert.equal(ambiguousRead.calls, 0);
    const noFind = operation({id: 'no-find', payload: {...operation().payload, externalId: 'reminder-3'}}); repository.save(noFind);
    const missingFind = {applyOperation() { throw new Error('must not run'); }};
    assert.equal((await applyApprovedOperations({repository, connectors: {reminders: missingFind}, currentRevision: 3}, [noFind]))[0].error.kind, 'missing_find_by_external_id');
    const noConnector = operation({id: 'no-connector', payload: {...operation().payload, externalId: 'reminder-no-connector'}}); repository.save(noConnector);
    assert.equal((await applyApprovedOperations({repository, connectors: {}, currentRevision: 3}, [noConnector]))[0].error.kind, 'missing_connector');
    const partial = operation({id: 'partial', payload: {...operation().payload, externalId: 'reminder-4'}}); const later = operation({id: 'later', payload: {...operation().payload, externalId: 'reminder-5'}}); repository.save(partial); repository.save(later);
    const connector = {calls: 0, async findByExternalId() { return {revision: '17'}; }, async applyOperation(item) { this.calls += 1; if (item.id === 'partial') throw {kind: 'validation', retryable: false, ambiguous: false}; return {externalId: item.payload.externalId, revision: '18'}; }};
    assert.deepEqual((await applyApprovedOperations({repository, connectors: {reminders: connector}, currentRevision: 3}, [partial, later])).map(item => item.state), ['failed', 'applied']);
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

test('drift reconciliation rolls back task locks and audit writes when the operation transition fails', async () => {
  await withRepository(async (repository, tasks, db) => {
    tasks.upsert({schemaVersion: 1, id: 'task-1', sourceType: 'jira', lane: 'owned', title: 'Task', projectKey: 'RHIZE', issueType: 'Task', assigneeAccountId: null, priority: 'normal', dueDate: null, status: 'Open', terminal: false, blocked: false, dependencyRisk: 0, remainingMinutes: null, explicitEstimateMinutes: null, competencies: [], manualLock: false, carryoverCount: 0, createdAt: '2026-08-14T09:00:00Z', reserved: false, sourceRevision: '17', jiraKey: 'RHIZE-1'});
    assert.throws(() => repository.reconcileDrift({operationId: 'missing', targetId: 'task-1', expectedRevision: '17', observedRevision: '18'}), /does not exist/);
    assert.equal(tasks.get('task-1').manualLock, false);
    assert.equal(db.prepare("select count(*) as count from audit_log where event = 'external_revision_drift'").get().count, 0);
  });
});
