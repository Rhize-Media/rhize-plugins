#!/usr/bin/env node
'use strict';

// session-disclosure.js — stack-aware progressive disclosure hook (SessionStart).
//
// Replaces the four per-plugin SessionStart banners retired in Phase 3 of
// .claude/plans/skill-map-graph-substrate.md (seo-aeo-geo, obsidian-second-brain,
// project-launcher, rhize-devflow) with one compact, map-driven surface:
// fingerprint the current repo against a small set of cheap file/dir existence
// checks, map any detected stack to its stack-tag edges in the compiled
// skill-map artifact, and surface at most 8 relevant skills. Silence when no
// stack is detected — a generic banner is worse than none (same principle as
// skill-router.js's "Router noise" risk, applied to disclosure).
//
// TIER: T3 (advisory). Never blocks (always exit 0). Fails silently on any
// missing/unreadable/corrupt map or stdin — mirrors skill-router.js's IO
// discipline exactly.
//
// INDEX RESOLUTION (relationships v2, section 7 of the design doc): the
// primary data source is now the materialized `disclosure` index, precomputed
// per single stack slug by build_skill_map.py so this hook never walks
// doc.edges itself. Preference order, all under ~/.claude/context-manager/:
//   1. skill-map.indexes.resolved.json (static + local-overlay merge)
//   2. skill-map.indexes.json          (installed by `build_skill_map.py --install`)
// Neither present/parseable/missing a `disclosure` section -> FALL BACK to
// the original map-scanning path below (readMap/relevantSkills), so an older
// install without an indexes file yet still works.
//
// KNOWN LIMITATION of the index path vs. the map-scan fallback: the
// `disclosure` index's extends-folding (base absorbs a matched extender into
// its `deeper` list) is computed PER STACK SLUG in isolation
// (build_disclosure_index), whereas the map-scan path folds across the
// UNION of all detected stacks. When multiple stacks are detected on the
// same repo AND a base/extender pair matches different stacks from each
// other (base matches stack A only, extender matches stack B only), the
// index path will list them as two separate lines while the map-scan
// fallback would fold them into one. This is a pre-existing property of the
// committed index contract (see docs/skill-map.md's Tier 1 note), not
// something this refactor changes; no shipped fixture/test exercises this
// cross-stack case, and it is rare enough (two stack markers present AND an
// extends edge that straddles them) to accept rather than redesign the
// index format for.
//
// MAP RESOLUTION (fallback only): same resolved-then-static as skill-router.js:
//   1. ~/.claude/context-manager/skill-map.resolved.json (static + local overlay)
//   2. ~/.claude/context-manager/skill-map.static.json   (installed static artifact)
// Neither present or parseable -> exit 0, no output.
//
// STACK DETECTION: cheap existence checks only (no package.json parsing, no
// directory walks) against the CWD:
//   next.config.{js,mjs,ts}  -> tag:stack/nextjs
//   sanity.config.{js,ts}    -> tag:stack/sanity
//   vercel.json              -> tag:stack/vercel
//   .obsidian/ (directory)   -> tag:stack/obsidian
// No stack detected -> exit 0, no output, before the map is even read.
//
// OUTPUT: a header line plus up to 8 "plugin:skill — matches <stacks>" lines,
// ranked by number of matched stacks (desc) then skill id (asc) for
// determinism. Nothing is emitted if no skill resolves for a detected stack.

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

const STACK_MARKERS = [
  {
    stack: 'nextjs',
    check: (cwd) =>
      ['next.config.js', 'next.config.mjs', 'next.config.ts'].some((f) =>
        isFile(path.join(cwd, f))
      ),
  },
  {
    stack: 'sanity',
    check: (cwd) =>
      ['sanity.config.js', 'sanity.config.ts'].some((f) => isFile(path.join(cwd, f))),
  },
  {
    stack: 'vercel',
    check: (cwd) => isFile(path.join(cwd, 'vercel.json')),
  },
  {
    stack: 'obsidian',
    check: (cwd) => isDir(path.join(cwd, '.obsidian')),
  },
];

const MAX_SKILLS = 8;

function isFile(p) {
  try {
    return fs.statSync(p).isFile();
  } catch (_err) {
    return false;
  }
}

function isDir(p) {
  try {
    return fs.statSync(p).isDirectory();
  } catch (_err) {
    return false;
  }
}

function detectStacks(cwd) {
  const stacks = [];
  for (const marker of STACK_MARKERS) {
    if (marker.check(cwd)) stacks.push(marker.stack);
  }
  return stacks;
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
      if (doc && doc.disclosure && typeof doc.disclosure === 'object') {
        return doc.disclosure;
      }
    } catch (_err) {
      // corrupt JSON at this path — try the next candidate
    }
  }
  return null;
}

// Index-backed equivalent of relevantSkills() below, sourced from the
// disclosure index's per-stack-slug precomputed lists
// (build_skill_map.py's build_disclosure_index()) instead of walking
// doc.nodes/doc.edges. See the KNOWN LIMITATION note above the file header
// for the one behavioral edge case (cross-stack extends folding) this does
// not reproduce from the map-scan path.
function relevantSkillsFromIndex(disclosureIndex, detectedStacks) {
  const stacksBySkill = new Map(); // skillId -> Set(stackSlug)
  const deeperBySkill = new Map(); // skillId -> Set(extenderId), unioned across stacks

  for (const stack of detectedStacks) {
    const entries = disclosureIndex[stack];
    if (!Array.isArray(entries)) continue;
    for (const entry of entries) {
      const skillId = entry && entry.skillId;
      if (!skillId) continue;
      let stacks = stacksBySkill.get(skillId);
      if (!stacks) {
        stacks = new Set();
        stacksBySkill.set(skillId, stacks);
      }
      stacks.add(stack);
      if (Array.isArray(entry.deeper) && entry.deeper.length > 0) {
        let deeper = deeperBySkill.get(skillId);
        if (!deeper) {
          deeper = new Set();
          deeperBySkill.set(skillId, deeper);
        }
        entry.deeper.forEach((id) => deeper.add(id));
      }
    }
  }

  // An extender folded under a base for ANY stack must not also appear as
  // its own standalone line.
  const folded = new Set();
  for (const deeper of deeperBySkill.values()) {
    for (const id of deeper) folded.add(id);
  }

  const results = [];
  for (const [skillId, stacks] of stacksBySkill) {
    if (folded.has(skillId)) continue;
    const deeper = deeperBySkill.get(skillId);
    results.push({
      skillId,
      stacks: Array.from(stacks).sort(),
      deeper: deeper ? Array.from(deeper).sort() : null,
    });
  }

  results.sort((a, b) => {
    if (b.stacks.length !== a.stacks.length) return b.stacks.length - a.stacks.length;
    return a.skillId < b.skillId ? -1 : a.skillId > b.skillId ? 1 : 0;
  });

  return results.slice(0, MAX_SKILLS);
}

// Returns skills relevant to the detected stacks, ranked by number of
// matched stacks (desc) then skill id (asc), capped at MAX_SKILLS.
//
// LAYERED DISCLOSURE: when a base skill and one or more of its extenders
// (an `extends` edge from extender -> base) all match the detected stack,
// the base is surfaced with a `deeper` list of the matched extenders
// instead of listing each extender as its own line — level-1 disclosure
// surfaces bases first. The cap (MAX_SKILLS) is applied to this compacted
// list, so a base+extenders group counts as one line toward the cap.
function relevantSkills(doc, detectedStacks) {
  const detectedSet = new Set(detectedStacks);

  const skillsById = new Map();
  const tagsById = new Map();
  for (const node of doc.nodes) {
    if (node.kind === 'skill') skillsById.set(node.id, node);
    else if (node.kind === 'tag') tagsById.set(node.id, node);
  }

  const matchesBySkill = new Map(); // skillId -> Set(stackSlug)
  for (const edge of doc.edges) {
    if (edge.type !== 'stack-tag') continue;
    const tag = tagsById.get(edge.to);
    if (!tag) continue;
    const idMatch = /^tag:stack\/(.+)$/.exec(tag.id);
    if (!idMatch) continue;
    const slug = idMatch[1];
    if (!detectedSet.has(slug)) continue;
    if (!skillsById.has(edge.from)) continue;
    let bucket = matchesBySkill.get(edge.from);
    if (!bucket) {
      bucket = new Set();
      matchesBySkill.set(edge.from, bucket);
    }
    bucket.add(slug);
  }

  // extends adjacency: extender skill id -> Set(base skill id)
  const extendsBases = new Map();
  for (const edge of doc.edges) {
    if (edge.type !== 'extends') continue;
    if (!skillsById.has(edge.from) || !skillsById.has(edge.to)) continue;
    let bases = extendsBases.get(edge.from);
    if (!bases) {
      bases = new Set();
      extendsBases.set(edge.from, bases);
    }
    bases.add(edge.to);
  }

  // Fold matched extenders into their matched base(s): base gets a `deeper`
  // list, extender is dropped as a standalone line.
  const deeperByBase = new Map(); // baseId -> Set(extenderId)
  const foldedExtenders = new Set();
  for (const [extenderId, bases] of extendsBases) {
    if (!matchesBySkill.has(extenderId)) continue;
    for (const baseId of bases) {
      if (!matchesBySkill.has(baseId)) continue;
      let bucket = deeperByBase.get(baseId);
      if (!bucket) {
        bucket = new Set();
        deeperByBase.set(baseId, bucket);
      }
      bucket.add(extenderId);
      foldedExtenders.add(extenderId);
    }
  }

  const results = [];
  for (const [skillId, stacks] of matchesBySkill) {
    if (foldedExtenders.has(skillId)) continue; // rendered under its base instead
    const deeper = deeperByBase.get(skillId);
    results.push({
      skillId,
      stacks: Array.from(stacks).sort(),
      deeper: deeper ? Array.from(deeper).sort() : null,
    });
  }

  results.sort((a, b) => {
    if (b.stacks.length !== a.stacks.length) return b.stacks.length - a.stacks.length;
    return a.skillId < b.skillId ? -1 : a.skillId > b.skillId ? 1 : 0;
  });

  return results.slice(0, MAX_SKILLS);
}

function shortName(skillId) {
  const idMatch = /^skill:[^/]+\/(.+)$/.exec(skillId);
  return idMatch ? idMatch[1] : skillId;
}

function formatBlock(matches) {
  const lines = [];
  for (const m of matches) {
    const idMatch = /^skill:([^/]+)\/(.+)$/.exec(m.skillId);
    if (!idMatch) continue;
    const [, plugin, skillName] = idMatch;
    let line = `- ${plugin}:${skillName} — matches ${m.stacks.join(', ')} stack`;
    if (m.deeper && m.deeper.length > 0) {
      const names = m.deeper.map(shortName).sort();
      line += ` (+${names.length} deeper: ${names.join(', ')})`;
    }
    lines.push(line);
  }
  if (lines.length === 0) return null;
  return ['Rhize skills relevant to this repo:'].concat(lines).join('\n');
}

function resolveStdinData() {
  let raw = '';
  try {
    raw = fs.readFileSync(0, 'utf8');
  } catch (_err) {
    // no stdin available — return null, callers fall back to defaults
  }
  try {
    return JSON.parse(raw);
  } catch (_err) {
    return null; // no/invalid stdin JSON
  }
}

// Returns null (nothing to do), or { message, sessionId, suggested,
// contextHash } for main() to emit and log. suggested is an array of skill
// ids (disclosure surfaces multiple skills at once). contextHash covers the
// repo fingerprint (the resolved cwd), never raw prompt text or file paths.
function computeMessage() {
  const data = resolveStdinData();
  const cwd = data && typeof data.cwd === 'string' && data.cwd ? data.cwd : process.cwd();
  const sessionId = data && typeof data.session_id === 'string' ? data.session_id : null;

  const stacks = detectStacks(cwd);
  if (stacks.length === 0) return null; // silence > generic banner

  const disclosureIndex = readIndexes();
  const matches = disclosureIndex
    ? relevantSkillsFromIndex(disclosureIndex, stacks)
    : (() => {
        const doc = readMap();
        return doc ? relevantSkills(doc, stacks) : [];
      })();

  const message = formatBlock(matches);
  if (!message) return null;

  return {
    message,
    sessionId,
    suggested: matches.map((m) => m.skillId),
    contextHash: contextHash(cwd),
  };
}

function main() {
  try {
    const result = computeMessage();
    if (result && result.message) {
      process.stdout.write(
        JSON.stringify({
          hookSpecificOutput: {
            hookEventName: 'SessionStart',
            additionalContext: result.message,
          },
        }) + '\n'
      );
      logSuggestion({
        ts: new Date().toISOString(),
        session_id: result.sessionId,
        hook: 'disclosure',
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
