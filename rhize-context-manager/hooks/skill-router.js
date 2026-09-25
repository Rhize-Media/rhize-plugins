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
// BUDGET: <150ms warm without workflow opt-in; opt-in bridge deadline 4.5s.
// No network; the optional metadata selector is a bounded child. The map is read
// synchronously once per invocation.

const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const os = require('os');
const { execFileSync } = require('child_process');

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

function shadowShortlist(index, promptTokens, incumbent) {
  if (!index || !incumbent || incumbent.signals.some((signal) => signal.label === 'explicit skill request')) return null;
  const scored = [];
  for (const [skillId, signals] of Object.entries(index.signals || {})) {
    const matched = signals.filter((signal) => {
      const words = [...tokenize(signal.label)];
      return words.length > 0 && words.every((word) => promptTokens.has(word));
    });
    if (matched.length < 2 || !matched.some((signal) => signal.weight >= 1)) continue;
    scored.push({ skillId, score: matched.reduce((sum, signal) => sum + signal.weight, 0), signals: matched });
  }
  scored.sort((a, b) => b.score - a.score || a.skillId.localeCompare(b.skillId));
  const selected = scored.slice(0, 5);
  if (!selected.some((item) => item.skillId === incumbent.skillId)) {
    selected.pop();
    selected.push({ skillId: incumbent.skillId, score: incumbent.score, signals: incumbent.signals });
  }
  if (!selected.length) return null;
  const id = (skillId) => 's' + crypto.createHash('sha256').update(skillId).digest('hex').slice(0, 16);
  const hint = (label) => String(label).toLowerCase().replace(/[^a-z0-9_-]+/g, '-').replace(/^-|-$/g, '').slice(0, 48);
  const taskSignals = [...new Set(selected.flatMap((item) => item.signals.flatMap((signal) => [...tokenize(signal.label)])))].filter((word) => /^[a-z][a-z0-9_-]{0,47}$/.test(word)).slice(0, 8);
  return {
    schema: 'rhize-typed-candidates-v1', capability: 'skill_workflow',
    sourceSha256: crypto.createHash('sha256').update(JSON.stringify(index)).digest('hex'),
    taskSignals,
    candidates: selected.map((item) => ({ id: id(item.skillId), hints: item.signals.map((signal) => hint(signal.label)).filter(Boolean).slice(0, 6), protected: false })),
    incumbentIds: [id(incumbent.skillId)],
  };
}

function shadowSkillDecision(index, promptTokens, incumbent, workflowHandled) {
  if (process.env.RHIZE_LAYA_SKILL_SHADOW !== '1' || workflowHandled) return null;
  const state = shadowShortlist(index, promptTokens, incumbent);
  if (!state) return null;
  try {
    const args = [path.join(__dirname, '..', 'scripts', 'context_experiments', 'typed_candidates.py'), '--mode', 'shadow'];
    if (process.env.RHIZE_LAYA_BASE_URL) args.push('--base-url', process.env.RHIZE_LAYA_BASE_URL);
    const raw = execFileSync('python3', args, {
      input: JSON.stringify(state), encoding: 'utf8', timeout: 2500, maxBuffer: 16384, stdio: ['pipe', 'pipe', 'ignore'],
    });
    const result = JSON.parse(raw);
    return { status: result.status, count: state.candidates.length };
  } catch (_) { return { status: 'unavailable', count: state.candidates.length }; }
}

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

  let workflowMessage = null;
  let workflowHandled = false;
  let workflowAttempted = false;
  // One shared selector owns opted-in workflow decisions. Both the legacy
  // router and packaged hook use its atomic receipt; configuration alone
  // never suppresses advice. A failed bridge falls back to this router.
  try {
    const root = process.env.XDG_DATA_HOME || path.join(os.homedir(), '.local', 'share');
    const cfgPath = path.join(root, 'rhize', 'workflow-selection', 'config.json');
    const cfg = JSON.parse(fs.readFileSync(cfgPath, 'utf8'));
    if (cfg.schemaVersion === 1 && cfg.enabled === true) {
      workflowAttempted = true;
      const output = execFileSync('python3', [path.join(__dirname, '..', 'scripts', 'workflow_selection.py'), 'hook', '--router-bridge'], {
        input: raw, encoding: 'utf8', timeout: 4500, maxBuffer: 16384, stdio: ['pipe','pipe','ignore'],
      });
      const bridge = JSON.parse(output);
      workflowHandled = bridge.handled === true;
      workflowMessage = bridge.hookOutput?.hookSpecificOutput?.additionalContext || null;
    }
  } catch (_) { /* missing/untrusted/unavailable selector: preserve old routing */ }

  const promptTokens = tokenize(prompt);
  const ctxHash = contextHash(prompt);

  const routerIndex = readIndexes();
  const match = routerIndex
    ? routeFromIndex(routerIndex, promptTokens, prompt)
    : (() => {
        const doc = readMap();
        return doc ? route(doc, promptTokens, prompt) : null;
      })();
  const typed = shadowSkillDecision(routerIndex, promptTokens, match, workflowAttempted);

  const overlaps = workflowHandled && match && /\/(?:rhize-content-engine|content-engine)$/.test(match.skillId) && !/\becc\b/i.test(prompt);
  const message = [workflowMessage, overlaps ? null : formatMatch(match)].filter(Boolean).join(' ') || null;
  if (message) {
    return { message, sessionId, suggested: match ? match.skillId : null, contextHash: ctxHash, typed };
  }
  return { message: null, sessionId, sampled: Math.random() < 1 / 20, contextHash: ctxHash, typed };
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
        typed_status: result.typed?.status || null,
        typed_candidate_count: result.typed?.count || null,
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
