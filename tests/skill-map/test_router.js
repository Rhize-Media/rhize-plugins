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

if (failures > 0) {
  console.error(`\n${failures} test(s) failed.`);
  process.exit(1);
} else {
  console.log('\nAll router tests passed.');
  process.exit(0);
}
