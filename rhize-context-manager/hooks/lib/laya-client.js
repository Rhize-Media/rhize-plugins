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
//   - native HTTP never follows redirects; injected fetch uses redirect:'error';
//     a redirect is 'redirect_refused';
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
const http = require('http');
const { Readable } = require('stream');
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

// Retain the fail-closed proxy policy: explicit proxy mode requires an exact
// loopback no-proxy exemption. Node's EnvHttpProxyAgent reads no_proxy first
// (including an empty value), so both defined spellings must exempt the host.
// CIDR and suffix forms are deliberately not trusted.
function envProxyHazard(env = process.env, endpoint = 'http://127.0.0.1:0') {
  const on = /^(1|true)$/i.test(String(env.NODE_USE_ENV_PROXY || '')) || /--use-env-proxy/.test(String(env.NODE_OPTIONS || ''));
  if (!on) return false;
  // Bare `::1` is NOT an exemption: undici parses it as host ':' port 1 and still proxies [::1] (verified,
  // Node 22.22 / undici 6.23). Only the bracketed form and '*' keep an IPv6 loopback request direct.
  const exempt = /^http:\/\/\[::1\]:/.test(String(endpoint)) ? ['*', '[::1]'] : ['*', '127.0.0.1'];
  const lists = ['no_proxy', 'NO_PROXY'].filter((name) => env[name] !== undefined).map((name) => String(env[name]));
  if (lists.length === 0) return true;
  return !lists.every((list) => list.split(',').map((s) => s.trim().toLowerCase()).some((entry) => exempt.includes(entry)));
}

function result(status, started, now, choice = null, probabilities = null) {
  let latencyMs = null;
  if (started !== null) latencyMs = Math.max(0, Math.round((now() - started) * 10) / 10);
  return { status, choice, probabilities, latencyMs };
}

// A deferred, passed probe travels with the result (deferProbeCache: true only).
function withCache(value, pending) {
  if (pending) value.probeCache = pending;
  return value;
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

function writeProbeCache(cachePath, endpoint, model, wallNow, atOverride) {
  try {
    const at = typeof atOverride === 'number' ? atOverride : wallNow();
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

// Direct HTTP avoids cold global-fetch initialization inside the hook's short deadline.
function requestLoopback(url, init) {
  return new Promise((resolve, reject) => {
    const request = http.request(url, {
      method: init.method, headers: init.headers, signal: init.signal, agent: false,
    }, (response) => resolve({
      status: response.statusCode,
      headers: { get: (name) => response.headers[name.toLowerCase()] ?? null },
      body: Readable.toWeb(response),
    }));
    request.once('error', reject);
    request.end(init.body);
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

// Writes a probe-cache entry that callChoice({deferProbeCache: true}) returned as
// `probeCache`, so a hook can do this synchronous I/O after its output is flushed.
function commitProbeCache(pending) {
  if (!pending || typeof pending.cachePath !== 'string' || typeof pending.at !== 'number') return;
  writeProbeCache(pending.cachePath, pending.endpoint, pending.model, () => pending.at, pending.at);
}

async function callChoice(options) {
  let started = null;
  let pendingCache = null;
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
    const doFetch = fetchImpl || requestLoopback;
    if (typeof doFetch !== 'function') return result('unavailable', null, clock);
    if (!fetchImpl && envProxyHazard(process.env, endpoint)) return result('unavailable', null, clock);

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
        if (cachePath) {
          if (options.deferProbeCache === true) pendingCache = { cachePath, endpoint, model, at: wallNow() };
          else writeProbeCache(cachePath, endpoint, model, wallNow);
        }
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
      if (remaining() <= 0) throw new DeadlineError('deadline');
      return withCache(result('ok', started, clock, decoded.choice, decoded.probabilities), pendingCache);
    } catch (err) {
      if (timedOut || err instanceof DeadlineError) return withCache(result('timeout', started, clock), pendingCache);
      if (err instanceof ProbeFailure) return withCache(result(err.layaStatus, started, clock), pendingCache);
      if (isRedirectError(err)) return withCache(result('redirect_refused', started, clock), pendingCache);
      return withCache(result('unavailable', started, clock), pendingCache);
    }
  } catch (_err) {
    return result('unavailable', started, clock);
  } finally {
    if (timer) clearTimeout(timer);
  }
}

module.exports = {
  callChoice, commitProbeCache, isLoopbackEndpoint, envProxyHazard, MAX_RESPONSE_BYTES, PROBE_TTL_MS,
};
