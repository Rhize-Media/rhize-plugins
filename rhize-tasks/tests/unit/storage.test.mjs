import assert from 'node:assert/strict';
import {mkdtemp, rm} from 'node:fs/promises';
import {readFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {DatabaseSync} from 'node:sqlite';
import test from 'node:test';

import {openDatabase, operationRepository, planRepository, taskRepository} from '../../service/src/storage/database.mjs';
import {operationKey} from '../../service/src/domain.mjs';

const task = {
  schemaVersion: 1, id: 'task-1', sourceType: 'jira', lane: 'owned', title: 'Persist state',
  projectKey: 'RHIZE', issueType: 'Task', assigneeAccountId: 'account-1', priority: 'high',
  dueDate: null, status: 'Open', terminal: false, blocked: false, dependencyRisk: 0,
  remainingMinutes: 30, explicitEstimateMinutes: null, competencies: [], manualLock: false,
  carryoverCount: 0, createdAt: '2026-08-14T09:00:00Z', reserved: false, sourceRevision: '17', jiraKey: 'RHIZE-17',
};

async function withDatabase(run) {
  const directory = await mkdtemp(join(tmpdir(), 'rhize-tasks-storage-'));
  const file = join(directory, 'state.sqlite');
  try { await run(file); } finally { await rm(directory, {recursive: true, force: true}); }
}

test('reopening applies each migration once and rejects newer databases', async () => {
  await withDatabase(file => {
    openDatabase(file).close();
    const db = openDatabase(file);
    assert.deepEqual(db.prepare('select version from schema_migrations').all(), [{version: 1}, {version: 2}]);
    db.prepare('insert into schema_migrations (version, applied_at) values (?, ?)').run(3, '2026-08-14T09:00:00Z');
    db.close();
    assert.throws(() => openDatabase(file), /newer schema migration/);
  });
});

test('migration locking rechecks the ledger under one write lock', async () => {
  await withDatabase(file => {
    let contested = false;
    const first = openDatabase(file, {beforeMigrations() {
      assert.throws(() => openDatabase(file), /locked|busy/i);
      contested = true;
    }});
    first.close();
    const second = openDatabase(file);
    assert.equal(contested, true);
    assert.deepEqual(second.prepare('select version from schema_migrations').all(), [{version: 1}, {version: 2}]);
    second.close();
  });
});

test('upgrades an exact v1 database without rewriting its stamped migration', async () => {
  await withDatabase(file => {
    const raw = new DatabaseSync(file);
    raw.exec('pragma foreign_keys = on');
    raw.exec('create table schema_migrations (version integer primary key, applied_at text not null)');
    raw.exec(readFileSync(new URL('../../service/src/storage/migrations/001-initial.sql', import.meta.url), 'utf8'));
    raw.prepare('insert into schema_migrations (version, applied_at) values (1, ?)').run('2026-08-14T09:00:00Z');
    raw.prepare('insert into plans (revision, data_json, created_at) values (1, ?, ?)').run(JSON.stringify({schemaVersion: 1, planRevision: 1, planningDate: '2026-08-14', generatedAt: '2026-08-14T09:00:00Z', status: 'preview', blocks: []}), '2026-08-14T09:00:00Z');
    const payload = {listId: 'tasks', title: 'Persist state', dueAt: null, notes: '', externalId: 'reminder-1'};
    const operation = {schemaVersion: 1, id: 'operation-v1', planRevision: 1, kind: 'reminder_upsert', targetSystem: 'reminders', targetId: 'task-1', payload, idempotencyKey: operationKey(1, 'reminder_upsert', 'task-1', payload), approval: 'required', preconditionRevision: null, retryState: 'pending', createdAt: '2026-08-14T09:00:00Z'};
    raw.prepare('insert into operations (id, plan_revision, idempotency_key, approval, retry_state, data_json, result_json, updated_at) values (?, ?, ?, ?, ?, ?, null, ?)').run(operation.id, operation.planRevision, operation.idempotencyKey, operation.approval, operation.retryState, JSON.stringify(operation), '2026-08-14T09:00:00Z');
    raw.prepare('insert into approvals (operation_id, approval, updated_at) values (?, ?, ?)').run(operation.id, operation.approval, '2026-08-14T09:00:00Z');
    raw.close();

    const db = openDatabase(file);
    const operations = operationRepository(db);
    assert.deepEqual(db.prepare('select version from schema_migrations order by version').all(), [{version: 1}, {version: 2}]);
    assert.equal(db.prepare('select attempt_count from operations where id = ?').get(operation.id).attempt_count, 0);
    assert.deepEqual(operations.get(operation.id), operation);
    assert.equal(db.prepare('select count(*) as count from approvals where operation_id = ?').get(operation.id).count, 1);
    operations.setApproval(operation.id, 'approved', 'migration-test');
    assert.equal(db.prepare('select count(*) as count from approvals where operation_id = ?').get(operation.id).count, 2);
    db.close();

    const reopened = openDatabase(file);
    assert.deepEqual(reopened.prepare('select version from schema_migrations order by version').all(), [{version: 1}, {version: 2}]);
    reopened.close();
  });
});

test('database constructor injection is used for hermetic tests', async () => {
  await withDatabase(file => {
    let constructions = 0;
    class InjectedDatabase extends DatabaseSync {
      constructor(path) { super(path); constructions += 1; }
    }
    const db = openDatabase(file, {Database: InjectedDatabase});
    assert.equal(constructions, 1);
    db.close();
  });
});

test('repositories round-trip validated objects, protect source mappings, and audit each write', async () => {
  await withDatabase(file => {
    const db = openDatabase(file);
    const tasks = taskRepository(db);
    const plans = planRepository(db);
    tasks.upsert(task);
    assert.deepEqual(tasks.get('task-1'), task);
    assert.throws(() => tasks.upsert({...task, id: 'task-2'}), /UNIQUE constraint failed/);
    const plan = {schemaVersion: 1, planRevision: 1, planningDate: '2026-08-14', generatedAt: '2026-08-14T09:00:00Z', status: 'preview', blocks: []};
    plans.save(plan);
    assert.deepEqual(plans.latest(), plan);
    assert.equal(db.prepare('select count(*) as count from audit_log').get().count, 2);
    db.prepare("insert into preferences (key, value_json, updated_at) values ('broken', '{', '2026-08-14T09:00:00Z')").run();
    assert.throws(() => tasks.preference('broken'), /invalid JSON/);
    db.close();
  });
});

test('operation state round-trips exactly and approval transitions are authoritative', async () => {
  await withDatabase(file => {
    const db = openDatabase(file);
    planRepository(db).save({schemaVersion: 1, planRevision: 1, planningDate: '2026-08-14', generatedAt: '2026-08-14T09:00:00Z', status: 'preview', blocks: []});
    const payload = {listId: 'tasks', title: 'Persist state', dueAt: null, notes: '', externalId: 'reminder-1'};
    const operation = {schemaVersion: 1, id: 'operation-1', planRevision: 1, kind: 'reminder_upsert', targetSystem: 'reminders', targetId: 'task-1', payload, idempotencyKey: operationKey(1, 'reminder_upsert', 'task-1', payload), approval: 'required', preconditionRevision: null, retryState: 'pending', createdAt: '2026-08-14T09:00:00Z'};
    const operations = operationRepository(db);
    assert.deepEqual(operations.save(operation), operation);
    assert.deepEqual(operations.setApproval(operation.id, 'approved', 'test-user'), {...operation, approval: 'approved'});
    assert.throws(() => operations.setApproval(operation.id, 'required', 'test-user'), TypeError);
    assert.equal(db.prepare('select count(*) as count from approvals where operation_id = ?').get(operation.id).count, 2);
    db.close();
  });
});

test('approved reconciliation resumes atomically with a fresh bounded budget and preserves the prior result in audit', async () => {
  await withDatabase(file => {
    const db = openDatabase(file);
    planRepository(db).save({schemaVersion: 1, planRevision: 1, planningDate: '2026-08-14', generatedAt: '2026-08-14T09:00:00Z', status: 'preview', blocks: []});
    const payload = {listId: 'tasks', title: 'Persist state', dueAt: null, notes: '', externalId: 'reminder-1'};
    const base = {schemaVersion: 1, id: 'operation-resume', planRevision: 1, kind: 'reminder_upsert', targetSystem: 'reminders', targetId: 'task-1', payload, idempotencyKey: operationKey(1, 'reminder_upsert', 'task-1', payload), approval: 'approved', preconditionRevision: null, retryState: 'pending', createdAt: '2026-08-14T09:00:00Z'};
    const operations = operationRepository(db);
    operations.save(base); operations.beginAttempt(base.id); operations.markState(base.id, 'reconciliation_required', {reason: 'ambiguous_apply', error: {kind: 'timeout', retryable: true, ambiguous: true, status: null}});
    const resumed = operations.resumeReconciliation(base.id, 'tom');
    assert.equal(resumed.retryState, 'pending');
    assert.deepEqual(operations.execution(base.id), {operation: resumed, attemptCount: 0, result: null});
    const audit = db.prepare("select data_json from audit_log where event = 'operation_reconciliation_resumed' and entity_id = ?").get(base.id);
    assert.deepEqual(JSON.parse(audit.data_json), {actor: 'tom', priorResult: {reason: 'ambiguous_apply', error: {kind: 'timeout', retryable: true, ambiguous: true, status: null}}});
    assert.throws(() => operations.resumeReconciliation(base.id, 'tom'), /not approved reconciliation work/);
    const unapproved = {...base, id: 'operation-unapproved', approval: 'required', idempotencyKey: 'b'.repeat(64)}; operations.save(unapproved); operations.markState(unapproved.id, 'reconciliation_required', {reason: 'ambiguous_apply'});
    assert.throws(() => operations.resumeReconciliation(unapproved.id, 'tom'), /not approved reconciliation work/);
    assert.equal(operations.execution(unapproved.id).result.reason, 'ambiguous_apply');
    db.close();
  });
});
