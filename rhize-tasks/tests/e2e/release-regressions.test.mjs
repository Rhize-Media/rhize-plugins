import assert from 'node:assert/strict';
import {mkdtemp, readFile, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import test from 'node:test';

import {cleanupPluginItems, uninstallCleanupRequest} from '../../service/src/api/cleanup.mjs';
import {createServiceContext} from '../../service/src/api/context.mjs';

const instant = '2026-08-17T08:00:00.000Z';
const token = 'release-regression-token-that-is-long-enough';

function profile() {
  return {
    schemaVersion: 1,
    identity: {name: 'Tom', timezone: 'UTC', locale: 'en-US'},
    jira: {accountId: 'tom', baseUrl: 'https://jira.example', projects: ['R'], issueTypes: ['Task'], excludedIssueTypes: [], projectImportance: {R: 3}, opportunityUrgencyThreshold: 'normal', maxDailySuggestions: 3, competencies: []},
    calendar: {readCalendarIds: ['focus'], focusCalendarId: 'focus', focusCalendarName: 'Rhize Focus', redactOutsideTitles: true},
    reminders: {awarenessLists: [], tasksListId: 'tasks', tasksListName: 'Rhize Tasks'},
    workingIntervals: [{dayOfWeek: 1, start: '09:00', end: '17:00'}], breaks: [],
    capacity: {bufferPercent: 20, maxDailyMinutes: 480}, planning: {focusBlockMinutes: 60, minimumBlockMinutes: 30, allowSplitting: true, meetingBufferMinutes: 0, freezeWindowMinutes: 0},
    routines: {replanningMode: 'bounded', reconciliationMode: 'prompted', morningTime: '09:00', middayTime: '12:00', eveningTime: '17:00'},
    approval: {setupComplete: true, firstPlanApproved: false, automationPaused: false}, privacy: {showOutsideTitles: false},
  };
}

function task(overrides = {}) {
  return {schemaVersion: 1, id: 'task-1', sourceType: 'jira', lane: 'owned', title: 'Audit', projectKey: 'R', issueType: 'Task', assigneeAccountId: 'tom', priority: 'high', dueDate: null, status: 'Open', terminal: false, blocked: false, dependencyRisk: 0, remainingMinutes: 60, explicitEstimateMinutes: null, competencies: [], manualLock: false, carryoverCount: 0, createdAt: '2026-08-01T09:00:00.000Z', reserved: false, sourceRevision: 'r1', jiraKey: 'R-1', ...overrides};
}

function emptyConnector() { return {async health() { return {ok: true}; }, async readSnapshot() { return []; }}; }

async function fixture(t, connectors) {
  const directory = await mkdtemp(path.join(tmpdir(), 'rhize-release-regression-'));
  const context = await createServiceContext({databasePath: path.join(directory, 'state.sqlite'), keychain: {async get() { return token; }, async set() {}, async delete() {}}, connectors, now: () => new Date(instant), lockPath: path.join(directory, 'routine.lock')});
  context.repositories.preferences.set('profile', profile());
  t.after(() => { context.close(); return rm(directory, {recursive: true, force: true}); });
  return context;
}

test('setup stage 2 omits explanatory credential storage from the persisted request', async () => {
  const javascript = await readFile(new URL('../../dashboard/app.js', import.meta.url), 'utf8');
  assert.doesNotMatch(javascript, /credentialStorage\s*:/);
});

test('Jira refresh preserves local carryover, manual lock, and reservation state', async t => {
  const current = task({manualLock: true, carryoverCount: 2, reserved: true, sourceRevision: 'r1'});
  const refreshed = task({title: 'Audit updated upstream', manualLock: false, carryoverCount: 0, reserved: false, sourceRevision: 'r2'});
  const context = await fixture(t, {jira: {...emptyConnector(), async readSnapshot() { return [refreshed]; }}, calendar: emptyConnector(), reminders: emptyConnector(), slack: emptyConnector()});
  context.repositories.tasks.upsert(current);
  await context.sync.readAll();
  assert.deepEqual(context.repositories.tasks.get('task-1'), {...refreshed, manualLock: true, carryoverCount: 2, reserved: true});
});

test('a moved owned Calendar block becomes a manual lock and is not overwritten', async t => {
  let events = [];
  const context = await fixture(t, {
    jira: {...emptyConnector(), async readSnapshot() { return [task()]; }},
    calendar: {...emptyConnector(), async readSnapshot() { return structuredClone(events); }},
    reminders: emptyConnector(), slack: emptyConnector(),
  });
  const first = await context.plans.preview({baseRevision: 0, planningDate: '2026-08-17'});
  await context.plans.approve(first.planRevision, 'Tom', false);
  const original = first.blocks[0]; const write = first.operations.find(operation => operation.kind === 'calendar_upsert');
  events = [{id: 'calendar-owned-1', calendarId: 'focus', revision: 'external-r2', start: '2026-08-17T11:00:00.000Z', end: '2026-08-17T12:00:00.000Z', owned: true, operationKey: write.payload.operationKey, taskId: original.taskId, blockSlot: `${original.taskId}:${original.sessionIndex}`}];
  const second = await context.plans.preview({baseRevision: 1, planningDate: '2026-08-17'});
  assert.equal(context.repositories.tasks.get('task-1').manualLock, true);
  assert.ok(second.protectedIntervals.some(interval => interval.id === 'calendar-owned-1' && interval.kind === 'manual_lock'));
  assert.equal(second.operations.some(operation => operation.targetId === 'calendar-owned-1'), false);
});

test('completed Rhize reminder records local completion and prompts Jira without writing it', async t => {
  let reminders = []; let jiraWrites = 0;
  const context = await fixture(t, {
    jira: {...emptyConnector(), async readSnapshot() { return [task()]; }, async applyOperation() { jiraWrites += 1; return {externalId: 'R-1', revision: 'r2'}; }},
    calendar: emptyConnector(),
    reminders: {...emptyConnector(), async readSnapshot() { return structuredClone(reminders); }},
    slack: emptyConnector(),
  });
  const first = await context.plans.preview({baseRevision: 0, planningDate: '2026-08-17'}); await context.plans.approve(first.planRevision, 'Tom', false);
  reminders = [{id: 'task-1', listId: 'tasks', title: 'Audit', dueAt: null, notes: '', completed: true, revision: 'reminder-r2'}];
  await context.sync.readAll();
  const states = context.repositories.preferences.get('block_states');
  assert.equal(states[first.blocks[0].id], 'completed');
  const prompt = context.repositories.operations.listForPlan(1).find(operation => operation.kind === 'jira_comment' && operation.targetId === 'R-1');
  assert.equal(prompt.approval, 'required');
  assert.equal(prompt.retryState, 'pending');
  assert.equal(jiraWrites, 0);
  assert.ok((await context.today()).approvals.some(item => item.operationId === prompt.id && item.title === 'Audit'));
  await context.plans.preview({baseRevision: 1, planningDate: '2026-08-17'}); await context.sync.readAll();
  assert.equal(context.repositories.operations.listForPlan(2).some(operation => operation.kind === 'jira_comment'), false);
});

test('Calendar uninstall cleanup uses the persisted private ownership key', async () => {
  const stableOwnershipKey = 'a'.repeat(64); const applyKey = 'b'.repeat(64); let received;
  const operations = [{kind: 'calendar_upsert', targetSystem: 'calendar', attemptCount: 1, idempotencyKey: applyKey, payload: {calendarId: 'focus', operationKey: stableOwnershipKey}}];
  const result = await cleanupPluginItems({request: uninstallCleanupRequest, profile: profile(), operations, connectors: {reminders: {async readSnapshot() { return []; }, async applyOperation() { throw new Error('unexpected'); }}}, async calendarCleanup(keys) { received = keys; return 1; }});
  assert.deepEqual(received, [stableOwnershipKey]);
  assert.deepEqual(result.calendar, {verified: true, deleted: 1});
});
