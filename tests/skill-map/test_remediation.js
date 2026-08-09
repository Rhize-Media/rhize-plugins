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

if (failures > 0) {
  console.error(`\n${failures} test(s) failed.`);
  process.exit(1);
} else {
  console.log('\nAll remediation tests passed.');
  process.exit(0);
}
