# Task 7 implementation report

## Result

Implemented one production-bootstrap-capable local planning service with a loopback-only authenticated API, bounded scheduler, sanitized TodayView, CLI, and the exact Task 6 item-cleanup handshake. No live network, Keychain, launchctl, Reminders, Calendar, Jira, or Slack operation was performed.

Commit: `feat(tasks): serve one bounded local planning authority` (this commit)

## RED evidence

- `node --test tests/e2e/local-service.test.mjs tests/failure-injection/routines.test.mjs` initially failed at module load because `service/src/api/context.mjs` and `service/src/api/cleanup.mjs` did not exist.
- The new tests were kept hermetic through temporary SQLite databases, injected Keychain/connector/HTTP fakes, in-process loopback requests, and temporary lock/artifact paths.

## Implemented behavior

- `service/src/api`
  - Production context opens the local SQLite database and migrations, composes repositories, Keychain, HTTP transport, and profile-scoped Jira, Google Calendar, Reminders, and optional Slack connectors.
  - `createServer(context)` refuses any bind host except `127.0.0.1` and also rejects non-loopback peers.
  - `/health` returns only version/status. Every `/v1/*` route requires the Keychain-backed bearer token.
  - Strict JSON handling requires `application/json`, caps bodies at 64 KiB while reading, rejects malformed/non-object bodies, and enforces exact route fields, profile validation, and current plan revisions.
  - Named setup, Today, preview/approval, operation approval, opportunity, reconcile, preference, pause, audit, and doctor routes are implemented. Preview/approval/reconciliation audit records are persisted before connector application.
  - Activation requires both a saved, setup-complete profile and a persisted first approved plan. Replayed plan approval uses the persisted operation state and cannot duplicate an applied connector write.
  - Connector refresh is partial-failure aware: freshness is retained per system, unavailable systems pause only their own proposed writes, and no raw connector/credential error is returned by the API.
- `service/src/scheduler`
  - Exclusive 0600 lock files prevent concurrent routines. Only a stale lock whose recorded process is demonstrably dead is reclaimed.
  - Morning, midday, evening, and catch-up share the same activation/pause, sync, preview, approval, operation, and audit authority.
  - Missed intervals collapse into one catch-up evaluation. Midday preservation converts active, completed, manual, and freeze-window blocks into immutable planning intervals.
- `service/src/views`
  - TodayView projects the exact plan revision, chronological timeline, current/next focus blocks, capacity/buffer risk, carryovers, approvals, opportunities, estimate warnings, connector freshness, pause, and degraded state.
  - Outside commitments use deterministic opaque IDs and omit source ID/title/description unless a separately stored label was explicitly approved and the profile permits display.
- `service/bin/rhize-tasks.mjs` and package start
  - Implements `serve`, `routine morning|midday|evening|catch-up`, `doctor --json`, `artifact --output`, `install`, `uninstall`, and the internal `uninstall-items --json` handshake.
  - The package `start` script runs the loopback service. CLI failures emit one structured error kind, never a raw message, process output, authorization header, or credential.
  - Artifact output is an atomic 0600 sanitized TodayView JSON snapshot; Task 8 owns the later standalone HTML renderer.
- bounded uninstall cleanup
  - Reads exactly one bounded JSON line and requires the byte-for-byte Task 6 request schema/scope/property contract.
  - Reminders deletion candidates come only from attempted persisted plugin upserts in the exact configured Rhize list. The connector snapshot is checked before and after deletion.
  - Calendar deletion candidates come only from attempted persisted focus-calendar upserts with valid operation keys. Each key is queried only through `privateExtendedProperty=rhizeOperationKey=<key>`, with bounded/repeated-token-safe paging; only exact matching event IDs are deleted, and a second exact lookup must prove absence before the deletion count is marked verified.
  - Any malformed, offline, timeout, ambiguous, or unverifiable result fails closed so Task 6 retains the local installation and data.

## Regression coverage

- Loopback-only bind/peer boundary, minimal health, missing/wrong bearer rejection.
- Saved-preference plus first-plan activation gate.
- Stale plan revision rejection and duplicate approved-plan replay without duplicate writes.
- Wrong content type, oversized JSON, unknown fields, Keychain credential non-echo, and sanitized audit output.
- Outside-calendar source ID/title/description redaction and focus-only current/next projection.
- Single-instance overlap, dead stale-lock reclaim, exactly-one catch-up, pause, partial source outage, and midday protected states.
- Exact one-line Task 6 CLI handshake, malformed extra-line rejection, private atomic artifact output, exact persisted Reminders/Calendar ownership, offline fail-closed behavior, and Calendar post-delete verification.

## Validation evidence

- Focused Task 7: `node --test tests/e2e/local-service.test.mjs tests/failure-injection/routines.test.mjs` -> 13 passed, 0 failed.
- Full Node: `npm test` -> 135 passed, 0 failed.
- Package validation: `npm run validate` -> passed.
- Syntax: `node --check` for the CLI and all Task 7 API, scheduler, and view modules -> passed.
- Diff hygiene: `git diff --check` -> passed.
- Tests required sandbox approval only to bind an ephemeral `127.0.0.1` port; all transports, credentials, helper processes, and external systems remained fake.

## Cold review

- Re-read the complete Task 7 implementation and tests against the approved Task 7 plan and Task 6 cleanup request/response contract.
- Confirmed no runtime dependency, broad bind, unauthenticated `/v1` route, secret-bearing response/audit field, outside title/source ID, live I/O, broad reminder/calendar scan, unverified uninstall count, silent opportunity claim, or unsupported automatic Jira write was introduced.
- Confirmed deterministic code-point ordering, focus-only current/next selection, audit-before-connector ordering, exact-scope staging, and no Task 6 installer/launchctl/connector-test file modification.

## Remaining acceptance gate

- The approved final Tom-Mac acceptance run remains intentionally unperformed: provision the API bearer and connector credentials in Keychain, complete setup/dry-run approval, exercise one disposable focus block/reminder, simulate pause/restart/catch-up/revocation, and verify bounded uninstall against disposable containers. Any failure should leave automation paused and item deletion unverified.
