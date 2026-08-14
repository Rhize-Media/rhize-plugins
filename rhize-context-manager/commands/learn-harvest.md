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
   - Run `headroom learn --project <cwd>`. **Never pass `--all`.** The `all`
     argument to *this command* means "all three sources below" — it is not
     headroom's `--all`, which analyses every discovered project (~17) and turns a
     seconds-long run into ~13 minutes. The two flags are also mutually exclusive:
     `headroom learn --project <path> --all` exits 2 with `--all and --project are
     mutually exclusive`, so the old wording here was unrunnable as written and
     broke two daily-harvest runs (2026-08-10).
   - `headroom learn` runs an LLM over conversation history and routinely exceeds
     the Bash tool's **120s default** timeout. Pass `timeout: 600000` explicitly.
     That 120s is a default, not a limit — and a timeout is **never on its own**
     grounds to report headroom unavailable (see Source-availability rule).
   - Tee stdout to `~/.claude/context-manager/harvest-logs/<YYYY-MM-DD>-headroom.txt`
     (`mkdir -p` the directory first). `headroom learn` writes nothing to disk on
     its own — `~/.headroom/learn-captures/` and `learn.log` are written by a
     separate weekly sweep wrapper — so an uncaptured run's output dies with the
     shell and its LLM spend is unrecoverable.
   - Parse each recommendation/pattern block into one queue entry
     (`source: headroom-learn`). Keep headroom's savings estimates in
     `est_savings` when present.
3. **claude-mem**: search recent observations (last 7 days) for
   correction/friction shaped entries — bugfix loops, repeated retries, user
   corrections of agent behavior. Take at most the top 10, one queue entry each
   (`source: claude-mem`).
   - **Load the tools first.** They are deferred, so calling one directly fails
     with `InputValidationError` — which reads like an auth error and has twice
     been misreported as "non-interactive session; MCP authentication not
     supported". Run this ToolSearch query before the first call:

     ```
     select:mcp__plugin_claude-mem_mcp-search__search,mcp__plugin_claude-mem_mcp-search__timeline,mcp__plugin_claude-mem_mcp-search__get_observations
     ```

   - The claude-mem search server is **not auth-gated**, and this was already
     disproven once — observation #45554, "claude-mem MCP Auth Succeeded in
     Scheduled Non-Interactive Run" (2026-08-09), recorded a clean scheduled run.
     It recurred on 2026-08-10 anyway, because nothing in the procedure recorded
     it. An `InputValidationError` means *tools not loaded*, never *auth failed*.
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
7. **Content noise filter — run it, do not eyeball it.** `id` is
   `sha1-12(source + pattern)`, so *any rephrasing of a known fact produces a new
   id and walks straight past step 6*. Headroom rephrases constantly: on
   2026-08-14, 3 of 5 headroom entries restated facts folded into CLAUDE.md on
   2026-08-12, and the two largest `est_savings` claims (235k, 45k) were the two
   most duplicative. That is ~30% of a day's yield spent re-litigating settled
   facts. Write the surviving candidates from step 6 to a JSONL file, then:

   ```bash
   python3 scripts/harvest_noise_filter.py \
     --candidates <candidates.jsonl> \
     --reference CLAUDE.md --reference ~/.claude/CLAUDE.md \
     --keep-out <kept.jsonl> \
     | tee ~/.claude/context-manager/harvest-logs/$(date +%F)-filter.txt
   ```

   It scores each candidate by how much of its normalized content is already
   covered by existing queue patterns (any status) or CLAUDE.md blocks, and sorts
   into three outcomes:
   - **suppressed** (coverage ≥ 0.75) — drop; it is a restatement.
   - **flagged** (0.45 ≤ coverage < 0.75) — **keep**, with a `filter_note`. These
     are usually composite entries (`Topic — Fact1. Fact2. Fact3.`) whose facts are
     each known but which retain novel detail. Suppressing at this score also kills
     genuine signals, so the human decides at `/skill-refine review`.
   - **thin** (< 6 content tokens) — drop; a bare heading is not an actionable signal.

   Append only what lands in `--keep-out`. **Tee the report** — a suppressed run and
   a run that never happened both produce few new entries, and the filter report is
   the only thing that tells them apart. Never suppress an entry that the report does
   not list, and never drop a *flagged* one.
8. Append new entries; report a summary table: source | new | duplicates
   skipped | suppressed by filter | flagged, plus current queue counts by status.
   Remind: next step is `/skill-refine review`.

## Source-availability rule

A dead source never blocks the others — but "unavailable" is a claim about the
world, and a wrong one silently starves the queue. **Never record a source
unavailable on the strength of a single failed call.** Prove it first:

- **headroom** — run `headroom learn --help`. It exits 0 in well under a second.
  Exit 0 means headroom is alive and the earlier failure was the call, not the
  tool. A slow or timed-out `headroom learn` is expected behaviour, not death; if
  it still exceeds `timeout: 600000`, suspect an accidental `--all` (that is the
  conflation's signature) rather than an unreachable binary.
- **claude-mem** — an `InputValidationError` means the deferred tools were not
  loaded. Run the ToolSearch query in step 3 and retry once before judging.
- **skill-monitor** — "no snapshot newer than the last harvest" is a *skip*, not
  an unavailability; on a daily cadence that is the normal case.

Report the probe's result alongside any unavailability claim, and state the
distinction explicitly: *"I found the wall"* (probe failed) versus *"I didn't find
a door"* (my call failed). Only the former is unavailability.

**A run reporting 2+ sources unavailable must say so loudly** — lead the output
with it, never bury it under a clean-looking empty table. "All sources
unavailable" and "no new signals" both render as zero new entries, so an
unflagged empty harvest is indistinguishable from a total failure. A zero-entry
run with every source verified live is a legitimate result; a zero-entry run with
unprobed sources is a failed run and must be reported as one.
