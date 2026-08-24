import assert from 'node:assert/strict';
import net from 'node:net';
import {mkdtemp, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import test from 'node:test';
import {createRemindersConnector} from '../../service/src/connectors/reminders.mjs';
import {createSlackConnector} from '../../service/src/connectors/slack.mjs';

const response = body => ({status: 200, headers: {}, body});
const credentials = {async get() { return 'secret'; }};

// Stub Unix-socket server matching the pinned cross-agent IPC contract: read
// one newline-terminated JSON request, write one JSON-line response, close.
// Never spawns the real helper binary and never touches EventKit.
async function startStubSocketServer(handler) {
  const dir = await mkdtemp(path.join(tmpdir(), 'rhize-reminders-socket-'));
  const socketPath = path.join(dir, 'helper.sock');
  const server = net.createServer(socket => {
    let buffer = '';
    socket.on('data', chunk => {
      buffer += chunk.toString('utf8');
      const newlineIndex = buffer.indexOf('\n');
      if (newlineIndex === -1) return;
      const request = JSON.parse(buffer.slice(0, newlineIndex));
      const raw = handler(request, socket);
      if (raw !== undefined) socket.end(raw);
    });
  });
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(socketPath, resolve); });
  return {
    socketPath,
    async close() { await new Promise(resolve => server.close(resolve)); await rm(dir, {recursive: true, force: true}); },
  };
}

test('Reminders socket transport writes one newline-terminated JSON request and parses the one-line response', async () => {
  let received;
  const stub = await startStubSocketServer(request => { received = request; return `${JSON.stringify({ok: true, authorized: true})}\n`; });
  try {
    const reminders = createRemindersConnector({helperPath: '/helper', tasksListId: 'tasks', socketPath: stub.socketPath, runner: async () => { throw new Error('spawn must not be used when the socket succeeds'); }});
    const result = await reminders.health();
    assert.equal(result.authorized, true);
    assert.equal(received.command, 'authorize');
  } finally { await stub.close(); }
});

test('Reminders socket maps error codes exactly as the spawn path (authorization_denied -> kind authorization) and tags transport', async () => {
  const stub = await startStubSocketServer(() => `${JSON.stringify({ok: false, error: 'authorization_denied'})}\n`);
  try {
    const reminders = createRemindersConnector({helperPath: '/helper', tasksListId: 'tasks', socketPath: stub.socketPath, runner: async () => { throw new Error('spawn must not be used'); }});
    await assert.rejects(reminders.health(), error => error.kind === 'authorization' && error.retryable === false && error.transport === 'socket');
  } finally { await stub.close(); }
});

test('Reminders socket enforces the same single-line strictness as spawn (malformed_response on extra lines), and does not mark a read command ambiguous', async () => {
  const stub = await startStubSocketServer(() => '{}\n{}\n');
  try {
    const reminders = createRemindersConnector({helperPath: '/helper', tasksListId: 'tasks', socketPath: stub.socketPath, runner: async () => { throw new Error('spawn must not be used'); }});
    await assert.rejects(reminders.health(), error => error.kind === 'malformed_response' && error.transport === 'socket' && error.ambiguous === false);
  } finally { await stub.close(); }
});

test('Reminders socket marks a WRITE command ambiguous on a multi-line/malformed response (mutation may already have applied)', async () => {
  const stub = await startStubSocketServer(() => '{}\n{}\n');
  try {
    const reminders = createRemindersConnector({helperPath: '/helper', tasksListId: 'tasks', socketPath: stub.socketPath, runner: async () => { throw new Error('spawn must not be used'); }});
    await assert.rejects(
      reminders.applyOperation({kind: 'reminder_complete', targetId: 'r1', idempotencyKey: 'op-1', payload: {completedAt: '2020-01-01T00:00:00.000Z'}}),
      error => error.kind === 'malformed_response' && error.ambiguous === true && error.transport === 'socket',
    );
  } finally { await stub.close(); }
});

test('Reminders socket marks a WRITE command ambiguous when the connection closes with no response at all', async () => {
  const dir = await mkdtemp(path.join(tmpdir(), 'rhize-reminders-empty-close-'));
  const socketPath = path.join(dir, 'helper.sock');
  const acceptedSockets = new Set();
  const server = net.createServer(socket => { acceptedSockets.add(socket); socket.on('error', () => {}); socket.on('close', () => acceptedSockets.delete(socket)); socket.end(); }); // accept then immediately close, writing nothing
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(socketPath, resolve); });
  try {
    const reminders = createRemindersConnector({helperPath: '/helper', tasksListId: 'tasks', socketPath, runner: async () => { throw new Error('spawn must not be used'); }});
    await assert.rejects(
      reminders.applyOperation({kind: 'reminder_delete', targetId: 'r1', idempotencyKey: 'op-1', payload: {}}),
      error => error.kind === 'malformed_response' && error.ambiguous === true && error.transport === 'socket',
    );
  } finally {
    for (const socket of acceptedSockets) socket.destroy();
    await new Promise(resolve => server.close(resolve));
    await rm(dir, {recursive: true, force: true});
  }
});

test('Reminders enforces the spawn path\'s 1MB response cap on the socket transport too, marking a WRITE command ambiguous', async () => {
  const dir = await mkdtemp(path.join(tmpdir(), 'rhize-reminders-oversize-'));
  const socketPath = path.join(dir, 'helper.sock');
  const acceptedSockets = new Set();
  const server = net.createServer(socket => {
    acceptedSockets.add(socket);
    socket.on('error', () => {});
    socket.on('close', () => acceptedSockets.delete(socket));
    // Stream well past 1MB without ever completing a valid response line.
    const chunk = 'x'.repeat(64 * 1024);
    let written = 0;
    const pump = () => {
      if (socket.destroyed || written > 1_100_000) return;
      written += chunk.length;
      if (socket.write(chunk)) pump(); else socket.once('drain', pump);
    };
    pump();
  });
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(socketPath, resolve); });
  try {
    const reminders = createRemindersConnector({helperPath: '/helper', tasksListId: 'tasks', socketPath, runner: async () => { throw new Error('spawn must not be used'); }});
    await assert.rejects(
      reminders.applyOperation({kind: 'reminder_complete', targetId: 'r1', idempotencyKey: 'op-1', payload: {completedAt: '2020-01-01T00:00:00.000Z'}}),
      error => error.kind === 'helper' && error.retryable === false && error.ambiguous === true && error.transport === 'socket',
    );
  } finally {
    for (const socket of acceptedSockets) socket.destroy();
    await new Promise(resolve => server.close(resolve));
    await rm(dir, {recursive: true, force: true});
  }
});

test('Reminders socket request carries allowedListId per call, matching the spawn path\'s per-call RHIZE_TASKS_REMINDERS_LIST_ID scope', async () => {
  const received = [];
  const stub = await startStubSocketServer(request => { received.push(request); return `${JSON.stringify({ok: true, items: []})}\n`; });
  try {
    const reminders = createRemindersConnector({helperPath: '/helper', tasksListId: 'tasks-list', awarenessListIds: ['aware-list'], socketPath: stub.socketPath, runner: async () => { throw new Error('spawn must not be used'); }});
    await reminders.readSnapshot(); // fetches the tasks list, then each awareness list, each scoped separately
    assert.deepEqual(received.map(item => item.allowedListId), ['tasks-list', 'aware-list']);
    assert.deepEqual(received.map(item => item.listIds), [['tasks-list'], ['aware-list']]);
  } finally { await stub.close(); }
});

test('Reminders falls back to spawn when the socket path does not exist (ENOENT), and surfaces transport spawn on the eventual result path', async () => {
  const dir = await mkdtemp(path.join(tmpdir(), 'rhize-reminders-missing-'));
  const missingSocketPath = path.join(dir, 'nobody-listening.sock');
  try {
    let invoked = false;
    const reminders = createRemindersConnector({helperPath: '/helper', tasksListId: 'tasks', socketPath: missingSocketPath, runner: async (...args) => { invoked = true; return {code: 0, stdout: `${JSON.stringify({ok: true, authorized: true})}\n`, args}; }});
    const result = await reminders.health();
    assert.equal(invoked, true);
    assert.equal(result.authorized, true);
  } finally { await rm(dir, {recursive: true, force: true}); }
});

test('Reminders falls back to spawn when the socket connection is refused (server closed, file gone)', async () => {
  const stub = await startStubSocketServer(() => `${JSON.stringify({ok: true, authorized: true})}\n`);
  const socketPath = stub.socketPath;
  await stub.close(); // server stopped and socket file removed -> ENOENT/ECONNREFUSED on connect
  let invoked = false;
  const reminders = createRemindersConnector({helperPath: '/helper', tasksListId: 'tasks', socketPath, runner: async () => { invoked = true; return {code: 0, stdout: `${JSON.stringify({ok: true, authorized: true})}\n`}; }});
  const result = await reminders.health();
  assert.equal(invoked, true);
  assert.equal(result.authorized, true);
});

test('Reminders does NOT fall back to spawn on a genuine socket timeout, and classifies write timeouts as ambiguous', async () => {
  const dir = await mkdtemp(path.join(tmpdir(), 'rhize-reminders-hang-'));
  const socketPath = path.join(dir, 'helper.sock');
  // Accept the connection and just sit on it: never respond, never close.
  // Track + explicitly destroy accepted sockets in cleanup below — otherwise
  // an un-listened 'error' on the accepted socket can throw uncaught, and
  // server.close()'s callback will not fire until every connection it holds
  // is actually torn down (it does not close them for you).
  const acceptedSockets = new Set();
  const server = net.createServer(socket => { acceptedSockets.add(socket); socket.on('error', () => {}); socket.on('close', () => acceptedSockets.delete(socket)); });
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(socketPath, resolve); });
  try {
    const reminders = createRemindersConnector({helperPath: '/helper', tasksListId: 'tasks', socketPath, socketTimeoutMs: 40, runner: async () => { throw new Error('spawn must not be used on a socket-level timeout'); }});
    await assert.rejects(
      reminders.applyOperation({kind: 'reminder_complete', targetId: 'r1', idempotencyKey: 'op-1', payload: {completedAt: '2020-01-01T00:00:00.000Z'}}),
      error => error.kind === 'timeout' && error.retryable === true && error.ambiguous === true && error.transport === 'socket',
    );
  } finally {
    for (const socket of acceptedSockets) socket.destroy();
    await new Promise(resolve => server.close(resolve));
    await rm(dir, {recursive: true, force: true});
  }
});

test('Reminders spawn-only path (no socketPath configured) still tags transport spawn on errors', async () => {
  const reminders = createRemindersConnector({helperPath: '/helper', tasksListId: 'tasks', runner: async () => ({code: 1, stdout: ''})});
  await assert.rejects(reminders.health(), error => error.kind === 'helper' && error.transport === 'spawn');
});

const validDelegation = ts => ({ts, bot_id: 'B1', text: '*Task:* Audit\n*Due:* 2026-08-17\n*Priority:* high\n*Jira:* needs_jira\nrhize-delegation:v1:550e8400-e29b-41d4-a716-446655440000'});

test('Slack readSnapshot honors an explicit per-call oldest over the historyLookbackMs default, and returns items with a non-enumerable syncMeta', async () => {
  const requests = [];
  const slack = createSlackConnector({
    workspaceId: 'T1', channelId: 'C1', senderIds: ['B1'], credentials,
    transport: async request => {
      requests.push(request);
      if (request.url.includes('conversations.history')) return response({ok: true, messages: [{ts: '100.000000', thread_ts: '100.000000'}]});
      return response({ok: true, messages: [{ts: '100.000000'}, validDelegation('100.500000')]});
    },
  });
  const items = await slack.readSnapshot({oldest: 42});
  const historyRequest = requests.find(request => request.url.includes('conversations.history'));
  assert.match(decodeURIComponent(historyRequest.url), /oldest=42\.000000/);
  assert.equal(items.length, 1);
  assert.equal(Array.isArray(items), true);
  assert.equal(items.syncMeta.latestTs, 100.5); // advances over the fetched reply's ts, not just the parent's
  assert.equal(items.syncMeta.truncated, false);
  assert.equal(Object.keys(items).includes('syncMeta'), false); // non-enumerable
  assert.equal(JSON.stringify(items), JSON.stringify([items[0]])); // array-shaped for existing consumers
});

test('Slack readSnapshot falls back to the historyLookbackMs-derived oldest when none is given, and rejects an invalid oldest', async () => {
  const requests = [];
  const fixedNow = new Date('2026-08-17T00:00:00.000Z');
  const historyLookbackMs = 3 * 24 * 60 * 60 * 1000;
  const slack = createSlackConnector({
    workspaceId: 'T1', channelId: 'C1', senderIds: ['B1'], credentials, now: () => fixedNow, historyLookbackMs,
    transport: async request => { requests.push(request); return response({ok: true, messages: []}); },
  });
  await slack.readSnapshot();
  const expected = ((fixedNow.getTime() - historyLookbackMs) / 1000).toFixed(6);
  assert.match(decodeURIComponent(requests[0].url), new RegExp(`oldest=${expected.replace('.', '\\.')}`));
  await assert.rejects(slack.readSnapshot({oldest: -1}), TypeError);
});

test('Slack readSnapshot reports truncated=true when the budget cuts off top-level channel-history pagination', async () => {
  let historyCalls = 0;
  const slack = createSlackConnector({
    workspaceId: 'T1', channelId: 'C1', senderIds: ['B1'], credentials, maxPagesPerSync: 1,
    transport: async request => {
      if (request.url.includes('conversations.history')) { historyCalls += 1; return response({ok: true, messages: [{ts: '100.000000'}], response_metadata: {next_cursor: 'more'}}); }
      return response({ok: true, messages: []});
    },
  });
  const items = await slack.readSnapshot();
  assert.equal(historyCalls, 1); // budget exhausted after the first page, no second page fetched
  assert.equal(items.syncMeta.truncated, true);
  assert.equal(items.syncMeta.latestTs, 100); // the fetched prefix still holds the true newest ts (newest-first pagination)
});

test('Slack readSnapshot reports truncated=true when the budget runs out before fetching a known thread\'s replies', async () => {
  const requests = [];
  const slack = createSlackConnector({
    workspaceId: 'T1', channelId: 'C1', senderIds: ['B1'], credentials, maxPagesPerSync: 1,
    transport: async request => { requests.push(request); return response({ok: true, messages: [{ts: '100.000000', thread_ts: '100.000000'}]}); },
  });
  const items = await slack.readSnapshot();
  assert.equal(requests.filter(request => request.url.includes('conversations.replies')).length, 0); // budget spent on history; replies never fetched
  assert.equal(items.syncMeta.truncated, true);
  assert.equal(items.syncMeta.latestTs, 100);
});

test('Slack readSnapshot reports latestTs=null and truncated=false when the channel history window is empty', async () => {
  const slack = createSlackConnector({
    workspaceId: 'T1', channelId: 'C1', senderIds: ['B1'], credentials,
    transport: async () => response({ok: true, messages: []}),
  });
  const items = await slack.readSnapshot();
  assert.equal(items.length, 0);
  assert.equal(items.syncMeta.latestTs, null);
  assert.equal(items.syncMeta.truncated, false);
});

// #8 regression: conversations.history must always scan the full lookback
// window for parents (never bounded by replyWatermark) so an old thread
// parent stays visible; replyWatermark only gates whether conversations.replies
// is worth paginating for that parent.
const REPLY_WATERMARK = 1_700_000_000; // arbitrary fixed epoch-seconds anchor
const GRACE_BOUNDARY = REPLY_WATERMARK - 24 * 60 * 60; // default 24h grace

test('Slack readSnapshot fetches replies for an old parent whose latest_reply is newer than watermark-24h grace (new reply to an old thread is not missed)', async () => {
  const requests = [];
  const oldParent = {ts: '1699000000.000000', thread_ts: '1699000000.000000', latest_reply: '1700000500.000000'}; // parent far older than watermark; latest_reply just after it
  const slack = createSlackConnector({
    workspaceId: 'T1', channelId: 'C1', senderIds: ['B1'], credentials,
    transport: async request => {
      requests.push(request);
      if (request.url.includes('conversations.history')) return response({ok: true, messages: [oldParent]});
      return response({ok: true, messages: [oldParent, validDelegation('1700000500.000000')]});
    },
  });
  const items = await slack.readSnapshot({replyWatermark: REPLY_WATERMARK});
  assert.equal(requests.some(request => request.url.includes('conversations.replies') && request.url.includes(`ts=${encodeURIComponent(oldParent.ts)}`)), true);
  assert.equal(items.length, 1); // the new reply to the old thread was ingested
  assert.equal(items.syncMeta.latestTs, 1700000500); // watermark advances over the reply activity, not just the (older) parent ts
});

test('Slack readSnapshot skips replies pagination for an old parent whose latest_reply is older than watermark-24h grace', async () => {
  const requests = [];
  const staleParent = {ts: '1699000000.000000', thread_ts: '1699000000.000000', latest_reply: String(GRACE_BOUNDARY - 1)}; // one second before the grace boundary
  const slack = createSlackConnector({
    workspaceId: 'T1', channelId: 'C1', senderIds: ['B1'], credentials,
    transport: async request => { requests.push(request); return response({ok: true, messages: [staleParent]}); },
  });
  const items = await slack.readSnapshot({replyWatermark: REPLY_WATERMARK});
  assert.equal(requests.some(request => request.url.includes('conversations.replies')), false); // no reply pagination attempted at all
  assert.equal(items.length, 0);
  assert.equal(items.syncMeta.latestTs, 1699000000); // only the parent's own ts was observed
  assert.equal(items.syncMeta.truncated, false); // a watermark-driven skip is not a truncation
});

test('Slack readSnapshot conservatively fetches replies when latest_reply is absent but reply_count > 0', async () => {
  const requests = [];
  const ambiguousParent = {ts: '1699000000.000000', thread_ts: '1699000000.000000', reply_count: 2}; // no latest_reply field at all
  const slack = createSlackConnector({
    workspaceId: 'T1', channelId: 'C1', senderIds: ['B1'], credentials,
    transport: async request => {
      requests.push(request);
      if (request.url.includes('conversations.history')) return response({ok: true, messages: [ambiguousParent]});
      return response({ok: true, messages: [ambiguousParent]});
    },
  });
  await slack.readSnapshot({replyWatermark: REPLY_WATERMARK});
  assert.equal(requests.some(request => request.url.includes('conversations.replies')), true);
});

test('Slack readSnapshot with no replyWatermark (first sync) fetches replies for every thread parent regardless of age', async () => {
  const requests = [];
  const veryOldParent = {ts: '1000000000.000000', thread_ts: '1000000000.000000', latest_reply: '1000000100.000000'};
  const slack = createSlackConnector({
    workspaceId: 'T1', channelId: 'C1', senderIds: ['B1'], credentials,
    transport: async request => {
      requests.push(request);
      if (request.url.includes('conversations.history')) return response({ok: true, messages: [veryOldParent]});
      return response({ok: true, messages: [veryOldParent]});
    },
  });
  await slack.readSnapshot(); // no oldest, no replyWatermark
  assert.equal(requests.some(request => request.url.includes('conversations.replies')), true);
});
