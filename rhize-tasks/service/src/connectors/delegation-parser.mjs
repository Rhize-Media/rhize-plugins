import {JIRA_KEY, PRIORITIES, UUID_V4, assertHttpsUrl, realDate} from '../domain.mjs';

const MARKER = /^rhize-delegation:v1:([0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})$/;
const FIELD = /^\*(Task|Due|Priority|Jira):\* (.+)$/;

function fail(message) { throw new TypeError(`delegation: ${message}`); }
function plainObject(value) { return value !== null && typeof value === 'object' && !Array.isArray(value) && Object.getPrototypeOf(value) === Object.prototype; }
function exactObject(value, allowed, path) { if (!plainObject(value)) fail(`${path} must be a plain object`); for (const key of Object.keys(value)) if (!allowed.includes(key)) fail(`${path}.${key} is not allowed`); for (const key of allowed) if (!(key in value)) fail(`${path}.${key} is required`); }
function identifier(value, path) { if (typeof value !== 'string' || value.length === 0) fail(`${path} must be a nonempty string`); }

export function parseDelegation(source, allowlist) {
  exactObject(source, ['workspaceId', 'channelId', 'senderId', 'text'], 'source');
  exactObject(allowlist, ['workspaceId', 'channelId', 'senderIds'], 'allowlist');
  identifier(source.workspaceId, 'source.workspaceId'); identifier(source.channelId, 'source.channelId'); identifier(source.senderId, 'source.senderId');
  identifier(allowlist.workspaceId, 'allowlist.workspaceId'); identifier(allowlist.channelId, 'allowlist.channelId');
  if (!Array.isArray(allowlist.senderIds) || allowlist.senderIds.length === 0 || allowlist.senderIds.some(sender => typeof sender !== 'string' || sender.length === 0) || new Set(allowlist.senderIds).size !== allowlist.senderIds.length) fail('allowlist.senderIds must be a unique nonempty string array');
  if (source.workspaceId !== allowlist.workspaceId || source.channelId !== allowlist.channelId || !allowlist.senderIds.includes(source.senderId)) fail('source identity is not allowlisted');
  if (typeof source.text !== 'string' || source.text.length === 0 || source.text.includes('\r')) fail('text must be a nonempty LF-delimited string');

  const lines = source.text.split('\n');
  while (lines.length > 0 && lines.at(-1).trim() === '') lines.pop();
  const markerIndex = lines.length - 1;
  const marker = MARKER.exec(lines[markerIndex] ?? '');
  if (!marker) fail('requires one final lowercase UUIDv4 marker');
  const markers = lines.filter(line => MARKER.test(line));
  if (markers.length !== 1) fail('requires exactly one marker');
  if (lines.length < 5) fail('requires four top fields and a marker');

  const expected = ['Task', 'Due', 'Priority', 'Jira'];
  const fields = {};
  for (let index = 0; index < expected.length; index += 1) {
    const field = FIELD.exec(lines[index]);
    if (!field || field[1] !== expected[index]) fail('requires Task, Due, Priority, and Jira fields in order at the top');
    fields[field[1]] = field[2];
  }
  for (const line of lines.slice(4, markerIndex)) if (FIELD.test(line)) fail('contains extra anchored fields');
  if (fields.Task.trim() !== fields.Task || fields.Task.length === 0) fail('Task must be a nonempty single-line title');
  try { realDate(fields.Due, 'Due'); } catch { fail('Due must be a real ISO date'); }
  if (!PRIORITIES.includes(fields.Priority)) fail('Priority is invalid');

  let jira;
  if (fields.Jira === 'needs_jira') jira = {kind: 'needs_jira', value: null};
  else if (JIRA_KEY.test(fields.Jira)) jira = {kind: 'key', value: fields.Jira};
  else {
    try { assertHttpsUrl(fields.Jira, 'Jira'); } catch { fail('Jira must be needs_jira, an uppercase Jira key, or a safe https URL'); }
    jira = {kind: 'url', value: fields.Jira};
  }
  const delegationId = marker[1];
  if (!UUID_V4.test(delegationId)) fail('marker UUID is invalid');
  return {
    schemaVersion: 1, workspaceId: source.workspaceId, channelId: source.channelId, senderId: source.senderId,
    delegationId, ingestionKey: `${source.workspaceId}:${source.channelId}:${delegationId}`,
    title: fields.Task, dueDate: fields.Due, priority: fields.Priority, jira,
    state: jira.kind === 'needs_jira' ? 'needs_jira' : 'jira_linked', planningLane: 'provisional', approval: 'required', schedulable: false,
  };
}

export {FIELD, MARKER};
