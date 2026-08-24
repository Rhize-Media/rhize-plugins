import {connectorError, normalizeError, unsupported} from './http.mjs';

const datePattern = /^(\d{4})-(\d{2})-(\d{2})$/;
const dateTimePattern = /^(\d{4})-(\d{2})-(\d{2})T([01][0-9]|2[0-3]):[0-5][0-9](?::[0-5][0-9](?:\.\d{1,9})?)?(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])$/;

function validDate(value) {
  const match = datePattern.exec(value);
  if (!match) return false;
  const [, year, month, day] = match;
  const date = new Date(0);
  date.setUTCFullYear(Number(year), Number(month) - 1, Number(day));
  return date.getUTCFullYear() === Number(year) && date.getUTCMonth() === Number(month) - 1 && date.getUTCDate() === Number(day);
}

function validDateTime(value) {
  return dateTimePattern.test(value) && validDate(value.slice(0, 10)) && !Number.isNaN(Date.parse(value));
}

export function createGoogleCalendarConnector({readCalendarIds, focusCalendarId, credentials, transport, now = () => new Date(), redactOutsideTitles = true, discoverAll = false, discoveryOnly = false} = {}) {
  if (!Array.isArray(readCalendarIds) || !focusCalendarId || !credentials?.get || typeof transport !== 'function') throw new TypeError('invalid Google Calendar connector configuration');
  const readable = new Set(readCalendarIds);
  const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
  function bodyOf(response) { if (!object(response?.body)) throw connectorError('malformed_response'); return response.body; }
  function eventIdentity(event) { if (!object(event) || typeof event.id !== 'string' || !event.id || typeof event.etag !== 'string' || !event.etag) throw connectorError('malformed_response'); return event; }
  function eventResult(response) { return eventIdentity(bodyOf(response)); }
  function eventTime(event, key) { const value = event[key]; if (!object(value)) throw connectorError('malformed_response'); const dateTime = value.dateTime; const date = value.date; if (dateTime !== undefined && date !== undefined) throw connectorError('malformed_response'); if (typeof dateTime === 'string' && validDateTime(dateTime)) return dateTime; if (typeof date === 'string' && validDate(date)) return date; throw connectorError('malformed_response'); }
  function snapshotEvent(event, calendarId) { const privateProperties = event.extendedProperties?.private; const owned = calendarId === focusCalendarId && typeof privateProperties?.rhizeOperationKey === 'string' && /^[0-9a-f]{64}$/.test(privateProperties.rhizeOperationKey) && typeof privateProperties.rhizeTaskId === 'string' && privateProperties.rhizeTaskId && typeof privateProperties.rhizeBlockSlot === 'string' && privateProperties.rhizeBlockSlot; return {id: event.id, calendarId, revision: event.etag, start: eventTime(event, 'start'), end: eventTime(event, 'end'), title: calendarId === focusCalendarId || !redactOutsideTitles ? event.summary ?? '' : '', description: calendarId === focusCalendarId || !redactOutsideTitles ? event.description ?? '' : '', ...(owned ? {owned: true, operationKey: privateProperties.rhizeOperationKey, taskId: privateProperties.rhizeTaskId, blockSlot: privateProperties.rhizeBlockSlot} : {})}; }
  async function normalized(action, {afterWrite = false} = {}) { try { return await action(); } catch (error) { throw normalizeError(error, {afterWrite}); } }
  const TOKEN_REFRESH_SKEW_MS = 60_000;
  let cachedToken = null;
  let refreshPromise = null;
  async function refreshAccessToken() {
    const [client_id, client_secret, refresh_token] = await Promise.all(['client-id', 'client-secret', 'refresh-token'].map(account => credentials.get('media.rhize.tasks.google', account)));
    const response = await transport({url: 'https://oauth2.googleapis.com/token', method: 'POST', headers: {'content-type': 'application/x-www-form-urlencoded'}, body: new URLSearchParams({client_id, client_secret, refresh_token, grant_type: 'refresh_token'}).toString()});
    if (!response || response.status < 200 || response.status >= 300 || !response.body || typeof response.body.access_token !== 'string') throw connectorError('authorization', {status: response?.status});
    const expiresIn = Number(response.body.expires_in);
    cachedToken = {accessToken: response.body.access_token, expiresAt: now().getTime() + (Number.isFinite(expiresIn) && expiresIn > 0 ? expiresIn * 1000 : 0)};
    return cachedToken.accessToken;
  }
  // Concurrent callers (readSnapshot fans out per calendar) must share one in-flight refresh
  // instead of each starting their own grant against Google's token endpoint.
  async function token() {
    if (cachedToken && cachedToken.expiresAt - now().getTime() > TOKEN_REFRESH_SKEW_MS) return cachedToken.accessToken;
    if (!refreshPromise) {
      refreshPromise = refreshAccessToken().catch(error => {
        cachedToken = null;
        if (error?.status === 400 && error?.body?.error === 'invalid_grant') throw connectorError('authorization', {status: error.status});
        throw normalizeError(error);
      }).finally(() => { refreshPromise = null; });
    }
    return refreshPromise;
  }
  async function request(path, options = {}) {
    const method = options.method ?? 'GET';
    const send = async access => {
      const response = await transport({url: `https://www.googleapis.com/calendar/v3${path}`, method, headers: {authorization: `Bearer ${access}`, ...(options.body ? {'content-type': 'application/json'} : {})}, body: options.body ? JSON.stringify(options.body) : undefined});
      if (!response || response.status < 200 || response.status >= 300) throw connectorError(response?.status === 401 || response?.status === 403 ? 'authorization' : 'http', {status: response?.status, retryable: response?.status >= 500 || response?.status === 429});
      return response;
    };
    try {
      const access = await token();
      try {
        return await send(access);
      } catch (error) {
        // A 401 mid-lifetime means Google revoked the token server-side before our local
        // expiry; the cache would otherwise keep replaying the known-bad token for the rest
        // of the sync. Only clear it if it is still the exact token we used (a concurrent
        // caller may have already refreshed it), and only auto-retry idempotent reads —
        // mutating calls propagate the error so reconciliation's own retry logic decides.
        if (error?.status === 401) {
          if (cachedToken?.accessToken === access) cachedToken = null;
          if (method === 'GET') return await send(await token());
        }
        throw error;
      }
    } catch (error) { throw normalizeError(error, {afterWrite: method !== 'GET'}); }
  }
  async function events(calendarId, extra = {}) { const all = []; const seen = new Set(); let pageToken; const keyQuery = Object.hasOwn(extra, 'privateExtendedProperty'); for (let count = 0; count < 100; count += 1) { const qs = new URLSearchParams({singleEvents: 'true', orderBy: 'startTime', ...(keyQuery ? {} : {timeMin: now().toISOString()}), maxResults: '250', ...extra}); if (pageToken) qs.set('pageToken', pageToken); const body = bodyOf(await request(`/calendars/${encodeURIComponent(calendarId)}/events?${qs}`)); if (!Array.isArray(body.items)) throw connectorError('malformed_response'); body.items.forEach(eventIdentity); all.push(...body.items); pageToken = body.nextPageToken; if (pageToken !== undefined && pageToken !== null && typeof pageToken !== 'string') throw connectorError('malformed_response'); if (!pageToken) return all; if (seen.has(pageToken)) throw connectorError('pagination_loop'); seen.add(pageToken); } throw connectorError('pagination_limit'); }
  const api = {
    async health() { return normalized(async () => { await request('/users/me/calendarList?maxResults=1'); return {ok: true}; }); },
    async discover() { return normalized(async () => { const all = []; const seen = new Set(); let pageToken = ''; for (let count = 0; count < 100; count += 1) { const body = bodyOf(await request(`/users/me/calendarList?${pageToken ? `pageToken=${encodeURIComponent(pageToken)}` : ''}`)); if (!Array.isArray(body.items) || body.items.some(item => !object(item) || typeof item.id !== 'string' || !item.id)) throw connectorError('malformed_response'); all.push(...body.items.map(item => ({id: item.id, summary: typeof item.summary === 'string' ? item.summary : '', primary: item.primary === true, accessRole: typeof item.accessRole === 'string' ? item.accessRole : ''}))); pageToken = body.nextPageToken ?? ''; if (typeof pageToken !== 'string') throw connectorError('malformed_response'); if (!pageToken) return discoverAll ? all : all.filter(item => readable.has(item.id) || item.id === focusCalendarId); if (seen.has(pageToken)) throw connectorError('pagination_loop'); seen.add(pageToken); } throw connectorError('pagination_limit'); }); },
    async readSnapshot() { return normalized(async () => { if (discoveryOnly) unsupported(); return (await Promise.all([...readable].map(async calendarId => (await events(calendarId)).map(event => snapshotEvent(event, calendarId))))).flat(); }); },
    async applyOperation(operation) { return normalized(async () => { if (discoveryOnly || !['calendar_upsert', 'calendar_delete'].includes(operation?.kind)) unsupported(); if (operation.kind === 'calendar_upsert') { if (operation.payload.calendarId !== focusCalendarId) throw connectorError('out_of_scope'); const stableKey = operation.payload.operationKey ?? operation.idempotencyKey; if (!operation.targetId) { const old = (await events(focusCalendarId, {privateExtendedProperty: `rhizeOperationKey=${stableKey}`}))[0]; if (old) return {externalId: old.id, revision: old.etag}; } else { const existing = eventResult(await request(`/calendars/${encodeURIComponent(focusCalendarId)}/events/${encodeURIComponent(operation.targetId)}`)); if (existing.extendedProperties?.private?.rhizeOperationKey !== stableKey) throw connectorError('out_of_scope'); } const privateProperties = {rhizeOperationKey: stableKey, ...(operation.payload.taskId ? {rhizeTaskId: operation.payload.taskId} : {}), ...(operation.payload.blockSlot ? {rhizeBlockSlot: operation.payload.blockSlot} : {})}; const body = {summary: operation.payload.title, description: operation.payload.description, start: {dateTime: operation.payload.start}, end: {dateTime: operation.payload.end}, extendedProperties: {private: privateProperties}}; try { const event = eventResult(await request(`/calendars/${encodeURIComponent(focusCalendarId)}/events${operation.targetId ? `/${encodeURIComponent(operation.targetId)}` : ''}`, {method: operation.targetId ? 'PUT' : 'POST', body})); return {externalId: event.id, revision: event.etag}; } catch (error) { if (error.ambiguous) { const old = (await events(focusCalendarId, {privateExtendedProperty: `rhizeOperationKey=${stableKey}`}))[0]; if (old) return {externalId: old.id, revision: old.etag}; } throw error; } } const existing = eventResult(await request(`/calendars/${encodeURIComponent(focusCalendarId)}/events/${encodeURIComponent(operation.targetId)}`)); const privateProperties = existing.extendedProperties?.private; if (typeof privateProperties?.rhizeOperationKey !== 'string' || typeof privateProperties.rhizeTaskId !== 'string' || typeof privateProperties.rhizeBlockSlot !== 'string') throw connectorError('out_of_scope'); await request(`/calendars/${encodeURIComponent(focusCalendarId)}/events/${encodeURIComponent(operation.targetId)}`, {method: 'DELETE'}); return {externalId: operation.targetId, revision: operation.idempotencyKey}; }, {afterWrite: true}); },
    async findByExternalId(externalId) { return normalized(async () => { if (discoveryOnly) unsupported(); const matches = await events(focusCalendarId, {privateExtendedProperty: `rhizeOperationKey=${externalId}`}); if (matches[0]) return {externalId: matches[0].id, revision: matches[0].etag}; try { const event = eventResult(await request(`/calendars/${encodeURIComponent(focusCalendarId)}/events/${encodeURIComponent(externalId)}`)); return {revision: event.etag}; } catch (error) { if (error.status === 404) return null; throw error; } }); },
  };
  return api;
}
