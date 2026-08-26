#!/usr/bin/env node
'use strict';

// test_agent_brief_router.js — exercises
// rhize-context-manager/hooks/agent-brief-router.js (Task 5 of
// .claude/plans/subagent-skill-injection.md) end-to-end via spawnSync, so it
// validates exactly what the PreToolUse hook harness invokes: stdin in,
// stdout/exit code out.
//
// Modeled directly on test_router.js: every case runs with HOME pointed at a
// temp directory — never the real ~/.claude — so route-core's resolution
// (~/.claude/context-manager/skill-map.indexes.{resolved,}.json, then
// skill-map.{resolved,static}.json) reads only the fixture this test wrote.
//
// The fixtures (valid-map.json / indexes-valid-map.json) contain exactly ONE
// skill — skill:rhize-context-manager/graphify, tagged tag:topic/context
// (weight 2) and tag:stack/git (weight 2), with name signal "graphify"
// (weight 1) — verified 2026-08-26. All cases below use it.

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
  'agent-brief-router.js'
);
const FIXTURE_PATH = path.join(__dirname, 'fixtures', 'valid-map.json');
const INDEX_FIXTURE_PATH = path.join(__dirname, 'fixtures', 'indexes-valid-map.json');

const GRAPHIFY_ID = 'skill:rhize-context-manager/graphify';

// Same matched prompt as test_router.js's positive case: two tag signals
// (context, git), score 4 — clears BRIEF_MIN_SCORE.
const MATCHED_PROMPT = 'help me get git and context tooling set up';

function withTempHome(fn) {
  const tmpHome = fs.mkdtempSync(path.join(os.tmpdir(), 'brief-router-test-'));
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

// Runs the hook with a well-formed PreToolUse Agent-dispatch stdin payload.
// extraEnv is applied last so a test can opt into RHIZE_AGENT_BRIEF_ADVISORY
// or RHIZE_SUGGESTION_LOG; both are always deleted first so an ambient value
// in the outer shell can never leak into a case that expects it unset — an
// ambient RHIZE_SUGGESTION_LOG would otherwise let a case silently append a
// row to a real measurement log instead of its own temp file.
function runHook(tmpHome, prompt, subagentType, extraEnv) {
  const env = { ...process.env, HOME: tmpHome };
  delete env.RHIZE_AGENT_BRIEF_ADVISORY;
  delete env.RHIZE_SUGGESTION_LOG;
  Object.assign(env, extraEnv || {});
  return spawnSync(process.execPath, [HOOK_PATH], {
    input: JSON.stringify({
      tool_name: 'Agent',
      tool_input: { prompt, subagent_type: subagentType },
    }),
    env,
    encoding: 'utf8',
    timeout: 5000,
  });
}

// Runs the hook with raw (possibly non-JSON) stdin, for the malformed-input case.
function runHookRaw(tmpHome, rawInput, extraEnv) {
  const env = { ...process.env, HOME: tmpHome };
  delete env.RHIZE_AGENT_BRIEF_ADVISORY;
  delete env.RHIZE_SUGGESTION_LOG;
  Object.assign(env, extraEnv || {});
  return spawnSync(process.execPath, [HOOK_PATH], {
    input: rawInput,
    env,
    encoding: 'utf8',
    timeout: 5000,
  });
}

function readLogLines(logPath) {
  if (!fs.existsSync(logPath)) return [];
  return fs.readFileSync(logPath, 'utf8').trim().split('\n').filter(Boolean);
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

// 1. Named-skill detection (directive form): a brief containing
// "Invoke rhize-context-manager:graphify first" must record the canonical map
// id in namedSkills, and (env flag unset) must emit no advisory on stdout.
check('[named] directive-form mention is recorded as a named skill', () => {
  withTempHome((tmpHome) => {
    writeIndexes(tmpHome, fs.readFileSync(INDEX_FIXTURE_PATH, 'utf8'));
    const logDir = fs.mkdtempSync(path.join(os.tmpdir(), 'brief-log-'));
    const logPath = path.join(logDir, 'suggestion-log.jsonl');
    try {
      const brief =
        'Invoke rhize-context-manager:graphify first, then summarize the results.';
      const result = runHook(tmpHome, brief, 'general-purpose', {
        RHIZE_SUGGESTION_LOG: logPath,
      });
      assert.strictEqual(result.status, 0, `exit code: ${result.status}, stderr: ${result.stderr}`);
      assert.strictEqual(result.stdout.trim(), '', 'expected no advisory (env flag unset)');
      const lines = readLogLines(logPath);
      assert.strictEqual(lines.length, 1, `expected exactly one log line, got ${lines.length}`);
      const entry = JSON.parse(lines[0]);
      assert.deepStrictEqual(entry.namedSkills, [GRAPHIFY_ID]);
    } finally {
      fs.rmSync(logDir, { recursive: true, force: true });
    }
  });
});

// 2. Prose mention does NOT count: no "Invoke" directive present -> namedSkills
// must be empty even though the skill is named in prose.
check('[named] prose mention without the Invoke directive does not count', () => {
  withTempHome((tmpHome) => {
    writeIndexes(tmpHome, fs.readFileSync(INDEX_FIXTURE_PATH, 'utf8'));
    const logDir = fs.mkdtempSync(path.join(os.tmpdir(), 'brief-log-'));
    const logPath = path.join(logDir, 'suggestion-log.jsonl');
    try {
      const brief = 'the rhize-context-manager:graphify skill is relevant here';
      const result = runHook(tmpHome, brief, 'general-purpose', {
        RHIZE_SUGGESTION_LOG: logPath,
      });
      assert.strictEqual(result.status, 0, `exit code: ${result.status}, stderr: ${result.stderr}`);
      const lines = readLogLines(logPath);
      assert.strictEqual(lines.length, 1, `expected exactly one log line, got ${lines.length}`);
      const entry = JSON.parse(lines[0]);
      assert.deepStrictEqual(entry.namedSkills, []);
    } finally {
      fs.rmSync(logDir, { recursive: true, force: true });
    }
  });
});

// 3. Suggestion logging: a brief matching the fixture's graphify topic signals
// (the same matched prompt as test_router.js, padded to a realistic brief
// length) must log source: "agent-dispatch", suggestedSkills with the
// canonical id, advisoryEmitted: false (env flag unset), and NO "hook" key —
// the legacy-reader invisibility is load-bearing.
check('[log] matching brief logs source=agent-dispatch with no "hook" key', () => {
  withTempHome((tmpHome) => {
    writeIndexes(tmpHome, fs.readFileSync(INDEX_FIXTURE_PATH, 'utf8'));
    const logDir = fs.mkdtempSync(path.join(os.tmpdir(), 'brief-log-'));
    const logPath = path.join(logDir, 'suggestion-log.jsonl');
    try {
      const brief = `${MATCHED_PROMPT}. ${'lorem ipsum dolor sit amet. '.repeat(40)}`;
      const result = runHook(tmpHome, brief, 'general-purpose', {
        RHIZE_SUGGESTION_LOG: logPath,
      });
      assert.strictEqual(result.status, 0, `exit code: ${result.status}, stderr: ${result.stderr}`);
      assert.strictEqual(result.stdout.trim(), '', 'expected no advisory (env flag unset)');
      const lines = readLogLines(logPath);
      assert.strictEqual(lines.length, 1, `expected exactly one log line, got ${lines.length}`);
      const entry = JSON.parse(lines[0]);
      assert.strictEqual(entry.source, 'agent-dispatch');
      assert.deepStrictEqual(entry.suggestedSkills, [GRAPHIFY_ID]);
      assert.strictEqual(entry.advisoryEmitted, false);
      assert.ok(!Object.prototype.hasOwnProperty.call(entry, 'hook'), 'entry must have no "hook" key');
    } finally {
      fs.rmSync(logDir, { recursive: true, force: true });
    }
  });
});

// 4. Privacy: the log entry carries briefHash + briefLength only — no key's
// value contains the raw brief text.
check('[log] privacy: no logged value contains the raw brief text', () => {
  withTempHome((tmpHome) => {
    writeIndexes(tmpHome, fs.readFileSync(INDEX_FIXTURE_PATH, 'utf8'));
    const logDir = fs.mkdtempSync(path.join(os.tmpdir(), 'brief-log-'));
    const logPath = path.join(logDir, 'suggestion-log.jsonl');
    try {
      const brief = `${MATCHED_PROMPT}. ${'lorem ipsum dolor sit amet. '.repeat(40)}`;
      const result = runHook(tmpHome, brief, 'general-purpose', {
        RHIZE_SUGGESTION_LOG: logPath,
      });
      assert.strictEqual(result.status, 0, `exit code: ${result.status}, stderr: ${result.stderr}`);
      const lines = readLogLines(logPath);
      assert.strictEqual(lines.length, 1, `expected exactly one log line, got ${lines.length}`);
      const entry = JSON.parse(lines[0]);
      assert.ok(typeof entry.briefHash === 'string' && entry.briefHash.length === 16);
      assert.strictEqual(entry.briefLength, brief.length);
      for (const [key, value] of Object.entries(entry)) {
        assert.ok(
          !(typeof value === 'string' && value.includes('lorem ipsum')),
          `key "${key}" leaks raw brief text`
        );
      }
    } finally {
      fs.rmSync(logDir, { recursive: true, force: true });
    }
  });
});

// 5. Corrupt/missing map: no fixture files at all in the temp HOME -> exit 0,
// empty stdout, and NO log write whatsoever.
check('[degrade] missing map/indexes: exit 0, no output, no log write', () => {
  withTempHome((tmpHome) => {
    const logDir = fs.mkdtempSync(path.join(os.tmpdir(), 'brief-log-'));
    const logPath = path.join(logDir, 'suggestion-log.jsonl');
    try {
      const result = runHook(tmpHome, MATCHED_PROMPT, 'general-purpose', {
        RHIZE_SUGGESTION_LOG: logPath,
      });
      assert.strictEqual(result.status, 0, `exit code: ${result.status}, stderr: ${result.stderr}`);
      assert.strictEqual(result.stdout.trim(), '', 'expected empty stdout');
      assert.ok(!fs.existsSync(logPath), 'expected no log file to be created at all');
    } finally {
      fs.rmSync(logDir, { recursive: true, force: true });
    }
  });
});

// 6. Malformed stdin ("not json") -> exit 0, empty stdout.
check('[degrade] malformed stdin: exit 0, empty stdout', () => {
  withTempHome((tmpHome) => {
    writeIndexes(tmpHome, fs.readFileSync(INDEX_FIXTURE_PATH, 'utf8'));
    const result = runHookRaw(tmpHome, 'not json');
    assert.strictEqual(result.status, 0, `exit code: ${result.status}, stderr: ${result.stderr}`);
    assert.strictEqual(result.stdout.trim(), '', 'expected empty stdout');
  });
});

// 7. Score gate: a brief clearing the built-in two-signal floor but scoring
// below BRIEF_MIN_SCORE (name signal weight 1 + one tag signal weight 2 = 3,
// per the fixture's signal weights as of 2026-08-26) must still log an entry,
// but with suggestedSkills empty — the miss-rate denominator needs the row.
check('[score-gate] two signals but score below BRIEF_MIN_SCORE logs an empty suggestion', () => {
  withTempHome((tmpHome) => {
    writeIndexes(tmpHome, fs.readFileSync(INDEX_FIXTURE_PATH, 'utf8'));
    const logDir = fs.mkdtempSync(path.join(os.tmpdir(), 'brief-log-'));
    const logPath = path.join(logDir, 'suggestion-log.jsonl');
    try {
      // Matches only the "graphify" name signal (weight 1) and the "context"
      // tag signal (weight 2) = score 3; deliberately no "git" word, so the
      // "stack/git" tag signal (weight 2) never fires.
      const brief = 'please handle the graphify context task carefully for the team';
      const result = runHook(tmpHome, brief, 'general-purpose', {
        RHIZE_SUGGESTION_LOG: logPath,
      });
      assert.strictEqual(result.status, 0, `exit code: ${result.status}, stderr: ${result.stderr}`);
      const lines = readLogLines(logPath);
      assert.strictEqual(lines.length, 1, `expected exactly one log line, got ${lines.length}`);
      const entry = JSON.parse(lines[0]);
      assert.deepStrictEqual(entry.suggestedSkills, []);
    } finally {
      fs.rmSync(logDir, { recursive: true, force: true });
    }
  });
});

// 8. Static-map fallback: with only valid-map.json present (no indexes file at
// all), the map-scanning route() path must find the same canonical candidate.
check('[fallback] no indexes file: map-scan path logs the same canonical candidate', () => {
  withTempHome((tmpHome) => {
    writeStaticMap(tmpHome, fs.readFileSync(FIXTURE_PATH, 'utf8'));
    const logDir = fs.mkdtempSync(path.join(os.tmpdir(), 'brief-log-'));
    const logPath = path.join(logDir, 'suggestion-log.jsonl');
    try {
      const brief = `${MATCHED_PROMPT}. ${'lorem ipsum dolor sit amet. '.repeat(40)}`;
      const result = runHook(tmpHome, brief, 'general-purpose', {
        RHIZE_SUGGESTION_LOG: logPath,
      });
      assert.strictEqual(result.status, 0, `exit code: ${result.status}, stderr: ${result.stderr}`);
      const lines = readLogLines(logPath);
      assert.strictEqual(lines.length, 1, `expected exactly one log line, got ${lines.length}`);
      const entry = JSON.parse(lines[0]);
      assert.deepStrictEqual(entry.suggestedSkills, [GRAPHIFY_ID]);
    } finally {
      fs.rmSync(logDir, { recursive: true, force: true });
    }
  });
});

// 9. Advisory (only implemented because Task 3's V2 verdict passed): with
// RHIZE_AGENT_BRIEF_ADVISORY=1, a matching brief with no named skills must
// emit exactly one hookSpecificOutput.additionalContext line; the same brief
// with the directive-form naming added must emit no advisory at all.
check('[advisory] fires only when suggested and named skills are disjoint', () => {
  withTempHome((tmpHome) => {
    writeIndexes(tmpHome, fs.readFileSync(INDEX_FIXTURE_PATH, 'utf8'));

    const unnamed = runHook(tmpHome, MATCHED_PROMPT, 'general-purpose', {
      RHIZE_AGENT_BRIEF_ADVISORY: '1',
    });
    assert.strictEqual(unnamed.status, 0, `exit code: ${unnamed.status}, stderr: ${unnamed.stderr}`);
    const unnamedStdout = unnamed.stdout.trim();
    assert.ok(unnamedStdout.length > 0, 'expected an advisory line');
    const unnamedLines = unnamedStdout.split('\n').filter(Boolean);
    assert.strictEqual(unnamedLines.length, 1, `expected exactly one line, got ${unnamedLines.length}`);
    const parsed = JSON.parse(unnamedLines[0]);
    const ctx = parsed.hookSpecificOutput && parsed.hookSpecificOutput.additionalContext;
    assert.ok(ctx, 'expected hookSpecificOutput.additionalContext');
    assert.strictEqual(
      ctx,
      'Brief for general-purpose may map to rhize-context-manager:graphify — consider naming it ' +
        '("Invoke rhize-context-manager:graphify first") or inlining its operative content on the next dispatch.'
    );

    const namedBrief = `${MATCHED_PROMPT} Invoke rhize-context-manager:graphify first.`;
    const named = runHook(tmpHome, namedBrief, 'general-purpose', {
      RHIZE_AGENT_BRIEF_ADVISORY: '1',
    });
    assert.strictEqual(named.status, 0, `exit code: ${named.status}, stderr: ${named.stderr}`);
    assert.strictEqual(named.stdout.trim(), '', 'expected no advisory when the skill is already named');
  });
});

if (failures > 0) {
  console.error(`\n${failures} test(s) failed.`);
  process.exit(1);
} else {
  console.log('\nAll agent-brief-router tests passed.');
  process.exit(0);
}
