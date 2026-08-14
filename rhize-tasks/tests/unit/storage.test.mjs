import assert from 'node:assert/strict';
import {mkdtemp, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import test from 'node:test';

import {openDatabase, planRepository, taskRepository} from '../../service/src/storage/database.mjs';

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
    assert.deepEqual(db.prepare('select version from schema_migrations').all(), [{version: 1}]);
    db.prepare('insert into schema_migrations (version, applied_at) values (?, ?)').run(2, '2026-08-14T09:00:00Z');
    db.close();
    assert.throws(() => openDatabase(file), /newer schema migration/);
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
