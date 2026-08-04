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
{"id": "<sha1-12 of source+pattern>", "ts": "<ISO8601>", "source": "headroom-learn|claude-mem|skill-monitor",
 "repo": "<project path or 'global'>", "pattern": "<the finding, verbatim or tightly summarized>",
 "est_savings": "<tokens/session if stated, else null>", "target_skill": null, "status": "pending"}
```

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
5. Skip any entry whose `id` already exists in the queue regardless of status.
6. Append new entries; report a summary table: source | new | duplicates
   skipped, plus current queue counts by status. Remind: next step is
   `/skill-refine review`.
