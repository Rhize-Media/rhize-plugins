import assert from 'node:assert/strict';
import test from 'node:test';

import {createGoogleCalendarConnector} from '../../service/src/connectors/google-calendar.mjs';
import {createJiraConnector} from '../../service/src/connectors/jira.mjs';

const credentials = {async get() { return 'secret'; }};
const ok = body => ({status: 200, headers: {}, body});

function jira(transport) {
  return createJiraConnector({baseUrl: 'https://jira.example', accountId: 'me', projectKeys: ['R'], issueTypes: ['Task'], credentials, transport});
}

test('Jira findByExternalId rejects a successful response without a genuine revision', async () => {
  for (const body of [{}, {fields: {updated: null}, version: null, id: null}, {fields: {updated: ' '}, version: '', id: ''}]) {
    await assert.rejects(jira(async () => ok(body)).findByExternalId('R-1'), error => {
      assert.deepEqual(error, {kind: 'malformed_response', retryable: false, ambiguous: false, status: null, body: null, retryAfterMs: null});
      return true;
    });
  }
});

test('Jira transition rejects a malformed fresh revision as ambiguous after dispatch', async () => {
  const connector = jira(async request => {
    if (request.url.includes('/properties/')) return {status: 404, headers: {}, body: {}};
    if (request.url.endsWith('/transitions') && request.method === 'GET') return ok({transitions: [{id: '31'}]});
    if (request.url.endsWith('/transitions') && request.method === 'POST') return ok({});
    if (request.url.includes('fields=updated')) return ok({});
    return ok({fields: {project: {key: 'R'}, issuetype: {name: 'Task'}, assignee: null, status: {name: 'Open'}, updated: 'before'}});
  });
  await assert.rejects(connector.applyOperation({kind: 'jira_transition', targetId: 'R-1', idempotencyKey: '6'.repeat(64), payload: {transitionId: '31', comment: null}}), error => {
    assert.deepEqual(error, {kind: 'malformed_response', retryable: false, ambiguous: true, status: null, body: null, retryAfterMs: null});
    return true;
  });
});

test('Jira findByExternalId accepts explicit nonempty revision sources', async () => {
  for (const [body, revision] of [[{fields: {updated: '2026-08-14T12:00:00.000Z'}}, '2026-08-14T12:00:00.000Z'], [{version: 7}, '7'], [{id: '10001'}, '10001']]) {
    assert.deepEqual(await jira(async () => ok(body)).findByExternalId('R-1'), {revision});
  }
});

function calendar(items) {
  return createGoogleCalendarConnector({
    readCalendarIds: ['focus'],
    focusCalendarId: 'focus',
    credentials,
    transport: async request => request.url.includes('oauth2') ? ok({access_token: 'access'}) : ok({items}),
    now: () => new Date('2026-08-14T12:00:00Z'),
  });
}

test('Calendar rejects a lexically valid but impossible all-day date', async () => {
  const connector = calendar([{id: 'event-1', etag: 'v1', start: {date: '2026-02-30'}, end: {date: '2026-03-01'}}]);
  await assert.rejects(connector.readSnapshot(), error => error.kind === 'malformed_response' && error.ambiguous === false);
});

test('Calendar preserves a valid all-day leap-day event', async () => {
  const connector = calendar([{id: 'event-1', etag: 'v1', start: {date: '2028-02-29'}, end: {date: '2028-03-01'}, summary: 'Leap day'}]);
  const [event] = await connector.readSnapshot();
  assert.equal(event.start, '2028-02-29');
  assert.equal(event.end, '2028-03-01');
});

test('Calendar requires a full ISO datetime and preserves a valid one', async () => {
  const invalid = calendar([{id: 'event-1', etag: 'v1', start: {dateTime: '2026-08-14 12:00:00Z'}, end: {dateTime: '2026-08-14T13:00:00Z'}}]);
  await assert.rejects(invalid.readSnapshot(), error => error.kind === 'malformed_response');

  const valid = calendar([{id: 'event-2', etag: 'v2', start: {dateTime: '2026-08-14T12:00:00Z'}, end: {dateTime: '2026-08-14T13:00:00-04:00'}}]);
  const [event] = await valid.readSnapshot();
  assert.equal(event.start, '2026-08-14T12:00:00Z');
  assert.equal(event.end, '2026-08-14T13:00:00-04:00');
});
