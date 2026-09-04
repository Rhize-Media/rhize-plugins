# Changelog — rhize-context-manager

Entries before 2026-09-03 live in [docs/release/CHANGELOG-history.md](../docs/release/CHANGELOG-history.md).

## [Unreleased]

### Added

- **Inferred router signals for third-party skills** (WP-I,
  `.claude/plans/skill-governance-optimization.md`). `build_local_skill_map.py`
  now infers up to 3 topic/stack tags per installed third-party skill from its
  name+description against `catalog/tags.json`'s vocabulary, and writes them
  into the resolved indexes' `router.signals[skillId]` as half-weight
  `{kind: "tag-inferred", weight: 0.5}` entries (resolved indexes'
  `schemaVersion` bumped to `1.2.0`; the static artifact and schema are
  untouched). `route-core.js`'s `routeFromIndex()` now refuses to qualify a
  match whose signals are ALL `tag-inferred`, so an inferred-backed match can
  never outrank a declared one. `skill-router.js` and `agent-brief-router.js`
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

### Changed

- `build_local_skill_map.py` and `suggestion_log_report.py` now resolve the
  skill-usage monitor's data directory through a shared `skill_monitor_data_dir()`
  helper (mirroring the standalone rhize-skill-monitor tool's own `paths.py`
  precedence: `RHIZE_SKILL_MONITOR_HOME`, else `RHIZE_SKILL_MONITOR_ROOT`/the
  default checkout's `data/`, else `~/.rhize/skill-monitor/data`) instead of the
  old hardcoded `rhize-ops/skill-monitor/data/` path, now that the monitor ships
  as its own repo. `/learn-harvest`'s runbook steps were updated to match.
