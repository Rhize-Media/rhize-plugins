#!/usr/bin/env node
'use strict';

// agent-brief-router.js — log-first skill-coverage measurement hook
// (PreToolUse, matcher SPIKE_MATCHER as recorded by Task 3's spike verdict in
// .claude/plans/subagent-skill-injection.md; wiring is Task 6's job, not
// this file's).
//
// TIER: T3 (measurement). Never blocks (always exit 0). Fails silently on any
// missing/unreadable/corrupt input, same fail-silent contract as
// skill-router.js/remediation-suggester.js.
//
// PURPOSE: measures how often an outgoing subagent brief already NAMES (via
// the Task 1 "Invoke <plugin:skill> first" directive) the skill route-core's
// scoring would otherwise suggest for that brief's content. Default behavior
// is LOG ONLY — no stdout, no effect on the dispatch — because briefs are
// long, multi-paragraph documents and the same signal weights that work for
// short user prompts (skill-router.js) over-match on them. BRIEF_MIN_SCORE
// below is a starting calibration point, to be revisited once the log has
// real data (see the plan's Background section).
//
// The one-line advisory (hookSpecificOutput.additionalContext) exists only
// because Task 3's V2 spike proved additionalContext from a PreToolUse hook
// reaches the model, and even then it ships DISABLED behind
// RHIZE_AGENT_BRIEF_ADVISORY=1 until that calibration review has happened.
//
// CONTRACT: reads hook JSON from stdin — tool_input.prompt (the outgoing
// brief) and tool_input.subagent_type. Never surfaces raw brief text anywhere
// (log or stdout) — only a hash + length, the same privacy stance as
// skill-monitor and route-core's existing loggers.
//
// LOGGING: entries carry source: "agent-dispatch" and deliberately NO "hook"
// field — scripts/suggestion_log_report.py keys on hook ∈ {router,
// disclosure, remediation, next-step} and ignores rows without it, so these
// rows stay invisible to the legacy reader until Task 6's source branch
// lands. Written via route-core's logSuggestion(), which appends whatever
// entry object it is given and does not itself inject a "hook" field —
// verified by reading hooks/lib/route-core.js before writing this file.

const fs = require('fs');
const path = require('path');

const {
  readIndexes,
  readMap,
  tokenize,
  formatSkillRef,
  routeFromIndex,
  route,
  contextHash,
  logSuggestion,
} = require(path.join(__dirname, 'lib', 'route-core.js'));

// Local policy constant — NOT part of route-core's built-in two-signal
// minimum (routeFromIndex()/route() already require 2+ matched signals just
// to return a candidate at all). This is a stricter post-filter on top of
// that: 2x the built-in floor, because a brief's sheer length means it often
// clears the floor on noise alone. Initial value; recalibrate from the log.
const BRIEF_MIN_SCORE = 4;

function escapeRegex(str) {
  return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

// Skill ids known to whichever data source loaded (index or map), so
// named-skill detection covers every skill the loaded map/index knows about.
// The router index's `signals` object is keyed by skill id; the static map
// carries skill ids on its `nodes` array (node.kind === 'skill').
function skillIdsOf(mode, routerIndex, mapDoc) {
  if (mode === 'index') {
    return Object.keys(routerIndex.signals || {});
  }
  return (mapDoc.nodes || []).filter((n) => n.kind === 'skill').map((n) => n.id);
}

// A brief "names" a skill iff it contains the directive form of the Task 1
// convention: "Invoke <plugin>:<name>" as a whole word, preceded by either
// start-of-string or whitespace (so "NotInvoke ..." can't match). A prose
// mention without the directive deliberately does not count — this measures
// compliance with the convention, not vocabulary overlap.
function namedSkillsIn(brief, skillIds) {
  const named = [];
  for (const skillId of skillIds) {
    const ref = formatSkillRef(skillId);
    if (!ref) continue;
    const directive = new RegExp('(?:^|\\s)Invoke\\s+' + escapeRegex(ref) + '\\b', 'i');
    if (directive.test(brief)) {
      named.push(skillId);
    }
  }
  return named;
}

// Reads stdin, loads map data, scores the brief, and returns everything main()
// needs to log (and possibly emit an advisory for) — or null if this dispatch
// doesn't reach the point of having anything to log (empty brief, or no
// usable map/index data at all). Throws on malformed stdin; main()'s
// try/catch turns that into the same silent no-op.
function computeResult() {
  const raw = fs.readFileSync(0, 'utf8');
  const data = JSON.parse(raw);

  const toolInput = (data && data.tool_input) || {};
  const brief = typeof toolInput.prompt === 'string' ? toolInput.prompt : '';
  const agentType = typeof toolInput.subagent_type === 'string' ? toolInput.subagent_type : '';
  if (!brief) return null;

  const routerIndex = readIndexes();
  let mode = null;
  let mapDoc = null;
  if (routerIndex) {
    mode = 'index';
  } else {
    mapDoc = readMap();
    if (mapDoc) mode = 'map';
  }
  if (!mode) return null; // a hook that can't rank must not emit half-measurements

  const promptTokens = tokenize(brief);
  const candidate =
    mode === 'index' ? routeFromIndex(routerIndex, promptTokens) : route(mapDoc, promptTokens);
  const suggestedSkills =
    candidate && candidate.score >= BRIEF_MIN_SCORE ? [candidate.skillId] : [];

  const skillIds = skillIdsOf(mode, routerIndex, mapDoc);
  const namedSkills = namedSkillsIn(brief, skillIds);

  let advisoryMessage = null;
  if (process.env.RHIZE_AGENT_BRIEF_ADVISORY === '1' && suggestedSkills.length > 0) {
    const disjoint = suggestedSkills.every((id) => !namedSkills.includes(id));
    if (disjoint) {
      const ref = formatSkillRef(suggestedSkills[0]);
      if (ref) {
        advisoryMessage =
          `Brief for ${agentType} may map to ${ref} — consider naming it ` +
          `("Invoke ${ref} first") or inlining its operative content on the ` +
          'next dispatch.';
      }
    }
  }

  return { agentType, brief, namedSkills, suggestedSkills, advisoryMessage };
}

function main() {
  try {
    const result = computeResult();
    if (result) {
      logSuggestion({
        ts: new Date().toISOString(),
        source: 'agent-dispatch',
        agentType: result.agentType,
        briefHash: contextHash(result.brief),
        briefLength: result.brief.length,
        namedSkills: result.namedSkills,
        suggestedSkills: result.suggestedSkills,
        advisoryEmitted: result.advisoryMessage !== null,
      });
      if (result.advisoryMessage) {
        process.stdout.write(
          JSON.stringify({
            hookSpecificOutput: {
              hookEventName: 'PreToolUse',
              additionalContext: result.advisoryMessage,
            },
          }) + '\n'
        );
      }
    }
  } catch (_err) {
    // fail-silent contract: never surface an error to the user or Claude
  } finally {
    process.exit(0);
  }
}

main();
