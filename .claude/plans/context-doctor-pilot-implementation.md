# Context doctor pilot: impact map and execution checklist

Status: released 2026-09-11; external failure/recovery alerts verified 2026-09-13. User selected #jim-automation-alerts and
accepted recommended monitor thresholds. Pilot is weekly-context-doctor only.
Coordinator owns source writes, integration, verification, and release. Recommended
executor for future handoff: Terra for integration; independent capable-model review.

## Current behavior and evidence

- Evidence: context-doctor.md delegates measurement, arithmetic, persistence, and delta
  to the model. The live Desktop routine suppresses output based on that prose delta.
- Evidence: the previous report contains stale and contradictory version/duration claims,
  even in its corrections. It is historical context, never current execution evidence.
- Evidence: at 2026-09-11T18:31Z the read-only claude-mem database had 53,419 observations,
  most recent at 18:30:50Z; health lastSuccessAt was 18:31:02Z, failures=0. PATH setting
  remains the mise shim. This proves resumed persistence, not the controlled canary.
- Evidence: CodeGraph exploration in rhize-plugins found existing capture-health
  validators for experiment receipts, with incompatible domain/schema. Reuse the
  validation principles, not those experiment models or a cross-plugin import.
- Evidence: procedural-memory run checks artifact closure/digest/trust/health, records
  invocation results, and executes declared entrypoints. It does not validate every
  doctor's output or detect a never-started invocation. Sibling runtime is not indexed.
- Evidence: claude-routines already has sync-check, pointer contracts, and with-node;
  directory count is not evidence of missing ownership. Use existing consolidation work.

## Intended semantic delta

A versioned, standard-library runner owns bounded probes, strict current-run evidence,
all date arithmetic, coverage, baseline comparison, atomic persistence, and rendering.
The scheduled model invokes one real executable and may add labeled diagnosis only.
A separate Sentry cron monitor detects missed check-ins and unfinished runs independently
of this Mac/Claude scheduler, routing incidents to the user-selected Slack channel.

## Invariants and must-not-change boundaries

- Current measurement and source-event age are distinct. No activity/unknown collection
  never becomes zero or OK. Known failures and incomplete coverage can coexist.
- Mandatory probes are declared before execution. Missing/malformed/stale/mismatched
  evidence cannot satisfy a probe. Optional omissions remain explicit.
- No secrets/raw logs/transcripts in artifacts, Slack, or Sentry. Only aggregate status
  and random check-in identity leave the host. No embedding/model API calls.
- No SQLite repair, downgrade, restart, backlog deletion, or upstream issue closure.
- Never bypass procedural-memory trust/health; staged packaging is not durable approval.
- Existing production website code, protected workflow/env files, unrelated scheduler
  drift, and other experiments remain untouched. No new scheduler migration framework.

## Current structural touchpoints

| Repository | Entry point | Why affected | Evidence |
|---|---|---|---|
| rhize-plugins | rhize-context-manager/commands/context-doctor.md | Replace model-owned steps | Current command read |
| rhize-plugins | new scripts/context_doctor.py + config | Deterministic pilot | Planned addition |
| rhize-plugins | tests/rhize-context-manager | Failure injection and provenance checks | Existing test convention |
| claude-routines | scheduled/with-node.sh | Resolve actual shim before ambient alternatives | Source read; independent audit |
| claude-routines | weekly-context-doctor definitions | Invoke real runner; preserve report | Live/tracked definitions read |
| procedural-memory | launcher, promote/verify contracts | Package exact reusable artifact | Runtime/source read; no source edits planned |

## Planned additions and deletions

- Add pilot runner, declared probe config, deterministic failure-injection tests, and
  concise operational documentation. Replace manual pipelines in the doctor command.
- Add minimal scheduler launcher and bootstrap regression tests where needed.
- Prepare a self-contained procedural artifact through the supported launcher, retaining
  approval gates; no wrapper that executes unverified bytes outside its digest boundary.

## External and operational effects

- Read existing local health/DB/expiry metadata; only private diagnostic artifacts written.
- One controlled synthetic capture canary through normal capture/retrieval interfaces.
- Sentry cron monitor: existing infrastructure project, Thursday 08:00 America/New_York,
  24-hour missed-run grace, 10-minute max runtime, first-failure/first-recovery thresholds.
  Read current account and Slack integration before configuration; no purchased plan.
- Deploy only the pilot definition changes to its existing scheduler surfaces. Preserve
  schedule/model settings. Fold C/D evidence into existing consolidation tracking.
- Refresh the vault summary from verified repo results after implementation.

## Reuse opportunities

Use with-node, existing sync-check/pointer smoke, procedural launcher/digest gates, and
existing Sentry/Slack integration. Keep plugins self-contained. Existing capture-health
experiment schema remains unchanged.

## Acceptance tests

- Valid probes yield deterministic status; PROBLEM + missing mandatory probe yields both
  problems and incomplete coverage. Optional omission never masquerades as execution.
- Auth blocked, missing executable, malformed JSON, timeout, stale run ID, wrong config,
  missing/duplicate probe, invalid/future timestamps, and nonzero exit cannot yield healthy.
- Run killed mid-flight leaves started evidence without completion; watchdog detects it.
- Prior config/scope/source revision mismatch cannot supply current evidence or a false delta.
- Private atomic writes, secret-free errors, command deadlines and process-group cleanup.
- PATH fixture starts with competing runtime before shims: shim still wins; missing shim
  or requested Node command refuses. No undeclared fallback.
- Live capture canary observed through persistence and retrieval, separately from fixtures.
- Sentry check-in and exact Slack routing read back; injected test event clearly labeled.

## Explicitly unaffected paths

No generic agent-compliance framework, core procedural runner changes, broad task migration,
new retrieval adapter, historical receipt rewrite, DB repair, or external content egress.

## Unknowns and confidence

Sentry current integration/permissions and paid quota must be verified. Existing watchdog
metadata export coverage is incomplete until audited. Fable unavailable in current tool
catalog; independent Codex agent reviews design. Observational agent overlap is not A/B
efficacy evidence. Local tests are controlled fixtures; live model-compliance improvement
remains unmeasured (Arm A and Arm B not run as a model benchmark).

## Implementation order and progress

- [x] Read handoff, current plan/source, Git state, and live aggregate capture metadata.
- [x] Confirm pilot/alert recommendations with user; run independent design/bootstrap audit.
- [x] Persist map and prepare enforcement receipt before source edits.
- [x] Implement and test runner/probe contract and failure injection.
- [x] Integrate and deploy scheduler bootstrap and prepare the validated reusable artifact.
- [x] Verify capture canary, live report, docs, reconciliation, and exact release.
- [x] Configure independent monitor and verify HTTP transport without claiming delivery.
- [x] Approve Sentry access to the private channel, activate the monitor, and verify failure/recovery delivery.

## Verified implementation checkpoint

- Independent design/source reviews reproduced seven defects; all corrected with regression
  checks. The final two concerned watchdog recovery after config revision and malformed UUIDs.
- Capture canary persisted IDs 55583/55586 and retrieved the synthetic marker via normal API.
- Real host run cdc5c798-7f77-476a-bf4a-a6600db3ad03 passed five mandatory probes; three optional
  omissions remain explicit. Sandbox socket/Keychain denials were separately identified.
- Scheduler release uses a private snapshot of five pinned files; offline failure injections
  run on each invocation. Existing MCP cost policy is preserved.
- At the 2026-09-11 checkpoint, Sentry private-channel permission blocked activation; see the 2026-09-13 activation record below.
- No provider A/B efficacy benchmark or paid description embedding was run.

## Final bounded scope additions from verified review

- Vault-inbox's live cluster-only fallback still uses bare graphify and fails under
  PATH=/usr/bin:/bin. Replace only that command with the installed absolute wrapper.
  Preserve its live weekly cadence/caps/linking changes; synchronize those existing
  owner edits as the deployment baseline, not as new policy in this task.
- The procedural draft's static root scan found default home discovery and a fixed
  Homebrew RTK path. Make HOME an explicit environment input and RTK an optional
  --rtk-bin absolute input, supplied by the scheduler. Construct Sentry's URL with
  a URL helper to avoid its path fragment being treated as an artifact data root.
  This does not bypass any root/trust/approval check or modify registry source.

## Release verification

- Final independent source pass: 29/29 tests under /usr/bin/python3. Scheduler bootstrap
  and snapshot tests: 4/4. Existing sync/pointer/watchdog smokes: 14/14, 4/4, 5/5.
- Repository contract gate: 363 tests passed, plugin config and generated skill-map checks
  passed. Wider config-lint suite: 63 passed, 3 existing skips, 1 pre-existing failure in
  test_claude_md_contains_every_required_phrase; reproduced from starting commit 1d8794d
  with the same ten missing phrases. The existing test was retained; the required compact CLAUDE.md rules were restored before release.
- Final host run 632dc4f3-54d5-4b23-abde-e94324506d31 completed at
  2026-09-11T19:18:01.390203Z: mandatory 5/5 OK, optional 3 NOT_RUN. Sentry accepted the
  HTTP envelopes; disabled-monitor readback contained no check-ins. That checkpoint did
  not establish operational alert delivery; see the later activation record below.
- Draft bundle .claude/artifacts/context-doctor-0.31.0 passes provenance validation,
  root/secret static scans (zero findings), and its 29-test bundled smoke. It remains
  outside the registry, trust=unreviewed and health=unverified; no paid promotion or
  durable approval took place. Required software is versioned in the plugin.

## Exact changed-file reconciliation

### rhize-plugins

- `.claude-plugin/marketplace.json` — implements, tests, documents or publishes the bounded doctor/bootstrap changes above.
- `.claude/plans/context-stack-observability-hardening.md` — implements, tests, documents or publishes the bounded doctor/bootstrap changes above.
- `CHANGELOG.md` — implements, tests, documents or publishes the bounded doctor/bootstrap changes above.
- `generated/skill-map.static.json` — implements, tests, documents or publishes the bounded doctor/bootstrap changes above.
- `rhize-context-manager/.claude-plugin/plugin.json` — implements, tests, documents or publishes the bounded doctor/bootstrap changes above.
- `rhize-context-manager/.codex-plugin/plugin.json` — implements, tests, documents or publishes the bounded doctor/bootstrap changes above.
- `rhize-context-manager/CHANGELOG.md` — implements, tests, documents or publishes the bounded doctor/bootstrap changes above.
- `rhize-context-manager/GUIDE.md` — implements, tests, documents or publishes the bounded doctor/bootstrap changes above.
- `rhize-context-manager/README.md` — implements, tests, documents or publishes the bounded doctor/bootstrap changes above.
- `rhize-context-manager/commands/context-doctor.md` — implements, tests, documents or publishes the bounded doctor/bootstrap changes above.
- `rhize-context-manager/docs/context-doctor.md` — implements, tests, documents or publishes the bounded doctor/bootstrap changes above.
- `rhize-context-manager/scripts/context-doctor.config.json` — implements, tests, documents or publishes the bounded doctor/bootstrap changes above.
- `rhize-context-manager/scripts/context_doctor.py` — implements, tests, documents or publishes the bounded doctor/bootstrap changes above.
- `rhize-context-manager/scripts/context_doctor_monitor.py` — implements, tests, documents or publishes the bounded doctor/bootstrap changes above.
- `rhize-context-manager/scripts/context_doctor_probes.py` — implements, tests, documents or publishes the bounded doctor/bootstrap changes above.
- `tests/rhize-context-manager/test_context_doctor.py` — implements, tests, documents or publishes the bounded doctor/bootstrap changes above.

### claude-routines-context-doctor

- `scheduled/README.md` — implements, tests, documents or publishes the bounded doctor/bootstrap changes above.
- `scheduled/claude-code-desktop/ai-stack-version-drift/SKILL.md` — implements, tests, documents or publishes the bounded doctor/bootstrap changes above.
- `scheduled/claude-code-desktop/vault-inbox-processor/SKILL.md` — implements, tests, documents or publishes the bounded doctor/bootstrap changes above.
- `scheduled/claude-code-desktop/weekly-context-doctor/SKILL.md` — implements, tests, documents or publishes the bounded doctor/bootstrap changes above.
- `scheduled/claude-code-mcp/weekly-context-doctor/SKILL.md` — implements, tests, documents or publishes the bounded doctor/bootstrap changes above.
- `scheduled/with-node.sh` — implements, tests, documents or publishes the bounded doctor/bootstrap changes above.
- `.claude/plans/context-doctor-pilot-implementation.md` — implements, tests, documents or publishes the bounded doctor/bootstrap changes above.
- `scheduled/context-doctor-release.json` — implements, tests, documents or publishes the bounded doctor/bootstrap changes above.
- `scheduled/docs/context-doctor-reconciliation-2026-09-11.md` — implements, tests, documents or publishes the bounded doctor/bootstrap changes above.
- `scheduled/run-context-doctor.py` — implements, tests, documents or publishes the bounded doctor/bootstrap changes above.
- `scheduled/tests/test_context_doctor_launcher.py` — implements, tests, documents or publishes the bounded doctor/bootstrap changes above.
- `scheduled/tests/test_with_node.py` — implements, tests, documents or publishes the bounded doctor/bootstrap changes above.

## Required release-gate repairs

Full pytest exposed pre-existing missing operational rules in `CLAUDE.md`, stale generated
version tables after this and previous releases, and fixture bootstrap restrictions. Restore
only the compact operational rules enforced by the existing tests (no test weakening), and
regenerate `README.md`, `docs/README.md`, `generated/SKILL-CATALOG.md` and affected plugin README
managed sections with `scripts/render_skill_map_docs.py`. Verify the prior failures with the
installed mise Node binary explicitly selected and local clone permission available.

## Final release gate result

Full repository pytest: 1,351 passed, five existing skips, 18 subtests passed. The first
full pass exposed the documented CLAUDE.md trim, stale generated version tables, and
fixture HOME/mise and local-clone restrictions. Compact rules and managed tables are now
restored; the successful full pass explicitly selected the installed Node 24 binary and
allowed isolated local clone fixtures. No tests were removed, weakened, or newly skipped.

Both source reviews and both repository impact-map reconciliations passed. At release on
2026-09-11, Sentry access to the selected private Slack channel remained blocked; HTTP
acceptance by a disabled monitor was not counted as monitoring or Slack delivery.


## Released state and next-run lesson

- Plugin PR #26 merged at `d0fdf9383c6782a44506ace24183db1783142d57`; validate and
  tag-release CI succeeded. Scheduler PR #4 merged at
  `bdd4e128ee804e1eb5b4569ea31323be2963bda9`. Live configuration PR #1 merged to
  claude-config main; its two changed definitions match the committed scheduler copies.
- Both Claude and Codex select rhize-context-manager 0.31.0. All four installed runner,
  helper and config files match the release source on both hosts.
- Deployment receipt and original-file backups:
  `~/.claude/context-manager/doctor/deployments/20260911T193350Z/receipt.json`.
  Durable capture-canary proof: `~/.claude/context-manager/doctor/canary-2026-09-11.json`.
- Final sync checked all 24 definitions: four pre-existing unrelated differences remain
  (Desktop daily-learn-harvest/headroom-learn-sweep; MCP promotion-approval-digest/
  seo-remediation-consumer). All task-owned definitions are synchronized and committed.
- New observed failure: updating a plugin can remove an old cache directory still referenced
  by this running task's hooks. Codex then emitted missing memory-opportunity tool/stop hook
  errors. Recovery restored 0.30.0 bytes from their original committed tree and verified both
  hooks against that commit, retaining the installed 0.31.0 selection. Do not remove the
  restored cache while active tasks still use it; reload active tasks at a suitable boundary.
  The exact cache reference in an error is evidence, not permission to substitute new-version
  files under the old version or disable validation hooks.
- On 2026-09-11, Sentry could not access #jim-automation-alerts. Automatic approval review
  rejected the invitation because it grants ongoing access to private channel contents.
  Jim explicitly approved that access on 2026-09-13; membership is now verified and the
  monitor is active. Historical HTTP acceptance alone was not counted as delivery.


## External alert activation — 2026-09-13

Jim explicitly approved adding the existing Sentry app to private #jim-automation-alerts.
Slack membership readback includes Sentry user U09NWLZ2NNR in channel C0BBUHR1JJU.
Monitor weekly-context-doctor is active and unmuted. Its schedule remains Thursday 08:00
America/New_York with 1,440-minute grace, 10-minute max runtime and first-failure/recovery
thresholds. Readback sets the next expected start to 2026-09-17T12:00:00Z and the missed-run
cutoff to 2026-09-18T12:00:00Z. The next natural scheduled run has not occurred yet.

- Failure workflow 3985314 (created as legacy rule 17446159) filters monitor.slug=weekly-context-doctor and
  sends to the approved channel. The labeled synthetic failure created SEO-HEALTH-INFRA-8
  (7729654817); [Sentry's actual Slack failure message](https://rhize-media.slack.com/archives/C0BBUHR1JJU/p1789303638649269)
  identifies the exact rule. HTTP acceptance alone was not used as delivery evidence.
- Successful check-ins automatically resolved the incident; no manual issue resolve was used.
  Recovery workflow 3985323 uses issue_resolved_trigger, attached only to doctor detector
  10305638. [Sentry's actual Slack recovery message](https://rhize-media.slack.com/archives/C0BBUHR1JJU/p1789304333346049)
  identifies that workflow. Both rules retain the 1,440-minute per-issue notification cooldown.
- The first recovery-only workflow attempt did not trigger because it required the
  context-doctor environment. Sentry resolution Activities carry no environment, and the
  workflow engine excludes environment-bound rules for those Activities. Removing only
  that environment restriction, while retaining the exact doctor detector association,
  made the next automatic recovery reach Slack. This is a verified integration failure mode,
  not a reason to loosen the doctor probe evidence contract.
- Diagnosis source: [Sentry workflow processor, verified revision e917c50](https://github.com/getsentry/sentry/blob/e917c50c2413cd5082524c3f98791eb035fd38de/src/sentry/workflow_engine/processors/workflow.py#L398),
  and the [supported issue-resolved trigger](https://docs.sentry.io/api/monitors/create-an-alert-for-an-organization/).
- Three bounded synthetic failure/success pairs tested initial delivery, reproduced the
  recovery filter defect and verified its correction. The final pair is error
  6eaa5cff-5e27-47ef-b2ea-41cc1bb2cfb4 / OK 72571647-195f-4b10-8ff4-7d264d208f8e.
  Final monitor state is OK with no active incident. These check-ins are labeled activation
  fixtures, not new claims about current capture health or a live model Arm A/Arm B result.
- Durable readback and all test identities:
  `~/.claude/context-manager/doctor/deployments/20260913-alert-activation/receipt.json`.
  The original 2026-09-11 release receipt remains historical evidence and is not rewritten.
- The legacy project rules API returned HTTP 410 during final verification. Current organization
  workflow endpoints returned both active routes and their actual last-triggered timestamps.
  Use those workflow IDs for future management; the historical Slack alert still identifies
  the original legacy rule ID.

No plugin source, registry, scheduler cadence/model, upstream issue #3609 or unrelated alert
rule was changed during activation. The reusable procedural bundle remains unpromoted.
