import {createHash} from 'node:crypto';

export const LANES = Object.freeze(['owned', 'opportunity', 'provisional']);
export const APPROVAL = Object.freeze(['required', 'approved', 'applied', 'rejected']);
export const CONFIDENCE = Object.freeze(['high', 'medium', 'low']);
export const PRIORITIES = Object.freeze(['urgent', 'high', 'normal', 'low']);

const ESTIMATE_SOURCES = new Set(['jira_remaining', 'explicit', 'history', 'inferred', 'agent_assisted']);
const REPLANNING = new Set(['bounded', 'stable', 'continuous']);
const RECONCILIATION = new Set(['prompted', 'automatic', 'local_only']);
const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const JIRA_KEY = /^[A-Z][A-Z0-9_]*-[1-9][0-9]*$/;
const TIME = /^([01][0-9]|2[0-3]):[0-5][0-9]$/;
const DATE = /^(\d{4})-(\d{2})-(\d{2})$/;
const DATE_TIME = /^(\d{4})-(\d{2})-(\d{2})T([01][0-9]|2[0-3]):[0-5][0-9](?::[0-5][0-9](?:\.\d{1,9})?)?(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])$/;

function fail(path, message) {
  throw new TypeError(`${path}: ${message}`);
}

function isObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value) && Object.getPrototypeOf(value) === Object.prototype;
}

function object(value, path, allowed, required = allowed) {
  if (!isObject(value)) fail(path, 'must be a plain object');
  for (const key of Object.keys(value)) if (!allowed.includes(key)) fail(`${path}.${key}`, 'is not allowed');
  for (const key of required) if (!(key in value)) fail(`${path}.${key}`, 'is required');
  return value;
}

function string(value, path, {min = 1, pattern} = {}) {
  if (typeof value !== 'string' || value.length < min) fail(path, `must be a string with at least ${min} character${min === 1 ? '' : 's'}`);
  if (pattern && !pattern.test(value)) fail(path, 'has an invalid format');
  return value;
}

function boolean(value, path) {
  if (typeof value !== 'boolean') fail(path, 'must be a boolean');
  return value;
}

function integer(value, path, min, max = Infinity) {
  if (!Number.isInteger(value) || value < min || value > max) fail(path, `must be an integer from ${min} to ${max === Infinity ? 'infinity' : max}`);
  return value;
}

function number(value, path, min, max) {
  if (!Number.isFinite(value) || value < min || value > max) fail(path, `must be a number from ${min} to ${max}`);
  return value;
}

function enumeration(value, path, values) {
  if (!values.includes(value)) fail(path, `must be one of ${values.join(', ')}`);
  return value;
}

function realDate(value, path) {
  string(value, path, {pattern: DATE});
  const [, year, month, day] = DATE.exec(value);
  const date = new Date(Date.UTC(Number(year), Number(month) - 1, Number(day)));
  if (date.getUTCFullYear() !== Number(year) || date.getUTCMonth() !== Number(month) - 1 || date.getUTCDate() !== Number(day)) fail(path, 'must be a real ISO date');
  return value;
}

function isoDateTime(value, path) {
  string(value, path, {pattern: DATE_TIME});
  realDate(value.slice(0, 10), path);
  if (Number.isNaN(Date.parse(value))) fail(path, 'must be a real ISO date-time');
  return value;
}

export function assertHttpsUrl(value, path = 'url') {
  string(value, path);
  if (/\s/.test(value)) fail(path, 'must not contain whitespace');
  let url;
  try { url = new URL(value); } catch { fail(path, 'must be a URL'); }
  if (url.protocol !== 'https:' || !url.hostname || url.username || url.password) fail(path, 'must be a safe https URL');
  return value;
}

function nullable(value, path, validator) {
  return value === null ? value : validator(value, path);
}

function strings(value, path, {min = 0, unique = false} = {}) {
  if (!Array.isArray(value) || value.length < min) fail(path, `must be an array with at least ${min} item${min === 1 ? '' : 's'}`);
  value.forEach((item, index) => string(item, `${path}[${index}]`));
  if (unique && new Set(value).size !== value.length) fail(path, 'must contain unique values');
  return value;
}

function interval(value, path) {
  object(value, path, ['dayOfWeek', 'start', 'end']);
  integer(value.dayOfWeek, `${path}.dayOfWeek`, 1, 7);
  string(value.start, `${path}.start`, {pattern: TIME});
  string(value.end, `${path}.end`, {pattern: TIME});
  if (value.start >= value.end) fail(path, 'start must precede end');
  return value;
}

function validateEstimate(value, path) {
  object(value, path, ['minutes', 'source', 'confidence', 'rationale', 'confirmedAt', 'requiresApproval']);
  integer(value.minutes, `${path}.minutes`, 1, 10080);
  enumeration(value.source, `${path}.source`, [...ESTIMATE_SOURCES]);
  enumeration(value.confidence, `${path}.confidence`, CONFIDENCE);
  string(value.rationale, `${path}.rationale`);
  nullable(value.confirmedAt, `${path}.confirmedAt`, isoDateTime);
  boolean(value.requiresApproval, `${path}.requiresApproval`);
}

export function validateProfile(value) {
  object(value, 'profile', ['schemaVersion', 'identity', 'jira', 'calendar', 'reminders', 'workingIntervals', 'breaks', 'capacity', 'planning', 'routines', 'approval', 'privacy']);
  integer(value.schemaVersion, 'profile.schemaVersion', 1, 1);

  object(value.identity, 'profile.identity', ['name', 'timezone', 'locale']);
  string(value.identity.name, 'profile.identity.name'); string(value.identity.timezone, 'profile.identity.timezone'); string(value.identity.locale, 'profile.identity.locale');

  object(value.jira, 'profile.jira', ['accountId', 'baseUrl', 'projects', 'issueTypes', 'excludedIssueTypes', 'projectImportance', 'opportunityUrgencyThreshold', 'maxDailySuggestions', 'competencies']);
  string(value.jira.accountId, 'profile.jira.accountId'); assertHttpsUrl(value.jira.baseUrl, 'profile.jira.baseUrl');
  strings(value.jira.projects, 'profile.jira.projects', {min: 1, unique: true}); strings(value.jira.issueTypes, 'profile.jira.issueTypes', {min: 1, unique: true}); strings(value.jira.excludedIssueTypes, 'profile.jira.excludedIssueTypes', {unique: true});
  if (!isObject(value.jira.projectImportance)) fail('profile.jira.projectImportance', 'must be a plain object map');
  for (const [key, importance] of Object.entries(value.jira.projectImportance)) { string(key, `profile.jira.projectImportance key`); integer(importance, `profile.jira.projectImportance.${key}`, 1, 5); }
  enumeration(value.jira.opportunityUrgencyThreshold, 'profile.jira.opportunityUrgencyThreshold', PRIORITIES); integer(value.jira.maxDailySuggestions, 'profile.jira.maxDailySuggestions', 0, 20);
  if (!Array.isArray(value.jira.competencies)) fail('profile.jira.competencies', 'must be an array');
  value.jira.competencies.forEach((competency, index) => { const path = `profile.jira.competencies[${index}]`; object(competency, path, ['name', 'confidence', 'excluded']); string(competency.name, `${path}.name`); number(competency.confidence, `${path}.confidence`, 0, 1); boolean(competency.excluded, `${path}.excluded`); });

  object(value.calendar, 'profile.calendar', ['readCalendarIds', 'focusCalendarId', 'focusCalendarName', 'redactOutsideTitles']);
  strings(value.calendar.readCalendarIds, 'profile.calendar.readCalendarIds', {min: 1, unique: true}); string(value.calendar.focusCalendarId, 'profile.calendar.focusCalendarId');
  if (value.calendar.focusCalendarName !== 'Rhize Focus') fail('profile.calendar.focusCalendarName', 'must equal Rhize Focus'); boolean(value.calendar.redactOutsideTitles, 'profile.calendar.redactOutsideTitles');

  object(value.reminders, 'profile.reminders', ['awarenessLists', 'tasksListId', 'tasksListName']);
  if (!Array.isArray(value.reminders.awarenessLists)) fail('profile.reminders.awarenessLists', 'must be an array');
  value.reminders.awarenessLists.forEach((list, index) => { const path = `profile.reminders.awarenessLists[${index}]`; object(list, path, ['id', 'protectedDurationMinutes', 'showTitles']); string(list.id, `${path}.id`); integer(list.protectedDurationMinutes, `${path}.protectedDurationMinutes`, 0, 480); boolean(list.showTitles, `${path}.showTitles`); });
  string(value.reminders.tasksListId, 'profile.reminders.tasksListId'); if (value.reminders.tasksListName !== 'Rhize Tasks') fail('profile.reminders.tasksListName', 'must equal Rhize Tasks');

  if (!Array.isArray(value.workingIntervals) || value.workingIntervals.length === 0) fail('profile.workingIntervals', 'must be a nonempty array'); value.workingIntervals.forEach((item, index) => interval(item, `profile.workingIntervals[${index}]`));
  if (!Array.isArray(value.breaks)) fail('profile.breaks', 'must be an array'); value.breaks.forEach((item, index) => interval(item, `profile.breaks[${index}]`));
  object(value.capacity, 'profile.capacity', ['bufferPercent', 'maxDailyMinutes']); number(value.capacity.bufferPercent, 'profile.capacity.bufferPercent', 0, 80); integer(value.capacity.maxDailyMinutes, 'profile.capacity.maxDailyMinutes', 1, 1440);
  object(value.planning, 'profile.planning', ['focusBlockMinutes', 'minimumBlockMinutes', 'allowSplitting', 'meetingBufferMinutes', 'freezeWindowMinutes']); integer(value.planning.focusBlockMinutes, 'profile.planning.focusBlockMinutes', 15, 240); integer(value.planning.minimumBlockMinutes, 'profile.planning.minimumBlockMinutes', 15, 120); boolean(value.planning.allowSplitting, 'profile.planning.allowSplitting'); integer(value.planning.meetingBufferMinutes, 'profile.planning.meetingBufferMinutes', 0, 120); integer(value.planning.freezeWindowMinutes, 'profile.planning.freezeWindowMinutes', 0, 240);
  object(value.routines, 'profile.routines', ['replanningMode', 'reconciliationMode', 'morningTime', 'middayTime', 'eveningTime']); enumeration(value.routines.replanningMode, 'profile.routines.replanningMode', [...REPLANNING]); enumeration(value.routines.reconciliationMode, 'profile.routines.reconciliationMode', [...RECONCILIATION]); ['morningTime', 'middayTime', 'eveningTime'].forEach(key => string(value.routines[key], `profile.routines.${key}`, {pattern: TIME}));
  object(value.approval, 'profile.approval', ['setupComplete', 'firstPlanApproved', 'automationPaused']); boolean(value.approval.setupComplete, 'profile.approval.setupComplete'); boolean(value.approval.firstPlanApproved, 'profile.approval.firstPlanApproved'); boolean(value.approval.automationPaused, 'profile.approval.automationPaused');
  object(value.privacy, 'profile.privacy', ['showOutsideTitles']); boolean(value.privacy.showOutsideTitles, 'profile.privacy.showOutsideTitles');
  return value;
}

export function isAutomationActive(profile) {
  validateProfile(profile);
  return profile.approval.setupComplete && profile.approval.firstPlanApproved && !profile.approval.automationPaused;
}

export function assertTask(value) {
  const required = ['schemaVersion', 'id', 'sourceType', 'lane', 'title', 'projectKey', 'issueType', 'assigneeAccountId', 'priority', 'dueDate', 'status', 'terminal', 'blocked', 'dependencyRisk', 'remainingMinutes', 'explicitEstimateMinutes', 'competencies', 'manualLock', 'carryoverCount', 'createdAt', 'reserved', 'sourceRevision'];
  object(value, 'task', [...required, 'jiraKey', 'jiraUrl', 'delegationId', 'description', 'estimate'], required);
  integer(value.schemaVersion, 'task.schemaVersion', 1, 1); string(value.id, 'task.id'); enumeration(value.sourceType, 'task.sourceType', ['jira', 'delegation']); enumeration(value.lane, 'task.lane', LANES); string(value.title, 'task.title'); string(value.projectKey, 'task.projectKey'); string(value.issueType, 'task.issueType'); nullable(value.assigneeAccountId, 'task.assigneeAccountId', string); enumeration(value.priority, 'task.priority', PRIORITIES); nullable(value.dueDate, 'task.dueDate', realDate); string(value.status, 'task.status'); boolean(value.terminal, 'task.terminal'); boolean(value.blocked, 'task.blocked'); integer(value.dependencyRisk, 'task.dependencyRisk', 0, 5); nullable(value.remainingMinutes, 'task.remainingMinutes', (item, path) => integer(item, path, 1, 10080)); nullable(value.explicitEstimateMinutes, 'task.explicitEstimateMinutes', (item, path) => integer(item, path, 1, 10080)); strings(value.competencies, 'task.competencies', {unique: true}); boolean(value.manualLock, 'task.manualLock'); integer(value.carryoverCount, 'task.carryoverCount', 0); isoDateTime(value.createdAt, 'task.createdAt'); boolean(value.reserved, 'task.reserved'); string(value.sourceRevision, 'task.sourceRevision');
  if ('jiraKey' in value) string(value.jiraKey, 'task.jiraKey', {pattern: JIRA_KEY}); if ('jiraUrl' in value) assertHttpsUrl(value.jiraUrl, 'task.jiraUrl'); if ('delegationId' in value) string(value.delegationId, 'task.delegationId', {pattern: UUID_V4}); if ('description' in value) string(value.description, 'task.description', {min: 0}); if ('estimate' in value) validateEstimate(value.estimate, 'task.estimate');
  if (value.sourceType === 'jira' && !('jiraKey' in value) && !('jiraUrl' in value)) fail('task', 'Jira tasks require jiraKey or jiraUrl');
  if (value.sourceType === 'delegation' && !('delegationId' in value)) fail('task', 'delegation tasks require delegationId');
  return value;
}

const OPERATION_KINDS = Object.freeze(['reminder_upsert', 'reminder_complete', 'reminder_delete', 'calendar_upsert', 'calendar_delete', 'jira_assign', 'jira_transition', 'jira_comment', 'jira_create', 'provisional_link', 'urgent_displacement', 'scope_expand']);
const OPERATION_SYSTEMS = Object.freeze({
  reminder_upsert: 'reminders', reminder_complete: 'reminders', reminder_delete: 'reminders',
  calendar_upsert: 'calendar', calendar_delete: 'calendar',
  jira_assign: 'jira', jira_transition: 'jira', jira_comment: 'jira', jira_create: 'jira',
  provisional_link: 'local', urgent_displacement: 'local', scope_expand: 'local',
});
const RETRY_STATES = Object.freeze(['pending', 'safe_retry', 'reconciliation_required', 'applied', 'failed']);

function operationPayload(kind, value) {
  const path = 'operation.payload';
  switch (kind) {
    case 'reminder_upsert':
      object(value, path, ['listId', 'title', 'dueAt', 'notes', 'externalId']);
      string(value.listId, `${path}.listId`); string(value.title, `${path}.title`); nullable(value.dueAt, `${path}.dueAt`, isoDateTime); string(value.notes, `${path}.notes`, {min: 0}); string(value.externalId, `${path}.externalId`);
      break;
    case 'reminder_complete':
      object(value, path, ['completedAt']); isoDateTime(value.completedAt, `${path}.completedAt`);
      break;
    case 'reminder_delete': object(value, path, []); break;
    case 'calendar_upsert':
      object(value, path, ['calendarId', 'title', 'start', 'end', 'description', 'externalId']);
      string(value.calendarId, `${path}.calendarId`); string(value.title, `${path}.title`); isoDateTime(value.start, `${path}.start`); isoDateTime(value.end, `${path}.end`); if (Date.parse(value.start) >= Date.parse(value.end)) fail(path, 'start must precede end'); string(value.description, `${path}.description`, {min: 0}); string(value.externalId, `${path}.externalId`);
      break;
    case 'calendar_delete': object(value, path, []); break;
    case 'jira_assign': object(value, path, ['accountId']); string(value.accountId, `${path}.accountId`); break;
    case 'jira_transition': object(value, path, ['transitionId', 'comment']); string(value.transitionId, `${path}.transitionId`); nullable(value.comment, `${path}.comment`, (item, itemPath) => string(item, itemPath, {min: 0})); break;
    case 'jira_comment': object(value, path, ['body']); string(value.body, `${path}.body`); break;
    case 'jira_create':
      object(value, path, ['projectKey', 'issueType', 'title', 'description', 'dueDate', 'priority']);
      string(value.projectKey, `${path}.projectKey`); string(value.issueType, `${path}.issueType`); string(value.title, `${path}.title`); string(value.description, `${path}.description`, {min: 0}); nullable(value.dueDate, `${path}.dueDate`, realDate); enumeration(value.priority, `${path}.priority`, PRIORITIES);
      break;
    case 'provisional_link':
      object(value, path, ['delegationId', 'jiraKey', 'jiraUrl']); string(value.delegationId, `${path}.delegationId`, {pattern: UUID_V4}); string(value.jiraKey, `${path}.jiraKey`, {pattern: JIRA_KEY}); assertHttpsUrl(value.jiraUrl, `${path}.jiraUrl`);
      break;
    case 'urgent_displacement':
      object(value, path, ['displacedBlockIds', 'replacementTaskId']); strings(value.displacedBlockIds, `${path}.displacedBlockIds`, {min: 1, unique: true}); string(value.replacementTaskId, `${path}.replacementTaskId`);
      break;
    case 'scope_expand':
      object(value, path, ['connector', 'resourceIds']); enumeration(value.connector, `${path}.connector`, ['jira', 'calendar', 'reminders', 'slack']); strings(value.resourceIds, `${path}.resourceIds`, {min: 1, unique: true});
      break;
    default: fail('operation.kind', 'is not supported');
  }
  return value;
}

export function assertOperation(value) {
  const required = ['schemaVersion', 'id', 'planRevision', 'kind', 'targetSystem', 'targetId', 'payload', 'idempotencyKey', 'approval', 'preconditionRevision', 'retryState', 'createdAt'];
  object(value, 'operation', required);
  integer(value.schemaVersion, 'operation.schemaVersion', 1, 1); string(value.id, 'operation.id'); integer(value.planRevision, 'operation.planRevision', 1); enumeration(value.kind, 'operation.kind', OPERATION_KINDS); enumeration(value.targetSystem, 'operation.targetSystem', ['jira', 'calendar', 'reminders', 'local']);
  if (value.targetSystem !== OPERATION_SYSTEMS[value.kind]) fail('operation.targetSystem', `must be ${OPERATION_SYSTEMS[value.kind]} for ${value.kind}`);
  if (value.kind === 'calendar_upsert') nullable(value.targetId, 'operation.targetId', string); else string(value.targetId, 'operation.targetId');
  operationPayload(value.kind, value.payload); string(value.idempotencyKey, 'operation.idempotencyKey', {pattern: /^[0-9a-f]{64}$/}); enumeration(value.approval, 'operation.approval', APPROVAL); nullable(value.preconditionRevision, 'operation.preconditionRevision', string); enumeration(value.retryState, 'operation.retryState', RETRY_STATES); isoDateTime(value.createdAt, 'operation.createdAt');
  return value;
}

function stableJson(value, ancestors = new WeakSet()) {
  if (value === null || typeof value === 'boolean' || typeof value === 'string') return JSON.stringify(value);
  if (typeof value === 'number') { if (!Number.isFinite(value)) fail('payload', 'must contain only finite JSON values'); return JSON.stringify(value); }
  if (typeof value === 'object' && value !== null && ancestors.has(value)) fail('payload', 'must not contain cycles');
  if (Array.isArray(value)) {
    ancestors.add(value);
    const items = [];
    for (let index = 0; index < value.length; index += 1) {
      if (!Object.hasOwn(value, index)) fail('payload', 'must not contain sparse arrays');
      items.push(stableJson(value[index], ancestors));
    }
    ancestors.delete(value);
    return `[${items.join(',')}]`;
  }
  if (!isObject(value)) fail('payload', 'must be JSON data');
  ancestors.add(value);
  const result = `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${stableJson(value[key], ancestors)}`).join(',')}}`;
  ancestors.delete(value);
  return result;
}

export function operationKey(revision, kind, targetId, payload) {
  return createHash('sha256').update(stableJson({revision, kind, targetId, payload})).digest('hex');
}

export {JIRA_KEY, UUID_V4, realDate, isoDateTime};
