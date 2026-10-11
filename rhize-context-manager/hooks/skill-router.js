#!/usr/bin/env node
'use strict';

// skill-router.js — map-driven skill suggestion hook (UserPromptSubmit).
//
// Replaces the keyword-grep skill-suggester.sh (retired 2026-08-09, see
// SOURCES.md / CHANGELOG). Ranks the submitted prompt against the compiled
// skill-map artifact's topic-tag/stack-tag edges and skill names instead of a
// fixed regex keyword list, so new skills route automatically once tagged —
// no hook edit required.
//
// TIER: T3 (advisory). Never blocks (always exit 0). Fails silently on any
// missing/unreadable/corrupt input — a missing map, a plugin installed
// without this repo's `generated/` dir, or a malformed prompt must never
// surface an error to the user or to Claude.
//
// CONTRACT: reads hook JSON from stdin, field "prompt" (not "user_prompt" —
// see skill-suggester.sh's history in git blame for why that distinction
// matters). additionalContext must be nested inside
// hookSpecificOutput.additionalContext to reach Claude; a top-level field or
// systemMessage alone would not.
//
// INDEX RESOLUTION (relationships v2, section 7 of the design doc): the
// primary data source is now the materialized `router` index, precomputed
// by build_skill_map.py/build_local_skill_map.py so this hook never walks
// doc.edges itself. Preference order, all under
// ~/.claude/context-manager/:
//   1. skill-map.indexes.resolved.json (static + local-overlay follows merge)
//   2. skill-map.indexes.json          (installed by `build_skill_map.py --install`)
// Neither present/parseable/missing a `router` section -> FALL BACK to the
// original map-scanning path below (readMap/route), so an older install that
// only shipped skill-map.{resolved,static}.json (no indexes file yet)
// degrades gracefully instead of going silent. Behavior is identical either
// way — the index only saves re-deriving signals from doc.edges per call.
//
// MAP RESOLUTION (fallback only):
//   1. skill-map.resolved.json (static + local overlay, once Phase 3 lands)
//   2. skill-map.static.json   (installed by `build_skill_map.py --install`)
// Neither present or parseable -> exit 0, no output.
//
// RANKING: tokenize the prompt into lowercase alnum words, plural-folded
// (route-core's normalizeWord(): `-ies` -> `-y`, trailing non-`ss` `-s`
// dropped; labels fold the same way). For every `skill` node, a
// topic-tag/stack-tag edge is a "tag signal" (weight 2) if every word of the
// tag's name is present among the prompt's tokens; the skill's own name is a
// "name signal" (weight 1) under the same all-words-present rule. A 3+-word
// name missing exactly one word adds a "name-partial" signal (weight 0.5),
// suppressed for the whole prompt whenever any skill's full name matched.
// Tag signals outweigh name signals, per the plan's "tag match > name match"
// rule. At least 2 DISTINCT signals must match for a skill to be considered
// at all, at least one of weight >= 1 — a single weak match must never emit
// (see plan's "Router noise" risk). Among qualifying skills, the highest
// total weight wins; ties break on skill id (deterministic, no randomness).
// All of this lives in route-core's shared matcher (scoreCandidates()).
//
// SKILL-FIT CO-SIGN (Laya earned authority, plan v3 §4.3): for a fired,
// non-explicit router suggestion the hook asks the local Laya server (literal
// loopback only, see lib/laya-client.js) which of the lexical top-5 skills (or
// none) fits the prompt. In mode `cosign`, in the treatment arm, a suggestion
// Laya does not independently choose is withheld; in every other case (mode
// `shadow`, the holdback arm, any Laya failure or deadline expiry, any
// exception) the precomputed incumbent payload is emitted unchanged. The
// payload is settled exactly once and flushed before any logging or exit, and
// one decision record (no prompt text) is appended per eligible prompt.
//
// BUDGET: <150ms warm without workflow opt-in or a reachable Laya; opt-in
// bridge deadline 4.5s; Laya probe + POST share one 800ms deadline (registry
// latencyBudgetMs). The host hook timeout must be >= 8s. The map is read
// synchronously once per invocation (and only for eligible prompts, for skill
// descriptions).

const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const os = require('os');
const { execFileSync } = require('child_process');
const { performance } = require('perf_hooks');

// Shared primitives (index/map reading, tokenize, scoring, logging) live in
// hooks/lib/route-core.js so agent-brief-router.js can reuse them without
// duplicating the ranking logic. Policy — thresholds, the one-suggestion
// cap, and message shaping (formatMatch below) — stays in this hook.
const {
  readIndexes,
  readMap,
  tokenize,
  formatSkillRef,
  formatSignalLabel,
  routeFromIndex,
  route,
  contextHash,
  logSuggestion,
  lexicalShortlist,
} = require(path.join(__dirname, 'lib', 'route-core.js'));
// The skill-fit layer is optional: if any of its modules cannot be loaded (a
// partially updated checkout, version skew) the hook behaves exactly like the
// legacy router instead of crashing.
let L = null;
try {
  const instrument = require(path.join(__dirname, 'lib', 'laya-instrument.js'));
  L = {
    buildChoiceRequest: instrument.buildChoiceRequest,
    canonicalJson: instrument.canonicalJson,
    sha256Hex: instrument.sha256Hex,
    INSTRUMENT: instrument.INSTRUMENT,
    td: require(path.join(__dirname, 'lib', 'typed-decisions.js')),
    readDecisionConfig: require(path.join(__dirname, 'lib', 'decision-registry.js')).readDecisionConfig,
    // Kept as a module object so callChoice is late-bound (a test preload can substitute the transport).
    client: require(path.join(__dirname, 'lib', 'laya-client.js')),
  };
} catch (_) { L = null; }

const DECISION = 'skill-fit';
const SKILL_ID = /^skill:[A-Za-z0-9_.\-/]+$/;
const MAX_RECORD_BYTES = 4096;
const SETTLE_MARGIN_MS = 50; // settle-once backstop fires this long after the Laya deadline
const HARD_EXIT_MARGIN_MS = 2000; // last-resort exit if a flush or socket never completes
const NON_LAYA_HARD_EXIT_MS = 2000;
const LAYA_STATUSES = ['ok', 'timeout', 'unavailable', 'invalid', 'identity_failed', 'redirect_refused'];

function formatMatch(match) {
  if (!match) return null;
  const ref = formatSkillRef(match.skillId);
  if (!ref) return null;
  const why = match.signals.map(formatSignalLabel).join(', ');
  return `Consider the ${ref} skill (matches ${why})`;
}

function payloadFor(message) {
  if (!message) return null;
  return JSON.stringify({
    hookSpecificOutput: {
      hookEventName: 'UserPromptSubmit',
      additionalContext: message,
    },
  }) + '\n';
}

// Reads stdin, ranks the prompt against the map, and returns everything main()
// needs to settle exactly once: the COMPLETE incumbent payload (the bytes
// today's hook would write, or null), the payload without the router
// suggestion (used only by a cosign suppression), and the facts the Laya
// co-sign and the logs need. Returns null when there is nothing to do. Throws
// on any unreadable/corrupt input; main()'s try/catch turns that into the
// same silent no-op.
//
// Tries the materialized router index first (routeFromIndex); only when no
// indexes file is present/parseable does this fall back to the original
// map-scanning path (readMap/route) — see the INDEX RESOLUTION note above.
function prepare() {
  const ts = new Date().toISOString();
  const raw = fs.readFileSync(0, 'utf8');
  const data = JSON.parse(raw);
  const prompt = typeof data.prompt === 'string' ? data.prompt : '';
  const sessionId = typeof data.session_id === 'string' ? data.session_id : null;
  if (!prompt) return null;

  let workflowMessage = null;
  let workflowHandled = false;
  // One shared selector owns opted-in workflow decisions. Both the legacy
  // router and packaged hook use its atomic receipt; configuration alone
  // never suppresses advice. A failed bridge falls back to this router.
  try {
    const root = process.env.XDG_DATA_HOME || path.join(os.homedir(), '.local', 'share');
    const cfgPath = path.join(root, 'rhize', 'workflow-selection', 'config.json');
    const cfg = JSON.parse(fs.readFileSync(cfgPath, 'utf8'));
    if (cfg.schemaVersion === 1 && cfg.enabled === true) {
      const output = execFileSync('python3', [path.join(__dirname, '..', 'scripts', 'workflow_selection.py'), 'hook', '--router-bridge'], {
        input: raw, encoding: 'utf8', timeout: 4500, maxBuffer: 16384, stdio: ['pipe','pipe','ignore'],
      });
      const bridge = JSON.parse(output);
      workflowHandled = bridge.handled === true;
      workflowMessage = bridge.hookOutput?.hookSpecificOutput?.additionalContext || null;
    }
  } catch (_) { /* missing/untrusted/unavailable selector: preserve old routing */ }

  const promptTokens = tokenize(prompt);
  const ctxHash = contextHash(prompt);

  const routerIndex = readIndexes();
  const match = routerIndex
    ? routeFromIndex(routerIndex, promptTokens, prompt)
    : (() => {
        const doc = readMap();
        return doc ? route(doc, promptTokens, prompt) : null;
      })();

  const overlaps = workflowHandled && match && /\/(?:rhize-content-engine|content-engine)$/.test(match.skillId) && !/\becc\b/i.test(prompt);
  const routerRef = overlaps ? null : formatMatch(match);
  const incumbentMessage = [workflowMessage, routerRef].filter(Boolean).join(' ') || null;
  const suppressedMessage = [workflowMessage].filter(Boolean).join(' ') || null;

  const explicit = Boolean(match) && match.signals.some((signal) => signal.label === 'explicit skill request');
  return {
    ts, prompt, sessionId, promptTokens, contextHash: ctxHash, routerIndex, match,
    incumbentPayload: payloadFor(incumbentMessage),
    incumbentShown: incumbentMessage && routerRef && match ? match.skillId : null,
    suppressedPayload: payloadFor(suppressedMessage),
    eligible: Boolean(match) && Boolean(routerIndex) && !explicit,
  };
}

// Builds the Laya request for an eligible prompt. Returns null (no Laya call,
// no record) when the mode is off, the incumbent id cannot be sent, or the
// request cannot be built; throws are caught by the caller with the same effect.
function planLaya(state) {
  if (!L) return null;
  const config = L.readDecisionConfig(DECISION);
  if (config.mode === 'off' || !config.endpoint || !config.model) return null;
  const incumbentId = state.match.skillId;
  if (!SKILL_ID.test(incumbentId)) return null;
  const shortlist = lexicalShortlist(state.routerIndex, state.promptTokens, incumbentId, 5).filter((id) => SKILL_ID.test(id));
  if (!shortlist.includes(incumbentId)) return null;

  const wanted = new Set(shortlist);
  const descriptions = new Map();
  try {
    const doc = readMap();
    if (doc) {
      for (const node of doc.nodes) {
        if (node && node.kind === 'skill' && wanted.has(node.id) && typeof node.description === 'string') {
          descriptions.set(node.id, node.description);
        }
      }
    }
  } catch (_) { /* descriptions are optional */ }
  const built = L.buildChoiceRequest(state.prompt, shortlist.map((skillId) => ({
    skillId, description: descriptions.has(skillId) ? descriptions.get(skillId) : null,
  })));

  const sessionHash = L.sha256Hex(state.sessionId || '');
  const promptHash = L.sha256Hex(state.prompt);
  const arm = L.td.armFor(sessionHash, promptHash, config.holdback);
  const propensity = arm === 'holdback' ? config.holdback : 1 - config.holdback;
  return { config, shortlist, built, sessionHash, promptHash, arm, propensity };
}

// Coerces whatever the transport returned into a record-safe Laya outcome.
function normalizeLaya(raw, plan) {
  const out = { status: 'unavailable', choice: null, probabilities: null, latencyMs: null, truncated: plan.built.truncated };
  if (!raw || typeof raw !== 'object' || !LAYA_STATUSES.includes(raw.status)) return out;
  if (typeof raw.latencyMs === 'number' && Number.isFinite(raw.latencyMs) && raw.latencyMs >= 0) out.latencyMs = raw.latencyMs;
  if (raw.status !== 'ok') { out.status = raw.status; return out; }
  const probs = raw.probabilities;
  const choiceOk = raw.choice === 'none' || plan.shortlist.includes(raw.choice);
  const probsOk = Array.isArray(probs) && probs.length === plan.shortlist.length + 1
    && probs.every((p) => typeof p === 'number' && Number.isFinite(p) && p >= 0 && p <= 1);
  if (!choiceOk || !probsOk) { out.status = 'invalid'; return out; }
  out.status = 'ok';
  out.choice = raw.choice;
  out.probabilities = probs.slice();
  return out;
}

// ---------------------------------------------------------------- persistence
// Everything below runs only AFTER the hook payload has been flushed, each part
// in its own try/catch: a persistence failure can never alter the output.

function ensurePrivateDir(dir) {
  for (let attempt = 0; attempt < 2; attempt += 1) {
    let stat = null;
    try { stat = fs.lstatSync(dir); } catch (err) { if (!err || err.code !== 'ENOENT') throw err; }
    if (stat) {
      if (stat.isSymbolicLink() || !stat.isDirectory()) throw new Error('unsafe typed-decision directory');
      return;
    }
    try { fs.mkdirSync(dir, { mode: 0o700 }); return; } catch (err) { if (!err || err.code !== 'EEXIST') throw err; }
  }
  throw new Error('typed-decision directory race');
}

function appendRecord(record) {
  const json = L.canonicalJson(record);
  if (Buffer.byteLength(json, 'utf8') >= MAX_RECORD_BYTES) return false; // records stay under 4096 bytes
  const root = L.td.defaultRoot();
  const file = L.td.recordsPath(root, DECISION, record.ts);
  fs.mkdirSync(path.dirname(root), { recursive: true, mode: 0o700 });
  ensurePrivateDir(root);
  ensurePrivateDir(path.join(root, DECISION));
  ensurePrivateDir(path.dirname(file));
  let stat = null;
  try { stat = fs.lstatSync(file); } catch (err) { if (!err || err.code !== 'ENOENT') throw err; }
  if (stat && (stat.isSymbolicLink() || !stat.isFile())) throw new Error('unsafe typed-decision file');
  const flags = fs.constants.O_WRONLY | fs.constants.O_APPEND | fs.constants.O_CREAT
    | (fs.constants.O_NOFOLLOW || 0) | (fs.constants.O_NONBLOCK || 0); // never block on a swapped-in FIFO
  const fd = fs.openSync(file, flags, 0o600);
  try { fs.writeSync(fd, json + '\n'); } finally { fs.closeSync(fd); }
  return true;
}

function readLayaRevision() {
  try {
    const doc = JSON.parse(fs.readFileSync(path.join(L.td.defaultRoot(), 'laya-runtime.json'), 'utf8'));
    if (doc && typeof doc.revision === 'string' && /^[A-Za-z0-9._-]{1,80}$/.test(doc.revision)) return doc.revision;
  } catch (_) { /* optional */ }
  return 'unknown';
}

function routerSourceSha256() {
  const lib = path.join(__dirname, 'lib');
  const hash = crypto.createHash('sha256');
  for (const file of [path.join(lib, 'route-core.js'), __filename, path.join(lib, 'laya-instrument.js')]) {
    hash.update(fs.readFileSync(file));
  }
  return hash.digest('hex');
}

function buildRecord(state, plan, laya, shown) {
  return {
    schema: L.td.RECORD_SCHEMA,
    decision: DECISION,
    decisionId: crypto.randomBytes(16).toString('hex'),
    occurrenceKey: L.td.occurrenceKey(plan.sessionHash, plan.promptHash, state.ts),
    ts: state.ts,
    host: process.env.RHIZE_HOST === 'codex' ? 'codex' : 'claude',
    basis: 'live',
    sourceStratum: 'fired',
    sessionHash: plan.sessionHash,
    promptHash: plan.promptHash,
    promptLengthBucket: plan.built.promptLengthBucket,
    routerSourceSha256: routerSourceSha256(),
    indexSha256: L.sha256Hex(JSON.stringify(state.routerIndex)),
    registryRevision: plan.config.registryRevision,
    policy: L.td.POLICY_COSIGN,
    policySha256: L.td.policySha256(),
    instrument: L.INSTRUMENT,
    instrumentSha256: plan.built.instrumentSha256,
    criteriaSha256: plan.built.criteriaSha256,
    layaRevision: readLayaRevision(),
    mode: plan.config.mode,
    arm: plan.arm,
    propensity: plan.propensity,
    incumbent: { skillId: state.match.skillId, score: state.match.score },
    shortlist: plan.shortlist,
    laya: {
      status: laya.status, choice: laya.choice, probabilities: laya.probabilities,
      latencyMs: laya.latencyMs, truncated: laya.truncated,
    },
    emitted: shown,
  };
}

function persist(state, plan, laya, emitted, shown) {
  try {
    const typed = plan && laya ? {
      typed_mode: plan.config.mode,
      typed_arm: plan.arm,
      typed_status: laya.status,
      typed_agrees: laya.status === 'ok' ? laya.choice === state.match.skillId : null,
    } : { typed_mode: null, typed_arm: null, typed_status: null, typed_agrees: null };
    if (emitted) {
      logSuggestion({
        ts: state.ts,
        session_id: state.sessionId,
        hook: 'router',
        suggested: shown,
        context_hash: state.contextHash,
        ...typed,
      });
    } else if (Math.random() < 1 / 20) {
      logSuggestion({
        ts: state.ts,
        session_id: state.sessionId,
        hook: 'router',
        suggested: null,
        context_hash: state.contextHash,
        ...(plan && laya ? typed : {}),
      });
    }
  } catch (_) { /* fail-silent */ }
  try {
    if (plan && laya) appendRecord(buildRecord(state, plan, laya, shown));
  } catch (_) { /* fail-silent */ }
}

// ---------------------------------------------------------------- settle once

function emit(payload) {
  return new Promise((resolve) => {
    if (!payload) { resolve(); return; }
    try { process.stdout.write(payload, () => resolve()); } catch (_) { resolve(); }
  });
}

async function finalize(state, plan, laya) {
  let payload = state.incumbentPayload;
  let shown = state.incumbentShown;
  try {
    if (plan && laya && plan.config.mode === 'cosign' && plan.arm === 'treatment'
        && laya.status === 'ok' && laya.choice !== state.match.skillId) {
      payload = state.suppressedPayload;
      shown = null;
    }
  } catch (_) { payload = state.incumbentPayload; shown = state.incumbentShown; }
  await emit(payload); // flush BEFORE any persistence or exit
  persist(state, plan, laya, Boolean(payload), shown);
}

let fatalHandler = null;
function onFatal() {
  try { if (fatalHandler) { fatalHandler(); return; } } catch (_) { /* fall through */ }
  process.exit(0);
}

async function main() {
  process.stdout.on('error', () => { /* EPIPE etc.: never crash the hook */ });
  process.on('uncaughtException', onFatal);
  process.on('unhandledRejection', onFatal);

  let state = null;
  try {
    state = prepare();
  } catch (_err) {
    state = null; // fail-silent contract: never surface an error to the user or Claude
  }
  if (!state) { process.exit(0); return; }

  let plan = null;
  if (state.eligible) {
    try { plan = planLaya(state); } catch (_) { plan = null; }
  }

  let settled = false;
  let backstop = null;
  let hardExit = null;
  const settleOnce = (laya) => {
    if (settled) return; // a late Laya completion after settlement is ignored
    settled = true;
    if (backstop) clearTimeout(backstop);
    finalize(state, plan, laya)
      .catch(() => {})
      .then(() => { if (hardExit) clearTimeout(hardExit); process.exit(0); });
  };

  if (!plan) {
    // Nothing to ask Laya (ineligible prompt, mode off, or no buildable request): emit the incumbent.
    fatalHandler = () => settleOnce(null);
    hardExit = setTimeout(() => process.exit(0), NON_LAYA_HARD_EXIT_MS);
    settleOnce(null);
    return;
  }

  const budget = plan.config.latencyBudgetMs;
  const startedAt = performance.now();
  const deadlineAt = startedAt + budget;
  const elapsed = () => Math.max(0, Math.round((performance.now() - startedAt) * 10) / 10);
  // Plain literals (no helper that could throw) for every fallback path.
  const failed = (status) => ({
    status, choice: null, probabilities: null, latencyMs: elapsed(), truncated: plan.built.truncated === true,
  });
  fatalHandler = () => settleOnce(failed('unavailable'));
  hardExit = setTimeout(() => process.exit(0), budget + SETTLE_MARGIN_MS + HARD_EXIT_MARGIN_MS);
  backstop = setTimeout(() => settleOnce(failed('timeout')), budget + SETTLE_MARGIN_MS);

  let outcome;
  try {
    outcome = normalizeLaya(await L.client.callChoice({
      endpoint: plan.config.endpoint,
      model: plan.config.model,
      request: plan.built.request,
      keyMap: plan.built.keyMap,
      deadlineAt,
    }), plan);
  } catch (_) {
    outcome = failed('unavailable');
  }
  settleOnce(outcome);
}

main();
