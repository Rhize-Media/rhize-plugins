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
// MAP RESOLUTION: an installed plugin cannot see this repo's `generated/`
// directory, so resolution always goes through the machine-local
// ~/.claude/context-manager/ install location, in preference order:
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

function wordsOf(value) {
  return String(value || '')
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter(Boolean);
}

function tokenize(prompt) {
  return new Set(wordsOf(prompt));
}

// Returns the single best-matching skill, or null if none qualifies.
//
// Single pass over doc.nodes to collect skill nodes and pre-tokenize every
// tag node's name once, plus edges bucketed by their `from` id, so the ranking
// loop below only ever touches each skill's own topic-tag/stack-tag edges
// instead of rescanning doc.edges per skill (was O(skills * edges)).
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
  for (const edge of doc.edges) {
    if (edge.type !== 'topic-tag' && edge.type !== 'stack-tag') continue;
    let bucket = tagEdgesByFrom.get(edge.from);
    if (!bucket) {
      bucket = [];
      tagEdgesByFrom.set(edge.from, bucket);
    }
    bucket.push(edge);
  }

  let best = null; // { skillId, score, signals }

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
    if (
      !best ||
      score > best.score ||
      (score === best.score && skill.id < best.skillId)
    ) {
      best = { skillId: skill.id, score, signals };
    }
  }

  return best;
}

// Reads stdin, ranks the prompt against the map, and returns the suggestion
// message, or null if nothing qualifies. Throws on any unreadable/corrupt
// input; main()'s try/catch turns that into the same silent no-op.
function computeMessage() {
  const raw = fs.readFileSync(0, 'utf8');
  const data = JSON.parse(raw);
  const prompt = typeof data.prompt === 'string' ? data.prompt : '';
  if (!prompt) return null;

  const doc = readMap();
  if (!doc) return null;

  const match = route(doc, tokenize(prompt));
  if (!match) return null;

  const idMatch = /^skill:([^/]+)\/(.+)$/.exec(match.skillId);
  if (!idMatch) return null;
  const [, plugin, skillName] = idMatch;
  const why = match.signals.map((s) => s.label).join(', ');
  return `Consider the ${plugin}:${skillName} skill (matches ${why})`;
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
