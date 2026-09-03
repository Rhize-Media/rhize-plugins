# Changelog — rhize-context-manager

Entries before 2026-09-03 live in [docs/release/CHANGELOG-history.md](../docs/release/CHANGELOG-history.md).

## [Unreleased]

### Added

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
