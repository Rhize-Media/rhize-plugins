#!/usr/bin/env node
'use strict';

// test_router.js — exercises rhize-context-manager/hooks/skill-router.js
// (Phase 2 of .claude/plans/skill-map-graph-substrate.md, refactored in
// relationships v2 — see the design doc's section 7 — to read the
// materialized `router` index first) end-to-end via spawnSync, so it
// validates exactly what the hook harness invokes: stdin in, stdout/exit
// code out.
//
// Every case runs with HOME pointed at a temp directory — never the real
// ~/.claude — so the router's resolution (~/.claude/context-manager/
// skill-map.indexes.{resolved,}.json, then skill-map.{resolved,static}.json)
// reads only the fixture this test wrote.
//
// The primary cases below write only an indexes fixture, exercising the
// index-backed `routeFromIndex()` path exclusively. The dedicated "fallback"
// case at the bottom writes only a static MAP fixture (no indexes file at
// all) to prove the original map-scanning `route()` path still works
// unaided — the degrade path for an older install that hasn't rebuilt its
// indexes file yet.

const assert = require('assert');
const crypto = require('crypto');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const ROUTER_PATH = path.join(REPO_ROOT, 'rhize-context-manager', 'hooks', 'skill-router.js');
const FIXTURE_PATH = path.join(__dirname, 'fixtures', 'valid-map.json');
const INDEX_FIXTURE_PATH = path.join(__dirname, 'fixtures', 'indexes-valid-map.json');
const INDEX_EXTENDS_FIXTURE_PATH = path.join(
  __dirname,
  'fixtures',
  'indexes-valid-map-extends.json'
);

function withTempHome(fn) {
  const tmpHome = fs.mkdtempSync(path.join(os.tmpdir(), 'skill-router-test-'));
  try {
    return fn(tmpHome);
  } finally {
    fs.rmSync(tmpHome, { recursive: true, force: true });
  }
}

function writeStaticMap(tmpHome, contents) {
  const dir = path.join(tmpHome, '.claude', 'context-manager');
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, 'skill-map.static.json'), contents);
}

function writeIndexes(tmpHome, contents) {
  const dir = path.join(tmpHome, '.claude', 'context-manager');
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, 'skill-map.indexes.json'), contents);
}

function runRouter(tmpHome, prompt) {
  const result = spawnSync(process.execPath, [ROUTER_PATH], {
    input: JSON.stringify({ prompt }),
    env: { ...process.env, HOME: tmpHome },
    encoding: 'utf8',
    timeout: 5000,
  });
  return result;
}

// Variant that also sets session_id (for suggestion-log assertions) and
// accepts extra env vars, notably RHIZE_SUGGESTION_LOG.
function runRouterFull(tmpHome, prompt, sessionId, extraEnv) {
  const result = spawnSync(process.execPath, [ROUTER_PATH], {
    input: JSON.stringify({ prompt, session_id: sessionId }),
    env: { ...process.env, HOME: tmpHome, ...extraEnv },
    encoding: 'utf8',
    timeout: 5000,
  });
  return result;
}

let failures = 0;

function check(name, fn) {
  try {
    fn();
    console.log(`PASS ${name}`);
  } catch (err) {
    failures += 1;
    console.error(`FAIL ${name}`);
    console.error(err && err.stack ? err.stack : err);
  }
}

// (a) [index path] A prompt matching a tagged skill on 2+ signals must emit
// exactly one suggestion. The fixture tags
// skill:rhize-context-manager/graphify with tag:topic/context and
// tag:stack/git — a prompt containing both words as whole tokens should
// fire. Only an indexes fixture is written (no static map at all), so this
// exercises routeFromIndex() exclusively.
check('[index] matched prompt emits exactly one suggestion', () => {
  withTempHome((tmpHome) => {
    writeIndexes(tmpHome, fs.readFileSync(INDEX_FIXTURE_PATH, 'utf8'));
    const result = runRouter(tmpHome, 'help me get git and context tooling set up');
    assert.strictEqual(result.status, 0, `exit code: ${result.status}, stderr: ${result.stderr}`);
    const stdout = result.stdout.trim();
    assert.ok(stdout.length > 0, 'expected non-empty stdout');
    const lines = stdout.split('\n').filter(Boolean);
    assert.strictEqual(lines.length, 1, `expected exactly one line, got ${lines.length}`);
    const parsed = JSON.parse(lines[0]);
    const ctx = parsed.hookSpecificOutput && parsed.hookSpecificOutput.additionalContext;
    assert.ok(ctx, 'expected hookSpecificOutput.additionalContext');
    assert.strictEqual(
      ctx,
      'Consider the rhize-context-manager:graphify skill (matches context, git)'
    );
  });
});

// (b) [index path] A prompt with no qualifying match (or only a single weak
// signal) must exit 0 with empty output.
check('[index] unmatched prompt emits nothing and exits 0', () => {
  withTempHome((tmpHome) => {
    writeIndexes(tmpHome, fs.readFileSync(INDEX_FIXTURE_PATH, 'utf8'));
    const result = runRouter(tmpHome, 'what is the weather like today');
    assert.strictEqual(result.status, 0, `exit code: ${result.status}, stderr: ${result.stderr}`);
    assert.strictEqual(result.stdout.trim(), '', 'expected empty stdout');
  });
});

// (c) A corrupt indexes file (and no static map available at all) must fall
// back to readMap()/route(), find nothing, and fail silently: exit 0, no
// output, no exception surfaced. Exercises the corrupt-index-degrades-to-
// fallback path end to end.
check('corrupt indexes file falls back and emits nothing (exit 0)', () => {
  withTempHome((tmpHome) => {
    const dir = path.join(tmpHome, '.claude', 'context-manager');
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(path.join(dir, 'skill-map.indexes.json'), '{ this is not valid JSON ');
    const result = runRouter(tmpHome, 'help me get git and context tooling set up');
    assert.strictEqual(result.status, 0, `exit code: ${result.status}, stderr: ${result.stderr}`);
    assert.strictEqual(result.stdout.trim(), '', 'expected empty stdout');
  });
});

// (d) No indexes or map installed at all (missing/unreadable everywhere)
// must also fail silently.
check('missing indexes and map emits nothing and exits 0', () => {
  withTempHome((tmpHome) => {
    const result = runRouter(tmpHome, 'help me get git and context tooling set up');
    assert.strictEqual(result.status, 0, `exit code: ${result.status}, stderr: ${result.stderr}`);
    assert.strictEqual(result.stdout.trim(), '', 'expected empty stdout');
  });
});

// (e) [index path] Extends tie-break: a base skill and its extender both
// qualify with equal score. Plain alphabetical tie-break would pick the base
// ("context-fundamentals" < "context-optimization"), but the extender must
// win because it's the more specific skill (extender score >= base score).
check('[index] extends tie-break: extender wins over its base on equal score', () => {
  withTempHome((tmpHome) => {
    writeIndexes(tmpHome, fs.readFileSync(INDEX_EXTENDS_FIXTURE_PATH, 'utf8'));
    const result = runRouter(tmpHome, 'help me get context and git tooling set up');
    assert.strictEqual(result.status, 0, `exit code: ${result.status}, stderr: ${result.stderr}`);
    const stdout = result.stdout.trim();
    assert.ok(stdout.length > 0, 'expected non-empty stdout');
    const lines = stdout.split('\n').filter(Boolean);
    assert.strictEqual(lines.length, 1, `expected exactly one line, got ${lines.length}`);
    const parsed = JSON.parse(lines[0]);
    const ctx = parsed.hookSpecificOutput && parsed.hookSpecificOutput.additionalContext;
    assert.ok(ctx, 'expected hookSpecificOutput.additionalContext');
    assert.strictEqual(
      ctx,
      'Consider the rhize-context-manager:context-optimization skill (matches context, git)'
    );
  });
});

// (f) [fallback path, explicit] With NO indexes file present at all (only
// the legacy static map), the original map-scanning route() path must
// reproduce the exact same result as case (a) above.
check('[fallback] no indexes file: map-scan path still matches', () => {
  withTempHome((tmpHome) => {
    writeStaticMap(tmpHome, fs.readFileSync(FIXTURE_PATH, 'utf8'));
    const result = runRouter(tmpHome, 'help me get git and context tooling set up');
    assert.strictEqual(result.status, 0, `exit code: ${result.status}, stderr: ${result.stderr}`);
    const stdout = result.stdout.trim();
    assert.ok(stdout.length > 0, 'expected non-empty stdout');
    const lines = stdout.split('\n').filter(Boolean);
    assert.strictEqual(lines.length, 1, `expected exactly one line, got ${lines.length}`);
    const parsed = JSON.parse(lines[0]);
    const ctx = parsed.hookSpecificOutput && parsed.hookSpecificOutput.additionalContext;
    assert.ok(ctx, 'expected hookSpecificOutput.additionalContext');
    assert.strictEqual(
      ctx,
      'Consider the rhize-context-manager:graphify skill (matches context, git)'
    );
  });
});

// --- suggestion-log assertions (RHIZE_SUGGESTION_LOG override) ---

const MATCHED_PROMPT = 'help me get git and context tooling set up';
const UNMATCHED_PROMPT = 'what is the weather like today';

// (g) A firing suggestion must append exactly one log line matching the
// pinned schema — and must never leak the raw prompt text.
check('[logging] suggestion fires: log line matches pinned schema', () => {
  withTempHome((tmpHome) => {
    writeIndexes(tmpHome, fs.readFileSync(INDEX_FIXTURE_PATH, 'utf8'));
    const logDir = fs.mkdtempSync(path.join(os.tmpdir(), 'router-log-'));
    const logPath = path.join(logDir, 'suggestion-log.jsonl');
    try {
      const result = runRouterFull(tmpHome, MATCHED_PROMPT, 'sess-router-1', {
        RHIZE_SUGGESTION_LOG: logPath,
      });
      assert.strictEqual(result.status, 0, `exit code: ${result.status}, stderr: ${result.stderr}`);
      assert.ok(fs.existsSync(logPath), 'expected log file to be created');
      const lines = fs.readFileSync(logPath, 'utf8').trim().split('\n').filter(Boolean);
      assert.strictEqual(lines.length, 1, `expected exactly one log line, got ${lines.length}`);
      const entry = JSON.parse(lines[0]);
      assert.ok(typeof entry.ts === 'string' && !Number.isNaN(Date.parse(entry.ts)), 'ts must be ISO8601');
      assert.strictEqual(entry.session_id, 'sess-router-1');
      assert.strictEqual(entry.hook, 'router');
      assert.strictEqual(entry.suggested, 'skill:rhize-context-manager/graphify');
      const expectedHash = crypto
        .createHash('sha256')
        .update(MATCHED_PROMPT)
        .digest('hex')
        .slice(0, 16);
      assert.strictEqual(entry.context_hash, expectedHash);
      assert.ok(
        !JSON.stringify(entry).includes('git and context'),
        'raw prompt text must never be logged'
      );
    } finally {
      fs.rmSync(logDir, { recursive: true, force: true });
    }
  });
});

// (h) A log write failure (unwritable path — parent is a file, not a
// directory) must never affect the hook's stdout or exit code.
check('[logging] log write failure does not affect hook output or exit code', () => {
  withTempHome((tmpHome) => {
    writeIndexes(tmpHome, fs.readFileSync(INDEX_FIXTURE_PATH, 'utf8'));
    const blockerDir = fs.mkdtempSync(path.join(os.tmpdir(), 'router-log-blocker-'));
    const blockerFile = path.join(blockerDir, 'not-a-dir');
    fs.writeFileSync(blockerFile, 'x');
    const logPath = path.join(blockerFile, 'suggestion-log.jsonl'); // parent is a file
    try {
      const result = runRouterFull(tmpHome, MATCHED_PROMPT, 'sess-router-2', {
        RHIZE_SUGGESTION_LOG: logPath,
      });
      assert.strictEqual(result.status, 0, `exit code: ${result.status}, stderr: ${result.stderr}`);
      const stdout = result.stdout.trim();
      assert.ok(stdout.length > 0, 'expected non-empty stdout despite log failure');
      const parsed = JSON.parse(stdout.split('\n')[0]);
      assert.strictEqual(
        parsed.hookSpecificOutput.additionalContext,
        'Consider the rhize-context-manager:graphify skill (matches context, git)'
      );
      assert.ok(!fs.existsSync(logPath), 'log file must not have been created');
    } finally {
      fs.rmSync(blockerDir, { recursive: true, force: true });
    }
  });
});

// (i) Statistical: an unmatched prompt logs a `{"suggested": null}` line at a
// sampled ~1-in-20 rate, so silence precision has a denominator. Run enough
// iterations that a true 5% sample rate makes zero hits implausible
// (P(0 hits in 150 draws) ≈ 0.0005%) while keeping runtime reasonable.
check('[logging] unmatched prompts sample suggested:null lines at ~1-in-20', () => {
  withTempHome((tmpHome) => {
    writeIndexes(tmpHome, fs.readFileSync(INDEX_FIXTURE_PATH, 'utf8'));
    const logDir = fs.mkdtempSync(path.join(os.tmpdir(), 'router-log-sample-'));
    const logPath = path.join(logDir, 'suggestion-log.jsonl');
    try {
      const iterations = 150;
      for (let i = 0; i < iterations; i += 1) {
        const result = runRouterFull(tmpHome, UNMATCHED_PROMPT, `sess-sample-${i}`, {
          RHIZE_SUGGESTION_LOG: logPath,
        });
        assert.strictEqual(result.status, 0, `exit code: ${result.status}, stderr: ${result.stderr}`);
        assert.strictEqual(result.stdout.trim(), '', 'unmatched prompt must never emit stdout');
      }
      const lines = fs.existsSync(logPath)
        ? fs.readFileSync(logPath, 'utf8').trim().split('\n').filter(Boolean)
        : [];
      assert.ok(lines.length > 0, 'expected at least one sampled suggested:null line');
      assert.ok(
        lines.length < iterations,
        'sampling must not log every no-suggestion invocation'
      );
      for (const line of lines) {
        const entry = JSON.parse(line);
        assert.strictEqual(entry.hook, 'router');
        assert.strictEqual(entry.suggested, null);
        assert.ok(typeof entry.context_hash === 'string' && entry.context_hash.length === 16);
      }
    } finally {
      fs.rmSync(logDir, { recursive: true, force: true });
    }
  });
});

// (j) Latency: appendFileSync of one suggestion line must stay well within
// the hooks' ~50ms budget. Measured in-process (not via spawnSync, whose
// per-call Node startup cost would dwarf the write itself and defeat the
// point of isolating appendFileSync's contribution).
check('[logging] appendFileSync of one line stays well within the 50ms hook budget', () => {
  const logDir = fs.mkdtempSync(path.join(os.tmpdir(), 'router-log-timing-'));
  const logPath = path.join(logDir, 'suggestion-log.jsonl');
  try {
    const entry =
      JSON.stringify({
        ts: new Date().toISOString(),
        session_id: 'sess-timing',
        hook: 'router',
        suggested: 'skill:rhize-context-manager/graphify',
        context_hash: 'a'.repeat(16),
      }) + '\n';
    const iterations = 200;
    const start = process.hrtime.bigint();
    for (let i = 0; i < iterations; i += 1) {
      fs.appendFileSync(logPath, entry);
    }
    const elapsedMs = Number(process.hrtime.bigint() - start) / 1e6;
    const perCallMs = elapsedMs / iterations;
    assert.ok(
      perCallMs < 5,
      `expected appendFileSync to average well under the 50ms hook budget, got ${perCallMs}ms/call`
    );
  } finally {
    fs.rmSync(logDir, { recursive: true, force: true });
  }
});

// Explicit directives can reach name-only entries; the index and map agree.
{
  const core = require(path.join(REPO_ROOT, 'rhize-context-manager/hooks/lib/route-core.js'));
  const ids = ['skill:ecc/accessibility', 'skill:ecc/react-patterns', 'skill:other/react-patterns'];
  const router = { signals: Object.fromEntries(ids.map((id) => [id, [{ kind: 'name', weight: 1, label: id.split('/').pop() }]])) };
  const map = { nodes: ids.map((id) => ({ id, kind: 'skill', name: id.split('/').pop() })), edges: [] };
  for (const [prompt, expected] of [
    ['Use accessibility', ids[0]],
    ['Please invoke ecc:react-patterns first', ids[1]],
    ['Run `ecc:accessibility`', ids[0]],
    ['Use react-patterns', null],
    ['Do not use accessibility', null],
    ['I read about accessibility', null],
    ['Audit this form', null],
    ['Use unknown-skill', null],
    ['Use ecc:accessibility-extra', null],
  ]) {
    for (const actual of [core.routeFromIndex(router, core.tokenize(prompt), prompt), core.route(map, core.tokenize(prompt), prompt)]) {
      assert.strictEqual(actual && actual.skillId, expected, prompt);
    }
  }
  withTempHome((home) => {
    writeIndexes(home, JSON.stringify({ router }));
    const result = runRouter(home, 'Use accessibility');
    assert.strictEqual(result.status, 0);
    assert.ok(result.stdout.includes('ecc:accessibility'), result.stdout);
  });
  const declared = { signals: { 'skill:rhize/context-engineering': [
    { kind: 'name', weight: 1, label: 'context-engineering' },
    { kind: 'tag', weight: 2, label: 'context' },
  ] } };
  const ordinary = 'Use context engineering to optimize this context';
  assert.strictEqual(core.routeFromIndex(declared, core.tokenize(ordinary), ordinary).skillId, 'skill:rhize/context-engineering');
  const negative = 'Do not use context-engineering for context engineering';
  assert.strictEqual(core.routeFromIndex(declared, core.tokenize(negative), negative), null);
  const collision = { signals: { 'skill:one/ecc/accessibility': router.signals[ids[0]], 'skill:two/ecc/accessibility': router.signals[ids[0]] } };
  assert.strictEqual(core.routeFromIndex(collision, core.tokenize('Use ecc:accessibility'), 'Use ecc:accessibility'), null);
}

if (failures > 0) {
  console.error(`\n${failures} test(s) failed.`);
  process.exit(1);
} else {
  console.log('\nAll router tests passed.');
  process.exit(0);
}
