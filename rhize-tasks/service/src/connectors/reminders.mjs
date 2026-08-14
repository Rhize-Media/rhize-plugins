import {connectorError, normalizeError, unsupported} from './http.mjs';
import {runProcess} from './process-runner.mjs';
const allowed = new Set(['authorize', 'lists', 'snapshot', 'upsert', 'complete', 'delete']);

function helperEnvironment(tasksListId) {
  return Object.fromEntries([
    ['HOME', process.env.HOME],
    ['LANG', process.env.LANG],
    ['TMPDIR', process.env.TMPDIR],
    ['RHIZE_TASKS_REMINDERS_LIST_ID', tasksListId],
  ].filter(([, value]) => typeof value === 'string'));
}

function isNonEmptyString(value) {
  return typeof value === 'string' && value.length > 0;
}

function validateResponse(command, payload, value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw connectorError('malformed_response');
  if (value.ok !== true) {
    if (value.ok === false && isNonEmptyString(value.error)) throw connectorError(value.error, {retryable: false});
    throw connectorError('malformed_response');
  }
  if (command === 'authorize' && value.authorized !== true) throw connectorError('malformed_response');
  if (command === 'lists' && !Array.isArray(value.lists)) throw connectorError('malformed_response');
  if (command === 'snapshot' && !Array.isArray(value.items)) throw connectorError('malformed_response');
  if (command === 'upsert' && (value.id !== payload.externalId || !isNonEmptyString(value.revision))) throw connectorError('malformed_response');
  if ((command === 'complete' || command === 'delete') && (value.id !== payload.id || !isNonEmptyString(value.revision))) throw connectorError('malformed_response');
  return value;
}

export function createRemindersConnector({helperPath, tasksListId, runner = runProcess} = {}) {
  if (!helperPath || !tasksListId || typeof runner !== 'function') throw new TypeError('invalid Reminders connector configuration');
  async function call(command, payload = {}) { if (!allowed.has(command)) throw connectorError('unsupported'); try { const result = await runner(helperPath, [], {input: JSON.stringify({command, ...payload}) + '\n', timeoutMs: 15_000, maxOutputBytes: 1_000_000, env: helperEnvironment(tasksListId)}); if (!result || result.timedOut) throw connectorError('timeout', {retryable: true, ambiguous: ['upsert', 'complete', 'delete'].includes(command)}); if (result.outputExceeded || result.code !== 0 || typeof result.stdout !== 'string' || Buffer.byteLength(result.stdout) > 1_000_000) throw connectorError('helper', {retryable: false}); const lines = result.stdout.split(/\r?\n/).filter(Boolean); if (lines.length !== 1) throw connectorError('malformed_response'); return validateResponse(command, payload, JSON.parse(lines[0])); } catch (error) { if (error?.kind) throw error; if (error instanceof SyntaxError) throw connectorError('malformed_response'); throw normalizeError(error, {afterWrite: ['upsert', 'complete', 'delete'].includes(command)}); } }
  return { async health() { return call('authorize'); }, async discover() { return call('lists'); }, async readSnapshot() { return call('snapshot', {listIds: [tasksListId]}); }, async applyOperation(operation) { const kind = operation?.kind; const payload = operation?.payload; if (!['reminder_upsert', 'reminder_complete', 'reminder_delete'].includes(kind) || !payload || Object.getPrototypeOf(payload) !== Object.prototype) unsupported(); let command; let safePayload; if (kind === 'reminder_upsert') { if (Object.keys(payload).some(key => !['listId', 'title', 'dueAt', 'notes', 'externalId'].includes(key)) || payload.listId !== tasksListId) throw connectorError('out_of_scope'); command = 'upsert'; safePayload = {title: payload.title, dueAt: payload.dueAt, notes: payload.notes, externalId: payload.externalId}; } else if (kind === 'reminder_complete') { if (Object.keys(payload).some(key => key !== 'completedAt')) throw connectorError('invalid_operation'); command = 'complete'; safePayload = {completedAt: payload.completedAt}; } else { if (Object.keys(payload).length !== 0) throw connectorError('invalid_operation'); command = 'delete'; safePayload = {}; } const result = await call(command, {listId: tasksListId, id: operation.targetId, ...safePayload, operationKey: operation.idempotencyKey}); return {externalId: kind === 'reminder_upsert' ? result.id ?? operation.targetId : operation.targetId, revision: String(result.revision ?? result.id ?? operation.idempotencyKey)}; }, async findByExternalId(externalId) { const snapshot = await call('snapshot', {listIds: [tasksListId]}); const value = (snapshot.items ?? snapshot).find(item => item.id === externalId); return value ? {revision: String(value.revision ?? value.updatedAt ?? value.id)} : null; } };
}
