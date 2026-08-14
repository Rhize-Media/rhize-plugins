import assert from 'node:assert/strict';
import test from 'node:test';

import {createGoogleCalendarConnector} from '../../service/src/connectors/google-calendar.mjs';
import {createHttpTransport} from '../../service/src/connectors/http.mjs';
import {adfToText, createJiraConnector} from '../../service/src/connectors/jira.mjs';
import {createRemindersConnector} from '../../service/src/connectors/reminders.mjs';

const credentials = {async get() { return 'secret'; }};
const ok = body => ({status: 200, headers: {}, body});
const jiraConfig = transport => ({baseUrl: 'https://jira.example', accountId: 'me', projectKeys: ['R'], issueTypes: ['Task'], credentials, transport});
const scoped = {fields: {project: {key: 'R'}, issuetype: {name: 'Task'}, assignee: null, status: {name: 'Open'}, updated: 'u1'}};

test('Jira recursively extracts nested ADF including lists and hard breaks', () => {
  const adf = {type: 'doc', version: 1, content: [{type: 'heading', content: [{type: 'text', text: 'Title'}]}, {type: 'bulletList', content: [{type: 'listItem', content: [{type: 'paragraph', content: [{type: 'text', text: 'one'}, {type: 'hardBreak'}, {type: 'text', text: 'two'}]}]}]}]};
  assert.equal(adfToText(adf), 'Titleone\ntwo');
});

test('Jira create maps normal to Medium and honors a configured priority name', async () => {
  for (const [priorityNames, expected] of [[undefined, 'Medium'], [{urgent: 'P0', high: 'P1', normal: 'Routine', low: 'P3'}, 'Routine']]) {
    let created;
    const jira = createJiraConnector({...jiraConfig(async request => { if (request.url.includes('/search/jql')) return ok({issues: []}); if (request.method === 'POST') { created = JSON.parse(request.body); return ok({key: 'R-1', id: '1'}); } return ok({}); }), ...(priorityNames ? {priorityNames} : {})});
    await jira.applyOperation({kind: 'jira_create', targetId: 'new', idempotencyKey: 'a'.repeat(64), payload: {projectKey: 'R', issueType: 'Task', title: 'T', description: '', dueDate: null, priority: 'normal'}});
    assert.equal(created.fields.priority.name, expected);
  }
});

test('Jira comment marker on page two prevents a duplicate comment', async () => {
  let posts = 0;
  const marker = `rhize-operation:${'b'.repeat(64)}`;
  const jira = createJiraConnector(jiraConfig(async request => {
    if (request.url.includes('/properties/')) return {status: 404, headers: {}, body: {}};
    if (request.url.includes('/comment?startAt=0')) return ok({comments: Array.from({length: 100}, (_, id) => ({id, body: {type: 'doc', content: []}})), total: 101});
    if (request.url.includes('/comment?startAt=100')) return ok({comments: [{id: 101, body: {type: 'doc', content: [{type: 'paragraph', content: [{type: 'text', text: marker}]}]}}], total: 101});
    if (request.method === 'POST') { posts += 1; return ok({}); }
    return ok(scoped);
  }));
  await jira.applyOperation({kind: 'jira_comment', targetId: 'R-1', idempotencyKey: 'b'.repeat(64), payload: {body: 'hello'}});
  assert.equal(posts, 0);
});

test('Jira transition with null comment carries a durable property marker', async () => {
  let transitionBody;
  const jira = createJiraConnector(jiraConfig(async request => {
    if (request.url.includes('/properties/')) return {status: 404, headers: {}, body: {}};
    if (request.url.endsWith('/transitions') && request.method === 'GET') return ok({transitions: [{id: '31'}]});
    if (request.url.endsWith('/transitions') && request.method === 'POST') { transitionBody = JSON.parse(request.body); return ok({}); }
    return ok(scoped);
  }));
  await jira.applyOperation({kind: 'jira_transition', targetId: 'R-1', idempotencyKey: 'c'.repeat(64), payload: {transitionId: '31', comment: null}});
  assert.deepEqual(transitionBody.properties[0].value, {operationKey: 'c'.repeat(64), transitionId: '31'});
  assert.equal('update' in transitionBody, false);
});

test('Jira ambiguous transition reconciles by durable marker and replay does not duplicate', async () => {
  let marked = false; let posts = 0;
  const jira = createJiraConnector(jiraConfig(async request => {
    if (request.url.includes('/properties/')) return marked ? ok({value: {operationKey: 'd'.repeat(64)}}) : {status: 404, headers: {}, body: {}};
    if (request.url.endsWith('/transitions') && request.method === 'GET') return ok({transitions: [{id: '31'}]});
    if (request.url.endsWith('/transitions') && request.method === 'POST') { posts += 1; marked = true; const error = new Error('timeout'); error.name = 'AbortError'; throw error; }
    return ok(scoped);
  }));
  const operation = {kind: 'jira_transition', targetId: 'R-1', idempotencyKey: 'd'.repeat(64), payload: {transitionId: '31', comment: null}};
  assert.equal((await jira.applyOperation(operation)).externalId, 'R-1');
  assert.equal((await jira.applyOperation(operation)).externalId, 'R-1');
  assert.equal(posts, 1);
});

test('Jira ambiguous transition without marker remains ambiguous', async () => {
  const jira = createJiraConnector(jiraConfig(async request => {
    if (request.url.includes('/properties/')) return {status: 404, headers: {}, body: {}};
    if (request.url.endsWith('/transitions') && request.method === 'GET') return ok({transitions: [{id: '31'}]});
    if (request.method === 'POST') { const error = new Error('timeout'); error.name = 'AbortError'; throw error; }
    return ok(scoped);
  }));
  await assert.rejects(jira.applyOperation({kind: 'jira_transition', targetId: 'R-1', idempotencyKey: 'e'.repeat(64), payload: {transitionId: '31', comment: null}}), error => error.kind === 'timeout' && error.ambiguous === true);
});

function calendar(transport) { return createGoogleCalendarConnector({readCalendarIds: ['focus'], focusCalendarId: 'focus', credentials, transport, now: () => new Date('2026-08-14T12:00:00Z')}); }

test('Calendar operation-key reconciliation includes past events and prevents duplicate POSTs', async () => {
  let posts = 0; const urls = [];
  const connector = calendar(async request => { urls.push(request.url); if (request.url.includes('oauth2')) return ok({access_token: 'a'}); if (request.method === 'POST') { posts += 1; return ok({id: 'event-1', etag: 'v1'}); } return ok({items: [{id: 'past-event', etag: 'v0', start: {dateTime: '2026-01-01T10:00:00Z'}}]}); });
  const operation = {kind: 'calendar_upsert', targetId: '', idempotencyKey: 'f'.repeat(64), payload: {calendarId: 'focus', title: 'T', description: '', start: '2026-01-01T10:00:00Z', end: '2026-01-01T11:00:00Z'}};
  await connector.applyOperation(operation); await connector.applyOperation(operation);
  const keyUrls = urls.filter(url => url.includes('privateExtendedProperty'));
  assert.ok(keyUrls.length >= 2); assert.ok(keyUrls.every(url => !url.includes('timeMin='))); assert.equal(posts, 0);
});

test('Calendar malformed discover body is normalized and supported findByExternalId returns revisions', async () => {
  const malformed = calendar(async request => request.url.includes('oauth2') ? ok({access_token: 'a'}) : ok(null));
  await assert.rejects(malformed.discover(), error => error.kind === 'malformed_response' && error.status === null);
  const found = calendar(async request => { if (request.url.includes('oauth2')) return ok({access_token: 'a'}); if (request.url.includes('privateExtendedProperty')) return ok({items: []}); return ok({id: 'event-1', etag: 'v2'}); });
  assert.deepEqual(await found.findByExternalId('event-1'), {revision: 'v2'});
});

test('HTTP status classification precedes non-JSON content validation', async () => {
  for (const [status, kind, retryable] of [[401, 'authorization', false], [500, 'http', true]]) {
    const request = createHttpTransport({fetch: async () => new Response('<html>secret</html>', {status, headers: {'content-type': 'text/html'}})});
    await assert.rejects(request({url: 'https://example.test'}), error => error.kind === kind && error.retryable === retryable && error.status === status && !JSON.stringify(error).includes('secret'));
  }
});

test('supported Jira and Reminders findByExternalId return normalized revisions', async () => {
  const jira = createJiraConnector(jiraConfig(async () => ok({id: '1', fields: {updated: 'u2'}})));
  assert.deepEqual(await jira.findByExternalId('R-1'), {revision: 'u2'});
  const reminders = createRemindersConnector({helperPath: '/helper', tasksListId: 'tasks', runner: async () => ({code: 0, stdout: JSON.stringify({ok: true, items: [{id: 'r1', revision: 'r2'}]})})});
  assert.deepEqual(await reminders.findByExternalId('r1'), {revision: 'r2'});
});
