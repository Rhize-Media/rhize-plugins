#!/usr/bin/env node
'use strict';

// test_disclosure.js — exercises
// rhize-context-manager/hooks/session-disclosure.js (Phase 3 of
// .claude/plans/skill-map-graph-substrate.md, refactored in relationships v2
// — see the design doc's section 7 — to read the materialized `disclosure`
// index first) end-to-end via spawnSync, so it validates exactly what the
// hook harness invokes: stdin in, stdout/exit code out.
//
// Every case runs with HOME pointed at a temp directory — never the real
// ~/.claude — so the hook's resolution (~/.claude/context-manager/
// skill-map.indexes.{resolved,}.json, then skill-map.{resolved,static}.json)
// reads only the fixture this test wrote, and with the spawned process's cwd
// pointed at a temp directory standing in for the repo being fingerprinted.
//
// The primary cases below write only an indexes fixture, exercising
// relevantSkillsFromIndex() exclusively. The dedicated "fallback" case at the
// bottom writes only a static MAP fixture (no indexes file at all) to prove
// the original map-scanning relevantSkills() path still works unaided.

const assert = require('assert');
const crypto = require('crypto');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const DISCLOSURE_PATH = path.join(
  REPO_ROOT,
  'rhize-context-manager',
  'hooks',
  'session-disclosure.js'
);
const FIXTURE_PATH = path.join(__dirname, 'fixtures', 'stack-map.json');
const INDEX_FIXTURE_PATH = path.join(__dirname, 'fixtures', 'indexes-stack-map.json');
const INDEX_EXTENDS_FIXTURE_PATH = path.join(
  __dirname,
  'fixtures',
  'indexes-stack-map-extends.json'
);

function withTempDir(prefix, fn) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
  try {
    return fn(dir);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
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

function runDisclosure(tmpHome, tmpCwd) {
  const result = spawnSync(process.execPath, [DISCLOSURE_PATH], {
    input: JSON.stringify({ cwd: tmpCwd }),
    cwd: tmpCwd,
    env: { ...process.env, HOME: tmpHome },
    encoding: 'utf8',
    timeout: 5000,
  });
  return result;
}

// Variant that also sets session_id (for suggestion-log assertions) and
// accepts extra env vars, notably RHIZE_SUGGESTION_LOG.
function runDisclosureFull(tmpHome, tmpCwd, sessionId, extraEnv) {
  const result = spawnSync(process.execPath, [DISCLOSURE_PATH], {
    input: JSON.stringify({ cwd: tmpCwd, session_id: sessionId }),
    cwd: tmpCwd,
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

// (a) [index path] A repo with a next.config.mjs must emit a block naming a
// nextjs-stack skill. Only an indexes fixture is written (no static map at
// all), so this exercises relevantSkillsFromIndex() exclusively.
check('[index] next.config.mjs emits block naming a nextjs-stack skill', () => {
  withTempDir('disclosure-home-', (tmpHome) => {
    withTempDir('disclosure-cwd-', (tmpCwd) => {
      writeIndexes(tmpHome, fs.readFileSync(INDEX_FIXTURE_PATH, 'utf8'));
      fs.writeFileSync(path.join(tmpCwd, 'next.config.mjs'), 'export default {};\n');

      const result = runDisclosure(tmpHome, tmpCwd);
      assert.strictEqual(result.status, 0, `exit code: ${result.status}, stderr: ${result.stderr}`);
      const stdout = result.stdout.trim();
      assert.ok(stdout.length > 0, 'expected non-empty stdout');
      const lines = stdout.split('\n').filter(Boolean);
      assert.strictEqual(lines.length, 1, `expected exactly one JSON line, got ${lines.length}`);
      const parsed = JSON.parse(lines[0]);
      const ctx = parsed.hookSpecificOutput && parsed.hookSpecificOutput.additionalContext;
      assert.ok(ctx, 'expected hookSpecificOutput.additionalContext');
      assert.ok(
        ctx.includes('seo-aeo-geo:nextjs-sanity-seo'),
        `expected block to name the nextjs-tagged skill, got: ${ctx}`
      );
    });
  });
});

// (b) [index path] An empty repo (no stack markers) must emit nothing and
// exit 0, even though the indexes exist and are valid — silence > generic
// banner. Stack detection happens before the index is even read.
check('[index] empty dir emits nothing and exits 0', () => {
  withTempDir('disclosure-home-', (tmpHome) => {
    withTempDir('disclosure-cwd-', (tmpCwd) => {
      writeIndexes(tmpHome, fs.readFileSync(INDEX_FIXTURE_PATH, 'utf8'));

      const result = runDisclosure(tmpHome, tmpCwd);
      assert.strictEqual(result.status, 0, `exit code: ${result.status}, stderr: ${result.stderr}`);
      assert.strictEqual(result.stdout.trim(), '', 'expected empty stdout');
    });
  });
});

// (c) A corrupt indexes file (and no static map available at all) must fall
// back to readMap()/relevantSkills(), find nothing, and fail silently — the
// corruption must never surface as an error even with a stack marker present.
check('corrupt indexes file falls back and emits nothing (exit 0)', () => {
  withTempDir('disclosure-home-', (tmpHome) => {
    withTempDir('disclosure-cwd-', (tmpCwd) => {
      const dir = path.join(tmpHome, '.claude', 'context-manager');
      fs.mkdirSync(dir, { recursive: true });
      fs.writeFileSync(path.join(dir, 'skill-map.indexes.json'), '{ this is not valid JSON ');
      fs.writeFileSync(path.join(tmpCwd, 'next.config.mjs'), 'export default {};\n');

      const result = runDisclosure(tmpHome, tmpCwd);
      assert.strictEqual(result.status, 0, `exit code: ${result.status}, stderr: ${result.stderr}`);
      assert.strictEqual(result.stdout.trim(), '', 'expected empty stdout');
    });
  });
});

// (d) [index path] A base skill and a matching extender (extends edge,
// folded per-stack by build_disclosure_index) must be compacted into one
// line for the base, with the extender appended as "(+N deeper: name)"
// instead of appearing as its own line.
check('[index] base + matched extender compact into one "+N deeper" line', () => {
  withTempDir('disclosure-home-', (tmpHome) => {
    withTempDir('disclosure-cwd-', (tmpCwd) => {
      writeIndexes(tmpHome, fs.readFileSync(INDEX_EXTENDS_FIXTURE_PATH, 'utf8'));
      fs.writeFileSync(path.join(tmpCwd, 'next.config.mjs'), 'export default {};\n');

      const result = runDisclosure(tmpHome, tmpCwd);
      assert.strictEqual(result.status, 0, `exit code: ${result.status}, stderr: ${result.stderr}`);
      const stdout = result.stdout.trim();
      assert.ok(stdout.length > 0, 'expected non-empty stdout');
      const lines = stdout.split('\n').filter(Boolean);
      assert.strictEqual(lines.length, 1, `expected exactly one JSON line, got ${lines.length}`);
      const parsed = JSON.parse(lines[0]);
      const ctx = parsed.hookSpecificOutput && parsed.hookSpecificOutput.additionalContext;
      assert.ok(ctx, 'expected hookSpecificOutput.additionalContext');
      const blockLines = ctx.split('\n');
      assert.strictEqual(
        blockLines.length,
        2,
        `expected header + exactly one compacted skill line, got: ${ctx}`
      );
      assert.strictEqual(
        blockLines[1],
        '- rhize-context-manager:context-fundamentals — matches nextjs stack (+1 deeper: context-compression)',
        `expected compact base+deeper line, got: ${blockLines[1]}`
      );
      assert.ok(
        !ctx.includes('context-compression —'),
        `extender must not appear as its own line, got: ${ctx}`
      );
    });
  });
});

// (e) [fallback path, explicit] With NO indexes file present at all (only
// the legacy static map), the original map-scanning relevantSkills() path
// must reproduce the exact same result as case (a) above.
check('[fallback] no indexes file: map-scan path still matches', () => {
  withTempDir('disclosure-home-', (tmpHome) => {
    withTempDir('disclosure-cwd-', (tmpCwd) => {
      writeStaticMap(tmpHome, fs.readFileSync(FIXTURE_PATH, 'utf8'));
      fs.writeFileSync(path.join(tmpCwd, 'next.config.mjs'), 'export default {};\n');

      const result = runDisclosure(tmpHome, tmpCwd);
      assert.strictEqual(result.status, 0, `exit code: ${result.status}, stderr: ${result.stderr}`);
      const stdout = result.stdout.trim();
      assert.ok(stdout.length > 0, 'expected non-empty stdout');
      const lines = stdout.split('\n').filter(Boolean);
      assert.strictEqual(lines.length, 1, `expected exactly one JSON line, got ${lines.length}`);
      const parsed = JSON.parse(lines[0]);
      const ctx = parsed.hookSpecificOutput && parsed.hookSpecificOutput.additionalContext;
      assert.ok(ctx, 'expected hookSpecificOutput.additionalContext');
      assert.ok(
        ctx.includes('seo-aeo-geo:nextjs-sanity-seo'),
        `expected block to name the nextjs-tagged skill, got: ${ctx}`
      );
    });
  });
});

// --- suggestion-log assertions (RHIZE_SUGGESTION_LOG override) ---

// (f) A firing disclosure block must append exactly one log line matching
// the pinned schema, with `suggested` as an array (disclosure's multi-skill
// surface) and context_hash covering the repo fingerprint (cwd), never a raw
// file path or prompt text.
check('[logging] disclosure fires: log line matches pinned schema', () => {
  withTempDir('disclosure-home-', (tmpHome) => {
    withTempDir('disclosure-cwd-', (tmpCwd) => {
      writeIndexes(tmpHome, fs.readFileSync(INDEX_FIXTURE_PATH, 'utf8'));
      fs.writeFileSync(path.join(tmpCwd, 'next.config.mjs'), 'export default {};\n');
      const logDir = fs.mkdtempSync(path.join(os.tmpdir(), 'disclosure-log-'));
      const logPath = path.join(logDir, 'suggestion-log.jsonl');
      try {
        const result = runDisclosureFull(tmpHome, tmpCwd, 'sess-disclosure-1', {
          RHIZE_SUGGESTION_LOG: logPath,
        });
        assert.strictEqual(result.status, 0, `exit code: ${result.status}, stderr: ${result.stderr}`);
        assert.ok(fs.existsSync(logPath), 'expected log file to be created');
        const lines = fs.readFileSync(logPath, 'utf8').trim().split('\n').filter(Boolean);
        assert.strictEqual(lines.length, 1, `expected exactly one log line, got ${lines.length}`);
        const entry = JSON.parse(lines[0]);
        assert.ok(typeof entry.ts === 'string' && !Number.isNaN(Date.parse(entry.ts)), 'ts must be ISO8601');
        assert.strictEqual(entry.session_id, 'sess-disclosure-1');
        assert.strictEqual(entry.hook, 'disclosure');
        assert.ok(Array.isArray(entry.suggested), 'disclosure suggested must be an array');
        assert.ok(
          entry.suggested.includes('skill:seo-aeo-geo/nextjs-sanity-seo'),
          `expected suggested to include the nextjs-tagged skill id, got: ${JSON.stringify(entry.suggested)}`
        );
        const expectedHash = crypto.createHash('sha256').update(tmpCwd).digest('hex').slice(0, 16);
        assert.strictEqual(entry.context_hash, expectedHash);
        assert.ok(
          !JSON.stringify(entry).includes(tmpCwd),
          'raw repo path must never be logged, only its hash'
        );
      } finally {
        fs.rmSync(logDir, { recursive: true, force: true });
      }
    });
  });
});

// (g) A log write failure (unwritable path — parent is a file, not a
// directory) must never affect the hook's stdout or exit code.
check('[logging] log write failure does not affect hook output or exit code', () => {
  withTempDir('disclosure-home-', (tmpHome) => {
    withTempDir('disclosure-cwd-', (tmpCwd) => {
      writeIndexes(tmpHome, fs.readFileSync(INDEX_FIXTURE_PATH, 'utf8'));
      fs.writeFileSync(path.join(tmpCwd, 'next.config.mjs'), 'export default {};\n');
      const blockerDir = fs.mkdtempSync(path.join(os.tmpdir(), 'disclosure-log-blocker-'));
      const blockerFile = path.join(blockerDir, 'not-a-dir');
      fs.writeFileSync(blockerFile, 'x');
      const logPath = path.join(blockerFile, 'suggestion-log.jsonl'); // parent is a file
      try {
        const result = runDisclosureFull(tmpHome, tmpCwd, 'sess-disclosure-2', {
          RHIZE_SUGGESTION_LOG: logPath,
        });
        assert.strictEqual(result.status, 0, `exit code: ${result.status}, stderr: ${result.stderr}`);
        const stdout = result.stdout.trim();
        assert.ok(stdout.length > 0, 'expected non-empty stdout despite log failure');
        const parsed = JSON.parse(stdout.split('\n')[0]);
        assert.ok(
          parsed.hookSpecificOutput.additionalContext.includes('seo-aeo-geo:nextjs-sanity-seo'),
          'hook output must be unaffected by log write failure'
        );
        assert.ok(!fs.existsSync(logPath), 'log file must not have been created');
      } finally {
        fs.rmSync(blockerDir, { recursive: true, force: true });
      }
    });
  });
});

if (failures > 0) {
  console.error(`\n${failures} test(s) failed.`);
  process.exit(1);
} else {
  console.log('\nAll disclosure tests passed.');
  process.exit(0);
}
