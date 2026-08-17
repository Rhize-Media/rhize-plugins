import assert from 'node:assert/strict';
import test from 'node:test';

import {createGoogleCalendarConnector} from '../../service/src/connectors/google-calendar.mjs';
import {createHttpTransport} from '../../service/src/connectors/http.mjs';
import {createRemindersConnector} from '../../service/src/connectors/reminders.mjs';
import {createSlackConnector} from '../../service/src/connectors/slack.mjs';
import {applyApprovedOperations} from '../../service/src/reconciliation/operations.mjs';
import {operationKey} from '../../service/src/domain.mjs';

const credentials = {async get() { return 'secret'; }};
const ok = body => ({status: 200, headers: {}, body});

function jsonResponse(status, body, headers = {}) {
  return new Response(JSON.stringify(body), {status, headers: {'content-type': 'application/json', ...headers}});
}

// --- #7: Google refresh-token revocation must classify as kind:'authorization' ---

test('Google 400 invalid_grant classifies as authorization, not http/offline', async () => {
  const transport = createHttpTransport({fetch: async () => jsonResponse(400, {error: 'invalid_grant', error_description: 'Token has been expired or revoked.'})});
  const google = createGoogleCalendarConnector({readCalendarIds: ['read'], focusCalendarId: 'focus', credentials, transport});
  await assert.rejects(google.health(), error => error.kind === 'authorization');
});

test('Google 400 with an unrelated error body stays kind:http', async () => {
  const transport = createHttpTransport({fetch: async () => jsonResponse(400, {error: 'invalid_request'})});
  const google = createGoogleCalendarConnector({readCalendarIds: ['read'], focusCalendarId: 'focus', credentials, transport});
  await assert.rejects(google.health(), error => error.kind === 'http' && error.status === 400);
});

// --- #7: Reminders authorization_denied must classify as kind:'authorization' ---

test('Reminders authorization_denied classifies as authorization, not offline', async () => {
  const connector = createRemindersConnector({helperPath: '/helper', tasksListId: 'tasks', runner: async () => ({code: 0, stdout: '{"ok":false,"error":"authorization_denied"}\n'})});
  await assert.rejects(connector.health(), error => error.kind === 'authorization');
});

test('Reminders other helper failures keep their own literal kind (e.g. list_not_found)', async () => {
  const connector = createRemindersConnector({helperPath: '/helper', tasksListId: 'tasks', runner: async () => ({code: 0, stdout: '{"ok":false,"error":"list_not_found"}\n'})});
  await assert.rejects(connector.health(), error => error.kind === 'list_not_found');
});

// --- #8: Google access token is cached in-memory and refreshed ~60s before expiry ---

test('Google caches the access token in memory and only refetches near expiry', async () => {
  let clock = new Date('2026-08-17T12:00:00Z');
  const tokenCalls = [];
  const google = createGoogleCalendarConnector({
    readCalendarIds: ['read'], focusCalendarId: 'focus', credentials,
    now: () => clock,
    transport: async request => {
      if (request.url.includes('/token')) { tokenCalls.push(clock.toISOString()); return ok({access_token: `access-${tokenCalls.length}`, expires_in: 3600}); }
      return ok({items: []});
    },
  });
  await google.health();
  await google.health();
  assert.equal(tokenCalls.length, 1, 'second call within the token lifetime must reuse the cached token');
  clock = new Date(clock.getTime() + 3600 * 1000 - 30_000); // inside the 60s refresh skew
  await google.health();
  assert.equal(tokenCalls.length, 2, 'a call within 60s of expiry must refresh the token');
});

test('Google concurrent requests share one in-flight token refresh (no stampede)', async () => {
  let tokenCalls = 0;
  const google = createGoogleCalendarConnector({
    readCalendarIds: ['cal-a', 'cal-b'], focusCalendarId: 'cal-a', credentials,
    transport: async request => {
      if (request.url.includes('/token')) { tokenCalls += 1; return ok({access_token: 'access-1', expires_in: 3600}); }
      return ok({items: []});
    },
  });
  await google.readSnapshot(); // fans out one request() per calendar via Promise.all
  assert.equal(tokenCalls, 1, 'two calendars read concurrently must share a single token refresh grant');
});

test('Google 401 on a GET triggers exactly one refresh and one retry', async () => {
  let tokenCalls = 0; let listCalls = 0;
  const google = createGoogleCalendarConnector({
    readCalendarIds: ['read'], focusCalendarId: 'focus', credentials,
    transport: async request => {
      if (request.url.includes('/token')) { tokenCalls += 1; return ok({access_token: `access-${tokenCalls}`, expires_in: 3600}); }
      listCalls += 1;
      if (listCalls === 1) return {status: 401, headers: {}, body: {error: {code: 401, message: 'Invalid Credentials'}}};
      return ok({items: []});
    },
  });
  await google.health();
  assert.equal(tokenCalls, 2, 'a 401 must clear the cache and force exactly one refresh');
  assert.equal(listCalls, 2, 'the GET must be retried exactly once after the refresh');
});

test('Google 401 on a write clears the cache but does not auto-retry the mutation', async () => {
  let tokenCalls = 0; let writeCalls = 0;
  const google = createGoogleCalendarConnector({
    readCalendarIds: ['focus'], focusCalendarId: 'focus', credentials,
    now: () => new Date('2026-08-17T12:00:00Z'),
    transport: async request => {
      if (request.url.includes('/token')) { tokenCalls += 1; return ok({access_token: `access-${tokenCalls}`, expires_in: 3600}); }
      if (request.method === 'POST') { writeCalls += 1; return {status: 401, headers: {}, body: {error: {code: 401, message: 'Invalid Credentials'}}}; }
      return ok({items: []}); // the pre-write existing-event search
    },
  });
  const operation = {kind: 'calendar_upsert', targetId: '', idempotencyKey: 'g'.repeat(64), payload: {calendarId: 'focus', title: 'T', description: '', start: '2026-08-17T12:00:00Z', end: '2026-08-17T13:00:00Z'}};
  await assert.rejects(google.applyOperation(operation), error => error.kind === 'authorization' && error.status === 401);
  assert.equal(writeCalls, 1, 'a write must not be auto-retried after a 401 — reconciliation handles the retry');
  assert.equal(tokenCalls, 1, 'the bad token is cleared from the cache but not eagerly re-fetched for a failed write');
});

// --- #9: Retry-After is captured and rate_limit/rate_limited spelling is unified ---

test('HTTP transport captures Retry-After on 429 and classifies as rate_limited', async () => {
  const transport = createHttpTransport({fetch: async () => new Response('{}', {status: 429, headers: {'content-type': 'application/json', 'retry-after': '2'}})});
  await assert.rejects(transport({url: 'https://example.test'}), error => error.kind === 'rate_limited' && error.retryable === true && error.retryAfterMs === 2000);
});

test('HTTP transport tolerates a missing or unparseable Retry-After', async () => {
  const transport = createHttpTransport({fetch: async () => new Response('{}', {status: 429, headers: {'content-type': 'application/json'}})});
  await assert.rejects(transport({url: 'https://example.test'}), error => error.kind === 'rate_limited' && error.retryAfterMs === null);
});

test('reconciliation waits before retrying a retryable failure instead of retrying immediately', async () => {
  const waits = [];
  const sleep = async ms => { waits.push(ms); };
  const repository = createFakeRepository();
  const operation = fakeOperation();
  repository.save(operation);
  const connector = {calls: 0, async findByExternalId() { return {revision: '17'}; }, async applyOperation() { this.calls += 1; throw {kind: 'rate_limited', retryable: true, ambiguous: false, retryAfterMs: 5000}; }};
  const results = await applyApprovedOperations({repository, connectors: {reminders: connector}, currentRevision: 3, sleep}, [operation]);
  assert.equal(connector.calls, 2, 'one immediate attempt plus one retry within the persisted two-attempt budget');
  assert.deepEqual(waits, [5000]);
  assert.equal(results[0].state, 'failed');
});

test('reconciliation caps the wait at 30s and falls back to a short default backoff without Retry-After', async () => {
  const waits = [];
  const sleep = async ms => { waits.push(ms); };
  const repository = createFakeRepository();
  const capped = fakeOperation({id: 'op-capped'});
  repository.save(capped);
  const hugeRetryAfter = {calls: 0, async findByExternalId() { return {revision: '17'}; }, async applyOperation() { this.calls += 1; throw {kind: 'rate_limited', retryable: true, ambiguous: false, retryAfterMs: 120_000}; }};
  await applyApprovedOperations({repository, connectors: {reminders: hugeRetryAfter}, currentRevision: 3, sleep}, [capped]);
  assert.deepEqual(waits, [30_000]);

  waits.length = 0;
  const noHeader = fakeOperation({id: 'op-default'});
  repository.save(noHeader);
  const noRetryAfter = {calls: 0, async findByExternalId() { return {revision: '17'}; }, async applyOperation() { this.calls += 1; throw {kind: 'timeout', retryable: true, ambiguous: false}; }};
  await applyApprovedOperations({repository, connectors: {reminders: noRetryAfter}, currentRevision: 3, sleep}, [noHeader]);
  assert.deepEqual(waits, [1500]);
});

// --- #10: Slack un-escapes mrkdwn before delegation parsing, caps pagination, logs (not throws) on parse failure ---

function validDelegationText(jiraField) {
  return `*Task:* Audit\n*Due:* 2026-08-17\n*Priority:* high\n*Jira:* ${jiraField}\nrhize-delegation:v1:550e8400-e29b-41d4-a716-446655440000`;
}

test('Slack un-escapes a real Slack-formatted Jira URL before delegation parsing', async () => {
  const escaped = validDelegationText('<https://example.atlassian.net/browse/ABC-1>');
  const requests = [];
  const slack = createSlackConnector({
    workspaceId: 'T1', channelId: 'C1', senderIds: ['B1'], credentials,
    transport: async request => { requests.push(request); return request.url.includes('history') ? ok({ok: true, messages: [{ts: '1', thread_ts: '1'}]}) : ok({ok: true, messages: [{ts: '1'}, {bot_id: 'B1', text: escaped}]}); },
  });
  const items = await slack.readSnapshot();
  assert.equal(items.length, 1);
  assert.deepEqual(items[0].jira, {kind: 'url', value: 'https://example.atlassian.net/browse/ABC-1'});
});

test('Slack decodes HTML entities and a piped link label', async () => {
  const escaped = validDelegationText('needs_jira').replace('Audit', 'Fix &lt;Q3&gt; goals &amp; scope');
  const slack = createSlackConnector({
    workspaceId: 'T1', channelId: 'C1', senderIds: ['B1'], credentials,
    transport: async request => request.url.includes('history') ? ok({ok: true, messages: [{ts: '1', thread_ts: '1'}]}) : ok({ok: true, messages: [{ts: '1'}, {bot_id: 'B1', text: escaped}]}),
  });
  const [item] = await slack.readSnapshot();
  assert.equal(item.title, 'Fix <Q3> goals & scope');
});

test('Slack skips an unparseable delegation message without throwing and still returns valid ones', async () => {
  const valid = validDelegationText('needs_jira');
  const originalWrite = process.stderr.write;
  const logged = [];
  process.stderr.write = chunk => { logged.push(chunk); return true; };
  try {
    const slack = createSlackConnector({
      workspaceId: 'T1', channelId: 'C1', senderIds: ['B1'], credentials,
      transport: async request => request.url.includes('history') ? ok({ok: true, messages: [{ts: '1', thread_ts: '1'}]}) : ok({ok: true, messages: [{ts: '1'}, {bot_id: 'B1', text: 'not a delegation message'}, {bot_id: 'B1', text: valid}]}),
    });
    const items = await slack.readSnapshot();
    assert.equal(items.length, 1);
    assert.ok(logged.some(line => line.includes('slack_delegation_parse_skipped')));
    assert.ok(logged.some(line => line.includes('slack_delegation_parse_summary')));
  } finally { process.stderr.write = originalWrite; }
});

test('Slack readSnapshot bounds conversations.history with an oldest watermark', async () => {
  const requests = [];
  const slack = createSlackConnector({
    workspaceId: 'T1', channelId: 'C1', senderIds: ['B1'], credentials,
    now: () => new Date('2026-08-17T00:00:00Z'),
    historyLookbackMs: 3600_000,
    transport: async request => { requests.push(request); return ok({ok: true, messages: []}); },
  });
  await slack.readSnapshot();
  const historyRequest = requests.find(request => request.url.includes('conversations.history'));
  assert.ok(historyRequest);
  const oldest = new URL(historyRequest.url).searchParams.get('oldest');
  assert.equal(oldest, ((new Date('2026-08-17T00:00:00Z').getTime() - 3600_000) / 1000).toFixed(6));
});

test('Slack readSnapshot caps total pagination across history and replies', async () => {
  let historyPages = 0; let repliesPages = 0;
  const slack = createSlackConnector({
    workspaceId: 'T1', channelId: 'C1', senderIds: ['B1'], credentials, maxPagesPerSync: 3,
    transport: async request => {
      if (request.url.includes('conversations.history')) {
        historyPages += 1;
        const cursor = new URL(request.url).searchParams.get('cursor');
        return ok({ok: true, messages: [{ts: `p${historyPages}`, thread_ts: `p${historyPages}`}], response_metadata: {next_cursor: cursor ? '' : 'next'}});
      }
      repliesPages += 1;
      return ok({ok: true, messages: [{ts: 'r1'}, {bot_id: 'B1', text: validDelegationText('needs_jira')}]});
    },
  });
  await slack.readSnapshot();
  assert.equal(historyPages + repliesPages, 3, 'total requests must stop at the configured budget');
});

test('Slack discover() fails a typo\'d channel instead of echoing it back', async () => {
  const slack = createSlackConnector({
    workspaceId: 'T1', channelId: 'C-typo', senderIds: ['B1'], credentials,
    transport: async request => request.url.includes('conversations.info') ? ok({ok: false, error: 'channel_not_found'}) : ok({ok: true}),
  });
  await assert.rejects(slack.discover(), error => error.kind === 'slack_api');
});

test('Slack discover() returns the exact echoed scope for a real channel', async () => {
  const slack = createSlackConnector({
    workspaceId: 'T1', channelId: 'C1', senderIds: ['B1'], credentials,
    transport: async request => {
      if (request.url.includes('conversations.info')) return ok({ok: true, channel: {id: 'C1'}});
      if (request.url.includes('users.info')) return ok({ok: false, error: 'user_not_found'});
      return ok({ok: true});
    },
  });
  assert.deepEqual(await slack.discover(), {workspaceId: 'T1', channelId: 'C1', senderIds: ['B1']});
});

// --- test helpers for the reconciliation retry tests ---

function fakeOperation(overrides = {}) {
  const id = overrides.id ?? 'op-1';
  const payload = {listId: 'tasks', title: 'Persist state', dueAt: null, notes: '', externalId: `reminder-${id}`};
  const base = {
    schemaVersion: 1, id, planRevision: 3, kind: 'reminder_upsert', targetSystem: 'reminders', targetId: 'task-1',
    payload, approval: 'approved', preconditionRevision: null, retryState: 'pending', createdAt: '2026-08-14T09:00:00Z',
  };
  return {...base, ...overrides, idempotencyKey: operationKey(base.planRevision, base.kind, base.targetId, base.payload)};
}

function createFakeRepository() {
  const operations = new Map();
  return {
    save(operation) { operations.set(operation.id, {...operation}); return operations.get(operation.id); },
    get(id) { return operations.get(id) ?? null; },
    execution(id) { const stored = operations.get(id); return {operation: stored, attemptCount: stored.attemptCount ?? 0, result: stored.result ?? null}; },
    beginAttempt(id) { const stored = operations.get(id); stored.attemptCount = (stored.attemptCount ?? 0) + 1; return {attemptCount: stored.attemptCount}; },
    markState(id, state, result) { const stored = operations.get(id); stored.retryState = state; stored.result = result; },
    appendAudit() {},
    reconcileDrift() {},
  };
}
