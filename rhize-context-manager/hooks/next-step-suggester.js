#!/usr/bin/env node
'use strict';

// next-step-suggester.js — succession-driven "what's next" hook (PostToolUse,
// matcher "Skill"). Implements the design doc's next-step-suggester
// (docs/superpowers/specs/2026-08-09-skill-map-relationships-v2-design.md
// section 7): after a skill invocation, look up the succession index and
// suggest the single next step — declared `precedes` first, mined `follows`
// as a fallback. This finally gives `precedes` a runtime consumer.
//
// TIER: T3 (advisory). Never blocks (always exit 0). Fails silently on any
// missing/unreadable/corrupt input, same discipline as the other consumers
// in this directory.
//
// CONTRACT: reads hook JSON from stdin. The Skill tool's PostToolUse
// tool_input carries the invoked skill under `skill` (matches how the
// matcher "Skill" scopes this hook) — accept a couple of reasonable
// alternate shapes (`name`) defensively since this is the first consumer of
// Skill-tool PostToolUse payloads in this repo and the exact field name for
// third-party/plugin-qualified invocations isn't schema-guaranteed.
//
// ID RESOLUTION: the succession index is keyed by skill-map node ids
// (`skill:<plugin>/<name>` or `command:<plugin>/<name>`), but the Skill tool
// reports a bare `<plugin>:<name>` (or bare `<name>` for a user-level skill
// outside any plugin). Try `skill:<plugin>/<name>` first, then
// `command:<plugin>/<name>`, then a bare-name variant for either kind.
//
// SUCCESSOR CHOICE: declared `precedes` (curated intent) wins over mined
// `follows` (observed co-occurrence) when both exist — same "declared over
// mined" precedence the resolved-indexes merge itself documents. Exactly one
// successor is named (the first, alphabetically — the index already sorts
// both lists) even if several exist; no successor in either list -> silent.
//
// STATELESS BY DESIGN: this hook does not track what it has already
// suggested across invocations, so it fires every time the same skill is
// invoked and has a successor. The task's "never fire in a loop" requirement
// is satisfied structurally, not by memoized state: it only fires on an
// actual Skill tool_call, never on its own suggestion (additionalContext is
// not a tool invocation), so there is no feedback path that could loop.
//
// INDEX RESOLUTION: resolved-then-static, same as the other consumers:
//   1. ~/.claude/context-manager/skill-map.indexes.resolved.json
//   2. ~/.claude/context-manager/skill-map.indexes.json (installed static copy)
// Neither present/parseable, or no `succession` section -> exit 0, no output.
//
// BUDGET: <150ms warm. No network, no child processes.

const crypto = require('crypto');
const fs = require('fs');
const os = require('os');
const path = require('path');

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
      if (doc && doc.succession && typeof doc.succession === 'object') {
        return doc;
      }
    } catch (_err) {
      // corrupt JSON at this path — try the next candidate
    }
  }
  return null;
}

// Extracts the invoked skill's raw "<plugin>:<name>" or bare "<name>" string
// from the Skill tool's PostToolUse tool_input, or null if unrecognized.
function invokedSkillName(data) {
  const input = data && data.tool_input;
  if (!input || typeof input !== 'object') return null;
  const raw = input.skill ?? input.name;
  return typeof raw === 'string' && raw ? raw : null;
}

// Builds the candidate node ids to look up in the succession index for a raw
// "<plugin>:<name>" or bare "<name>" skill reference, most specific first.
function candidateIds(raw) {
  const colonMatch = /^([^:]+):(.+)$/.exec(raw);
  if (colonMatch) {
    const [, plugin, name] = colonMatch;
    return [`skill:${plugin}/${name}`, `command:${plugin}/${name}`];
  }
  return [`skill:${raw}`, `command:${raw}`];
}

function shortName(nodeId) {
  const idMatch = /^(?:skill|command):(?:([^/]+)\/)?(.+)$/.exec(nodeId);
  if (!idMatch) return nodeId;
  const [, plugin, name] = idMatch;
  return plugin ? `${plugin}:${name}` : name;
}

// Returns null (nothing to do — not logged, per the
// no-suggestion-invocations-are-not-logged rule), or { message, sessionId,
// suggested, contextHash } for main() to emit and log. contextHash covers the
// completed skill's id, never raw prompt text or file paths.
function computeMessage() {
  const raw = fs.readFileSync(0, 'utf8');
  const data = JSON.parse(raw);
  const sessionId = typeof data.session_id === 'string' ? data.session_id : null;

  const invoked = invokedSkillName(data);
  if (!invoked) return null;

  const indexes = readIndexes();
  if (!indexes) return null;

  const succession = indexes.succession;
  let entry = null;
  for (const id of candidateIds(invoked)) {
    if (succession[id]) {
      entry = succession[id];
      break;
    }
  }
  if (!entry) return null;

  const precedes = Array.isArray(entry.precedes) ? entry.precedes : [];
  const follows = Array.isArray(entry.follows) ? entry.follows : [];
  const successor = precedes[0] || follows[0];
  if (!successor) return null;

  const message = `After ${invoked}, the usual next step is ${shortName(successor)}`;
  return { message, sessionId, suggested: successor, contextHash: contextHash(invoked) };
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
        hook: 'next-step',
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
