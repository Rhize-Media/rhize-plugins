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

## Running under Claude Cowork / non-macOS environments

Claude Cowork sessions run in a Linux container. Rhize Tasks cannot install, run its LaunchAgent, sign or launch the Swift EventKit helper, or open the local dashboard there — Keychain, EventKit, `launchctl`, `security`, `swift`, and `codesign` do not exist outside macOS.

Every skill in this plugin checks `uname -s` before attempting any macOS-only step. On a non-Darwin host, it will not touch the installer or the local service; instead it reviews the `service/`/`installer/` code, runs `npm test` (the fake-backed service-layer suite — no live connector I/O either way), and hands back a setup runbook for you to run yourself in Terminal.app on your Mac. Use one of these environments when you want to actually install, run, or exercise Rhize Tasks against a real Jira/Calendar/Reminders/Slack account.

## Install

From the plugin directory:

```bash
npm run install:local
```

The install is transactional. It builds the Swift helper in release mode, constructs and ad-hoc signs `RhizeRemindersHelper.app` with bundle ID `media.rhize.tasks.reminders-helper` (set `RHIZE_TASKS_SIGN_IDENTITY` to sign with a real identity instead), installs an immutable runtime copy, writes the manifest and LaunchAgent atomically, boots out the old agent before swapping the runtime, and restores the previous loaded configuration only when it can verify that restore is safe — otherwise it stops with `manual_recovery_required` rather than mutating a runtime it cannot prove is quiescent.

Reinstalling while the plugin's own local server is running is handled automatically: the installer recognizes its own `/health` endpoint on port `43179`, stops that server via its pidfile, and proceeds. Only a foreign process on the port aborts the install.

The LaunchAgent's Node binary is resolved to a stable path at install time. If the installing shell's `node` lives in an ephemeral location (fnm multishell, nvm version dir, Homebrew Cellar), the installer probes `/usr/local/bin/node` and `/opt/homebrew/bin/node` for a capable (≥22, `node:sqlite`-enabled) alternative; if none exists it fails closed with a remediation pointing to the nodejs.org installer. Set `RHIZE_TASKS_ALLOW_EPHEMERAL_NODE=1` to override, accepting that the agent dies when that path disappears. The chosen path is recorded in `installation.json` and checked by `doctor`.

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

The CLI is not assumed to be on `PATH`. Resolve the installed `cliPath` from `installation.json` once — this is the one canonical way these docs reach the CLI, reused in the Commands section below:

```bash
RHIZE_TASKS_CLI="$(python3 -c 'import json, pathlib; print(json.loads((pathlib.Path.home()/"Library/Application Support/Rhize Tasks/installation.json").read_text())["cliPath"])')"
```

Run the installed CLI's dashboard command to create a single-use, 60-second session URL:

```bash
node "$RHIZE_TASKS_CLI" dashboard --json
```

The `dashboard` command ensures the server is actually running before minting the URL: it probes `/health`, starts a detached `serve` process (tracked by a pidfile in Application Support) if nothing answers, and waits for health before returning. The installer and uninstaller use the same pidfile to stop the server cleanly.

Opening that URL exchanges a hashed nonce for an `HttpOnly`, `SameSite=Strict` cookie; the nonce is consumed only after it validates, so a garbage request cannot burn a pending session URL. The nonce is not stored in the DOM or browser storage. Every cookie-authenticated request — all methods, not just mutations — requires the exact loopback Origin when an Origin header is present, a validated `Host`, and the dashboard's own `x-rhize-tasks-dashboard` request header, so pages served from other local ports cannot trigger side-effectful GETs (discovery, doctor) as subresources. A manual bearer field exists only for local troubleshooting and is never persisted.

Static browser assets are dependency-free and served from an allowlist: `/`, `/app.js`, and `/styles.css`. The standalone artifact contains escaped TodayView data, makes no network request, has no form or mutation control, and displays its plan revision.

## Seven-stage setup

1. Confirm local-first and approval boundaries.
2. Save identity and connector locations; credentials go directly to Keychain.
3. Discover and approve Jira projects/types, project importance, competencies, exclusions, urgency threshold, and suggestion limit.
4. Discover and approve awareness calendars, the focus calendar, awareness reminder lists, and the `Rhize Tasks` list. The focus calendar is always included in read scope.
5. Save per-day working intervals, breaks, capacity, buffer, focus-block sizing, splitting, meeting buffer, and freeze window.
6. Choose routine times, replanning mode, and reconciliation mode. Defaults are bounded replanning and prompted reconciliation.
7. Review the server-derived dry run and approve the first plan.

Scope expansion is previewed as an exact operation and requires approval. Expanding an already-configured profile beyond its approved scopes now stages a pending scope change (visible in the dashboard's dedicated approval list and in `/v1/setup/status`) for one-click approval instead of hard-rejecting the settings save; approval applies the settings, audit record, and pending-state cleanup in a single transaction. The access probe is also exact and approval-bound: it creates, verifies, deletes, and verifies absence of one disposable Calendar event and one Reminder. A pending or orphaned probe is surfaced through setup status with its ID and state, is never silently overwritten by a re-preview, and its items are folded into uninstall cleanup. Any ambiguous cleanup fails closed and leaves automation inactive.

## Planning lifecycle

- **Morning:** sync approved sources and produce today's plan.
- **Midday:** bounded replan around current commitments while preserving active, completed, manually adjusted, and freeze-window blocks.
- **Evening:** identify unfinished scheduled work, increment carryover once, and preview the next day.
- **Catch-up:** after sleep or a missed launch, evaluate all missed phases but run exactly one appropriate phase. Repeated wakeups do not duplicate the evaluation.

The LaunchAgent invokes `routine catch-up` every 15 minutes and at load. The local routine evaluator decides whether morning, midday, or evening is actually due from Tom's saved times. A single-instance lock prevents overlapping runs and reclaims a stale lock only when its recorded process is no longer alive.

Carryover is intentionally bounded: the first miss is rescheduled once, the next asks for diagnosis, and repeated misses require a decision such as split, delegate, defer, or renegotiate. Local carryover, manual locks, reservations, and confirmed estimates survive ordinary Jira refreshes.

## Commands

Using the same `$RHIZE_TASKS_CLI` resolved above:

```text
node "$RHIZE_TASKS_CLI" install
node "$RHIZE_TASKS_CLI" serve
node "$RHIZE_TASKS_CLI" routine morning|midday|evening|catch-up
node "$RHIZE_TASKS_CLI" doctor --json
node "$RHIZE_TASKS_CLI" provision-token --json
node "$RHIZE_TASKS_CLI" dashboard --json
node "$RHIZE_TASKS_CLI" artifact --output <private-html-path>
node "$RHIZE_TASKS_CLI" uninstall-items --json        # installer handshake; bounded request on stdin
node "$RHIZE_TASKS_CLI" uninstall --retain-data|--delete-data --retain-items|--delete-items
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

Use the dashboard pause control before changing credentials, permissions, calendar/list ownership, or routine policy. `doctor --json` reports redacted version (read from `package.json`), database, activation, pause, connector health, and installation health: `agentLoaded`, `plistNodePathExists`, `runtimeVersionMatch`, and `lastRoutineRun` (each degrades to `null` rather than failing). `revoked` means the credential or permission must be restored; it does not authorize a new write. A Google refresh token rejected with `invalid_grant` and a denied macOS Reminders authorization both report as `revoked` — they are no longer indistinguishable from `offline`.

On a `revision_conflict`, refresh TodayView and review the new operations. On `reconciliation_required`, select only displayed operation IDs and approve one bounded attempt. If Reminders permission is denied, open macOS **System Settings > Privacy & Security > Reminders** and restore access to Rhize Reminders Helper, then rerun doctor and the approved probe. If port `43179` is occupied by a foreign process, identify and stop it before reinstalling; the plugin's own server is detected and stopped automatically. Connector rate limits are honored: a `429` waits out `Retry-After` (capped at 30s) before its single bounded retry instead of retrying immediately.

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

No automated test performs live connector I/O. The test suite uses injected fakes and temporary SQLite databases. Run these from the plugin directory (`rhize-tasks/`) unless noted otherwise:

```bash
npm test
swift test --package-path native/reminders-helper
python3 ../tests/rhize-ops/test_delegation_contract.py
```

`python3 -m unittest tests.test_bump_version -v` lives in the parent `rhize-plugins` repo, not this plugin, so it needs that directory as its working directory — run it as `(cd .. && python3 -m unittest tests.test_bump_version -v)` from `rhize-tasks/`, or `python3 -m unittest tests.test_bump_version -v` directly from the `rhize-plugins` root.

`npm run validate` is not a release gate — it only checks that `package.json` and `setup/manifest.json` are syntactically valid JSON. Treat it as a quick manifest sanity check, not a substitute for the tests above.

Repository release validation also checks both plugin manifests, the marketplace, generated skill map, Claude plugin validation, JSON/plist syntax, deterministic generation, and whitespace. A real Tom-Mac acceptance remains mandatory before enabling writes: approve a disposable Jira issue and disposable Calendar/Reminder containers, complete setup, move and complete one sample, exercise pause/restart/catch-up/revocation/uninstall, and verify outside records are unchanged.

## Known limitations (open decisions)

- **Reminders writes under launchd are expected to fail authorization.** macOS attributes a TCC request to the responsible process; the helper binary is spawned directly by the Node agent, so under launchd there is no GUI context to prompt and no bundle-derived attribution. Interactive use (server started from Terminal via `dashboard`) prompts and works; the background routine's Reminders writes will report `revoked` until the helper is registered as its own launch agent or launched through LaunchServices. This is a deliberate open design decision, now *visible* through doctor rather than silent.
- **Ad-hoc signing resets the Reminders grant on every rebuild.** Without a stable Developer ID signature, the helper's cdhash changes each time it is rebuilt and TCC re-prompts. Supply `RHIZE_TASKS_SIGN_IDENTITY` once a signing identity is provisioned.
- **Google OAuth apps in “Testing” publishing status expire refresh tokens after 7 days.** That expiry now surfaces as `revoked` instead of `offline`, but the fix is publishing the OAuth consent screen, not code.
- **Slack sync reads a bounded 7-day lookback window per run** (configurable), not a persisted high-water mark.

## Current 0.1 boundary

Rhize Tasks is a Mac-local planning service, not a cloud sync product or a general Jira automation engine. The first release handles the exact completion signal from a plugin-created reminder by prompting an approval-required Jira comment. Choosing among site-specific Done/Blocked/Partial transitions still requires Tom to review the actual Jira workflow; the plugin does not guess transition IDs. Slack messages outside the strict delegation contract are ignored.
