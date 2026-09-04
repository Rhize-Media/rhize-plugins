# Changelog — rhize-context-manager

Entries before 2026-09-03 live in [docs/release/CHANGELOG-history.md](../docs/release/CHANGELOG-history.md).

## [Unreleased]

### Added

- _2026-09-04_ version bump — 0.25.3 → 0.26.0 (minor); marketplace 2.62.0 → 2.63.0.
- **Inferred router signals for third-party skills** (WP-I,
  `.claude/plans/skill-governance-optimization.md`). `build_local_skill_map.py`
  now infers up to 3 topic/stack tags per installed third-party skill from its
  name+description against `catalog/tags.json`'s vocabulary, and writes them
  into the resolved indexes' `router.signals[skillId]` as half-weight
  `{kind: "tag-inferred", weight: 0.5}` entries (resolved indexes'
  `schemaVersion` bumped to `1.2.0`; the static artifact and schema are
  untouched); every third-party skill also gets an unconditional `name`
  signal, so index membership never depends on inference hitting.
  `route-core.js`'s `routeFromIndex()` now requires at least one full-weight
  (`weight >= 1`) matched signal, so an inferred-only match never qualifies;
  the half weight itself (max `1 + 3 × 0.5 = 2.5` vs. a declared `1 + 2 = 3`)
  is what keeps an inferred-backed match from outranking a declared one. `skill-router.js` and `agent-brief-router.js`
  render a third-party skill's three-segment id as `<plugin>:<skill>`
  (previously rendered with the marketplace segment attached, e.g.
  `claude-plugins-official:mattpocock-skills/tdd`) and suffix an inferred
  label with `(inferred)`. New `build_local_skill_map.py --report-inferred`
  flag prints a per-skill inferred-tag table without writing anything, for a
  precision review. See `docs/skill-map/edge-semantics.md`'s "Inferred router
  signals for third-party skills".
- `skill-refine.md`'s `review` section and `learn-harvest.md` now document
  that a `target_skill` under any plugin cache or marketplace checkout
  (`~/.claude/plugins/cache/`, `~/.claude/plugins/marketplaces/`,
  `~/.codex/plugins/`) is refused at review — fork/vendor into a Rhize
  plugin (recording the fork + drift check in `SOURCES.md`) or contribute
  upstream instead — and that routing such a signal through `skill-forge
  refine capture` is deferred until its project-scope override files can be
  materialized into a plugin cache.
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
