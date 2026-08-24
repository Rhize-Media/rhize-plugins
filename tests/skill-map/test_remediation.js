#!/usr/bin/env node
'use strict';

// test_remediation.js — exercises
// rhize-context-manager/hooks/remediation-suggester.js (relationships v2,
// docs/superpowers/specs/2026-08-09-skill-map-relationships-v2-design.md
// section 7) end-to-end via spawnSync: stdin in (a Bash PostToolUse payload),
// stdout/exit code out.
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
  'remediation-suggester.js'
);
const FIXTURE_PATH = path.join(__dirname, 'fixtures', 'indexes-remediation.json');

function withTempHome(fn) {
  const tmpHome = fs.mkdtempSync(path.join(os.tmpdir(), 'remediation-test-'));
  try {
    return fn(tmpHome);
  } finally {
    fs.rmSync(tmpHome, { recursive: true, force: true });
  }
}

function writeIndexes(tmpHome, contents) {
  const dir = path.join(tmpHome, '.claude', 'context-manager');
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, 'skill-map.indexes.json'), contents);
}

function runHook(tmpHome, { stdout = '', stderr = '' } = {}) {
  const payload = {
    tool_name: 'Bash',
    tool_input: { command: 'npm run build' },
    tool_response: { stdout, stderr, interrupted: false },
  };
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
function runHookFull(tmpHome, { stdout = '', stderr = '', sessionId, extraEnv } = {}) {
  const payload = {
    tool_name: 'Bash',
    tool_input: { command: 'npm run build' },
    tool_response: { stdout, stderr, interrupted: false },
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

// (a) Failing output matching a condition pattern with declared remediators
// must emit exactly one suggestion naming the top-ranked (first-listed)
// remediator, phrased as an agent suggestion for an `external:` id.
check('failing output emits exactly one suggestion', () => {
  withTempHome((tmpHome) => {
    writeIndexes(tmpHome, fs.readFileSync(FIXTURE_PATH, 'utf8'));
    const result = runHook(tmpHome, { stderr: 'Error: build failed\n' });
    assert.strictEqual(result.status, 0, `exit code: ${result.status}, stderr: ${result.stderr}`);
    const stdout = result.stdout.trim();
    assert.ok(stdout.length > 0, 'expected non-empty stdout');
    const lines = stdout.split('\n').filter(Boolean);
    assert.strictEqual(lines.length, 1, `expected exactly one line, got ${lines.length}`);
    const parsed = JSON.parse(lines[0]);
    const ctx = parsed.hookSpecificOutput && parsed.hookSpecificOutput.additionalContext;
    assert.strictEqual(
      ctx,
      'Build failed — the ecc:build-error-resolver agent remediates build-failure'
    );
  });
});

// (b) Passing output (no pattern match) must emit nothing and exit 0.
check('passing output emits nothing and exits 0', () => {
  withTempHome((tmpHome) => {
    writeIndexes(tmpHome, fs.readFileSync(FIXTURE_PATH, 'utf8'));
    const result = runHook(tmpHome, { stdout: 'Build succeeded in 4.2s\n' });
    assert.strictEqual(result.status, 0, `exit code: ${result.status}, stderr: ${result.stderr}`);
    assert.strictEqual(result.stdout.trim(), '', 'expected empty stdout');
  });
});

// (c) Failing-looking output that matches no known condition pattern must
// also emit nothing.
check('unknown failure text emits nothing and exits 0', () => {
  withTempHome((tmpHome) => {
    writeIndexes(tmpHome, fs.readFileSync(FIXTURE_PATH, 'utf8'));
    const result = runHook(tmpHome, { stderr: 'Something weird happened over there.\n' });
    assert.strictEqual(result.status, 0, `exit code: ${result.status}, stderr: ${result.stderr}`);
    assert.strictEqual(result.stdout.trim(), '', 'expected empty stdout');
  });
});

// (d) No indexes file installed at all must fail silently.
check('missing index emits nothing and exits 0', () => {
  withTempHome((tmpHome) => {
    const result = runHook(tmpHome, { stderr: 'Error: build failed\n' });
    assert.strictEqual(result.status, 0, `exit code: ${result.status}, stderr: ${result.stderr}`);
    assert.strictEqual(result.stdout.trim(), '', 'expected empty stdout');
  });
});

// --- suggestion-log assertions (RHIZE_SUGGESTION_LOG override) ---

const FAILING_STDERR = 'Error: build failed\n';

// (e) A firing remediation must append exactly one log line matching the
// pinned schema. context_hash covers the matched stdout+stderr text, never
// the raw tool output itself.
check('[logging] remediation fires: log line matches pinned schema', () => {
  withTempHome((tmpHome) => {
    writeIndexes(tmpHome, fs.readFileSync(FIXTURE_PATH, 'utf8'));
    const logDir = fs.mkdtempSync(path.join(os.tmpdir(), 'remediation-log-'));
    const logPath = path.join(logDir, 'suggestion-log.jsonl');
    try {
      const result = runHookFull(tmpHome, {
        stderr: FAILING_STDERR,
        sessionId: 'sess-remediation-1',
        extraEnv: { RHIZE_SUGGESTION_LOG: logPath },
      });
      assert.strictEqual(result.status, 0, `exit code: ${result.status}, stderr: ${result.stderr}`);
      assert.ok(fs.existsSync(logPath), 'expected log file to be created');
      const lines = fs.readFileSync(logPath, 'utf8').trim().split('\n').filter(Boolean);
      assert.strictEqual(lines.length, 1, `expected exactly one log line, got ${lines.length}`);
      const entry = JSON.parse(lines[0]);
      assert.ok(typeof entry.ts === 'string' && !Number.isNaN(Date.parse(entry.ts)), 'ts must be ISO8601');
      assert.strictEqual(entry.session_id, 'sess-remediation-1');
      assert.strictEqual(entry.hook, 'remediation');
      assert.strictEqual(entry.suggested, 'external:ecc-build-error-resolver');
      const expectedHash = crypto
        .createHash('sha256')
        .update(`\n${FAILING_STDERR}`)
        .digest('hex')
        .slice(0, 16);
      assert.strictEqual(entry.context_hash, expectedHash);
      assert.ok(
        !JSON.stringify(entry).includes('build failed'),
        'raw tool output must never be logged'
      );
    } finally {
      fs.rmSync(logDir, { recursive: true, force: true });
    }
  });
});

// (f) A log write failure (unwritable path — parent is a file, not a
// directory) must never affect the hook's stdout or exit code.
check('[logging] log write failure does not affect hook output or exit code', () => {
  withTempHome((tmpHome) => {
    writeIndexes(tmpHome, fs.readFileSync(FIXTURE_PATH, 'utf8'));
    const blockerDir = fs.mkdtempSync(path.join(os.tmpdir(), 'remediation-log-blocker-'));
    const blockerFile = path.join(blockerDir, 'not-a-dir');
    fs.writeFileSync(blockerFile, 'x');
    const logPath = path.join(blockerFile, 'suggestion-log.jsonl'); // parent is a file
    try {
      const result = runHookFull(tmpHome, {
        stderr: FAILING_STDERR,
        sessionId: 'sess-remediation-2',
        extraEnv: { RHIZE_SUGGESTION_LOG: logPath },
      });
      assert.strictEqual(result.status, 0, `exit code: ${result.status}, stderr: ${result.stderr}`);
      const stdout = result.stdout.trim();
      assert.ok(stdout.length > 0, 'expected non-empty stdout despite log failure');
      const parsed = JSON.parse(stdout.split('\n')[0]);
      assert.strictEqual(
        parsed.hookSpecificOutput.additionalContext,
        'Build failed — the ecc:build-error-resolver agent remediates build-failure'
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
  console.log('\nAll remediation tests passed.');
  process.exit(0);
}
