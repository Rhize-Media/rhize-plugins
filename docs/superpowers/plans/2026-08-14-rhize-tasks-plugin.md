# Rhize Tasks Plugin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and release a local-first, dual-host Rhize Tasks plugin that turns approved Jira work into a realistic daily plan in Google Calendar and Apple Reminders while protecting outside commitments and preserving human approval.

**Architecture:** A dependency-free Node.js 22+ ESM service owns normalization, planning, approvals, SQLite state, loopback HTTP, connector writes, dashboard data, and bounded launchd routines. A minimal Swift/EventKit helper is the only Reminders bridge; Claude and Codex are thin adapters over the same authenticated API and schemas. The implementation extends `delegate-to-teammate` with a strict per-task `rhize-delegation:v1` producer contract but keeps Slack read-only in Rhize Tasks.

**Tech Stack:** Node.js 22+ ESM (`fetch`, `node:test`, `node:sqlite`, `http`, `crypto`), Swift 6/EventKit, SQLite, HTML/CSS/vanilla JavaScript, JSON Schema, macOS Keychain, launchd, Claude plugin manifest, Codex plugin manifest

**Spec:** `docs/superpowers/specs/2026-08-14-rhize-tasks-plugin-design.md`

## Global Constraints

- Bind the service to `127.0.0.1` only and require a Keychain-backed bearer token for every API route except `/health`.
- Store operational state under `~/Library/Application Support/Rhize Tasks`; never store credential values in SQLite, JSON, logs, prompts, or globally exported shell variables.
- Use Jira as the Rhize task authority, Google Calendar as the time authority, and only `Rhize Focus`/`Rhize Tasks` for writes.
- Read approved outside calendars and reminder lists only for availability; never mutate them and redact outside titles by default.
- Force approval-required mode until setup preferences and the first live-data plan are approved.
- Always require approval for opportunity claims, provisional links/scheduling, urgent displacement, low-confidence estimates, ambiguous Jira transitions, and connector-scope expansion.
- Use bounded replanning by default, prompted Jira reconciliation by default, one catch-up evaluation after a missed routine, a single-instance lock, immutable plan revisions, and deterministic operation idempotency keys.
- Accept Slack delegations only from configured workspace/channel/sender identities and only when anchored v1 fields plus one final lowercase UUIDv4 marker validate.
- Keep baseline planning deterministic and usable without a model API key.
- Do not add runtime npm dependencies; Node.js 22+ and macOS 14+ are the supported floors.
- Do not edit `.github/workflows/*`.
- Keep all automated connector tests hermetic; no test may write to production Jira, Calendar, Reminders, Slack, or Keychain.

## File Map

```text
docs/superpowers/specs/2026-08-14-rhize-tasks-plugin-design.md  approved contract
docs/superpowers/plans/2026-08-14-rhize-tasks-plugin.md         execution source
scripts/bump_version.py                                        dual-manifest release atomics
tests/test_bump_version.py                                     release-tool regression coverage
rhize-tasks/.claude-plugin/plugin.json                         Claude identity
rhize-tasks/.codex-plugin/plugin.json                          Codex identity and shared skills path
rhize-tasks/package.json                                       local scripts and Node floor
rhize-tasks/schemas/*.schema.json                              external data contracts
rhize-tasks/service/src/domain.mjs                             shared enums, validation, identifiers
rhize-tasks/service/src/planner/*.mjs                          pure planning rules
rhize-tasks/service/src/storage/*.mjs                          SQLite migrations and repositories
rhize-tasks/service/src/api/*.mjs                              authenticated loopback API
rhize-tasks/service/src/connectors/*.mjs                       Jira, Calendar, Slack, Reminders, Keychain
rhize-tasks/service/src/scheduler/*.mjs                        bounded routines, lock, catch-up
rhize-tasks/service/src/reconciliation/*.mjs                   operation preview/apply and drift
rhize-tasks/service/src/views/today-view.mjs                   sanitized dashboard projection
rhize-tasks/service/bin/rhize-tasks.mjs                        CLI entry point
rhize-tasks/native/reminders-helper/*                          stable EventKit app/helper
rhize-tasks/installer/*                                        install, uninstall, launchd template
rhize-tasks/dashboard/*                                        setup wizard and today-first command center
rhize-tasks/skills/*/SKILL.md                                  shared Claude/Codex adapters
rhize-tasks/commands/*.md                                      Claude slash-command wrappers
rhize-tasks/tests/*                                            unit, invariant, connector, failure, E2E
rhize-ops/skills/delegate-to-teammate/*                        v1 producer contract
rhize-ops/README.md, rhize-ops/GUIDE.md                         producer documentation
.claude-plugin/marketplace.json, README.md, CHANGELOG.md        release/catalog documentation
generated/*                                                     rebuilt skill map and catalog
```

---

### Task 1: Release Foundation and Dual Manifests

**Files:**
- Create: `rhize-tasks/.claude-plugin/plugin.json`
- Create: `rhize-tasks/.codex-plugin/plugin.json`
- Create: `rhize-tasks/package.json`
- Create: `rhize-tasks/setup/manifest.json`
- Modify: `scripts/bump_version.py`
- Create: `tests/test_bump_version.py`
- Modify: `rhize-ops/commands/bump-version.md`

**Interfaces:**
- Consumes: marketplace entries shaped as `{name, source, description, version, author, keywords, category}`.
- Produces: `rhize-tasks` version `0.0.0` in both manifests and atomic `update_plugin_manifests(plugin, version)` release behavior.

- [ ] **Step 1: Add a failing dual-manifest version test**

```python
def test_updates_claude_and_codex_manifests(tmp_path, monkeypatch):
    repo = seed_repo(tmp_path, plugin="rhize-tasks", dual=True)
    monkeypatch.setattr(bump_version, "REPO", repo)
    bump_version.apply_bumps({"rhize-tasks": "0.1.0"}, "2.28.0")
    assert load(repo / "rhize-tasks/.claude-plugin/plugin.json")["version"] == "0.1.0"
    assert load(repo / "rhize-tasks/.codex-plugin/plugin.json")["version"] == "0.1.0"
```

- [ ] **Step 2: Run the focused test and confirm the Codex manifest assertion fails**

Run: `python3 -m unittest tests.test_bump_version -v`

Expected: failure because `scripts/bump_version.py` does not update `.codex-plugin/plugin.json`.

- [ ] **Step 3: Add the two manifests and package metadata**

```json
{
  "name": "rhize-tasks",
  "version": "0.0.0",
  "description": "Local-first planning for Rhize Jira work across Calendar and Reminders",
  "author": {"name": "Rhize Media"},
  "homepage": "https://rhize.media",
  "keywords": ["tasks", "jira", "calendar", "reminders", "planning", "rhize"]
}
```

The Codex manifest includes `"skills": "./skills/"` plus an `interface` object with display name, concise descriptions, workflow category, task-planning capabilities, setup/today prompts, and Rhize brand colors. `package.json` sets `"type":"module"`, `"engines":{"node":">=22"}`, and scripts for `test`, `validate`, `start`, `install`, and `uninstall` using only checked-in files.

- [ ] **Step 4: Make release tooling update the optional Codex manifest atomically**

```python
def update_plugin_manifests(plugin: str, version: str) -> None:
    paths = [REPO / plugin / ".claude-plugin/plugin.json"]
    codex = REPO / plugin / ".codex-plugin/plugin.json"
    if codex.exists():
        paths.append(codex)
    for path in paths:
        document = json.loads(path.read_text())
        document["version"] = version
        path.write_text(json.dumps(document, indent=2) + "\n")
```

- [ ] **Step 5: Run release tests and JSON validation**

Run: `python3 -m unittest tests.test_bump_version -v && python3 -m json.tool rhize-tasks/.claude-plugin/plugin.json >/dev/null && python3 -m json.tool rhize-tasks/.codex-plugin/plugin.json >/dev/null`

Expected: all pass.

- [ ] **Step 6: Commit the foundation**

```bash
git add docs/superpowers rhize-tasks/.claude-plugin rhize-tasks/.codex-plugin rhize-tasks/package.json rhize-tasks/setup scripts/bump_version.py tests/test_bump_version.py rhize-ops/commands/bump-version.md
git commit -m "feat(tasks): establish dual-host plugin foundation"
```

### Task 2: Schemas, Domain Contracts, and Strict Delegation Parser

**Files:**
- Create: `rhize-tasks/schemas/profile.schema.json`
- Create: `rhize-tasks/schemas/task.schema.json`
- Create: `rhize-tasks/schemas/today-view.schema.json`
- Create: `rhize-tasks/schemas/operation.schema.json`
- Create: `rhize-tasks/schemas/delegation-v1.schema.json`
- Create: `rhize-tasks/service/src/domain.mjs`
- Create: `rhize-tasks/service/src/connectors/delegation-parser.mjs`
- Create: `rhize-tasks/tests/unit/domain.test.mjs`
- Create: `rhize-tasks/tests/connectors/delegation-parser.test.mjs`

**Interfaces:**
- Consumes: normalized source snapshots and Slack reply text.
- Produces: `validateProfile(value)`, `assertTask(value)`, `operationKey(planRevision, kind, targetId, payload)`, and `parseDelegation({workspaceId, channelId, senderId, text}, allowlist)`.

- [ ] **Step 1: Write schema and parser contract tests**

```javascript
test('accepts one exact v1 task reply', () => {
  const parsed = parseDelegation({
    workspaceId: 'T1', channelId: 'C1', senderId: 'B1',
    text: '*Task:* Audit paid search\n*Due:* 2026-08-17\n*Priority:* high\n*Jira:* needs_jira\n\nrhize-delegation:v1:550e8400-e29b-41d4-a716-446655440000'
  }, {workspaceId: 'T1', channelId: 'C1', senderIds: ['B1']});
  assert.equal(parsed.delegationId, '550e8400-e29b-41d4-a716-446655440000');
  assert.equal(parsed.state, 'needs_jira');
});

for (const mutation of [wrongChannel, wrongSender, duplicateMarker, nonFinalMarker, invalidUuid, multilineTitle, invalidPriority]) {
  test(`rejects ${mutation.name}`, () => assert.throws(() => parseDelegation(mutation(message), allowlist)));
}
```

- [ ] **Step 2: Run tests and confirm imports fail**

Run: `node --test rhize-tasks/tests/unit/domain.test.mjs rhize-tasks/tests/connectors/delegation-parser.test.mjs`

Expected: failure because domain/parser modules do not exist.

- [ ] **Step 3: Define closed enums and stable identifiers**

```javascript
export const LANES = Object.freeze(['owned', 'opportunity', 'provisional']);
export const APPROVAL = Object.freeze(['required', 'approved', 'applied', 'rejected']);
export const CONFIDENCE = Object.freeze(['high', 'medium', 'low']);
export function operationKey(revision, kind, targetId, payload) {
  return createHash('sha256').update(stableJson({revision, kind, targetId, payload})).digest('hex');
}
```

Implement strict object validators that reject unknown properties, invalid enum values, non-ISO dates, unsafe URLs, negative durations, and unsupported schema versions. JSON Schema files mirror the runtime validation shapes.

- [ ] **Step 4: Implement the anchored delegation grammar**

```javascript
const MARKER = /^rhize-delegation:v1:([0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})$/;
const FIELD = /^\*(Task|Due|Priority|Jira):\* (.+)$/;
```

Require exactly four anchored fields at the top, a single-line title, ISO date, closed priority, Jira URL/key or `needs_jira`, exactly one marker as the final nonblank line, and exact workspace/channel/sender allowlists. Return an ingestion key built from workspace, channel, and delegation ID.

- [ ] **Step 5: Run the focused contract suite**

Run: `node --test rhize-tasks/tests/unit/domain.test.mjs rhize-tasks/tests/connectors/delegation-parser.test.mjs`

Expected: all pass, including idempotent duplicate identity and root-summary rejection.

- [ ] **Step 6: Commit contracts**

```bash
git add rhize-tasks/schemas rhize-tasks/service/src/domain.mjs rhize-tasks/service/src/connectors/delegation-parser.mjs rhize-tasks/tests
git commit -m "feat(tasks): define planning and delegation contracts"
```

### Task 3: Pure Planning Engine

**Files:**
- Create: `rhize-tasks/service/src/planner/eligibility.mjs`
- Create: `rhize-tasks/service/src/planner/priority.mjs`
- Create: `rhize-tasks/service/src/planner/estimates.mjs`
- Create: `rhize-tasks/service/src/planner/intervals.mjs`
- Create: `rhize-tasks/service/src/planner/planning.mjs`
- Create: `rhize-tasks/service/src/planner/carryover.mjs`
- Create: `rhize-tasks/tests/unit/planner.test.mjs`
- Create: `rhize-tasks/tests/invariants/planning-invariants.test.mjs`

**Interfaces:**
- Consumes: `ProfileV1`, normalized `TaskV1[]`, protected `Interval[]`, historical actuals, and an ISO planning date.
- Produces: `classifyTask(task, profile)`, `estimateTask(task, history, profile)`, `rankTasks(tasks, profile, now)`, `planDay(input) -> PlanDraft`, and `nextCarryover(task, answer?)`.

- [ ] **Step 1: Encode required examples and invariants as failing tests**

```javascript
test('owned deadline risk precedes an urgent opportunity', () => {
  const ranked = rankTasks([urgentOpportunity, dueOwned], profile, now);
  assert.equal(ranked[0].task.id, dueOwned.id);
  assert.equal(ranked[0].lane, 'owned');
});

test('preserves buffer and protected intervals', () => {
  const plan = planDay(fixture);
  assert.ok(plan.usedMinutes <= plan.availableMinutes * 0.8);
  assert.ok(plan.blocks.every(block => fixture.protected.every(interval => !overlaps(block, interval))));
});
```

- [ ] **Step 2: Run tests and confirm planner imports fail**

Run: `node --test rhize-tasks/tests/unit/planner.test.mjs rhize-tasks/tests/invariants/planning-invariants.test.mjs`

- [ ] **Step 3: Implement lane eligibility and explainable ranking**

```javascript
export function classifyTask(task, profile) {
  if (!profile.jira.projects.includes(task.projectKey) || task.terminal || profile.jira.excludedIssueTypes.includes(task.issueType)) return null;
  if (task.assigneeAccountId === profile.jira.accountId) return {lane: 'owned', schedulable: true};
  if (!task.assigneeAccountId && opportunityEligible(task, profile)) return {lane: 'opportunity', schedulable: false};
  return null;
}
```

Ranking returns ordered factor objects rather than a hidden scalar. Owned tasks always precede opportunities unless an opportunity has already been approved and assigned in Jira.

- [ ] **Step 4: Implement estimate hierarchy and confidence gates**

`estimateTask` chooses Jira remaining, explicit local, similar-history median, then deterministic scope inference. It returns `{minutes, source, confidence, rationale, requiresApproval}` and never overwrites source estimates.

- [ ] **Step 5: Implement interval subtraction, splitting, context grouping, freeze windows, and buffer**

```javascript
export function planDay({tasks, protectedIntervals, profile, now, planRevision}) {
  const windows = subtractIntervals(profile.workingIntervals, protectedIntervals);
  const capacity = Math.floor(totalMinutes(windows) * (1 - profile.capacity.bufferPercent / 100));
  return placeRankedTasks({tasks: rankTasks(tasks, profile, now), windows, capacity, profile, planRevision});
}
```

Low-confidence, opportunity, provisional, blocked, manually locked, and freeze-window items cannot be placed automatically.

- [ ] **Step 6: Implement carryover escalation**

First miss returns `reschedule_once`; second returns `needs_diagnosis`; third and later returns `decision_required` with split/delegate/defer/renegotiate choices.

- [ ] **Step 7: Run unit and invariant tests with randomized fixtures**

Run: `node --test rhize-tasks/tests/unit/planner.test.mjs rhize-tasks/tests/invariants/planning-invariants.test.mjs`

Expected: no overlap, outside mutation, silent claim, provisional scheduling, capacity overflow, or manual-lock loss across at least 250 seeded cases.

- [ ] **Step 8: Commit the planning core**

```bash
git add rhize-tasks/service/src/planner rhize-tasks/tests/unit/planner.test.mjs rhize-tasks/tests/invariants
git commit -m "feat(tasks): add explainable bounded planning engine"
```

### Task 4: SQLite State, Audit, and Operation Reconciliation

**Files:**
- Create: `rhize-tasks/service/src/storage/paths.mjs`
- Create: `rhize-tasks/service/src/storage/database.mjs`
- Create: `rhize-tasks/service/src/storage/migrations/001-initial.sql`
- Create: `rhize-tasks/service/src/reconciliation/operations.mjs`
- Create: `rhize-tasks/service/src/reconciliation/drift.mjs`
- Create: `rhize-tasks/tests/unit/storage.test.mjs`
- Create: `rhize-tasks/tests/failure-injection/operations.test.mjs`

**Interfaces:**
- Consumes: validated profiles, tasks, plans, source mappings, and proposed operations.
- Produces: `openDatabase(path)`, `taskRepository(db)`, `planRepository(db)`, `operationRepository(db)`, `previewOperations(plan, snapshot)`, and `applyApprovedOperations(context, operations)`.

- [ ] **Step 1: Write migration/idempotency/partial-failure tests**

```javascript
test('reopening applies each migration once', () => {
  openDatabase(file).close();
  const db = openDatabase(file);
  assert.deepEqual(db.prepare('select version from schema_migrations').all(), [{version: 1}]);
});

test('ambiguous timeout is not retried', async () => {
  const result = await applyApprovedOperations(contextWithTimeoutAfterWrite, [operation]);
  assert.equal(result[0].state, 'reconciliation_required');
  assert.equal(contextWithTimeoutAfterWrite.connector.calls, 1);
});
```

- [ ] **Step 2: Run tests and confirm missing modules**

Run: `node --test rhize-tasks/tests/unit/storage.test.mjs rhize-tasks/tests/failure-injection/operations.test.mjs`

- [ ] **Step 3: Add the versioned SQLite schema**

Tables: `preferences`, `tasks`, `task_sources`, `plans`, `plan_blocks`, `operations`, `approvals`, `audit_log`, `routine_runs`, and `schema_migrations`. Foreign keys are enabled. Operation keys and source external IDs are unique. JSON columns are validated before writes.

- [ ] **Step 4: Implement deterministic preview/apply behavior**

```javascript
export async function applyApprovedOperations({repository, connectors, currentRevision}, operations) {
  for (const operation of operations) {
    assertRevision(operation.planRevision, currentRevision);
    if (operation.approval !== 'approved') continue;
    if (repository.wasApplied(operation.idempotencyKey)) continue;
    await applyOneWithAudit({repository, connectors, operation});
  }
}
```

Safe retries require connector-proven idempotence. Ambiguous outcomes move to `reconciliation_required`. Manual external revision drift moves to `manual_lock` and produces a proposal instead of an overwrite.

- [ ] **Step 5: Run storage and failure tests**

Run: `node --test rhize-tasks/tests/unit/storage.test.mjs rhize-tasks/tests/failure-injection/operations.test.mjs`

Expected: migrations, revision preconditions, audit entries, duplicate suppression, partial success, ambiguous failure, and drift tests pass.

- [ ] **Step 6: Commit state and reconciliation**

```bash
git add rhize-tasks/service/src/storage rhize-tasks/service/src/reconciliation rhize-tasks/tests
git commit -m "feat(tasks): persist plans and reconcile idempotent operations"
```

### Task 5: Keychain and External Connector Contracts

**Files:**
- Create: `rhize-tasks/service/src/connectors/keychain.mjs`
- Create: `rhize-tasks/service/src/connectors/jira.mjs`
- Create: `rhize-tasks/service/src/connectors/google-calendar.mjs`
- Create: `rhize-tasks/service/src/connectors/slack.mjs`
- Create: `rhize-tasks/service/src/connectors/reminders.mjs`
- Create: `rhize-tasks/service/src/connectors/http.mjs`
- Create: `rhize-tasks/tests/connectors/*.test.mjs`
- Create: `rhize-tasks/tests/fixtures/connectors/*.json`

**Interfaces:**
- Consumes: `fetch`/process runner injection, Keychain service/account names, approved source IDs, and normalized operations.
- Produces: connector methods `health`, `discover`, `readSnapshot`, `applyOperation`, and `findByExternalId` with normalized errors `{kind, retryable, ambiguous, status}`.

- [ ] **Step 1: Write hermetic connector contract tests with fake transports**

```javascript
test('Jira discovery paginates and filters active projects', async () => {
  const jira = createJiraConnector({transport: fixtureTransport('jira-projects')});
  const projects = await jira.discover();
  assert.deepEqual(projects.map(p => p.key), ['RHIZE', 'CLIENT']);
});

test('Slack reads only configured channel and replies', async () => {
  const slack = createSlackConnector({transport, workspaceId: 'T1', channelId: 'C1', senderIds: ['B1']});
  assert.deepEqual((await slack.readSnapshot()).map(x => x.delegationId), [validId]);
  assert.equal(transport.writeCalls, 0);
});
```

- [ ] **Step 2: Run connector tests and confirm missing factories**

Run: `node --test rhize-tasks/tests/connectors/*.test.mjs`

- [ ] **Step 3: Implement Keychain retrieval without shell interpolation**

Use `spawnFile`-style argument arrays for `/usr/bin/security`. Service names are `media.rhize.tasks.api`, `.jira`, `.google`, and `.slack`; account names come from the saved profile. Never echo values and redact child-process errors.

- [ ] **Step 4: Implement Jira and Calendar adapters**

Jira discovers accessible projects, issue types, priorities, transitions, and Tom's account; reads allowlisted non-terminal issues with pagination; assigns/comments/transitions only from approved operations. Calendar refreshes OAuth tokens on demand, reads selected calendars, and writes only to the selected Rhize Focus calendar using stable extended properties.

- [ ] **Step 5: Implement read-only Slack and Reminders process adapters**

Slack requests only configured channel history/replies, filters exact sender identity, and passes replies through `parseDelegation`. The Reminders adapter invokes the helper with JSON on stdin and parses JSON stdout; allowed commands are `authorize`, `lists`, `snapshot`, `upsert`, `complete`, and `delete`, with write commands restricted to the configured Rhize Tasks list ID.

- [ ] **Step 6: Run all connector tests**

Run: `node --test rhize-tasks/tests/connectors/*.test.mjs`

Expected: pagination, token refresh, scope restriction, revocation, redaction, timeout classification, and write-boundary tests pass with no network or real Keychain calls.

- [ ] **Step 7: Commit connectors**

```bash
git add rhize-tasks/service/src/connectors rhize-tasks/tests/connectors rhize-tasks/tests/fixtures/connectors
git commit -m "feat(tasks): add scoped productivity connectors"
```

### Task 6: Swift EventKit Helper and macOS Installer

**Files:**
- Create: `rhize-tasks/native/reminders-helper/Package.swift`
- Create: `rhize-tasks/native/reminders-helper/Sources/RhizeRemindersHelper/main.swift`
- Create: `rhize-tasks/native/reminders-helper/Sources/RhizeRemindersHelper/EventKitStore.swift`
- Create: `rhize-tasks/native/reminders-helper/Resources/Info.plist`
- Create: `rhize-tasks/native/reminders-helper/Tests/RhizeRemindersHelperTests/EventKitStoreTests.swift`
- Create: `rhize-tasks/installer/install.mjs`
- Create: `rhize-tasks/installer/uninstall.mjs`
- Create: `rhize-tasks/installer/media.rhize.tasks.plist.template`
- Create: `rhize-tasks/tests/connectors/reminders-process.test.mjs`

**Interfaces:**
- Consumes: newline-delimited JSON requests on stdin and an injected EventKit store for tests.
- Produces: newline-delimited JSON responses, a stable `media.rhize.tasks.reminders-helper` bundle identity, and installer commands `install`, `uninstall --retain-data|--delete-data`.

- [ ] **Step 1: Write Swift permission and list-boundary tests**

```swift
func testRejectsWriteOutsideRhizeTasksList() async throws {
    let store = EventKitStore(eventStore: FakeEventStore(), allowedListID: "rhize")
    await XCTAssertThrowsErrorAsync(try await store.upsert(request(listID: "personal")))
}
```

- [ ] **Step 2: Run Swift tests and confirm target is absent**

Run: `swift test --package-path rhize-tasks/native/reminders-helper`

- [ ] **Step 3: Implement authorization, snapshot, and restricted mutation**

Use `EKEventStore.requestFullAccessToReminders()`. Create/adopt `Rhize Tasks` only through an approved setup request. Stable mapping uses a namespaced URL/notes marker; queries never return outside titles when redaction is enabled.

- [ ] **Step 4: Build a stable local app bundle**

The installer builds release Swift, creates `RhizeRemindersHelper.app` with `CFBundleIdentifier=media.rhize.tasks.reminders-helper` and `NSRemindersUsageDescription`, then ad-hoc signs it. It validates Node 22+, macOS, Keychain, writable application-support path, loopback port availability, and launchctl before installing.

- [ ] **Step 5: Add launchd install/uninstall and reversible access probe**

The plist invokes `rhize-tasks routine catch-up`, sets no secrets, and uses explicit paths. Install bootstraps one user agent. Uninstall boots it out, removes runtime files, and requires an explicit data/item retention choice. The sample reminder create/delete check runs only from an approved wizard operation.

- [ ] **Step 6: Run Swift and process-contract tests**

Run: `swift test --package-path rhize-tasks/native/reminders-helper && node --test rhize-tasks/tests/connectors/reminders-process.test.mjs`

Expected: permission denial, restricted list, stable IDs, malformed input, timeout, and reversible probe cases pass.

- [ ] **Step 7: Commit native integration**

```bash
git add rhize-tasks/native rhize-tasks/installer rhize-tasks/tests/connectors/reminders-process.test.mjs
git commit -m "feat(tasks): bridge Reminders and install bounded routines"
```

### Task 7: Authenticated Local API, Routines, and Today View

**Files:**
- Create: `rhize-tasks/service/src/api/server.mjs`
- Create: `rhize-tasks/service/src/api/routes.mjs`
- Create: `rhize-tasks/service/src/api/auth.mjs`
- Create: `rhize-tasks/service/src/scheduler/bounded-routines.mjs`
- Create: `rhize-tasks/service/src/scheduler/single-instance.mjs`
- Create: `rhize-tasks/service/src/scheduler/catch-up.mjs`
- Create: `rhize-tasks/service/src/views/today-view.mjs`
- Create: `rhize-tasks/service/bin/rhize-tasks.mjs`
- Create: `rhize-tasks/tests/e2e/local-service.test.mjs`
- Create: `rhize-tasks/tests/failure-injection/routines.test.mjs`

**Interfaces:**
- Consumes: connector registry, repositories, planner, approved operations, and Keychain API token.
- Produces: `createServer(context)`, `/v1/setup/*`, `/v1/today`, `/v1/plans/preview`, `/v1/plans/:revision/approve`, `/v1/operations/:id/approve`, `/v1/opportunities/*`, `/v1/reconcile`, `/v1/preferences`, `/v1/pause`, `/v1/audit`, and `/v1/doctor`.

- [ ] **Step 1: Write loopback auth, setup gate, and routine tests**

```javascript
test('rejects non-loopback bind and missing bearer token', async () => {
  assert.throws(() => createServer({...context, host: '0.0.0.0'}));
  assert.equal((await request('/v1/today')).status, 401);
});

test('activation requires saved preferences and first approved plan', async () => {
  assert.equal(await context.activation.canActivate(), false);
  await savePreferences(); await approveFirstPlan();
  assert.equal(await context.activation.canActivate(), true);
});
```

- [ ] **Step 2: Run E2E tests and confirm API modules are absent**

Run: `node --test rhize-tasks/tests/e2e/local-service.test.mjs rhize-tasks/tests/failure-injection/routines.test.mjs`

- [ ] **Step 3: Implement bearer-authenticated loopback routing and strict JSON bodies**

`/health` returns only version/status. Every v1 route checks bearer token, content type, size ceiling, known properties, profile schema version, and plan revision. State-changing routes create preview/approval audit entries before connector application.

- [ ] **Step 4: Implement bounded routine orchestration**

```javascript
export async function runRoutine(kind, context, now = new Date()) {
  return withSingleInstance(context.lockPath, async () => {
    const due = await context.routineState.evaluate(kind, now);
    if (!due.shouldRun) return {state: 'not_due'};
    const snapshot = await context.sync.readAll();
    return context.plans.reconcileAndPlan({kind: due.catchUp ? 'catch_up' : kind, snapshot, now});
  });
}
```

Catch-up produces one evaluation regardless of missed count. Midday protects active/completed/manual/freeze blocks. Offline sources mark freshness and pause only affected writes.

- [ ] **Step 5: Build the sanitized `TodayView` projection**

The projection carries `schemaVersion`, `planRevision`, timeline, current/next block, capacity, buffer, carryovers, approvals, opportunities, estimate warnings, and connector freshness. Outside commitments expose opaque IDs, busy intervals, and optional user-approved labels only.

- [ ] **Step 6: Add CLI commands**

`rhize-tasks.mjs` implements `serve`, `routine morning|midday|evening|catch-up`, `doctor --json`, `artifact --output`, `install`, and `uninstall`. It exits nonzero with redacted structured errors and never prints secrets.

- [ ] **Step 7: Run E2E and failure-injection tests**

Run: `node --test rhize-tasks/tests/e2e/local-service.test.mjs rhize-tasks/tests/failure-injection/routines.test.mjs`

Expected: auth, activation, revision conflict, duplicate routine, sleep catch-up, partial connector outage, pause, and redaction cases pass.

- [ ] **Step 8: Commit service orchestration**

```bash
git add rhize-tasks/service rhize-tasks/tests/e2e rhize-tasks/tests/failure-injection
git commit -m "feat(tasks): serve one bounded local planning authority"
```

### Task 8: Setup Wizard, Dashboard, Artifact, and Host Skills

**Files:**
- Create: `rhize-tasks/dashboard/index.html`
- Create: `rhize-tasks/dashboard/app.js`
- Create: `rhize-tasks/dashboard/styles.css`
- Create: `rhize-tasks/dashboard/artifact-template.html`
- Create: `rhize-tasks/skills/rhize-tasks-setup/SKILL.md`
- Create: `rhize-tasks/skills/plan-my-day/SKILL.md`
- Create: `rhize-tasks/skills/review-task-opportunities/SKILL.md`
- Create: `rhize-tasks/skills/reconcile-rhize-tasks/SKILL.md`
- Create: `rhize-tasks/skills/manage-task-preferences/SKILL.md`
- Create: `rhize-tasks/skills/rhize-tasks-doctor/SKILL.md`
- Create: `rhize-tasks/commands/{setup,today,review-opportunities,reconcile,preferences,doctor}.md`
- Create: `rhize-tasks/tests/e2e/dashboard.test.mjs`

**Interfaces:**
- Consumes: the v1 API and sanitized TodayView.
- Produces: resumable seven-stage setup UI, today-first dashboard, read-only artifact export, six shared skills, and six Claude command wrappers.

- [ ] **Step 1: Write dashboard accessibility, setup-state, and artifact immutability tests**

```javascript
test('artifact contains revision and no mutation controls', () => {
  const html = renderArtifact(todayView);
  assert.match(html, /Plan revision 42/);
  assert.doesNotMatch(html, /approve|assign|transition|fetch\(/i);
});
```

Static tests require one H1, labeled navigation, keyboard focus, status text not encoded only by color, escaped source text, seven resumable setup stages, and a pause control.

- [ ] **Step 2: Run dashboard tests and confirm assets are absent**

Run: `node --test rhize-tasks/tests/e2e/dashboard.test.mjs`

- [ ] **Step 3: Implement the seven-stage setup flow**

The browser sends secrets directly to a local Keychain route whose response never echoes values. Each stage saves completion separately. Project/calendar/list discovery is explicit; connector scope expansion and the reversible sample write display exact previews and require approval.

- [ ] **Step 4: Implement the today-first command center**

Render chronological blocks, current/next work, redacted commitments, capacity/buffer, carryovers, approvals, opportunity rationales/impact, estimate warnings, connector freshness, and paused/degraded state. Approval buttons post the operation ID plus the displayed plan revision and refresh after success/conflict.

- [ ] **Step 5: Implement read-only Artifact export**

Embed escaped TodayView JSON into a standalone local HTML snapshot with no network calls, forms, or mutation code. It names the revision and directs actions to `/rhize-tasks:today` or the authenticated dashboard.

- [ ] **Step 6: Generate and validate six additive shared skills**

Each skill is created with the repository skill initializer, contains concise frontmatter, invokes the local CLI/API rather than reimplementing Jira/Calendar behavior, treats source content as untrusted, and has `metadata.rhize` tags from `catalog/tags.json`. Each skill gets `agents/openai.yaml` only where the Codex interface benefits from an explicit prompt.

- [ ] **Step 7: Add Claude wrappers with complete frontmatter**

Commands delegate to the corresponding shared skill and preserve the same approval boundary. They never ask for secrets in chat.

- [ ] **Step 8: Run dashboard and skill validation**

Run: `node --test rhize-tasks/tests/e2e/dashboard.test.mjs && claude plugin validate rhize-tasks`

Also run `quick_validate.py` from the system skill-creator against every new skill directory.

- [ ] **Step 9: Commit the user experience**

```bash
git add rhize-tasks/dashboard rhize-tasks/skills rhize-tasks/commands rhize-tasks/tests/e2e/dashboard.test.mjs
git commit -m "feat(tasks): add setup and today-first command center"
```

### Task 9: Delegation Producer Compatibility

**Files:**
- Modify: `rhize-ops/skills/delegate-to-teammate/SKILL.md`
- Create: `rhize-ops/skills/delegate-to-teammate/references/rhize-delegation-v1.md`
- Create: `tests/rhize-ops/test_delegation_contract.py`
- Modify: `rhize-ops/README.md`
- Modify: `rhize-ops/GUIDE.md`

**Interfaces:**
- Consumes: one approved delegation task before Jira/Slack side effects.
- Produces: one stable lowercase UUIDv4, matching Jira-description and per-task Slack-reply footers, and parser-stable Task/Due/Priority/Jira fields.

- [ ] **Step 1: Write producer conformance tests**

```python
def test_contract_has_jira_and_no_jira_templates():
    skill = SKILL.read_text()
    assert "*Jira:* needs_jira" in skill
    assert skill.count("rhize-delegation:v1:<delegation-id>") >= 2

def test_each_task_gets_one_stable_id_before_side_effects():
    skill = SKILL.read_text()
    assert skill.index("Generate delegation IDs") < skill.index("Create Jira")
    assert "never regenerate" in skill.lower()
```

- [ ] **Step 2: Run the test and confirm the old contract fails**

Run: `python3 tests/rhize-ops/test_delegation_contract.py`

- [ ] **Step 3: Add UUID generation and retry rules before side effects**

For each task, generate `uuidgen | tr '[:upper:]' '[:lower:]'`, validate UUIDv4, keep it in memory for the whole operation, and never regenerate after an ambiguous Jira or Slack response.

- [ ] **Step 4: Update Jira and Slack formats**

Append one exact plain final nonblank marker to the Jira description. Put anchored Task, Due, Priority, and Jira lines at the top of that task's Slack thread reply, followed by human detail and the same exact final marker. Jira failure uses `needs_jira`. The shared root summary stays unmarked.

- [ ] **Step 5: Document grammar and trust boundary**

The reference defines valid/invalid examples, per-task cardinality, sender semantics, retry behavior, uniqueness key, and exact-ID merge. README/GUIDE explain how Rhize Tasks uses the fallback and why arbitrary Slack text is ignored.

- [ ] **Step 6: Run producer and consumer contract tests**

Run: `python3 tests/rhize-ops/test_delegation_contract.py && node --test rhize-tasks/tests/connectors/delegation-parser.test.mjs`

- [ ] **Step 7: Commit delegation compatibility**

```bash
git add rhize-ops/skills/delegate-to-teammate rhize-ops/README.md rhize-ops/GUIDE.md tests/rhize-ops
git commit -m "feat(ops): emit stable Rhize delegation contracts"
```

### Task 10: Documentation, Integration Gate, Versioning, and Release

**Files:**
- Create: `rhize-tasks/README.md`
- Create: `rhize-tasks/GUIDE.md`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `.claude-plugin/marketplace.json`
- Create: `docs/release/rhize-tasks-pr-body.md`
- Modify: `catalog/tags.json` only if new closed stack tags pass curation review
- Regenerate: `generated/skill-map.static.json`
- Regenerate: `generated/skill-map.indexes.json`
- Regenerate: `generated/SKILL-CATALOG.md`
- Modify: `docs/skill-map.md` only through the renderer's managed sections

**Interfaces:**
- Consumes: the complete tested plugin, dual-manifest version tool, delegation producer, and repository renderers.
- Produces: installable marketplace releases `rhize-tasks@0.1.0` and `rhize-ops@0.9.0`, one synchronized marketplace version, complete technical/user documentation, and release evidence.

- [ ] **Step 1: Write technical and user documentation before release metadata**

README covers architecture, prerequisites, Node/macOS floors, install, direct connector authorization, Keychain services, permissions, local paths, dashboard/API boundaries, launchd, commands/skills, validation, pause, uninstall, and data retention. GUIDE walks Tom through setup, first dry-run approval, daily use, opportunities, carryover, reconciliation, privacy, recovery, and example prompts from both Claude and Codex.

- [ ] **Step 2: Register the plugin at `0.0.0` and rebuild managed artifacts**

Add the marketplace entry, then run:

```bash
python3 scripts/build_skill_map.py
python3 scripts/render_skill_map_docs.py
python3 scripts/validate_skill_map.py --check-stale
```

Expected: seven plugins and every new skill exactly once; generated outputs are deterministic on a second build.

- [ ] **Step 3: Run the complete plugin gate**

```bash
node --test rhize-tasks/tests/**/*.test.mjs
swift test --package-path rhize-tasks/native/reminders-helper
python3 tests/rhize-ops/test_delegation_contract.py
python3 -m unittest tests.test_bump_version -v
claude plugin validate rhize-tasks
python3 -m json.tool .claude-plugin/marketplace.json >/dev/null
python3 scripts/validate_skill_map.py --check-stale
python3 tests/skill-map/test_build.py
git diff --check
```

Expected: all pass. Live connector writes remain disabled.

- [ ] **Step 4: Run disposable local acceptance with fake connectors**

Start the service with a temporary application-support directory and fixture connectors. Complete all seven setup stages, approve the first plan, create one fake reminder/block, simulate movement/completion/carryover/Jira reconciliation, exercise pause/restart/catch-up/revocation/uninstall, and assert outside fixture records are byte-identical.

- [ ] **Step 5: Bump both plugins atomically**

Run: `python3 scripts/bump_version.py --auto --since origin/main --yes`

Expected: `rhize-tasks` becomes `0.1.0`, `rhize-ops` becomes `0.9.0`, both dual manifests match where present, and marketplace top-level version changes once.

- [ ] **Step 6: Re-run generated and release checks after versioning**

Run: `python3 scripts/build_skill_map.py && python3 scripts/render_skill_map_docs.py && python3 scripts/validate_skill_map.py --check-stale && python3 scripts/bump_version.py --check --since origin/main && git diff --check`

- [ ] **Step 7: Perform a cold independent review**

Read `git diff origin/main...HEAD` as a skeptical reviewer. Verify every spec success criterion maps to code/tests/docs; no secret, real ID, private event title, unsupported auto-write, unknown stack tag, unfinished implementation marker, generated drift, protected workflow edit, or unrelated change exists. Re-run the focused gate after each correction. Record the scope, safety boundaries, validation output, remaining Tom-Mac acceptance gate, and rollback path in `docs/release/rhize-tasks-pr-body.md`.

- [ ] **Step 8: Commit release state**

```bash
git add rhize-tasks rhize-ops tests scripts docs README.md CHANGELOG.md .claude-plugin catalog generated
git commit -m "release(tasks): ship local-first unified planning plugin"
```

- [ ] **Step 9: Push and merge under the repository auto-push policy**

```bash
git push -u origin feat/rhize-tasks-plugin
gh pr create --base main --head feat/rhize-tasks-plugin --title "release(tasks): local-first unified planning" --body-file docs/release/rhize-tasks-pr-body.md
gh pr checks <pr-number> --watch
gh pr merge <pr-number> --squash --delete-branch
git -C /Users/jamesdeola/dev-local/RHIZE/rhize-plugins pull --ff-only
```

The PR body records validation evidence, the no-live-write boundary, remaining Tom-Mac acceptance gate, and rollback/uninstall behavior. Merge only after checks and the cold review pass.

## Parallel Execution Map

After Task 2 freezes interfaces, the following lanes can run concurrently in isolated file ownership:

| Lane | Tasks | Exclusive write surface | Merge dependency |
| --- | --- | --- | --- |
| Planning | Task 3 | `service/src/planner`, planner tests | Task 2 |
| State/API | Tasks 4 then 7 | storage, reconciliation, API, scheduler, views, CLI | Task 2; Task 7 also consumes Tasks 3-6 |
| Connectors/native | Tasks 5 then 6 | connectors, native helper, installer | Task 2 |
| Experience | Task 8 | dashboard, skills, commands | Task 2 API contracts; final integration after Task 7 |
| Delegation | Task 9 | `rhize-ops` contract/docs/tests | Task 2 parser contract |

Task 10 is sequential integration and release. Agents must not edit marketplace, root catalog, changelog, generated skill-map outputs, or shared version files until the Task 10 integration lane owns them.
