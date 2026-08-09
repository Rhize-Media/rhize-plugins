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
// MAP RESOLUTION: same resolved-then-static fallback as skill-router.js:
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

const fs = require('fs');
const os = require('os');
const path = require('path');

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

function resolveCwd() {
  let raw = '';
  try {
    raw = fs.readFileSync(0, 'utf8');
  } catch (_err) {
    // no stdin available — fall back to process.cwd()
  }
  try {
    const data = JSON.parse(raw);
    if (data && typeof data.cwd === 'string' && data.cwd) return data.cwd;
  } catch (_err) {
    // no/invalid stdin JSON — fall back to process.cwd()
  }
  return process.cwd();
}

function computeMessage() {
  const cwd = resolveCwd();

  const stacks = detectStacks(cwd);
  if (stacks.length === 0) return null; // silence > generic banner

  const doc = readMap();
  if (!doc) return null;

  const matches = relevantSkills(doc, stacks);
  return formatBlock(matches);
}

function main() {
  try {
    const message = computeMessage();
    if (message) {
      process.stdout.write(
        JSON.stringify({
          hookSpecificOutput: {
            hookEventName: 'SessionStart',
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
