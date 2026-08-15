import {ApiError, exactObject} from './auth.mjs';

const expectedRequest = Object.freeze({
  schemaVersion: 1,
  scope: {reminders: 'plugin-owned', calendar: 'plugin-owned'},
  ownership: {remindersMarkerPrefix: 'rhize-tasks:item:', calendarPrivateProperty: 'rhizeOperationKey'},
  requireVerifiedResults: true,
});

function assertCleanupRequest(request) {
  try {
    exactObject(request, ['schemaVersion', 'scope', 'ownership', 'requireVerifiedResults']);
    exactObject(request.scope, ['reminders', 'calendar']); exactObject(request.ownership, ['remindersMarkerPrefix', 'calendarPrivateProperty']);
  } catch { throw new Error('cleanup_request_invalid'); }
  if (JSON.stringify(request) !== JSON.stringify(expectedRequest)) throw new Error('cleanup_request_invalid');
}

function attempted(operation) { return Number.isInteger(operation.attemptCount) && operation.attemptCount > 0; }

export async function cleanupPluginItems({request, profile, operations, connectors, calendarCleanup}) {
  assertCleanupRequest(request);
  if (!profile?.reminders?.tasksListId || !profile?.calendar?.focusCalendarId || !Array.isArray(operations)) throw new Error('cleanup_unavailable');
  const reminders = connectors?.reminders;
  if (!reminders || typeof reminders.readSnapshot !== 'function' || typeof reminders.applyOperation !== 'function' || typeof calendarCleanup !== 'function') throw new Error('cleanup_unavailable');
  const reminderIds = [...new Set(operations.filter(operation => operation.kind === 'reminder_upsert' && operation.targetSystem === 'reminders' && attempted(operation) && operation.payload?.listId === profile.reminders.tasksListId && typeof operation.payload.externalId === 'string').map(operation => operation.payload.externalId))];
  const calendarKeys = [...new Set(operations.filter(operation => operation.kind === 'calendar_upsert' && operation.targetSystem === 'calendar' && attempted(operation) && operation.payload?.calendarId === profile.calendar.focusCalendarId && /^[0-9a-f]{64}$/.test(operation.idempotencyKey)).map(operation => operation.idempotencyKey))];
  let before;
  try { before = await reminders.readSnapshot(); } catch { throw new Error('cleanup_unavailable'); }
  if (!Array.isArray(before) || before.some(item => !item || typeof item.id !== 'string')) throw new Error('cleanup_unverified');
  const present = reminderIds.filter(id => before.some(item => item.id === id));
  for (const id of present) {
    let result;
    try { result = await reminders.applyOperation({kind: 'reminder_delete', targetId: id, payload: {}, idempotencyKey: operations.find(operation => operation.payload?.externalId === id)?.idempotencyKey ?? '0'.repeat(64)}); } catch { throw new Error('cleanup_unavailable'); }
    if (!result || result.externalId !== id || typeof result.revision !== 'string' || !result.revision) throw new Error('cleanup_unverified');
  }
  let after;
  try { after = await reminders.readSnapshot(); } catch { throw new Error('cleanup_unavailable'); }
  if (!Array.isArray(after) || present.some(id => after.some(item => item?.id === id))) throw new Error('cleanup_unverified');
  let calendarDeleted;
  try { calendarDeleted = await calendarCleanup(calendarKeys); } catch { throw new Error('cleanup_unavailable'); }
  if (!Number.isInteger(calendarDeleted) || calendarDeleted < 0) throw new Error('cleanup_unverified');
  return {ok: true, reminders: {verified: true, deleted: present.length}, calendar: {verified: true, deleted: calendarDeleted}};
}

export function cleanupApiError(error) {
  return new ApiError(error?.message === 'cleanup_request_invalid' ? 'cleanup_request_invalid' : error?.message === 'cleanup_unverified' ? 'cleanup_unverified' : 'cleanup_unavailable', error?.message === 'cleanup_request_invalid' ? 400 : 503);
}

export {expectedRequest as uninstallCleanupRequest};
