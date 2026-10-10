'use strict';

// route-core.js — shared primitives extracted from skill-router.js
// (rhize-context-manager/hooks/skill-router.js) so a second routing hook
// (agent-brief-router.js) can reuse index/map reading, tokenization, and
// scoring without duplicating the ranking logic.
//
// Everything here is a primitive: reading the index/map files, tokenizing
// prompts (with plural folding, see normalizeWord()), the shared matcher
// (matchSignals()/scoreCandidates()/pickBest()) that both entry points —
// index-backed routeFromIndex() and the map-scan fallback route() — score
// through, plus the shared qualification floor (>= 2 matched signals, at
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

// Plural folding applied to every matched word, on BOTH sides of a match:
// prompt tokens (tokenize()) and signal labels (wordsOf() inside
// matchSignals()), so "obsidian bases" meets the `obsidian-bases` name and
// "meeting notes" meets a `note`-bearing label. Deliberately tiny: `-ies` ->
// `-y` (len > 4) and a trailing `-s` that isn't `-ss` (len > 3) — nothing
// else. No `-ing`/`-ed` folding: that would merge `testing` into `test` and
// change which skill a prompt names. Known harmless collisions (news -> new,
// nextjs -> nextj, status -> statu, analysis -> analysi, canvas -> canva)
// apply identically to labels and prompts, so they never create a match that
// the unfolded words would not also have created against the same spelling.
// Mirrored byte-for-byte by build_local_skill_map.py's _normalize_word();
// tests/skill-map/fixtures/stem-parity.json pins both implementations.
function normalizeWord(word) {
  const w = String(word);
  if (w.length > 4 && w.endsWith('ies')) return w.slice(0, -3) + 'y';
  if (w.length > 3 && w.endsWith('s') && !w.endsWith('ss')) return w.slice(0, -1);
  return w;
}

// Lowercase, split on runs of non-alphanumerics, drop empties — no folding.
// Used only where the original spelling matters (shadow-mode task hints);
// matching always goes through wordsOf().
function rawWordsOf(value) {
  return String(value || '')
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter(Boolean);
}

// The match-time word split: rawWordsOf() + normalizeWord(). Display text
// never passes through here — labels are printed from signal.label as-is.
function wordsOf(value) {
  return rawWordsOf(value).map(normalizeWord);
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
// path (route(), not routeFromIndex()) carry only `tag`/`name`/`name-partial`
// kinds (no inference there) and so never get the suffix — see
// docs/skill-map/edge-semantics.md's documented divergence. A `name-partial`
// signal's label already ends in " (partial)" (see matchSignals()).
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

// ---------------------------------------------------------------------------
// Shared matcher. routeFromIndex(), route() and skill-router.js's
// shadowShortlist() all score through scoreCandidates() so the three can't
// drift apart.
//
// MATCH RULE: a signal matches when every word of its label (wordsOf(): lowercased, split on
// non-alphanumerics, plural-folded) is in the prompt token set (tokenize(), same folding).
//
// PARTIAL NAME (P1): when a skill's name has 3+ words, its full name did NOT
// match, and exactly one of its name words is missing from the prompt, the
// skill gets one extra matched signal {kind: "name-partial", weight: 0.5,
// label: "<name> (partial)"}. Sub-unit weight, so it never satisfies the
// full-weight floor on its own. GUARD: if ANY skill's full name matched for
// this prompt, every partial-name signal is suppressed for this prompt — a
// sibling's near-miss must never outrank (or qualify against) a skill the
// user actually named. Name signals are identified by kind "name"; a
// signal list without one (none in shipped data) simply gets no partial.
// ---------------------------------------------------------------------------

const PARTIAL_NAME_WEIGHT = 0.5;
const PARTIAL_NAME_MIN_WORDS = 3;

// Per-skill pass: which signals fully match, whether the skill's own name
// fully matched, and the partial-name signal it would get (null when not
// eligible). Pure; the cross-skill guard is applied by scoreCandidates().
function matchSignals(signals, promptTokens) {
  const matched = [];
  let nameMatched = false;
  let partial = null;
  for (const sig of signals || []) {
    const words = wordsOf(sig.label);
    if (words.length === 0) continue;
    let missing = 0;
    for (const w of words) if (!promptTokens.has(w)) missing += 1;
    if (missing === 0) {
      matched.push(sig);
      if (sig.kind === 'name') nameMatched = true;
    } else if (
      sig.kind === 'name' &&
      partial === null &&
      words.length >= PARTIAL_NAME_MIN_WORDS &&
      missing === 1
    ) {
      partial = { kind: 'name-partial', weight: PARTIAL_NAME_WEIGHT, label: `${String(sig.label)} (partial)` };
    }
  }
  return { matched, nameMatched, partial: nameMatched ? null : partial };
}

// Qualification floor shared by every caller: >= 2 matched signals, at least
// one full-weight (weight >= 1: a name, a declared tag, or a phrase). Inferred
// and partial-name signals are sub-unit, so they can add score and count
// toward the 2-signal minimum but never qualify a skill on their own.
function qualifies(matched) {
  return matched.length >= 2 && matched.some((s) => s.weight >= 1);
}

// Scores every skill in `entries` (an iterable of [skillId, signals]) against
// the prompt tokens. Returns Map skillId -> { score, signals } holding only
// qualifying skills; signals keep their input order, a partial-name signal
// (if any) last.
function scoreCandidates(entries, promptTokens) {
  const perSkill = [];
  let anyFullName = false;
  for (const [skillId, signals] of entries) {
    const result = matchSignals(signals, promptTokens);
    if (result.nameMatched) anyFullName = true;
    perSkill.push([skillId, result]);
  }
  const scored = new Map();
  for (const [skillId, result] of perSkill) {
    const matched = !anyFullName && result.partial ? [...result.matched, result.partial] : result.matched;
    if (!qualifies(matched)) continue;
    scored.set(skillId, { score: matched.reduce((sum, s) => sum + s.weight, 0), signals: matched });
  }
  return scored;
}

// EXTENDS TIE-BREAK + final pick, shared by routeFromIndex() and route().
// `extendsEntries` is an iterable of [extenderId, iterable of baseIds]. A
// qualifying extender scoring >= its base drops the base (the extender is
// more specific); then the highest score wins, ties broken on skill id.
function pickBest(scored, extendsEntries) {
  for (const [extenderId, bases] of extendsEntries) {
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

// Index-backed equivalent of route() below: identical scoring/tie-break
// rules, sourced from the router index's precomputed per-skill signal lists
// (build_skill_map.py's build_router_index()) instead of walking
// doc.nodes/doc.edges. Floor reminder: inferred signals are sub-unit weight,
// so an inferred-only match never qualifies; the weight math (max 1 + 3*0.5 =
// 2.5 < name + declared tag = 3) is what keeps them from outranking.
function routeFromIndex(routerIndex, promptTokens, prompt) {
  const signalsBySkill = routerIndex.signals || {};
  const explicit = explicitRequest(Object.keys(signalsBySkill), prompt);
  if (explicit !== undefined) return explicit;
  const scored = scoreCandidates(Object.entries(signalsBySkill), promptTokens);
  return pickBest(scored, Object.entries(routerIndex.extendsBases || {}));
}

// Map-scan fallback: returns the single best-matching skill, or null if none
// qualifies.
//
// Single pass over doc.nodes to collect skill and tag nodes, plus edges
// bucketed by their `from` id, so each skill's signal list is built from only
// its own topic-tag/stack-tag edges (not a rescan of doc.edges per skill).
// The list mirrors build_router_index()'s shape — {kind: "tag", weight: 2}
// per tag edge, then {kind: "name", weight: 1} — and is scored by the same
// scoreCandidates()/pickBest() as routeFromIndex(), so partial-name signals
// and the guard behave identically on both paths.
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
  const tagNames = new Map(); // tagId -> name
  for (const node of doc.nodes) {
    if (node.kind === 'skill') {
      skills.push(node);
    } else if (node.kind === 'tag') {
      tagNames.set(node.id, node.name);
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

  const entries = skills.map((skill) => {
    const signals = [];
    for (const edge of tagEdgesByFrom.get(skill.id) || []) {
      if (!tagNames.has(edge.to)) continue;
      signals.push({ kind: 'tag', weight: 2, label: String(tagNames.get(edge.to)) });
    }
    signals.push({ kind: 'name', weight: 1, label: String(skill.name) });
    return [skill.id, signals];
  });

  return pickBest(scoreCandidates(entries, promptTokens), extendsBasesByFrom);
}

module.exports = {
  readIndexes,
  readMap,
  tokenize,
  wordsOf,
  rawWordsOf,
  normalizeWord,
  matchSignals,
  scoreCandidates,
  pickBest,
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
