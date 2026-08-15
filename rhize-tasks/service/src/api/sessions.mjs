import {createHash, randomBytes, timingSafeEqual} from 'node:crypto';
import {ApiError} from './auth.mjs';

const digest = value => createHash('sha256').update(typeof value === 'string' ? value : '').digest();
const equalDigest = (value, encoded) => /^[0-9a-f]{64}$/.test(encoded ?? '') && timingSafeEqual(digest(value), Buffer.from(encoded, 'hex'));

export function createSessionAuthority({preferences, audit, now = () => new Date(), port = 43179, nonceTtlMs = 60_000, sessionTtlMs = 15 * 60_000}) {
  const sessions = new Map();
  return {
    issue() {
      const nonce = randomBytes(24).toString('base64url'); const expiresAt = new Date(now().getTime() + nonceTtlMs).toISOString();
      preferences.set('dashboard_bootstrap', {digest: digest(nonce).toString('hex'), expiresAt}); audit.append('dashboard_bootstrap_issued', 'service', 'local', {expiresAt});
      return {nonce, expiresAt};
    },
    exchange(nonce) {
      const bootstrap = preferences.get('dashboard_bootstrap'); preferences.delete('dashboard_bootstrap');
      if (!bootstrap || typeof bootstrap.digest !== 'string' || typeof bootstrap.expiresAt !== 'string' || Date.parse(bootstrap.expiresAt) < now().getTime() || !equalDigest(nonce, bootstrap.digest)) throw new ApiError('invalid_session_nonce', 401);
      const session = randomBytes(32).toString('base64url'); const expiresAt = now().getTime() + sessionTtlMs; sessions.set(digest(session).toString('hex'), expiresAt); audit.append('dashboard_session_started', 'service', 'local', {expiresAt: new Date(expiresAt).toISOString()});
      return `rhize_tasks_session=${session}; HttpOnly; SameSite=Strict; Path=/; Max-Age=${Math.floor(sessionTtlMs / 1000)}`;
    },
    authenticate(request) {
      const cookie = request.headers.cookie ?? ''; const match = /(?:^|;\s*)rhize_tasks_session=([A-Za-z0-9_-]+)(?:;|$)/.exec(cookie); if (!match) return false;
      const key = digest(match[1]).toString('hex'); const expiresAt = sessions.get(key); if (!expiresAt || expiresAt < now().getTime()) { sessions.delete(key); return false; }
      if (!['GET', 'HEAD'].includes(request.method ?? 'GET') && request.headers.origin !== `http://127.0.0.1:${port}`) return false;
      return true;
    },
  };
}
