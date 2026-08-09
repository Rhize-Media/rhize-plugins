#!/usr/bin/env node
'use strict';

// test_disclosure.js — exercises
// rhize-context-manager/hooks/session-disclosure.js (Phase 3 of
// .claude/plans/skill-map-graph-substrate.md) end-to-end via spawnSync, so it
// validates exactly what the hook harness invokes: stdin in, stdout/exit
// code out.
//
// Every case runs with HOME pointed at a temp directory — never the real
// ~/.claude — so the hook's map resolution (~/.claude/context-manager/
// skill-map.{resolved,static}.json) reads only the fixture this test wrote,
// and with the spawned process's cwd pointed at a temp directory standing in
// for the repo being fingerprinted.

const assert = require('assert');
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

// (a) A repo with a next.config.mjs must emit a block naming a nextjs-stack
// skill.
check('next.config.mjs emits block naming a nextjs-stack skill', () => {
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

// (b) An empty repo (no stack markers) must emit nothing and exit 0, even
// though the map exists and is valid — silence > generic banner.
check('empty dir emits nothing and exits 0', () => {
  withTempDir('disclosure-home-', (tmpHome) => {
    withTempDir('disclosure-cwd-', (tmpCwd) => {
      writeStaticMap(tmpHome, fs.readFileSync(FIXTURE_PATH, 'utf8'));

      const result = runDisclosure(tmpHome, tmpCwd);
      assert.strictEqual(result.status, 0, `exit code: ${result.status}, stderr: ${result.stderr}`);
      assert.strictEqual(result.stdout.trim(), '', 'expected empty stdout');
    });
  });
});

// (c) A corrupt map must fail silently even when a stack marker IS present —
// the corruption in the map must never surface as an error.
check('corrupt map emits nothing and exits 0', () => {
  withTempDir('disclosure-home-', (tmpHome) => {
    withTempDir('disclosure-cwd-', (tmpCwd) => {
      writeStaticMap(tmpHome, '{ this is not valid JSON ');
      fs.writeFileSync(path.join(tmpCwd, 'next.config.mjs'), 'export default {};\n');

      const result = runDisclosure(tmpHome, tmpCwd);
      assert.strictEqual(result.status, 0, `exit code: ${result.status}, stderr: ${result.stderr}`);
      assert.strictEqual(result.stdout.trim(), '', 'expected empty stdout');
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
