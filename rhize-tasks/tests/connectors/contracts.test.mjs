import assert from 'node:assert/strict';
import test from 'node:test';
import {createKeychain} from '../../service/src/connectors/keychain.mjs';
import {createJiraConnector} from '../../service/src/connectors/jira.mjs';
import {createGoogleCalendarConnector} from '../../service/src/connectors/google-calendar.mjs';
import {createSlackConnector} from '../../service/src/connectors/slack.mjs';
import {createRemindersConnector} from '../../service/src/connectors/reminders.mjs';

const credentials = {async get() { return 'secret'; }};
const interfaceNames = ['health', 'discover', 'readSnapshot', 'applyOperation', 'findByExternalId'];
const response = body => ({status: 200, headers: {}, body});

test('keychain uses fixed security arguments, stdin values, and supports revocation', async () => {
  const calls = []; const keychain = createKeychain({async spawnFile(file, args, options) { calls.push({file, args, options}); return {code: 0, stdout: 'value\n'}; }});
  await keychain.set('media.rhize.tasks.api', 'bearer', 'do-not-leak'); await keychain.get('media.rhize.tasks.api', 'bearer'); await keychain.delete('media.rhize.tasks.api', 'bearer');
  assert.equal(calls[0].file, '/usr/bin/security'); assert.ok(!calls[0].args.join(' ').includes('do-not-leak')); assert.equal(calls[0].options.input, 'do-not-leak'); assert.deepEqual(calls[2].args.slice(0, 1), ['delete-generic-password']);
});

test('connectors expose the complete common interface and block unsupported writes', async () => {
  const transport = async request => request.url.includes('auth.test') ? response({team_id: 'T1'}) : response({messages: []});
  const connectors = [createJiraConnector({baseUrl: 'https://jira.example', accountId: 'a', projectKeys: ['RHIZE'], issueTypes: ['Task'], credentials, transport: async () => response({})}), createGoogleCalendarConnector({readCalendarIds: ['read'], focusCalendarId: 'focus', credentials, transport: async () => response({items: []})}), createSlackConnector({workspaceId: 'T1', channelId: 'C1', senderIds: ['B1'], credentials, transport}), createRemindersConnector({helperPath: '/helper', tasksListId: 'tasks', runner: async () => ({code: 0, stdout: '{"items":[]}'}),})];
  for (const connector of connectors) assert.deepEqual(Object.keys(connector).sort(), [...interfaceNames].sort());
  assert.throws(() => connectors[2].applyOperation({}), error => error.kind === 'unsupported');
});

test('Jira snapshot keeps JQL within allowlisted projects/types and discovers transitions before writing', async () => {
  const calls = []; const jira = createJiraConnector({baseUrl: 'https://jira.example', accountId: 'a', projectKeys: ['RHIZE'], issueTypes: ['Task'], credentials, transport: async request => { calls.push(request); if (request.url.includes('/transitions') && request.method === 'GET') return response({transitions: [{id: '7'}]}); if (request.url.includes('/search/jql')) return response({issues: [], total: 0}); return response({}); }});
  await jira.readSnapshot(); assert.match(decodeURIComponent(calls[0].url), /project in \("RHIZE"\) AND issuetype in \("Task"\)/);
  await jira.applyOperation({kind: 'jira_transition', targetId: 'RHIZE-1', payload: {transitionId: '7', comment: null}, idempotencyKey: 'x'}); assert.equal(calls.filter(call => call.method === 'POST').length, 1);
});

test('Google refreshes only in memory and rejects writes outside the focus calendar', async () => {
  const calls = []; const google = createGoogleCalendarConnector({readCalendarIds: ['read'], focusCalendarId: 'focus', credentials, transport: async request => { calls.push(request); return request.url.includes('/token') ? response({access_token: 'access-token'}) : response({}); }});
  await assert.rejects(google.applyOperation({kind: 'calendar_upsert', targetId: '', payload: {calendarId: 'other'}}), error => error.kind === 'out_of_scope');
  await google.health(); assert.ok(calls.some(call => call.url === 'https://oauth2.googleapis.com/token')); assert.ok(!calls.some(call => String(call.body).includes('access-token')));
});

test('Slack reads only configured channel replies from exact senders and ignores invalid text', async () => {
  const requests = []; const valid = '*Task:* Audit\n*Due:* 2026-08-17\n*Priority:* high\n*Jira:* needs_jira\nrhize-delegation:v1:550e8400-e29b-41d4-a716-446655440000';
  const slack = createSlackConnector({workspaceId: 'T1', channelId: 'C1', senderIds: ['B1'], credentials, transport: async request => { requests.push(request); if (request.url.includes('history')) return response({messages: [{ts: '1', thread_ts: '1'}]}); return response({messages: [{ts: '1'}, {bot_id: 'B1', text: valid}, {bot_id: 'B2', text: valid}]}); }});
  assert.equal((await slack.readSnapshot()).length, 1); assert.ok(requests.every(request => request.method === 'GET' && request.url.includes('channel=C1')));
});

test('Reminders bounds process output and classifies write timeout as ambiguous', async () => {
  const reminders = createRemindersConnector({helperPath: '/helper', tasksListId: 'tasks', runner: async () => ({code: 0, timedOut: true, stdout: ''})});
  await assert.rejects(reminders.applyOperation({kind: 'reminder_delete', targetId: 'r', payload: {}, idempotencyKey: 'x'}), error => error.kind === 'timeout' && error.ambiguous === true);
});
