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

## Fix Round 1 — bounded planning lifecycle

### Corrected behavior

- Calendar planning now represents new events with `targetId: null`. New blocks reconcile by operation key and use event insertion; updates first prove that the supplied Google event ID carries a Rhize operation marker. The runtime validator and JSON Schema permit null only for `calendar_upsert`.
- Setup scope is a server-owned, authenticated approval flow that works before profile activation. `POST /v1/setup/connectors` accepts one strict connector-specific scope, performs only read-only discovery/validation, persists a resumable `scope_expand` preview, and returns the exact operation. Existing operation approval records the setup approval without activating preferences. Final profile and Slack-config saves accept only covered approved scopes and consume the approval. Later project/type, calendar, Reminders, or Slack scope expansion must repeat this preview; planning-material changes clear first-plan approval.
- `POST /v1/setup/probe` now has explicit `preview` and revision-bound, once-only `apply` modes. Apply creates, verifies, deletes, and verifies absence for one exact Rhize Tasks reminder and one exact focus-calendar event, audits success/failure, and never activates automation.
- The runtime provisions a 32-byte random API bearer into the approved Keychain pair when absent. `provision-token --json` reports only metadata. Bearer comparison hashes both inputs to a fixed length before `timingSafeEqual`.
- Catch-up evaluates the saved local timezone and morning/midday/evening schedule, selects at most one due phase across sleep/wake boundaries, preserves midday active/completed/manual/frozen blocks, and makes evening a prompted next-day reconciliation with carryover updates.
- Awareness Reminders are read from exact configured lists with per-list title redaction and become immutable protected intervals from `startAt` or `dueAt`; writes and cleanup remain restricted to the Rhize Tasks list. Titles can surface only through the existing approved-label plus profile privacy gate.
- Slack delegations retain exact Jira key/URL/state and UUID. Only one Jira task whose description contains the exact marker line is merged; unmatched Jira-ready and `needs_jira` messages remain provisional and unscheduled.
- The service serves only `/`, `/app.js`, and `/styles.css` from the loopback dashboard directory. `dashboard --json` issues a short-lived, single-use bootstrap nonce; `GET /session?nonce=...` exchanges it for an in-memory `HttpOnly; SameSite=Strict` session cookie. Long-lived bearer values are never placed in URLs, browser storage, plist data, responses, or audit records. All `/v1` data remains authenticated.

### Regression coverage

- Nullable Calendar create versus proven-ID update and absence of a fabricated event ID in POST paths.
- Pre-activation Jira/Calendar/Reminders/Slack scope discovery, exact preview persistence/resumption, explicit approval, final-scope enforcement, expansion gating, and first-plan invalidation.
- Revision conflict, once-only sample probe, exact create/find/delete/find sequence for both writable systems, and no activation from probing.
- Strong first-run bearer provisioning, Keychain-only storage, output/audit non-disclosure, and fixed-work authentication comparison.
- DST-aware local phase selection, multiple missed phases collapsing to one, midday preservation, evening/carryover behavior, pause, and partial outage isolation.
- Awareness-list process scoping, redaction, protected-time overlap prevention, and rejection of writes outside the Rhize list.
- Exact delegation-marker merge, Jira state retention, `needs_jira` provisional handling, and idempotent repeated ingestion.
- Static asset allowlist, raw traversal rejection, unauthenticated data rejection, nonce single use/expiry, cookie flags, and nonce audit redaction.

### Validation evidence

- Focused Task 7 plus Reminders boundary: `node --test rhize-tasks/tests/e2e/local-service.test.mjs rhize-tasks/tests/e2e/lifecycle-fix-round-1.test.mjs rhize-tasks/tests/failure-injection/routines.test.mjs rhize-tasks/tests/connectors/reminders-process.test.mjs` -> 52 passed, 0 failed.
- Current shared-tree full suite from `rhize-tasks`: `npm test` -> 150 passed, 0 failed.
- Package validation: `npm run validate` -> passed.
- Syntax: `node --check` for the CLI and all changed API/scheduler modules -> passed.
- The first repository-root `npm test` invocation failed with `ENOENT` because the package manifest is intentionally under `rhize-tasks/`; the command was rerun from the actual package root and passed. Loopback tests required sandbox approval only to bind temporary `127.0.0.1` ports; all external transports, credentials, Keychain calls, and helper processes remained injected fakes.

### Cold review and remaining gate

- Re-read the final source/tests for auth bypass, nonce/bearer disclosure, client-authored setup operations, scope reuse, premature activation, calendar fake IDs, non-Rhize Reminders writes, fuzzy delegation merge, broad static paths, and routine double dispatch. No such path remains in the tested boundary.
- No runtime dependency or Task 6 installer/launchctl test edit was introduced. Concurrent Task 8 dashboard/skill/command files were not staged as Task 7 work.
- The same intentionally unperformed live Tom-Mac acceptance gate above remains. Setup probe failure is fail-closed and audited; it does not claim activation or successful cleanup without exact post-delete absence checks.

## Fix Round 2 — lifecycle-owned reconciliation

### Corrected behavior

- Focus-calendar events are considered mutable only when all three private properties are present: `rhizeOperationKey`, `rhizeTaskId`, and `rhizeBlockSlot`. Snapshot sync removes only those proven-owned events from protected time. Planning reuses the stable logical `taskId:sessionIndex` slot across plan revisions, updates the proven Google event ID, creates only a missing slot, and proposes deletion only for exact orphaned owned events. Unmarked focus events and all outside-calendar events remain immutable commitments.
- Catch-up completion now stores the selected due instance plus every earlier missed instance and records all of them in one database transaction. The next poll is therefore `not_due` until a genuinely new phase. Evening carryover is limited to unfinished, nonterminal owned tasks that appeared in the prior approved plan; opportunities, provisional work, terminal work, and never-scheduled tasks are excluded.
- Authenticated pre-profile discovery uses credential-backed, discovery-only adapters and never depends on an active profile. Jira, Calendar, Reminders, and Slack responses expose only sanitized identifiers/names/configuration, and the common mutation/snapshot methods on production discovery adapters return `unsupported`.
- Setup probes now require the current plan revision and previously approved exact Reminders/Calendar scope at preview and apply. The pending record contains the exact scope, operations, operation keys, and revision. Apply persists its actor approval audit before acquiring connectors or performing a side effect, reconciles an ambiguous create by exact `findByExternalId`, verifies both samples, and always attempts exact cleanup. An unproven ambiguous result remains `reconciliation_required` and never returns a verified response.
- Installer activation now verifies an existing strong API bearer or generates, writes, and reads back a new 32-byte bearer through the injected Keychain adapter before LaunchAgent activation. Existing tokens are never rotated implicitly. Keychain failure aborts activation; a newly introduced token is deleted during rollback. Runtime bootstrap no longer creates or rotates credentials and fails closed when installation did not provision a valid bearer. This supersedes the Fix Round 1 runtime-provisioning statement above.
- `POST /v1/plans/preview` now accepts only `{planRevision, planningDate?}`. The service validates the optional Gregorian date, performs its own connector snapshot and planning pass, and derives the exact operations. Client-authored operation arrays are rejected. An empty plan is approvable only with the explicit `zeroWorkReason: "no_eligible_tasks"`; an empty plan with eligible work is rejected at approval.

### Regression coverage

- Proven owned event update, orphan deletion, stable block-slot key, user focus-event protection, and exact private-property round trip.
- DST/backlog catch-up collapse with a second same-wake evaluation returning `not_due`.
- Pre-profile discovery factory invocation in discovery-only mode.
- Existing/missing/failed Keychain bearer behavior and installer rollback paths.
- Server-owned plan preview contract plus existing revision, activation, approval replay, and JSON strictness E2E coverage.
- Existing setup-probe tests now require approved scope and prove revision binding, once-only execution, verification, exact deletion, and non-activation.

### Validation evidence

- Focused lifecycle/installer/routine boundary: `node --test tests/e2e/lifecycle-fix-round-2.test.mjs tests/connectors/reminders-process.test.mjs tests/failure-injection/routines.test.mjs` -> 42 passed, 0 failed after the final installer state correction; the narrower final lifecycle/installer rerun was 35 passed, 0 failed.
- Full package suite with ephemeral loopback permission: `npm test` -> 155 passed, 0 failed.
- Package validation: `npm run validate` -> passed.
- Syntax: `node --check` for changed context, routes, probe, Calendar connector, and installer modules -> passed.
- Diff hygiene: `git diff --check` -> passed.
- No network, real Keychain, real Google/Jira/Slack transport, or real Reminders helper was used; every external boundary was injected.

### Cold review and handoff

- Re-read the changed service, connector, scheduler, installer, schema, and tests for unproven Calendar deletion, plan-revision-dependent ownership, catch-up replay, broad discovery, pre-audit probe writes, token disclosure/rotation, and client-authored plan operations. No such path remains in the tested boundary.
- Task 8 must update its plan-preview request to the exact contract `POST /v1/plans/preview` with `{planRevision, planningDate?}`. The response contains the server-derived `operations`, `approvalsRequired`, freshness, and `zeroWorkReason`.
- The live Tom-Mac acceptance gate remains intentionally unperformed.

## Fix Round 3 — ambiguous setup-write cleanup

### Corrected behavior

- Calendar operation-key lookup now returns the exact matched event ID together with its revision. Setup-probe reconciliation treats that exact marker proof as authoritative, does not issue another create, retains the ID for cleanup, and verifies absence through both the event ID and private operation key. A lost create response followed by marker proof therefore produces one create, one exact delete, and no leaked sample.
- Calendar and Reminder cleanup are attempted independently. Repeated ambiguous Calendar lookup or unresolved cleanup persists the pending probe as `reconciliation_required`, returns an ambiguous reconciliation error, and still removes the exact Reminder sample. A verified absent Calendar sample is accepted even when the delete response itself was lost.
- `planningDate` is genuinely optional on strict `POST /v1/plans/preview` requests. Omitted dates are derived server-side in the saved profile timezone; supplied values still require a real Gregorian `YYYY-MM-DD` date.
- Keychain provisioning cleanup is now compound and verifiable. A failed readback attempts deletion, verifies the approved pair is absent, and reports exact non-secret cleanup states when deletion or verification fails. Later activation rollback applies the same delete-and-verify rule to a newly introduced bearer; any failure is included in the installer rollback state.
- Applied-plan reconciliation is covered end to end: the second plan reuses and moves the proven owned event, deletes an exact orphan, keeps one logical block/event, and never writes or deletes the unmarked user focus event.

### Regression and validation evidence

- Focused route/probe/Calendar/installer suite: `node --test tests/e2e/lifecycle-fix-round-2.test.mjs tests/e2e/local-service.test.mjs tests/connectors/reminders-process.test.mjs tests/connectors/fix-round-3.test.mjs` -> 57 tests, 57 passed after the final test-fixture path correction.
- Full package suite with ephemeral loopback permission: `npm test` -> 160 passed, 0 failed.
- Package validation: `npm run validate` -> passed.
- Syntax: `node --check` for routes, setup probe, Google Calendar, and installer modules -> passed.
- LaunchAgent template: `/usr/bin/plutil -lint installer/media.rhize.tasks.plist.template` -> `OK`.
- Diff hygiene: `git diff --check` -> passed.
- All credentials, transports, Keychain behavior, Calendar state, helper behavior, and loopback requests remained injected and hermetic; no live I/O ran.

### Cold review

- Re-read the final diff for duplicate creates after proof, lost cleanup authority, false verified responses, skipped Reminder cleanup, optional-field strictness regressions, secret-bearing compound errors, unverified token rollback, duplicate owned events, broad deletion, and user-event mutation. The new tests exercise each boundary and the full suite remains green.
- Task 8 files were not modified. The plan-preview contract remains `{planRevision, planningDate?}`.
- The live Tom-Mac acceptance gate remains intentionally unperformed.

## Fix Round 4 — fail-closed Calendar probe verification

### RED and corrected behavior

- Two production Google Calendar connector fixtures initially failed because a successful event POST followed by transiently absent marker/ID reads was incorrectly returned as `{verified:{calendar:true}}`.
- Calendar probe state now separates a known create/result ID, exact positive operation-marker proof, confirmed delete dispatch/response, and final absence. `calendarProven` is set only when the private operation-key lookup returns the same nonempty event ID.
- A known POST result remains exact cleanup authority even when verification is transiently absent, but absence alone cannot prove cleanup. If the connector's delete preflight cannot find the event and therefore sends no DELETE, the probe persists `reconciliation_required` with non-secret cleanup state and never returns verified success. The original verification failure is not cleared by later null lookups.
- A reconciliation replay reuses the preserved event ID and never issues another create. Only a later positive marker-to-ID match allows the exact delete; success then additionally requires the confirmed delete result and verified absence by both event ID and operation key. Reminder cleanup remains independent on every path.

### Regression and validation evidence

- Focused lifecycle suite: `node --test tests/e2e/lifecycle-fix-round-1.test.mjs tests/e2e/lifecycle-fix-round-2.test.mjs` -> 17 passed, 0 failed.
- The transient-loss fixture uses the production Google Calendar connector: one event POST, no DELETE after the connector's 404 preflight, pending `reconciliation_required`, no verified response, and successful Reminder cleanup.
- The recovery fixture runs the same pending probe again after visibility returns: still one total event POST, exact marker proof, one DELETE, absence by ID and marker, no Calendar or Reminder sample left, and verified success.
- Full package suite with ephemeral loopback permission: `npm test` -> 162 passed, 0 failed.
- Package validation: `npm run validate` -> passed.
- Syntax and diff hygiene: `node --check rhize-tasks/service/src/api/setup-probe.mjs` and `git diff --check` -> passed.
- No network, real Keychain, live Calendar, or helper process was used; transports and connector state remained injected and hermetic.

### Cold review

- Re-read the state transitions for false proof, duplicate create on replay, delete-preflight 404, response-lost ambiguity, final-null false success, stale pending IDs, and skipped Reminder cleanup. Success now requires every positive and cleanup gate in the same attempt; unresolved history remains pending for reconciliation.
- Task 8 dashboard, skills, commands, and tests were not modified. The paused Task 8 read-only review can resume independently.
- The live Tom-Mac acceptance gate remains intentionally unperformed.

## Final reconciliation contract — prompted resume authority

### Corrected behavior

- Added the single-purpose transactional `resumeReconciliation(id, actor)` repository transition. It accepts only approved operations currently in `reconciliation_required`, preserves the prior normalized result in the same-transaction audit event, clears the active result, resets the state to `pending` and attempt count to zero, and therefore grants exactly one new maximum-two-attempt budget after explicit human approval. Other operation states and unapproved records are rejected.
- `POST /v1/reconcile` now accepts only `{planRevision, operationIds, actor}`. It rejects empty/duplicate/unknown IDs, stale revisions, paused automation, unapproved or non-reconciliation records, and unhealthy affected connectors before changing operation state. The exact human request is audited before any resume. Only the selected persisted IDs are resumed and passed to the existing idempotent connector executor; no client-authored operation data or new ID is accepted.
- A repeated ambiguous connector outcome returns the operation to `reconciliation_required`; it is never retried automatically. A later explicit request starts another independently bounded attempt whose connector marker/preflight runs before mutation.
- TodayView now requires a separate `reconciliation` array containing only sanitized `{operationId, kind, targetSystem, reason}` records. Reasons come from a fixed safe internal allowlist or the generic `reconciliation_required` value, and reconciliation records are not duplicated in the approval-required list.

### Regression and validation evidence

- Focused storage/API/schema/dashboard boundary: `node --test tests/e2e/local-service.test.mjs tests/e2e/dashboard.test.mjs tests/unit/storage.test.mjs tests/unit/schema-contract.test.mjs` -> 30 passed, 0 failed.
- Full package suite after the final safe-reason allowlist review: `npm test` -> 170 passed, 0 failed.
- `npm run validate` -> passed; `claude plugin validate rhize-tasks` -> passed; all six `quick_validate.py` skill checks -> valid.
- `node --check` for the changed dashboard, API, context, storage, and TodayView modules -> passed. `git diff --check` -> passed.
- Tests prove the prior terminal-replay behavior, transactional reset/audit preservation, actual connector health/preflight/write after explicit resume, exact selected-ID isolation, audit ordering, stale/paused/unapproved/wrong-state/duplicate rejection, and a second ambiguous result returning to prompted reconciliation.

### Cold review

- Re-read the final boundary for generic state mutation exposure, implicit retries, actor omission, client-supplied operation substitution, pre-audit state changes, partial selected-ID broadening, unsafe persisted reason disclosure, and approval/reconciliation mixing. The public API exposes only the purpose-built route and the repository transition remains state-specific.
- Loopback tests used only the local hermetic server with injected connectors and credentials. No live connector, Keychain, helper, or external network call ran.

## Final authority race closure

- After all asynchronous connector health checks, reconciliation now enters one synchronous database transaction. That transaction re-reads the latest plan revision and both persisted pause sources, then re-reads every exact selected record and verifies its ID, plan revision, approved state, `reconciliation_required` state, target system, kind, and idempotency key against the pre-health snapshot.
- The same transaction appends the human request audit and resumes every selected operation. A stale plan, newly paused service, or changed selected operation rolls back the complete batch, so no partial multi-operation reset or request audit survives. The returned transaction revision—not an unchecked request cache—is passed to the existing executor.
- Deferred-health loopback regressions pause automation, save a new plan, and change the selected operation while health is pending. Each returns HTTP 409 with no connector write, no operation reset, and no reconciliation-request audit. A storage regression changes the second of two selected records and proves the first reset and batch audit both roll back.

### Validation

- Focused storage and loopback boundary: `node --test tests/unit/storage.test.mjs tests/e2e/local-service.test.mjs` -> 21 passed, 0 failed.
- Final full suite: `npm test` -> 175 passed, 0 failed.
- `npm run validate`, changed-module syntax checks, and `git diff --check` -> passed.
- Cold review confirmed there is no `await` between the final transactional authority checks, audit, and all selected resets; the route no longer performs per-operation resume transactions.
