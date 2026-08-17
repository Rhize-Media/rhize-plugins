import {parseDelegation} from './delegation-parser.mjs';
import {connectorError, normalizeError, unsupported} from './http.mjs';

const DEFAULT_HISTORY_LOOKBACK_MS = 7 * 24 * 60 * 60 * 1000;
const DEFAULT_MAX_PAGES_PER_SYNC = 200;
const DEFAULT_REPLY_GRACE_MS = 24 * 60 * 60 * 1000;

function unescapeSlackText(text) {
  return String(text ?? '')
    .replace(/<(https?:\/\/[^<>|]+)(?:\|[^<>]*)?>/g, '$1')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&');
}

// Slack's `ts` is "<seconds>.<microseconds>" as a string — already the same
// epoch-seconds unit the `oldest` param takes, so no unit conversion (and no
// precision loss) is needed to turn one into the other.
function slackTsToEpochSeconds(ts) {
  const value = Number(ts);
  return Number.isFinite(value) ? value : null;
}

// Should conversations.replies be paginated for this parent? `replyWatermark`
// is null on a first sync (no prior state) -> always check. Otherwise: a
// parent newer than the watermark is new since last sync and must be
// checked; an older parent is only re-checked if it shows activity within
// the grace window (see the readSnapshot comment for why the grace window
// exists at all). Slack's `latest_reply` is the authoritative freshness
// signal for that; when Slack omits it despite reply_count > 0 (observed for
// some threads), there is no persisted per-thread state here to compare
// against, so a positive reply_count with no timestamp is conservatively
// treated as "unknown, must check" rather than silently skipped — a false
// positive costs one extra replies fetch, a false negative silently drops a
// delegation.
function shouldFetchReplies(parent, replyWatermarkSeconds, graceMs) {
  if (!parent.thread_ts) return false;
  if (replyWatermarkSeconds === null) return true;
  const parentTs = slackTsToEpochSeconds(parent.ts);
  if (parentTs !== null && parentTs >= replyWatermarkSeconds) return true;
  if (typeof parent.latest_reply === 'string') {
    const latestReplyTs = slackTsToEpochSeconds(parent.latest_reply);
    return latestReplyTs !== null && latestReplyTs >= replyWatermarkSeconds - graceMs / 1000;
  }
  return typeof parent.reply_count === 'number' && parent.reply_count > 0;
}

export function createSlackConnector({workspaceId, channelId, senderIds, credentials, transport, now = () => new Date(), historyLookbackMs = DEFAULT_HISTORY_LOOKBACK_MS, maxPagesPerSync = DEFAULT_MAX_PAGES_PER_SYNC, replyGraceMs = DEFAULT_REPLY_GRACE_MS} = {}) {
  if (!workspaceId || !channelId || !Array.isArray(senderIds) || !credentials?.get || typeof transport !== 'function') throw new TypeError('invalid Slack connector configuration');
  if (!Number.isFinite(replyGraceMs) || replyGraceMs < 0) throw new TypeError('invalid Slack connector configuration');
  async function request(method, params = {}) { try { const token = await credentials.get('media.rhize.tasks.slack', 'bot-token'); const response = await transport({url: `https://slack.com/api/${method}?${new URLSearchParams(params)}`, method: 'GET', headers: {authorization: `Bearer ${token}`}}); const body = response?.body; if (response?.status < 200 || response?.status >= 300 || !body || body.ok !== true) throw connectorError(body?.error === 'invalid_auth' ? 'authorization' : 'slack_api', {retryable: response?.status >= 500, status: response?.status}); return response; } catch (error) { throw normalizeError(error); } }
  // `budget.truncated` is the sync-wide signal that the maxPagesPerSync cap
  // cut this sync short (either the top-level channel-history pagination
  // below, or a thread's reply pagination in readSnapshot). It is shared
  // across every pages() call in one readSnapshot() run.
  async function pages(method, params, budget) {
    const all = []; const cursors = new Set(); let cursor = '';
    for (let count = 0; count < 100; count += 1) {
      if (budget && budget.remaining <= 0) { budget.truncated = true; return all; }
      if (budget) budget.remaining -= 1;
      const body = (await request(method, {...params, cursor, limit: '100'})).body;
      all.push(...(body.messages ?? []));
      cursor = body.response_metadata?.next_cursor ?? '';
      if (!cursor) return all;
      if (cursors.has(cursor)) throw connectorError('pagination_loop');
      cursors.add(cursor);
    }
    throw connectorError('pagination_limit');
  }
  return {
    async health() { const body = (await request('auth.test')).body; if (body.team_id !== workspaceId) throw connectorError('authorization'); return {ok: true}; },
    async discover() {
      const channelInfo = (await request('conversations.info', {channel: channelId})).body;
      if (!channelInfo?.channel || channelInfo.channel.id !== channelId) throw connectorError('malformed_response');
      for (const senderId of senderIds) { try { await request('users.info', {user: senderId}); } catch { /* bot/app sender IDs cannot be resolved via users.info; best-effort only */ } }
      return {workspaceId, channelId, senderIds: [...senderIds]};
    },
    async readSnapshot({oldest, replyWatermark} = {}) {
      if (oldest !== undefined && (!Number.isFinite(oldest) || oldest < 0)) throw new TypeError('invalid Slack readSnapshot argument');
      if (replyWatermark !== undefined && replyWatermark !== null && (!Number.isFinite(replyWatermark) || replyWatermark < 0)) throw new TypeError('invalid Slack readSnapshot argument');
      const budget = {remaining: maxPagesPerSync, truncated: false};
      const seen = new Set(); const values = []; let skipped = 0;
      // Bounding conversations.history: `oldest` (epoch seconds) is a
      // test-only override, kept for direct control in tests. Production
      // does NOT derive `oldest` from a watermark — conversations.history
      // always scans the full historyLookbackMs window (default 7d).
      // Fetching parents is cheap; see the replyWatermark comment below for
      // why bounding this call by watermark was the actual bug.
      const oldestSeconds = oldest ?? (Number.isFinite(historyLookbackMs) && historyLookbackMs > 0 ? (now().getTime() - historyLookbackMs) / 1000 : null);
      const oldestParam = oldestSeconds !== null ? oldestSeconds.toFixed(6) : null;
      const parents = await pages('conversations.history', {channel: channelId, ...(oldestParam ? {oldest: oldestParam} : {})}, budget);
      const replyWatermarkSeconds = replyWatermark ?? null;
      // latestTs tracks the newest ts actually observed this sync, across
      // BOTH parents and any replies we actually fetched (see below) — the
      // watermark must advance over reply activity too, or a caller passing
      // this straight back in as the next replyWatermark would keep
      // re-checking a thread it has already fully caught up on.
      let latestTs = null;
      const bumpLatestTs = ts => { const value = slackTsToEpochSeconds(ts); if (value !== null && (latestTs === null || value > latestTs)) latestTs = value; };
      for (const parent of parents) {
        bumpLatestTs(parent.ts);
        // replyWatermark decides whether conversations.replies is worth
        // paginating for THIS parent — it does not bound conversations.history
        // itself (see above). This is the fix for the old design's bug: with
        // `oldest` bounding conversations.history, a parent older than the
        // watermark (even with a 24h grace subtracted) was excluded from the
        // results entirely, so a *new* reply to that old thread was never
        // seen — the sync still reported clean/complete. Scanning parents
        // unconditionally and only gating the expensive replies fetch on
        // shouldFetchReplies() fixes that: old parents stay visible, and are
        // only skipped from a replies re-fetch when they show no recent
        // activity per Slack's own latest_reply/reply_count fields.
        if (!shouldFetchReplies(parent, replyWatermarkSeconds, replyGraceMs)) continue;
        if (budget.remaining <= 0) { budget.truncated = true; break; }
        const replies = await pages('conversations.replies', {channel: channelId, ts: parent.ts}, budget);
        for (const reply of replies.slice(1)) {
          bumpLatestTs(reply.ts);
          const senderId = reply.bot_id ?? reply.app_id ?? reply.user;
          try {
            const item = parseDelegation({workspaceId, channelId, senderId, text: unescapeSlackText(reply.text)}, {workspaceId, channelId, senderIds});
            if (!seen.has(item.ingestionKey)) { seen.add(item.ingestionKey); values.push(item); }
          } catch (error) {
            skipped += 1;
            process.stderr.write(`${JSON.stringify({event: 'slack_delegation_parse_skipped', channelId, ts: reply.ts ?? null, reason: error?.message ?? 'unknown'})}\n`);
          }
        }
      }
      if (skipped > 0) process.stderr.write(`${JSON.stringify({event: 'slack_delegation_parse_summary', channelId, skipped})}\n`);
      // CRITICAL correctness rule: the caller must never advance a persisted
      // watermark past messages it did not actually read. `truncated` exists
      // so the caller can detect that case — it is true iff the
      // maxPagesPerSync budget cut this sync short, meaning some in-window
      // messages (top-level history pagination, or a thread's reply
      // pagination that shouldFetchReplies() had already decided to fetch)
      // were never retrieved. A parent that shouldFetchReplies() decided to
      // SKIP (no recent activity signal) is not a truncation — it is an
      // intentional, watermark-driven skip, not missing data.
      //
      // Shape: `values` stays a plain array (existing `for (const item of
      // snapshot)` / `.length` consumers are unaffected); syncMeta is
      // attached as a non-enumerable own property, matching this codebase's
      // existing convention for hanging extra metadata off a return value
      // (see `Object.defineProperty(plan, '__tasks', ...)` in context.mjs).
      Object.defineProperty(values, 'syncMeta', {value: {latestTs, truncated: budget.truncated === true}, enumerable: false, configurable: true});
      return values;
    },
    applyOperation: unsupported,
    findByExternalId: unsupported,
  };
}
