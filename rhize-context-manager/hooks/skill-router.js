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
const os = require('os');
const path = require('path');

function readMap() {
  const dir = path.join(os.homedir(), '.claude', 'context-manager');
  const candidates = [
    path.join(dir, 'skill-map.resolved.json'),
    path.join(dir, 'skill-map.static.json'),
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
      if (doc && Array.isArray(doc.nodes) && Array.isArray(doc.edges)) {
        return doc;
      }
    } catch (_err) {
      // corrupt JSON at this path — try the next candidate rather than
      // failing outright, since a stale resolved map shouldn't block the
      // static fallback.
    }
  }
  return null;
}

function readIndexes() {
  const dir = path.join(os.homedir(), '.claude', 'context-manager');
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
      if (doc && doc.router && typeof doc.router === 'object') {
        return doc.router;
      }
    } catch (_err) {
      // corrupt JSON at this path — try the next candidate
    }
  }
  return null;
}

function wordsOf(value) {
  return String(value || '')
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter(Boolean);
}

function tokenize(prompt) {
  return new Set(wordsOf(prompt));
}

// Index-backed equivalent of route() below: identical scoring/tie-break
// rules, sourced from the router index's precomputed per-skill signal lists
// (build_skill_map.py's build_router_index()) instead of walking
// doc.nodes/doc.edges. See route()'s docstring for the shared semantics.
function routeFromIndex(routerIndex, promptTokens) {
  const signalsBySkill = routerIndex.signals || {};
  const extendsBases = routerIndex.extendsBases || {};

  const scored = new Map(); // skillId -> { score, signals }

  for (const [skillId, signals] of Object.entries(signalsBySkill)) {
    const matched = [];
    for (const sig of signals) {
      const words = wordsOf(sig.label);
      if (words.length > 0 && words.every((w) => promptTokens.has(w))) {
        matched.push(sig);
      }
    }
    if (matched.length < 2) continue; // single weak match must not emit
    const score = matched.reduce((sum, s) => sum + s.weight, 0);
    scored.set(skillId, { score, signals: matched });
  }

  // Same extends tie-break as route(): a qualifying extender scoring >= its
  // base drops the base from consideration.
  for (const [extenderId, bases] of Object.entries(extendsBases)) {
    const extenderResult = scored.get(extenderId);
    if (!extenderResult) continue;
    for (const baseId of bases) {
      const baseResult = scored.get(baseId);
      if (!baseResult) continue;
      if (extenderResult.score >= baseResult.score) {
        scored.delete(baseId);
      }
    }
  }

  let best = null; // { skillId, score, signals }
  for (const [skillId, result] of scored) {
    if (
      !best ||
      result.score > best.score ||
      (result.score === best.score && skillId < best.skillId)
    ) {
      best = { skillId, score: result.score, signals: result.signals };
    }
  }

  return best;
}

// Returns the single best-matching skill, or null if none qualifies.
//
// Single pass over doc.nodes to collect skill nodes and pre-tokenize every
// tag node's name once, plus edges bucketed by their `from` id, so the ranking
// loop below only ever touches each skill's own topic-tag/stack-tag edges
// instead of rescanning doc.edges per skill (was O(skills * edges)).
//
// EXTENDS TIE-BREAK: when both a base skill and one of its extenders
// (an `extends` edge from extender -> base) qualify (2+ signals), and the
// extender's score is >= the base's, the extender wins — it's the more
// specific skill. Otherwise the base wins, same as ordinary score
// comparison. This only ever affects a base/extender pair directly; it does
// not change max-one-suggestion or the 2-signal qualifying threshold.
function route(doc, promptTokens) {
  const skills = [];
  const tagsById = new Map(); // tagId -> { name, words }
  for (const node of doc.nodes) {
    if (node.kind === 'skill') {
      skills.push(node);
    } else if (node.kind === 'tag') {
      tagsById.set(node.id, { name: node.name, words: wordsOf(node.name) });
    }
  }

  const tagEdgesByFrom = new Map(); // skillId -> [topic-tag/stack-tag edge, ...]
  const extendsBasesByFrom = new Map(); // extenderId -> Set(baseId)
  for (const edge of doc.edges) {
    if (edge.type === 'topic-tag' || edge.type === 'stack-tag') {
      let bucket = tagEdgesByFrom.get(edge.from);
      if (!bucket) {
        bucket = [];
        tagEdgesByFrom.set(edge.from, bucket);
      }
      bucket.push(edge);
    } else if (edge.type === 'extends') {
      let bases = extendsBasesByFrom.get(edge.from);
      if (!bases) {
        bases = new Set();
        extendsBasesByFrom.set(edge.from, bases);
      }
      bases.add(edge.to);
    }
  }

  const scored = new Map(); // skillId -> { score, signals }

  for (const skill of skills) {
    const signals = [];

    for (const edge of tagEdgesByFrom.get(skill.id) || []) {
      const tag = tagsById.get(edge.to);
      if (!tag) continue;
      if (tag.words.length > 0 && tag.words.every((w) => promptTokens.has(w))) {
        signals.push({ weight: 2, label: String(tag.name) });
      }
    }

    const nameWords = wordsOf(skill.name);
    if (nameWords.length > 0 && nameWords.every((w) => promptTokens.has(w))) {
      signals.push({ weight: 1, label: String(skill.name) });
    }

    if (signals.length < 2) continue; // single weak match must not emit

    const score = signals.reduce((sum, s) => sum + s.weight, 0);
    scored.set(skill.id, { score, signals });
  }

  // Drop a base from consideration whenever a qualifying extender of it
  // scores at least as well — the extender is more specific and should win
  // the tie instead of falling back to alphabetical skill-id order.
  for (const [extenderId, bases] of extendsBasesByFrom) {
    const extenderResult = scored.get(extenderId);
    if (!extenderResult) continue;
    for (const baseId of bases) {
      const baseResult = scored.get(baseId);
      if (!baseResult) continue;
      if (extenderResult.score >= baseResult.score) {
        scored.delete(baseId);
      }
    }
  }

  let best = null; // { skillId, score, signals }
  for (const [skillId, result] of scored) {
    if (
      !best ||
      result.score > best.score ||
      (result.score === best.score && skillId < best.skillId)
    ) {
      best = { skillId, score: result.score, signals: result.signals };
    }
  }

  return best;
}

function formatMatch(match) {
  if (!match) return null;
  const idMatch = /^skill:([^/]+)\/(.+)$/.exec(match.skillId);
  if (!idMatch) return null;
  const [, plugin, skillName] = idMatch;
  const why = match.signals.map((s) => s.label).join(', ');
  return `Consider the ${plugin}:${skillName} skill (matches ${why})`;
}

// Reads stdin, ranks the prompt against the map, and returns the suggestion
// message, or null if nothing qualifies. Throws on any unreadable/corrupt
// input; main()'s try/catch turns that into the same silent no-op.
//
// Tries the materialized router index first (routeFromIndex); only when no
// indexes file is present/parseable does this fall back to the original
// map-scanning path (readMap/route) — see the INDEX RESOLUTION note above.
function computeMessage() {
  const raw = fs.readFileSync(0, 'utf8');
  const data = JSON.parse(raw);
  const prompt = typeof data.prompt === 'string' ? data.prompt : '';
  if (!prompt) return null;

  const promptTokens = tokenize(prompt);

  const routerIndex = readIndexes();
  if (routerIndex) {
    return formatMatch(routeFromIndex(routerIndex, promptTokens));
  }

  const doc = readMap();
  if (!doc) return null;
  return formatMatch(route(doc, promptTokens));
}

function main() {
  try {
    const message = computeMessage();
    if (message) {
      process.stdout.write(
        JSON.stringify({
          hookSpecificOutput: {
            hookEventName: 'UserPromptSubmit',
            additionalContext: message,
          },
        }) + '\n'
      );
    }
  } catch (_err) {
    // fail-silent contract: never surface an error to the user or Claude
  } finally {
    process.exit(0);
  }
}

main();
