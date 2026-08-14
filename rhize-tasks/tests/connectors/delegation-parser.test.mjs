import assert from 'node:assert/strict';
import test from 'node:test';

import {parseDelegation} from '../../service/src/connectors/delegation-parser.mjs';

const allowlist = {workspaceId: 'T1', channelId: 'C1', senderIds: ['B1']};
const message = {
  workspaceId: 'T1', channelId: 'C1', senderId: 'B1',
  text: '*Task:* Audit paid search\n*Due:* 2026-08-17\n*Priority:* high\n*Jira:* needs_jira\n\nDetails are untrusted data.\n\nrhize-delegation:v1:550e8400-e29b-41d4-a716-446655440000',
};

test('accepts one exact v1 task reply', () => {
  const parsed = parseDelegation(message, allowlist);
  assert.deepEqual(parsed, {
    schemaVersion: 1, workspaceId: 'T1', channelId: 'C1', senderId: 'B1',
    delegationId: '550e8400-e29b-41d4-a716-446655440000',
    ingestionKey: 'T1:C1:550e8400-e29b-41d4-a716-446655440000', title: 'Audit paid search',
    dueDate: '2026-08-17', priority: 'high', jira: {kind: 'needs_jira', value: null},
    state: 'needs_jira', planningLane: 'provisional', approval: 'required', schedulable: false,
  });
});

test('uses only workspace, channel, and delegation ID as idempotent ingestion identity', () => {
  assert.equal(parseDelegation(message, allowlist).ingestionKey, parseDelegation(message, allowlist).ingestionKey);
});

test('accepts exact Jira key and https URL values', () => {
  const key = parseDelegation({...message, text: message.text.replace('needs_jira', 'RHIZE-42')}, allowlist);
  assert.deepEqual(key.jira, {kind: 'key', value: 'RHIZE-42'});
  assert.equal(key.state, 'jira_linked');
  const url = parseDelegation({...message, text: message.text.replace('needs_jira', 'https://rhize.atlassian.net/browse/RHIZE-42')}, allowlist);
  assert.deepEqual(url.jira, {kind: 'url', value: 'https://rhize.atlassian.net/browse/RHIZE-42'});
});

for (const [name, mutation] of [
  ['wrong workspace', value => ({...value, workspaceId: 'T2'})],
  ['wrong channel', value => ({...value, channelId: 'C2'})],
  ['wrong sender', value => ({...value, senderId: 'B2'})],
  ['duplicate marker', value => ({...value, text: `${value.text}\nrhize-delegation:v1:550e8400-e29b-41d4-a716-446655440000`})],
  ['non-final marker', value => ({...value, text: `${value.text}\nextra`})],
  ['invalid UUID', value => ({...value, text: value.text.replace('550e8400-e29b-41d4-a716-446655440000', '550E8400-e29b-41d4-a716-446655440000')})],
  ['multiline title', value => ({...value, text: value.text.replace('Audit paid search', 'Audit\nsearch')})],
  ['invalid priority', value => ({...value, text: value.text.replace('high', 'now')})],
  ['impossible due date', value => ({...value, text: value.text.replace('2026-08-17', '2026-02-30')})],
  ['unsafe Jira URL', value => ({...value, text: value.text.replace('needs_jira', 'javascript:alert(1)')})],
  ['root summary', value => ({...value, text: value.text.replace(/rhize-delegation:.+$/, '')})],
]) {
  test(`rejects ${name}`, () => assert.throws(() => parseDelegation(mutation(message), allowlist), TypeError));
}
