# Changelog — rhize-ops

Entries before 2026-09-03 live in [docs/release/CHANGELOG-history.md](../docs/release/CHANGELOG-history.md).

## [Unreleased]

### Added

- _2026-09-04_ **rhize-ops:** `scripts/jira_attach.py` uploads exported vault-note copies and
  their embedded files to the Jira issue via the Atlassian REST API, and `delegate-to-teammate`
  Step 7 gets a new "Upload attachments" step that calls it right after the Jira issue is
  created.

### Changed

- _2026-09-04_ **rhize-ops:** `delegate-to-teammate`'s per-note context documents now travel as
  Jira attachments instead of per-note Confluence pages — scrubbed `.md` copies of the vault
  notes plus the images/PDFs/documents they embed. `scripts/vault_note_export.py` takes
  `--out-dir`/`--max-bytes` instead of `--ledger`, `scripts/delegation_lint.py` gains an
  `attachment-body` lint kind, and `/rhize-ops:delegate-setup` adds a read-only Keychain check
  that reports whether Jira attachments are enabled.

### Removed

- _2026-09-04_ **rhize-ops:** per-note Confluence context pages, `vault_note_export.py`'s
  `record` subcommand, the `delegate.confluence-index.json` ledger, and its
  `delegate-confluence-index` setup-manifest artifact.

### Added

- _2026-09-03_ version bump — 0.19.0 → 0.20.0 (minor); marketplace 2.60.0 → 2.61.0.
- _2026-09-03_ version bump — 0.18.0 → 0.19.0 (minor); marketplace 2.59.1 → 2.60.0.

### Changed

- _2026-09-03_ **rhize-ops: setup engine split out to `rhize-core` (repo-shape R-B).**
  `/rhize-ops:rhize-setup`, the four platform scripts, `setup/evaluation-catalog.json`,
  `schemas/*.json`, `templates/claude-home.gitignore`, and `docs/setup-artifacts.md` moved to the
  new `rhize-core` plugin. `rhize-ops/commands/rhize-setup.md` is now a **one-release
  compatibility adapter**: it forwards to `rhize-core:setup` when that plugin is installed and
  stops, otherwise it runs a byte-identical fallback copy of the same orchestrator prose against
  byte-identical fallback copies of the four scripts plus `setup/evaluation-catalog.json`,
  `templates/claude-home.gitignore`, and `schemas/*.json` — drift-tested by `tests/config-lint/
  test_platform_fallback_drift.py`. **This adapter and its fallback assets are scheduled for
  removal in the next `rhize-ops` minor version** (0.19.0) — install `rhize-core@rhize-plugins`
  before then. `rhize-ops/setup/manifest.json` keeps its five skill-monitor/savings-scorecard
  dependencies (ecc, rtk, Headroom, claude-mem, OpenWolf) and its `delegate-setup` wizard
  unchanged; only the platform artifacts (`evals-config`, `evals-receipts`, `evals-hmac-key`,
  `setup-runs`, and `project-settings`) moved to `rhize-core`'s manifest, alongside a new
  `runtime-home` artifact documenting the isolated per-suite HOME the evaluation engine already
  used but never declared.

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
  The weekly routine's wrapper in claude-routines (`run-pinned-benchmark-status.sh`) now runs
  the standalone `Rhize-Media/rhize-skill-monitor` checkout pinned to tag `v1.0.0` plus the
  script digest (claude-routines `8525d2e`), which carries this change.

### Removed

- _2026-09-03_ **`rhize-ops/skill-monitor/` (repo shape R-C, M-2):** the bundled skill-usage
  monitor (`monitor.py`, `dashboard.py`, `savings_scorecard.py`, `skill_roi.py`,
  `benchmark_status.py`, and friends) was extracted with its history to the standalone
  [`Rhize-Media/rhize-skill-monitor`](https://github.com/Rhize-Media/rhize-skill-monitor) repo.
  `tests/rhize-ops/test_devflow_control_plane_section.py`, which imported `monitor.py` directly,
  is removed with it — the same coverage lives in that repository's own test suite.

### Changed

- _2026-09-03_ **`skill-dashboard` resolves the monitor tool externally (repo shape R-C, M-2):**
  the skill now runs `scripts/skill_monitor_root.sh` to locate a `rhize-skill-monitor` checkout
  (`$RHIZE_SKILL_MONITOR_ROOT`, default `~/dev-local/RHIZE/rhize-skill-monitor`) instead of
  hardcoding `${CLAUDE_PLUGIN_ROOT}/skill-monitor/`; it stops with a clone hint when the tool
  isn't found. `setup/manifest.json` gains an optional `rhize-skill-monitor` data dependency and
  the `skill-monitor-data` artifact's viewer command is updated to match.
