import assert from 'node:assert/strict';
import {mkdtemp, rm, writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import test from 'node:test';

import {cleanupPluginItems, uninstallCleanupRequest} from '../../service/src/api/cleanup.mjs';
import {createServiceContext} from '../../service/src/api/context.mjs';
import {runRoutine, protectedForMidday} from '../../service/src/scheduler/bounded-routines.mjs';
import {evaluateCatchUp, scheduledInstant, selectDuePhase} from '../../service/src/scheduler/catch-up.mjs';
import {withSingleInstance} from '../../service/src/scheduler/single-instance.mjs';

test('single-instance lock rejects overlap and reclaims only a dead stale owner', async t => {
  const directory = await mkdtemp(path.join(tmpdir(), 'rhize-task7-lock-'));
  const lockPath = path.join(directory, 'routine.lock');
  t.after(() => rm(directory, {recursive: true, force: true}));
  let release;
  const first = withSingleInstance(lockPath, () => new Promise(resolve => { release = resolve; }));
  while (!release) await new Promise(resolve => setImmediate(resolve));
  await assert.rejects(withSingleInstance(lockPath, async () => null), error => error.kind === 'already_running');
  release('done'); assert.equal(await first, 'done');
  await writeFile(lockPath, JSON.stringify({pid: 999999, token: 'old', startedAt: '2020-01-01T00:00:00.000Z'}), {mode: 0o600});
  assert.equal(await withSingleInstance(lockPath, async () => 'reclaimed', {now: () => new Date('2026-08-17T08:00:00Z'), staleMs: 60_000}), 'reclaimed');
});

test('catch-up collapses any missed count into exactly one evaluation', () => {
  assert.deepEqual(evaluateCatchUp({lastCompletedAt: '2026-08-17T05:00:00.000Z', now: '2026-08-17T08:00:00.000Z', intervalMinutes: 15}), {shouldRun: true, catchUp: true, missedCount: 12});
  assert.deepEqual(evaluateCatchUp({lastCompletedAt: '2026-08-17T07:55:00.000Z', now: '2026-08-17T08:00:00.000Z', intervalMinutes: 15}), {shouldRun: false, catchUp: false, missedCount: 0});
});

test('catch-up selects one latest local phase across DST and missed phases', () => {
  const profile = {identity: {timezone: 'America/New_York'}, routines: {morningTime: '09:00', middayTime: '12:00', eveningTime: '17:00'}};
  assert.equal(scheduledInstant('2026-03-08', '09:00', 'America/New_York'), '2026-03-08T13:00:00.000Z');
  const due = selectDuePhase({profile, lastRuns: {morning: '2026-03-08T13:00:00.000Z', evening: '2026-03-07T22:00:00.000Z'}, now: new Date('2026-03-08T16:30:00.000Z')}); assert.equal(due.phase, 'midday'); assert.equal(due.dueAt, '2026-03-08T16:00:00.000Z'); assert.ok(due.missedCount > 1);
  const missed = selectDuePhase({profile, lastRuns: {}, now: new Date('2026-03-09T12:00:00.000Z')});
  assert.equal(missed.phase, 'evening'); assert.equal(missed.dueAt, '2026-03-08T21:00:00.000Z'); assert.ok(missed.missedCount > 1);
});

test('paused routines do no sync/write and partial connector outage remains scoped', async t => {
  const directory = await mkdtemp(path.join(tmpdir(), 'rhize-task7-routine-'));
  t.after(() => rm(directory, {recursive: true, force: true}));
  let syncCalls = 0; let planCalls = 0;
  const base = {
    lockPath: path.join(directory, 'routine.lock'),
    activation: {async canActivate() { return true; }},
    routineState: {async evaluate() { return {shouldRun: true, catchUp: false}; }, async begin() { return 'run-1'; }, async complete() {}},
    sync: {async readAll() { syncCalls += 1; return {tasks: [], protectedIntervals: [], freshness: {jira: {status: 'offline'}, calendar: {status: 'healthy'}}, offlineSystems: ['jira']}; }},
    plans: {async reconcileAndPlan(input) { planCalls += 1; assert.deepEqual(input.snapshot.offlineSystems, ['jira']); return {state: 'planned', writesPausedFor: ['jira']}; }},
  };
  assert.deepEqual(await runRoutine('midday', {...base, pause: {async isPaused() { return true; }}}), {state: 'paused'});
  assert.equal(syncCalls, 0);
  assert.deepEqual(await runRoutine('midday', {...base, pause: {async isPaused() { return false; }}}), {state: 'planned', writesPausedFor: ['jira'], phase: 'midday'});
  assert.equal(syncCalls, 1); assert.equal(planCalls, 1);
});

test('midday preservation converts active, completed, manual, and freeze-window blocks into immutable intervals', () => {
  const blocks = [
    {id: 'active', taskId: 'a', start: '2026-08-17T08:00:00.000Z', end: '2026-08-17T09:00:00.000Z', locked: false},
    {id: 'completed', taskId: 'b', start: '2026-08-17T09:00:00.000Z', end: '2026-08-17T10:00:00.000Z', locked: false},
    {id: 'manual', taskId: 'c', start: '2026-08-17T10:00:00.000Z', end: '2026-08-17T11:00:00.000Z', locked: true},
    {id: 'frozen', taskId: 'd', start: '2026-08-17T11:10:00.000Z', end: '2026-08-17T12:00:00.000Z', locked: false},
    {id: 'future', taskId: 'e', start: '2026-08-17T15:00:00.000Z', end: '2026-08-17T16:00:00.000Z', locked: false},
  ];
  const intervals = protectedForMidday({blocks}, {active: 'active', completed: 'completed'}, '2026-08-17T11:00:00.000Z', 30);
  assert.deepEqual(intervals.map(item => item.id), ['preserved:active', 'preserved:completed', 'preserved:manual', 'preserved:frozen']);
  assert.ok(intervals.every(item => item.mutable === false && item.sourceSystem === 'local'));
});

test('uninstall cleanup deletes only persisted exact owned IDs/keys and fails closed offline', async () => {
  const deletedReminders = []; const deletedCalendar = [];
  const operations = [
    {kind: 'reminder_upsert', targetSystem: 'reminders', targetId: 'task-1', idempotencyKey: 'a'.repeat(64), attemptCount: 1, payload: {listId: 'tasks', externalId: 'task-1'}},
    {kind: 'calendar_upsert', targetSystem: 'calendar', targetId: 'focus-1', idempotencyKey: 'b'.repeat(64), attemptCount: 1, payload: {calendarId: 'focus'}},
    {kind: 'calendar_upsert', targetSystem: 'calendar', targetId: 'outside', idempotencyKey: 'c'.repeat(64), attemptCount: 0, payload: {calendarId: 'outside'}},
  ];
  const request = {schemaVersion: 1, scope: {reminders: 'plugin-owned', calendar: 'plugin-owned'}, ownership: {remindersMarkerPrefix: 'rhize-tasks:item:', calendarPrivateProperty: 'rhizeOperationKey'}, requireVerifiedResults: true};
  const reminders = {
    async readSnapshot() { return [{id: 'task-1', revision: deletedReminders.length ? 'gone' : 'r1'}, {id: 'outside-reminder', revision: 'r2'}].filter(item => !deletedReminders.includes(item.id)); },
    async applyOperation(value) { deletedReminders.push(value.targetId); return {externalId: value.targetId, revision: 'deleted'}; },
  };
  const result = await cleanupPluginItems({request, profile: {reminders: {tasksListId: 'tasks'}, calendar: {focusCalendarId: 'focus'}}, operations, connectors: {reminders}, calendarCleanup: async keys => { deletedCalendar.push(...keys); return keys.length; }});
  assert.deepEqual(result, {ok: true, reminders: {verified: true, deleted: 1}, calendar: {verified: true, deleted: 1}});
  assert.deepEqual(deletedReminders, ['task-1']); assert.deepEqual(deletedCalendar, ['b'.repeat(64)]);
  await assert.rejects(cleanupPluginItems({request: {...request, ownership: {...request.ownership, remindersMarkerPrefix: ''}}, profile: {}, operations: [], connectors: {}, calendarCleanup: async () => 0}), /cleanup_request_invalid/);
  await assert.rejects(cleanupPluginItems({request, profile: {reminders: {tasksListId: 'tasks'}, calendar: {focusCalendarId: 'focus'}}, operations, connectors: {}, calendarCleanup: async () => 1}), /cleanup_unavailable/);
});

test('Calendar uninstall counts are verified by an exact post-delete ownership lookup', async t => {
  const makeContext = async stubborn => {
    const directory = await mkdtemp(path.join(tmpdir(), 'rhize-task7-cleanup-'));
    let deleted = false; let listCalls = 0; let deleteCalls = 0;
    const transport = async request => {
      if (request.url === 'https://oauth2.googleapis.com/token') return {status: 200, body: {access_token: 'access-value'}};
      if (request.method === 'GET') {
        listCalls += 1;
        assert.match(request.url, /privateExtendedProperty=rhizeOperationKey%3D[bB]{64}/);
        assert.doesNotMatch(request.url, /timeMin|outside/);
        return {status: 200, body: {items: !deleted || stubborn ? [{id: 'owned-event', extendedProperties: {private: {rhizeOperationKey: 'b'.repeat(64)}}}] : []}};
      }
      if (request.method === 'DELETE') { deleteCalls += 1; deleted = true; return {status: 204, body: ''}; }
      throw new Error('unexpected_transport_call');
    };
    const context = await createServiceContext({
      databasePath: path.join(directory, 'state.sqlite'), transport,
      keychain: {async get() { return 'credential'; }, async set() {}, async delete() {}},
      connectors: {reminders: {async readSnapshot() { return []; }, async applyOperation() { throw new Error('unexpected_reminder_write'); }}},
    });
    context.repositories.preferences.set('profile', {reminders: {tasksListId: 'tasks'}, calendar: {focusCalendarId: 'focus'}});
    context.repositories.plans.save({schemaVersion: 1, planRevision: 1, blocks: []});
    const operation = {schemaVersion: 1, id: 'calendar-operation', planRevision: 1, kind: 'calendar_upsert', targetSystem: 'calendar', targetId: 'focus-block', payload: {calendarId: 'focus', title: 'Focus', start: '2026-08-17T09:00:00Z', end: '2026-08-17T10:00:00Z', description: '', externalId: 'focus-block'}, idempotencyKey: 'b'.repeat(64), approval: 'approved', preconditionRevision: null, retryState: 'pending', createdAt: '2026-08-17T08:00:00Z'};
    context.repositories.operations.save(operation); context.repositories.operations.beginAttempt(operation.id);
    t.after(() => { context.close(); return rm(directory, {recursive: true, force: true}); });
    return {context, counts: () => ({listCalls, deleteCalls})};
  };
  const success = await makeContext(false);
  assert.deepEqual(await success.context.cleanup(uninstallCleanupRequest), {ok: true, reminders: {verified: true, deleted: 0}, calendar: {verified: true, deleted: 1}});
  assert.deepEqual(success.counts(), {listCalls: 2, deleteCalls: 1});
  const unverifiable = await makeContext(true);
  await assert.rejects(unverifiable.context.cleanup(uninstallCleanupRequest), /cleanup_unavailable/);
  assert.deepEqual(unverifiable.counts(), {listCalls: 2, deleteCalls: 1});
});
