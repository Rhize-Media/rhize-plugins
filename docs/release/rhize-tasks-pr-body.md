# Release Rhize Tasks: local-first unified planning

## Outcome

This release adds `rhize-tasks`, a dual Claude/Codex plugin that keeps one local planning authority for Tom's Rhize, client, other-company, and personal commitments. It also extends `rhize-ops`'s delegation contract so a recognized Slack handoff can merge into its canonical Jira issue without turning Slack into a second task database.

## Scope

- Seven-stage resumable setup with direct-to-Keychain credential entry, exact connector discovery, scope approval, reversible sample write, and first-plan activation gate.
- Deterministic today-first planning with working intervals, breaks, capacity buffer, assigned-work priority, competency-filtered opportunities, bounded carryover, and immutable plan revisions.
- Jira, Google Calendar, Apple Reminders/EventKit, and strict Slack fallback connectors.
- Loopback-only authenticated API, single-use dashboard session nonce, accessible dependency-free dashboard, and escaped read-only artifact.
- Morning, midday, evening, and exactly-once catch-up evaluation behind a single-instance lock.
- Transactional versioned installer, ad-hoc signed Swift helper, one LaunchAgent, redacted doctor output, pause/recovery controls, and two-axis uninstall retention.
- Six additive skills for Claude and Codex plus six Claude command wrappers.

## Safety boundaries

- No test or release command performs live connector writes.
- SQLite on the Mac is the planning authority; Jira is the canonical work source.
- Calendar writes are limited to the approved focus calendar; Reminder writes are limited to the exact `Rhize Tasks` list.
- Awareness calendars/lists remain read-only and outside titles stay redacted by default.
- Structured Slack fallback accepts only the exact v1 contract in one approved channel from approved sender IDs. `Needs Jira` items remain provisional and unschedulable.
- Automation is inactive until saved preferences and the first approved plan both exist.
- Every mutation is revision-bound and idempotent; ambiguous results require prompted reconciliation.
- External focus-block moves become manual locks. Exact Reminder completion creates a Jira comment proposal but never an unapproved Jira write.
- Installation and removal reject unsafe/symlinked path chains; secrets never enter plist, SQLite, runtime copies, dashboard storage, logs, artifacts, or error output.

## Validation evidence

- Focused release regressions: 5/5 pass for setup payload, Jira local-state preservation, manual Calendar movement, Reminder-completion prompting, and exact Calendar ownership cleanup.
- Disposable release acceptance: 1/1 passes all seven setup stages, approved scopes/probe/first plan, real fake Calendar/Reminder writes, manual move, completion, ambiguous Jira reconciliation, no-duplicate replan, carryover, pause/restart/catch-up, API credential revocation, exact uninstall cleanup, and byte-identical outside fixtures.
- Full Node gate: 181/181 pass on the final versioned tree. The Python delegation producer contract passes 10/10 and bump-version tests pass 2/2.
- Claude and Codex plugin validation, all six skill validations, JSON/plist syntax, skill-map tests, stale-generation checks, and two consecutive deterministic generation passes succeed.
- The canonical Swift command exposes an installed Command Line Tools compiler/SDK mismatch. The isolated documented workaround passes 8/8 tests and the release helper build succeeds without changing machine settings.
- No validation command performs live connector I/O.

## Environment gate still required

Before enabling real writes on Tom's Mac, run the documented acceptance with an approved Jira test issue and disposable Calendar/Reminder containers. It must prove macOS TCC, selected Xcode/Swift toolchain, Google OAuth, Jira workflow permissions, move/completion/carryover behavior, pause/restart/catch-up, credential revocation, and uninstall retention while outside records remain unchanged. A Command Line Tools-only Swift failure is an environment caveat, not permission to skip the full Xcode/Tom-Mac gate.

## Rollback

1. Pause automation in the local dashboard.
2. Run uninstall with explicit data and item choices. Prefer `--retain-data --retain-items` for a reversible rollback; use `--delete-items` only when exact connector cleanup is healthy and verified.
3. Reinstall the previous marketplace version. The transactional installer preserves and restores the prior runtime/plist/manifest if new activation fails.
4. Restore or rotate connector credentials in Keychain as needed. Do not copy secrets into configuration files.

The installer never deletes a prior runtime until a new activation succeeds. The uninstaller stops before local deletion if launchd shutdown or requested owned-item cleanup cannot be verified.
