#!/usr/bin/env node
// End-to-end tests for the skill-fit co-sign in rhize-context-manager/hooks/skill-router.js
// (Laya earned-authority plan v3, A1). Every case spawns the REAL hook as a child process
// with a throw-away HOME / XDG_DATA_HOME / RHIZE_TYPED_DECISIONS_ROOT, a fixture router
// index + skill map, and a fake Laya server on 127.0.0.1 (random port, via
// RHIZE_LAYA_ENDPOINT). Standalone: exits non-zero on any failure.
'use strict';
const assert = require('assert');
const crypto = require('crypto');
const fs = require('fs');
const http = require('http');
const os = require('os');
const path = require('path');
const { spawn, spawnSync } = require('child_process');

const REPO = path.resolve(__dirname, '..', '..');
const ROUTER = path.join(REPO, 'rhize-context-manager', 'hooks', 'skill-router.js');
const LIB = path.join(REPO, 'rhize-context-manager', 'hooks', 'lib');
const instrument = require(path.join(LIB, 'laya-instrument.js'));
const td = require(path.join(LIB, 'typed-decisions.js'));

const MODEL = 'typed-decisions';
const SKILL = {
  ctx: 'skill:alpha/context-pack',
  git: 'skill:alpha/git-helper',
  setup: 'skill:beta/tool-setup',
  review: 'skill:beta/code-review',
};
const DESCRIPTIONS = {
  [SKILL.ctx]: 'Pack project context for handoff.',
  [SKILL.git]: 'Git history and rebase help.',
  [SKILL.setup]: 'Install and configure dev tooling.',
  [SKILL.review]: 'Review a diff.',
};
const INDEX = {
  schemaVersion: '1.1.0', disclosure: {}, remediation: {}, succession: {},
  router: {
    extendsBases: {},
    signals: {
      [SKILL.ctx]: [{ kind: 'name', weight: 1, label: 'context-pack' }, { kind: 'tag', weight: 2, label: 'context' }, { kind: 'tag', weight: 2, label: 'git' }],
      [SKILL.git]: [{ kind: 'name', weight: 1, label: 'git-helper' }, { kind: 'tag', weight: 2, label: 'git' }, { kind: 'tag', weight: 2, label: 'rebase' }],
      [SKILL.setup]: [{ kind: 'name', weight: 1, label: 'tool-setup' }, { kind: 'tag', weight: 2, label: 'tooling' }],
      [SKILL.review]: [{ kind: 'name', weight: 1, label: 'code-review' }, { kind: 'tag', weight: 2, label: 'diff' }],
    },
  },
};
const MAP = {
  nodes: Object.keys(DESCRIPTIONS).map((id) => ({ id, kind: 'skill', name: id.split('/').pop(), description: DESCRIPTIONS[id] })),
  edges: [],
};
const PROMPT = 'help me get git and context tooling set up';
const INCUMBENT_MESSAGE = 'Consider the alpha:context-pack skill (matches context, git)';
const lineFor = (message) => JSON.stringify({ hookSpecificOutput: { hookEventName: 'UserPromptSubmit', additionalContext: message } }) + '\n';
const INCUMBENT_LINE = lineFor(INCUMBENT_MESSAGE);
const sha = (text) => crypto.createHash('sha256').update(text, 'utf8').digest('hex');

// ---------------------------------------------------------------- harness

const results = [];
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

function stateDoc(mode, { pinned = false, revision = 1 } = {}) {
  return {
    schemaVersion: 1, revision, updatedAt: '2026-10-11T12:00:00Z',
    decisions: {
      'skill-fit': {
        mode, pinned, since: '2026-10-11T12:00:00Z', reason: 'test_setup',
        policySha256: mode === 'cosign' ? td.policySha256() : null,
        instrumentSha256: mode === 'cosign' ? instrument.instrumentSha256() : null,
        layaRevision: null, cohortId: null,
      },
    },
  };
}

// opts: mode | state (raw string or object) | noIndex | staticMap | workflow | endpoint | env
function scenario(opts = {}) {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'router-skill-fit-'));
  const root = path.join(home, 'typed');
  const logPath = path.join(home, 'suggestion-log.jsonl');
  const ctxDir = path.join(home, '.claude', 'context-manager');
  fs.mkdirSync(ctxDir, { recursive: true });
  if (!opts.noIndex) fs.writeFileSync(path.join(ctxDir, 'skill-map.indexes.json'), JSON.stringify(opts.index || INDEX));
  if (!opts.noMap) fs.writeFileSync(path.join(ctxDir, 'skill-map.static.json'), JSON.stringify(opts.map || MAP));
  if (opts.mode || opts.state !== undefined) {
    fs.mkdirSync(root, { recursive: true });
    const body = opts.state !== undefined ? opts.state : stateDoc(opts.mode, { pinned: opts.pinned, revision: opts.revision });
    fs.writeFileSync(path.join(root, 'registry-state.json'), typeof body === 'string' ? body : JSON.stringify(body));
  }
  if (opts.workflow) {
    const cfg = path.join(home, 'xdg', 'rhize', 'workflow-selection', 'config.json');
    fs.mkdirSync(path.dirname(cfg), { recursive: true });
    fs.writeFileSync(cfg, JSON.stringify({ schemaVersion: 1, enabled: true }));
  }
  const env = {
    ...process.env, HOME: home, XDG_DATA_HOME: path.join(home, 'xdg'), RHIZE_TYPED_DECISIONS_ROOT: root,
    RHIZE_SUGGESTION_LOG: logPath, PYTHONDONTWRITEBYTECODE: '1', ...(opts.env || {}),
  };
  delete env.RHIZE_HOST;
  if (opts.env && opts.env.RHIZE_HOST) env.RHIZE_HOST = opts.env.RHIZE_HOST;
  // The fake server stands in for the evaluated checkpoint, so the harness asserts endpoint authority.
  if (opts.endpoint) { env.RHIZE_LAYA_ENDPOINT = opts.endpoint; env.RHIZE_LAYA_ENDPOINT_AUTHORITY = '1'; }
  else { delete env.RHIZE_LAYA_ENDPOINT; delete env.RHIZE_LAYA_ENDPOINT_AUTHORITY; }
  return { home, root, logPath, env };
}

function runHook(sc, { prompt = PROMPT, sessionId = 'sess-default', preload = null, input = null, hook = ROUTER } = {}) {
  return new Promise((resolve) => {
    const args = preload ? ['--require', preload, hook] : [hook];
    const started = process.hrtime.bigint();
    const child = spawn(process.execPath, args, { env: sc.env, stdio: ['pipe', 'pipe', 'pipe'] });
    let stdout = ''; let stderr = ''; let firstByteMs = null;
    child.stdout.on('data', (d) => {
      if (firstByteMs === null) firstByteMs = Number(process.hrtime.bigint() - started) / 1e6;
      stdout += d;
    });
    child.stderr.on('data', (d) => { stderr += d; });
    const killer = setTimeout(() => child.kill('SIGKILL'), 15000);
    child.on('close', (code) => {
      clearTimeout(killer);
      resolve({ code, stdout, stderr, firstByteMs, ms: Number(process.hrtime.bigint() - started) / 1e6 });
    });
    child.stdin.end(input !== null ? input : JSON.stringify({ prompt, session_id: sessionId }));
  });
}

function recordFiles(sc) {
  const dir = path.join(sc.root, 'skill-fit', 'records');
  try { return fs.readdirSync(dir).filter((n) => n.endsWith('.jsonl')).map((n) => path.join(dir, n)); } catch (_e) { return []; }
}
function readRecords(sc) {
  const out = [];
  for (const file of recordFiles(sc)) {
    for (const line of fs.readFileSync(file, 'utf8').split('\n')) if (line.trim()) out.push(JSON.parse(line));
  }
  return out;
}
function readLog(sc) {
  try {
    return fs.readFileSync(sc.logPath, 'utf8').split('\n').filter(Boolean).map((l) => JSON.parse(l));
  } catch (_e) { return []; }
}
function pythonValidate(file) {
  const code = 'import sys,json; sys.path.insert(0,"rhize-context-manager/scripts"); from typed_decisions import contract; '
    + '[contract.validate_record(json.loads(l)) for l in open(sys.argv[1])]';
  const r = spawnSync('python3', ['-c', code, file], { cwd: REPO, encoding: 'utf8' });
  assert.strictEqual(r.status, 0, `contract.validate_record rejected ${file}:\n${r.stderr}`);
}
function assertRecordsValid(sc, expected) {
  const files = recordFiles(sc);
  let lines = 0;
  for (const file of files) {
    pythonValidate(file);
    const mode = fs.statSync(file).mode & 0o777;
    assert.strictEqual(mode, 0o600, `record file mode ${mode.toString(8)}`);
    for (const line of fs.readFileSync(file, 'utf8').split('\n').filter(Boolean)) {
      assert.ok(Buffer.byteLength(line) < 4096, `record is ${Buffer.byteLength(line)} bytes`);
      lines += 1;
    }
  }
  if (expected !== undefined) assert.strictEqual(lines, expected, `expected ${expected} record(s), found ${lines}`);
  return readRecords(sc);
}

// ---- fake Laya

function keyFor(request, skillName) {
  const criteria = request.questions.skill.criteria;
  for (const [key, text] of Object.entries(criteria)) {
    if (key !== 'none' && (text === skillName || text.startsWith(`${skillName}:`))) return key;
  }
  return 'none';
}
function answerBody(request, key) {
  const keys = Object.keys(request.questions.skill.criteria);
  const probabilities = {};
  for (const k of keys) probabilities[k] = k === key ? 0.7 : 0.3 / (keys.length - 1);
  return { routing: { model: MODEL }, answers: { skill: { type: 'choice', choice: key, probabilities } } };
}
// handlers.choose(request) -> skill name | 'none'; health/post override the raw handlers.
function layaServer(handlers = {}) {
  const hits = { health: 0, post: 0, requests: [] };
  const sockets = new Set();
  const server = http.createServer((req, res) => {
    if (req.method === 'GET' && req.url === '/health') {
      hits.health += 1;
      if (handlers.health) return handlers.health(req, res);
      res.writeHead(200, { 'content-type': 'application/json' });
      return res.end(JSON.stringify({ status: 'ok', loaded: [MODEL] }));
    }
    let body = '';
    req.on('data', (c) => { body += c; });
    req.on('end', () => {
      hits.post += 1;
      let request = null;
      try { request = JSON.parse(body); hits.requests.push(request); } catch (_e) { /* keep null */ }
      if (handlers.post) return handlers.post(req, res, request);
      const skillName = handlers.choose ? handlers.choose(request) : 'context-pack';
      res.writeHead(200, { 'content-type': 'application/json' });
      return res.end(JSON.stringify(answerBody(request, skillName === 'none' ? 'none' : keyFor(request, skillName))));
    });
    return undefined;
  });
  server.on('connection', (s) => { sockets.add(s); s.on('close', () => sockets.delete(s)); });
  return new Promise((resolve) => server.listen(0, '127.0.0.1', () => {
    const { port } = server.address();
    resolve({
      port, endpoint: `http://127.0.0.1:${port}`, hits,
      close: () => new Promise((done) => { for (const s of sockets) s.destroy(); server.close(() => done()); }),
    });
  }));
}
async function closedEndpoint() {
  const s = await layaServer();
  await s.close();
  return s.endpoint;
}

function sessionForArm(arm, prompt = PROMPT, holdback = 0.1) {
  for (let i = 0; i < 5000; i += 1) {
    const id = `sess-${arm}-${i}`;
    if (td.armFor(sha(id), sha(prompt), holdback) === arm) return id;
  }
  throw new Error('no session found');
}
const TREATMENT = sessionForArm('treatment');
const HOLDBACK = sessionForArm('holdback');

const cleanup = [];
function track(sc) { cleanup.push(sc.home); return sc; }

// ---------------------------------------------------------------- tests

(async () => {
  // Baseline: what today's hook writes for the fixture (also the startup-cost reference).
  const baselineSc = track(scenario({ mode: 'off' }));
  const baselineServer = await layaServer();
  baselineSc.env.RHIZE_LAYA_ENDPOINT = baselineServer.endpoint;
  const baseline = await runHook(baselineSc);

  await check('mode off: incumbent payload, Laya never contacted, no decision record', async () => {
    assert.strictEqual(baseline.code, 0, baseline.stderr);
    assert.strictEqual(baseline.stdout, INCUMBENT_LINE);
    assert.strictEqual(baselineServer.hits.health + baselineServer.hits.post, 0);
    assert.strictEqual(recordFiles(baselineSc).length, 0);
    const [row] = readLog(baselineSc);
    assert.deepStrictEqual(Object.keys(row), ['ts', 'session_id', 'hook', 'suggested', 'context_hash', 'typed_mode', 'typed_arm', 'typed_status', 'typed_agrees']);
    assert.strictEqual(row.suggested, SKILL.ctx);
    assert.strictEqual(row.typed_mode, null);
    assert.strictEqual(row.typed_status, null);
  });

  await check('cosign + treatment + Laya agrees: incumbent emitted, record + legacy row written', async () => {
    const server = await layaServer({ choose: () => 'context-pack' });
    const sc = track(scenario({ mode: 'cosign', revision: 4, endpoint: server.endpoint }));
    const out = await runHook(sc, { sessionId: TREATMENT });
    assert.strictEqual(out.code, 0, out.stderr);
    assert.strictEqual(out.stdout, INCUMBENT_LINE);
    assert.strictEqual(out.stderr, '');
    assert.strictEqual(server.hits.health, 1);
    assert.strictEqual(server.hits.post, 1);
    const [rec] = assertRecordsValid(sc, 1);
    assert.strictEqual(rec.mode, 'cosign');
    assert.strictEqual(rec.arm, 'treatment');
    assert.strictEqual(rec.propensity, 0.9);
    assert.strictEqual(rec.registryRevision, 4);
    assert.strictEqual(rec.basis, 'live');
    assert.strictEqual(rec.sourceStratum, 'fired');
    assert.strictEqual(rec.host, 'claude');
    assert.strictEqual(rec.policy, 'cosign-v1');
    assert.strictEqual(rec.policySha256, td.policySha256());
    assert.strictEqual(rec.instrument, 'laya-choice-v1');
    assert.strictEqual(rec.instrumentSha256, instrument.instrumentSha256());
    assert.strictEqual(rec.layaRevision, 'unknown');
    assert.deepStrictEqual(rec.incumbent, { skillId: SKILL.ctx, score: 4 });
    assert.deepStrictEqual(rec.shortlist, [SKILL.ctx, SKILL.git, SKILL.setup]);
    assert.strictEqual(rec.laya.status, 'ok');
    assert.strictEqual(rec.laya.choice, SKILL.ctx);
    assert.strictEqual(rec.laya.probabilities.length, 4);
    assert.strictEqual(rec.laya.truncated, false);
    assert.ok(typeof rec.laya.latencyMs === 'number' && rec.laya.latencyMs >= 0);
    assert.strictEqual(rec.emitted, SKILL.ctx);
    assert.strictEqual(rec.sessionHash, sha(TREATMENT));
    assert.strictEqual(rec.promptHash, sha(PROMPT));
    assert.strictEqual(rec.promptLengthBucket, 'lt200');
    assert.strictEqual(rec.occurrenceKey, td.occurrenceKey(rec.sessionHash, rec.promptHash, rec.ts));
    // the version hashes pin the live code and index
    const hook = ['route-core.js', path.join('..', 'skill-router.js'), 'laya-instrument.js']
      .map((f) => fs.readFileSync(path.join(LIB, f)));
    assert.strictEqual(rec.routerSourceSha256, crypto.createHash('sha256').update(Buffer.concat(hook)).digest('hex'));
    assert.strictEqual(rec.indexSha256, sha(JSON.stringify(INDEX.router)));
    // the request the fake server saw is exactly the contract builder's request
    const expected = instrument.buildChoiceRequest(PROMPT, [SKILL.ctx, SKILL.git, SKILL.setup].map((skillId) => ({ skillId, description: DESCRIPTIONS[skillId] })));
    assert.strictEqual(instrument.canonicalJson(server.hits.requests[0]), instrument.canonicalJson(expected.request));
    assert.strictEqual(rec.criteriaSha256, expected.criteriaSha256);
    assert.ok(expected.request.questions.skill.criteria.s0.includes('Pack project context'), 'map descriptions reach Laya');
    // legacy row
    const rows = readLog(sc);
    assert.strictEqual(rows.length, 1);
    assert.deepStrictEqual(rows[0], {
      ts: rec.ts, session_id: TREATMENT, hook: 'router', suggested: SKILL.ctx, context_hash: sha(PROMPT).slice(0, 16),
      typed_mode: 'cosign', typed_arm: 'treatment', typed_status: 'ok', typed_agrees: true,
    });
    await server.close();
  });

  for (const [label, pick] of [['another skill', 'git-helper'], ['none', 'none']]) {
    await check(`cosign + treatment + Laya picks ${label}: router suggestion withheld`, async () => {
      const server = await layaServer({ choose: () => pick });
      const sc = track(scenario({ mode: 'cosign', endpoint: server.endpoint }));
      const out = await runHook(sc, { sessionId: TREATMENT });
      assert.strictEqual(out.code, 0, out.stderr);
      assert.strictEqual(out.stdout, '', 'no workflow message -> nothing emitted');
      const [rec] = assertRecordsValid(sc, 1);
      assert.strictEqual(rec.laya.status, 'ok');
      assert.strictEqual(rec.laya.choice, pick === 'none' ? 'none' : SKILL.git);
      assert.strictEqual(rec.emitted, null);
      assert.strictEqual(rec.incumbent.skillId, SKILL.ctx);
      for (const row of readLog(sc)) assert.strictEqual(row.suggested, null, 'a withheld suggestion is never logged as shown');
      await server.close();
    });
  }

  await check('cosign disagreement keeps a workflow message and drops only the router suggestion', async () => {
    const disagree = await layaServer({ choose: () => 'git-helper' });
    const agree = await layaServer({ choose: () => 'context-pack' });
    const scD = track(scenario({ mode: 'cosign', workflow: true, endpoint: disagree.endpoint }));
    const scA = track(scenario({ mode: 'cosign', workflow: true, endpoint: agree.endpoint }));
    const scS = track(scenario({ mode: 'shadow', workflow: true, endpoint: disagree.endpoint }));
    const [outD, outA, outS] = await Promise.all([runHook(scD, { sessionId: TREATMENT }), runHook(scA, { sessionId: TREATMENT }), runHook(scS, { sessionId: TREATMENT })]);
    const msg = (o) => JSON.parse(o.stdout).hookSpecificOutput.additionalContext;
    const norm = (text) => text.replace(/[0-9a-f]{64}/g, 'ID'); // opportunity ids differ per HOME
    assert.ok(msg(outA).startsWith('Workflow selection checkpoint') && msg(outA).endsWith(INCUMBENT_MESSAGE), 'agree: both parts');
    assert.ok(msg(outS).startsWith('Workflow selection checkpoint') && msg(outS).endsWith(INCUMBENT_MESSAGE), 'shadow keeps the router suggestion');
    const withheld = msg(outD);
    assert.ok(withheld.startsWith('Workflow selection checkpoint'), withheld);
    assert.ok(!withheld.includes('Consider the'), 'router suggestion removed');
    assert.strictEqual(outD.stdout.split('\n').filter(Boolean).length, 1, 'one JSON line');
    assert.strictEqual(`${norm(withheld)} ${INCUMBENT_MESSAGE}`, norm(msg(outA)), 'suppressed payload = incumbent payload minus the router sentence');
    const [rec] = assertRecordsValid(scD, 1);
    assert.strictEqual(rec.emitted, null);
    const [row] = readLog(scD);
    assert.strictEqual(row.suggested, null);
    assert.strictEqual(row.typed_mode, 'cosign');
    assert.strictEqual(row.typed_status, 'ok');
    assert.strictEqual(row.typed_agrees, false);
    await Promise.all([disagree.close(), agree.close()]);
  });

  await check('shadow always emits the incumbent, even when Laya disagrees, and records the disagreement', async () => {
    const server = await layaServer({ choose: () => 'git-helper' });
    const sc = track(scenario({ mode: 'shadow', revision: 2, endpoint: server.endpoint }));
    const out = await runHook(sc, { sessionId: TREATMENT });
    assert.strictEqual(out.stdout, INCUMBENT_LINE);
    const [rec] = assertRecordsValid(sc, 1);
    assert.strictEqual(rec.mode, 'shadow');
    assert.strictEqual(rec.registryRevision, 2);
    assert.strictEqual(rec.laya.choice, SKILL.git);
    assert.strictEqual(rec.emitted, SKILL.ctx);
    const [row] = readLog(sc);
    assert.strictEqual(row.suggested, SKILL.ctx);
    assert.strictEqual(row.typed_mode, 'shadow');
    assert.strictEqual(row.typed_agrees, false);
    await server.close();
  });

  await check('holdback arm stays on the incumbent (cosign mode, Laya disagrees) with propensity = holdback', async () => {
    const server = await layaServer({ choose: () => 'none' });
    const sc = track(scenario({ mode: 'cosign', endpoint: server.endpoint }));
    const out = await runHook(sc, { sessionId: HOLDBACK });
    assert.strictEqual(out.stdout, INCUMBENT_LINE);
    const [rec] = assertRecordsValid(sc, 1);
    assert.strictEqual(rec.arm, 'holdback');
    assert.strictEqual(rec.propensity, 0.1);
    assert.strictEqual(rec.laya.status, 'ok', 'Laya is still asked in the holdback arm');
    assert.strictEqual(rec.laya.choice, 'none');
    assert.strictEqual(rec.emitted, SKILL.ctx);
    const [row] = readLog(sc);
    assert.strictEqual(row.typed_arm, 'holdback');
    assert.strictEqual(row.suggested, SKILL.ctx);
    await server.close();
  });

  await check('arm assignment is deterministic and matches the contract helper', async () => {
    const server = await layaServer({ choose: () => 'context-pack' });
    const sc = track(scenario({ mode: 'shadow', endpoint: server.endpoint }));
    const sessions = ['alpha', 'beta', 'gamma', 'delta', 'epsilon', 'zeta', TREATMENT, HOLDBACK];
    for (const id of [...sessions, TREATMENT, HOLDBACK]) await runHook(sc, { sessionId: id });
    const records = assertRecordsValid(sc, sessions.length + 2);
    for (const rec of records) {
      const expected = td.armFor(rec.sessionHash, rec.promptHash, 0.1);
      assert.strictEqual(rec.arm, expected);
      assert.strictEqual(rec.propensity, expected === 'holdback' ? 0.1 : 0.9);
    }
    const bySession = new Map();
    for (const rec of records) bySession.set(rec.sessionHash, new Set([...(bySession.get(rec.sessionHash) || []), rec.arm]));
    for (const arms of bySession.values()) assert.strictEqual(arms.size, 1, 'same session+prompt -> same arm');
    await server.close();
  });

  // ---- failure statuses: the incumbent payload is emitted byte-for-byte
  const hung = () => {};
  const failureCases = [
    { name: 'timeout (health never answers)', status: 'timeout', server: { health: hung }, noPost: true },
    { name: 'timeout (POST never answers)', status: 'timeout', server: { post: hung } },
    { name: 'unavailable (closed port)', status: 'unavailable', closed: true },
    { name: 'unavailable (HTTP 500)', status: 'unavailable', server: { post: (req, res) => { res.writeHead(500); res.end('{}'); } } },
    { name: 'invalid (not JSON)', status: 'invalid', server: { post: (req, res) => { res.writeHead(200); res.end('<html>'); } } },
    { name: 'invalid (wrong shape)', status: 'invalid', server: { post: (req, res) => { res.writeHead(200); res.end(JSON.stringify({ routing: { model: MODEL }, answers: {} })); } } },
    { name: 'invalid (oversize body)', status: 'invalid', server: { post: (req, res) => { res.writeHead(200); res.end('x'.repeat(100 * 1024)); } } },
    { name: 'identity_failed (model not loaded)', status: 'identity_failed', server: { health: (req, res) => { res.writeHead(200); res.end(JSON.stringify({ loaded: [] })); } }, noPost: true },
    { name: 'identity_failed (health not JSON)', status: 'identity_failed', server: { health: (req, res) => { res.writeHead(200); res.end('hello'); } }, noPost: true },
    { name: 'redirect_refused (probe)', status: 'redirect_refused', redirect: 'health', noPost: true },
    { name: 'redirect_refused (POST)', status: 'redirect_refused', redirect: 'post' },
  ];
  for (const fc of failureCases) {
    await check(`cosign + ${fc.name}: byte-identical incumbent payload and a valid record`, async () => {
      const target = await layaServer();
      let server = null;
      let endpoint;
      if (fc.closed) {
        endpoint = await closedEndpoint();
      } else if (fc.redirect) {
        const move = (req, res) => { res.writeHead(307, { location: `${target.endpoint}${req.url}` }); res.end(); };
        server = await layaServer(fc.redirect === 'health' ? { health: move } : { post: move });
        endpoint = server.endpoint;
      } else {
        server = await layaServer(fc.server);
        endpoint = server.endpoint;
      }
      const sc = track(scenario({ mode: 'cosign', endpoint }));
      const out = await runHook(sc, { sessionId: TREATMENT });
      assert.strictEqual(out.code, 0, out.stderr);
      assert.strictEqual(out.stdout, INCUMBENT_LINE);
      assert.strictEqual(out.stdout, baseline.stdout, 'identical to the mode-off (today) payload');
      const [rec] = assertRecordsValid(sc, 1);
      assert.strictEqual(rec.laya.status, fc.status);
      assert.strictEqual(rec.laya.choice, null);
      assert.strictEqual(rec.laya.probabilities, null);
      assert.strictEqual(rec.emitted, SKILL.ctx);
      assert.strictEqual(rec.mode, 'cosign');
      const [row] = readLog(sc);
      assert.strictEqual(row.suggested, SKILL.ctx);
      assert.strictEqual(row.typed_status, fc.status);
      assert.strictEqual(row.typed_agrees, null);
      if (fc.noPost && server) assert.strictEqual(server.hits.post, 0, 'prompt text is not sent unless the probe passed');
      assert.strictEqual(target.hits.health + target.hits.post, 0, 'redirect targets are never contacted');
      if (fc.status === 'timeout') {
        assert.ok(rec.laya.latencyMs >= 700 && rec.laya.latencyMs < 1500, `latency ${rec.laya.latencyMs}`);
        assert.ok(out.ms < baseline.ms + 800 + 700, `hung Laya run took ${out.ms} ms vs baseline ${baseline.ms} ms`);
      }
      if (server) await server.close();
      await target.close();
    });
  }

  await check('late HTTP completion after the fallback is ignored', async () => {
    const server = await layaServer({
      post: (req, res, request) => setTimeout(() => {
        try { res.writeHead(200); res.end(JSON.stringify(answerBody(request, 'none'))); } catch (_e) { /* client gone */ }
      }, 1500),
    });
    const sc = track(scenario({ mode: 'cosign', endpoint: server.endpoint }));
    const out = await runHook(sc, { sessionId: TREATMENT });
    assert.strictEqual(out.stdout, INCUMBENT_LINE, 'the disagreeing answer arrived too late to matter');
    assert.ok(out.ms < baseline.ms + 800 + 700, `took ${out.ms} ms`);
    assert.ok(out.ms < 1400 + baseline.ms, 'the hook did not wait for the late answer');
    assert.strictEqual(out.stdout.split('\n').filter(Boolean).length, 1);
    const [rec] = assertRecordsValid(sc, 1);
    assert.strictEqual(rec.laya.status, 'timeout');
    assert.strictEqual(rec.emitted, SKILL.ctx);
    await new Promise((r) => setTimeout(r, 1300)); // let the late reply fire; nothing may change
    assert.strictEqual(readRecords(sc).length, 1);
    await server.close();
  });

  // ---- settle-once with a substituted transport (preload patches laya-client's callChoice)
  const preloadDir = fs.mkdtempSync(path.join(os.tmpdir(), 'router-preload-'));
  cleanup.push(preloadDir);
  const preload = path.join(preloadDir, 'preload.js');
  fs.writeFileSync(preload, `
    const client = require(${JSON.stringify(path.join(LIB, 'laya-client.js'))});
    const mode = process.env.TEST_CLIENT_MODE;
    const probs = [0.1, 0.1, 0.1, 0.7];
    if (mode === 'never') client.callChoice = () => new Promise(() => {});
    if (mode === 'late') client.callChoice = () => new Promise((resolve) => setTimeout(() => resolve({ status: 'ok', choice: 'none', probabilities: probs, latencyMs: 5 }), 2500));
    if (mode === 'throw') client.callChoice = () => { throw new Error('boom'); };
    if (mode === 'reject') client.callChoice = () => Promise.reject(new Error('boom'));
    if (mode === 'garbage-choice') client.callChoice = async () => ({ status: 'ok', choice: 'skill:not/in-list', probabilities: probs, latencyMs: 5 });
    if (mode === 'garbage-probs') client.callChoice = async () => ({ status: 'ok', choice: 'none', probabilities: [2, 0], latencyMs: 5 });
    if (mode === 'garbage-status') client.callChoice = async () => ({ status: 'maybe' });
    if (mode === 'undefined') client.callChoice = async () => undefined;
    if (mode === 'async-fatal') { client.callChoice = () => new Promise(() => {}); setTimeout(() => { throw new Error('late uncaught'); }, 100); }
    if (mode === 'double') client.callChoice = () => new Promise((resolve) => setTimeout(() => {
      resolve({ status: 'ok', choice: 'none', probabilities: probs, latencyMs: 5 }); // completes AFTER the fatal handler settled
      throw new Error('uncaught in the same tick');
    }, 100));
    if (mode === 'ok-disagree') client.callChoice = async () => ({ status: 'ok', choice: 'none', probabilities: probs, latencyMs: 5 });
  `);
  const stubCases = [
    { mode: 'never', status: 'timeout', maxMs: 800 + 50 + 600 },
    { mode: 'late', status: 'timeout', maxMs: 800 + 50 + 600 },
    { mode: 'throw', status: 'unavailable', maxMs: 600 },
    { mode: 'reject', status: 'unavailable', maxMs: 600 },
    { mode: 'garbage-choice', status: 'invalid', maxMs: 600 },
    { mode: 'garbage-probs', status: 'invalid', maxMs: 600 },
    { mode: 'garbage-status', status: 'unavailable', maxMs: 600 },
    { mode: 'undefined', status: 'unavailable', maxMs: 600 },
    { mode: 'async-fatal', status: 'unavailable', maxMs: 600 },
    { mode: 'double', status: 'unavailable', maxMs: 600 },
  ];
  for (const sc0 of stubCases) {
    await check(`settle-once: client ${sc0.mode} -> incumbent payload once, record ${sc0.status}`, async () => {
      const sc = track(scenario({ mode: 'cosign', env: { TEST_CLIENT_MODE: sc0.mode } }));
      const out = await runHook(sc, { sessionId: TREATMENT, preload });
      assert.strictEqual(out.code, 0, out.stderr);
      assert.strictEqual(out.stdout, INCUMBENT_LINE, 'exactly one payload line even if a late completion races the fallback');
      assert.ok(out.ms < baseline.ms + sc0.maxMs + 400, `took ${out.ms} ms (baseline ${baseline.ms})`);
      const [rec] = assertRecordsValid(sc, 1);
      assert.strictEqual(rec.laya.status, sc0.status);
      assert.strictEqual(rec.laya.choice, null);
      assert.strictEqual(rec.emitted, SKILL.ctx);
      if (sc0.mode === 'never' || sc0.mode === 'late') {
        assert.ok(rec.laya.latencyMs >= 800 && rec.laya.latencyMs < 1500, `backstop latency ${rec.laya.latencyMs}`);
      }
    });
  }
  await check('settle-once: a substituted transport that agrees/disagrees is honoured exactly once', async () => {
    const sc = track(scenario({ mode: 'cosign', env: { TEST_CLIENT_MODE: 'ok-disagree' } }));
    const out = await runHook(sc, { sessionId: TREATMENT, preload });
    assert.strictEqual(out.stdout, '');
    const [rec] = assertRecordsValid(sc, 1);
    assert.strictEqual(rec.laya.choice, 'none');
    assert.strictEqual(rec.emitted, null);
  });

  // ---- persistence failure never touches the output
  await check('persistence failure: unwritable records dir leaves stdout and exit code intact', async () => {
    for (const [mode, choose, expectLine] of [['cosign', 'context-pack', INCUMBENT_LINE], ['cosign', 'git-helper', ''], ['shadow', 'git-helper', INCUMBENT_LINE]]) {
      const server = await layaServer({ choose: () => choose });
      const sc = track(scenario({ mode, endpoint: server.endpoint }));
      fs.writeFileSync(path.join(sc.root, 'skill-fit'), 'a regular file where the records dir should be');
      const out = await runHook(sc, { sessionId: TREATMENT });
      assert.strictEqual(out.code, 0, out.stderr);
      assert.strictEqual(out.stdout, expectLine);
      assert.strictEqual(out.stderr, '');
      assert.strictEqual(fs.readFileSync(path.join(sc.root, 'skill-fit'), 'utf8'), 'a regular file where the records dir should be');
      if (expectLine) assert.strictEqual(readLog(sc).length, 1, 'legacy row still written');
      await server.close();
    }
  });
  await check('persistence failure: root that cannot be created leaves stdout intact (shadow default)', async () => {
    const server = await layaServer({ choose: () => 'git-helper' });
    const sc = track(scenario({ endpoint: server.endpoint }));
    const blocker = path.join(sc.home, 'blocker');
    fs.writeFileSync(blocker, 'x');
    sc.env.RHIZE_TYPED_DECISIONS_ROOT = path.join(blocker, 'nested', 'typed');
    const out = await runHook(sc);
    assert.strictEqual(out.code, 0, out.stderr);
    assert.strictEqual(out.stdout, INCUMBENT_LINE);
    await server.close();
  });
  await check('persistence failure: unwritable legacy log leaves stdout intact and the record is still written', async () => {
    const server = await layaServer({ choose: () => 'context-pack' });
    const sc = track(scenario({ mode: 'cosign', endpoint: server.endpoint }));
    const blocker = path.join(sc.home, 'blocker');
    fs.writeFileSync(blocker, 'x');
    sc.env.RHIZE_SUGGESTION_LOG = path.join(blocker, 'log.jsonl');
    const out = await runHook(sc, { sessionId: TREATMENT });
    assert.strictEqual(out.code, 0, out.stderr);
    assert.strictEqual(out.stdout, INCUMBENT_LINE);
    assertRecordsValid(sc, 1);
    await server.close();
  });
  await check('symlinked records dir / file are refused (nothing written through the link)', async () => {
    const server = await layaServer({ choose: () => 'context-pack' });
    const sc = track(scenario({ mode: 'cosign', endpoint: server.endpoint }));
    const elsewhere = path.join(sc.home, 'elsewhere');
    fs.mkdirSync(elsewhere);
    fs.symlinkSync(elsewhere, path.join(sc.root, 'skill-fit'));
    const out = await runHook(sc, { sessionId: TREATMENT });
    assert.strictEqual(out.stdout, INCUMBENT_LINE);
    assert.deepStrictEqual(fs.readdirSync(elsewhere), []);
    fs.unlinkSync(path.join(sc.root, 'skill-fit'));
    const day = new Date().toISOString().slice(0, 10);
    fs.mkdirSync(path.join(sc.root, 'skill-fit', 'records'), { recursive: true });
    const victim = path.join(sc.home, 'victim.jsonl');
    fs.writeFileSync(victim, '');
    fs.symlinkSync(victim, path.join(sc.root, 'skill-fit', 'records', `${day}.jsonl`));
    const out2 = await runHook(sc, { sessionId: TREATMENT });
    assert.strictEqual(out2.stdout, INCUMBENT_LINE);
    assert.strictEqual(fs.readFileSync(victim, 'utf8'), '');
    await server.close();
  });
  await check('records dirs are created 0700 and record files 0600 when absent', async () => {
    const server = await layaServer();
    const sc = track(scenario({ endpoint: server.endpoint }));
    assert.ok(!fs.existsSync(sc.root));
    await runHook(sc);
    for (const dir of [sc.root, path.join(sc.root, 'skill-fit'), path.join(sc.root, 'skill-fit', 'records')]) {
      assert.strictEqual(fs.statSync(dir).mode & 0o777, 0o700, dir);
    }
    assertRecordsValid(sc, 1);
    await server.close();
  });

  // ---- eligibility
  await check('explicit skill request skips Laya entirely (no request reaches the server, no record)', async () => {
    const server = await layaServer({ choose: () => 'none' });
    const sc = track(scenario({ mode: 'cosign', endpoint: server.endpoint }));
    const out = await runHook(sc, { prompt: 'Use git-helper please', sessionId: TREATMENT });
    assert.strictEqual(out.stdout, lineFor('Consider the alpha:git-helper skill (matches explicit skill request)'));
    assert.strictEqual(server.hits.health + server.hits.post, 0);
    assert.strictEqual(recordFiles(sc).length, 0);
    const [row] = readLog(sc);
    assert.strictEqual(row.suggested, SKILL.git);
    assert.strictEqual(row.typed_mode, null);
    assert.strictEqual(row.typed_status, null);
    await server.close();
  });
  await check('map-scan fallback (no router index) and unmatched prompts never call Laya', async () => {
    const server = await layaServer({ choose: () => 'none' });
    const fixtureMap = fs.readFileSync(path.join(__dirname, 'fixtures', 'valid-map.json'), 'utf8');
    const sc1 = track(scenario({ mode: 'cosign', endpoint: server.endpoint, noIndex: true, map: JSON.parse(fixtureMap) }));
    const out1 = await runHook(sc1, { sessionId: TREATMENT });
    assert.strictEqual(out1.stdout, lineFor('Consider the rhize-context-manager:graphify skill (matches context, git)'));
    const sc2 = track(scenario({ mode: 'cosign', endpoint: server.endpoint }));
    const out2 = await runHook(sc2, { prompt: 'what is the weather like today', sessionId: TREATMENT });
    assert.strictEqual(out2.stdout, '');
    const out3 = await runHook(sc2, { input: JSON.stringify({ prompt: '' }) });
    assert.strictEqual(out3.stdout, '');
    const out4 = await runHook(sc2, { input: '{ not json' });
    assert.strictEqual(out4.code, 0);
    assert.strictEqual(out4.stdout, '');
    assert.strictEqual(server.hits.health + server.hits.post, 0);
    assert.strictEqual(recordFiles(sc1).length + recordFiles(sc2).length, 0);
    await server.close();
  });

  // ---- registry state handling
  await check('missing state -> shipped default (shadow, revision 0)', async () => {
    const server = await layaServer({ choose: () => 'git-helper' });
    const sc = track(scenario({ endpoint: server.endpoint }));
    const out = await runHook(sc, { sessionId: TREATMENT });
    assert.strictEqual(out.stdout, INCUMBENT_LINE);
    const [rec] = assertRecordsValid(sc, 1);
    assert.strictEqual(rec.mode, 'shadow');
    assert.strictEqual(rec.registryRevision, 0);
    await server.close();
  });
  const corrupt = {
    'junk JSON': '{"schemaVersion": 1, "revi',
    'empty file': '',
    'schema-invalid (cosign without bound hashes)': (() => { const d = stateDoc('cosign'); d.decisions['skill-fit'].policySha256 = null; return d; })(),
    'schema-invalid (revision 0)': { ...stateDoc('cosign'), revision: 0 },
    'schema-invalid (unknown decision)': (() => { const d = stateDoc('cosign'); d.decisions['nope'] = d.decisions['skill-fit']; return d; })(),
    'schema-invalid (extra key)': { ...stateDoc('cosign'), extra: true },
    'schema-invalid (unreachable mode)': stateDoc('critical'),
    'JSON array': [],
  };
  for (const [name, state] of Object.entries(corrupt)) {
    await check(`corrupt registry state (${name}) -> shadow, revision 0, incumbent kept`, async () => {
      const server = await layaServer({ choose: () => 'git-helper' });
      const sc = track(scenario({ state, endpoint: server.endpoint }));
      const out = await runHook(sc, { sessionId: TREATMENT });
      assert.strictEqual(out.stdout, INCUMBENT_LINE, 'a corrupt state can never suppress');
      const [rec] = assertRecordsValid(sc, 1);
      assert.strictEqual(rec.mode, 'shadow');
      assert.strictEqual(rec.registryRevision, 0);
      await server.close();
    });
  }
  await check('cosign state bound to other policy/instrument hashes is not deployed (shadow, incumbent kept)', async () => {
    const server = await layaServer({ choose: () => 'git-helper' });
    const state = stateDoc('cosign', { revision: 3 });
    state.decisions['skill-fit'].instrumentSha256 = 'e'.repeat(64);
    const sc = track(scenario({ state, endpoint: server.endpoint }));
    const out = await runHook(sc, { sessionId: TREATMENT });
    assert.strictEqual(out.stdout, INCUMBENT_LINE);
    const [rec] = assertRecordsValid(sc, 1);
    assert.strictEqual(rec.mode, 'shadow');
    assert.strictEqual(rec.registryRevision, 3);
    await server.close();
  });
  await check('state path that is a directory counts as corrupt -> shadow', async () => {
    const server = await layaServer({ choose: () => 'git-helper' });
    const sc = track(scenario({ endpoint: server.endpoint }));
    fs.mkdirSync(path.join(sc.root, 'registry-state.json'), { recursive: true });
    const out = await runHook(sc, { sessionId: TREATMENT });
    assert.strictEqual(out.stdout, INCUMBENT_LINE);
    assert.strictEqual(assertRecordsValid(sc, 1)[0].mode, 'shadow');
    await server.close();
  });
  await check('pinned shadow is respected (and the revision is recorded)', async () => {
    const server = await layaServer({ choose: () => 'git-helper' });
    const sc = track(scenario({ mode: 'shadow', pinned: true, revision: 9, endpoint: server.endpoint }));
    const out = await runHook(sc, { sessionId: TREATMENT });
    assert.strictEqual(out.stdout, INCUMBENT_LINE);
    const [rec] = assertRecordsValid(sc, 1);
    assert.strictEqual(rec.mode, 'shadow');
    assert.strictEqual(rec.registryRevision, 9);
    await server.close();
  });
  await check('pinned cosign stays cosign; pinned off disables Laya completely', async () => {
    const server = await layaServer({ choose: () => 'git-helper' });
    const cos = track(scenario({ mode: 'cosign', pinned: true, endpoint: server.endpoint }));
    assert.strictEqual((await runHook(cos, { sessionId: TREATMENT })).stdout, '');
    const hitsAfterCosign = server.hits.post;
    const off = track(scenario({ mode: 'off', pinned: true, endpoint: server.endpoint }));
    const out = await runHook(off, { sessionId: TREATMENT });
    assert.strictEqual(out.stdout, INCUMBENT_LINE);
    assert.strictEqual(server.hits.post, hitsAfterCosign);
    assert.strictEqual(recordFiles(off).length, 0);
    await server.close();
  });
  await check('RHIZE_LAYA_ENDPOINT overrides only to a literal loopback; localhost is ignored', async () => {
    const server = await layaServer();
    const sc = track(scenario({ mode: 'cosign', env: { RHIZE_LAYA_ENDPOINT: `http://localhost:${new URL(server.endpoint).port}` } }));
    sc.env.RHIZE_LAYA_ENDPOINT = `http://localhost:${new URL(server.endpoint).port}`;
    const out = await runHook(sc, { sessionId: TREATMENT });
    assert.strictEqual(out.stdout, INCUMBENT_LINE);
    assert.strictEqual(server.hits.health + server.hits.post, 0, 'localhost override must not be used');
    await server.close();
  });

  // ---- privacy / evidence quality
  await check('no prompt text reaches records, the legacy log or the health cache; Laya gets the head only', async () => {
    const secret = 'zebracorn';
    const prompt = `${PROMPT} ${secret}`;
    const server = await layaServer({ choose: () => 'context-pack' });
    const sc = track(scenario({ mode: 'cosign', endpoint: server.endpoint }));
    await runHook(sc, { prompt, sessionId: TREATMENT });
    assert.ok(JSON.stringify(server.hits.requests[0]).includes(secret), 'Laya receives the prompt head');
    const sink = [];
    const walk = (dir) => { for (const e of fs.readdirSync(dir, { withFileTypes: true })) { const p = path.join(dir, e.name); if (e.isDirectory()) walk(p); else sink.push(fs.readFileSync(p, 'utf8')); } };
    walk(sc.root);
    sink.push(fs.readFileSync(sc.logPath, 'utf8'));
    for (const text of sink) assert.ok(!text.includes(secret), 'prompt text leaked to disk');
    assert.ok(fs.existsSync(path.join(sc.root, 'laya-health.json')), 'identity probe cached');
    assertRecordsValid(sc, 1);
    await server.close();
  });
  await check('probe cache is shared across hook runs (second run skips /health)', async () => {
    const server = await layaServer();
    const sc = track(scenario({ mode: 'cosign', endpoint: server.endpoint }));
    await runHook(sc, { sessionId: TREATMENT });
    await runHook(sc, { sessionId: TREATMENT });
    assert.strictEqual(server.hits.health, 1);
    assert.strictEqual(server.hits.post, 2);
    assertRecordsValid(sc, 2);
    await server.close();
  });
  await check('long prompts are truncated for Laya, bucketed from the original, and record truncated:true', async () => {
    const server = await layaServer();
    const sc = track(scenario({ mode: 'shadow', endpoint: server.endpoint }));
    const prompt = `${PROMPT}. ${'lorem ipsum dolor '.repeat(120)}`;
    await runHook(sc, { prompt, sessionId: TREATMENT });
    const sent = server.hits.requests[0].state.request;
    assert.ok(Array.from(sent).length <= 1200);
    const [rec] = assertRecordsValid(sc, 1);
    assert.strictEqual(rec.promptLengthBucket, 'gt1200');
    assert.strictEqual(rec.laya.truncated, true);
    assert.strictEqual(rec.promptHash, sha(prompt));
    await server.close();
  });
  await check('layaRevision comes from laya-runtime.json only when well formed; host honours RHIZE_HOST=codex', async () => {
    const server = await layaServer();
    const good = track(scenario({ mode: 'shadow', endpoint: server.endpoint, env: { RHIZE_HOST: 'codex' } }));
    fs.mkdirSync(good.root, { recursive: true });
    fs.writeFileSync(path.join(good.root, 'laya-runtime.json'), JSON.stringify({ revision: '55cf4c4' }));
    await runHook(good);
    const [rec] = assertRecordsValid(good, 1);
    assert.strictEqual(rec.layaRevision, '55cf4c4');
    assert.strictEqual(rec.host, 'codex');
    const bad = track(scenario({ mode: 'shadow', endpoint: server.endpoint, env: { RHIZE_HOST: 'something-else' } }));
    fs.writeFileSync(path.join(bad.root, 'laya-runtime.json'), JSON.stringify({ revision: 'has spaces/and slashes' }));
    await runHook(bad);
    const [rec2] = assertRecordsValid(bad, 1);
    assert.strictEqual(rec2.layaRevision, 'unknown');
    assert.strictEqual(rec2.host, 'claude');
    await server.close();
  });
  await check('descriptions are optional: no skill map -> still builds, validates and asks Laya', async () => {
    const server = await layaServer({ choose: () => 'context-pack' });
    const sc = track(scenario({ mode: 'cosign', noMap: true, endpoint: server.endpoint }));
    const out = await runHook(sc, { sessionId: TREATMENT });
    assert.strictEqual(out.stdout, INCUMBENT_LINE);
    assert.strictEqual(server.hits.requests[0].questions.skill.criteria.s0, 'context-pack');
    assertRecordsValid(sc, 1);
    await server.close();
  });
  await check('the payload is flushed BEFORE persistence work (slow persistence cannot delay output)', async () => {
    // A large router index makes the post-flush work (indexSha256 over JSON.stringify(index)) slow.
    const filler = {};
    for (let i = 0; i < 90000; i += 1) {
      filler[`skill:filler/f${i}`] = [{ kind: 'name', weight: 1, label: `filler-${i}-${'q'.repeat(150)}` }];
    }
    const big = { ...INDEX, router: { extendsBases: {}, signals: { ...INDEX.router.signals, ...filler } } };
    const server = await layaServer({ choose: () => 'context-pack' });
    const sc = track(scenario({ mode: 'shadow', endpoint: server.endpoint, index: big }));
    const out = await runHook(sc, { sessionId: TREATMENT });
    assert.strictEqual(out.stdout, INCUMBENT_LINE);
    const [rec] = assertRecordsValid(sc, 1);
    assert.strictEqual(rec.indexSha256, sha(JSON.stringify(big.router)));
    assert.ok(out.ms - out.firstByteMs > 40, `persistence should trail the flush: first byte ${out.firstByteMs} ms, exit ${out.ms} ms`);
    await server.close();
  });
  await check('missing or broken skill-fit modules degrade to the legacy router (no crash, no output change)', async () => {
    const server = await layaServer({ choose: () => 'none' });
    for (const damage of ['missing laya-client.js', 'syntax error in decision-registry.js', 'missing typed-decisions.js']) {
      const copy = fs.mkdtempSync(path.join(os.tmpdir(), 'router-partial-'));
      cleanup.push(copy);
      fs.mkdirSync(path.join(copy, 'hooks', 'lib'), { recursive: true });
      fs.copyFileSync(ROUTER, path.join(copy, 'hooks', 'skill-router.js'));
      for (const f of fs.readdirSync(LIB)) fs.copyFileSync(path.join(LIB, f), path.join(copy, 'hooks', 'lib', f));
      if (damage === 'missing laya-client.js') fs.unlinkSync(path.join(copy, 'hooks', 'lib', 'laya-client.js'));
      if (damage === 'syntax error in decision-registry.js') fs.writeFileSync(path.join(copy, 'hooks', 'lib', 'decision-registry.js'), 'module.exports = {{{');
      if (damage === 'missing typed-decisions.js') fs.unlinkSync(path.join(copy, 'hooks', 'lib', 'typed-decisions.js'));
      const sc = track(scenario({ mode: 'cosign', endpoint: server.endpoint }));
      const out = await runHook(sc, { sessionId: TREATMENT, hook: path.join(copy, 'hooks', 'skill-router.js') });
      assert.strictEqual(out.code, 0, `${damage}: ${out.stderr}`);
      assert.strictEqual(out.stdout, INCUMBENT_LINE, damage);
      assert.strictEqual(out.stderr, '', damage);
      assert.strictEqual(recordFiles(sc).length, 0, damage);
    }
    assert.strictEqual(server.hits.health + server.hits.post, 0);
    await server.close();
  });
  await check('concurrent hooks append whole, valid lines', async () => {
    const server = await layaServer();
    const sc = track(scenario({ mode: 'shadow', endpoint: server.endpoint }));
    await Promise.all(Array.from({ length: 8 }, (_v, i) => runHook(sc, { sessionId: `concurrent-${i}` })));
    assertRecordsValid(sc, 8);
    await server.close();
  });

  for (const dir of cleanup) fs.rmSync(dir, { recursive: true, force: true });
  await baselineServer.close();
  const failed = results.filter(([, ok]) => !ok);
  console.log(`\n${results.length - failed.length}/${results.length} router skill-fit tests passed.`);
  process.exit(failed.length ? 1 : 0);
})().catch((err) => { console.error(err); process.exit(1); });
