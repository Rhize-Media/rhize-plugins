# Changelog — rhize-ops

Entries before 2026-09-03 live in [docs/release/CHANGELOG-history.md](../docs/release/CHANGELOG-history.md).

## [Unreleased]

### Added

- _2026-09-03_ **rhize-ops/skill-monitor:** the benchmark watchdog now watches the
  Rhize Dashboard Snapshot Refresh Arm-A pre-check — a sixth note
  (`Project-Dashboard/Procedural Memory Benchmark.md`, Desktop scheduler key
  `rhize-dashboard-snapshot-refresh`), registered the day the routine was instrumented
  (claude-routines `a6e65a1`) so it is never instrumented and unmonitored; a registration
  test asserts the note, scheduler-key and receipt-id maps share one key set.
- _2026-09-03_ **rhize-ops:** `delegate-to-teammate` progressive disclosure — Jira now gets a
  concise brief (target ≤ 1,500 chars: what/why, done criteria, one gotcha, one starter prompt,
  links) instead of the full task package, which moves to a Confluence "handoff brief" page, with
  one Confluence context page (alongside the existing Slack Canvas) per Obsidian vault note the
  delegation relies on; a new `references/handoff-brief-template.md` defines both page layouts. No
  local, vault-relative, or repo-relative path may appear in any Jira, Slack, or Confluence output
  — `scripts/delegation_lint.py` gates every external write, and `scripts/vault_note_export.py`
  turns a vault note into Confluence-ready markdown plus a local export ledger. The config's
  optional `confluence` block (space, "Delegations" parent page) is resolved by a new step in
  `/rhize-ops:delegate-setup`; a config without it, or marked `incomplete`, falls back to today's
  full-description-in-Jira behavior. Also fixes stale Obsidian tool names and a stale
  transcript-tool reference in the skill body. Measured motivation (last 50 delegated issues):
  median Jira description ~4,500 chars (max ~13,700), and 8 of 50 carried a vault- or
  repo-relative path the recipient couldn't open.
- _2026-09-03_ **rhize-ops/skill-monitor — benchmark watchdog covers every instrumented
  routine.** `benchmark_status.py` now reads a fifth note (Weekly Skill Audit,
  `Skill-Audit-and-Monitoring/Procedural Memory Benchmark.md`) and a sixth data source: the
  private lifecycle state files under `~/.rhize/procedural-memory/routine-state/`, whose
  `startedAtEpochMs` is written at run start by `routine-benchmark.py`. Run recency is now the
  newest of the Desktop registry's `lastRunAt` and that routine-state start, so a routine whose
  canonical scheduler is Registry-B (which persists no timestamp on disk) is no longer
  invisible — Weekly Skill Audit had been instrumented since 2026-08-30 and unmonitored. The
  human report names the source per routine (`via desktop+routine-state`). Ten new tests; the
  shared receipt-snapshot test helper now isolates `routine_state_dir`. Found while fixing the
  `bench-append` capture crash (procedural-memory: `datetime.UTC` is 3.11+, Cowork's host
  `python3` is 3.9.6 — every scheduled append 2026-08-31 → 09-02 landed a row with no receipt).
  The pinned wrapper in claude-routines (`run-pinned-benchmark-status.sh`) still runs rhize-ops
  0.13.6; a release plus pin update is needed before the weekly routine picks this up.
