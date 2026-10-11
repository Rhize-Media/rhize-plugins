#!/usr/bin/env node
// Unit tests for rhize-context-manager/hooks/lib/laya-client.js (plan v3 §4.2, A2).
// Standalone script: exits non-zero on any failure. Uses real loopback http servers
// (random ports) plus scripted fetch doubles; no external network.
'use strict';
const assert = require('assert');
const fs = require('fs');
const http = require('http');
const net = require('net');
const os = require('os');
const path = require('path');
const { performance } = require('perf_hooks');

const REPO = path.resolve(__dirname, '..', '..');
const LIB = path.join(REPO, 'rhize-context-manager', 'hooks', 'lib');
const client = require(path.join(LIB, 'laya-client.js'));
const instrument = require(path.join(LIB, 'laya-instrument.js'));

const MODEL = 'typed-decisions';
const SKILLS = ['skill:alpha/context-pack', 'skill:alpha/git-helper', 'skill:beta/tool-setup'];
const built = instrument.buildChoiceRequest('help me get git and context tooling set up',
  SKILLS.map((skillId) => ({ skillId, description: 'does a thing' })));

const results = [];
function okAnswer(choiceKey = 's0') {
  const keys = [...Object.keys(built.keyMap), 'none'];
  const probabilities = {};
  for (const key of keys) probabilities[key] = key === choiceKey ? 0.7 : 0.3 / (keys.length - 1);
  return { routing: { model: MODEL }, answers: { skill: { type: 'choice', choice: choiceKey, probabilities } } };
}

function tmpDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'laya-client-test-'));
}

// handlers: {health(req,res), post(req,res,body)}; counters in server.hits
function startServer(handlers = {}, host = '127.0.0.1') {
  const hits = { health: 0, post: 0, other: 0, bodies: [] };
  const sockets = new Set();
  const server = http.createServer((req, res) => {
    if (req.method === 'GET' && req.url === '/health') {
      hits.health += 1;
      if (handlers.health) return handlers.health(req, res);
      res.writeHead(200, { 'content-type': 'application/json' });
      return res.end(JSON.stringify({ status: 'ok', loaded: [MODEL] }));
    }
    if (req.method === 'POST' && req.url === '/v1/systemone') {
      let body = '';
      req.on('data', (chunk) => { body += chunk; });
      req.on('end', () => {
        hits.post += 1;
        hits.bodies.push(body);
        if (handlers.post) return handlers.post(req, res, body);
        res.writeHead(200, { 'content-type': 'application/json' });
        return res.end(JSON.stringify(okAnswer()));
      });
      return undefined;
    }
    hits.other += 1;
    res.writeHead(404);
    return res.end();
  });
  server.on('connection', (socket) => { sockets.add(socket); socket.on('close', () => sockets.delete(socket)); });
  return new Promise((resolve) => {
    server.once('error', () => resolve(null)); // e.g. no IPv6 loopback in this sandbox
    server.listen(0, host, () => {
      const port = server.address().port;
      const endpoint = host === '::1' ? `http://[::1]:${port}` : `http://127.0.0.1:${port}`;
      resolve({
        endpoint, port, hits,
        close: () => new Promise((done) => { for (const s of sockets) s.destroy(); server.close(() => done()); }),
      });
    });
  });
}

async function closedPort() {
  const s = await startServer();
  const { port } = s;
  await s.close();
  return `http://127.0.0.1:${port}`;
}

function call(overrides = {}) {
  const dir = overrides.__dir || tmpDir();
  const budget = overrides.__budget === undefined ? 1500 : overrides.__budget;
  const opts = {
    endpoint: 'http://127.0.0.1:1', model: MODEL, request: built.request, keyMap: built.keyMap,
    deadlineAt: performance.now() + budget, healthCachePath: path.join(dir, 'laya-health.json'),
    ...overrides,
  };
  delete opts.__dir;
  delete opts.__budget;
  return client.callChoice(opts);
}

async function check(name, fn) {
  try {
    await fn();
    results.push([name, true]);
    console.log(`PASS ${name}`);
  } catch (err) {
    results.push([name, false]);
    console.error(`FAIL ${name}`);
    console.error(err && err.stack ? err.stack : err);
  }
}

function scriptedFetch(script) {
  const calls = [];
  const impl = async (url, init) => {
    calls.push({ url: String(url), init });
    const step = script[Math.min(calls.length - 1, script.length - 1)];
    return typeof step === 'function' ? step(url, init) : step;
  };
  impl.calls = calls;
  return impl;
}
function jsonResponse(status, body, extra = {}) {
  return new Response(typeof body === 'string' ? body : JSON.stringify(body), {
    status, headers: { 'content-type': 'application/json' }, ...extra,
  });
}

(async () => {
  await check('non-loopback and non-literal endpoints are refused with no network I/O', async () => {
    const bad = [
      'http://localhost:8000', 'http://localhost', 'https://127.0.0.1:8000', 'http://127.0.0.1', 'http://127.0.0.1:8000/',
      'http://127.0.0.1:8000/health', 'http://127.0.0.1.evil.example:8000', 'http://0.0.0.0:8000', 'http://127.0.0.2:8000',
      'http://[::ffff:127.0.0.1]:8000', 'http://user@127.0.0.1:8000', 'http://127.0.0.1:0', 'http://127.0.0.1:70000',
      'http://example.com:8000', 'http://10.0.0.5:8000', '', null, undefined, 42,
    ];
    for (const endpoint of bad) {
      const fetchImpl = scriptedFetch([jsonResponse(200, { loaded: [MODEL] })]);
      const out = await call({ endpoint, fetchImpl });
      assert.strictEqual(out.status, 'unavailable', String(endpoint));
      assert.strictEqual(out.choice, null);
      assert.strictEqual(out.probabilities, null);
      assert.strictEqual(out.latencyMs, null, 'never started -> null latency');
      assert.strictEqual(fetchImpl.calls.length, 0, `no I/O for ${endpoint}`);
    }
  });

  await check('literal [::1] endpoints pass validation and use redirect:error on probe and POST', async () => {
    const fetchImpl = scriptedFetch([jsonResponse(200, { loaded: [MODEL] }), jsonResponse(200, okAnswer('s1'))]);
    const out = await call({ endpoint: 'http://[::1]:8123', fetchImpl });
    assert.strictEqual(out.status, 'ok');
    assert.strictEqual(out.choice, SKILLS[1]);
    assert.strictEqual(fetchImpl.calls.length, 2);
    assert.strictEqual(fetchImpl.calls[0].url, 'http://[::1]:8123/health');
    assert.strictEqual(fetchImpl.calls[1].url, 'http://[::1]:8123/v1/systemone');
    for (const c of fetchImpl.calls) assert.strictEqual(c.init.redirect, 'error');
    assert.ok(!('body' in fetchImpl.calls[0].init) || fetchImpl.calls[0].init.body === undefined, 'probe carries no body');
    assert.strictEqual(fetchImpl.calls[1].init.method, 'POST');
    assert.strictEqual(fetchImpl.calls[1].init.body, JSON.stringify(built.request));
  });

  await check('real server on [::1] works when IPv6 loopback is available', async () => {
    const server = await startServer({}, '::1');
    if (!server) return; // IPv6 loopback not available here
    const out = await call({ endpoint: server.endpoint });
    await server.close();
    assert.strictEqual(out.status, 'ok');
  });

  await check('ok path decodes choice, maps keys to skill ids and returns aligned probabilities', async () => {
    const server = await startServer({ post: (req, res) => { res.writeHead(200); res.end(JSON.stringify(okAnswer('none'))); } });
    const out = await call({ endpoint: server.endpoint });
    assert.strictEqual(out.status, 'ok');
    assert.strictEqual(out.choice, 'none');
    assert.strictEqual(out.probabilities.length, SKILLS.length + 1);
    assert.ok(typeof out.latencyMs === 'number' && out.latencyMs >= 0);
    const second = await call({ endpoint: server.endpoint });
    assert.strictEqual(second.status, 'ok');
    await server.close();
    const sent = JSON.parse(server.hits.bodies[0]);
    assert.deepStrictEqual(sent, JSON.parse(JSON.stringify(built.request)));
  });

  await check('an external redirect on the probe is refused and never followed', async () => {
    const target = await startServer();
    const origin = await startServer({
      health: (req, res) => { res.writeHead(302, { location: `${target.endpoint}/health` }); res.end(); },
    });
    const out = await call({ endpoint: origin.endpoint });
    assert.strictEqual(out.status, 'redirect_refused');
    assert.strictEqual(target.hits.health, 0, 'redirect target must not be contacted');
    assert.strictEqual(origin.hits.post, 0, 'no prompt text without a passed probe');
    await Promise.all([origin.close(), target.close()]);
  });

  await check('an external redirect on the POST is refused and never followed', async () => {
    const target = await startServer();
    const origin = await startServer({
      post: (req, res) => { res.writeHead(307, { location: `${target.endpoint}/v1/systemone` }); res.end(); },
    });
    const out = await call({ endpoint: origin.endpoint });
    assert.strictEqual(out.status, 'redirect_refused');
    assert.strictEqual(target.hits.post, 0, 'the prompt must not be re-sent to the redirect target');
    await Promise.all([origin.close(), target.close()]);
  });

  await check('redirect errors from the transport map to redirect_refused', async () => {
    const err = new TypeError('fetch failed', { cause: new Error('unexpected redirect') });
    const out = await call({ endpoint: 'http://127.0.0.1:8123', fetchImpl: scriptedFetch([() => { throw err; }]) });
    assert.strictEqual(out.status, 'redirect_refused');
    const opaque = await call({ endpoint: 'http://127.0.0.1:8123', fetchImpl: scriptedFetch([{ status: 0, type: 'opaqueredirect' }]) });
    assert.strictEqual(opaque.status, 'redirect_refused');
  });

  await check('a hanging probe times out at the single deadline and no prompt is sent', async () => {
    const server = await startServer({ health: () => { /* never answers */ } });
    const started = performance.now();
    const out = await call({ endpoint: server.endpoint, __budget: 300 });
    const elapsed = performance.now() - started;
    assert.strictEqual(out.status, 'timeout');
    assert.ok(elapsed >= 250 && elapsed < 900, `elapsed ${elapsed}`);
    assert.ok(out.latencyMs >= 250 && out.latencyMs < 900, `latency ${out.latencyMs}`);
    assert.strictEqual(server.hits.post, 0);
    await server.close();
  });

  await check('the probe and the POST share ONE deadline', async () => {
    const slow = (ms, fn) => (req, res, body) => setTimeout(() => fn(req, res, body), ms);
    const handlers = {
      health: slow(160, (req, res) => { res.writeHead(200); res.end(JSON.stringify({ loaded: [MODEL] })); }),
      post: slow(160, (req, res) => { res.writeHead(200); res.end(JSON.stringify(okAnswer())); }),
    };
    const server = await startServer(handlers);
    const tight = await call({ endpoint: server.endpoint, __budget: 250 });
    assert.strictEqual(tight.status, 'timeout', 'each hop fits 250 ms alone but together they do not');
    const roomy = await call({ endpoint: server.endpoint, __budget: 1200 });
    assert.strictEqual(roomy.status, 'ok');
    await server.close();
  });

  await check('a transport that ignores the abort signal still resolves at the deadline', async () => {
    const fetchImpl = () => new Promise(() => { /* never settles */ });
    const started = performance.now();
    const out = await call({ endpoint: 'http://127.0.0.1:8123', fetchImpl, __budget: 200 });
    const elapsed = performance.now() - started;
    assert.strictEqual(out.status, 'timeout');
    assert.ok(elapsed < 600, `elapsed ${elapsed}`);
  });

  await check('a deadline that already passed times out without any I/O', async () => {
    const fetchImpl = scriptedFetch([jsonResponse(200, { loaded: [MODEL] })]);
    const out = await call({ endpoint: 'http://127.0.0.1:8123', fetchImpl, __budget: -5 });
    assert.strictEqual(out.status, 'timeout');
    assert.strictEqual(fetchImpl.calls.length, 0);
    assert.strictEqual(typeof out.latencyMs, 'number');
  });

  await check('probe is cached for 60 s (0600 file) and the POST alone follows', async () => {
    const dir = tmpDir();
    const cachePath = path.join(dir, 'sub', 'laya-health.json');
    const server = await startServer();
    const first = await call({ endpoint: server.endpoint, healthCachePath: cachePath });
    assert.strictEqual(first.status, 'ok');
    assert.strictEqual(server.hits.health, 1);
    assert.strictEqual(fs.statSync(cachePath).mode & 0o777, 0o600);
    assert.deepStrictEqual(fs.readdirSync(path.dirname(cachePath)), ['laya-health.json'], 'no temp files left behind');
    const second = await call({ endpoint: server.endpoint, healthCachePath: cachePath });
    assert.strictEqual(second.status, 'ok');
    assert.strictEqual(server.hits.health, 1, 'cached probe skips /health');
    assert.strictEqual(server.hits.post, 2);
    await server.close();
  });

  await check('probe cache expires after 60 s and is keyed by endpoint and model', async () => {
    const dir = tmpDir();
    const cachePath = path.join(dir, 'laya-health.json');
    const a = await startServer();
    const b = await startServer();
    const t0 = 1_700_000_000_000;
    await call({ endpoint: a.endpoint, healthCachePath: cachePath, wallNow: () => t0 });
    assert.strictEqual(a.hits.health, 1);
    await call({ endpoint: a.endpoint, healthCachePath: cachePath, wallNow: () => t0 + 59_000 });
    assert.strictEqual(a.hits.health, 1, 'still fresh at 59 s');
    await call({ endpoint: a.endpoint, healthCachePath: cachePath, wallNow: () => t0 + 61_000 });
    assert.strictEqual(a.hits.health, 2, 'expired at 61 s');

    // a different endpoint must not reuse endpoint A's probe
    const outB = await call({ endpoint: b.endpoint, healthCachePath: cachePath, wallNow: () => t0 + 61_500 });
    assert.strictEqual(outB.status, 'ok');
    assert.strictEqual(b.hits.health, 1, 'new endpoint is probed');
    // ... and both stay cached side by side
    await call({ endpoint: a.endpoint, healthCachePath: cachePath, wallNow: () => t0 + 62_000 });
    await call({ endpoint: b.endpoint, healthCachePath: cachePath, wallNow: () => t0 + 62_000 });
    assert.strictEqual(a.hits.health, 2);
    assert.strictEqual(b.hits.health, 1);

    // a different model must not reuse the cached probe for the same endpoint
    const postsBefore = a.hits.post;
    const other = await call({ endpoint: a.endpoint, model: 'other-model', healthCachePath: cachePath, wallNow: () => t0 + 62_500 });
    assert.strictEqual(other.status, 'identity_failed', 'other-model is not loaded');
    assert.strictEqual(a.hits.health, 3, 'a model change re-probes');
    assert.strictEqual(a.hits.post, postsBefore, 'identity failure sent no further prompt');
    await Promise.all([a.close(), b.close()]);
  });

  await check('a future-dated or corrupt cache entry never extends trust', async () => {
    const dir = tmpDir();
    const cachePath = path.join(dir, 'laya-health.json');
    const server = await startServer();
    const key = `${server.endpoint}\n${MODEL}`;
    fs.writeFileSync(cachePath, JSON.stringify({ entries: { [key]: { endpoint: server.endpoint, model: MODEL, at: Date.now() + 3_600_000 } } }));
    assert.strictEqual((await call({ endpoint: server.endpoint, healthCachePath: cachePath })).status, 'ok');
    assert.strictEqual(server.hits.health, 1, 'future timestamp ignored -> probed');
    fs.writeFileSync(cachePath, '{not json');
    assert.strictEqual((await call({ endpoint: server.endpoint, healthCachePath: cachePath })).status, 'ok');
    assert.strictEqual(server.hits.health, 2, 'corrupt cache -> probed');
    await server.close();
  });

  await check('cache I/O failures are ignored', async () => {
    const dir = tmpDir();
    const blocker = path.join(dir, 'file');
    fs.writeFileSync(blocker, 'x');
    const server = await startServer();
    const out = await call({ endpoint: server.endpoint, healthCachePath: path.join(blocker, 'nested', 'laya-health.json') });
    assert.strictEqual(out.status, 'ok');
    const disabled = await call({ endpoint: server.endpoint, healthCachePath: null });
    assert.strictEqual(disabled.status, 'ok');
    await server.close();
  });

  await check('the default cache lives under the typed-decisions root', async () => {
    const dir = tmpDir();
    const prior = process.env.RHIZE_TYPED_DECISIONS_ROOT;
    process.env.RHIZE_TYPED_DECISIONS_ROOT = dir;
    try {
      const server = await startServer();
      const out = await client.callChoice({
        endpoint: server.endpoint, model: MODEL, request: built.request, keyMap: built.keyMap, deadlineAt: performance.now() + 1500,
      });
      assert.strictEqual(out.status, 'ok');
      assert.ok(fs.existsSync(path.join(dir, 'laya-health.json')));
      await server.close();
    } finally {
      if (prior === undefined) delete process.env.RHIZE_TYPED_DECISIONS_ROOT; else process.env.RHIZE_TYPED_DECISIONS_ROOT = prior;
    }
  });

  await check('identity probe failures are identity_failed and no prompt is sent', async () => {
    const variants = {
      'empty loaded': (req, res) => { res.writeHead(200); res.end(JSON.stringify({ loaded: [] })); },
      'other model': (req, res) => { res.writeHead(200); res.end(JSON.stringify({ loaded: ['someone-else'] })); },
      'no loaded array': (req, res) => { res.writeHead(200); res.end(JSON.stringify({ status: 'ok', loaded: MODEL })); },
      'non-JSON': (req, res) => { res.writeHead(200); res.end('<html>ok</html>'); },
      'array JSON': (req, res) => { res.writeHead(200); res.end('[]'); },
      'HTTP 404': (req, res) => { res.writeHead(404); res.end('{}'); },
      'HTTP 503': (req, res) => { res.writeHead(503); res.end(JSON.stringify({ loaded: [MODEL] })); },
      'oversize health': (req, res) => { res.writeHead(200); res.end(JSON.stringify({ loaded: [MODEL], pad: 'x'.repeat(70 * 1024) })); },
    };
    for (const [name, health] of Object.entries(variants)) {
      const server = await startServer({ health });
      const out = await call({ endpoint: server.endpoint });
      assert.strictEqual(out.status, 'identity_failed', name);
      assert.strictEqual(server.hits.post, 0, `${name}: nothing sent`);
      await server.close();
    }
  });

  await check('connection refused is unavailable; non-2xx POST is unavailable', async () => {
    const refused = await call({ endpoint: await closedPort() });
    assert.strictEqual(refused.status, 'unavailable');
    assert.ok(typeof refused.latencyMs === 'number', 'a started call reports its latency');
    for (const code of [500, 503, 404, 400]) {
      const server = await startServer({ post: (req, res) => { res.writeHead(code); res.end(JSON.stringify(okAnswer())); } });
      const out = await call({ endpoint: server.endpoint });
      assert.strictEqual(out.status, 'unavailable', `HTTP ${code}`);
      assert.strictEqual(out.choice, null);
      await server.close();
    }
  });

  await check('a closed port is detected by a bare TCP connect before fetch is touched', async () => {
    const original = Object.getOwnPropertyDescriptor(globalThis, 'fetch');
    let fetchCalls = 0;
    Object.defineProperty(globalThis, 'fetch', {
      configurable: true, writable: true, value: (...args) => { fetchCalls += 1; return original.get ? original.get.call(globalThis)(...args) : original.value(...args); },
    });
    try {
      const started = performance.now();
      const out = await call({ endpoint: await closedPort() });
      assert.strictEqual(out.status, 'unavailable');
      assert.strictEqual(fetchCalls, 0, 'fetch must not be used when nothing is listening');
      assert.ok(performance.now() - started < 500);
      const server = await startServer();
      assert.strictEqual((await call({ endpoint: server.endpoint })).status, 'ok');
      assert.strictEqual(fetchCalls, 2, 'probe + POST use fetch when the port is open');
      await server.close();
    } finally {
      Object.defineProperty(globalThis, 'fetch', original);
    }
  });

  await check('invalid POST bodies are invalid', async () => {
    const wrongModel = okAnswer(); wrongModel.routing.model = 'other';
    const badChoice = okAnswer(); badChoice.answers.skill.choice = 's9';
    const missingProb = okAnswer(); delete missingProb.answers.skill.probabilities.none;
    const outOfRange = okAnswer(); outOfRange.answers.skill.probabilities.s0 = 1.5;
    const noAnswers = { routing: { model: MODEL } };
    const bodies = {
      'non-JSON': 'oops', 'empty': '', 'wrong model': JSON.stringify(wrongModel), 'bad choice': JSON.stringify(badChoice),
      'missing probability': JSON.stringify(missingProb), 'probability > 1': JSON.stringify(outOfRange),
      'no answers': JSON.stringify(noAnswers), 'JSON null': 'null', 'invalid UTF-8': Buffer.from([0x7b, 0xff, 0x7d]),
    };
    for (const [name, body] of Object.entries(bodies)) {
      const server = await startServer({ post: (req, res) => { res.writeHead(200); res.end(body); } });
      const out = await call({ endpoint: server.endpoint });
      assert.strictEqual(out.status, 'invalid', name);
      assert.strictEqual(out.choice, null, name);
      assert.strictEqual(out.probabilities, null, name);
      await server.close();
    }
  });

  await check('responses are capped at 64 KiB (declared, buffered and endless)', async () => {
    assert.strictEqual(client.MAX_RESPONSE_BYTES, 64 * 1024);
    const padded = (n) => { const a = okAnswer(); a.pad = 'x'.repeat(n); return JSON.stringify(a); };
    const justUnder = await startServer({ post: (req, res) => { res.writeHead(200); res.end(padded(60 * 1024)); } });
    assert.strictEqual((await call({ endpoint: justUnder.endpoint })).status, 'ok', '60 KiB body is still accepted');
    await justUnder.close();

    const over = await startServer({ post: (req, res) => { res.writeHead(200); res.end(padded(70 * 1024)); } });
    assert.strictEqual((await call({ endpoint: over.endpoint })).status, 'invalid');
    await over.close();

    const chunked = await startServer({
      post: (req, res) => {
        res.writeHead(200);
        res.write(padded(10).slice(0, 5));
        res.write('x'.repeat(80 * 1024));
        res.end('y');
      },
    });
    assert.strictEqual((await call({ endpoint: chunked.endpoint })).status, 'invalid');
    await chunked.close();

    let writing = true;
    const endless = await startServer({
      post: (req, res) => {
        res.writeHead(200);
        const pump = () => { if (writing && !res.destroyed) { res.write('x'.repeat(16 * 1024)); setImmediate(pump); } };
        pump();
        res.on('close', () => { writing = false; });
      },
    });
    const started = performance.now();
    const out = await call({ endpoint: endless.endpoint, __budget: 3000 });
    const elapsed = performance.now() - started;
    writing = false;
    assert.strictEqual(out.status, 'invalid', 'an endless body is cut at the cap, not at the deadline');
    assert.ok(elapsed < 1500, `elapsed ${elapsed}`);
    await endless.close();
  });

  await check('a hanging POST body after a passed probe times out', async () => {
    const server = await startServer({ post: (req, res) => { res.writeHead(200); res.write('{'); /* never ends */ } });
    const out = await call({ endpoint: server.endpoint, __budget: 300 });
    assert.strictEqual(out.status, 'timeout');
    assert.strictEqual(server.hits.post, 1);
    await server.close();
  });

  await check('prompt text is sent only after the probe passed (call order)', async () => {
    const fetchImpl = scriptedFetch([jsonResponse(200, { loaded: [MODEL] }), jsonResponse(200, okAnswer())]);
    await call({ endpoint: 'http://127.0.0.1:8123', fetchImpl });
    assert.ok(fetchImpl.calls[0].url.endsWith('/health') && fetchImpl.calls[0].init.body === undefined);
    assert.ok(fetchImpl.calls[1].url.endsWith('/v1/systemone'));
    const failing = scriptedFetch([jsonResponse(200, { loaded: [] }), jsonResponse(200, okAnswer())]);
    const out = await call({ endpoint: 'http://127.0.0.1:8123', fetchImpl: failing });
    assert.strictEqual(out.status, 'identity_failed');
    assert.strictEqual(failing.calls.length, 1);
  });

  await check('callChoice never throws', async () => {
    const outputs = [
      await client.callChoice(),
      await client.callChoice(null),
      await client.callChoice({}),
      await call({ endpoint: 'http://127.0.0.1:8123', fetchImpl: () => { throw new Error('sync boom'); } }),
      await call({ endpoint: 'http://127.0.0.1:8123', fetchImpl: () => Promise.reject(new Error('async boom')) }),
      await call({ endpoint: 'http://127.0.0.1:8123', fetchImpl: scriptedFetch([{ status: 200 }]) }),
      await call({ endpoint: 'http://127.0.0.1:8123', request: (() => { const c = {}; c.c = c; return c; })() }),
      await call({ endpoint: 'http://127.0.0.1:8123', deadlineAt: NaN }),
      await call({ endpoint: 'http://127.0.0.1:8123', keyMap: null }),
      await call({ endpoint: 'http://127.0.0.1:8123', model: '' }),
      await call({ endpoint: 'http://127.0.0.1:8123', now: () => { throw new Error('clock'); } }),
    ];
    for (const out of outputs) {
      assert.ok(out && typeof out.status === 'string', JSON.stringify(out));
      assert.ok(['ok', 'timeout', 'unavailable', 'invalid', 'identity_failed', 'redirect_refused'].includes(out.status));
      assert.ok('choice' in out && 'probabilities' in out && 'latencyMs' in out);
      if (out.status !== 'ok') assert.strictEqual(out.choice, null);
    }
  });

  await check('env-proxy hazard: refuse when node would route loopback through a proxy', async () => {
    assert.strictEqual(client.envProxyHazard({}), false);
    assert.strictEqual(client.envProxyHazard({ NODE_USE_ENV_PROXY: '1' }), true);
    assert.strictEqual(client.envProxyHazard({ NODE_USE_ENV_PROXY: '1', NO_PROXY: 'localhost,127.0.0.1,::1' }), false);
    assert.strictEqual(client.envProxyHazard({ NODE_OPTIONS: '--use-env-proxy', no_proxy: 'example.com' }), true);
    assert.strictEqual(client.envProxyHazard({ NODE_USE_ENV_PROXY: '1', NO_PROXY: '*' }), false);
    // the exemption must cover THIS endpoint's host: 127.0.0.1 does not exempt [::1], CIDR is not trusted
    assert.strictEqual(client.envProxyHazard({ NODE_USE_ENV_PROXY: '1', NO_PROXY: '127.0.0.1' }, 'http://[::1]:8000'), true);
    assert.strictEqual(client.envProxyHazard({ NODE_USE_ENV_PROXY: '1', NO_PROXY: '::1' }, 'http://[::1]:8000'), false);
    assert.strictEqual(client.envProxyHazard({ NODE_USE_ENV_PROXY: '1', NO_PROXY: '127.0.0.0/8' }, 'http://127.0.0.1:8000'), true);
  });

  const failed = results.filter(([, ok]) => !ok);
  console.log(`\n${results.length - failed.length}/${results.length} laya-client tests passed.`);
  process.exit(failed.length ? 1 : 0);
})().catch((err) => { console.error(err); process.exit(1); });
