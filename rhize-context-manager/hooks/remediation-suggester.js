#!/usr/bin/env node
'use strict';

// remediation-suggester.js — condition-driven remediation hook (PostToolUse,
// matcher "Bash"). Implements the design doc's remediation-suggester
// (docs/superpowers/specs/2026-08-09-skill-map-relationships-v2-design.md
// section 7): when a Bash command fails, match its output against the
// remediation index's condition patterns and suggest the top remediating
// skill/agent.
//
// TIER: T3 (advisory). Never blocks (always exit 0). Fails silently on any
// missing/unreadable/corrupt input, same discipline as skill-router.js and
// session-disclosure.js.
//
// FAILURE DETECTION (Bash PostToolUse payload shape): per this Claude Code
// install's shipped BashOutput type (sdk-tools.d.ts), the Bash tool_response
// is `{stdout, stderr, interrupted, isImage?, ...}` — there is NO exit-code
// or success/failure boolean field. So an explicit "no failure signal ->
// silent" gate can only rely on: (a) any success/failure field a future or
// non-Bash caller might supply (defensively checked, since a matcher can
// still route unexpected shapes through), and (b) the condition patterns
// themselves, which are written against real FAILING output text (`build
// failed`, `error TS\d+`, `CONFLICT (.*):`, etc. — see catalog/tags.json).
// A pattern match against stdout+stderr IS the failure signal for Bash; an
// explicit success field (success===true / isError===false / exitCode===0)
// short-circuits to silent even if text superficially matches, guarding
// against false positives like "webpack compiled with 0 errors".
//
// INDEX RESOLUTION: resolved-then-static, mirroring skill-router.js:
//   1. ~/.claude/context-manager/skill-map.indexes.resolved.json
//   2. ~/.claude/context-manager/skill-map.indexes.json (installed static copy)
// Neither present/parseable, or no `remediation` section -> exit 0, no output.
//
// RANKING: among conditions whose pattern matches, pick the condition with
// the most specific (first, since catalog order is curated) match; within
// that condition, skills are already sorted by id (alphabetical — no
// promotion/ranking signal exists yet, see build_skill_map.py's
// build_remediation_index). The first skill in that sorted list is the
// suggestion. At most one suggestion total, ever.
//
// EXTERNAL IDS: a remediator id of the form `external:<slug>` names a
// third-party capability that isn't a proper skill-map skill node (e.g. an
// ecc build-resolver *agent*). Phrase those as an agent suggestion
// ("ecc:react-build-resolver agent") rather than a skill invocation.
//
// BUDGET: <150ms warm. No network, no child processes.

const crypto = require('crypto');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { formatSkillRef } = require(path.join(__dirname, 'lib', 'route-core.js'));

// Suggestion logging (append-only, local-machine JSONL; see
// scripts/suggestion_log_report.py for the reader). NEVER logs raw prompt
// text, file paths, or tool output — only ids/hashes, matching
// skill-monitor's privacy precedent. Fully fail-silent: a logging failure
// must never affect the suggestion path or exit code.
// RHIZE_SUGGESTION_LOG overrides the path for testability.
function resolveContextManagerDir() {
  if (typeof process.env.RHIZE_CONTEXT_MANAGER_DIR === 'string' && process.env.RHIZE_CONTEXT_MANAGER_DIR) {
    return process.env.RHIZE_CONTEXT_MANAGER_DIR;
  }
  return path.join(os.homedir(), '.claude', 'context-manager');
}

function resolveLogPath() {
  if (typeof process.env.RHIZE_SUGGESTION_LOG === 'string' && process.env.RHIZE_SUGGESTION_LOG) {
    return process.env.RHIZE_SUGGESTION_LOG;
  }
  return path.join(os.homedir(), '.claude', 'context-manager', 'suggestion-log.jsonl');
}

function contextHash(value) {
  return crypto.createHash('sha256').update(String(value || '')).digest('hex').slice(0, 16);
}

function logSuggestion(entry) {
  try {
    const logPath = resolveLogPath();
    fs.mkdirSync(path.dirname(logPath), { recursive: true });
    fs.appendFileSync(logPath, JSON.stringify(entry) + '\n');
  } catch (_err) {
    // fail-silent: logging must never affect the suggestion path or exit code
  }
}

function readIndexes() {
  const dir = resolveContextManagerDir();
  const candidates = [
    path.join(dir, 'skill-map.indexes.resolved.json'),
    path.join(dir, 'skill-map.indexes.json'),
  ];
  for (const candidate of candidates) {
    let text;
    try {
      text = fs.readFileSync(candidate, 'utf8');
    } catch (_err) {
      continue; // missing or unreadable — try the next candidate
    }
    try {
      const doc = JSON.parse(text);
      if (doc && doc.remediation && typeof doc.remediation === 'object') {
        return doc;
      }
    } catch (_err) {
      // corrupt JSON at this path — try the next candidate
    }
  }
  return null;
}

// Returns a human-facing name for a remediator id: strips the `external:`
// prefix and phrases it as an agent suggestion; a real skill id
// (`skill:<plugin>/<name>`) is phrased as `<plugin>:<name>`.
function describeRemediator(id) {
  if (typeof id !== 'string') return null;
  if (id.startsWith('external:')) {
    const slug = id.slice('external:'.length);
    return { label: `${slug.replace(/^ecc-/, 'ecc:')} agent`, kind: 'agent' };
  }
  const ref = formatSkillRef(id);
  if (ref) return { label: `${ref} skill`, kind: 'skill' };
  // Unknown id shape — surface the raw id rather than emitting nothing, but
  // never throw.
  return { label: id, kind: 'unknown' };
}

// catalog/tags.json's condition patterns are authored as Python `re`
// patterns, which allow the `(?i)` inline case-insensitivity flag anywhere
// in the pattern; JS RegExp has no inline-flag syntax at all and throws
// "Invalid group" on `(?i)`. Every pattern in the catalog puts `(?i)` (if
// present) at the very start, so stripping a single leading occurrence and
// mapping it to the JS 'i' flag covers the real catalog without attempting
// a general Python-regex-to-JS translator.
function compilePattern(source) {
  const inlineFlag = /^\(\?i\)/.exec(source);
  const body = inlineFlag ? source.slice(inlineFlag[0].length) : source;
  return new RegExp(body, inlineFlag ? 'i' : '');
}

// Returns { conditionSlug, remediatorId } for the first condition (catalog
// order, i.e. object key insertion order from the index JSON) whose pattern
// matches `text` and which has at least one declared remediator. null if
// nothing matches.
function matchCondition(remediationIndex, text) {
  for (const [slug, entry] of Object.entries(remediationIndex)) {
    const patterns = Array.isArray(entry && entry.patterns) ? entry.patterns : [];
    const skills = Array.isArray(entry && entry.skills) ? entry.skills : [];
    if (skills.length === 0) continue; // nothing to suggest for this condition
    for (const patternSource of patterns) {
      let re;
      try {
        re = compilePattern(patternSource);
      } catch (_err) {
        continue; // malformed/unsupported pattern in the index — skip, never throw
      }
      if (re.test(text)) {
        return { conditionSlug: slug, remediatorId: skills[0] };
      }
    }
  }
  return null;
}

// Explicit success signal on tool_response, when present, short-circuits
// remediation even if the text superficially matches a pattern. Bash's real
// shape carries none of these fields today; this only guards a future or
// unexpected caller shape.
function isExplicitSuccess(toolResponse) {
  if (!toolResponse || typeof toolResponse !== 'object') return false;
  if (toolResponse.success === true) return true;
  if (toolResponse.isError === false) return true;
  if (toolResponse.is_error === false) return true;
  const exitCode = toolResponse.exitCode ?? toolResponse.exit_code ?? toolResponse.code;
  if (typeof exitCode === 'number' && exitCode === 0) return true;
  return false;
}

// Returns null (nothing to do, or no suggestion — not logged per the
// no-suggestion-invocations-are-not-logged rule), or { message, sessionId,
// suggested, contextHash } for main() to emit and log. contextHash covers the
// matched stdout+stderr snippet, never the raw text itself.
function computeMessage() {
  const raw = fs.readFileSync(0, 'utf8');
  const data = JSON.parse(raw);
  const sessionId = typeof data.session_id === 'string' ? data.session_id : null;

  const toolName = typeof data.tool_name === 'string' ? data.tool_name : '';
  if (toolName && toolName !== 'Bash') return null; // defensive; matcher already scopes this

  const toolResponse = data.tool_response;
  if (isExplicitSuccess(toolResponse)) return null;

  const stdout =
    toolResponse && typeof toolResponse.stdout === 'string' ? toolResponse.stdout : '';
  const stderr =
    toolResponse && typeof toolResponse.stderr === 'string' ? toolResponse.stderr : '';
  const text = `${stdout}\n${stderr}`;
  if (!text.trim()) return null; // no output at all — no failure signal

  const indexes = readIndexes();
  if (!indexes) return null;

  const match = matchCondition(indexes.remediation, text);
  if (!match) return null;

  const described = describeRemediator(match.remediatorId);
  if (!described) return null;

  const message = `Build failed — the ${described.label} remediates ${match.conditionSlug}`;
  return { message, sessionId, suggested: match.remediatorId, contextHash: contextHash(text) };
}

function main() {
  try {
    const result = computeMessage();
    if (result && result.message) {
      process.stdout.write(
        JSON.stringify({
          hookSpecificOutput: {
            hookEventName: 'PostToolUse',
            additionalContext: result.message,
          },
        }) + '\n'
      );
      logSuggestion({
        ts: new Date().toISOString(),
        session_id: result.sessionId,
        hook: 'remediation',
        suggested: result.suggested,
        context_hash: result.contextHash,
      });
    }
  } catch (_err) {
    // fail-silent contract: never surface an error to the user or Claude
  } finally {
    process.exit(0);
  }
}

main();
