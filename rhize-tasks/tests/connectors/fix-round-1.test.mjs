import assert from 'node:assert/strict';
import test from 'node:test';
import {createRemindersConnector} from '../../service/src/connectors/reminders.mjs';
import {createJiraConnector, textToAdf, adfToText} from '../../service/src/connectors/jira.mjs';
import {createSlackConnector} from '../../service/src/connectors/slack.mjs';
import {createKeychain} from '../../service/src/connectors/keychain.mjs';

const credentials = {async get() { return 'secret'; }};
const ok = body => ({status: 200, body, headers: {}});

test('Reminders rejects unknown kinds and cannot override helper command/list', async () => {
  let called = false; const connector = createRemindersConnector({helperPath: '/helper', tasksListId: 'tasks', runner: async (_p, _a, options) => { called = JSON.parse(options.input); return {code: 0, stdout: '{"id":"x","revision":"1"}'}; }});
  await assert.rejects(connector.applyOperation({kind: 'reminder_surprise', payload: {}, targetId: 'x'}), error => error.kind === 'unsupported');
  await assert.rejects(connector.applyOperation({kind: 'reminder_upsert', targetId: 'x', idempotencyKey: 'k', payload: {listId: 'tasks', title: 't', dueAt: null, notes: '', externalId: 'x', command: 'delete'}}), error => error.kind === 'out_of_scope');
  assert.equal(called, false);
});

test('Jira blocks an out-of-scope existing issue before any mutation and paginates tokens safely', async () => {
  const calls = []; const jira = createJiraConnector({baseUrl: 'https://jira.example', accountId: 'a', projectKeys: ['R\\"X'], issueTypes: ['Task'], credentials, transport: async request => { calls.push(request); if (request.url.includes('/search/jql')) return ok({issues: [], nextPageToken: calls.filter(c => c.url.includes('/search/jql')).length === 1 ? 'p2' : null}); return ok({fields: {project: {key: 'NO'}, issuetype: {name: 'Task'}}}); }});
  await jira.readSnapshot(); assert.match(decodeURIComponent(calls[0].url), /R\\\\\\"X/);
  await assert.rejects(jira.applyOperation({kind: 'jira_assign', targetId: 'NO-1', payload: {accountId: 'a'}, idempotencyKey: 'k'}), error => error.kind === 'out_of_scope');
  assert.equal(calls.some(call => call.method === 'PUT'), false); assert.equal(adfToText(textToAdf('hello')), 'hello');
});

test('Slack application errors are never treated as empty successful snapshots', async () => {
  const slack = createSlackConnector({workspaceId: 'T', channelId: 'C', senderIds: ['B'], credentials, transport: async () => ok({ok: false, error: 'invalid_auth'})});
  await assert.rejects(slack.readSnapshot(), error => error.kind === 'authorization');
});

test('Keychain rejects unapproved service/account pairs without invoking security', async () => {
  let calls = 0; const keychain = createKeychain({async spawnFile() { calls += 1; return {code: 0, stdout: ''}; }});
  await assert.rejects(keychain.get('media.rhize.tasks.jira', 'bearer'), error => error.kind === 'invalid_credential'); assert.equal(calls, 0);
});
