# Task 8 report — Setup, today-first dashboard, artifact, and host skills

## Scope and boundaries

- Implemented only the Task 8 dashboard, artifact renderer/template, six shared skills, six Claude wrappers, and their E2E/static tests.
- Did not edit marketplace metadata, the root README, the root CHANGELOG, the catalog, generated files, or protected workflows.
- Task 7 Fix1 was allowed to land first. Task 8 then made only the approved narrow integration change in the CLI and its existing artifact test: `artifact --output` now delegates to the standalone HTML writer instead of serializing raw JSON.
- After Task 7 Fix2 (`7f16e08`), the final plan-preview client was narrowed to `{planRevision, planningDate?}`. The browser no longer supplies base/source revisions or any proposed connector operations.
- The dashboard is dependency-free HTML/CSS/ES modules. It calls only relative loopback routes with same-origin credentials. Normal access uses the CLI-issued single-use link and HttpOnly session cookie; the optional bearer troubleshooting fallback exists only in page memory. Browser persistence APIs and URL credentials are not used.

## TDD evidence

### Initial dashboard RED

`node --test rhize-tasks/tests/e2e/dashboard.test.mjs` initially failed with `ERR_MODULE_NOT_FOUND` for `dashboard/artifact.mjs`. The missing dashboard and artifact assets were then implemented.

### Skills/wrappers RED

After the six skill directories were initialized, the host-boundary test failed with `ENOENT` for the absent Claude command wrapper. Finished skill instructions and all six wrappers were then added.

### Artifact-detail RED

The artifact test was tightened to require current/next work and connector freshness; it failed because the first renderer showed only capacity, timeline, decisions, and service state. The read-only renderer was extended with those today-first details.

### Artifact-writer RED

The private export test initially failed because `writeArtifactFile` did not exist. The renderer gained an atomic same-directory writer that fsyncs a mode-0600 temporary file before replacement, and the production CLI was switched to that tested path.

### Final-preview contract RED

After Task 7 Fix2, dashboard tests were extended to reject the former `baseRevision`, `sourceRevision`, and `proposedOperations` fields and require the lifecycle-owned `{planRevision, planningDate}` request plus rendered `operations` and `zeroWorkReason`. The test failed against the old browser-authored body, then passed after the dashboard adopted the server-derived preview.

## Implementation

### Seven-stage setup dashboard

The setup UI has exactly seven independently saved stages:

1. Safety and control
2. Identity and authorization
3. Jira discovery and exact scope
4. Calendar/Reminders discovery and reversible sample
5. Work style
6. Routine/replanning preferences
7. Dry run and first plan approval

Credentials are sent only to the authenticated local Keychain route and cleared from the page before the request, including on failure. Discovery is explicit. Scope expansion and the reversible Reminders/Calendar probe are server-owned exact previews that require approval; the browser does not author connector operations. The displayed plan revision is attached to state-changing actions, and an HTTP 409 causes the today view to refresh before another decision.

The wizard represents every ProfileV1 preference in practical fields: identity and time zone; Jira account, project scope, issue types, project importance, urgency threshold, suggestion limit, and competencies; Calendar awareness, focus target, and privacy; Reminders awareness durations and exact Rhize Tasks boundary; working days, hours, breaks, capacity, focus sizing, splitting, buffers, and freeze window; and all three routine times with replanning/reconciliation choices. Structured Slack fallback is limited to an explicit workspace, #tom-tasks channel ID, recognized sender IDs, and a Keychain-held token. Non-secret stage data rehydrates when setup resumes, with authoritative saved preferences taking precedence.

The today-first command center renders current/next work, chronological blocks, redacted commitments, capacity and buffer, carryovers, approval operation IDs, opportunity rationale/impact, estimate warnings, connector freshness, paused/degraded state, and a pause/resume control. Opportunity claims are explicit revision-bound user actions. External text is written with DOM `textContent`, never interpreted as markup.

The final setup preview now displays every exact server-returned operation—ID, kind, target system, target, approval status, and payload—before the approval button is enabled. It also shows the complete server-derived preview, freshness and approval metadata, and a visible `zeroWorkReason` when no eligible work can be scheduled. A zero-work plan can only be approved when the service itself declares it valid.

Accessibility features include one H1, a named primary navigation landmark, a skip link, real labels and fieldsets, keyboard-visible focus, live status text, semantic lists/definition lists, forced-color support, reduced-motion behavior, and statuses that are expressed in text rather than color alone. The interactive dashboard also has a same-origin-only Content Security Policy.

### Read-only artifact

The renderer strictly requires the core TodayView shape, escapes every displayed value and the embedded JSON, includes the plan revision, current/next work, capacity, timeline, carryovers, pending decisions, opportunities, warnings, connector freshness, and service state. The standalone HTML has a deny-by-default Content Security Policy and contains no external resources, network code, forms, buttons, or mutation controls. It routes follow-up actions to `/rhize-tasks:today` or the authenticated local dashboard.

### Shared skills and Claude wrappers

All six skill directories were created with the required system `init_skill.py` before their generated content was replaced:

- `rhize-tasks-setup`
- `plan-my-day`
- `review-task-opportunities`
- `reconcile-rhize-tasks`
- `manage-task-preferences`
- `rhize-tasks-doctor`

Each initializer invocation supplied a quoted display name, a 25–64 character short description, and a one-sentence default prompt naming its `$skill-name`. Each final skill has an `agents/openai.yaml`, concise triggering description, and `metadata.rhize` topics drawn only from `catalog/tags.json`; stacks are empty because the catalog has no accurate Jira, Calendar, Reminders, Slack, Node, or macOS stack tag.

The skills use the installed local CLI/service/dashboard rather than calling Jira, Google Calendar, Apple Reminders, or Slack directly. They treat source content as untrusted, never ask for secrets in chat, and preserve preferences, approval, stable-ID, and plan-revision boundaries. The Claude commands use the plan-specified names `setup`, `today`, `review-opportunities`, `reconcile`, `preferences`, and `doctor`, contain complete frontmatter, and delegate to the corresponding shared skill.

## Validation

- `node --test rhize-tasks/tests/e2e/dashboard.test.mjs`: 6 passed, 0 failed.
- `npm test` (outside the restricted sandbox because loopback E2E tests need `127.0.0.1`): 155 passed, 0 failed after Task 7 Fix2 alignment.
- `npm run validate`: passed.
- `claude plugin validate rhize-tasks`: passed.
- `quick_validate.py` for each of the six new skill directories: all valid.
- `node --check rhize-tasks/dashboard/app.js`: passed.
- `node --check rhize-tasks/dashboard/artifact.mjs`: passed.
- `node --check rhize-tasks/service/bin/rhize-tasks.mjs`: passed.
- `git diff --check`: passed.

## Cold-review notes

- Confirmed the command names match the approved plan rather than the longer skill directory names.
- Confirmed no CDN, third-party API endpoint, browser persistence, `innerHTML`, TODO, implementation placeholder, or sample credential remains in Task 8 assets.
- Confirmed the artifact displays only escaped values and remains operationally inert.
- Confirmed the only Task 7-owned files in the Task 8 diff are the narrow CLI artifact delegation and its corresponding E2E assertion.

## Fix Round 1 — faithful setup preference preservation

### Review findings addressed

- Replaced the flattened workday controls with ordered, day-specific working-interval and break rows. Each row has a real day/start/end label plus accessible add/remove controls. Multiple intervals on one day and different schedules across days now rehydrate and serialize without collapsing.
- Replaced the lossy competency textarea with ordered name/confidence/excluded rows. The `excluded` flag is visible, editable, and preserved with the original confidence value.
- Added a stable Calendar scope union. The Rhize Focus calendar is included exactly once alongside the chosen awareness calendars for both the setup-scope preview and the saved ProfileV1. The dashboard explains this boundary next to the fields.
- Extracted profile conversion, request construction, stage resume, credential submission, and authenticated request behavior into pure exports in the already-allowlisted `app.js`. The DOM boot is guarded with `typeof document`, so Node can test these behaviors without a browser dependency. A cold review caught and removed an interim second ES-module asset because Task 7 deliberately serves only `/`, `/app.js`, and `/styles.css`.
- Credential fields are cleared before the Keychain request and remain clear on failure. Every HTTP 401 clears the in-memory troubleshooting bearer before response parsing and marks the UI disconnected with fresh CLI-session guidance. No token is persisted.
- Corrected the reconciliation skill and Claude wrapper to resolve the installed CLI through `installation.json`/`runtimePath`, use TodayView's existing reconciliation-required operations as the review surface, request explicit approval for exact operation IDs and revision, and then call the real authenticated `POST /v1/reconcile` contract. The former invented reconciliation-preview step was removed.

### TDD and behavior evidence

The Fix Round 1 behavior tests were added before implementation. The first focused run failed with `ERR_MODULE_NOT_FOUND` for the not-yet-created pure setup model. After implementing the behavior, the suite verifies:

- exact ProfileV1 rehydrate/serialize round trips for ordered intervals, per-day breaks, and competency exclusion;
- stable focus-calendar union and exact setup connector, probe preview/apply, and server-owned plan-preview bodies;
- deterministic seven-stage resume state;
- credential clearing on a rejected request and immediate token clearing on 401;
- dependency-free import of the guarded dashboard application;
- the installed-runtime reconciliation workflow and absence of any invented preview/CLI command;
- continued standalone artifact immutability and the original static/accessibility boundaries.

### Fix Round 1 validation

- `node --test tests/e2e/dashboard.test.mjs`: 11 passed, 0 failed.
- `npm test` outside the restricted sandbox for hermetic loopback binding: 167 passed, 0 failed.
- `npm run validate`: passed.
- `claude plugin validate rhize-tasks`: passed.
- `quick_validate.py` for all six skills: all valid.
- `node --check dashboard/app.js` and `node --check dashboard/artifact.mjs`: passed.
- `git diff --check`: passed.

### Fix Round 1 scope review

Only Task 8 dashboard assets, its E2E test, the reconciliation skill/wrapper, and this ignored report were changed. No Task 7 production route, marketplace file, catalog, generated file, root README, root CHANGELOG, protected workflow, or credential file was edited.

## Final reconciliation contract — actionable TodayView workflow

- The today-first dashboard now renders a dedicated labeled reconciliation section with each exact operation ID, target system, kind, and safe reason. Every item has an individual explicit action; unhealthy connectors disable it, and browser confirmation is required before the dashboard sends `{planRevision, operationIds: [id], actor: "tom"}`. Success refreshes TodayView, revision conflicts use the existing refresh path, offline errors remain visible, and nothing retries automatically.
- The shared reconciliation skill continues to resolve the installed CLI through `installation.json` and its bounded `runtimePath`. It now reads the required TodayView `reconciliation` array, explains exact IDs/system/kind/reason, asks for approval and a nonblank actor, and submits the real `{planRevision, operationIds, actor}` body. It explicitly forbids client operation objects, broadened IDs, invented previews, and automatic retries. The Claude wrapper matches this workflow.
- Dashboard behavior tests execute the pure request helper and assert the accessible/static surface and exact skill/command contract. The Task 7 loopback E2E test additionally proves that an ID displayed by TodayView is actually resumed, preflighted, and applied through `/v1/reconcile`, while an unselected record remains untouched.

### Final validation

- `node --test tests/e2e/local-service.test.mjs tests/e2e/dashboard.test.mjs tests/unit/storage.test.mjs tests/unit/schema-contract.test.mjs` -> 30 passed, 0 failed.
- `npm test` -> 170 passed, 0 failed.
- `npm run validate` and `claude plugin validate rhize-tasks` -> passed.
- All six skills passed `quick_validate.py`; changed module syntax and `git diff --check` passed.
- Cold review confirmed DOM output remains `textContent`-only, the long-lived bearer is not added to URL/storage, confirmation is explicit, affected connector health gates the action, and no automatic reconciliation loop was introduced.
