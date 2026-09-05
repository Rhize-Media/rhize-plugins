'use strict';

// route-core.js — shared primitives extracted from skill-router.js
// (rhize-context-manager/hooks/skill-router.js) so a second routing hook
// (agent-brief-router.js) can reuse index/map reading, tokenization, and
// scoring without duplicating the ranking logic.
//
// Everything here is a primitive: reading the index/map files, tokenizing
// prompts, and the two scoring algorithms (index-backed and map-scan
// fallback), plus the shared qualification floor (>= 2 matched signals, at
// least one full-weight). Policy — score thresholds, the one-suggestion cap,
// and message/output shaping — stays per-hook, since briefs need different
// calibration than prompts. See
// skill-router.js's header comments for the full INDEX RESOLUTION / MAP
// RESOLUTION / RANKING contract these primitives implement.

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

function readMap() {
  const dir = resolveContextManagerDir();
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

// Splits a "skill:<...>" id into { plugin, skill } for display, dropping a
// leading marketplace segment on a third-party ecosystem id
// (skill:<marketplace>/<plugin>/<skill-dir>, see build_local_skill_map.py's
// third-party inventory) so it renders the same "<plugin>:<skill>" shape as
// this repo's own two-segment ids (skill:<plugin>/<name>). Returns null for
// anything that isn't a "skill:" id with exactly 2 or 3 slash-separated
// segments.
function splitSkillId(skillId) {
  const match = /^skill:(.+)$/.exec(String(skillId || ''));
  if (!match) return null;
  const parts = match[1].split('/');
  if (parts.length === 2) return { plugin: parts[0], skill: parts[1] };
  if (parts.length === 3) return { plugin: parts[1], skill: parts[2] };
  return null;
}

// "<plugin>:<skill>" display form of a skill id, shared by skill-router.js's
// suggestion message and agent-brief-router.js's directive matching/advisory
// text. See splitSkillId() for the segment rule; returns null for the same
// inputs splitSkillId() rejects.
function formatSkillRef(skillId) {
  const split = splitSkillId(skillId);
  return split ? safeLabel(`${split.plugin}:${split.skill}`) : null;
}

// A matched router signal's display label, suffixed "(inferred)" for a
// tag-inferred signal (see build_local_skill_map.py's infer_tags_for_skill())
// so a suggestion's "matches ..." text distinguishes a half-weight guessed
// tag from a declared name/tag match. Signals from the map-scanning fallback
// path (route(), not routeFromIndex()) never carry a `kind` field and so
// never get the suffix — see docs/skill-map.md's documented divergence.
// Display boundary for index-sourced text: the resolved index is written by
// build_local_skill_map.py from third-party plugin file names, so strip
// C0/C1 control, zero-width, and bidi-override characters again here rather
// than trust the writer (a second-language consumer of the same JSON file).
const UNSAFE_LABEL_RE = /[\u0000-\u001f\u007f-\u009f\u200b-\u200f\u202a-\u202e\u2066-\u2069]/g;
function safeLabel(value) {
  return String(value == null ? '' : value).replace(UNSAFE_LABEL_RE, '');
}

function formatSignalLabel(signal) {
  const label = safeLabel(signal.label);
  return signal.kind === 'tag-inferred' ? `${label} (inferred)` : label;
}

// A leading explicit request is stronger than inferred tags. Matching is exact and
// unique across the loaded inventory; negation/prose mentions use ordinary scoring.
function explicitRequest(skillIds, prompt) {
  if (/^(?:please\s+)?(?:do not|don't|never)\s+(?:use|invoke|run)\s+/i.test(String(prompt || '').trim())) return null;
  const directive = /^(?:please\s+)?(?:use|invoke|run)\s+[`/]?([a-z0-9][a-z0-9_:-]*)(?=[`\s.,;!?]|$)/i.exec(String(prompt || '').trim());
  if (!directive) return undefined;
  const requested = directive[1].toLowerCase();
  const matches = skillIds.filter((id) => {
    const ref = formatSkillRef(id);
    const parts = splitSkillId(id);
    return ref && parts && (requested.includes(':') ? ref.toLowerCase() === requested : parts.skill.toLowerCase() === requested);
  });
  if (matches.length === 0) return undefined;
  if (matches.length !== 1) return null;
  return { skillId: matches[0], score: 3, signals: [{ weight: 3, label: 'explicit skill request' }] };
}

// Index-backed equivalent of route() below: identical scoring/tie-break
// rules, sourced from the router index's precomputed per-skill signal lists
// (build_skill_map.py's build_router_index()) instead of walking
// doc.nodes/doc.edges. See route()'s docstring for the shared semantics.
function routeFromIndex(routerIndex, promptTokens, prompt) {
  const signalsBySkill = routerIndex.signals || {};
  const explicit = explicitRequest(Object.keys(signalsBySkill), prompt);
  if (explicit !== undefined) return explicit;
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
    // Floor: at least one full-weight (declared) signal among the matches. Inferred signals
    // are sub-unit weight, so an inferred-only match never qualifies; the weight math
    // (max 1 + 3*0.5 = 2.5 < name + declared tag = 3) is what keeps them from outranking.
    if (!matched.some((s) => s.weight >= 1)) continue;
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
function route(doc, promptTokens, prompt) {
  const explicit = explicitRequest(doc.nodes.filter((n) => n.kind === 'skill').map((n) => n.id), prompt);
  if (explicit !== undefined) return explicit;
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

module.exports = {
  readIndexes,
  readMap,
  tokenize,
  wordsOf,
  splitSkillId,
  formatSkillRef,
  formatSignalLabel,
  safeLabel,
  routeFromIndex,
  route,
  contextHash,
  logSuggestion,
  resolveContextManagerDir,
  resolveLogPath,
};
