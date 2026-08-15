import assert from 'node:assert/strict';
import {mkdtemp, readFile, rm, stat} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {Readable} from 'node:stream';
import test from 'node:test';

import {uninstallCleanupRequest} from '../../service/src/api/cleanup.mjs';
import {createServiceContext} from '../../service/src/api/context.mjs';
import {createServer} from '../../service/src/api/server.mjs';
import {runCli} from '../../service/bin/rhize-tasks.mjs';
import {projectTodayView} from '../../service/src/views/today-view.mjs';

const token = 'api-token-that-must-never-appear';
const now = '2026-08-17T08:00:00.000Z';

function profile(overrides = {}) {
  return {
    schemaVersion: 1,
    identity: {name: 'Tom', timezone: 'UTC', locale: 'en-US'},
    jira: {accountId: 'tom', baseUrl: 'https://jira.example', projects: ['R'], issueTypes: ['Task'], excludedIssueTypes: [], projectImportance: {R: 3}, opportunityUrgencyThreshold: 'normal', maxDailySuggestions: 3, competencies: [{name: 'ops', confidence: .9, excluded: false}]},
    calendar: {readCalendarIds: ['outside', 'focus'], focusCalendarId: 'focus', focusCalendarName: 'Rhize Focus', redactOutsideTitles: true},
    reminders: {awarenessLists: [], tasksListId: 'tasks', tasksListName: 'Rhize Tasks'},
    workingIntervals: [{dayOfWeek: 1, start: '09:00', end: '17:00'}], breaks: [],
    capacity: {bufferPercent: 20, maxDailyMinutes: 480},
    planning: {focusBlockMinutes: 90, minimumBlockMinutes: 30, allowSplitting: true, meetingBufferMinutes: 0, freezeWindowMinutes: 30},
    routines: {replanningMode: 'bounded', reconciliationMode: 'prompted', morningTime: '09:00', middayTime: '12:00', eveningTime: '17:00'},
    approval: {setupComplete: true, firstPlanApproved: false, automationPaused: false}, privacy: {showOutsideTitles: false},
    ...overrides,
  };
}

function task(overrides = {}) {
  return {schemaVersion: 1, id: 'task-1', sourceType: 'jira', lane: 'owned', title: 'Audit', projectKey: 'R', issueType: 'Task', assigneeAccountId: 'tom', priority: 'high', dueDate: null, status: 'Open', terminal: false, blocked: false, dependencyRisk: 0, remainingMinutes: 60, explicitEstimateMinutes: null, competencies: ['ops'], manualLock: false, carryoverCount: 0, createdAt: '2026-08-01T09:00:00.000Z', reserved: false, sourceRevision: 'r1', jiraKey: 'R-1', ...overrides};
}

function operation(overrides = {}) {
  return {schemaVersion: 1, id: 'operation-1', planRevision: 1, kind: 'reminder_upsert', targetSystem: 'reminders', targetId: 'task-1', payload: {listId: 'tasks', title: 'Audit', dueAt: null, notes: '', externalId: 'task-1'}, idempotencyKey: 'a'.repeat(64), approval: 'required', preconditionRevision: null, retryState: 'pending', createdAt: now, ...overrides};
}

async function fixture(t) {
  const directory = await mkdtemp(path.join(tmpdir(), 'rhize-task7-api-'));
  const writes = [];
  const secrets = [];
  const keychain = {
    async get(service, account) { return service === 'media.rhize.tasks.api' && account === 'bearer' ? token : 'credential'; },
    async set(service, account, value) { secrets.push({service, account, value}); },
    async delete() {},
  };
  const connectors = {
    jira: {async readSnapshot() { return []; }, async health() { return {ok: true}; }},
    calendar: {async readSnapshot() { return [{id: 'private-source-id', calendarId: 'outside', revision: 'e1', start: '2026-08-17T12:00:00.000Z', end: '2026-08-17T13:00:00.000Z', title: 'Private therapy', description: 'secret'}]; }, async health() { return {ok: true}; }},
    reminders: {async readSnapshot() { return []; }, async health() { return {ok: true}; }, async findByExternalId() { return null; }, async applyOperation(value) { writes.push(value); return {externalId: value.targetId, revision: 'r2'}; }},
    slack: {async readSnapshot() { return []; }, async health() { return {ok: true}; }},
  };
  const context = await createServiceContext({databasePath: path.join(directory, 'state.sqlite'), keychain, connectors, now: () => new Date(now)});
  context.repositories.preferences.set('approved_setup_scopes', {jira: {projectKeys: ['R'], issueTypes: ['Task']}, calendar: {readCalendarIds: ['outside', 'focus'], focusCalendarId: 'focus'}, reminders: {awarenessListIds: [], tasksListId: 'tasks'}});
  context.repositories.tasks.upsert(task());
  const server = createServer(context);
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  const base = `http://127.0.0.1:${server.address().port}`;
  t.after(async () => { await new Promise(resolve => server.close(resolve)); context.close(); await rm(directory, {recursive: true, force: true}); });
  const request = async (pathname, {method = 'GET', body, auth = true, headers = {}} = {}) => {
    const response = await fetch(`${base}${pathname}`, {method, headers: {...(auth ? {authorization: `Bearer ${token}`} : {}), ...(body === undefined ? {} : {'content-type': 'application/json'}), ...headers}, body: body === undefined ? undefined : typeof body === 'string' ? body : JSON.stringify(body)});
    const text = await response.text();
    return {status: response.status, body: text ? JSON.parse(text) : null};
  };
  return {context, request, writes, secrets};
}

test('server is loopback-only, health is minimal, and every v1 route requires bearer auth', async t => {
  const {context, request} = await fixture(t);
  assert.throws(() => createServer({...context, host: '0.0.0.0'}), /loopback/);
  assert.deepEqual(await request('/health', {auth: false}), {status: 200, body: {version: '0.0.0', status: 'ok'}});
  assert.equal((await request('/v1/today', {auth: false})).status, 401);
  assert.equal((await request('/v1/doctor', {headers: {authorization: 'Bearer wrong'}})).status, 401);
});

test('preferences and first approved plan are both required for activation', async t => {
  const {context, request} = await fixture(t);
  assert.equal(await context.activation.canActivate(), false);
  assert.equal((await request('/v1/preferences', {method: 'PUT', body: {planRevision: 0, profile: profile()}})).status, 200);
  assert.equal(await context.activation.canActivate(), false);
  const preview = await request('/v1/plans/preview', {method: 'POST', body: {baseRevision: 0, planningDate: '2026-08-17', sourceRevision: 'snapshot-1', proposedOperations: [operation()]}});
  assert.equal(preview.status, 201);
  assert.equal((await request('/v1/plans/1/approve', {method: 'POST', body: {actor: 'tom', apply: false}})).status, 200);
  assert.equal(await context.activation.canActivate(), true);
});

test('revision gates and persisted approval prevent duplicate connector writes', async t => {
  const {request, writes} = await fixture(t);
  await request('/v1/preferences', {method: 'PUT', body: {planRevision: 0, profile: profile()}});
  assert.equal((await request('/v1/plans/preview', {method: 'POST', body: {baseRevision: 1, planningDate: '2026-08-17', sourceRevision: 'snapshot-1', proposedOperations: []}})).status, 409);
  await request('/v1/plans/preview', {method: 'POST', body: {baseRevision: 0, planningDate: '2026-08-17', sourceRevision: 'snapshot-1', proposedOperations: [operation()]}});
  const first = await request('/v1/plans/1/approve', {method: 'POST', body: {actor: 'tom', apply: true}});
  const replay = await request('/v1/plans/1/approve', {method: 'POST', body: {actor: 'tom', apply: true}});
  assert.equal(first.status, 200); assert.equal(replay.status, 200);
  assert.equal(writes.length, 1);
});

test('JSON handling rejects wrong content type, oversized/unknown bodies, and never echoes credentials', async t => {
  const {request, secrets} = await fixture(t);
  assert.equal((await request('/v1/preferences', {method: 'PUT', body: '{}', headers: {'content-type': 'text/plain'}})).status, 415);
  assert.equal((await request('/v1/preferences', {method: 'PUT', body: {planRevision: 0, profile: profile(), surprise: true}})).status, 400);
  assert.equal((await request('/v1/preferences', {method: 'PUT', body: JSON.stringify({padding: 'x'.repeat(70_000)})})).status, 413);
  const saved = await request('/v1/setup/credentials', {method: 'POST', body: {planRevision: 0, connector: 'jira', values: {email: 'tom@example.com', 'api-token': 'jira-secret-value'}}});
  assert.equal(saved.status, 200);
  assert.deepEqual(secrets.map(item => item.account), ['email', 'api-token']);
  assert.doesNotMatch(JSON.stringify(saved.body), /jira-secret|tom@example/);
  assert.doesNotMatch(JSON.stringify((await request('/v1/audit')).body), /jira-secret|tom@example|api-token-that/);
});

test('TodayView exposes opaque outside commitments and no outside title or description', () => {
  const view = projectTodayView({
    plan: {schemaVersion: 1, planRevision: 3, generatedAt: now, availableMinutes: 420, capacityMinutes: 336, usedMinutes: 60, bufferMinutes: 84, blocks: [], protectedIntervals: [{id: 'private-source-id', start: '2026-08-17T12:00:00.000Z', end: '2026-08-17T13:00:00.000Z', kind: 'outside', sourceSystem: 'calendar', mutable: false}]},
    tasks: [], operations: [], profile: profile(), freshness: {}, now,
  });
  assert.equal(view.timeline[0].redacted, true);
  assert.notEqual(view.timeline[0].id, 'private-source-id');
  assert.equal(Object.hasOwn(view.timeline[0], 'title'), false);
  assert.equal(view.currentBlock, null);
  assert.equal(view.nextBlock, null);
  assert.doesNotMatch(JSON.stringify(view), /therapy|secret|private-source-id/);
});

test('CLI uninstall handshake accepts exactly one bounded JSON line and returns verified counts', async () => {
  const outputs = [];
  const received = [];
  const context = {
    async cleanup(request) { received.push(request); return {ok: true, reminders: {verified: true, deleted: 1}, calendar: {verified: true, deleted: 2}}; },
    close() {},
  };
  await runCli(['uninstall-items', '--json'], {
    createContext: async () => context,
    stdin: Readable.from(`${JSON.stringify(uninstallCleanupRequest)}\n`),
    stdout: value => outputs.push(value),
  });
  assert.deepEqual(received, [uninstallCleanupRequest]);
  assert.deepEqual(JSON.parse(outputs.join('')), {ok: true, reminders: {verified: true, deleted: 1}, calendar: {verified: true, deleted: 2}});
  await assert.rejects(runCli(['uninstall-items', '--json'], {
    createContext: async () => context,
    stdin: Readable.from(`${JSON.stringify(uninstallCleanupRequest)}\n{}\n`),
    stdout() {},
  }), /invalid_json_line/);
});

test('CLI artifact writes one private read-only TodayView snapshot', async t => {
  const directory = await mkdtemp(path.join(tmpdir(), 'rhize-task7-artifact-'));
  const output = path.join(directory, 'today.json'); let closed = false;
  t.after(() => rm(directory, {recursive: true, force: true}));
  const view = {schemaVersion: 1, planRevision: 7, timeline: [{id: 'busy-opaque', redacted: true}], approvals: []};
  await runCli(['artifact', '--output', output], {
    createContext: async () => ({async today() { return view; }, close() { closed = true; }}),
    stdout() {},
  });
  assert.deepEqual(JSON.parse(await readFile(output, 'utf8')), view);
  assert.equal((await stat(output)).mode & 0o777, 0o600);
  assert.equal(closed, true);
});
