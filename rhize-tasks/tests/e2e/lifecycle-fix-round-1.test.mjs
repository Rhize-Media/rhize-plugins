import assert from 'node:assert/strict';
import http from 'node:http';
import {mkdtemp, rm, writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import test from 'node:test';

import {runCli} from '../../service/bin/rhize-tasks.mjs';
import {createServiceContext} from '../../service/src/api/context.mjs';
import {createServer} from '../../service/src/api/server.mjs';
import {createGoogleCalendarConnector} from '../../service/src/connectors/google-calendar.mjs';
import {createRemindersConnector} from '../../service/src/connectors/reminders.mjs';
import {assertOperation, operationKey} from '../../service/src/domain.mjs';
import {planDay} from '../../service/src/planner/planning.mjs';
import {projectTodayView} from '../../service/src/views/today-view.mjs';

const token = 'task7-fix-round-one-api-token-value';
const instant = '2026-08-17T08:00:00.000Z';

function profile(overrides = {}) {
  const value = {
    schemaVersion: 1, identity: {name: 'Tom', timezone: 'UTC', locale: 'en-US'},
    jira: {accountId: 'tom', baseUrl: 'https://jira.example', projects: ['R'], issueTypes: ['Task'], excludedIssueTypes: [], projectImportance: {R: 3}, opportunityUrgencyThreshold: 'normal', maxDailySuggestions: 3, competencies: [{name: 'ops', confidence: .9, excluded: false}]},
    calendar: {readCalendarIds: ['outside', 'focus'], focusCalendarId: 'focus', focusCalendarName: 'Rhize Focus', redactOutsideTitles: true},
    reminders: {awarenessLists: [], tasksListId: 'tasks', tasksListName: 'Rhize Tasks'},
    workingIntervals: [{dayOfWeek: 1, start: '09:00', end: '17:00'}], breaks: [], capacity: {bufferPercent: 20, maxDailyMinutes: 480},
    planning: {focusBlockMinutes: 90, minimumBlockMinutes: 30, allowSplitting: true, meetingBufferMinutes: 0, freezeWindowMinutes: 0},
    routines: {replanningMode: 'bounded', reconciliationMode: 'prompted', morningTime: '09:00', middayTime: '12:00', eveningTime: '17:00'},
    approval: {setupComplete: true, firstPlanApproved: false, automationPaused: false}, privacy: {showOutsideTitles: false},
  };
  return {...value, ...overrides};
}

function taskValue(overrides = {}) {
  return {schemaVersion: 1, id: 'jira-1', sourceType: 'jira', lane: 'owned', title: 'Audit', projectKey: 'R', issueType: 'Task', assigneeAccountId: 'tom', priority: 'high', dueDate: null, status: 'Open', terminal: false, blocked: false, dependencyRisk: 0, remainingMinutes: 60, explicitEstimateMinutes: null, competencies: ['ops'], manualLock: false, carryoverCount: 0, createdAt: '2026-08-01T09:00:00.000Z', reserved: false, sourceRevision: 'r1', jiraKey: 'R-1', jiraUrl: 'https://jira.example/browse/R-1', ...overrides};
}

function emptyConnectors(overrides = {}) {
  const empty = {async readSnapshot() { return []; }, async health() { return {ok: true}; }};
  return {jira: empty, calendar: empty, reminders: empty, slack: empty, ...overrides};
}

async function contextFixture(t, options = {}) {
  const directory = await mkdtemp(path.join(tmpdir(), 'rhize-task7-fix1-')); const stored = new Map([['media.rhize.tasks.api\0bearer', token]]);
  const keychain = options.keychain ?? {async get(service, account) { const value = stored.get(`${service}\0${account}`); if (!value) throw new Error('missing'); return value; }, async set(service, account, value) { stored.set(`${service}\0${account}`, value); }, async delete(service, account) { stored.delete(`${service}\0${account}`); }};
  const context = await createServiceContext({databasePath: path.join(directory, 'state.sqlite'), keychain, connectors: options.connectors ?? emptyConnectors(), now: options.now ?? (() => new Date(instant))});
  t.after(() => { context.close(); return rm(directory, {recursive: true, force: true}); });
  return {context, directory, stored};
}

async function httpFixture(t, options = {}) {
  const fixture = await contextFixture(t, options); if (options.dashboardRoot) fixture.context.dashboardRoot = options.dashboardRoot;
  const server = createServer(fixture.context); await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  const base = `http://127.0.0.1:${server.address().port}`; fixture.context.port = server.address().port;
  t.after(() => new Promise(resolve => server.close(resolve)));
  const request = async (pathname, {method = 'GET', body, auth = true, headers = {}, redirect} = {}) => { const response = await fetch(`${base}${pathname}`, {method, redirect, headers: {...(auth ? {authorization: `Bearer ${token}`} : {}), ...(body === undefined ? {} : {'content-type': 'application/json'}), ...headers}, body: body === undefined ? undefined : JSON.stringify(body)}); const text = await response.text(); return {status: response.status, headers: response.headers, body: text && response.headers.get('content-type')?.includes('json') ? JSON.parse(text) : text}; };
  return {...fixture, server, base, request};
}

test('calendar create uses nullable targetId and POST while updates require a proven plugin event ID', async () => {
  const calls = []; const credentials = {async get() { return 'credential'; }};
  const transport = async request => { calls.push(request); if (request.url.includes('oauth2')) return {status: 200, body: {access_token: 'access'}}; if (request.method === 'GET' && request.url.includes('privateExtendedProperty')) return {status: 200, body: {items: []}}; if (request.method === 'POST') return {status: 200, body: {id: 'google-event-1', etag: 'etag-1'}}; throw new Error('unexpected'); };
  const connector = createGoogleCalendarConnector({readCalendarIds: ['focus'], focusCalendarId: 'focus', credentials, transport});
  const payload = {calendarId: 'focus', title: 'Focus', start: '2026-08-17T09:00:00Z', end: '2026-08-17T10:00:00Z', description: '', externalId: 'block-1'};
  const create = {schemaVersion: 1, id: 'calendar-create', planRevision: 1, kind: 'calendar_upsert', targetSystem: 'calendar', targetId: null, payload, idempotencyKey: operationKey(1, 'calendar_upsert', null, payload), approval: 'approved', preconditionRevision: null, retryState: 'pending', createdAt: instant};
  assert.equal(assertOperation(create), create); assert.throws(() => assertOperation({...create, kind: 'calendar_delete', payload: {}}));
  assert.deepEqual(await connector.applyOperation(create), {externalId: 'google-event-1', revision: 'etag-1'});
  assert.equal(calls.filter(call => call.method === 'POST' && call.url.includes('/events')).length, 1); assert.doesNotMatch(calls.find(call => call.method === 'POST' && call.url.includes('/events')).url, /null|block-1/);

  const unsafe = createGoogleCalendarConnector({readCalendarIds: ['focus'], focusCalendarId: 'focus', credentials, transport: async request => request.url.includes('oauth2') ? {status: 200, body: {access_token: 'access'}} : {status: 200, body: {id: 'manual-event', etag: 'e', extendedProperties: {private: {}}}}});
  await assert.rejects(unsafe.applyOperation({...create, targetId: 'manual-event'}), error => error.kind === 'out_of_scope');
});

test('scope expansion stays pending, narrowing is immediate, and material planning changes require a new plan approval', async t => {
  const jira = {async discover() { return {projects: [{key: 'R'}], issueTypes: [{name: 'Task'}, {name: 'Bug'}]}; }, async readSnapshot() { return []; }, async health() { return {ok: true}; }};
  const {context, request} = await httpFixture(t, {connectors: emptyConnectors({jira})}); context.repositories.tasks.upsert(taskValue()); context.repositories.preferences.set('approved_setup_scopes', {jira: {projectKeys: ['R'], issueTypes: ['Task']}, calendar: {readCalendarIds: ['outside', 'focus'], focusCalendarId: 'focus'}, reminders: {awarenessListIds: [], tasksListId: 'tasks'}});
  assert.equal((await request('/v1/preferences', {method: 'PUT', body: {planRevision: 0, profile: profile()}})).status, 200);
  await request('/v1/plans/preview', {method: 'POST', body: {planRevision: 0, planningDate: '2026-08-17'}});
  await request('/v1/plans/1/approve', {method: 'POST', body: {actor: 'tom', apply: false}}); assert.equal(await context.activation.canActivate(), true);
  const expanded = profile({jira: {...profile().jira, issueTypes: ['Task', 'Bug']}});
  assert.equal((await request('/v1/preferences', {method: 'PUT', body: {planRevision: 1, profile: expanded}})).status, 409); assert.equal(context.repositories.preferences.get('profile').jira.issueTypes.includes('Bug'), false);
  const pending = await request('/v1/setup/connectors', {method: 'POST', body: {planRevision: 1, connector: 'jira', scope: {projectKeys: ['R'], issueTypes: ['Task', 'Bug']}}}); assert.equal(pending.status, 201);
  assert.equal((await request(`/v1/operations/${pending.body.operation.id}/approve`, {method: 'POST', body: {planRevision: 1, actor: 'tom'}})).status, 200); assert.equal((await request('/v1/preferences', {method: 'PUT', body: {planRevision: 1, profile: expanded}})).status, 200); assert.deepEqual(context.repositories.preferences.get('profile').jira.issueTypes, ['Task', 'Bug']); assert.equal(await context.activation.canActivate(), false);
  await request('/v1/plans/preview', {method: 'POST', body: {planRevision: 1, planningDate: '2026-08-17'}}); await request('/v1/plans/2/approve', {method: 'POST', body: {actor: 'tom', apply: false}}); assert.equal(await context.activation.canActivate(), true);
  const narrowed = await request('/v1/preferences', {method: 'PUT', body: {planRevision: 2, profile: profile()}}); assert.equal(narrowed.status, 200); assert.deepEqual(context.repositories.preferences.get('profile').jira.issueTypes, ['Task']);
  const material = profile({capacity: {bufferPercent: 30, maxDailyMinutes: 480}}); assert.equal((await request('/v1/preferences', {method: 'PUT', body: {planRevision: 2, profile: material}})).status, 200); assert.equal(context.repositories.preferences.get('profile').approval.firstPlanApproved, false); assert.equal(await context.activation.canActivate(), false);
});

test('setup scope previews validate discovery before activation and final preferences use only approved scopes', async t => {
  const discovered = {
    jira: {projects: [{key: 'R'}], issueTypes: [{name: 'Task'}]},
    calendar: [{id: 'outside'}, {id: 'focus'}],
    reminders: {ok: true, lists: [{id: 'tasks'}, {id: 'aware'}]},
    slack: {workspaceId: 'W', channelId: 'C', senderIds: ['B']},
  };
  const connectors = Object.fromEntries(Object.entries(discovered).map(([name, value]) => [name, {async discover() { return value; }, async readSnapshot() { return []; }, async health() { return {ok: true}; }}]));
  const {context, request} = await httpFixture(t, {connectors});
  const scopes = [
    ['jira', {projectKeys: ['R'], issueTypes: ['Task']}],
    ['calendar', {readCalendarIds: ['outside', 'focus'], focusCalendarId: 'focus'}],
    ['reminders', {awarenessListIds: ['aware'], tasksListId: 'tasks'}],
    ['slack', {workspaceId: 'W', channelId: 'C', senderIds: ['B']}],
  ];
  for (const [connector, scope] of scopes) {
    const preview = await request('/v1/setup/connectors', {method: 'POST', body: {planRevision: 0, connector, scope}}); assert.equal(preview.status, 201); assert.deepEqual(preview.body.scope, scope); assert.equal(preview.body.operation.kind, 'scope_expand'); assert.equal(preview.body.operation.approval, 'required');
    assert.ok((await request('/v1/setup/status')).body.scopePreviews.some(item => item.operation.id === preview.body.operation.id));
    const approved = await request(`/v1/operations/${encodeURIComponent(preview.body.operation.id)}/approve`, {method: 'POST', body: {planRevision: 0, actor: 'tom'}}); assert.equal(approved.status, 200); assert.equal(approved.body.state, 'approved_setup_scope');
  }
  assert.equal(context.repositories.preferences.get('profile'), null); assert.equal(await context.activation.canActivate(), false);
  const outside = await request('/v1/setup/connectors', {method: 'POST', body: {planRevision: 0, connector: 'jira', scope: {projectKeys: ['OTHER'], issueTypes: ['Task']}}}); assert.equal(outside.status, 400);
  assert.equal((await request('/v1/preferences', {method: 'PUT', body: {planRevision: 0, profile: profile()}})).status, 200);
  assert.equal((await request('/v1/setup/connectors', {method: 'PUT', body: {planRevision: 0, connector: 'slack', scope: {workspaceId: 'W', channelId: 'C', senderIds: ['B']}, apply: true}})).status, 200);
  assert.deepEqual(context.repositories.preferences.get('connector_config').slack, {workspaceId: 'W', channelId: 'C', senderIds: ['B']});
});

test('setup probe is revision-bound, once-only, verified, reversible, and does not activate automation', async t => {
  const reminders = new Map(); const events = new Map(); const calls = [];
  const connector = (system, store) => ({
    async readSnapshot() { return []; }, async health() { return {ok: true}; },
    async findByExternalId(id) { calls.push(`${system}:find:${id}`); const direct = store.get(id); if (direct) return {revision: direct.revision}; const keyed = [...store].find(([, value]) => value.operationKey === id); return keyed ? {externalId: keyed[0], revision: keyed[1].revision} : null; },
    async applyOperation(operation) { calls.push(`${system}:${operation.kind}:${String(operation.targetId)}`); if (operation.kind.endsWith('delete')) { store.delete(operation.targetId); return {externalId: operation.targetId, revision: 'deleted'}; } const id = operation.targetId ?? 'google-probe-event'; store.set(id, {revision: `${system}-revision`, operationKey: operation.payload.operationKey}); return {externalId: id, revision: `${system}-revision`}; },
  });
  const {context, request} = await httpFixture(t, {connectors: emptyConnectors({reminders: connector('reminders', reminders), calendar: connector('calendar', events)})});
  context.repositories.preferences.set('approved_setup_scopes', {reminders: {awarenessListIds: [], tasksListId: 'tasks'}, calendar: {readCalendarIds: ['focus'], focusCalendarId: 'focus'}});
  const preview = await request('/v1/setup/probe', {method: 'POST', body: {planRevision: 0, mode: 'preview', remindersListId: 'tasks', focusCalendarId: 'focus'}}); assert.equal(preview.status, 201); assert.equal(preview.body.approvalRequired, true); assert.equal(calls.length, 0);
  assert.equal((await request('/v1/setup/probe', {method: 'POST', body: {planRevision: 1, mode: 'apply', probeId: preview.body.probeId, actor: 'tom'}})).status, 409);
  const applied = await request('/v1/setup/probe', {method: 'POST', body: {planRevision: 0, mode: 'apply', probeId: preview.body.probeId, actor: 'tom'}}); assert.equal(applied.status, 200); assert.deepEqual(applied.body.verified, {reminders: true, calendar: true}); assert.equal(reminders.size, 0); assert.equal(events.size, 0); assert.equal(await context.activation.canActivate(), false);
  assert.equal((await request('/v1/setup/probe', {method: 'POST', body: {planRevision: 0, mode: 'apply', probeId: preview.body.probeId, actor: 'tom'}})).status, 404);
  assert.ok(calls.some(value => value === 'calendar:calendar_upsert:null')); assert.ok(calls.some(value => value === 'calendar:calendar_delete:google-probe-event'));
});

test('runtime fails closed when the installer has not provisioned the bearer', async () => {
  const keychain = {async get() { throw new Error('missing'); }, async set() { throw new Error('unexpected_write'); }, async delete() {}};
  await assert.rejects(createServiceContext({databasePath: ':memory:', keychain, connectors: emptyConnectors()}), error => error.kind === 'api_token_missing' && error.status === 503);
});

test('awareness reminders are read globally as redacted protected time while writes remain list-bound', async t => {
  const calls = [];
  const runner = async (_file, _args, options) => { const request = JSON.parse(options.input); calls.push({request, list: options.env.RHIZE_TASKS_REMINDERS_LIST_ID}); const items = options.env.RHIZE_TASKS_REMINDERS_LIST_ID === 'aware' ? [{id: 'private-reminder', listId: 'aware', title: 'Busy', dueAt: '2026-08-17T09:00:00.000Z', notes: null, completed: false, revision: 'r1'}] : []; return {code: 0, timedOut: false, stdout: `${JSON.stringify({ok: true, items})}\n`}; };
  const reminders = createRemindersConnector({helperPath: '/fake/helper', tasksListId: 'tasks', awarenessListIds: ['aware'], runner});
  const {context} = await contextFixture(t, {connectors: emptyConnectors({reminders})}); const configured = profile({reminders: {tasksListId: 'tasks', tasksListName: 'Rhize Tasks', awarenessLists: [{id: 'aware', protectedDurationMinutes: 60, showTitles: false}]}}); context.repositories.preferences.set('profile', configured);
  const snapshot = await context.sync.readAll(); assert.deepEqual(calls.map(call => call.list), ['tasks', 'aware']); assert.equal(calls[1].request.redactTitles, true); assert.equal(snapshot.protectedIntervals.length, 1); assert.equal(Object.hasOwn(snapshot.protectedIntervals[0], 'title'), false);
  const planned = planDay({tasks: [taskValue()], protectedIntervals: snapshot.protectedIntervals, profile: configured, planningDate: '2026-08-17', now: instant, planRevision: 1}); assert.ok(Date.parse(planned.blocks[0].start) >= Date.parse('2026-08-17T10:00:00.000Z'));
  const view = projectTodayView({plan: planned, tasks: [taskValue()], profile: configured, now: instant}); assert.doesNotMatch(JSON.stringify(view), /private-reminder/);
  await assert.rejects(reminders.applyOperation({kind: 'reminder_upsert', targetId: 'x', idempotencyKey: 'a'.repeat(64), payload: {listId: 'aware', title: 'x', dueAt: null, notes: '', externalId: 'x'}}), error => error.kind === 'out_of_scope');
});

test('delegations retain Jira state and merge only an exact description marker match', async t => {
  const exactId = '550e8400-e29b-41d4-a716-446655440000'; const unmatchedId = '650e8400-e29b-41d4-a716-446655440000'; const needsId = '750e8400-e29b-41d4-a716-446655440000';
  const jiraTask = taskValue({description: `Details\nrhize-delegation:v1:${exactId}`});
  const delegation = (id, jira) => ({schemaVersion: 1, workspaceId: 'W', channelId: 'C', senderId: 'B', delegationId: id, ingestionKey: `W:C:${id}`, title: `Delegation ${id[0]}`, dueDate: '2026-08-20', priority: 'normal', jira, state: jira.kind === 'needs_jira' ? 'needs_jira' : 'jira_linked', planningLane: 'provisional', approval: 'required', schedulable: false});
  const connectors = emptyConnectors({jira: {async readSnapshot() { return [jiraTask]; }, async health() { return {ok: true}; }}, slack: {async readSnapshot() { return [delegation(exactId, {kind: 'key', value: 'R-1'}), delegation(unmatchedId, {kind: 'key', value: 'R-2'}), delegation(needsId, {kind: 'needs_jira', value: null})]; }, async health() { return {ok: true}; }}});
  const {context} = await contextFixture(t, {connectors}); context.repositories.preferences.set('profile', profile()); await context.sync.readAll(); await context.sync.readAll(); const tasks = context.repositories.tasks.list();
  assert.equal(tasks.find(item => item.id === 'jira-1').delegationId, exactId); assert.equal(tasks.some(item => item.id === `delegation:${exactId}`), false);
  const linked = tasks.find(item => item.id === `delegation:${unmatchedId}`); assert.equal(linked.status, 'Jira Linked'); assert.equal(linked.jiraKey, 'R-2'); assert.equal(linked.lane, 'provisional');
  const needs = tasks.find(item => item.id === `delegation:${needsId}`); assert.equal(needs.status, 'Needs Jira'); assert.equal(needs.lane, 'provisional'); assert.equal(tasks.length, 3);
});

test('dashboard assets are allowlisted and a short-lived nonce is single-use without exposing the bearer', async t => {
  const root = await mkdtemp(path.join(tmpdir(), 'rhize-task7-dashboard-')); t.after(() => rm(root, {recursive: true, force: true})); await Promise.all([writeFile(path.join(root, 'index.html'), '<!doctype html><title>Local</title>'), writeFile(path.join(root, 'app.js'), 'export {};'), writeFile(path.join(root, 'styles.css'), 'body{}')]);
  let current = new Date(instant); const fixture = await httpFixture(t, {dashboardRoot: root, now: () => current});
  assert.equal((await fixture.request('/', {auth: false})).status, 200); assert.equal((await fixture.request('/app.js', {auth: false})).status, 200); assert.equal((await fixture.request('/v1/preferences', {auth: false})).status, 401);
  const traversalStatus = await new Promise((resolve, reject) => { const request = http.request({host: '127.0.0.1', port: fixture.server.address().port, path: '/../app.js'}, response => { response.resume(); response.on('end', () => resolve(response.statusCode)); }); request.on('error', reject); request.end(); }); assert.equal(traversalStatus, 404);
  const issued = fixture.context.sessions.issue(); const exchange = await fixture.request(`/session?nonce=${encodeURIComponent(issued.nonce)}`, {auth: false, redirect: 'manual'}); assert.equal(exchange.status, 303); const cookie = exchange.headers.get('set-cookie'); assert.match(cookie, /HttpOnly/); assert.match(cookie, /SameSite=Strict/); assert.equal((await fixture.request(`/session?nonce=${encodeURIComponent(issued.nonce)}`, {auth: false, redirect: 'manual'})).status, 401);
  assert.equal((await fixture.request('/v1/preferences', {auth: false, headers: {cookie}})).status, 200); assert.equal((await fixture.request('/v1/pause', {method: 'POST', auth: false, headers: {cookie}, body: {planRevision: 0, paused: true}})).status, 401);
  const expired = fixture.context.sessions.issue(); current = new Date(Date.parse(instant) + 61_000); assert.equal((await fixture.request(`/session?nonce=${encodeURIComponent(expired.nonce)}`, {auth: false, redirect: 'manual'})).status, 401); assert.doesNotMatch(JSON.stringify(fixture.context.repositories.audit.list()), new RegExp(expired.nonce));
});
