// Regression coverage for the round-3 external code review (rhize-tasks-feedback-for-jim.md),
// findings #7 (context.mjs status-mapping portion), #11, #12, #13, #15, #16, #17, #18, and the
// #25 sub-items owned by the API/dashboard/storage layer: doctor blindness, session-map sweep,
// and repeat opportunity claim 500->409.
//
// Safety: every server binds to an ephemeral port (0), no launchctl/security command is ever
// invoked (systemProbe is always faked here), and no test makes a real network call (transport
// is always faked when reached).

import assert from 'node:assert/strict';
import http from 'node:http';
import {mkdtemp, rm} from 'node:fs/promises';
import {readFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import path from 'node:path';
import test from 'node:test';

import {createServiceContext} from '../../service/src/api/context.mjs';
import {createServer} from '../../service/src/api/server.mjs';
import {uninstallCleanupRequest} from '../../service/src/api/cleanup.mjs';
import {openDatabase} from '../../service/src/storage/database.mjs';
import {operationKey} from '../../service/src/domain.mjs';
import {renderArtifact} from '../../dashboard/artifact.mjs';
import {createApiRequest} from '../../dashboard/app.js';

const token = 'fix-round-three-api-token-value-32chars';
const instant = '2026-08-17T09:00:00.000Z';

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

function emptyConnectors(overrides = {}) {
  const empty = {async readSnapshot() { return []; }, async health() { return {ok: true}; }};
  return {jira: empty, calendar: empty, reminders: empty, slack: empty, ...overrides};
}

const fakeKeychain = () => ({async get(service, account) { return service === 'media.rhize.tasks.api' && account === 'bearer' ? token : 'credential'; }, async set() {}, async delete() {}});

async function fixture(t, options = {}) {
  const directory = await mkdtemp(path.join(tmpdir(), 'rhize-task7-fix3-'));
  const context = await createServiceContext({
    databasePath: path.join(directory, 'state.sqlite'),
    keychain: options.keychain ?? fakeKeychain(),
    connectors: options.connectors ?? emptyConnectors(),
    transport: options.transport,
    systemProbe: options.systemProbe,
    now: options.now ?? (() => new Date(instant)),
  });
  t.after(() => { context.close(); return rm(directory, {recursive: true, force: true}); });
  const server = createServer(context);
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  const base = `http://127.0.0.1:${server.address().port}`;
  t.after(() => new Promise(resolve => server.close(resolve)));
  const request = async (pathname, {method = 'GET', body, auth = true, headers = {}, redirect} = {}) => {
    const response = await fetch(`${base}${pathname}`, {method, redirect, headers: {...(auth ? {authorization: `Bearer ${token}`} : {}), ...(body === undefined ? {} : {'content-type': 'application/json'}), ...headers}, body: body === undefined ? undefined : JSON.stringify(body)});
    const text = await response.text();
    return {status: response.status, headers: response.headers, body: text && response.headers.get('content-type')?.includes('json') ? JSON.parse(text) : text};
  };
  return {context, server, base, request};
}

// --- #7: kind:'authorization' -> 'revoked', everything else network-ish -> 'offline' ------

test('#7 doctor and plan-preview freshness map connector error kind, not implementation details', async t => {
  const authError = Object.assign(new Error('bad token'), {kind: 'authorization'});
  const networkError = Object.assign(new Error('timeout'), {kind: 'timeout'});
  const connectors = {
    jira: {async readSnapshot() { throw authError; }, async health() { throw authError; }},
    calendar: {async readSnapshot() { throw networkError; }, async health() { throw networkError; }},
    reminders: {async readSnapshot() { return []; }, async health() { return {ok: true}; }},
    slack: {async readSnapshot() { return []; }, async health() { return {ok: true}; }},
  };
  const {context} = await fixture(t, {connectors, systemProbe: {async agentLoaded() { return null; }, async plistNodePathExists() { return null; }, async installedRuntimeVersion() { return null; }}});
  context.repositories.preferences.set('profile', profile());
  const doctor = await context.doctor();
  assert.equal(doctor.connectors.jira, 'revoked');
  assert.equal(doctor.connectors.calendar, 'offline');
  assert.equal(doctor.connectors.reminders, 'healthy');
  const preview = await context.plans.preview({baseRevision: 0});
  assert.equal(preview.freshness.jira.status, 'revoked');
  assert.equal(preview.freshness.calendar.status, 'offline');
});

// --- #11: artifact rendering must not treat untrusted content as a replace() pattern -------

test('#11 artifact rendering survives Jira titles that are dollar-sign replacement patterns', () => {
  const baseView = title => ({
    schemaVersion: 1, planRevision: 1, generatedAt: '2026-08-17T00:00:00.000Z',
    currentBlock: null, nextBlock: null,
    capacity: {plannedMinutes: 1, availableMinutes: 1, bufferMinutes: 1, risk: 'low'},
    timeline: [{start: 'a', end: 'b', title, kind: 'focus'}],
    carryovers: [], approvals: [], opportunities: [], warnings: [],
    connectors: {}, paused: false, degraded: false,
  });
  for (const title of ['Normal title', 'Fix $<10 rounding', 'A$`B', "Tom's $'quote"]) {
    const html = renderArtifact(baseView(title));
    assert.equal((html.match(/<!doctype/gi) ?? []).length, 1, title);
    assert.equal(html.includes('{{TODAY_CONTENT}}'), false, title);
    assert.equal(html.includes('{{TODAY_VIEW_JSON}}'), false, title);
  }
});

// --- #12: setup-probe orphan protection, concurrency guard, and cleanup wiring -------------

test('#12 previewing a new setup probe while a prior one is stranded is refused, not silently overwritten', async t => {
  const {context} = await fixture(t);
  context.repositories.preferences.set('approved_setup_scopes', {reminders: {awarenessListIds: [], tasksListId: 'tasks'}, calendar: {readCalendarIds: ['focus'], focusCalendarId: 'focus'}});
  context.repositories.preferences.set('pending_setup_probe', {state: 'reconciliation_required', probeId: 'orphan-1', planRevision: 0, exact: {remindersListId: 'tasks', focusCalendarId: 'focus'}});
  assert.throws(() => context.setupProbe.preview({planRevision: 0, remindersListId: 'tasks', focusCalendarId: 'focus'}), error => error.status === 409 && error.detail?.probeId === 'orphan-1');
  assert.equal(context.repositories.preferences.get('pending_setup_probe').probeId, 'orphan-1');
});

test('#12 previewing again is fine once the prior probe was only awaiting approval (nothing external touched yet)', async t => {
  const {context} = await fixture(t);
  context.repositories.preferences.set('approved_setup_scopes', {reminders: {awarenessListIds: [], tasksListId: 'tasks'}, calendar: {readCalendarIds: ['focus'], focusCalendarId: 'focus'}});
  const first = context.setupProbe.preview({planRevision: 0, remindersListId: 'tasks', focusCalendarId: 'focus'});
  const second = context.setupProbe.preview({planRevision: 0, remindersListId: 'tasks', focusCalendarId: 'focus'});
  assert.notEqual(second.probeId, first.probeId);
  assert.equal(context.repositories.preferences.get('pending_setup_probe').probeId, second.probeId);
});

test('#12 concurrent apply attempts against the same probe are rejected server-side instead of both racing to create', async t => {
  let inFlight = 0; let maxConcurrent = 0;
  const stall = async () => { inFlight += 1; maxConcurrent = Math.max(maxConcurrent, inFlight); await new Promise(resolve => setTimeout(resolve, 20)); inFlight -= 1; return null; };
  const connectors = {
    jira: {async readSnapshot() { return []; }, async health() { return {ok: true}; }},
    calendar: {async readSnapshot() { return []; }, async health() { return {ok: true}; }, findByExternalId: stall, async applyOperation() { return {externalId: 'evt', revision: 'e1'}; }},
    reminders: {async readSnapshot() { return []; }, async health() { return {ok: true}; }, async findByExternalId() { return null; }, async applyOperation(value) { return {externalId: value.targetId, revision: 'r1'}; }},
    slack: {async readSnapshot() { return []; }, async health() { return {ok: true}; }},
  };
  const {context} = await fixture(t, {connectors});
  context.repositories.preferences.set('approved_setup_scopes', {reminders: {awarenessListIds: [], tasksListId: 'tasks'}, calendar: {readCalendarIds: ['focus'], focusCalendarId: 'focus'}});
  const preview = context.setupProbe.preview({planRevision: 0, remindersListId: 'tasks', focusCalendarId: 'focus'});
  const [first, second] = await Promise.allSettled([
    context.setupProbe.apply({planRevision: 0, probeId: preview.probeId, actor: 'tom'}),
    context.setupProbe.apply({planRevision: 0, probeId: preview.probeId, actor: 'tom'}),
  ]);
  const rejected = [first, second].filter(result => result.status === 'rejected');
  assert.equal(rejected.length >= 1, true);
  assert.ok(rejected.some(result => result.reason?.kind === 'setup_probe_busy'));
  assert.equal(maxConcurrent, 1);
});

test('#12 cleanup finds an orphaned setup-probe item even though it never went through the operations table', async t => {
  const remindersCalls = [];
  const remindersPresent = new Set(['access-probe:orphan-1']);
  const remindersConnector = {
    async readSnapshot() { return [...remindersPresent].map(id => ({id})); },
    async applyOperation(operation) { remindersCalls.push(operation); if (operation.kind === 'reminder_delete') remindersPresent.delete(operation.targetId); return {externalId: operation.targetId, revision: 'r1'}; },
  };
  const calendarOperationKey = operationKey(1, 'calendar_upsert', 'orphan-1', {probeId: 'orphan-1'});
  const transportCalls = [];
  const transport = async ({url, method}) => {
    transportCalls.push({url, method});
    if (url === 'https://oauth2.googleapis.com/token') return {status: 200, body: {access_token: 'tok'}};
    if (method === 'GET') { const alreadyDeleted = transportCalls.some(call => call.method === 'DELETE'); return {status: 200, body: {items: alreadyDeleted ? [] : [{id: 'calendar-event-1', extendedProperties: {private: {rhizeOperationKey: calendarOperationKey}}}]}}; }
    if (method === 'DELETE') return {status: 204};
    throw new Error(`unexpected request ${method} ${url}`);
  };
  const {context} = await fixture(t, {connectors: emptyConnectors({reminders: remindersConnector}), transport});
  context.repositories.preferences.set('profile', profile());
  const reminderPayload = {listId: 'tasks', title: 'Rhize Tasks access check', dueAt: null, notes: 'probe', externalId: 'access-probe:orphan-1'};
  const calendarPayload = {calendarId: 'focus', title: 'Rhize Tasks access check', start: '2026-08-17T09:05:00.000Z', end: '2026-08-17T09:20:00.000Z', description: 'probe', externalId: 'access-probe:orphan-1', operationKey: calendarOperationKey, taskId: 'setup-probe:orphan-1', blockSlot: 'setup-probe:orphan-1:1'};
  context.repositories.preferences.set('pending_setup_probe', {
    state: 'reconciliation_required', probeId: 'orphan-1', planRevision: 0,
    reminder: {schemaVersion: 1, id: 'setup-probe:reminder_upsert:orphan', planRevision: 1, kind: 'reminder_upsert', targetSystem: 'reminders', targetId: 'access-probe:orphan-1', payload: reminderPayload, idempotencyKey: operationKey(1, 'reminder_upsert', 'access-probe:orphan-1', reminderPayload), approval: 'approved', preconditionRevision: null, retryState: 'pending', createdAt: instant},
    calendar: {schemaVersion: 1, id: 'setup-probe:calendar_upsert:orphan', planRevision: 1, kind: 'calendar_upsert', targetSystem: 'calendar', targetId: null, payload: calendarPayload, idempotencyKey: operationKey(1, 'calendar_upsert', null, calendarPayload), approval: 'approved', preconditionRevision: null, retryState: 'pending', createdAt: instant},
    exact: {remindersListId: 'tasks', focusCalendarId: 'focus', reminderExternalId: 'access-probe:orphan-1', calendarOperationKey},
  });
  const result = await context.cleanup(uninstallCleanupRequest);
  assert.equal(result.ok, true);
  assert.equal(result.reminders.deleted, 1);
  assert.equal(result.calendar.deleted, 1);
  assert.ok(remindersCalls.some(operation => operation.kind === 'reminder_delete' && operation.targetId === 'access-probe:orphan-1'));
  assert.ok(transportCalls.some(call => call.method === 'DELETE'));
});

// --- #15: discovery path enforces https on jiraBaseUrl (token exfiltration) ----------------

test('#15 jira discovery rejects a non-https baseUrl before ever constructing a connector', async t => {
  const directory = await mkdtemp(path.join(tmpdir(), 'rhize-task7-fix3-discovery-'));
  const context = await createServiceContext({databasePath: path.join(directory, 'state.sqlite'), keychain: fakeKeychain(), transport: async () => { throw new Error('no real network in tests'); }, now: () => new Date(instant)});
  t.after(() => { context.close(); return rm(directory, {recursive: true, force: true}); });
  context.repositories.preferences.set('setup_stages', {2: {complete: true, data: {jiraBaseUrl: 'http://attacker.example', jiraAccountId: 'tom'}}});
  await assert.rejects(context.connectorRegistry.getDiscovery('jira'), /https/i);
  context.repositories.preferences.set('setup_stages', {2: {complete: true, data: {jiraBaseUrl: 'https://jira.example', jiraAccountId: 'tom'}}});
  const adapter = await context.connectorRegistry.getDiscovery('jira');
  assert.equal(typeof adapter.discover, 'function');
});

// --- #16: /session must validate before it burns the nonce ---------------------------------

test('#16 exchanging the wrong nonce does not consume the pending bootstrap secret', async t => {
  const {context} = await fixture(t);
  const issued = context.sessions.issue();
  assert.throws(() => context.sessions.exchange('not-the-right-nonce'), error => error.status === 401);
  const cookie = context.sessions.exchange(issued.nonce);
  assert.match(cookie, /rhize_tasks_session=/);
});

test('#16 a nonce-guessing loop cannot burn a still-pending bootstrap before its real owner arrives', async t => {
  const {context} = await fixture(t);
  const issued = context.sessions.issue();
  for (let attempt = 0; attempt < 20; attempt += 1) assert.throws(() => context.sessions.exchange(`guess-${attempt}`), error => error.status === 401);
  assert.doesNotThrow(() => context.sessions.exchange(issued.nonce));
});

// --- #17: Origin-if-present + a custom header on side-effectful discovery GETs, plus Host --

test('#17 a cookie-authenticated GET to a discovery endpoint is refused without the dashboard header', async t => {
  const {context, request} = await fixture(t, {connectors: emptyConnectors({jira: {async readSnapshot() { return []; }, async health() { return {ok: true}; }, async discover() { return {projects: [], issueTypes: []}; }}})});
  const issued = context.sessions.issue();
  const exchange = await request(`/session?nonce=${encodeURIComponent(issued.nonce)}`, {auth: false, redirect: 'manual'});
  const cookie = exchange.headers.get('set-cookie');
  context.repositories.preferences.set('setup_stages', {2: {complete: true, data: {jiraBaseUrl: 'https://jira.example', jiraAccountId: 'tom'}}});
  const withoutHeader = await request('/v1/setup/discover/jira', {auth: false, headers: {cookie}});
  assert.equal(withoutHeader.status, 401);
  const withHeader = await request('/v1/setup/discover/jira', {auth: false, headers: {cookie, 'x-rhize-tasks-dashboard': '1'}});
  assert.equal(withHeader.status, 200);
});

test('#17 the dashboard header is required on every cookie-authenticated request, not just discovery GETs (Codex finding 7)', async t => {
  // GET /v1/doctor is a plain read from the URL's point of view but runs real side effects
  // (connector health checks: outbound token refresh, spawning the Reminders helper) — a page
  // on another 127.0.0.1 port could trigger it as an unreadable subresource if the header
  // requirement were scoped to only the four discovery endpoints, as it originally was.
  const {context, request} = await fixture(t);
  const issued = context.sessions.issue();
  const exchange = await request(`/session?nonce=${encodeURIComponent(issued.nonce)}`, {auth: false, redirect: 'manual'});
  const cookie = exchange.headers.get('set-cookie');
  const withoutHeader = await request('/v1/preferences', {auth: false, headers: {cookie}});
  assert.equal(withoutHeader.status, 401);
  const doctorWithoutHeader = await request('/v1/doctor', {auth: false, headers: {cookie}});
  assert.equal(doctorWithoutHeader.status, 401);
  const withHeader = await request('/v1/preferences', {auth: false, headers: {cookie, 'x-rhize-tasks-dashboard': '1'}});
  assert.equal(withHeader.status, 200);
});

test('#17 a mismatched Host header is refused even from a loopback socket', async t => {
  const {server} = await fixture(t);
  const status = await new Promise((resolve, reject) => {
    const req = http.request({host: '127.0.0.1', port: server.address().port, path: '/health', headers: {host: 'evil.example:9999'}}, response => { response.resume(); response.on('end', () => resolve(response.statusCode)); });
    req.on('error', reject); req.end();
  });
  assert.equal(status, 403);
});

// --- #18: SQLite is opened with WAL + a real busy_timeout, not an instant-fail lock --------

test('#18 database opens with WAL journal mode and a nonzero busy_timeout', async t => {
  const directory = await mkdtemp(path.join(tmpdir(), 'rhize-task7-fix3-wal-'));
  t.after(() => rm(directory, {recursive: true, force: true}));
  const db = openDatabase(path.join(directory, 'state.sqlite'));
  t.after(() => db.close());
  assert.equal(db.prepare('pragma journal_mode').get().journal_mode, 'wal');
  assert.equal(db.prepare('pragma busy_timeout').get().timeout, 5000);
});

// --- #25: doctor blindness, VERSION from package.json, session cap, claim 409 --------------

test('#25 doctor reports agent/plist/runtime-version/last-routine-run best-effort via an injectable probe', async t => {
  const {context} = await fixture(t, {systemProbe: {async agentLoaded() { return true; }, async plistNodePathExists() { return false; }, async installedRuntimeVersion() { return '9.9.9'; }}});
  context.repositories.preferences.set('profile', profile());
  const id = await context.routineState.begin('catch-up', new Date(instant), {catchUp: false});
  await context.routineState.complete(id, 'completed', {});
  const doctor = await context.doctor();
  assert.equal(doctor.agentLoaded, true);
  assert.equal(doctor.plistNodePathExists, false);
  assert.equal(doctor.runtimeVersionMatch, false);
  assert.equal(doctor.lastRoutineRun, instant);
});

test('#25 doctor system-probe failures degrade to null (best-effort) rather than throwing', async t => {
  const {context} = await fixture(t, {systemProbe: {async agentLoaded() { throw new Error('nope'); }, async plistNodePathExists() { throw new Error('nope'); }, async installedRuntimeVersion() { throw new Error('nope'); }}});
  const doctor = await context.doctor();
  assert.equal(doctor.agentLoaded, null);
  assert.equal(doctor.plistNodePathExists, null);
  assert.equal(doctor.runtimeVersionMatch, null);
});

test('#25 VERSION is read from package.json, not hardcoded', async t => {
  const packageVersion = JSON.parse(readFileSync(new URL('../../package.json', import.meta.url), 'utf8')).version;
  const {context} = await fixture(t);
  assert.equal(context.version, packageVersion);
});

test('#25 the dashboard session map is bounded so it cannot grow without limit across launches', async t => {
  const {context} = await fixture(t);
  const cookies = [];
  for (let index = 0; index < 55; index += 1) {
    const issued = context.sessions.issue();
    const raw = context.sessions.exchange(issued.nonce);
    cookies.push(raw.split(';')[0]);
  }
  const fakeRequest = cookie => ({headers: {cookie, 'x-rhize-tasks-dashboard': '1'}, method: 'GET'});
  assert.equal(context.sessions.authenticate(fakeRequest(cookies[0])), false);
  assert.equal(context.sessions.authenticate(fakeRequest(cookies.at(-1))), true);
});

test('#25 a repeat opportunity claim at the same plan revision is a 409 conflict, not a 500', async t => {
  const {context, request} = await fixture(t);
  context.repositories.tasks.upsert({schemaVersion: 1, id: 'task-1', sourceType: 'jira', lane: 'opportunity', title: 'Audit', projectKey: 'R', issueType: 'Task', assigneeAccountId: null, priority: 'high', dueDate: null, status: 'Open', terminal: false, blocked: false, dependencyRisk: 0, remainingMinutes: 60, explicitEstimateMinutes: null, competencies: ['ops'], manualLock: false, carryoverCount: 0, createdAt: instant, reserved: false, sourceRevision: 'r1', jiraKey: 'R-1'});
  // Operations must reference a real plan revision (the `operations` table has a foreign key
  // onto `plans`), so a plan has to exist before anything can be claimed against it.
  context.repositories.preferences.set('approved_setup_scopes', {jira: {projectKeys: ['R'], issueTypes: ['Task']}, calendar: {readCalendarIds: ['outside', 'focus'], focusCalendarId: 'focus'}, reminders: {awarenessListIds: [], tasksListId: 'tasks'}});
  assert.equal((await request('/v1/preferences', {method: 'PUT', body: {planRevision: 0, profile: profile()}})).status, 200);
  assert.equal((await request('/v1/plans/preview', {method: 'POST', body: {planRevision: 0}})).status, 201);
  const first = await request('/v1/opportunities/task-1/claim', {method: 'POST', body: {planRevision: 1, actor: 'tom', accountId: 'tom'}});
  assert.equal(first.status, 200);
  const repeat = await request('/v1/opportunities/task-1/claim', {method: 'POST', body: {planRevision: 1, actor: 'tom', accountId: 'tom'}});
  assert.equal(repeat.status, 409);
  assert.equal(repeat.body.error.kind, 'opportunity_already_claimed');
  const differentAccount = await request('/v1/opportunities/task-1/claim', {method: 'POST', body: {planRevision: 1, actor: 'tom', accountId: 'someone-else'}});
  assert.equal(differentAccount.status, 200);
});

// --- Codex adversarial-review follow-ups on the combined diff -----------------------------

// Finding 5 (MAJOR): scope_expand proposals saved through repositories.operations had three
// concrete failure modes. Chosen fix: proposals never touch repositories.operations/plans at
// all — they live entirely in the `pending_scope_change` preferences record (mirroring
// `previewSetupScope`'s already-working pattern), with a random id per proposal.

test('Codex#5a proposing a scope expansion works even when no plan has ever been previewed (no FK insert)', async t => {
  const {context} = await fixture(t);
  context.repositories.preferences.set('approved_setup_scopes', {jira: {projectKeys: ['R'], issueTypes: ['Task']}, calendar: {readCalendarIds: ['outside', 'focus'], focusCalendarId: 'focus'}, reminders: {awarenessListIds: [], tasksListId: 'tasks'}});
  await context.settings.proposeProfile(profile());
  assert.equal(context.repositories.plans.latest(), null);
  const expanded = profile({jira: {...profile().jira, issueTypes: ['Task', 'Bug']}});
  const result = await context.settings.proposeProfile(expanded);
  assert.equal(result.status, 'approval_required');
  assert.equal(result.operations.length, 1);
  assert.equal(context.repositories.preferences.get('profile').jira.issueTypes.includes('Bug'), false);
});

test('Codex#5b a pending scope change is immune to the generic plan-approval/apply path', async t => {
  const {context} = await fixture(t);
  context.repositories.preferences.set('approved_setup_scopes', {jira: {projectKeys: ['R'], issueTypes: ['Task']}, calendar: {readCalendarIds: ['outside', 'focus'], focusCalendarId: 'focus'}, reminders: {awarenessListIds: [], tasksListId: 'tasks'}});
  await context.settings.proposeProfile(profile());
  await context.plans.preview({baseRevision: 0}); // plan revision 1, pending
  const expanded = profile({jira: {...profile().jira, issueTypes: ['Task', 'Bug']}});
  const proposed = await context.settings.proposeProfile(expanded);
  assert.equal(context.repositories.operations.listForPlan(1).length, 0, 'the scope proposal must never appear in the plan-1 operations list');
  // Approving plan revision 1 through the ordinary path must not touch the scope proposal at all.
  const approved = await context.plans.approve(1, 'tom', true);
  assert.deepEqual(approved.results, []);
  const pending = context.repositories.preferences.get('pending_scope_change');
  assert.equal(pending.operations[0].id, proposed.operations[0].id);
  assert.equal(pending.operations[0].approval, 'required', 'still untouched, not silently approved/dispatched/stranded by the generic plan apply');
});

test('Codex#5c re-proposing the same connector+resources after a resolved cycle gets a fresh id, not a collision', async t => {
  const {context} = await fixture(t);
  context.repositories.preferences.set('approved_setup_scopes', {jira: {projectKeys: ['R'], issueTypes: ['Task']}, calendar: {readCalendarIds: ['outside', 'focus'], focusCalendarId: 'focus'}, reminders: {awarenessListIds: [], tasksListId: 'tasks'}});
  await context.settings.proposeProfile(profile());
  const expanded = profile({jira: {...profile().jira, issueTypes: ['Task', 'Bug']}});
  const first = await context.settings.proposeProfile(expanded);
  const approved = await context.settings.approveScope(first.operations[0].id, 'tom');
  assert.equal(approved.state, 'applied');
  // Narrow back, then re-expand to the exact same connector+resources at a later moment.
  await context.settings.proposeProfile(profile());
  const second = await context.settings.proposeProfile(expanded);
  assert.equal(second.status, 'approval_required');
  assert.notEqual(second.operations[0].id, first.operations[0].id);
});

test('Codex#5 end-to-end: propose, discover via setup status, approve, and the profile is applied', async t => {
  const {context, request} = await fixture(t);
  context.repositories.preferences.set('approved_setup_scopes', {jira: {projectKeys: ['R'], issueTypes: ['Task']}, calendar: {readCalendarIds: ['outside', 'focus'], focusCalendarId: 'focus'}, reminders: {awarenessListIds: [], tasksListId: 'tasks'}});
  assert.equal((await request('/v1/preferences', {method: 'PUT', body: {planRevision: 0, profile: profile()}})).status, 200);
  const expanded = profile({jira: {...profile().jira, issueTypes: ['Task', 'Bug']}});
  const proposed = await request('/v1/preferences', {method: 'PUT', body: {planRevision: 0, profile: expanded}});
  assert.equal(proposed.status, 202); assert.equal(proposed.body.approvalRequired, true);
  const status = await request('/v1/setup/status');
  assert.equal(status.body.pendingScopeChange.operations.length, 1);
  assert.equal(status.body.pendingScopeChange.operations[0].connector, 'jira');
  const operationId = status.body.pendingScopeChange.operations[0].id;
  const approved = await request(`/v1/operations/${encodeURIComponent(operationId)}/approve`, {method: 'POST', body: {planRevision: 0, actor: 'tom'}});
  assert.equal(approved.status, 200); assert.equal(approved.body.state, 'applied');
  assert.deepEqual(context.repositories.preferences.get('profile').jira.issueTypes, ['Task', 'Bug']);
  assert.equal((await request('/v1/setup/status')).body.pendingScopeChange, null);
});

test('Codex#5-atomic settings.approveScope\'s final approval is all-or-nothing under a crash mid-sequence', async t => {
  const {context} = await fixture(t);
  context.repositories.preferences.set('approved_setup_scopes', {jira: {projectKeys: ['R'], issueTypes: ['Task']}, calendar: {readCalendarIds: ['outside', 'focus'], focusCalendarId: 'focus'}, reminders: {awarenessListIds: [], tasksListId: 'tasks'}});
  await context.settings.proposeProfile(profile());
  const expanded = profile({jira: {...profile().jira, issueTypes: ['Task', 'Bug']}});
  const proposed = await context.settings.proposeProfile(expanded);
  const operationId = proposed.operations[0].id;
  // Simulate a crash between the individual writes that used to be separate auto-committed
  // statements: let every earlier write in the sequence (marking the operation approved, the
  // profile update, the approved_setup_scopes update, deleting pending_scope_change) actually
  // run, then fail on the very LAST one (the closing audit entry). If the whole sequence is
  // genuinely one transaction, that failure must roll back everything that came before it too.
  const realAppend = context.repositories.audit.append.bind(context.repositories.audit);
  context.repositories.audit.append = (event, ...rest) => { if (event === 'scope_change_applied') throw new Error('simulated crash before final commit'); return realAppend(event, ...rest); };
  try {
    await assert.rejects(context.settings.approveScope(operationId, 'tom'), /simulated crash/);
  } finally {
    context.repositories.audit.append = realAppend;
  }
  // Nothing from the failed attempt may have stuck: profile unchanged, the operation still
  // shows 'required' (not stranded half-approved), and a fresh, uninterrupted retry succeeds.
  assert.equal(context.repositories.preferences.get('profile').jira.issueTypes.includes('Bug'), false);
  const pendingAfterCrash = context.repositories.preferences.get('pending_scope_change');
  assert.ok(pendingAfterCrash, 'pending_scope_change must still exist for the retry to be possible');
  assert.equal(pendingAfterCrash.operations[0].approval, 'required');
  const retried = await context.settings.approveScope(operationId, 'tom');
  assert.equal(retried.state, 'applied');
  assert.deepEqual(context.repositories.preferences.get('profile').jira.issueTypes, ['Task', 'Bug']);
  assert.equal(context.repositories.preferences.get('pending_scope_change'), null);
});

// Finding 7 (MAJOR): already covered by the rewritten "#17 the dashboard header is required on
// every cookie-authenticated request" test above, which specifically exercises GET /v1/doctor.

// Finding 10 (MAJOR): setup-probe orphan recovery was unreachable from the dashboard — the 409
// carried the pointer only in error.detail, setup status never exposed it, and the client's
// generic onConflict handler cleared state.probe on every 409 including this one.

test('Codex#10a a stranded setup probe is discoverable through /v1/setup/status, not just the failing request\'s error detail', async t => {
  // Reminders round-trips cleanly (create, findByExternalId sees it, delete on cleanup) so the
  // probe leaves no reminder orphan — only Calendar genuinely fails to reconcile (an ambiguous
  // create error on every attempt), landing state 'reconciliation_required' with a real
  // calendar-side orphan, matching the scenario in the review's finding #12.
  const remindersStore = new Set();
  const connectors = {
    jira: {async readSnapshot() { return []; }, async health() { return {ok: true}; }},
    calendar: {async readSnapshot() { return []; }, async health() { return {ok: true}; }, async findByExternalId() { return null; }, async applyOperation() { throw {kind: 'timeout', ambiguous: true}; }},
    reminders: {async readSnapshot() { return []; }, async health() { return {ok: true}; }, async findByExternalId(id) { return remindersStore.has(id) ? {externalId: id, revision: 'r1'} : null; }, async applyOperation(value) { if (value.kind === 'reminder_delete') { remindersStore.delete(value.targetId); return {externalId: value.targetId, revision: 'deleted'}; } remindersStore.add(value.payload.externalId); return {externalId: value.payload.externalId, revision: 'r1'}; }},
    slack: {async readSnapshot() { return []; }, async health() { return {ok: true}; }},
  };
  const {context, request} = await fixture(t, {connectors});
  context.repositories.preferences.set('approved_setup_scopes', {reminders: {awarenessListIds: [], tasksListId: 'tasks'}, calendar: {readCalendarIds: ['focus'], focusCalendarId: 'focus'}});
  const preview = context.setupProbe.preview({planRevision: 0, remindersListId: 'tasks', focusCalendarId: 'focus'});
  await assert.rejects(context.setupProbe.apply({planRevision: 0, probeId: preview.probeId, actor: 'tom'}));
  const status = await request('/v1/setup/status');
  assert.equal(status.body.pendingSetupProbe.probeId, preview.probeId);
  assert.equal(status.body.pendingSetupProbe.state, 'reconciliation_required');
  assert.equal(status.body.pendingSetupProbe.planRevision, 0);
  assert.deepEqual(status.body.pendingSetupProbe.exact, preview.exact);
});

test('Codex#10b the dashboard client keeps (does not wipe) state on a setup-probe retry conflict, but does wipe it on a real plan-revision conflict', async t => {
  const responses = [
    {status: 409, body: {error: {kind: 'setup_probe_orphan_pending', status: 409, detail: {probeId: 'p1', state: 'reconciliation_required'}}}},
    {status: 409, body: {error: {kind: 'setup_probe_busy', status: 409}}},
    {status: 409, body: {error: {kind: 'reconciliation_required', status: 409}}},
    {status: 409, body: {error: {kind: 'revision_conflict', status: 409}}},
  ];
  let conflictCalls = 0;
  const authState = {token: 'x'};
  const api = createApiRequest({authState, onConflict: async () => { conflictCalls += 1; }, fetchImpl: async () => { const next = responses.shift(); return {status: next.status, headers: {get: () => null}, async json() { return next.body; }}; }});
  for (const kind of ['setup_probe_orphan_pending', 'setup_probe_busy', 'reconciliation_required']) {
    await assert.rejects(api('/v1/setup/probe', {method: 'POST', body: {}}));
  }
  assert.equal(conflictCalls, 0, 'setup-probe-retry kinds must not trigger the generic plan-changed handler');
  await assert.rejects(api('/v1/setup/probe', {method: 'POST', body: {}}));
  assert.equal(conflictCalls, 1, 'an ordinary revision_conflict must still trigger it');
});

// Finding 12 (MINOR): busy_timeout must be set before the journal_mode=wal switch itself, or
// that specific transition races an existing reader/writer with a zero timeout on first
// post-upgrade open.

test('Codex#12 busy_timeout is effective from a database\'s very first open, including through the journal_mode=wal switch', async t => {
  const directory = await mkdtemp(path.join(tmpdir(), 'rhize-task7-fix3-wal-race-'));
  t.after(() => rm(directory, {recursive: true, force: true}));
  const file = path.join(directory, 'state.sqlite');
  // A connection opened synchronously inside the first one's `beforeMigrations` can never
  // actually succeed — the lock holder can't release until the nested call returns, same
  // thread — so this can't prove "no error", only that busy_timeout is genuinely being
  // *waited out* rather than failing instantly, on a BRAND NEW file (the one case that also
  // exercises the journal_mode=wal switch). If busy_timeout were set AFTER journal_mode=wal in
  // a way that left it not-yet-effective for the first open, this would fail near-instantly
  // instead of after ~timeoutMs, the same way storage.test.mjs's "migration locking" test
  // proves busyTimeoutMs:0 fails near-instantly.
  const timeoutMs = 250;
  let waitedMs = 0;
  const first = openDatabase(file, {busyTimeoutMs: timeoutMs, beforeMigrations() {
    const started = Date.now();
    assert.throws(() => openDatabase(file, {busyTimeoutMs: timeoutMs}), /locked|busy/i);
    waitedMs = Date.now() - started;
  }});
  first.close();
  assert.ok(waitedMs >= timeoutMs * 0.7, `expected the nested open to honor busy_timeout (~${timeoutMs}ms) on this brand-new file, waited only ${waitedMs}ms`);
});
