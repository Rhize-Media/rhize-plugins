---
description: Operate the gated skill-refinement pipeline — `review` triages queued signals to target skills; `run` evolves each targeted skill via skill-forge (SkillOpt + safety re-gate) with auto-promote for gate-passing SKILL.md edits
---

# /skill-refine [review|run]

Consume the refinement queue at `~/.claude/context-manager/refinement-queue.jsonl`.
Trust model: **human gate at triage** (nothing untriaged reaches the optimizer),
**machine gate at promote** (skill-forge re-gates every proposal). No argument →
show queue counts by status and suggest the next subcommand.

## `review` — human triage (interactive)

1. Load all `pending` entries. Present them one at a time (or grouped by
   source) with: pattern, source, repo, est_savings. Surface any `filter_note`
   (set by `/learn-harvest`'s noise filter) — it marks a probable composite of
   already-documented facts and is usually a reject.
2. For each, the user decides: assign a `target_skill` (path under
   `rhize-context-manager/skills/` or `~/.claude/skills/learned/`) → status
   `triaged`; or reject → status `rejected`. Suggest a target skill per entry,
   but the USER decides — never auto-triage. A repo-environment fact with no
   legal skill target does not get a `target_skill`: fold it in by hand into
   `docs/session-guardrails.md` (never into `CLAUDE.md` — that file is a
   router, not a home for telemetry) and mark the entry `consumed` directly.
3. **Refuse a `target_skill` under any plugin cache or marketplace checkout**
   — `~/.claude/plugins/cache/`, `~/.claude/plugins/marketplaces/`, or
   `~/.codex/plugins/`. These are Claude Code/Codex-managed install trees,
   not this repo: an edit there is invisible to `git` and gets silently
   overwritten by the next `claude plugin update`/marketplace sync. Refuse
   the assignment and tell the user to either (a) fork/vendor the skill
   into a Rhize plugin under `rhize-context-manager/skills/` — recording
   the fork and its `Drift check` in that plugin's `SOURCES.md`, per the
   repo's curation rule (see `CLAUDE.md`'s "Curation Rule") — or (b)
   contribute the fix upstream to the third-party plugin's own repo. Mark
   the entry `rejected` with a note; never `triaged` against a path outside
   this repo. Rhize-owned targets (`rhize-context-manager/skills/*`,
   `~/.claude/skills/learned/*`) are edited in-repo/in-place and committed
   normally — no forking needed.

   Routing a triaged entry through `skill-forge refine capture` is
   **deferred** for this case: its project-scope override files are not
   yet materialized into a plugin cache, so it cannot stand in for editing
   an installed third-party skill today.
4. Back up the queue (see Guardrails), then rewrite it with updated statuses.
   Summarize: N triaged toward M skills, K rejected.

**Two facts that make triage suggestions better, both measured:**

- **`est_savings` is anti-correlated with entry quality** and type-chaotic (ints,
  strings, and free text like `'~100,000 tokens/session'` in one field). On
  2026-08-12 the three largest savings claims were content-free CLAUDE.md section
  headings; on 2026-08-14 the two largest (235k, 45k) were the two most duplicative
  entries in the batch. **Never rank or threshold dispositions on it.**
- **`evolve` needs a skill *directory*.** `rhize-context-manager/skills/*` are
  directories with a `SKILL.md` and are valid targets. Most `~/.claude/skills/learned/*`
  entries are bare `.md` files — they can still receive the step-3 "known failure
  modes" text fold-in under `run`, but `evolve` cannot operate on them. Prefer
  directory-shaped targets for anything meant to reach the drain, and verify the
  target has a `SKILL.md` before assigning it.

## `run` — gated refinement pass (safe to run headless)

1. Group `triaged` entries by `target_skill`. If none, report and stop.
2. For each target skill:
   a. Present the queued signals as reviewer context in the run report.
   b. Execute: `npx @rhize/skill-forge evolve <skill-dir> --project <repo-of-signals> -y --json`
      (SkillOpt-Sleep harvests session history itself — the queue selects WHICH
      skill evolves and records WHY; `--lookback-hours` may be raised to cover
      the oldest triaged signal).
   c. **Auto-promote rule**: accept the automatic promote only when the re-gate
      verdict is ALLOW, the score improved, AND the proposal touches only
      SKILL.md / reference markdown. If the proposal modifies anything under
      `scripts/`, `hooks/`, or frontmatter `allowed-tools`, HOLD it regardless
      of verdict and flag for human review.
   d. Mark the skill's queue entries `consumed` (promoted) or leave `triaged`
      with a note (held/rejected by gate).
3. Also fold simple, directly-actionable signals (e.g. a known-failure-mode
   bullet from headroom) into the target skill's "known failure modes" section
   per the Compounding Contract — these small text edits follow the same
   auto-promote rule (SKILL.md text only) and are recorded in the run report.
4. Write a run report to `~/.claude/context-manager/runs/<date>.md`: per skill —
   signals consumed, evolve verdict, promoted/held, diff summary. Print the
   report path and a compact summary table.

## Guardrails

- Never run `evolve` on an untriaged skill.
- Never bypass a HOLD by re-running with `--force`.
- Before any whole-file rewrite that touches more than ~10 entries (a bulk
  triage pass, not a single status flip), copy the queue to
  `~/.claude/context-manager/refinement-queue.jsonl.bak-<YYYY-MM-DD>` first —
  one `cp` / `shutil.copy2`, no rotation. It lives next to the queue file,
  never in a session scratchpad (2026-09-04: 125 entries were rewritten with
  the only copy in a scratchpad that died with the session). Never overwrite
  an existing backup; if today's already exists, suffix the time (`-HHMM`).
- Queue writes are whole-file rewrites; if the file changed mid-run (mtime
  check), re-read and merge before writing.
