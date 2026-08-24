// Coverage for two previously-deferred API-layer fixes:
//   1. Reminders helper config resolution from the installer's installation.json
//      (helperAppPath / helperSocketPath), with a runtime-relative dev/test fallback, and a
//      best-effort doctor field for whichever transport/paths resolved.
//   2. Slack sync-watermark persistence (slack_sync_watermark): context.mjs passes the raw
//      stored watermark through as `replyWatermark` (no client-side grace/floor — that's now
//      slack.mjs's job, see the design note near the replyWatermark tests below) and applies a
//      truncation guard so the watermark never advances past a sync's cutoff.
//
// Most of these tests exercise context.mjs against the CONTRACT the connectors/installer agents
// implement, not their real implementations: fake connectors and a fake installation.json
// reader stand in for reminders.mjs/slack.mjs/the installer. The exception is the one
// integration test in section 4, which uses the real createSlackConnector to prove that
// contract assumption actually holds against the shipped connector.
//
// Safety: every server binds to an ephemeral port (0), no launchctl/security command is ever
// invoked (systemProbe is always faked here), and no test makes a real network call — including
// the section-4 integration test, whose transport is still a fake.

import assert from 'node:assert/strict';
import {mkdtemp, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import test from 'node:test';

import {createServiceContext, resolveRemindersHelperConfig} from '../../service/src/api/context.mjs';
import {createSlackConnector} from '../../service/src/connectors/slack.mjs';

const token = 'reminders-config-slack-watermark-token-32';
const instant = '2026-08-17T09:00:00.000Z';

function emptyConnectors(overrides = {}) {
  const empty = {async readSnapshot() { return []; }, async health() { return {ok: true}; }};
  return {jira: empty, calendar: empty, reminders: empty, slack: empty, ...overrides};
}

const fakeKeychain = () => ({async get(service, account) { return service === 'media.rhize.tasks.api' && account === 'bearer' ? token : 'credential'; }, async set() {}, async delete() {}});

async function fixture(t, options = {}) {
  const directory = await mkdtemp(path.join(tmpdir(), 'rhize-task-reminders-slack-'));
  const context = await createServiceContext({
    databasePath: path.join(directory, 'state.sqlite'),
    keychain: options.keychain ?? fakeKeychain(),
    connectors: options.connectors ?? emptyConnectors(),
    systemProbe: options.systemProbe,
    now: options.now ?? (() => new Date(instant)),
  });
  t.after(() => { context.close(); return rm(directory, {recursive: true, force: true}); });
  return {context};
}

// --- 1a: resolveRemindersHelperConfig — installation.json present -------------------------

test('resolveRemindersHelperConfig prefers helperAppPath/helperSocketPath from a fake installation.json', async () => {
  const manifest = {version: '1.0.0', helperAppPath: '/Applications/Rhize Tasks/RhizeRemindersHelper.app', helperSocketPath: '/tmp/rhize-tasks/reminders.sock'};
  const config = await resolveRemindersHelperConfig({home: '/Users/fake', readManifest: async home => { assert.equal(home, '/Users/fake'); return manifest; }});
  assert.equal(config.helperPath, '/Applications/Rhize Tasks/RhizeRemindersHelper.app/Contents/MacOS/RhizeRemindersHelper');
  assert.equal(config.socketPath, '/tmp/rhize-tasks/reminders.sock');
});

test('resolveRemindersHelperConfig falls back to the runtime-relative path when installation.json is missing', async () => {
  const config = await resolveRemindersHelperConfig({home: '/Users/fake', readManifest: async () => null});
  assert.ok(config.helperPath.endsWith('native/RhizeRemindersHelper.app/Contents/MacOS/RhizeRemindersHelper'));
  assert.equal(config.socketPath, null);
});

test('resolveRemindersHelperConfig falls back when installation.json is malformed (non-string helperAppPath)', async () => {
  const config = await resolveRemindersHelperConfig({home: '/Users/fake', readManifest: async () => ({helperAppPath: 42, helperSocketPath: 7})});
  assert.ok(config.helperPath.endsWith('native/RhizeRemindersHelper.app/Contents/MacOS/RhizeRemindersHelper'));
  assert.equal(config.socketPath, null);
});

test('resolveRemindersHelperConfig falls back when the manifest reader throws', async () => {
  const config = await resolveRemindersHelperConfig({home: '/Users/fake', readManifest: async () => { throw new Error('ENOENT'); }});
  assert.ok(config.helperPath.endsWith('native/RhizeRemindersHelper.app/Contents/MacOS/RhizeRemindersHelper'));
  assert.equal(config.socketPath, null);
});

// --- 1b: doctor reports the resolved reminders-helper transport/paths, best-effort ---------

test('doctor reports remindersHelper transport/paths via the injectable systemProbe', async t => {
  const {context} = await fixture(t, {systemProbe: {
    async agentLoaded() { return null; }, async plistNodePathExists() { return null; }, async installedRuntimeVersion() { return null; },
    async remindersHelperConfig() { return {helperPath: '/opt/rhize/RhizeRemindersHelper', socketPath: '/tmp/reminders.sock'}; },
  }});
  const doctor = await context.doctor();
  assert.deepEqual(doctor.remindersHelper, {transport: 'socket', helperPath: '/opt/rhize/RhizeRemindersHelper', socketPath: '/tmp/reminders.sock'});
});

test('doctor reports transport "spawn" when no socket path resolved', async t => {
  const {context} = await fixture(t, {systemProbe: {
    async agentLoaded() { return null; }, async plistNodePathExists() { return null; }, async installedRuntimeVersion() { return null; },
    async remindersHelperConfig() { return {helperPath: '/opt/rhize/RhizeRemindersHelper', socketPath: null}; },
  }});
  const doctor = await context.doctor();
  assert.deepEqual(doctor.remindersHelper, {transport: 'spawn', helperPath: '/opt/rhize/RhizeRemindersHelper', socketPath: null});
});

test('doctor remindersHelper degrades to null when the probe throws (best-effort)', async t => {
  const {context} = await fixture(t, {systemProbe: {
    async agentLoaded() { return null; }, async plistNodePathExists() { return null; }, async installedRuntimeVersion() { return null; },
    async remindersHelperConfig() { throw new Error('nope'); },
  }});
  const doctor = await context.doctor();
  assert.equal(doctor.remindersHelper, null);
});

test('doctor remindersHelper degrades to null when the injected systemProbe does not implement it at all', async t => {
  // Regression guard: an older/partial systemProbe fixture (like the ones other test files
  // already use) must not make doctor() throw just because it lacks this new method.
  const {context} = await fixture(t, {systemProbe: {
    async agentLoaded() { return true; }, async plistNodePathExists() { return false; }, async installedRuntimeVersion() { return '9.9.9'; },
  }});
  const doctor = await context.doctor();
  assert.equal(doctor.remindersHelper, null);
  assert.equal(doctor.agentLoaded, true);
});

// --- 2: slack_sync_watermark persistence -----------------------------------------------------

function fakeSlack({items = [], syncMeta, captureOptions} = {}) {
  const values = [...items];
  if (syncMeta) values.syncMeta = syncMeta;
  return {
    async health() { return {ok: true}; },
    async readSnapshot(options) { captureOptions?.(options); return values; },
  };
}

test('slack watermark advances to syncMeta.latestTs after a complete sync', async t => {
  const {context} = await fixture(t, {connectors: emptyConnectors({slack: fakeSlack({items: [], syncMeta: {latestTs: 1_700_000_500, truncated: false}})})});
  await context.sync.readAll();
  assert.equal(context.repositories.preferences.get('slack_sync_watermark'), 1_700_000_500);
});

test('slack watermark holds (does not advance) after a truncated sync', async t => {
  const {context} = await fixture(t, {connectors: emptyConnectors({slack: fakeSlack({items: [], syncMeta: {latestTs: 1_700_000_500, truncated: true}})})});
  await context.sync.readAll();
  assert.equal(context.repositories.preferences.get('slack_sync_watermark'), null);
});

test('a truncated sync never regresses an existing watermark on a later run', async t => {
  const {context} = await fixture(t, {connectors: emptyConnectors({slack: fakeSlack({syncMeta: {latestTs: 1_700_000_000, truncated: false}})})});
  await context.sync.readAll();
  assert.equal(context.repositories.preferences.get('slack_sync_watermark'), 1_700_000_000);
  // Second sync comes back truncated with a smaller latestTs than the persisted watermark
  // (e.g. a partial re-scan) — the watermark must not move at all, forward or backward.
  const truncated = fakeSlack({syncMeta: {latestTs: 1_690_000_000, truncated: true}});
  Object.assign(context.connectorRegistry, {async get() { return {...emptyConnectors(), slack: truncated}; }});
  await context.sync.readAll();
  assert.equal(context.repositories.preferences.get('slack_sync_watermark'), 1_700_000_000);
});

// Design note (redesigned after a Codex adversarial finding): context.mjs used to compute
// `oldest = max(watermark - 24h, now - 7d)` itself and pass that as a bound on Slack's parent
// scan. That was broken by construction — a thread whose PARENT predates any client-computed
// bound is invisible to conversations.history entirely, so no amount of grace applied to
// `oldest` ever rescans it for new replies once the watermark has advanced past it, permanently
// dropping them. The fix moves the windowing into slack.mjs: context.mjs now hands over the raw
// stored watermark, unmodified, as `replyWatermark`; slack.mjs always fully rescans parents and
// alone decides (with its own ~24h grace against replyWatermark) which threads' replies to
// paginate. context.mjs's only remaining job is passing the raw value through and applying the
// truncation guard below.

test('slack readSnapshot receives replyWatermark: null on the first sync (no watermark yet)', async t => {
  let captured;
  const {context} = await fixture(t, {connectors: emptyConnectors({slack: fakeSlack({captureOptions: options => { captured = options; }})})});
  await context.sync.readAll();
  assert.deepEqual(captured, {replyWatermark: null});
});

test('slack readSnapshot receives the raw stored watermark as replyWatermark, unmodified', async t => {
  const watermarkSeconds = Math.floor(Date.parse(instant) / 1000) - 30 * 24 * 60 * 60; // deliberately stale: no client-side floor/grace applies anymore
  let captured;
  const {context} = await fixture(t, {connectors: emptyConnectors({slack: fakeSlack({captureOptions: options => { captured = options; }})})});
  context.repositories.preferences.set('slack_sync_watermark', watermarkSeconds);
  await context.sync.readAll();
  assert.deepEqual(captured, {replyWatermark: watermarkSeconds});
});

// --- 3: downstream idempotency across repeated parent rescans -----------------------------
//
// Now that slack.mjs always fully rescans parents every sync (the whole point of the redesign
// above), the SAME delegation message routinely comes back from readSnapshot() run after run —
// not just on retries. sync.readAll() must not turn repeat sightings of one message into
// duplicate task records. Confirmed by reading the source (not just asserting the behavior):
//
//   - delegationId is a UUID embedded in the message's own marker text (delegation-parser.mjs),
//     stable across re-parses of the same message — it is not derived from the message ts or
//     any other per-request value, so re-reading the same message always yields the same id.
//   - context.mjs turns that into task id `delegation:${delegationId}` (delegationTask()).
//   - taskRepository.upsert() (storage/database.mjs) is a genuine SQLite
//     `insert ... on conflict(id) do update`, keyed on that id — so re-upserting the same
//     delegationId replaces the existing row rather than inserting a second one.
//
// This dedup already has explicit coverage elsewhere (lifecycle-fix-round-1.test.mjs's
// "delegations retain Jira state..." calls sync.readAll() twice with identical slack items and
// asserts a stable task count) but that test predates this redesign and doesn't name the
// concern it now also protects against. Adding a redesign-scoped test here so the connection is
// explicit for whoever next touches the watermark logic.

test('re-reading the same delegation message across repeated parent rescans does not duplicate its task', async t => {
  const id = '550e8400-e29b-41d4-a716-446655440000';
  const item = {schemaVersion: 1, workspaceId: 'W', channelId: 'C', senderId: 'B', delegationId: id, ingestionKey: `W:C:${id}`, title: 'Delegation task', dueDate: '2026-08-20', priority: 'normal', jira: {kind: 'needs_jira', value: null}, state: 'needs_jira', planningLane: 'provisional', approval: 'required', schedulable: false};
  // Every sync returns the identical item — exactly what "parents are always fully rescanned"
  // means downstream, regardless of what replyWatermark was passed in.
  const {context} = await fixture(t, {connectors: emptyConnectors({slack: fakeSlack({items: [item], syncMeta: {latestTs: 1_700_000_000, truncated: false}})})});
  await context.sync.readAll();
  await context.sync.readAll();
  await context.sync.readAll();
  const tasks = context.repositories.tasks.list();
  assert.equal(tasks.filter(task => task.id === `delegation:${id}`).length, 1);
  assert.equal(tasks.length, 1);
});

// --- 4: integration test against the REAL createSlackConnector ----------------------------
//
// Everything above tests context.mjs's own logic against a fake connector matching the agreed
// contract. This test instead drives the actual shipped slack.mjs to confirm that contract
// assumption is real, not just agreed-upon: that replyWatermark does NOT bound
// conversations.history (parents always get the full historyLookbackMs window), and that a
// thread whose PARENT predates replyWatermark still gets its replies paginated when Slack's own
// `latest_reply` shows activity inside the grace window — the exact scenario the Codex finding
// said the old oldest-only design silently dropped.

const ok = body => ({status: 200, body});

test('the real slack connector: replyWatermark does not bound conversations.history, and a stale parent with a fresh reply is still fetched', async () => {
  const nowMs = Date.parse(instant);
  const historyLookbackMs = 7 * 24 * 60 * 60 * 1000;
  const replyWatermarkSeconds = nowMs / 1000 - 2 * 24 * 60 * 60; // watermark from 2 days ago
  const staleParentTs = (nowMs / 1000 - 5 * 24 * 60 * 60).toFixed(6); // parent from 5 days ago — older than the watermark, but inside the 7-day lookback
  const freshReplyTs = (nowMs / 1000 - 60 * 60).toFixed(6); // a reply posted an hour ago — inside the watermark's 24h grace

  const requests = [];
  const credentials = {async get() { return 'bot-token'; }};
  const transport = async request => {
    requests.push(request);
    const url = new URL(request.url);
    if (url.pathname.endsWith('conversations.history')) return ok({ok: true, messages: [{ts: staleParentTs, thread_ts: staleParentTs, latest_reply: freshReplyTs}]});
    if (url.pathname.endsWith('conversations.replies')) return ok({ok: true, messages: [{ts: staleParentTs}, {ts: freshReplyTs, bot_id: 'B1', text: 'not a valid delegation, fetch-happened is what matters here'}]});
    return ok({ok: true});
  };
  const slack = createSlackConnector({workspaceId: 'W', channelId: 'C', senderIds: ['B1'], credentials, transport, now: () => new Date(instant), historyLookbackMs});

  await slack.readSnapshot({replyWatermark: replyWatermarkSeconds});

  const historyRequest = requests.find(request => request.url.includes('conversations.history'));
  assert.ok(historyRequest, 'conversations.history must be called');
  const oldestParam = new URL(historyRequest.url).searchParams.get('oldest');
  const expectedFullLookbackOldest = ((nowMs - historyLookbackMs) / 1000).toFixed(6);
  assert.equal(oldestParam, expectedFullLookbackOldest, 'conversations.history must use the full lookback window, not anything derived from replyWatermark');
  assert.notEqual(Number(oldestParam), replyWatermarkSeconds, 'sanity check: the two bounds really are different values in this scenario');

  const repliesRequest = requests.find(request => request.url.includes('conversations.replies'));
  assert.ok(repliesRequest, 'conversations.replies must have been fetched for the stale parent because its latest_reply falls inside the grace window');
  assert.equal(new URL(repliesRequest.url).searchParams.get('ts'), staleParentTs);
});
