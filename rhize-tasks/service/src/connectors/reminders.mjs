import net from 'node:net';
import {connectorError, normalizeError, unsupported} from './http.mjs';
import {runProcess} from './process-runner.mjs';
const allowed = new Set(['authorize', 'lists', 'snapshot', 'upsert', 'complete', 'delete']);
const DEFAULT_SOCKET_TIMEOUT_MS = 15_000;
const SOCKET_MAX_RESPONSE_BYTES = 1_000_000; // matches callViaSpawn's maxOutputBytes
// Only these connection-level failures mean "no socket server is there" —
// fall back to spawning the helper binary. Any other socket error (timeout,
// mid-response reset, malformed reply) is a real failure of a transport that
// DID connect, and must be surfaced as-is rather than silently retried via a
// second transport (retrying a write op through spawn after an ambiguous
// socket failure could double-apply it).
const SOCKET_FALLBACK_CODES = new Set(['ENOENT', 'ECONNREFUSED']);

function helperEnvironment(allowedListId) {
  return Object.fromEntries([
    ['HOME', process.env.HOME],
    ['LANG', process.env.LANG],
    ['TMPDIR', process.env.TMPDIR],
    ['RHIZE_TASKS_REMINDERS_LIST_ID', allowedListId],
  ].filter(([, value]) => typeof value === 'string'));
}

function isNonEmptyString(value) {
  return typeof value === 'string' && value.length > 0;
}

function validateResponse(command, payload, value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw connectorError('malformed_response');
  if (value.ok !== true) {
    if (value.ok === false && isNonEmptyString(value.error)) throw connectorError(value.error === 'authorization_denied' ? 'authorization' : value.error, {retryable: false});
    throw connectorError('malformed_response');
  }
  if (command === 'authorize' && value.authorized !== true) throw connectorError('malformed_response');
  if (command === 'lists' && !Array.isArray(value.lists)) throw connectorError('malformed_response');
  if (command === 'snapshot' && !Array.isArray(value.items)) throw connectorError('malformed_response');
  if (command === 'upsert' && (value.id !== payload.externalId || !isNonEmptyString(value.revision))) throw connectorError('malformed_response');
  if ((command === 'complete' || command === 'delete') && (value.id !== payload.id || !isNonEmptyString(value.revision))) throw connectorError('malformed_response');
  return value;
}

// Unix-socket transport per the pinned cross-agent IPC contract: connect,
// write ONE newline-terminated JSON request (identical body to the stdin
// protocol below), read until the server closes the connection, then treat
// whatever arrived as the single JSON-line response. The server is expected
// to write exactly one line and close — buffering until 'close' (rather than
// resolving on the first newline) lets us apply the same "exactly one line"
// strictness the spawn path already enforces, instead of trusting the first
// newline blindly.
function callSocket({socketPath, request, timeoutMs, createConnection}) {
  return new Promise((resolve, reject) => {
    let settled = false;
    let buffer = '';
    let receivedBytes = 0;
    let timer;
    const socket = createConnection(socketPath);
    const finish = (isResolve, value) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      socket.removeAllListeners();
      socket.destroy();
      if (isResolve) resolve(value); else reject(value);
    };
    timer = setTimeout(() => finish(false, Object.assign(new Error('reminders_socket_timeout'), {code: 'ETIMEDOUT'})), timeoutMs);
    timer.unref?.();
    socket.on('connect', () => socket.write(`${JSON.stringify(request)}\n`));
    socket.on('data', chunk => {
      // Same cap as callViaSpawn's maxOutputBytes, enforced the same way: stop
      // accumulating and tear down the connection rather than let a runaway
      // or malicious server grow this buffer unbounded.
      receivedBytes += chunk.length;
      if (receivedBytes > SOCKET_MAX_RESPONSE_BYTES) { finish(false, Object.assign(new Error('reminders_socket_response_too_large'), {code: 'ERESPONSETOOLARGE'})); return; }
      buffer += chunk.toString('utf8');
    });
    socket.on('error', error => finish(false, error));
    socket.on('close', () => finish(true, buffer));
  });
}

export function createRemindersConnector({helperPath, tasksListId, awarenessListIds = [], awarenessLists, runner = runProcess, socketPath, socketTimeoutMs = DEFAULT_SOCKET_TIMEOUT_MS, createConnection = net.createConnection} = {}) {
  const configuredAwareness = awarenessLists ?? awarenessListIds.map(id => ({id, showTitles: false}));
  if (!helperPath || !tasksListId || !Array.isArray(configuredAwareness) || configuredAwareness.some(item => !item || typeof item.id !== 'string' || !item.id || typeof item.showTitles !== 'boolean') || typeof runner !== 'function') throw new TypeError('invalid Reminders connector configuration');
  if (socketPath !== undefined && (typeof socketPath !== 'string' || socketPath.length === 0)) throw new TypeError('invalid Reminders connector configuration');
  if (!Number.isFinite(socketTimeoutMs) || socketTimeoutMs <= 0 || typeof createConnection !== 'function') throw new TypeError('invalid Reminders connector configuration');
  async function callViaSpawn(command, payload, allowedListId) {
    const result = await runner(helperPath, [], {input: `${JSON.stringify({command, ...payload})}\n`, timeoutMs: 15_000, maxOutputBytes: 1_000_000, env: helperEnvironment(allowedListId)});
    if (!result || result.timedOut) throw connectorError('timeout', {retryable: true, ambiguous: ['upsert', 'complete', 'delete'].includes(command)});
    if (result.outputExceeded || result.code !== 0 || typeof result.stdout !== 'string' || Buffer.byteLength(result.stdout) > 1_000_000) throw connectorError('helper', {retryable: false});
    return result.stdout;
  }
  async function call(command, payload = {}, allowedListId = tasksListId) {
    if (!allowed.has(command)) throw connectorError('unsupported');
    const ambiguous = ['upsert', 'complete', 'delete'].includes(command);
    let transport = socketPath ? 'socket' : 'spawn';
    try {
      let raw;
      if (socketPath) {
        try {
          // allowedListId travels as an explicit request field, never inferred
          // from payload.listId/listIds — the socket protocol has no env-var
          // side channel like the spawn path's RHIZE_TASKS_REMINDERS_LIST_ID,
          // so this is the only way the served helper can learn (and enforce)
          // which list this call is scoped to. Placed after ...payload so
          // caller-supplied payload data can never shadow the real scope.
          raw = await callSocket({socketPath, request: {command, ...payload, allowedListId}, timeoutMs: socketTimeoutMs, createConnection});
        } catch (error) {
          if (!SOCKET_FALLBACK_CODES.has(error?.code)) throw error;
          transport = 'spawn';
          raw = await callViaSpawn(command, payload, allowedListId);
        }
      } else {
        raw = await callViaSpawn(command, payload, allowedListId);
      }
      // Socket-only ambiguity note: once the request bytes for a write command
      // have been written to the socket, a failure to get back a clean,
      // complete, single-line response (multi-line, empty/close-without-data,
      // unparseable/truncated JSON, or the size cap below) means the mutation
      // may already have been applied server-side — we just lost the ability
      // to confirm it. Those cases are marked ambiguous the same way the
      // spawn path already marks a write timeout ambiguous; a business-level
      // rejection from a *complete, valid* response (validateResponse below)
      // is not touched, since that's the server explicitly telling us what
      // happened, not a torn/lost response.
      const lines = raw.split(/\r?\n/).filter(Boolean);
      if (lines.length !== 1) throw connectorError('malformed_response', {ambiguous: transport === 'socket' && ambiguous});
      return validateResponse(command, payload, JSON.parse(lines[0]));
    } catch (error) {
      if (error?.kind) { error.transport = error.transport ?? transport; throw error; }
      if (error instanceof SyntaxError) { const wrapped = connectorError('malformed_response', {ambiguous: transport === 'socket' && ambiguous}); wrapped.transport = transport; throw wrapped; }
      if (error?.code === 'ETIMEDOUT') { const wrapped = connectorError('timeout', {retryable: true, ambiguous}); wrapped.transport = transport; throw wrapped; }
      if (error?.code === 'ERESPONSETOOLARGE') { const wrapped = connectorError('helper', {retryable: false, ambiguous: transport === 'socket' && ambiguous}); wrapped.transport = transport; throw wrapped; }
      const normalized = normalizeError(error, {afterWrite: ambiguous});
      normalized.transport = transport;
      throw normalized;
    }
  }
  return { async health() { return call('authorize'); }, async discover() { return call('lists'); }, async readSnapshot() { const items = []; for (const entry of [{id: tasksListId, showTitles: true}, ...configuredAwareness.filter(item => item.id !== tasksListId)]) { const response = await call('snapshot', {listIds: [entry.id], ...(entry.showTitles ? {} : {redactTitles: true})}, entry.id); items.push(...response.items); } return items; }, async applyOperation(operation) { const kind = operation?.kind; const payload = operation?.payload; if (!['reminder_upsert', 'reminder_complete', 'reminder_delete'].includes(kind) || !payload || Object.getPrototypeOf(payload) !== Object.prototype) unsupported(); let command; let safePayload; if (kind === 'reminder_upsert') { if (Object.keys(payload).some(key => !['listId', 'title', 'dueAt', 'notes', 'externalId'].includes(key)) || payload.listId !== tasksListId) throw connectorError('out_of_scope'); command = 'upsert'; safePayload = {title: payload.title, dueAt: payload.dueAt, notes: payload.notes, externalId: payload.externalId}; } else if (kind === 'reminder_complete') { if (Object.keys(payload).some(key => key !== 'completedAt')) throw connectorError('invalid_operation'); command = 'complete'; safePayload = {completedAt: payload.completedAt}; } else { if (Object.keys(payload).length !== 0) throw connectorError('invalid_operation'); command = 'delete'; safePayload = {}; } const result = await call(command, {listId: tasksListId, id: operation.targetId, ...safePayload, operationKey: operation.idempotencyKey}); return {externalId: kind === 'reminder_upsert' ? result.id ?? operation.targetId : operation.targetId, revision: String(result.revision ?? result.id ?? operation.idempotencyKey)}; }, async findByExternalId(externalId) { const snapshot = await call('snapshot', {listIds: [tasksListId]}); const value = (snapshot.items ?? snapshot).find(item => item.id === externalId); return value ? {revision: String(value.revision ?? value.updatedAt ?? value.id)} : null; } };
}
