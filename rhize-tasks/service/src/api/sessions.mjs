import {createHash, randomBytes, timingSafeEqual} from 'node:crypto';
import {ApiError} from './auth.mjs';

const digest = value => createHash('sha256').update(typeof value === 'string' ? value : '').digest();
const equalDigest = (value, encoded) => /^[0-9a-f]{64}$/.test(encoded ?? '') && timingSafeEqual(digest(value), Buffer.from(encoded, 'hex'));
// Every cookie-authenticated request must also carry this header. A plain cross-site
// navigation (<img>, <a>, <form>) can never set it, so it closes the gap the GET/HEAD Origin
// exemption below leaves open: 127.0.0.1 ports other than this one are still "same-site", so a
// SameSite=Strict cookie is attached, and a simple GET often carries no Origin header at all
// for the Origin check to compare against. This is not limited to the discovery endpoints —
// GET /v1/doctor also fires real side effects (connector health checks: outbound token
// refresh, spawning the Reminders helper), and any other GET could gain side effects later, so
// the header is required uniformly rather than allowlisting specific paths. dashboard/app.js
// already sends it on every request, so this costs the real dashboard nothing.
const DASHBOARD_HEADER = 'x-rhize-tasks-dashboard';
const MAX_SESSIONS = 50;

function sweepExpiredSessions(sessions, nowMs) {
  for (const [key, expiresAt] of sessions) if (expiresAt < nowMs) sessions.delete(key);
}

export function createSessionAuthority({preferences, audit, now = () => new Date(), port = 43179, nonceTtlMs = 60_000, sessionTtlMs = 15 * 60_000}) {
  const sessions = new Map();
  return {
    issue() {
      const nonce = randomBytes(24).toString('base64url'); const expiresAt = new Date(now().getTime() + nonceTtlMs).toISOString();
      preferences.set('dashboard_bootstrap', {digest: digest(nonce).toString('hex'), expiresAt}); audit.append('dashboard_bootstrap_issued', 'service', 'local', {expiresAt});
      return {nonce, expiresAt};
    },
    exchange(nonce) {
      // Only a successful digest match consumes the bootstrap secret — burning it unconditionally
      // and first let any page on the loopback host DoS every future dashboard session by replaying
      // `/session?nonce=x` until the 60s window lapses, with no valid nonce required.
      const bootstrap = preferences.get('dashboard_bootstrap');
      if (!bootstrap || typeof bootstrap.digest !== 'string' || typeof bootstrap.expiresAt !== 'string' || Date.parse(bootstrap.expiresAt) < now().getTime() || !equalDigest(nonce, bootstrap.digest)) throw new ApiError('invalid_session_nonce', 401);
      preferences.delete('dashboard_bootstrap');
      sweepExpiredSessions(sessions, now().getTime());
      if (sessions.size >= MAX_SESSIONS) sessions.delete(sessions.keys().next().value);
      const session = randomBytes(32).toString('base64url'); const expiresAt = now().getTime() + sessionTtlMs; sessions.set(digest(session).toString('hex'), expiresAt); audit.append('dashboard_session_started', 'service', 'local', {expiresAt: new Date(expiresAt).toISOString()});
      return `rhize_tasks_session=${session}; HttpOnly; SameSite=Strict; Path=/; Max-Age=${Math.floor(sessionTtlMs / 1000)}`;
    },
    authenticate(request) {
      const cookie = request.headers.cookie ?? ''; const match = /(?:^|;\s*)rhize_tasks_session=([A-Za-z0-9_-]+)(?:;|$)/.exec(cookie); if (!match) return false;
      const key = digest(match[1]).toString('hex'); const expiresAt = sessions.get(key); if (!expiresAt || expiresAt < now().getTime()) { sessions.delete(key); return false; }
      const origin = request.headers.origin;
      if (typeof origin === 'string' && origin !== `http://127.0.0.1:${port}`) return false;
      if (!['GET', 'HEAD'].includes(request.method ?? 'GET') && typeof origin !== 'string') return false;
      return request.headers[DASHBOARD_HEADER] === '1';
    },
  };
}
