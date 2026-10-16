#!/usr/bin/env node
// Tests for rhize-context-manager/hooks/lib/decision-registry.js, the READ-ONLY registry/state
// reader the skill-router hook uses (plan v3 §4.1, I6). Its validators mirror
// scripts/typed_decisions/contract.py; parity is checked here against the shared fixtures and
// against the Python validators themselves on a set of mutated documents.
'use strict';
const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');

const REPO = path.resolve(__dirname, '..', '..');
const LIB = path.join(REPO, 'rhize-context-manager', 'hooks', 'lib');
const FIX = path.join(REPO, 'tests', 'rhize-context-manager', 'fixtures', 'typed-decisions');
const reg = require(path.join(LIB, 'decision-registry.js'));
const REGISTRY_PATH = path.join(REPO, 'rhize-context-manager', 'catalog', 'decision-registry.json');
const baseRegistry = JSON.parse(fs.readFileSync(REGISTRY_PATH, 'utf8'));
const fixtures = JSON.parse(fs.readFileSync(path.join(FIX, 'registry.json'), 'utf8'));

let passed = 0;
let failed = 0;
function check(name, fn) {
  try { fn(); passed += 1; console.log(`PASS ${name}`); } catch (err) {
    failed += 1; console.error(`FAIL ${name}`); console.error(err && err.stack ? err.stack : err);
  }
}

const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'decision-registry-test-'));
let counter = 0;
function write(name, body) {
  counter += 1;
  const file = path.join(dir, `${counter}-${name}`);
  fs.writeFileSync(file, typeof body === 'string' ? body : JSON.stringify(body));
  return file;
}
const clone = (v) => JSON.parse(JSON.stringify(v));
// The cosign fixture is bound to Laya revision 55cf4c4ebb4e: point the reader at a runtime pin that matches.
const FIXTURE_REVISION = fixtures.validStates.cosign.decisions['skill-fit'].layaRevision;
const RUNTIME = path.join(dir, 'laya-runtime.json');
fs.writeFileSync(RUNTIME, JSON.stringify({ revision: FIXTURE_REVISION }));
const read = (opts) => reg.readDecisionConfig('skill-fit', { layaRuntimePath: RUNTIME, ...opts });
const noEnv = (fn) => {
  const prior = process.env.RHIZE_LAYA_ENDPOINT;
  delete process.env.RHIZE_LAYA_ENDPOINT;
  try { return fn(); } finally { if (prior !== undefined) process.env.RHIZE_LAYA_ENDPOINT = prior; }
};
const withEnv = (value, fn) => {
  const prior = process.env.RHIZE_LAYA_ENDPOINT;
  process.env.RHIZE_LAYA_ENDPOINT = value;
  try { return fn(); } finally { if (prior === undefined) delete process.env.RHIZE_LAYA_ENDPOINT; else process.env.RHIZE_LAYA_ENDPOINT = prior; }
};
const missing = path.join(dir, 'does-not-exist.json');

check('shipped registry + missing state -> defaultMode shadow, revision 0, registry values', () => noEnv(() => {
  const cfg = read({ statePath: missing });
  assert.deepStrictEqual(cfg, {
    mode: 'shadow', pinned: false, holdback: 0.1, latencyBudgetMs: 800, endpoint: 'http://127.0.0.1:8000',
    model: 'typed-decisions', lambda: 1, registryRevision: 0, deployablePolicy: 'cosign-v1',
  });
}));

check('default state path is <typed-decisions root>/registry-state.json', () => noEnv(() => {
  const prior = process.env.RHIZE_TYPED_DECISIONS_ROOT;
  const root = fs.mkdtempSync(path.join(dir, 'root-'));
  process.env.RHIZE_TYPED_DECISIONS_ROOT = root;
  try {
    fs.writeFileSync(path.join(root, 'registry-state.json'), JSON.stringify(fixtures.validStates.cosign));
    fs.writeFileSync(path.join(root, 'laya-runtime.json'), JSON.stringify({ revision: FIXTURE_REVISION }));
    const cfg = reg.readDecisionConfig('skill-fit');
    assert.strictEqual(cfg.mode, fixtures.validStates.cosign.decisions['skill-fit'].mode);
    assert.strictEqual(cfg.registryRevision, fixtures.validStates.cosign.revision);
    assert.strictEqual(reg.defaultRegistryPath(), REGISTRY_PATH);
    assert.strictEqual(reg.defaultStatePath(), path.join(root, 'registry-state.json'));
  } finally {
    if (prior === undefined) delete process.env.RHIZE_TYPED_DECISIONS_ROOT; else process.env.RHIZE_TYPED_DECISIONS_ROOT = prior;
  }
}));

check('valid state entries drive mode, pinned and revision', () => noEnv(() => {
  const cosign = read({ statePath: write('cosign.json', fixtures.validStates.cosign) });
  assert.strictEqual(cosign.mode, 'cosign');
  assert.strictEqual(cosign.registryRevision, fixtures.validStates.cosign.revision);
  const pinned = read({ statePath: write('pinned.json', fixtures.validStates['pinned-shadow']) });
  assert.strictEqual(pinned.mode, 'shadow');
  assert.strictEqual(pinned.pinned, true);
  assert.strictEqual(pinned.registryRevision, fixtures.validStates['pinned-shadow'].revision);
  const off = clone(fixtures.validStates['pinned-shadow']);
  off.decisions['skill-fit'].mode = 'off';
  assert.strictEqual(read({ statePath: write('off.json', off) }).mode, 'off');
}));

check('cosign bound to different policy/instrument hashes is not deployed (shadow, revision and pin kept)', () => noEnv(() => {
  for (const field of ['policySha256', 'instrumentSha256']) {
    const state = clone(fixtures.validStates.cosign);
    state.decisions['skill-fit'][field] = 'f'.repeat(64);
    reg.validateState(state, baseRegistry); // schema-valid ...
    const cfg = read({ statePath: write(`stale-${field}.json`, state) });
    assert.strictEqual(cfg.mode, 'shadow', field); // ... but not what this code evaluated
    assert.strictEqual(cfg.registryRevision, state.revision, field);
  }
  const ok = read({ statePath: write('bound.json', fixtures.validStates.cosign) });
  assert.strictEqual(ok.mode, 'cosign', 'the fixture binds the real policy and instrument hashes');
}));

check('cosign bound to another Laya revision (or to one the runtime pin no longer confirms) reads as shadow', () => noEnv(() => {
  const other = write('runtime-other.json', { revision: 'ffffffffffff' });
  assert.strictEqual(read({ statePath: write('rev.json', fixtures.validStates.cosign), layaRuntimePath: other }).mode, 'shadow');
  assert.strictEqual(read({ statePath: write('rev2.json', fixtures.validStates.cosign), layaRuntimePath: missing }).mode, 'shadow');
  const unbound = clone(fixtures.validStates.cosign);
  unbound.decisions['skill-fit'].layaRevision = null;
  assert.strictEqual(read({ statePath: write('rev3.json', unbound), layaRuntimePath: missing }).mode, 'cosign');
  assert.strictEqual(reg.currentLayaRevision(RUNTIME), FIXTURE_REVISION);
  assert.strictEqual(reg.currentLayaRevision(missing), 'unknown');
}));

check('an overriding endpoint keeps an earned cosign only when its authority is asserted', () => {
  const statePath = write('override.json', fixtures.validStates.cosign);
  const priorAuthority = process.env.RHIZE_LAYA_ENDPOINT_AUTHORITY;
  delete process.env.RHIZE_LAYA_ENDPOINT_AUTHORITY;
  try {
    withEnv('http://127.0.0.1:9999', () => {
      const cfg = read({ statePath });
      assert.strictEqual(cfg.endpoint, 'http://127.0.0.1:9999');
      assert.strictEqual(cfg.mode, 'shadow');
    });
    withEnv('http://127.0.0.1:8000', () => assert.strictEqual(read({ statePath }).mode, 'cosign')); // same endpoint: no override
    process.env.RHIZE_LAYA_ENDPOINT_AUTHORITY = '1';
    withEnv('http://127.0.0.1:9999', () => assert.strictEqual(read({ statePath }).mode, 'cosign'));
  } finally {
    if (priorAuthority === undefined) delete process.env.RHIZE_LAYA_ENDPOINT_AUTHORITY; else process.env.RHIZE_LAYA_ENDPOINT_AUTHORITY = priorAuthority;
  }
});

check('a symlinked state file is corrupt -> shadow (parity with the Python reader)', () => noEnv(() => {
  const target = write('real-state.json', fixtures.validStates.cosign);
  const link = path.join(dir, 'linked-state.json');
  fs.symlinkSync(target, link);
  assert.strictEqual(read({ statePath: link }).mode, 'shadow');
}));

check('valid state without a skill-fit entry -> registry default, state revision', () => noEnv(() => {
  const state = { schemaVersion: 1, revision: 6, updatedAt: '2026-10-11T12:00:00Z', decisions: {} };
  const cfg = read({ statePath: write('empty.json', state) });
  assert.strictEqual(cfg.mode, 'shadow');
  assert.strictEqual(cfg.registryRevision, 6);
}));

check('fixture invalid states -> shadow / revision 0, with the contract reason', () => noEnv(() => {
  // These frozen fixtures predate the bounded workflow policy; retain their original reachability.
  const frozen = clone(fixtures.invalidRegistries.find((item) => item.name === 'workflow-cosign').registry);
  frozen.decisions['workflow-fit'].reachableModes = ['shadow'];
  const frozenPath = write('frozen-registry.json', frozen);
  for (const item of fixtures.invalidStates) {
    assert.throws(() => reg.validateState(item.state, frozen), (err) => err.message === item.reason, item.name);
    const cfg = read({ registryPath: frozenPath, statePath: write(`${item.name}.json`, item.state) });
    assert.strictEqual(cfg.mode, 'shadow', item.name);
    assert.strictEqual(cfg.registryRevision, 0, item.name);
  }
  for (const [name, state] of Object.entries(fixtures.validStates)) reg.validateState(state, baseRegistry, name);
}));

check('corrupt / unreadable / oversize / non-file state -> shadow, revision 0', () => noEnv(() => {
  for (const [name, file] of Object.entries({
    junk: write('junk.json', '{"schemaVersion":'),
    empty: write('empty.json', ''),
    huge: write('huge.json', ' '.repeat((1 << 20) + 1)),
    array: write('array.json', '[]'),
    directory: dir,
  })) {
    const cfg = read({ statePath: file });
    assert.strictEqual(cfg.mode, 'shadow', name);
    assert.strictEqual(cfg.registryRevision, 0, name);
    assert.strictEqual(cfg.pinned, false, name);
  }
}));

check('registry unreadable or invalid -> off (no Laya at all)', () => noEnv(() => {
  assert.strictEqual(read({ registryPath: missing, statePath: missing }).mode, 'off');
  assert.strictEqual(read({ registryPath: write('junk.json', '{nope'), statePath: missing }).mode, 'off');
  assert.strictEqual(read({ registryPath: write('arr.json', '[]'), statePath: missing }).mode, 'off');
  for (const item of fixtures.invalidRegistries) {
    assert.throws(() => reg.validateRegistry(item.registry), (err) => err.message === item.reason, item.name);
    const cfg = read({ registryPath: write(`${item.name}.json`, item.registry), statePath: missing });
    assert.strictEqual(cfg.mode, 'off', item.name);
    assert.strictEqual(cfg.endpoint, null, item.name);
  }
  // even a valid state cannot resurrect an invalid registry
  const bad = clone(baseRegistry); bad.decisions['skill-fit'].endpoint = 'http://localhost:8000';
  assert.strictEqual(read({ registryPath: write('bad.json', bad), statePath: write('cosign.json', fixtures.validStates.cosign) }).mode, 'off');
}));

check('unknown decision -> off; bounded workflow-fit defaults shadow with its own policy', () => noEnv(() => {
  assert.strictEqual(reg.readDecisionConfig('nope', { statePath: missing }).mode, 'off');
  const wf = reg.readDecisionConfig('workflow-fit', { statePath: missing });
  assert.strictEqual(wf.mode, 'shadow');
  assert.strictEqual(wf.endpoint, 'http://127.0.0.1:8000');
  assert.strictEqual(wf.holdback, 0);
  assert.strictEqual(wf.deployablePolicy, 'credential-cli-v1');
}));

check('RHIZE_LAYA_ENDPOINT overrides the endpoint only when it is a literal loopback URL', () => {
  const endpoint = (value) => withEnv(value, () => read({ statePath: missing }).endpoint);
  assert.strictEqual(endpoint('http://127.0.0.1:43211'), 'http://127.0.0.1:43211');
  assert.strictEqual(endpoint('http://[::1]:43211'), 'http://[::1]:43211');
  for (const bad of ['http://localhost:43211', 'https://127.0.0.1:43211', 'http://127.0.0.1:43211/', 'http://127.0.0.1',
    'http://127.0.0.1:0', 'http://127.0.0.1:99999', 'http://example.com:80', 'http://127.0.0.1.evil.com:80', 'http://0.0.0.0:80',
    'http://user@127.0.0.1:80', '']) {
    assert.strictEqual(endpoint(bad), 'http://127.0.0.1:8000', JSON.stringify(bad));
  }
  assert.strictEqual(withEnv('http://127.0.0.1:43211', () => reg.readDecisionConfig('workflow-fit', { statePath: missing }).endpoint), 'http://127.0.0.1:43211');
});

check('the reader never writes (no files or directories are created)', () => noEnv(() => {
  const sandbox = fs.mkdtempSync(path.join(dir, 'ro-'));
  const before = fs.readdirSync(sandbox);
  read({ statePath: path.join(sandbox, 'nope', 'registry-state.json') });
  assert.deepStrictEqual(fs.readdirSync(sandbox), before);
}));

// ---- parity with contract.py on mutated documents
function pythonVerdicts(registries, states) {
  const code = [
    'import sys, json',
    'sys.path.insert(0, "rhize-context-manager/scripts")',
    'from typed_decisions import contract',
    'doc = json.load(sys.stdin)',
    'def ok(fn):',
    '    try:',
    '        fn(); return True',
    '    except (ValueError, KeyError, TypeError):',
    '        return False',
    'base = doc["base"]',
    'print(json.dumps({"registries": [ok(lambda r=r: contract.validate_registry(r)) for r in doc["registries"]],',
    '                  "states": [ok(lambda s=s: contract.validate_state(s, base)) for s in doc["states"]]}))',
  ].join('\n');
  const run = spawnSync('python3', ['-c', code], { cwd: REPO, input: JSON.stringify({ base: baseRegistry, registries, states }), encoding: 'utf8' });
  assert.strictEqual(run.status, 0, run.stderr);
  return JSON.parse(run.stdout);
}
const jsOk = (fn) => { try { fn(); return true; } catch (_e) { return false; } };

check('validators agree with contract.validate_registry / validate_state on mutated documents', () => {
  const mutateRegistry = (fn) => { const r = clone(baseRegistry); fn(r.decisions['skill-fit'], r); return r; };
  const registries = [
    baseRegistry,
    mutateRegistry((e) => { e.holdback = 0.6; }),
    mutateRegistry((e) => { e.holdback = 0.5; }),
    mutateRegistry((e) => { e.holdback = -0.1; }),
    mutateRegistry((e) => { e.latencyBudgetMs = 99; }),
    mutateRegistry((e) => { e.latencyBudgetMs = 5001; }),
    mutateRegistry((e) => { e.latencyBudgetMs = 100.5; }),
    mutateRegistry((e) => { e.lambda = 0; }),
    mutateRegistry((e) => { e.lambda = 2.5; }),
    mutateRegistry((e) => { e.endpoint = 'http://localhost:8000'; }),
    mutateRegistry((e) => { e.endpoint = 'http://[::1]:8000'; }),
    mutateRegistry((e) => { e.endpoint = 'http://127.0.0.1:8000/'; }),
    mutateRegistry((e) => { e.model = 'other'; }),
    mutateRegistry((e) => { e.instrument = 'laya-choice-v0'; }),
    mutateRegistry((e) => { e.deployablePolicy = 'nope'; }),
    mutateRegistry((e) => { e.deployablePolicy = null; }),
    mutateRegistry((e) => { e.reachableModes = ['off', 'off']; }),
    mutateRegistry((e) => { e.reachableModes = []; }),
    mutateRegistry((e) => { e.reachableModes = ['shadow']; }),
    mutateRegistry((e) => { e.defaultMode = 'off'; }),
    mutateRegistry((e) => { e.tier = 'critical'; }),
    mutateRegistry((e) => { e.tier = 'workflow'; }),
    mutateRegistry((e) => { e.tier = 'nope'; }),
    mutateRegistry((e) => { e.incumbent = 'has space'; }),
    mutateRegistry((e) => { delete e.gates.promote.cohortSize; }),
    mutateRegistry((e) => { e.gates.promote.cohortSize = 19; }),
    mutateRegistry((e) => { e.gates.promote.alphaBase = 0.3; }),
    mutateRegistry((e) => { e.gates.demote.minLabeled = 9; }),
    mutateRegistry((e) => { e.gates.demote.extra = 1; }),
    mutateRegistry((e) => { e.gates = null; }),
    mutateRegistry((e) => { e.extra = true; }),
    mutateRegistry((e, r) => { r.schemaVersion = 2; }),
    mutateRegistry((e, r) => { r.decisions = {}; }),
    mutateRegistry((e, r) => { r.decisions['unknown'] = e; }),
    mutateRegistry((e, r) => { r.decisions['workflow-fit'].endpoint = 'http://127.0.0.1:8000'; }),
    mutateRegistry((e, r) => { r.decisions['workflow-fit'].reachableModes = ['shadow', 'cosign']; }),
  ];
  const mutateState = (fn) => { const s = clone(fixtures.validStates.cosign); fn(s, s.decisions['skill-fit'] || s.decisions[Object.keys(s.decisions)[0]]); return s; };
  const states = [
    fixtures.validStates.cosign,
    fixtures.validStates['pinned-shadow'],
    mutateState((s) => { s.schemaVersion = 2; }),
    mutateState((s) => { s.revision = 0; }),
    mutateState((s) => { s.revision = -3; }),
    mutateState((s) => { s.revision = 1.5; }),
    mutateState((s) => { s.revision = '2'; }),
    mutateState((s) => { s.updatedAt = '2026-10-11'; }),
    mutateState((s) => { s.updatedAt = '2026-10-11T12:00:00+00:00'; }),
    mutateState((s) => { s.updatedAt = '2026-10-11T12:00:00.123Z'; }),
    mutateState((s) => { s.extra = 1; }),
    mutateState((s) => { delete s.updatedAt; }),
    mutateState((s) => { s.decisions = []; }),
    mutateState((s) => { s.decisions['mystery'] = s.decisions['skill-fit']; }),
    mutateState((s, e) => { e.mode = 'critical'; }),
    mutateState((s, e) => { e.mode = 'off'; }),
    mutateState((s, e) => { e.pinned = 'yes'; }),
    mutateState((s, e) => { e.since = 'yesterday'; }),
    mutateState((s, e) => { e.reason = 'Gate Passed'; }),
    mutateState((s, e) => { e.reason = ''; }),
    mutateState((s, e) => { e.policySha256 = 'ABC'; }),
    mutateState((s, e) => { e.policySha256 = null; }),
    mutateState((s, e) => { e.instrumentSha256 = null; }),
    mutateState((s, e) => { e.mode = 'shadow'; e.policySha256 = null; e.instrumentSha256 = null; }),
    mutateState((s, e) => { e.layaRevision = 'has space'; }),
    mutateState((s, e) => { e.layaRevision = null; }),
    mutateState((s, e) => { e.cohortId = 'xyz'; }),
    mutateState((s, e) => { e.cohortId = null; }),
    mutateState((s, e) => { e.extra = 1; }),
    mutateState((s, e) => { delete e.cohortId; }),
    mutateState((s) => { s.decisions = {}; }),
  ];
  const py = pythonVerdicts(registries, states);
  registries.forEach((r, i) => assert.strictEqual(jsOk(() => reg.validateRegistry(clone(r))), py.registries[i], `registry case ${i}: ${JSON.stringify(r).slice(0, 160)}`));
  states.forEach((s, i) => assert.strictEqual(jsOk(() => reg.validateState(clone(s), baseRegistry)), py.states[i], `state case ${i}: ${JSON.stringify(s).slice(0, 160)}`));
  assert.ok(py.registries.some((v) => v) && py.registries.some((v) => !v), 'mix of accepted and rejected registries');
  assert.ok(py.states.some((v) => v) && py.states.some((v) => !v), 'mix of accepted and rejected states');
});

fs.rmSync(dir, { recursive: true, force: true });
console.log(`\n${passed}/${passed + failed} decision-registry tests passed.`);
process.exit(failed ? 1 : 0);
