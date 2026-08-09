---
description: Harvest refinement signals (headroom learn, claude-mem observations, skill-monitor deltas) into the pending-refinement queue for human triage — writes the queue only, never skills or CLAUDE.md
---

# /learn-harvest

Collect skill-refinement signals into the queue at
`~/.claude/context-manager/refinement-queue.jsonl`. This command NEVER edits
skills, CLAUDE.md, or CLAUDE.local.md — signals wait in the queue until triaged
via `/skill-refine review`.

## Cadence

Runs DAILY as its own scheduled task,
`~/Documents/Claude/Scheduled/daily-learn-harvest/SKILL.md`, on a cheap model — this is
mechanical collection with no judgment calls, so it belongs on the cheap tier. (Moved off
the weekly `weekly-skill-audit` routine in 2026-08, where it used to run as step 8; that
routine now only runs the weekly drain, step 8, on the capable-model tier.) Manual
on-demand runs of `/learn-harvest` remain fine any time — the daily schedule doesn't
replace ad-hoc use, e.g. right before a `/skill-refine review` session.

## Queue entry schema

One JSON object per line:

```json
{"id": "<sha1-12 of source+pattern>", "ts": "<ISO8601>", "source": "headroom-learn|claude-mem|skill-monitor|skill-map-drift",
 "repo": "<project path or 'global'>", "pattern": "<the finding, verbatim or tightly summarized>",
 "est_savings": "<tokens/session if stated, else null>", "target_skill": null, "status": "pending",
 "signal_type": "<optional: 'routing-miss'|'drift' — omit for the original skill-body-refinement signals>"}
```

`signal_type` is optional and new (added alongside the skill-map substrate's routing-miss and
drift signals below); its absence means "skill body/description" is the implied refinement
target, matching every pre-existing entry.

`id` is the dedupe key. Statuses: `pending → triaged | rejected → consumed`.

## Procedure

1. `mkdir -p ~/.claude/context-manager` and load existing queue ids for dedupe.
2. **Headroom** (dry-run is the default — do NOT pass `--apply`):
   - Run `headroom learn --project <cwd>` (add `--all` when invoked with the
     `all` argument). Capture stdout.
   - Parse each recommendation/pattern block into one queue entry
     (`source: headroom-learn`). Keep headroom's savings estimates in
     `est_savings` when present.
3. **claude-mem**: search recent observations (last 7 days) for
   correction/friction shaped entries — bugfix loops, repeated retries, user
   corrections of agent behavior. Use the mem-search tooling; take at most the
   top 10, one queue entry each (`source: claude-mem`).
4. **skill-monitor**: read the newest snapshot in
   `rhize-ops/skill-monitor/data/snapshots/` (this repo). Queue skills that are
   heavily used but error-prone, or in the prune-candidate list
   (`source: skill-monitor`, pattern = the observation).
5. **Routing-miss (measurable today: map/tag deficiency only — do not overclaim)**.
   - Read the resolved skill map (`~/.claude/context-manager/skill-map.resolved.json`,
     falling back to `skill-map.static.json` — same resolution order `skill-router.js` uses)
     and the newest skill-monitor snapshot's usage totals
     (`rhize-ops/skill-monitor/data/skill-cooccurrence.json`'s `totals`, or the latest
     `data/snapshots/*.json`).
   - For every skill with a nonzero usage total (it HAS been invoked in sessions), check
     whether the map has at least one `topic-tag` or `stack-tag` edge from that skill's
     node. `skill-router.js` requires ≥2 signals to ever emit a suggestion, and a tag match
     is the only way to get there without an exact name match — a skill with zero tag edges
     is structurally unroutable regardless of how much real usage it has. Flag each such
     skill as a routing-miss.
   - **What is NOT computed here, and must not be claimed as computed**: true
     "suggested-but-ignored" (the router surfaced a skill in a session but a different one
     was used instead). `skill-router.js` emits its suggestion transiently as
     `additionalContext` per prompt and persists nothing, and no prompt text is retained
     anywhere in this pipeline by design (see skill-monitor's co-occurrence snapshot —
     counts only). Computing that signal needs future instrumentation: a small append-only
     suggestion log on the router (e.g. `{ts, sessionIdHash, suggestedSkillId}`, no prompt
     text) diffed against skill-monitor's per-session invocation record. Until that log
     exists, only the map/tag-deficiency check above runs.
   - Queue one entry per flagged skill: `source: skill-monitor`, `signal_type: "routing-miss"`,
     `target_skill` set to the skill, and `pattern` stating the skill is used but has 0
     topic/stack tag edges. The proposed fix is always to the **map or the skill's
     frontmatter tags/description** (`catalog/tags.json` vocabulary, the skill's
     `metadata.rhize.{topics,stacks}` block, or `catalog/skill-relations.json`) — never a
     rewrite of the skill's body. Example:

```json
{"id": "<sha1-12>", "ts": "<ISO8601>", "source": "skill-monitor", "repo": "rhize-plugins",
 "pattern": "routing-miss: skill:rhize-ops/skill-dashboard has usage in the last snapshot but 0 topic-tag/stack-tag edges — unroutable by skill-router.js",
 "est_savings": null, "target_skill": "rhize-ops/skill-dashboard", "status": "pending",
 "signal_type": "routing-miss"}
```
6. Skip any entry whose `id` already exists in the queue regardless of status.
7. Append new entries; report a summary table: source | new | duplicates
   skipped, plus current queue counts by status. Remind: next step is
   `/skill-refine review`.
