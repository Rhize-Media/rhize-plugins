# Rhize Tasks Plugin Design Specification

**Date:** 2026-08-14
**Status:** Approved for implementation
**Product:** `rhize-tasks`
**Primary user:** Tom Cassidy
**Planning/review model:** Sol
**Implementation model:** Terra for integration-heavy work; smaller bounded slices may use a lower-cost executor

## Purpose

Rhize Tasks gives Tom one practical daily plan for Rhize and client work without replacing the tools he already trusts. Jira remains authoritative for Rhize work, Google Calendar remains authoritative for fixed time, and an Apple Reminders list named **Rhize Tasks** becomes the daily execution queue. The system sees approved outside commitments so it can protect them, but it controls only Rhize work.

The plugin is local-first on Tom's Mac and exposes the same local planning service to Claude and ChatGPT/Codex. It ships one shared today-first dashboard and a read-only Claude Artifact snapshot generated from the same plan revision.

## Goals

1. Discover every appropriate active Rhize and client Jira project during setup and let Tom confirm the allowlist.
2. Prioritize open Jira work assigned to Tom.
3. Suggest urgent unassigned work that matches Tom's competencies, including ads, marketing, GHL, and non-development-heavy Sanity work, without silently assigning it.
4. Estimate duration, fit eligible work around protected commitments, preserve configurable capacity buffer, split long work into focus sessions, and explain every ranking and estimate.
5. Carry unfinished work forward with escalating prompts instead of silently rescheduling it forever.
6. Require approval until preferences are saved and the first live-data plan is approved.
7. Use bounded replanning and prompted Jira reconciliation by default, while letting Tom choose other supported policies in setup.
8. Provide resumable setup, pause, audit, recovery, doctor, and uninstall paths.
9. Package the system as a dedicated plugin with both Claude and Codex manifests.

## Non-goals

- Moving, completing, or reprioritizing non-Rhize calendar events or reminders.
- Automatically claiming unassigned Jira work.
- Replacing Jira with Reminders.
- Hosting the dashboard or operational database in the cloud.
- Treating arbitrary Slack messages as tasks.
- Automatically scheduling Jira-less delegations.
- Requiring a separate model API key for baseline planning.

## Control boundaries

| System | Authoritative data | Allowed writes |
| --- | --- | --- |
| Jira | Rhize/client scope, assignment, priority, due dates, estimates, workflow state | Approved assignments, transitions, comments, and issue creation; activated-policy reconciliation only |
| Google Calendar | Fixed events, availability, and plugin focus blocks | Only a dedicated approved calendar, recommended name `Rhize Focus` |
| Apple Reminders | Daily execution queue and completion signal | Only a dedicated approved list named `Rhize Tasks` |
| Slack | Structured delegation fallback | Read-only, one configured channel, recognized contract messages only |
| Other calendar/reminder sources | Global capacity awareness | None |

Outside timed reminders reserve a configurable per-list protected duration. Untimed reminders inform deadline awareness but do not reserve arbitrary blocks. Outside titles are redacted by default.

## Architecture

`rhize-tasks` is a dedicated plugin because it installs a background scheduler, accesses personal productivity data, and has a different permission and release risk from `rhize-ops`.

```text
Claude skills/commands ─┐
                       ├── versioned loopback API ── local Node service ── SQLite
Codex skills/manifest ─┘                            │
                                                    ├── Jira REST
                                                    ├── Google Calendar REST
                                                    ├── Slack read-only REST
                                                    ├── Keychain
                                                    └── Swift/EventKit helper

launchd ── bounded routines ── same service
dashboard ── authenticated loopback API ── same TodayView revision
Claude Artifact ── sanitized read-only TodayView snapshot
```

The implementation uses Node.js 22+ ESM, built-in `fetch`, `node:test`, and `node:sqlite`, plus a minimal Swift/EventKit helper. Runtime npm dependencies are not required. Credentials are entered through the local setup dashboard and stored in macOS Keychain, not in agent prompts, configuration files, or globally exported shell variables.

## Local data and API contracts

The versioned SQLite store contains preferences, normalized tasks, source mappings, estimates, plans, operations, approvals, audit entries, routine state, and migrations. It never contains credential values.

Every plan has an immutable revision. Every proposed write has a deterministic idempotency key, source revision precondition, approval state, and audit record. The API rejects unknown fields and unsupported operation kinds. Loopback requests require an unguessable bearer token retrieved from Keychain.

Core lanes are:

- `owned`: allowlisted, non-terminal Jira issues assigned to Tom.
- `opportunity`: allowlisted, unassigned, above-threshold, high-fit and unblocked Jira issues.
- `provisional`: recognized Jira-less delegations in `needs_jira` state.

Only owned tasks are automatically schedulable after activation. Opportunities require explicit claim approval. Provisional items require approval plus Jira creation or linking before scheduling.

## Setup wizard

The wizard is resumable from either host and writes one shared profile.

1. **Safety:** Explain global awareness, Rhize-only control, connector read/write boundaries, audit, pause, and revocation. Force approval-required mode.
2. **Identity:** Confirm Tom's identity, timezone, and locale. Authorize Jira and Calendar, request Reminders permission, optionally authorize strict Slack fallback, validate connections, and store secrets in Keychain.
3. **Jira scope:** Discover projects and issue types. Confirm active Rhize/client allowlists, project importance, competencies, exclusions, opportunity threshold, and daily suggestion cap.
4. **Time boundaries:** Choose readable calendars and reminder lists, per-list protected reminder durations, and create or adopt `Rhize Focus` and `Rhize Tasks`. A reversible create/delete permission probe runs only after explicit approval.
5. **Work style:** Confirm days, hours, breaks, hard stops, travel, energy windows, focus-block sizes, task splitting, meeting buffers, capacity ceiling, and buffer. Recommend at least 20 percent buffer, but require Tom to confirm or change it.
6. **Routines:** Default to bounded replanning and prompted Jira reconciliation. Configure morning, midday, evening, catch-up, freeze window, and urgent interruption policy.
7. **Dry run:** Read live sources, generate a complete no-write preview, show every proposed operation, allow preference changes, then require saving preferences and approving the first plan.

Automatic policy-based scheduling is unavailable until Stage 7 completes.

## Planning rules

Owned ordering considers, in order: due-date feasibility/overdue state, Jira priority/delegator urgency, blockers/dependencies/downstream impact, configured project importance, remaining effort versus focus windows, competency fit/estimate confidence, and context grouping/task age.

Opportunity ordering combines urgency, fit, project importance, deadline/dependency risk, effort/capacity, and age. It never displaces owned work before Tom sees and approves the impact.

Estimate hierarchy:

1. Jira remaining estimate.
2. Tom's explicit saved estimate.
3. Historical actual duration for similar completed work.
4. Deterministic structured inference from scope, issue type, project, checklist, dependencies, and competencies.

Every estimate records source, confidence, rationale, and confirmation time. Low-confidence inferred estimates may appear in preview but cannot consume live calendar capacity until confirmed. Agent-assisted estimates use the same endpoint and approval rules.

The planner subtracts fixed events, protected reminders, locks, breaks, hard stops, freeze windows, and buffer before placing work. It never overlaps protected time, exceeds configured capacity, moves outside commitments, changes manual locks, claims an opportunity silently, or schedules a provisional item.

## Bounded routines and carryover

- **Morning:** refresh, reconcile, estimate new owned work, build the day, reserve buffer, and surface approvals.
- **Midday:** replan only the unfinished eligible future; preserve completed, active, manually moved, outside, and freeze-window blocks.
- **Urgent event:** explain the urgency and displaced work, then require approval before changing the current plan.
- **Evening:** prompt Jira reconciliation, record blockers/actual effort, carry work to the next safe window, and surface deadline risk.

Carryover escalates:

- First miss: move once to the nearest safe pre-deadline window and retain the estimate.
- Second miss: ask whether it is blocked, underestimated, or no longer important.
- Repeated miss: stop silent rescheduling and require split, delegate, defer, or renegotiate.

Prompted Jira reconciliation is the default. Reminder completion offers Done, Blocked/waiting, Partially complete, or Completed locally/awaiting evidence. Exact Jira transitions and comments are previewed. Automatic completion, if enabled, applies only to eligible Jira-backed reminders and never weakens always-approval operations.

## Delegation fallback contract

`delegate-to-teammate` produces one lowercase UUIDv4 per task before any side effect. It reuses that ID across retries and writes the exact final nonblank footer to both the task's Jira description and per-task Slack thread reply:

```text
rhize-delegation:v1:<uuid>
```

The per-task Slack reply begins with parser-stable fields:

```text
*Task:* <single-line title>
*Due:* YYYY-MM-DD
*Priority:* urgent|high|normal|low
*Jira:* <URL-or-key> | needs_jira
```

The shared multi-task root message has no marker. The consumer accepts a message only when workspace ID, channel ID, configured app/bot or user sender identity, anchored fields, and one final valid UUIDv4 marker all pass. It uses `(workspace_id, channel_id, delegation_id)` as the uniqueness key. Exact Jira-description ID matches merge automatically; fuzzy title/date matches only propose a merge for approval.

A valid Jira-less delegation creates an approval-required `needs_jira` record. It is never automatically scheduled. Arbitrary messages, quoted markers, malformed values, wrong senders/channels, and root summaries are ignored.

## Dashboard and host adapters

The authenticated loopback dashboard is the only interactive visual surface and the canonical approval surface. Its Today-first view shows the chronological plan, current/next focus block, redacted outside commitments, capacity/buffer risk, carryovers and reasons, pending operations, high-fit opportunities, low-confidence estimates, missing Jira information, connector freshness, and pause/degraded status.

Claude and Codex invoke the same versioned local API through thin shared skills. Claude may render a sanitized read-only Artifact snapshot with the same plan revision, timeline, capacity, carryovers, and approval summaries. Artifact actions point to a plugin command or local dashboard and cannot mutate state.

## Approval policy

Before activation, every create, update, assignment, transition, and reschedule requires approval. After preferences and the first plan are approved, the service may create/update owned-task reminders, create/update focus blocks inside policy, and perform bounded routines.

The following always require approval:

- Claiming unassigned Jira work.
- Scheduling or linking provisional delegations.
- Urgent-plan displacement.
- Low-confidence estimates.
- Ambiguous Jira transitions.
- Expanding connector scope.

Tom can pause automation or return to approval-required mode immediately.

## Reliability and privacy

- Single-instance locking and one catch-up evaluation prevent routine replay and duplicate host installs.
- Stable external IDs, plan revisions, preconditions, and idempotency keys prevent duplicate writes.
- Partial writes are recorded per operation; only proven-safe retries run automatically.
- Manual edits are authoritative and create temporary locks; reconciliation is proposed rather than overwritten.
- Offline or expired connectors pause affected writes, preserve the last plan, show freshness, and catch up once after recovery.
- Source content is untrusted data, never agent instructions.
- Logs redact secrets and default to identifiers/status rather than private titles.
- Slack is read-only and channel-restricted; connector scopes are least privilege.
- Uninstall removes the launch agent and runtime, then explicitly asks whether to retain history and plugin-created items.

## Verification and acceptance

Tests cover schemas/migrations, eligibility, ordering, estimates, interval fitting, buffer, splitting, freeze windows, carryover, reconciliation, strict delegation parsing/merge, log redaction, connector contracts, Keychain revocation, launchd catch-up/single-instance behavior, failures, and cross-host discovery.

Invariants prove no protected overlap, no outside mutation, no silent opportunity claim, no provisional auto-scheduling, idempotent repeated plans, preserved locks, and capacity compliance.

Before activation on Tom's Mac, use an approved Jira test issue plus disposable Calendar and Reminders containers. Complete setup with no production writes, approve a dry-run, apply one reminder and block, simulate manual movement/completion/carryover/reconciliation, verify outside items unchanged, test pause/restart/catch-up/credential failure/uninstall, and verify discovery from Claude and Codex. Any failed gate leaves automation paused.

## Success criteria

The release succeeds when Tom can finish setup from either host without editing config files; discover and select all appropriate Rhize/client projects; see assigned tasks in explainable order; review high-fit urgent opportunities without silent claims; see Jira-less delegations only as unscheduled `needs_jira`; receive a feasible buffered plan around all visible commitments; use bounded replanning, carryover escalation, and configured reconciliation; view the same plan revision in both hosts; avoid duplicate or unsafe writes; and pause, audit, change preferences, or uninstall cleanly.
