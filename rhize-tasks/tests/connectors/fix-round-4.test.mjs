import assert from 'node:assert/strict';
import test from 'node:test';

import {createGoogleCalendarConnector} from '../../service/src/connectors/google-calendar.mjs';
import {createJiraConnector} from '../../service/src/connectors/jira.mjs';

const credentials = {async get() { return 'secret'; }};
const ok = body => ({status: 200, headers: {}, body});
const notFound = () => ({status: 404, headers: {}, body: {}});
const scoped = updated => ({fields: {project: {key: 'R'}, issuetype: {name: 'Task'}, assignee: null, status: {name: 'Open'}, updated}});
const operation = {kind: 'jira_transition', targetId: 'R-1', idempotencyKey: '4'.repeat(64), payload: {transitionId: '31', comment: null}};

function jira(transport) {
  return createJiraConnector({baseUrl: 'https://jira.example', accountId: 'me', projectKeys: ['R'], issueTypes: ['Task'], credentials, transport});
}

test('Jira transition POST 500 preserves status/retryability and is ambiguous', async () => {
  const connector = jira(async request => {
    if (request.url.includes('/properties/')) return notFound();
    if (request.url.endsWith('/transitions') && request.method === 'GET') return ok({transitions: [{id: '31'}]});
    if (request.url.endsWith('/transitions') && request.method === 'POST') return {status: 500, headers: {}, body: {private: 'redacted'}};
    return ok(scoped('before'));
  });
  await assert.rejects(connector.applyOperation(operation), error => { assert.deepEqual(error, {kind: 'http', retryable: true, ambiguous: true, status: 500}); return true; });
});

test('Jira successful transition followed by revision timeout remains ambiguous', async () => {
  const connector = jira(async request => {
    if (request.url.includes('/properties/')) return notFound();
    if (request.url.endsWith('/transitions') && request.method === 'GET') return ok({transitions: [{id: '31'}]});
    if (request.url.endsWith('/transitions') && request.method === 'POST') return ok({});
    if (request.url.includes('fields=updated')) { const error = new Error('timeout after write'); error.name = 'AbortError'; throw error; }
    return ok(scoped('before'));
  });
  await assert.rejects(connector.applyOperation(operation), error => error.kind === 'timeout' && error.retryable === true && error.ambiguous === true && error.status === null);
});

test('Jira transition returns the post-transition revision', async () => {
  const connector = jira(async request => {
    if (request.url.includes('/properties/')) return notFound();
    if (request.url.endsWith('/transitions') && request.method === 'GET') return ok({transitions: [{id: '31'}]});
    if (request.url.endsWith('/transitions') && request.method === 'POST') return ok({});
    if (request.url.includes('fields=updated')) return ok({fields: {updated: 'after'}});
    return ok(scoped('before'));
  });
  assert.deepEqual(await connector.applyOperation(operation), {externalId: 'R-1', revision: 'after'});
});

test('Jira ambiguous transition reconciles only from the exact marker and then reads the new revision', async () => {
  let marked = false;
  const connector = jira(async request => {
    if (request.url.includes('/properties/')) return marked ? ok({value: {operationKey: operation.idempotencyKey}}) : notFound();
    if (request.url.endsWith('/transitions') && request.method === 'GET') return ok({transitions: [{id: '31'}]});
    if (request.url.endsWith('/transitions') && request.method === 'POST') { marked = true; return {status: 500, headers: {}, body: {}}; }
    if (request.url.includes('fields=updated')) return ok({fields: {updated: 'after-ambiguous'}});
    return ok(scoped('before'));
  });
  assert.deepEqual(await connector.applyOperation(operation), {externalId: 'R-1', revision: 'after-ambiguous'});
});

function calendar(transport) {
  return createGoogleCalendarConnector({readCalendarIds: ['focus'], focusCalendarId: 'focus', credentials, transport, now: () => new Date('2026-08-14T12:00:00Z')});
}

function malformedCalendarTransport() {
  let writes = 0;
  return {
    transport: async request => {
      if (request.url.includes('oauth2')) return ok({access_token: 'access'});
      if (request.method === 'POST' || request.method === 'PUT' || request.method === 'DELETE') writes += 1;
      return ok({items: [{}]});
    },
    writes: () => writes,
  };
}

test('Calendar rejects empty list events in findByExternalId', async () => {
  const fake = malformedCalendarTransport();
  await assert.rejects(calendar(fake.transport).findByExternalId('event-1'), error => error.kind === 'malformed_response' && error.ambiguous === false);
});

test('Calendar rejects empty list events in readSnapshot', async () => {
  const fake = malformedCalendarTransport();
  await assert.rejects(calendar(fake.transport).readSnapshot(), error => error.kind === 'malformed_response' && error.ambiguous === false);
});

test('Calendar rejects empty keyed preflight events before any write', async () => {
  const fake = malformedCalendarTransport();
  const candidate = {kind: 'calendar_upsert', targetId: '', idempotencyKey: '5'.repeat(64), payload: {calendarId: 'focus', title: 'T', description: '', start: '2026-08-14T12:00:00Z', end: '2026-08-14T13:00:00Z'}};
  await assert.rejects(calendar(fake.transport).applyOperation(candidate), error => error.kind === 'malformed_response' && error.ambiguous === false);
  assert.equal(fake.writes(), 0);
});

test('Calendar readSnapshot requires usable start and end values', async () => {
  const connector = calendar(async request => request.url.includes('oauth2') ? ok({access_token: 'access'}) : ok({items: [{id: 'event-1', etag: 'v1', start: {dateTime: '2026-08-14T12:00:00Z'}}]}));
  await assert.rejects(connector.readSnapshot(), error => error.kind === 'malformed_response');
});
