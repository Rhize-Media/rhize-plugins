---
description: Harvest refinement signals (headroom learn, claude-mem observations, skill-monitor deltas) into the pending-refinement queue for human triage — writes the queue only, never skills, CLAUDE.md, or docs/session-guardrails.md
---

# /learn-harvest

Collect skill-refinement signals into the queue at
`~/.claude/context-manager/refinement-queue.jsonl`. This command NEVER edits
skills, CLAUDE.md, `docs/session-guardrails.md`, or CLAUDE.local.md — signals
wait in the queue until triaged via `/skill-refine review`.

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
{"id": "<sha1-12 of source+pattern>", "ts": "<ISO8601>", "source": "headroom-learn|claude-mem|skill-monitor|skill-map-drift|skill-fit-decisions",
 "repo": "<project path or 'global'>", "pattern": "<the finding, verbatim or tightly summarized>",
 "est_savings": "<tokens/session if stated, else null>", "target_skill": null, "status": "pending",
 "signal_type": "<optional: 'routing-miss'|'drift'|'decision-layer' — omit for the original skill-body-refinement signals>"}
```

`signal_type` is optional and new (added alongside the skill-map substrate's routing-miss and
drift signals below); its absence means "skill body/description" is the implied refinement
target, matching every pre-existing entry. `source: "skill-fit-decisions"` and
`signal_type: "decision-layer"` come from the skill-fit decision records (step 5, "Decision-record
signals"); `decision-layer` findings are about the co-sign and keep-warm path rather than a skill's own
text, so their `target_skill` is informational (and `null` for `laya-timeouts`).

`id` is the dedupe key. Statuses: `pending → triaged | rejected → consumed`.

## Procedure

1. `mkdir -p ~/.claude/context-manager` and load existing queue ids for dedupe.
2. **Headroom** (dry-run is the default — do NOT pass `--apply`):
   - Run `headroom learn --project <cwd> --main-only`. **Never pass `--all`.** The `all`
     argument to *this command* means "all three sources below" — it is not
     headroom's `--all`, which analyses every discovered project (~17) and turns a
     seconds-long run into ~13 minutes. The two flags are also mutually exclusive:
     `headroom learn --project <path> --all` exits 2 with `--all and --project are
     mutually exclusive`, so the old wording here was unrunnable as written and
     broke two daily-harvest runs (2026-08-10).
   - **Pass `--main-only` on every `headroom learn` call.** `headroom learn` has no
     time-bounded lookback — `--help` offers no `--since`/`--days` — so each run
     re-analyses the project's entire session history, and that history only grows
     (207→337 Claude sessions and 72→154 Codex across ~2 weeks of captures).
     `--main-only` restricts the scan to top-level sessions, skipping nested
     subagent/workflow transcripts: that is where the volume growth is, and subagent
     internals are the least likely to generalise into a skill- or MEMORY.md-worthy
     pattern. It is what keeps the daily cadence affordable (added 2026-09-04). Every
     agent plugin accepts the flag (`--help` scopes its effect to Claude Code
     sessions), so it is safe on `--agent codex` and `--agent gemini` calls too.
   - `headroom learn` runs an LLM over conversation history and routinely exceeds
     the Bash tool's **120s default** timeout. Pass `timeout: 600000` explicitly.
     That 120s is a default, not a limit — and a timeout is **never on its own**
     grounds to report headroom unavailable (see Source-availability rule).
   - Tee stdout to `~/.claude/context-manager/harvest-logs/<YYYY-MM-DD>-headroom.txt`
     (`mkdir -p` the directory first). `headroom learn` writes nothing to disk on
     its own — `~/.headroom/learn-captures/` and `learn.log` are written by a
     separate weekly sweep wrapper — so an uncaptured run's output dies with the
     shell and its LLM spend is unrecoverable.
   - Turn the captured report into queue entries with the shipped parser — never by
     reading and re-typing the blocks yourself:

     ```bash
     python3 "$CLAUDE_PLUGIN_ROOT/scripts/harvest_headroom.py" \
       ~/.claude/context-manager/harvest-logs/<date>-headroom.txt \
       --repo <repo-name> --json
     ```

     It stores every block's `pattern` verbatim (title, headroom's savings estimate in
     `est_savings`, and the full body), derives `id` as `sha1-12(source + pattern)`, and
     skips ids already in the queue, so re-running is safe. On 2026-08-26 the previous
     prose version of this step produced seven entries cut at exactly 550 characters
     mid-word; `python3 "$CLAUDE_PLUGIN_ROOT/scripts/harvest_headroom.py" --audit` lists
     any pending entry that still looks truncated so it can be recovered from its
     harvest log.
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
4. **skill-monitor**: read the newest snapshot in the skill-monitor data directory
   (`RHIZE_SKILL_MONITOR_HOME`, else the standalone checkout's `data/`, else
   `~/.rhize/skill-monitor/data`)'s `snapshots/`. Queue skills that are heavily
   used but error-prone, or in the prune-candidate list (`source: skill-monitor`,
   pattern = the observation).
5. **Routing-miss (measurable today: map/tag deficiency only — do not overclaim)**.
   - Read the resolved skill map (`~/.claude/context-manager/skill-map.resolved.json`,
     falling back to `skill-map.static.json` — same resolution order `skill-router.js` uses)
     and the newest skill-monitor snapshot's usage totals (the skill-monitor data
     directory's `skill-cooccurrence.json`'s `totals` — `RHIZE_SKILL_MONITOR_HOME`,
     else the standalone checkout's `data/`, else `~/.rhize/skill-monitor/data` —
     or the latest `snapshots/*.json`).
   - For every skill with a nonzero usage total (it HAS been invoked in sessions), check
     whether the map has at least one `topic-tag` or `stack-tag` edge from that skill's
     node. `skill-router.js` requires ≥2 signals to ever emit a suggestion, and a tag match
     is the only way to get there without an exact name match — a skill with zero tag edges
     is structurally unroutable regardless of how much real usage it has. Flag each such
     skill as a routing-miss.
   - **Resolve the node first, and skip what cannot be tagged.** Before counting edges,
     drop any usage entry that (a) resolves to a `kind: "command"` node —
     `build_skill_map.py` emits tag edges only inside `load_skills()`, never for commands,
     so every command with usage would fail forever; (b) resolves to no node at all — the
     monitor's `plugin:name` key maps to a two-segment `skill:<plugin>/<name>` id only for
     this repo's own plugins, and a skill outside the map has nothing here to tag; or (c)
     carries `origin: "third-party"` — the resolver adds installed third-party plugins as
     three-segment `skill:<marketplace>/<plugin>/<dir>` nodes and deliberately emits no tag
     edges for them (`build_local_skill_map.py`: "No topic/stack-tag edges are emitted"),
     since their frontmatter is not ours to edit. Flag only an owned `kind: "skill"` node
     (no `origin` key) with zero tag edges — the one case where the fix below is
     actionable. (Tightened 2026-09-04 after four routing-miss signals were rejected at
     `/skill-refine review` as exactly these classes: two commands, one third-party skill,
     one skill with no node.)
   - **Suggested-but-ignored is computed, but not by this check.** The router's
     suggestion is now recorded per prompt in the skill-fit decision records (hashes, ids and
     statuses only, never prompt text) and joined to what the user invoked next, so
     `scripts/typed_decisions/harvest_signals.py emit` derives it deterministically — see
     "Decision-record signals" after this step. The map/tag-deficiency check in this
     bullet list still covers only structural deficiency, and nothing here may claim more.
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

   **Note:** `target_skill` here is always a Rhize-owned skill by construction
   (the third-party-origin exclusion above), never a path under a plugin
   cache or marketplace checkout — `/skill-refine review` refuses any
   human-assigned `target_skill` outside its two allowed roots
   (`rhize-context-manager/skills/*`, `~/.claude/skills/learned/*`), for any
   source, with the instruction to fork/vendor into a Rhize plugin or
   contribute upstream (see its `review` section — the allowlist is the rule;
   install trees are just the common case). Routing a signal through `skill-forge refine
   capture` instead of `/skill-refine` is also deferred until that command's
   project-scope override files can be materialized into a plugin cache.

   **Decision-record signals (`source: "skill-fit-decisions"`).** Run, with a NEW private
   file that does not exist yet:

   ```bash
   python3 "$CLAUDE_PLUGIN_ROOT/scripts/typed_decisions/harvest_signals.py" emit \
     --queue <private-dir>/decision-candidates.jsonl --repo rhize-plugins
   ```

   Options: `--root` (typed-decisions store, default `~/.local/share/rhize/typed-decisions`),
   `--now`, `--window-days 14`, `--min-events 3`. It reads the skill-fit records and outcomes
   (ids, hashes and statuses; no prompt text exists there) over the trailing window, writes
   queue-schema candidates to `--queue`, and prints a counts-only JSON summary.

   - **Private-file contract.** `--queue` must not exist (it is created `0600`, atomically,
     symlinks refused) and must never be the live queue: `emit` refuses
     `~/.claude/context-manager/refinement-queue.jsonl`, in any spelling or through any
     symlink, and exits 2 without writing. It never touches the live queue. Its candidates
     reach the queue only through the steps below — id dedupe (step 6), the noise filter
     (step 7), the routine's verify step — and then the normal append.
   - **Idempotent, no watermark.** Every run recomputes the whole trailing window. The pattern
     text has no counts and no dates, so a finding keeps the same `id`
     (`sha1-12(source + pattern)`) day after day and step 6 drops repeats against every queue
     status. A candidate is a *review candidate*, not ground truth.
   - **Signals**, grouped per (signal, subtype, skill, host); a group is emitted at
     `--min-events` or more events. Subtypes 1-3 use finalized records only (a record with an
     outcome); the host (`claude`, `codex`, `unknown`) is part of every pattern:
     1. `signal_type: "routing-miss"`, subtype `not-shortlisted`: a skill was invoked
        (`invoked_unlisted`) after prompts where the router suggested another skill or none
        and did not shortlist it. `target_skill` is the invoked skill. Fix target: its tags and
        trigger phrases.
     2. `signal_type: "routing-miss"`, subtype `suggested-but-ignored`: the router's shown
        suggestion (`emitted`, non-null) was passed over for a different shortlisted skill
        (`invoked_other_shortlisted`). `target_skill` is the suggested skill.
     3. `signal_type: "decision-layer"`, subtype `cosign-suppressed-then-invoked`: mode `cosign`,
        treatment arm, nothing emitted (Laya disagreed or was unavailable), and the incumbent
        was invoked within one user turn. `target_skill` is the incumbent — the direct cost of
        Laya's authority.
     4. `signal_type: "decision-layer"`, subtype `laya-timeouts`: live records in the window with
        at least 20 Laya calls (status not `skipped`) and a timeout share above 5%. One
        candidate per host, `target_skill: null`. Needs no outcome. The fix is keep-warm
        health (`scripts/typed_decisions/laya_keepwarm.py status`) or the latency budget, never
        a skill edit.
   - **Verify before queuing.** For the two `routing-miss` subtypes apply the node-resolution
     rule of the map/tag check above (drop commands, skills with no node, third-party
     `origin`) so triage only sees an owned `kind: "skill"` target. `decision-layer`
     candidates are operational findings and are kept as emitted. Example:

   ```json
   {"id": "<sha1-12>", "ts": "<ISO8601>", "source": "skill-fit-decisions", "repo": "rhize-plugins",
    "pattern": "routing-miss (not-shortlisted, host claude): skill:rhize-ops/skill-dashboard was invoked soon after prompts where the router suggested another skill or none and did not shortlist it, repeatedly within the trailing window — review its tags and trigger phrases.",
    "est_savings": null, "target_skill": "rhize-ops/skill-dashboard", "status": "pending",
    "signal_type": "routing-miss"}
   ```
6. Skip any entry whose `id` already exists in the queue regardless of status.
7. **Content noise filter — run it, do not eyeball it.** `id` is
   `sha1-12(source + pattern)`, so *any rephrasing of a known fact produces a new
   id and walks straight past step 6*. Headroom rephrases constantly: on
   2026-08-14, 3 of 5 headroom entries restated facts folded into
   `docs/session-guardrails.md` on 2026-08-12 (folded into CLAUDE.md at the
   time; repo-shape R-A later moved that content), and the two largest
   `est_savings` claims (235k, 45k) were the two
   most duplicative. That is ~30% of a day's yield spent re-litigating settled
   facts. Write the surviving candidates from step 6 to a JSONL file, then:

   ```bash
   python3 scripts/harvest_noise_filter.py \
     --candidates <candidates.jsonl> \
     --reference CLAUDE.md --reference ~/.claude/CLAUDE.md \
     --reference docs/session-guardrails.md \
     --reference "$HOME/.claude/projects/$(pwd | tr '/' '-')/memory/MEMORY.md" \
     --keep-out <kept.jsonl> \
     | tee ~/.claude/context-manager/harvest-logs/$(date +%F)-filter.txt
   ```

   The reference set is every file that already holds settled facts — pass **all
   four** (`--reference` repeats; the daily routine's collector block must match this
   one exactly):
   - `docs/session-guardrails.md` — most repo-environment facts now live there, not
     CLAUDE.md; without it the filter dedupes against a file that no longer holds
     most of the settled facts.
   - The project's auto-memory `MEMORY.md` — the dominant duplicate source. Headroom's
     proposed MEMORY.md block echoes existing memory entries back verbatim, and on
     2026-09-04 19 of a 22-candidate batch were rejected at triage as restatements of
     a MEMORY.md section the filter had never seen. The path is derived from `pwd`
     (Claude Code names the project directory by replacing `/` with `-`), so the same
     line works from any project; keep it quoted, since some project paths contain
     spaces. If the project has no memory file yet, the script prints `warning:
     reference doc not found, skipping` and continues — never omit it "because it
     might not exist".

   It scores each candidate by how much of its normalized content is already
   covered by existing queue patterns (any status) or reference-file blocks, and sorts
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
