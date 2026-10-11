'use strict';
// decision-registry.js: READ-ONLY reader for the typed-decision registry and its
// machine-local state (plan v3 §4.1). The Node hook only ever reads; all state
// writes go through scripts/typed_decisions/decision_registry.py.
//
//   shipped default : ../../catalog/decision-registry.json (validated like
//                     contract.validate_registry)
//   machine state   : <defaultRoot()>/registry-state.json (validated like
//                     contract.validate_state against the shipped registry)
//
// Resolution rules (never throws, never writes):
//   registry unreadable / invalid            -> mode 'off' (no Laya at all)
//   state file missing                       -> registry defaultMode, registryRevision 0
//   state corrupt / unreadable / invalid     -> mode 'shadow', registryRevision 0
//   state valid, entry present               -> entry.mode / entry.pinned, revision = state.revision
//   state valid, entry absent                -> registry defaultMode, revision = state.revision
//   state says cosign but its bound policySha256 / instrumentSha256 differ from
//   this code's (the gate was passed for different bits; plan §5 I8)
//                                            -> mode 'shadow' (revision and pin kept)
// RHIZE_LAYA_ENDPOINT overrides the endpoint only when it is a literal loopback
// http URL (tests use it to point at a random-port fake server).
//
// The validators below mirror scripts/typed_decisions/contract.py
// (validate_registry / validate_state). Parity is exercised by
// tests/skill-map/test_decision_registry.js against the shared registry fixtures.
const fs = require('fs');
const path = require('path');
const { INSTRUMENT, instrumentSha256 } = require('./laya-instrument.js');
const { POLICIES, policySha256, defaultRoot } = require('./typed-decisions.js');

const REGISTRY_SCHEMA_VERSION = 1;
const STATE_SCHEMA_VERSION = 1;
const DECISIONS = ['skill-fit', 'workflow-fit'];
const MODES = ['off', 'shadow', 'cosign'];
const TIERS = ['advisory', 'workflow', 'critical'];
const MAX_FILE_BYTES = 1 << 20;

const REGISTRY_ENTRY_KEYS = ['tier', 'defaultMode', 'reachableModes', 'incumbent', 'deployablePolicy', 'instrument',
  'holdback', 'latencyBudgetMs', 'lambda', 'endpoint', 'model', 'gates'];
const PROMOTE_GATE_KEYS = ['cohortSize', 'maxPerSession', 'alphaBase', 'maxAmbiguousShare', 'maxUnavailableShare'];
const DEMOTE_GATE_KEYS = ['minLabeled', 'alpha', 'maxUnavailableShare', 'operationalWindowDays', 'latencyReportOnlyDays'];
const STATE_ENTRY_KEYS = ['mode', 'pinned', 'since', 'reason', 'policySha256', 'instrumentSha256', 'layaRevision',
  'cohortId'];

const HEX64 = /^[0-9a-f]{64}$/;
const HEX32 = /^[0-9a-f]{32}$/;
const TS = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z$/;
const REVISION = /^[A-Za-z0-9._-]{1,80}$/;
const REASON = /^[a-z_]{1,40}$/;
const LOOPBACK_ENDPOINT = /^http:\/\/(127\.0\.0\.1|\[::1\]):(\d{1,5})$/;

function isLoopbackEndpoint(value) {
  if (typeof value !== 'string') return false;
  const m = LOOPBACK_ENDPOINT.exec(value);
  if (!m) return false;
  const port = Number(m[2]);
  return port >= 1 && port <= 65535;
}

// ---------------------------------------------------------------- validators

function fail(reason) { throw new Error(reason); }
function isObject(v) { return v !== null && typeof v === 'object' && !Array.isArray(v); }
function keysEqual(obj, expected, name) {
  if (!isObject(obj)) fail(`${name} must be an object`);
  const keys = Object.keys(obj);
  if (keys.length !== expected.length || keys.some((k) => !expected.includes(k))) fail(`${name} keys mismatch`);
}
function enumOf(value, allowed, field) { if (!allowed.includes(value)) fail(`invalid ${field}`); }
function numberOf(value, field, lo, hi, nullable) {
  if (value === null && nullable) return;
  if (typeof value !== 'number' || !Number.isFinite(value)) fail(`invalid ${field}`);
  if ((lo !== undefined && value < lo) || (hi !== undefined && value > hi)) fail(`invalid ${field}`);
}
function intOf(value, field, lo) {
  if (typeof value !== 'number' || !Number.isInteger(value) || (lo !== undefined && value < lo)) fail(`invalid ${field}`);
}

function validateRegistry(registry) {
  keysEqual(registry, ['schemaVersion', 'decisions'], 'registry');
  if (registry.schemaVersion !== REGISTRY_SCHEMA_VERSION) fail('invalid schemaVersion');
  const decisions = registry.decisions;
  if (!isObject(decisions) || Object.keys(decisions).length === 0) fail('invalid decisions');
  for (const [decisionId, entry] of Object.entries(decisions)) {
    enumOf(decisionId, DECISIONS, 'decision id');
    keysEqual(entry, REGISTRY_ENTRY_KEYS, `registry entry ${decisionId}`);
    enumOf(entry.tier, TIERS, 'tier');
    const reachable = entry.reachableModes;
    if (!Array.isArray(reachable) || reachable.length === 0 || new Set(reachable).size !== reachable.length) {
      fail('invalid reachableModes');
    }
    for (const mode of reachable) enumOf(mode, MODES, 'reachableModes');
    enumOf(entry.defaultMode, reachable, 'defaultMode');
    if (entry.tier === 'critical' && reachable.some((m) => m !== 'off' && m !== 'shadow')) {
      fail('critical decisions are shadow-only');
    }
    if (reachable.includes('cosign')) {
      if (entry.tier !== 'advisory') fail('only advisory decisions may reach cosign');
      enumOf(entry.deployablePolicy, Object.keys(POLICIES), 'deployablePolicy');
      if (entry.instrument !== INSTRUMENT) fail('cosign requires the laya-choice-v1 instrument');
      if (!isLoopbackEndpoint(entry.endpoint)) fail('endpoint must be a literal loopback http address');
      if (entry.model !== 'typed-decisions') fail('invalid model');
      numberOf(entry.holdback, 'holdback', 0, 0.5);
      intOf(entry.latencyBudgetMs, 'latencyBudgetMs', 100);
      if (entry.latencyBudgetMs > 5000) fail('invalid latencyBudgetMs');
      numberOf(entry.lambda, 'lambda', 0);
      if (entry.lambda === 0) fail('invalid lambda');
      const gates = entry.gates;
      keysEqual(gates, ['promote', 'demote'], 'gates');
      keysEqual(gates.promote, PROMOTE_GATE_KEYS, 'gates.promote');
      keysEqual(gates.demote, DEMOTE_GATE_KEYS, 'gates.demote');
      intOf(gates.promote.cohortSize, 'cohortSize', 20);
      intOf(gates.promote.maxPerSession, 'maxPerSession', 1);
      numberOf(gates.promote.alphaBase, 'alphaBase', 0, 0.2);
      for (const key of ['maxAmbiguousShare', 'maxUnavailableShare']) numberOf(gates.promote[key], key, 0, 1);
      intOf(gates.demote.minLabeled, 'minLabeled', 10);
      numberOf(gates.demote.alpha, 'demote.alpha', 0, 0.5);
      numberOf(gates.demote.maxUnavailableShare, 'demote.maxUnavailableShare', 0, 1);
      intOf(gates.demote.operationalWindowDays, 'operationalWindowDays', 1);
      intOf(gates.demote.latencyReportOnlyDays, 'latencyReportOnlyDays', 0);
    } else {
      for (const key of ['deployablePolicy', 'instrument', 'holdback', 'latencyBudgetMs', 'lambda', 'endpoint',
        'model', 'gates']) {
        if (entry[key] !== null) fail(`${key} must be null unless cosign is reachable`);
      }
    }
    if (typeof entry.incumbent !== 'string' || !REVISION.test(entry.incumbent)) fail('invalid incumbent');
  }
  return registry;
}

function validateState(state, registry) {
  keysEqual(state, ['schemaVersion', 'revision', 'updatedAt', 'decisions'], 'state');
  if (state.schemaVersion !== STATE_SCHEMA_VERSION) fail('invalid schemaVersion');
  intOf(state.revision, 'revision', 1);
  if (typeof state.updatedAt !== 'string' || !TS.test(state.updatedAt)) fail('invalid updatedAt');
  if (!isObject(state.decisions)) fail('invalid decisions');
  for (const [decisionId, entry] of Object.entries(state.decisions)) {
    if (!Object.prototype.hasOwnProperty.call(registry.decisions, decisionId)) fail('unknown decision in state');
    keysEqual(entry, STATE_ENTRY_KEYS, `state entry ${decisionId}`);
    enumOf(entry.mode, registry.decisions[decisionId].reachableModes, 'mode');
    if (typeof entry.pinned !== 'boolean') fail('invalid pinned');
    if (typeof entry.since !== 'string' || !TS.test(entry.since)) fail('invalid since');
    if (typeof entry.reason !== 'string' || !REASON.test(entry.reason)) fail('invalid reason');
    for (const field of ['policySha256', 'instrumentSha256']) {
      if (entry[field] !== null && (typeof entry[field] !== 'string' || !HEX64.test(entry[field]))) fail(`invalid ${field}`);
    }
    if (entry.layaRevision !== null && (typeof entry.layaRevision !== 'string' || !REVISION.test(entry.layaRevision))) {
      fail('invalid layaRevision');
    }
    if (entry.cohortId !== null && (typeof entry.cohortId !== 'string' || !HEX32.test(entry.cohortId))) {
      fail('invalid cohortId');
    }
    if (entry.mode === 'cosign' && (entry.policySha256 === null || entry.instrumentSha256 === null)) {
      fail('cosign state must bind policy and instrument hashes');
    }
  }
  return state;
}

// ---------------------------------------------------------------- reading

function readJson(file) {
  // Returns {status: 'ok', value} | {status: 'missing'} | {status: 'bad'}.
  // lstat: a symlinked state/registry file is 'bad' (the Python reader treats it as corrupt too).
  let stat;
  try {
    stat = fs.lstatSync(file);
  } catch (err) {
    return { status: err && err.code === 'ENOENT' ? 'missing' : 'bad' };
  }
  try {
    if (!stat.isFile() || stat.size > MAX_FILE_BYTES) return { status: 'bad' };
    return { status: 'ok', value: JSON.parse(fs.readFileSync(file, 'utf8')) };
  } catch (_err) {
    return { status: 'bad' };
  }
}

function offConfig() {
  return {
    mode: 'off', pinned: false, holdback: null, latencyBudgetMs: null, endpoint: null, model: null,
    lambda: null, registryRevision: 0, deployablePolicy: null,
  };
}

function defaultRegistryPath() {
  return path.join(__dirname, '..', '..', 'catalog', 'decision-registry.json');
}

function defaultStatePath() {
  return path.join(defaultRoot(), 'registry-state.json');
}

// Current Laya checkpoint revision from <root>/laya-runtime.json ({"revision": ...});
// 'unknown' when the file is missing or invalid. Mirrors records.laya_revision().
function currentLayaRevision(runtimePath) {
  const loaded = readJson(runtimePath || path.join(defaultRoot(), 'laya-runtime.json'));
  if (loaded.status === 'ok' && loaded.value && typeof loaded.value.revision === 'string'
      && /^[A-Za-z0-9._-]{1,80}$/.test(loaded.value.revision)) return loaded.value.revision;
  return 'unknown';
}

function readDecisionConfig(decisionId, options = {}) {
  try {
    const registryPath = options.registryPath || defaultRegistryPath();
    const statePath = options.statePath || defaultStatePath();
    const loaded = readJson(registryPath);
    if (loaded.status !== 'ok') return offConfig();
    const registry = validateRegistry(loaded.value);
    const entry = registry.decisions[decisionId];
    if (!entry) return offConfig();

    let mode = entry.defaultMode;
    let pinned = false;
    let registryRevision = 0;
    const stateFile = readJson(statePath);
    if (stateFile.status === 'bad') {
      mode = 'shadow';
    } else if (stateFile.status === 'ok') {
      try {
        const state = validateState(stateFile.value, registry);
        registryRevision = state.revision;
        const stateEntry = state.decisions[decisionId];
        if (stateEntry) {
          mode = stateEntry.mode;
          pinned = stateEntry.pinned;
          // A promotion is valid only for the policy and instrument it was tested with.
          if (mode === 'cosign' && (stateEntry.policySha256 !== policySha256(entry.deployablePolicy)
              || stateEntry.instrumentSha256 !== instrumentSha256())) {
            mode = 'shadow';
          }
          // ... and for the Laya checkpoint it was tested against (laya-runtime.json).
          if (mode === 'cosign' && stateEntry.layaRevision !== null
              && stateEntry.layaRevision !== currentLayaRevision(options.layaRuntimePath)) {
            mode = 'shadow';
          }
        }
      } catch (_err) {
        mode = 'shadow';
        pinned = false;
        registryRevision = 0;
      }
    }
    // A reachable-modes registry could in principle list only 'off'; 'shadow'
    // fallbacks above are never applied to a decision that cannot shadow.
    if (!entry.reachableModes.includes(mode)) mode = entry.reachableModes.includes('off') ? 'off' : entry.defaultMode;

    let endpoint = entry.endpoint;
    const override = process.env.RHIZE_LAYA_ENDPOINT;
    if (endpoint !== null && isLoopbackEndpoint(override)) endpoint = override;

    return {
      mode, pinned, holdback: entry.holdback, latencyBudgetMs: entry.latencyBudgetMs, endpoint,
      model: entry.model, lambda: entry.lambda, registryRevision, deployablePolicy: entry.deployablePolicy,
    };
  } catch (_err) {
    return offConfig();
  }
}

module.exports = {
  readDecisionConfig, validateRegistry, validateState, isLoopbackEndpoint, defaultRegistryPath, defaultStatePath,
  currentLayaRevision,
};
