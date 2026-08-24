import {operationKey} from '../domain.mjs';
import {ApiError, exactObject} from './auth.mjs';

const connectors = ['jira', 'calendar', 'reminders', 'slack'];

const stable = value => {
  const canonical = item => item === null || typeof item !== 'object' ? item : Array.isArray(item) ? item.map(canonical).sort((left, right) => JSON.stringify(left) < JSON.stringify(right) ? -1 : JSON.stringify(left) > JSON.stringify(right) ? 1 : 0) : Object.fromEntries(Object.keys(item).sort().map(key => [key, canonical(item[key])]));
  return JSON.stringify(canonical(value));
};
const changed = (left, right) => stable(left) !== stable(right);
const additions = (before = [], after = []) => after.filter(value => !before.includes(value));
const strings = (value, {empty = false} = {}) => Array.isArray(value) && (empty || value.length > 0) && value.every(item => typeof item === 'string' && item.length > 0) && new Set(value).size === value.length;

export function validateConnectorConfig(value) {
  exactObject(value, ['slack']);
  if (value.slack === null) return value;
  exactObject(value.slack, ['workspaceId', 'channelId', 'senderIds']);
  if (typeof value.slack.workspaceId !== 'string' || !value.slack.workspaceId || typeof value.slack.channelId !== 'string' || !value.slack.channelId || !Array.isArray(value.slack.senderIds) || value.slack.senderIds.length === 0 || value.slack.senderIds.some(id => typeof id !== 'string' || !id) || new Set(value.slack.senderIds).size !== value.slack.senderIds.length) throw new ApiError('invalid_connector_config');
  return value;
}

export function profileScopeChanges(before, after) {
  if (!before) return [];
  const result = [];
  const jira = [...additions(before.jira.projects, after.jira.projects), ...additions(before.jira.issueTypes, after.jira.issueTypes)];
  if (jira.length) result.push({connector: 'jira', resourceIds: jira});
  const calendar = additions(before.calendar.readCalendarIds, after.calendar.readCalendarIds);
  if (before.calendar.focusCalendarId !== after.calendar.focusCalendarId) calendar.push(`focus:${before.calendar.focusCalendarId}->${after.calendar.focusCalendarId}`);
  if (calendar.length) result.push({connector: 'calendar', resourceIds: calendar});
  const beforeAwareness = before.reminders.awarenessLists.map(item => item.id); const afterAwareness = after.reminders.awarenessLists.map(item => item.id);
  const reminders = additions(beforeAwareness, afterAwareness);
  if (before.reminders.tasksListId !== after.reminders.tasksListId) reminders.push(`tasks:${before.reminders.tasksListId}->${after.reminders.tasksListId}`);
  if (reminders.length) result.push({connector: 'reminders', resourceIds: reminders});
  return result;
}

export function connectorScopeChanges(before, after) {
  if (!before) return [];
  const oldSlack = before.slack; const nextSlack = after.slack;
  if (!oldSlack && !nextSlack) return [];
  const resources = [];
  if (!oldSlack && nextSlack) resources.push(`workspace:${nextSlack.workspaceId}`, `channel:${nextSlack.channelId}`, ...nextSlack.senderIds);
  else if (oldSlack && nextSlack) {
    if (oldSlack.workspaceId !== nextSlack.workspaceId) resources.push(`workspace:${oldSlack.workspaceId}->${nextSlack.workspaceId}`);
    if (oldSlack.channelId !== nextSlack.channelId) resources.push(`channel:${oldSlack.channelId}->${nextSlack.channelId}`);
    resources.push(...additions(oldSlack.senderIds, nextSlack.senderIds));
  }
  return resources.length ? [{connector: 'slack', resourceIds: resources}] : [];
}

export function planningMaterialChanged(before, after) {
  if (!before) return false;
  const select = profile => ({
    timezone: profile.identity.timezone,
    jira: profile.jira,
    calendar: profile.calendar,
    reminders: profile.reminders,
    workingIntervals: profile.workingIntervals, breaks: profile.breaks, capacity: profile.capacity, planning: profile.planning, routines: profile.routines,
  });
  return changed(select(before), select(after));
}

export function validateSetupScope(connector, scope) {
  if (!connectors.includes(connector)) throw new ApiError('invalid_connector');
  if (connector === 'jira') {
    exactObject(scope, ['projectKeys', 'issueTypes']);
    if (!strings(scope.projectKeys) || !strings(scope.issueTypes)) throw new ApiError('invalid_setup_scope');
  } else if (connector === 'calendar') {
    exactObject(scope, ['readCalendarIds', 'focusCalendarId']);
    if (!strings(scope.readCalendarIds) || typeof scope.focusCalendarId !== 'string' || !scope.focusCalendarId || !scope.readCalendarIds.includes(scope.focusCalendarId)) throw new ApiError('invalid_setup_scope');
  } else if (connector === 'reminders') {
    exactObject(scope, ['awarenessListIds', 'tasksListId']);
    if (!strings(scope.awarenessListIds, {empty: true}) || typeof scope.tasksListId !== 'string' || !scope.tasksListId || scope.awarenessListIds.includes(scope.tasksListId)) throw new ApiError('invalid_setup_scope');
  } else {
    validateConnectorConfig({slack: scope});
  }
  return structuredClone(scope);
}

export function scopeResourceIds(connector, scope) {
  const value = validateSetupScope(connector, scope);
  if (connector === 'jira') return [...value.projectKeys.map(id => `project:${id}`), ...value.issueTypes.map(id => `issueType:${id}`)].sort();
  if (connector === 'calendar') return [...value.readCalendarIds.map(id => `read:${id}`), `focus:${value.focusCalendarId}`].sort();
  if (connector === 'reminders') return [...value.awarenessListIds.map(id => `awareness:${id}`), `tasks:${value.tasksListId}`].sort();
  return [`workspace:${value.workspaceId}`, `channel:${value.channelId}`, ...value.senderIds.map(id => `sender:${id}`)].sort();
}

export function validateDiscoveredScope(connector, scope, discovery) {
  const selected = validateSetupScope(connector, scope); let available;
  if (connector === 'jira') available = {projectKeys: new Set(discovery?.projects?.map(item => item?.key)), issueTypes: new Set(discovery?.issueTypes?.map(item => item?.name))};
  else if (connector === 'calendar') available = {calendarIds: new Set(Array.isArray(discovery) ? discovery.map(item => item?.id) : [])};
  else if (connector === 'reminders') available = {listIds: new Set(discovery?.lists?.map(item => item?.id))};
  else available = discovery;
  const valid = connector === 'jira' ? selected.projectKeys.every(id => available.projectKeys.has(id)) && selected.issueTypes.every(id => available.issueTypes.has(id))
    : connector === 'calendar' ? selected.readCalendarIds.every(id => available.calendarIds.has(id))
      : connector === 'reminders' ? [selected.tasksListId, ...selected.awarenessListIds].every(id => available.listIds.has(id))
        : changed(selected, available) === false;
  if (!valid) throw new ApiError('setup_scope_not_discovered');
  return selected;
}

export function profileSetupScopes(profile) {
  return {
    jira: {projectKeys: profile.jira.projects, issueTypes: profile.jira.issueTypes},
    calendar: {readCalendarIds: profile.calendar.readCalendarIds, focusCalendarId: profile.calendar.focusCalendarId},
    reminders: {awarenessListIds: profile.reminders.awarenessLists.map(item => item.id), tasksListId: profile.reminders.tasksListId},
  };
}

export function setupScopeCovered(connector, approved, requested) {
  if (!approved) return false;
  const allowed = new Set(scopeResourceIds(connector, approved));
  return scopeResourceIds(connector, requested).every(id => allowed.has(id));
}

export function scopeOperations({planRevision, changes, now}) {
  if (!Number.isInteger(planRevision) || planRevision < 1 || !Array.isArray(changes)) throw new TypeError('invalid_scope_preview');
  return changes.map(({connector, resourceIds}) => {
    if (!connectors.includes(connector)) throw new TypeError('invalid_scope_connector');
    const payload = {connector, resourceIds: [...new Set(resourceIds)].sort()}; const targetId = `scope:${connector}`; const idempotencyKey = operationKey(planRevision, 'scope_expand', targetId, payload);
    return {schemaVersion: 1, id: `scope:${idempotencyKey.slice(0, 24)}`, planRevision, kind: 'scope_expand', targetSystem: 'local', targetId, payload, idempotencyKey, approval: 'required', preconditionRevision: null, retryState: 'pending', createdAt: now};
  });
}
