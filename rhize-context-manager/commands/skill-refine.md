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
3. Back up the queue (see Guardrails), then rewrite it with updated statuses.
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
   b. Execute: `npx @rhize/skill-forge evolve <skill-dir> --project <repo-of-signals> --backend claude -y --json`
      (SkillOpt-Sleep harvests session history itself — the queue selects WHICH
      skill evolves and records WHY; `--lookback-hours` may be raised to cover
      the oldest triaged signal). **`--backend claude` is required — omitting it
      silently falls back to SkillOpt-Sleep's `mock` backend** (fully offline,
      deterministic, produces no real analysis), which is why `evolve` never
      successfully consumed a single queue entry before 2026-09-04: all 30
      entries this pipeline had consumed to that point were manual fold-ins,
      not `evolve` promotions. **Data boundary**: `claude` (like `codex`/`copilot`)
      sends truncated excerpts from harvested sessions to Anthropic — measured
      2026-09-04 to be the local `claude` CLI under its existing subscription
      login by default, so a run consumes Claude Code subscription/rate-limit
      quota, not per-token billing; setting `ANTHROPIC_API_KEY` in the
      environment flips it to metered API billing instead (see Auth + model
      below). Either way, session excerpts leave the machine and are not
      guaranteed secret-free per SkillOpt-Sleep's own docs. Requires
      `skillopt-sleep` on PATH (`pipx install skillopt` — use pipx, not plain
      `pip install`, since Homebrew's Python is externally-managed and refuses
      a bare `pip install`).
      Verified 2026-09-04, one layer at a time (the full wrapper command above
      with a real backend was NOT itself executed — composed from these three
      checks instead, to keep the one real-backend run capped and bounded):
      (1) the wrapper's offline paths — `--backend claude --dry-run --json`
      without `-y` refuses before any backend call (data-boundary disclosure
      enforced); `--backend mock --dry-run -y --json` completes clean; (2) the
      wrapper forwards `--backend` straight through to `skillopt-sleep`
      (`evolve.ts:152`); (3) a direct, capped `skillopt-sleep dry-run --backend
      claude --target-skill-path rhize-context-manager/skills/context-optimization/SKILL.md
      --max-sessions 6 --max-tasks 6` run (6 sessions, 5 mined tasks, ~10 min)
      scored baseline 0.29 → candidate 0.63 and proposed 4 genuine, target-
      specific skill-body edits (0 matched the mock backend's canned text); 2
      memory-targeted edits were rejected by SkillOpt-Sleep's score gate (they
      didn't beat the held-out score — there is no scope check; see the
      CLAUDE.md exposure below) — non-mock, coherent, real analysis, nothing
      adopted (`staging_dir` empty, SHA-256 of the live skill/CLAUDE.md/queue
      unchanged before/after). Four more measured facts from that run:
      - **Auth + model.** `claude` shells out to the local `claude` CLI
        (`claude -p --model sonnet …`; override with `SKILLOPT_SLEEP_CLAUDE_MODEL`)
        under the CLI's own login — no API key is read. With `ANTHROPIC_API_KEY`
        in the environment the calls become metered API billing and gain
        `--bare`. `-y` is required, not a convenience: skill-forge refuses a
        non-`mock` backend under `--json` without it.
      - **Cost.** 20 `claude -p` calls, 9m53s, 1.92M tokens on claude-sonnet-5
        (1.62M cache-write, 0.25M cache-read, 50k output — ≈ $7 at API list
        price; every cache write was 1-hour TTL, i.e. 2× input). ~52k of every
        call is fixed CLI context because non-`--bare` loads hooks and plugins,
        and each call re-writes it to cache rather than reading it back. The
        wrapper forwards only `--lookback-hours`; SkillOpt's `max_tokens_per_night`
        is never enforced; the only other caps are `max_tasks_per_night` /
        `max_sessions_per_night` in `~/.skillopt-sleep/config.json` (defaults 40
        and 120 — roughly an order of magnitude above the measured run).
      - **The proposal answers SkillOpt's own mined tasks, not the queued
        signals** — the queue only picks the target. Step 3's fold-in is still
        how a specific signal lands.
      - **CLAUDE.md exposure — mitigated.** `evolve_memory` defaults to `true`:
        "memory" is `<repo-of-signals>/CLAUDE.md`, an accepted run stages
        `proposed_CLAUDE.md`, and skill-forge's promote would adopt it together
        with the skill. `~/.skillopt-sleep/config.json` now sets
        `"evolve_memory": false` (applied 2026-09-04, machine-wide — this file
        did not exist before) so a real `run` can no longer touch CLAUDE.md at
        all. Still HOLD (never auto-promote) any staging dir that contains a
        `proposed_CLAUDE.md` regardless — a future config change or a run on a
        different machine could re-enable it. Side effect of every run: one
        `claude -p` transcript per call under
        `~/.claude/projects/*skillopt-sleep-claude-*/` (not auto-cleaned;
        20 accumulated from today's verification and were left in place).
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
- A real `run` stages under `<repo-of-signals>/.skillopt-sleep/staging/` —
  `.skillopt-sleep/` is gitignored repo-wide (added 2026-09-04); never force-add it.
- Before any whole-file rewrite that touches more than ~10 entries (a bulk
  triage pass, not a single status flip), copy the queue to
  `~/.claude/context-manager/refinement-queue.jsonl.bak-<YYYY-MM-DD>` first —
  one `cp` / `shutil.copy2`, no rotation. It lives next to the queue file,
  never in a session scratchpad (2026-09-04: 125 entries were rewritten with
  the only copy in a scratchpad that died with the session). Never overwrite
  an existing backup; if today's already exists, suffix the time (`-HHMM`).
- Queue writes are whole-file rewrites; if the file changed mid-run (mtime
  check), re-read and merge before writing.
