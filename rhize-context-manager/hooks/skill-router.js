#!/usr/bin/env node
'use strict';

// skill-router.js — map-driven skill suggestion hook (UserPromptSubmit).
//
// Replaces the keyword-grep skill-suggester.sh (retired 2026-08-09, see
// SOURCES.md / CHANGELOG). Ranks the submitted prompt against the compiled
// skill-map artifact's topic-tag/stack-tag edges and skill names instead of a
// fixed regex keyword list, so new skills route automatically once tagged —
// no hook edit required.
//
// TIER: T3 (advisory). Never blocks (always exit 0). Fails silently on any
// missing/unreadable/corrupt input — a missing map, a plugin installed
// without this repo's `generated/` dir, or a malformed prompt must never
// surface an error to the user or to Claude.
//
// CONTRACT: reads hook JSON from stdin, field "prompt" (not "user_prompt" —
// see skill-suggester.sh's history in git blame for why that distinction
// matters). additionalContext must be nested inside
// hookSpecificOutput.additionalContext to reach Claude; a top-level field or
// systemMessage alone would not.
//
// INDEX RESOLUTION (relationships v2, section 7 of the design doc): the
// primary data source is now the materialized `router` index, precomputed
// by build_skill_map.py/build_local_skill_map.py so this hook never walks
// doc.edges itself. Preference order, all under
// ~/.claude/context-manager/:
//   1. skill-map.indexes.resolved.json (static + local-overlay follows merge)
//   2. skill-map.indexes.json          (installed by `build_skill_map.py --install`)
// Neither present/parseable/missing a `router` section -> FALL BACK to the
// original map-scanning path below (readMap/route), so an older install that
// only shipped skill-map.{resolved,static}.json (no indexes file yet)
// degrades gracefully instead of going silent. Behavior is identical either
// way — the index only saves re-deriving signals from doc.edges per call.
//
// MAP RESOLUTION (fallback only):
//   1. skill-map.resolved.json (static + local overlay, once Phase 3 lands)
//   2. skill-map.static.json   (installed by `build_skill_map.py --install`)
// Neither present or parseable -> exit 0, no output.
//
// RANKING: tokenize the prompt into lowercase alnum words. For every `skill`
// node, a topic-tag/stack-tag edge is a "tag signal" (weight 2) if every word
// of the tag's name is present among the prompt's tokens; the skill's own
// name is a "name signal" (weight 1) under the same all-words-present rule.
// Tag signals outweigh name signals, per the plan's "tag match > name match"
// rule. At least 2 DISTINCT signals must match for a skill to be considered
// at all — a single weak match must never emit (see plan's "Router noise"
// risk). Among qualifying skills, the highest total weight wins; ties break
// on skill id (deterministic, no randomness).
//
// BUDGET: <150ms warm. No network, no child processes; the map is read
// synchronously once per invocation.

const fs = require('fs');
const path = require('path');

// Shared primitives (index/map reading, tokenize, scoring, logging) live in
// hooks/lib/route-core.js so agent-brief-router.js can reuse them without
// duplicating the ranking logic. Policy — thresholds, the one-suggestion
// cap, and message shaping (formatMatch below) — stays in this hook.
const {
  readIndexes,
  readMap,
  tokenize,
  formatSkillRef,
  formatSignalLabel,
  routeFromIndex,
  route,
  contextHash,
  logSuggestion,
} = require(path.join(__dirname, 'lib', 'route-core.js'));

function formatMatch(match) {
  if (!match) return null;
  const ref = formatSkillRef(match.skillId);
  if (!ref) return null;
  const why = match.signals.map(formatSignalLabel).join(', ');
  return `Consider the ${ref} skill (matches ${why})`;
}

// Reads stdin, ranks the prompt against the map, and returns the suggestion
// message, or null if nothing qualifies. Throws on any unreadable/corrupt
// input; main()'s try/catch turns that into the same silent no-op.
//
// Tries the materialized router index first (routeFromIndex); only when no
// indexes file is present/parseable does this fall back to the original
// map-scanning path (readMap/route) — see the INDEX RESOLUTION note above.
// Returns null (nothing to do), or an object describing the outcome for
// main() to emit and log: { message, sessionId, suggested, contextHash } when
// a suggestion fires, or { message: null, sessionId, sampled, contextHash }
// when the prompt qualified for consideration but nothing matched (sampled is
// true 1-in-20 times, so silence precision has a denominator — see
// scripts/suggestion_log_report.py).
function computeMessage() {
  const raw = fs.readFileSync(0, 'utf8');
  const data = JSON.parse(raw);
  const prompt = typeof data.prompt === 'string' ? data.prompt : '';
  const sessionId = typeof data.session_id === 'string' ? data.session_id : null;
  if (!prompt) return null;

  const promptTokens = tokenize(prompt);
  const ctxHash = contextHash(prompt);

  const routerIndex = readIndexes();
  const match = routerIndex
    ? routeFromIndex(routerIndex, promptTokens, prompt)
    : (() => {
        const doc = readMap();
        return doc ? route(doc, promptTokens, prompt) : null;
      })();

  const message = formatMatch(match);
  if (message) {
    return { message, sessionId, suggested: match.skillId, contextHash: ctxHash };
  }
  return { message: null, sessionId, sampled: Math.random() < 1 / 20, contextHash: ctxHash };
}

function main() {
  try {
    const result = computeMessage();
    if (result && result.message) {
      process.stdout.write(
        JSON.stringify({
          hookSpecificOutput: {
            hookEventName: 'UserPromptSubmit',
            additionalContext: result.message,
          },
        }) + '\n'
      );
      logSuggestion({
        ts: new Date().toISOString(),
        session_id: result.sessionId,
        hook: 'router',
        suggested: result.suggested,
        context_hash: result.contextHash,
      });
    } else if (result && result.sampled) {
      logSuggestion({
        ts: new Date().toISOString(),
        session_id: result.sessionId,
        hook: 'router',
        suggested: null,
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
