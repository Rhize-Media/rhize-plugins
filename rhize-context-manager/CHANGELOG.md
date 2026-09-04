# Changelog — rhize-context-manager

Entries before 2026-09-03 live in [docs/release/CHANGELOG-history.md](../docs/release/CHANGELOG-history.md).

## [Unreleased]

### Added

- _2026-09-04_ version bump — 0.25.3 → 0.26.0 (minor); marketplace 2.62.0 → 2.63.0.
- _2026-09-03_ version bump — 0.25.2 → 0.25.3 (patch); marketplace 2.60.0 → 2.61.0.
- _2026-09-03_ version bump — 0.25.1 → 0.25.2 (patch); marketplace 2.59.1 → 2.60.0.
- _2026-09-03_ version bump — 0.25.0 → 0.25.1 (patch); marketplace 2.58.1 → 2.58.2.
- `tests/rhize-context-manager/test_harvest_noise_filter.py` — first test
  coverage for `scripts/harvest_noise_filter.py` (30 cases: tokenizer,
  reference-building, all four classification outcomes at their boundaries,
  `--max-blocks` union behavior, default-threshold regression pin).

### Changed

- `build_local_skill_map.py` and `suggestion_log_report.py` now resolve the
  skill-usage monitor's data directory through a shared `skill_monitor_data_dir()`
  helper (mirroring the standalone rhize-skill-monitor tool's own `paths.py`
  precedence: `RHIZE_SKILL_MONITOR_HOME`, else `RHIZE_SKILL_MONITOR_ROOT`/the
  default checkout's `data/`, else `~/.rhize/skill-monitor/data`) instead of the
  old hardcoded `rhize-ops/skill-monitor/data/` path, now that the monitor ships
  as its own repo. `/learn-harvest`'s runbook steps were updated to match.
- `/skill-refine run`'s `evolve` invocation now passes `--backend claude`
  explicitly — it previously fell back to SkillOpt-Sleep's offline `mock`
  backend silently, which is why the pipeline had never actually consumed a
  queue entry via `evolve` (all 30 prior consumptions were manual fold-ins).
  Verified via a direct, capped `skillopt-sleep dry-run --backend claude`
  (6 sessions, 5 mined tasks, baseline 0.29 → candidate 0.63, 4 genuine
  proposed edits) — the wrapper's `--backend` passthrough was confirmed at
  source (`evolve.ts:152`), not executed end-to-end with a real backend, to
  keep the one real-backend run capped and bounded. Requires `skillopt-sleep`
  on PATH (`pipx install skillopt`).
- `/learn-harvest`'s noise filter reference set (both the command and the
  `daily-learn-harvest` scheduled routine) now includes `docs/session-guardrails.md`
  and the invoking project's auto-memory `MEMORY.md` — MEMORY.md was the
  dominant missing reference (headroom's dry-run output echoes existing
  MEMORY.md sections back as apparent new findings). Measured against the
  reference docs alone (queue excluded), adding MEMORY.md moved 21 of 41
  candidates in a real 2026-09-03 batch from "kept" to correctly `suppressed`;
  with the live queue's own 821 reference chunks included (production
  config), the queue already caught most of that overlap, so the incremental
  production delta on that same batch was 1 of 41 — still a real, cost-free
  fix (a missing reference file warns and skips, never errors), and its value
  scales with how sparse a given project's queue history is.
- `headroom learn` calls in both files now pass `--main-only`, bounding each
  run to top-level sessions (no time-bounded lookback exists otherwise, and
  reanalyzed session counts were growing weekday over weekday). Daily cadence
  itself is kept — the weekly `headroom-learn-sweep` task that would have
  provided redundant coverage is currently disabled.
