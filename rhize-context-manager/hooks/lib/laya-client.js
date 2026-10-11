'use strict';
// laya-client.js: Node client for the local Laya server's /v1/systemone `choice`
// question (plan v3 §4.2). Python mirror: scripts/typed_decisions/laya_choice.py.
//
// callChoice() NEVER throws. It resolves to
//   {status, choice, probabilities, latencyMs}
// with status one of ok | timeout | unavailable | invalid | identity_failed |
// redirect_refused. choice/probabilities are non-null only for 'ok'.
//
// Safety properties (plan §3 P-A, §5 I3/I4):
//   - the endpoint must be a literal loopback http URL (http://127.0.0.1:<port>
//     or http://[::1]:<port>); 'localhost', other hosts, paths and https are
//     rejected with status 'unavailable' before any network I/O;
//   - both the identity probe and the POST use fetch redirect:'error'; a
//     redirect is 'redirect_refused';
//   - ONE monotonic deadline (deadlineAt, same clock as `now`) covers the probe
//     and the POST together. Every await is raced against it, so the call
//     resolves with 'timeout' at the deadline even if the transport ignores the
//     abort signal;
//   - prompt text (the request) is sent only after an identity probe passed:
//     GET <endpoint>/health must be HTTP 200 JSON whose `loaded` array includes
//     the model. A passed probe is cached for 60 s in a 0600 JSON file keyed by
//     endpoint+model (cache I/O errors are ignored);
//   - at most 64 KiB of any response is read; beyond that the stream is
//     cancelled and the call is 'invalid';
//   - the response is decoded with decodeChoiceResponse() (routing.model,
//     choice key, probabilities coverage and range).
const fs = require('fs');
const net = require('net');
const path = require('path');
const crypto = require('crypto');
const { performance } = require('perf_hooks');
const { decodeChoiceResponse } = require('./laya-instrument.js');
const { defaultRoot } = require('./typed-decisions.js');

const MAX_RESPONSE_BYTES = 64 * 1024;
const PROBE_TTL_MS = 60 * 1000;
const MAX_CACHE_BYTES = 16 * 1024;
const MAX_CACHE_ENTRIES = 8;
const LOOPBACK_ENDPOINT = /^http:\/\/(127\.0\.0\.1|\[::1\]):(\d{1,5})$/;

class DeadlineError extends Error {}
class OversizeError extends Error {}
class ProbeFailure extends Error {
  constructor(status) { super(status); this.layaStatus = status; }
}

function isLoopbackEndpoint(endpoint) {
  if (typeof endpoint !== 'string') return false;
  const m = LOOPBACK_ENDPOINT.exec(endpoint);
  if (!m) return false;
  const port = Number(m[2]);
  return port >= 1 && port <= 65535;
}

// Node's fetch ignores proxy variables unless the env-proxy mode is on. When it
// is on and loopback is not exempted, a request to 127.0.0.1 could be routed to
// the proxy, so refuse rather than risk sending task text off-host.
function envProxyHazard(env = process.env) {
  const on = /^(1|true)$/i.test(String(env.NODE_USE_ENV_PROXY || '')) || /--use-env-proxy/.test(String(env.NODE_OPTIONS || ''));
  if (!on) return false;
  const noProxy = String(env.NO_PROXY || env.no_proxy || '').split(',').map((s) => s.trim().toLowerCase());
  return !noProxy.some((entry) => entry === '*' || entry === '127.0.0.1' || entry === '::1' || entry === '[::1]'
    || entry === '127.0.0.0/8');
}

function result(status, started, now, choice = null, probabilities = null) {
  let latencyMs = null;
  if (started !== null) latencyMs = Math.max(0, Math.round((now() - started) * 10) / 10);
  return { status, choice, probabilities, latencyMs };
}

// ---------------------------------------------------------------- probe cache

function cacheKey(endpoint, model) {
  return `${endpoint}\n${model}`;
}

function readProbeCache(cachePath, endpoint, model, wallNow) {
  try {
    const stat = fs.lstatSync(cachePath);
    if (!stat.isFile() || stat.size > MAX_CACHE_BYTES) return false;
    const doc = JSON.parse(fs.readFileSync(cachePath, 'utf8'));
    const entry = doc && doc.entries && doc.entries[cacheKey(endpoint, model)];
    if (!entry || entry.endpoint !== endpoint || entry.model !== model || typeof entry.at !== 'number') return false;
    const age = wallNow() - entry.at;
    return age >= -5000 && age < PROBE_TTL_MS;
  } catch (_err) {
    return false;
  }
}

function writeProbeCache(cachePath, endpoint, model, wallNow) {
  try {
    const at = wallNow();
    let entries = {};
    try {
      const stat = fs.lstatSync(cachePath);
      if (stat.isFile() && stat.size <= MAX_CACHE_BYTES) {
        const doc = JSON.parse(fs.readFileSync(cachePath, 'utf8'));
        if (doc && doc.entries && typeof doc.entries === 'object' && !Array.isArray(doc.entries)) entries = doc.entries;
      }
    } catch (_err) { entries = {}; }
    const fresh = {};
    for (const [key, entry] of Object.entries(entries)) {
      if (entry && typeof entry.at === 'number' && at - entry.at >= 0 && at - entry.at < PROBE_TTL_MS
        && typeof entry.endpoint === 'string' && typeof entry.model === 'string') fresh[key] = entry;
    }
    fresh[cacheKey(endpoint, model)] = { endpoint, model, at };
    const kept = Object.entries(fresh).sort((a, b) => b[1].at - a[1].at).slice(0, MAX_CACHE_ENTRIES);
    const dir = path.dirname(cachePath);
    fs.mkdirSync(dir, { recursive: true, mode: 0o700 });
    const tmp = `${cachePath}.${process.pid}.${crypto.randomBytes(4).toString('hex')}.tmp`;
    fs.writeFileSync(tmp, JSON.stringify({ schemaVersion: 1, entries: Object.fromEntries(kept) }), { mode: 0o600, flag: 'wx' });
    try {
      fs.renameSync(tmp, cachePath);
    } catch (err) {
      try { fs.unlinkSync(tmp); } catch (_e) { /* ignore */ }
      throw err;
    }
  } catch (_err) {
    // cache I/O is best effort
  }
}

// ---------------------------------------------------------------- transport

// A bare TCP connect to the literal loopback port, used before the first real
// request so that "nothing is listening" costs ~1 ms instead of the ~70 ms it
// takes Node to initialise fetch (undici). It sends no bytes. Not used when a
// fetch implementation is injected (tests).
function tcpReachable(endpoint, signal) {
  const m = LOOPBACK_ENDPOINT.exec(endpoint);
  const host = m[1] === '[::1]' ? '::1' : m[1];
  return new Promise((resolve) => {
    let done = false;
    const socket = net.createConnection({ host, port: Number(m[2]) });
    const finish = (reachable) => {
      if (done) return;
      done = true;
      signal.removeEventListener('abort', onAbort);
      socket.destroy();
      resolve(reachable);
    };
    const onAbort = () => finish(false);
    signal.addEventListener('abort', onAbort, { once: true });
    socket.once('connect', () => finish(true));
    socket.once('error', () => finish(false));
  });
}

async function readCapped(res, race) {
  const length = res.headers && typeof res.headers.get === 'function' ? Number(res.headers.get('content-length')) : NaN;
  if (Number.isFinite(length) && length > MAX_RESPONSE_BYTES) {
    try { if (res.body && res.body.cancel) res.body.cancel().catch(() => {}); } catch (_e) { /* ignore */ }
    throw new OversizeError('oversize');
  }
  if (res.body && typeof res.body.getReader === 'function') {
    const reader = res.body.getReader();
    const chunks = [];
    let total = 0;
    try {
      for (;;) {
        const { done, value } = await race(reader.read());
        if (done) break;
        total += value.byteLength;
        if (total > MAX_RESPONSE_BYTES) throw new OversizeError('oversize');
        chunks.push(Buffer.from(value.buffer, value.byteOffset, value.byteLength));
      }
    } finally {
      try { reader.cancel().catch(() => {}); } catch (_e) { /* ignore */ }
    }
    return Buffer.concat(chunks);
  }
  const text = await race(res.text());
  const buf = Buffer.from(String(text), 'utf8');
  if (buf.length > MAX_RESPONSE_BYTES) throw new OversizeError('oversize');
  return buf;
}

function parseJson(buffer) {
  const text = new TextDecoder('utf-8', { fatal: true }).decode(buffer);
  return JSON.parse(text);
}

function isRedirectError(err) {
  const parts = [err && err.message, err && err.cause && err.cause.message].filter((s) => typeof s === 'string');
  return parts.some((s) => /redirect/i.test(s));
}

function isRedirectResponse(res) {
  return Boolean(res) && (res.redirected === true || res.type === 'opaqueredirect'
    || (typeof res.status === 'number' && res.status >= 300 && res.status < 400));
}

// ---------------------------------------------------------------- main entry

async function callChoice(options) {
  let started = null;
  const clock = (options && typeof options.now === 'function') ? options.now : () => performance.now();
  let timer = null;
  try {
    const {
      endpoint, model, request, keyMap, deadlineAt, healthCachePath, fetchImpl, wallNow: wallNowOpt,
    } = options || {};
    if (!isLoopbackEndpoint(endpoint)) return result('unavailable', null, clock);
    if (typeof model !== 'string' || model.length === 0 || !request || typeof request !== 'object'
      || !keyMap || typeof keyMap !== 'object' || typeof deadlineAt !== 'number' || !Number.isFinite(deadlineAt)) {
      return result('invalid', null, clock);
    }
    let body;
    try { body = JSON.stringify(request); } catch (_e) { body = undefined; }
    if (typeof body !== 'string') return result('invalid', null, clock);
    const doFetch = fetchImpl || globalThis.fetch;
    if (typeof doFetch !== 'function') return result('unavailable', null, clock);
    if (!fetchImpl && envProxyHazard()) return result('unavailable', null, clock);

    started = clock();
    const wallNow = typeof wallNowOpt === 'function' ? wallNowOpt : () => Date.now();
    const remaining = () => deadlineAt - clock();
    if (remaining() <= 0) return result('timeout', started, clock);

    const controller = new AbortController();
    let timedOut = false;
    let rejectDeadline;
    const deadlinePromise = new Promise((_resolve, reject) => { rejectDeadline = reject; });
    deadlinePromise.catch(() => {});
    timer = setTimeout(() => {
      timedOut = true;
      try { controller.abort(); } catch (_e) { /* ignore */ }
      rejectDeadline(new DeadlineError('deadline'));
    }, Math.max(0, remaining()));
    const race = (promise) => Promise.race([promise, deadlinePromise]);

    try {
      if (!fetchImpl && !(await race(tcpReachable(endpoint, controller.signal)))) throw new ProbeFailure('unavailable');

      // ---- identity probe (cached for PROBE_TTL_MS per endpoint+model)
      const cachePath = healthCachePath === undefined ? path.join(defaultRoot(), 'laya-health.json') : healthCachePath;
      const cached = cachePath ? readProbeCache(cachePath, endpoint, model, wallNow) : false;
      if (!cached) {
        const probe = await race(doFetch(`${endpoint}/health`, {
          method: 'GET', headers: { accept: 'application/json' }, redirect: 'error', signal: controller.signal,
        }));
        if (isRedirectResponse(probe)) throw new ProbeFailure('redirect_refused');
        if (probe.status !== 200) {
          try { if (probe.body && probe.body.cancel) probe.body.cancel().catch(() => {}); } catch (_e) { /* ignore */ }
          throw new ProbeFailure('identity_failed');
        }
        let health;
        try { health = parseJson(await readCapped(probe, race)); } catch (err) {
          if (err instanceof DeadlineError) throw err;
          throw new ProbeFailure('identity_failed'); // oversize, non-UTF-8 or non-JSON body (a deadline hit wins in the outer catch)
        }
        if (!health || typeof health !== 'object' || !Array.isArray(health.loaded) || !health.loaded.includes(model)) {
          throw new ProbeFailure('identity_failed');
        }
        if (cachePath) writeProbeCache(cachePath, endpoint, model, wallNow);
      }

      // ---- POST (only after the probe passed)
      if (remaining() <= 0) throw new DeadlineError('deadline');
      const response = await race(doFetch(`${endpoint}/v1/systemone`, {
        method: 'POST',
        headers: { 'content-type': 'application/json', accept: 'application/json' },
        body,
        redirect: 'error',
        signal: controller.signal,
      }));
      if (isRedirectResponse(response)) throw new ProbeFailure('redirect_refused');
      if (typeof response.status !== 'number' || response.status < 200 || response.status > 299) {
        try { if (response.body && response.body.cancel) response.body.cancel().catch(() => {}); } catch (_e) { /* ignore */ }
        throw new ProbeFailure('unavailable');
      }
      let decoded;
      try {
        decoded = decodeChoiceResponse(parseJson(await readCapped(response, race)), keyMap);
      } catch (err) {
        if (err instanceof DeadlineError) throw err;
        if (timedOut) throw new DeadlineError('deadline');
        throw new ProbeFailure('invalid');
      }
      return result('ok', started, clock, decoded.choice, decoded.probabilities);
    } catch (err) {
      if (timedOut || err instanceof DeadlineError) return result('timeout', started, clock);
      if (err instanceof ProbeFailure) return result(err.layaStatus, started, clock);
      if (isRedirectError(err)) return result('redirect_refused', started, clock);
      return result('unavailable', started, clock);
    }
  } catch (_err) {
    return result('unavailable', started, clock);
  } finally {
    if (timer) clearTimeout(timer);
  }
}

module.exports = {
  callChoice, isLoopbackEndpoint, envProxyHazard, MAX_RESPONSE_BYTES, PROBE_TTL_MS,
};
