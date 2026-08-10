#!/usr/bin/env node
'use strict';

// test_next_step.js — exercises
// rhize-context-manager/hooks/next-step-suggester.js (relationships v2,
// docs/superpowers/specs/2026-08-09-skill-map-relationships-v2-design.md
// section 7) end-to-end via spawnSync: stdin in (a Skill PostToolUse
// payload), stdout/exit code out.
//
// Every case runs with HOME pointed at a temp directory — never the real
// ~/.claude — so the hook's index resolution (~/.claude/context-manager/
// skill-map.indexes.{resolved,}.json) reads only the fixture this test wrote.

const assert = require('assert');
const crypto = require('crypto');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const HOOK_PATH = path.join(
  REPO_ROOT,
  'rhize-context-manager',
  'hooks',
  'next-step-suggester.js'
);
const STATIC_FIXTURE_PATH = path.join(
  __dirname,
  'fixtures',
  'indexes-succession-static.json'
);
const RESOLVED_FOLLOWS_FIXTURE_PATH = path.join(
  __dirname,
  'fixtures',
  'indexes-succession-resolved-follows.json'
);

function withTempHome(fn) {
  const tmpHome = fs.mkdtempSync(path.join(os.tmpdir(), 'next-step-test-'));
  try {
    return fn(tmpHome);
  } finally {
    fs.rmSync(tmpHome, { recursive: true, force: true });
  }
}

function writeStaticIndexes(tmpHome, contents) {
  const dir = path.join(tmpHome, '.claude', 'context-manager');
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, 'skill-map.indexes.json'), contents);
}

function writeResolvedIndexes(tmpHome, contents) {
  const dir = path.join(tmpHome, '.claude', 'context-manager');
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, 'skill-map.indexes.resolved.json'), contents);
}

function runHook(tmpHome, skillName) {
  const payload = { tool_name: 'Skill', tool_input: { skill: skillName } };
  const result = spawnSync(process.execPath, [HOOK_PATH], {
    input: JSON.stringify(payload),
    env: { ...process.env, HOME: tmpHome },
    encoding: 'utf8',
    timeout: 5000,
  });
  return result;
}

// Variant that also sets session_id (for suggestion-log assertions) and
// accepts extra env vars, notably RHIZE_SUGGESTION_LOG.
function runHookFull(tmpHome, skillName, sessionId, extraEnv) {
  const payload = {
    tool_name: 'Skill',
    tool_input: { skill: skillName },
    session_id: sessionId,
  };
  const result = spawnSync(process.execPath, [HOOK_PATH], {
    input: JSON.stringify(payload),
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

// (a) A skill with a declared `precedes` successor must emit exactly one
// suggestion naming it.
check('skill with a precedes successor emits a suggestion', () => {
  withTempHome((tmpHome) => {
    writeStaticIndexes(tmpHome, fs.readFileSync(STATIC_FIXTURE_PATH, 'utf8'));
    const result = runHook(tmpHome, 'project-launcher:write-prd');
    assert.strictEqual(result.status, 0, `exit code: ${result.status}, stderr: ${result.stderr}`);
    const stdout = result.stdout.trim();
    assert.ok(stdout.length > 0, 'expected non-empty stdout');
    const lines = stdout.split('\n').filter(Boolean);
    assert.strictEqual(lines.length, 1, `expected exactly one line, got ${lines.length}`);
    const parsed = JSON.parse(lines[0]);
    const ctx = parsed.hookSpecificOutput && parsed.hookSpecificOutput.additionalContext;
    assert.strictEqual(
      ctx,
      'After project-launcher:write-prd, the usual next step is project-launcher:grill-prd'
    );
  });
});

// (b) A skill with only a mined `follows` entry in the RESOLVED indexes layer
// (no declared `precedes`) must still emit a suggestion — the fallback path.
check('skill with only a mined follows successor emits a suggestion', () => {
  withTempHome((tmpHome) => {
    writeResolvedIndexes(tmpHome, fs.readFileSync(RESOLVED_FOLLOWS_FIXTURE_PATH, 'utf8'));
    const result = runHook(tmpHome, 'rhize-context-manager:context-fundamentals');
    assert.strictEqual(result.status, 0, `exit code: ${result.status}, stderr: ${result.stderr}`);
    const stdout = result.stdout.trim();
    assert.ok(stdout.length > 0, 'expected non-empty stdout');
    const lines = stdout.split('\n').filter(Boolean);
    assert.strictEqual(lines.length, 1, `expected exactly one line, got ${lines.length}`);
    const parsed = JSON.parse(lines[0]);
    const ctx = parsed.hookSpecificOutput && parsed.hookSpecificOutput.additionalContext;
    assert.strictEqual(
      ctx,
      'After rhize-context-manager:context-fundamentals, the usual next step is rhize-context-manager:context-optimization'
    );
  });
});

// (c) A skill with no successor at all (present in the index with empty
// precedes/follows) must emit nothing.
check('skill with no successor emits nothing and exits 0', () => {
  withTempHome((tmpHome) => {
    writeStaticIndexes(tmpHome, fs.readFileSync(STATIC_FIXTURE_PATH, 'utf8'));
    const result = runHook(tmpHome, 'project-launcher:grill-prd');
    assert.strictEqual(result.status, 0, `exit code: ${result.status}, stderr: ${result.stderr}`);
    assert.strictEqual(result.stdout.trim(), '', 'expected empty stdout');
  });
});

// --- suggestion-log assertions (RHIZE_SUGGESTION_LOG override) ---

const INVOKED_SKILL = 'project-launcher:write-prd';

// (d) A firing next-step suggestion must append exactly one log line
// matching the pinned schema. context_hash covers the completed skill's id,
// never raw prompt text or file paths.
check('[logging] next-step fires: log line matches pinned schema', () => {
  withTempHome((tmpHome) => {
    writeStaticIndexes(tmpHome, fs.readFileSync(STATIC_FIXTURE_PATH, 'utf8'));
    const logDir = fs.mkdtempSync(path.join(os.tmpdir(), 'next-step-log-'));
    const logPath = path.join(logDir, 'suggestion-log.jsonl');
    try {
      const result = runHookFull(tmpHome, INVOKED_SKILL, 'sess-next-step-1', {
        RHIZE_SUGGESTION_LOG: logPath,
      });
      assert.strictEqual(result.status, 0, `exit code: ${result.status}, stderr: ${result.stderr}`);
      assert.ok(fs.existsSync(logPath), 'expected log file to be created');
      const lines = fs.readFileSync(logPath, 'utf8').trim().split('\n').filter(Boolean);
      assert.strictEqual(lines.length, 1, `expected exactly one log line, got ${lines.length}`);
      const entry = JSON.parse(lines[0]);
      assert.ok(typeof entry.ts === 'string' && !Number.isNaN(Date.parse(entry.ts)), 'ts must be ISO8601');
      assert.strictEqual(entry.session_id, 'sess-next-step-1');
      assert.strictEqual(entry.hook, 'next-step');
      assert.strictEqual(entry.suggested, 'skill:project-launcher/grill-prd');
      const expectedHash = crypto
        .createHash('sha256')
        .update(INVOKED_SKILL)
        .digest('hex')
        .slice(0, 16);
      assert.strictEqual(entry.context_hash, expectedHash);
    } finally {
      fs.rmSync(logDir, { recursive: true, force: true });
    }
  });
});

// (e) A log write failure (unwritable path — parent is a file, not a
// directory) must never affect the hook's stdout or exit code.
check('[logging] log write failure does not affect hook output or exit code', () => {
  withTempHome((tmpHome) => {
    writeStaticIndexes(tmpHome, fs.readFileSync(STATIC_FIXTURE_PATH, 'utf8'));
    const blockerDir = fs.mkdtempSync(path.join(os.tmpdir(), 'next-step-log-blocker-'));
    const blockerFile = path.join(blockerDir, 'not-a-dir');
    fs.writeFileSync(blockerFile, 'x');
    const logPath = path.join(blockerFile, 'suggestion-log.jsonl'); // parent is a file
    try {
      const result = runHookFull(tmpHome, INVOKED_SKILL, 'sess-next-step-2', {
        RHIZE_SUGGESTION_LOG: logPath,
      });
      assert.strictEqual(result.status, 0, `exit code: ${result.status}, stderr: ${result.stderr}`);
      const stdout = result.stdout.trim();
      assert.ok(stdout.length > 0, 'expected non-empty stdout despite log failure');
      const parsed = JSON.parse(stdout.split('\n')[0]);
      assert.strictEqual(
        parsed.hookSpecificOutput.additionalContext,
        'After project-launcher:write-prd, the usual next step is project-launcher:grill-prd'
      );
      assert.ok(!fs.existsSync(logPath), 'log file must not have been created');
    } finally {
      fs.rmSync(blockerDir, { recursive: true, force: true });
    }
  });
});

if (failures > 0) {
  console.error(`\n${failures} test(s) failed.`);
  process.exit(1);
} else {
  console.log('\nAll next-step tests passed.');
  process.exit(0);
}
