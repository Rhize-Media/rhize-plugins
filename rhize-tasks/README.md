# Rhize Tasks

Rhize Tasks is the local-first unified planning authority for Tom's Rhize, client, other-company, and personal work. It reads approved Jira, Google Calendar, Apple Reminders, and structured Slack inputs, produces one today-first plan, and writes only approved focus blocks and reminders inside dedicated boundaries.

The plugin is part of the Rhize OS **Get Your Time Back** module. Its purpose is practical: keep assigned work visible, surface urgent work Tom is well suited to take on, fit the work into real capacity, and carry unfinished work forward without letting an automation silently take over his calendar or task systems.

## Safety model

- SQLite on Tom's Mac is the planning authority. Jira remains the canonical work source.
- Preferences, scope discovery, the reversible access probe, and the first plan are reviewed locally.
- Setup is inactive until preferences are saved and the first plan is approved.
- Calendar writes are limited to one approved focus calendar. Reminder writes are limited to the exact approved `Rhize Tasks` list.
- Awareness calendars and reminder lists are read-only. Outside titles are redacted unless Tom explicitly opts in to a label.
- Assigned Jira work is considered first. Unassigned work is only suggested when it is in approved projects/types, urgent enough, and compatible with non-excluded competencies.
- Slack fallback reads only recognized structured delegation messages in the configured `#tom-tasks` channel from approved sender IDs. Items without Jira become approval-required `Needs Jira` records and are never scheduled.
- Every write is revision-bound and idempotent. Ambiguous results stop in prompted reconciliation instead of retrying indefinitely.
- A manual move of a plugin-owned focus block becomes protected local state; a later plan does not overwrite it.
- Completing an exact plugin-created reminder records local completion and creates an approval-required Jira reconciliation comment. It never changes Jira without approval.
- Pausing stops routines and connector writes. A stale or revoked connector pauses only that connector's writes where the remaining plan can still be evaluated safely.

## Architecture and source split

| Component | Authority | Read boundary | Write boundary |
| --- | --- | --- | --- |
| Jira | Canonical task state | Approved projects and issue types | Explicitly approved assignment, transition, comment, or create operations |
| Slack | Delegation fallback | One workspace, one channel, recognized bot/sender IDs, strict v1 message format | None |
| Google Calendar | Time awareness and focus blocks | Approved awareness calendars plus the focus calendar | Exact approved focus calendar only |
| Apple Reminders | Awareness and daily execution | Approved awareness lists plus `Rhize Tasks` | Exact `Rhize Tasks` list only |
| Local service | Unified plan, approvals, audit, carryover, setup | Local SQLite and connector snapshots | Local SQLite; approved operations delegated to connectors |
| Dashboard/artifact | Human review | Sanitized TodayView | Dashboard uses authenticated API; artifact is read-only |

The production runtime is split into a Node.js service and a small Swift EventKit helper. The helper accepts newline-delimited JSON, requests full Reminders access through macOS, and enforces the configured list ID. The service owns validation, planning, connector scopes, approval state, routine locks, and audit records. Claude and Codex skills call this same local authority; they do not independently reimplement Jira or scheduling logic.

## Requirements

- macOS 14 or newer.
- Node.js 22 or newer.
- `/usr/bin/security`, `/bin/launchctl`, `/usr/bin/swift`, `/usr/bin/codesign`, and `/usr/bin/sw_vers`.
- Xcode or Command Line Tools capable of building the Swift 6 EventKit package. Some Command Line Tools-only installations cannot resolve the macOS framework/toolchain combination even when `swift` is present; install or select a compatible full Xcode toolchain before treating that as an application defect.
- Loopback port `43179` available.
- Jira Cloud API credentials, Google OAuth client/refresh credentials, and a Slack bot token if Slack fallback is enabled.
- macOS Reminders permission for the installed helper app. Grant access only when the setup wizard runs its explicit check.

The installer validates these requirements before activation. It does not perform a live Jira, Calendar, Reminders, or Slack write during installation.

## Install

From the plugin directory:

```bash
npm run install:local
```

The install is transactional. It builds the Swift helper in release mode, constructs and ad-hoc signs `RhizeRemindersHelper.app` with bundle ID `media.rhize.tasks.reminders-helper`, installs an immutable runtime copy, writes the manifest and LaunchAgent atomically, and restores the previous loaded configuration if activation fails.

Installed paths:

| Purpose | Path |
| --- | --- |
| Application support and SQLite | `~/Library/Application Support/Rhize Tasks/` |
| Versioned runtime | `~/Library/Application Support/Rhize Tasks/runtime/versions/<version>/` |
| Install manifest | `~/Library/Application Support/Rhize Tasks/installation.json` |
| Database | `~/Library/Application Support/Rhize Tasks/state.sqlite` |
| Routine lock | `~/Library/Application Support/Rhize Tasks/routine.lock` |
| Logs | `~/Library/Application Support/Rhize Tasks/logs/` |
| LaunchAgent | `~/Library/LaunchAgents/media.rhize.tasks.plist` |

Support/runtime/log directories are restricted to the user, metadata is written with private modes, and symlinked or changed path ancestors are rejected. No token is written to the plist, runtime tree, logs, or SQLite database.

## Credentials and permissions

The wizard sends credentials directly to the authenticated loopback Keychain route. Values are cleared from the page before the request and are never echoed. The fixed Keychain pairs are:

| Connector | Keychain service | Accounts |
| --- | --- | --- |
| Local API | `media.rhize.tasks.api` | `bearer` |
| Jira | `media.rhize.tasks.jira` | `email`, `api-token` |
| Google | `media.rhize.tasks.google` | `client-id`, `client-secret`, `refresh-token` |
| Slack | `media.rhize.tasks.slack` | `bot-token` |

The installer provisions the local API bearer if it is absent. Connector secrets are entered only in the local dashboard. Do not paste them into Claude, Codex, a shell history, a config file, or a plugin prompt.

The EventKit helper requests full Reminders access because current macOS APIs require that authorization level. Application logic still narrows reads to configured awareness lists and narrows writes to the exact `Rhize Tasks` list. Google authorization is similarly narrowed in application code to approved calendar IDs and the one focus-calendar write target.

## Local dashboard and API

The service binds only to `127.0.0.1:43179`. `/health` returns only version and status. Every `/v1` route requires authentication.

Run the installed CLI's dashboard command to create a single-use, 60-second session URL:

```bash
node "$(python3 -c 'import json, pathlib; print(json.loads((pathlib.Path.home()/"Library/Application Support/Rhize Tasks/installation.json").read_text())["cliPath"])')" dashboard --json
```

Opening that URL exchanges a hashed nonce for an `HttpOnly`, `SameSite=Strict` cookie. The nonce is not stored in the DOM or browser storage. Cookie-authenticated mutations require the exact loopback Origin. A manual bearer field exists only for local troubleshooting and is never persisted.

Static browser assets are dependency-free and served from an allowlist: `/`, `/app.js`, and `/styles.css`. The standalone artifact contains escaped TodayView data, makes no network request, has no form or mutation control, and displays its plan revision.

## Seven-stage setup

1. Confirm local-first and approval boundaries.
2. Save identity and connector locations; credentials go directly to Keychain.
3. Discover and approve Jira projects/types, project importance, competencies, exclusions, urgency threshold, and suggestion limit.
4. Discover and approve awareness calendars, the focus calendar, awareness reminder lists, and the `Rhize Tasks` list. The focus calendar is always included in read scope.
5. Save per-day working intervals, breaks, capacity, buffer, focus-block sizing, splitting, meeting buffer, and freeze window.
6. Choose routine times, replanning mode, and reconciliation mode. Defaults are bounded replanning and prompted reconciliation.
7. Review the server-derived dry run and approve the first plan.

Scope expansion is previewed as an exact operation and requires approval. The access probe is also exact and approval-bound: it creates, verifies, deletes, and verifies absence of one disposable Calendar event and one Reminder. Any ambiguous cleanup fails closed and leaves automation inactive.

## Planning lifecycle

- **Morning:** sync approved sources and produce today's plan.
- **Midday:** bounded replan around current commitments while preserving active, completed, manually adjusted, and freeze-window blocks.
- **Evening:** identify unfinished scheduled work, increment carryover once, and preview the next day.
- **Catch-up:** after sleep or a missed launch, evaluate all missed phases but run exactly one appropriate phase. Repeated wakeups do not duplicate the evaluation.

The LaunchAgent invokes `routine catch-up` every 15 minutes and at load. The local routine evaluator decides whether morning, midday, or evening is actually due from Tom's saved times. A single-instance lock prevents overlapping runs and reclaims a stale lock only when its recorded process is no longer alive.

Carryover is intentionally bounded: the first miss is rescheduled once, the next asks for diagnosis, and repeated misses require a decision such as split, delegate, defer, or renegotiate. Local carryover, manual locks, reservations, and confirmed estimates survive ordinary Jira refreshes.

## Commands

Resolve the installed `cliPath` from `installation.json`; the CLI is not assumed to be on `PATH`.

```text
install
serve
routine morning|midday|evening|catch-up
doctor --json
provision-token --json
dashboard --json
artifact --output <private-html-path>
uninstall-items --json        # installer handshake; bounded request on stdin
uninstall --retain-data|--delete-data --retain-items|--delete-items
```

Repository convenience scripts are `npm run install:local`, `npm start`, `npm test`, `npm run validate`, and `npm run uninstall:local -- <both uninstall choices>`.

## Skills and Claude commands

The same six skills are packaged for Claude and Codex:

<!-- SKILL-MAP:BEGIN -->
| Skill | Description | Topics |
| --- | --- | --- |
| `manage-task-preferences` | Review and update Rhize Tasks planning preferences through the authenticated local dashboard. | project-planning, workflow-patterns |
| `plan-my-day` | Build, inspect, and approve a today-first Rhize Tasks plan from the local planning authority. | automation, project-planning |
| `reconcile-rhize-tasks` | Compare local Rhize task state with approved connector state and resolve drift through prompted reconciliation. | data-consistency, workflow-patterns |
| `review-task-opportunities` | Review urgent unassigned Jira work suggested for Tom by Rhize Tasks competency rules. | project-planning, search |
| `rhize-tasks-doctor` | Diagnose Rhize Tasks installation, local service, source freshness, and scheduling health without mutating connectors. | automation, observability |
| `rhize-tasks-setup` | Set up or resume the seven-stage local Rhize Tasks wizard, including connector discovery, scope approval, planning preferences, routines, a… | automation, project-planning, workflow-patterns |
<!-- SKILL-MAP:END -->

| Skill | Claude command |
| --- | --- |
| `$rhize-tasks-setup` | `/rhize-tasks:setup` |
| `$plan-my-day` | `/rhize-tasks:today` |
| `$review-task-opportunities` | `/rhize-tasks:review-opportunities` |
| `$reconcile-rhize-tasks` | `/rhize-tasks:reconcile` |
| `$manage-task-preferences` | `/rhize-tasks:preferences` |
| `$rhize-tasks-doctor` | `/rhize-tasks:doctor` |

Each skill resolves the versioned installed CLI, treats imported content as untrusted, and preserves the local approval and plan-revision boundary.

## Pause, recovery, and diagnosis

Use the dashboard pause control before changing credentials, permissions, calendar/list ownership, or routine policy. `doctor --json` reports only redacted version, database, activation, pause, and connector health. `revoked` means the credential or permission must be restored; it does not authorize a new write.

On a `revision_conflict`, refresh TodayView and review the new operations. On `reconciliation_required`, select only displayed operation IDs and approve one bounded attempt. If Reminders permission is denied, open macOS **System Settings > Privacy & Security > Reminders** and restore access to Rhize Reminders Helper, then rerun doctor and the approved probe. If port `43179` is occupied, identify and stop the conflicting local service before reinstalling.

The installer and uninstaller reject symlinked install ancestors. Do not move the installed runtime by hand; reinstall so the manifest, plist, signature, and runtime path remain consistent.

## Uninstall and retention

Uninstall requires two explicit decisions:

```bash
npm run uninstall:local -- --retain-data --retain-items
npm run uninstall:local -- --delete-data --retain-items
npm run uninstall:local -- --retain-data --delete-items
npm run uninstall:local -- --delete-data --delete-items
```

The data choice controls local Application Support data. The item choice separately controls plugin-owned Calendar/Reminder items. `--delete-items` invokes the installed runtime's bounded cleanup handshake, derives exact Reminder IDs and Calendar private ownership keys from attempted persisted operations, and refuses local deletion unless both systems return verified counts. It never broad-scans or deletes outside records. Keychain credentials are not embedded in retained data; remove connector credentials separately through Keychain when decommissioning access.

## Validation

No automated test performs live connector I/O. The release gate uses injected fakes and temporary SQLite databases:

```bash
npm test
npm run validate
swift test --package-path native/reminders-helper
python3 ../tests/rhize-ops/test_delegation_contract.py
python3 -m unittest ../tests.test_bump_version -v
```

Repository release validation also checks both plugin manifests, the marketplace, generated skill map, Claude plugin validation, JSON/plist syntax, deterministic generation, and whitespace. A real Tom-Mac acceptance remains mandatory before enabling writes: approve a disposable Jira issue and disposable Calendar/Reminder containers, complete setup, move and complete one sample, exercise pause/restart/catch-up/revocation/uninstall, and verify outside records are unchanged.

## Current 0.1 boundary

Rhize Tasks is a Mac-local planning service, not a cloud sync product or a general Jira automation engine. The first release handles the exact completion signal from a plugin-created reminder by prompting an approval-required Jira comment. Choosing among site-specific Done/Blocked/Partial transitions still requires Tom to review the actual Jira workflow; the plugin does not guess transition IDs. Slack messages outside the strict delegation contract are ignored.
