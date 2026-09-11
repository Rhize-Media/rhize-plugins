# Context doctor operations

The doctor is a Python 3.9+ executable. A model may add diagnosis after the authoritative
output; all measurements, arithmetic, coverage, and rendering belong to code. It never
performs repairs. `HOME` or `--home` supplies the data root; `--state-dir` can override
the derived evidence directory. `--rtk-bin` (or `RHIZE_RTK_BIN`) supplies the absolute RTK
executable when it is not in the declared home tool directories. Run `scripts/context_doctor.py --help` for its entrypoints.

## What a result proves

Each probe returns `OK`, `PROBLEM`, or `NOT_RUN` with run/probe/config identities and
measurement times. A completed measurement can establish a problem. Launch failures,
timeouts, blocked credentials, invalid output, and unsupported interfaces leave coverage
incomplete. “Problems detected; coverage incomplete” is deliberately possible.

The default pilot requires Headroom HTTP availability, RTK executable availability,
claude-mem capture persistence, CodeGraph currency, and credential-expiry metadata.
Availability does not establish compression benefit or recall quality. Capture uses
read-only SQLite counts/event times against session activity. Quiet windows are `NOT_RUN`;
stale telemetry is not described as a continuously failing writer. Access-token expiry
is not the lifetime of a refreshable login; unknown refresh expiry remains unknown.

Optional OpenWolf, memory-adapter, and host harness lanes remain explicit omissions.
Their owner/review date is declared in `scripts/context-doctor.config.json`. An expired
review makes configuration invalid until reviewed. Never demote a required probe to hide
a failure. Review config for other repositories: this pilot expects an existing CodeGraph
index and never initializes one.

## Durable evidence

Each attempt has a private directory in `~/.claude/context-manager/doctor/v1/`:

- `started.json`: attempt recorded before probes/config validation.
- `report.json`: immutable completed assessment, with source/config digests, scope,
  ordered evidence, calculated headline, and baseline identity/digest.
- `delivery.json`: monitor transport outcomes, separate from assessment health.
- `failure.json`: runner contract failure without raw exception text.

Directories use 0700 and files 0600 with atomic replacement. A killed runner leaves
started evidence without completion. A completed assessment can report problems.
Only compatible validated reports predating the new start supply a baseline. Rendering
rechecks the baseline and recomputes the delta, refusing altered or absent history.
Historical model-authored JSON in the parent directory is excluded.

Schema/hashes defend against accidental corruption and stale substitution. They cannot
defend against an actor allowed to rewrite both code and all local evidence.
`watch --state-dir PATH --repo REPO --config CONFIG --max-age-hours 192` checks local
completion/freshness in the expected scope/config. It cannot detect this Mac being down;
the external monitor owns that control.

## Independent monitor

The scheduler supplies `--monitor-config`, a private JSON file containing exactly
`organization`, `monitor_slug`, `environment`, and `keychain_service`. The service names
an existing Sentry DSN in Keychain. No secret belongs in config/source. Only a random
check-in ID, monitor slug, status, and environment leave the host in a check-in envelope;
no report, source content, file path, or token does. `accepted` means HTTP acceptance only: transport evidence,
not proof of Slack delivery.

Pilot: Thursday 08:00 America/New_York; 24-hour missed-start grace; 10-minute maximum
runtime; first-failure/first-recovery thresholds. Sentry is outside the Mac and Claude
scheduler. Missing launch produces no check-in; a killed run remains `in_progress`;
problematic/incomplete mandatory coverage sends `error`; successful mandatory measurements
send `ok`. Optional omissions remain in the report. Alert routing is separate from code.

The user selected `#jim-automation-alerts`. Sentry must have access to that private channel.
Read back configuration and matching check-in identities; verify actual Slack delivery and
recovery before describing the external path as operational. A same-host heartbeat is not
an independent monitor.

## Procedural memory

Package actual source, imported helpers, config, and verification tests together under
the registry artifact's `scripts/`. Never register a wrapper importing mutable source
outside the artifact's digest boundary. The scheduler verifies an explicit release hash
manifest before executing a private copy of those exact bytes. Report validation remains
necessary even when a registry runner reports invocation success.

A self-contained draft bundle prepared during this rollout passed the provenance schema,
static root/secret scans and its bundled failure suite. It is outside the registry and
retains `trust=unreviewed`, `health=unverified`; direct smoke success is not registry admission.

Admission uses the procedural-memory launcher and retains trust/health gates. Promotion
currently performs a Gemini description embedding and registry commit/index operation;
it is not a free read-only action. Promotion alone does not verify health. Durable approval
of an unreviewed artifact requires an explicit user decision. Never automatically add
`--approve-unreviewed` or `--allow-unverified`. Refused/never-started registry execution
must still be visible to the external monitor.

## Verification

From the marketplace root, run
`python3 -m unittest discover -s tests/rhize-context-manager -p test_context_doctor.py`.
Also use `/usr/bin/python3` on macOS: it is the scheduler's minimum runtime. Tests use
private fixtures without live credentials/providers. They inject malformed output/times,
replays, missing executables, auth blocks, timeouts, parent death, invalid configuration,
false deltas, wrong scope, unsafe URLs, and monitoring failures.

Live capture verification is separate: initialize one synthetic session through normal
claude-mem capture; use an event its actual tool filter permits; trace the unique marker
through observation persistence and the normal retrieval API. A skipped event is not a
passed canary. Never insert rows directly or close an upstream issue on a port check.

No live model A/B benchmark has run for this pilot. Failure injection proves deterministic
contracts, not improved model compliance or measured token savings.
