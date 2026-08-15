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
    calendar: {async readSnapshot() { return [{id: 'private-source-id', calendarId: 'outside', revision: 'e1', start: '2026-08-17T12:00:00.000Z', end: '2026-08-17T13:00:00.000Z', title: 'Private therapy', description: 'secret'}]; }, async health() { return {ok: true}; }, async findByExternalId() { return null; }, async applyOperation(value) { writes.push(value); return {externalId: value.targetId ?? 'calendar-created', revision: 'e2'}; }},
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
  return {context, request, writes, secrets, connectors};
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
  const preview = await request('/v1/plans/preview', {method: 'POST', body: {planRevision: 0}});
  assert.equal(preview.status, 201);
  assert.equal(preview.body.planningDate, '2026-08-17');
  assert.equal((await request('/v1/plans/1/approve', {method: 'POST', body: {actor: 'tom', apply: false}})).status, 200);
  assert.equal(await context.activation.canActivate(), true);
});

test('revision gates and persisted approval prevent duplicate connector writes', async t => {
  const {request, writes} = await fixture(t);
  await request('/v1/preferences', {method: 'PUT', body: {planRevision: 0, profile: profile()}});
  assert.equal((await request('/v1/plans/preview', {method: 'POST', body: {planRevision: 1, planningDate: '2026-08-17'}})).status, 409);
  await request('/v1/plans/preview', {method: 'POST', body: {planRevision: 0, planningDate: '2026-08-17'}});
  const first = await request('/v1/plans/1/approve', {method: 'POST', body: {actor: 'tom', apply: true}});
  const replay = await request('/v1/plans/1/approve', {method: 'POST', body: {actor: 'tom', apply: true}});
  assert.equal(first.status, 200); assert.equal(replay.status, 200);
  assert.ok(writes.length >= 1); assert.equal(new Set(writes.map(value => value.idempotencyKey)).size, writes.length);
});

test('prompted reconciliation exposes exact safe IDs and explicitly resumes only selected approved work', async t => {
  const {context, request, connectors, writes} = await fixture(t);
  context.repositories.plans.save({schemaVersion: 1, planRevision: 1, planningDate: '2026-08-17', generatedAt: now, status: 'approved', blocks: []});
  const first = operation({id: 'reconcile-first', approval: 'approved', retryState: 'pending', preconditionRevision: 'r1'});
  const second = operation({id: 'reconcile-second', approval: 'required', retryState: 'pending', idempotencyKey: 'b'.repeat(64), payload: {listId: 'tasks', title: 'Other', dueAt: null, notes: '', externalId: 'task-2'}});
  for (const value of [first, second]) { context.repositories.operations.save(value); context.repositories.operations.beginAttempt(value.id); context.repositories.operations.markState(value.id, 'reconciliation_required', {reason: value === first ? 'ambiguous_apply' : '<private source text>'}); }
  let preflights = 0; connectors.reminders.findByExternalId = async () => { preflights += 1; return {revision: 'r1'}; };
  const today = await request('/v1/today');
  assert.deepEqual(today.body.reconciliation, [
    {operationId: first.id, kind: first.kind, targetSystem: 'reminders', reason: 'ambiguous_apply'},
    {operationId: second.id, kind: second.kind, targetSystem: 'reminders', reason: 'reconciliation_required'},
  ]);
  assert.deepEqual(today.body.approvals, []);
  const resumed = await request('/v1/reconcile', {method: 'POST', body: {planRevision: 1, operationIds: [first.id], actor: 'tom'}});
  assert.equal(resumed.status, 200); assert.equal(resumed.body.results[0].state, 'applied'); assert.equal(writes.at(-1).id, first.id); assert.equal(preflights, 1);
  assert.equal(context.repositories.operations.execution(first.id).attemptCount, 1);
  assert.equal(context.repositories.operations.get(second.id).retryState, 'reconciliation_required');
  const events = context.repositories.audit.list(100).reverse().filter(entry => entry.entityId === first.id || entry.event === 'reconciliation_requested').map(entry => entry.event);
  const requestedAt = events.indexOf('reconciliation_requested'); const resumedAt = events.indexOf('operation_reconciliation_resumed', requestedAt + 1); const attemptedAt = events.indexOf('operation_attempted', resumedAt + 1);
  assert.ok(requestedAt >= 0 && requestedAt < resumedAt && resumedAt < attemptedAt);
});

test('reconciliation route rejects invalid authority and a second ambiguous attempt returns to reconciliation required', async t => {
  const {context, request, connectors} = await fixture(t);
  context.repositories.plans.save({schemaVersion: 1, planRevision: 1, planningDate: '2026-08-17', generatedAt: now, status: 'approved', blocks: []});
  const pending = operation({id: 'pending', approval: 'approved'}); context.repositories.operations.save(pending);
  const unapproved = operation({id: 'unapproved', approval: 'required', idempotencyKey: 'c'.repeat(64)}); context.repositories.operations.save(unapproved); context.repositories.operations.markState(unapproved.id, 'reconciliation_required', {reason: 'ambiguous_apply'});
  const ambiguous = operation({id: 'ambiguous-again', approval: 'approved', idempotencyKey: 'd'.repeat(64)}); context.repositories.operations.save(ambiguous); context.repositories.operations.markState(ambiguous.id, 'reconciliation_required', {reason: 'ambiguous_apply'});
  const post = body => request('/v1/reconcile', {method: 'POST', body});
  assert.equal((await post({planRevision: 1, operationIds: [], actor: 'tom'})).status, 400);
  assert.equal((await post({planRevision: 1, operationIds: [ambiguous.id, ambiguous.id], actor: 'tom'})).status, 400);
  assert.equal((await post({planRevision: 1, operationIds: [ambiguous.id]})).status, 400);
  assert.equal((await post({planRevision: 0, operationIds: [ambiguous.id], actor: 'tom'})).status, 409);
  assert.equal((await post({planRevision: 1, operationIds: ['missing'], actor: 'tom'})).status, 404);
  assert.equal((await post({planRevision: 1, operationIds: [pending.id], actor: 'tom'})).status, 409);
  assert.equal((await post({planRevision: 1, operationIds: [unapproved.id], actor: 'tom'})).status, 409);
  context.repositories.preferences.set('paused', true); assert.equal((await post({planRevision: 1, operationIds: [ambiguous.id], actor: 'tom'})).status, 409); context.repositories.preferences.set('paused', false);
  const healthy = connectors.reminders.health; connectors.reminders.health = async () => { throw new Error('offline'); }; assert.equal((await post({planRevision: 1, operationIds: [ambiguous.id], actor: 'tom'})).status, 503); connectors.reminders.health = healthy;
  let calls = 0; connectors.reminders.applyOperation = async () => { calls += 1; throw {kind: 'timeout', retryable: true, ambiguous: true, status: null}; };
  const first = await post({planRevision: 1, operationIds: [ambiguous.id], actor: 'tom'}); assert.equal(first.body.results[0].state, 'reconciliation_required'); assert.equal(calls, 1);
  const second = await post({planRevision: 1, operationIds: [ambiguous.id], actor: 'tom'}); assert.equal(second.body.results[0].state, 'reconciliation_required'); assert.equal(calls, 2); assert.equal(context.repositories.operations.execution(ambiguous.id).attemptCount, 1);
});

test('JSON handling rejects wrong content type, oversized/unknown bodies, and never echoes credentials', async t => {
  const {request, secrets} = await fixture(t);
  assert.equal((await request('/v1/preferences', {method: 'PUT', body: '{}', headers: {'content-type': 'text/plain'}})).status, 415);
  assert.equal((await request('/v1/preferences', {method: 'PUT', body: {planRevision: 0, profile: profile(), surprise: true}})).status, 400);
  assert.equal((await request('/v1/plans/preview', {method: 'POST', body: {planRevision: 0, planningDate: '2026-02-30'}})).status, 400);
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
  const output = path.join(directory, 'today.html'); let closed = false;
  t.after(() => rm(directory, {recursive: true, force: true}));
  const view = {schemaVersion: 1, planRevision: 7, generatedAt: now, timeline: [{id: 'busy-opaque', kind: 'outside', start: now, end: '2026-08-17T13:00:00.000Z', redacted: true}], currentBlock: null, nextBlock: null, capacity: {availableMinutes: 420, plannedMinutes: 0, bufferMinutes: 84, risk: 'normal'}, carryovers: [], approvals: [], reconciliation: [], opportunities: [], warnings: [], connectors: Object.fromEntries(['jira', 'calendar', 'reminders', 'slack'].map(name => [name, {status: 'healthy', freshAt: now, staleMinutes: 0}])), paused: false, degraded: false};
  await runCli(['artifact', '--output', output], {
    createContext: async () => ({async today() { return view; }, close() { closed = true; }}),
    stdout() {},
  });
  const html = await readFile(output, 'utf8'); assert.match(html, /Plan revision 7/); assert.doesNotMatch(html, /<form\b|<button\b|fetch\s*\(/i);
  assert.equal((await stat(output)).mode & 0o777, 0o600);
  assert.equal(closed, true);
});
