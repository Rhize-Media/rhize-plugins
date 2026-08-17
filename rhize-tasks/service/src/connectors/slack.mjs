import {parseDelegation} from './delegation-parser.mjs';
import {connectorError, normalizeError, unsupported} from './http.mjs';

const DEFAULT_HISTORY_LOOKBACK_MS = 7 * 24 * 60 * 60 * 1000;
const DEFAULT_MAX_PAGES_PER_SYNC = 200;

function unescapeSlackText(text) {
  return String(text ?? '')
    .replace(/<(https?:\/\/[^<>|]+)(?:\|[^<>]*)?>/g, '$1')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&');
}

export function createSlackConnector({workspaceId, channelId, senderIds, credentials, transport, now = () => new Date(), historyLookbackMs = DEFAULT_HISTORY_LOOKBACK_MS, maxPagesPerSync = DEFAULT_MAX_PAGES_PER_SYNC} = {}) {
  if (!workspaceId || !channelId || !Array.isArray(senderIds) || !credentials?.get || typeof transport !== 'function') throw new TypeError('invalid Slack connector configuration');
  async function request(method, params = {}) { try { const token = await credentials.get('media.rhize.tasks.slack', 'bot-token'); const response = await transport({url: `https://slack.com/api/${method}?${new URLSearchParams(params)}`, method: 'GET', headers: {authorization: `Bearer ${token}`}}); const body = response?.body; if (response?.status < 200 || response?.status >= 300 || !body || body.ok !== true) throw connectorError(body?.error === 'invalid_auth' ? 'authorization' : 'slack_api', {retryable: response?.status >= 500, status: response?.status}); return response; } catch (error) { throw normalizeError(error); } }
  async function pages(method, params, budget) {
    const all = []; const cursors = new Set(); let cursor = '';
    for (let count = 0; count < 100; count += 1) {
      if (budget && budget.remaining <= 0) return all;
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
    async readSnapshot() {
      const budget = {remaining: maxPagesPerSync};
      const seen = new Set(); const values = []; let skipped = 0;
      const oldest = Number.isFinite(historyLookbackMs) && historyLookbackMs > 0 ? ((now().getTime() - historyLookbackMs) / 1000).toFixed(6) : null;
      const parents = await pages('conversations.history', {channel: channelId, ...(oldest ? {oldest} : {})}, budget);
      for (const parent of parents) {
        if (!parent.thread_ts) continue;
        if (budget.remaining <= 0) break;
        const replies = await pages('conversations.replies', {channel: channelId, ts: parent.ts}, budget);
        for (const reply of replies.slice(1)) {
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
      return values;
    },
    applyOperation: unsupported,
    findByExternalId: unsupported,
  };
}
