# Project State

## Verified facts

- 2026-09-19: paired-measurement commands in `rhize-context-manager/hooks/hooks.json` resolve
  through `${CLAUDE_PLUGIN_ROOT}`. Codex documents this compatibility variable and a versioned
  marketplace cache; source does not embed a specific cache version.
- The checked-out 0.32.0 package and local Codex cache copies at 0.31.0 and 0.32.0 contain the tool
  and Stop entrypoints. Current cache contents do not prove what was present when the failure
  occurred.
- Codex's current user config enables `rhize-context-manager`; it has no `installed_plugins.json`
  registry here. The exact plugin root loaded by the historical task is not recoverable from current
  state.
- A Python missing-file error exits nonzero with stderr. Codex treats a Stop hook's exit code 2 plus
  stderr as a continuation request. Release 0.32.1 suppressed these failures. The corrective release retains exit zero while
  emitting a bounded warning and persisting private diagnostic state.

## General rules

- Passive paired-measurement hooks must not block, continue, or alter user work when capture is
  unavailable. Preserve A/B, privacy, scope, authorization, and hook-trust gates.
- Do not mutate the global Codex config or installed cache to repair a version-root issue without
  evidence and a reversible verification plan.

## Open failures

- The historical 0.31.0 file absence is not reproducible from current cache state. A source packaging
  omission and wrong compatibility variable are not supported by current evidence; a transiently
  incomplete or removed task-pinned cache root remains possible, but Codex's historical update
  lifecycle evidence is unavailable.
- The new hook definition has not yet been installed or trusted in Codex. Existing tasks must reload
  the plugin root; updated hooks require host review/trust before execution.

## Lessons learned

- An infrastructure failure on Codex Stop differs from a normal silent hook skip: stderr plus exit 2
  is interpreted as a request to continue the agent. Non-blocking telemetry hooks must protect the
  process boundary as well as catch errors inside the script.
- Marketplace version bumps must be followed by `scripts/render_skill_map_docs.py`; the full-suite
  idempotence check catches stale generated README version tables even when skill inventories do
  not change.

## Last session

- 2026-09-19: verified no other reachable branch or shared checkout contained a fix, added a
  fail-silent process boundary to all four native paired-measurement events, and added isolated
  version-root and repeated-Stop regression coverage. The 120 Context Manager tests and 362 Dev
  Flow release tests pass. Version 0.32.1 is prepared but not installed in Codex; active tasks must
  reload and the changed hook definition must be reviewed/trusted by the host.

## Benchmark capture follow-through — 2026-09-19

- Model metadata may first become visible near the transcript tail at Stop. Capture now persists
  that bounded, matching-session observation even without a pending pair. Later prompts may use
  the session cache; existing receipt model/answer-status fields remain unchanged.
- A clean native smoke must use an explicit stdin boundary. A Python heredoc inherited by a
  Claude subprocess contaminated the smoke prompt; this was not host-added action guidance.
  Controlled answer drivers already use explicit stdin PIPE and were unaffected.
- The expanded exploratory memory screen completed 180 calls across both hosts, with frozen
  source snapshots preserved before this patch. Synthetic transport completion and term checks
  are separate from semantic review and do not establish general benefit.
- Cold source review checked stale-turn handling, no-pair persistence, scope, bounded transcript
  reads and immutable prompt-time evidence. Focused regressions cover each boundary. Version
  0.32.2 follows the separately merged 0.32.1 hook-containment release; installation and observed
  native activation are verified separately from source checks.

- Independent model review found delayed-Stop and replay-counting edge cases in the initial patch.
  Explicit turn bindings now survive unmeasured prompts, while late-resolved model identity is
  excluded from pair identity. Regressions pin both cases and mixed prompt/Stop turn-id presence.
  Hosts that omit explicit turn identifiers cannot supply a reliable stale-event comparison.

## Passive measurement corrective release — 2026-09-19

- Verified the four passive hooks still suppressed missing entrypoint and runner failures on base
  5788492, after the separate 0.32.2 attribution fix. No historical cache cause was established.
- Claude Code Fable (native observed claude-fable-5-1) reviewed the full private plan before source
  implementation. Incorporated flock/fd inheritance, detached stdio, dead-worker lock probes,
  superseded-install eviction, quiet oversized-payload handling and atomic warning deduplication.
- New stdlib runtime separates foreground and worker diagnostics from actual A/B completeness.
  Missing/corrupt diagnostic storage remains unavailable, never healthy; runtime recovery cannot
  reconstruct lost measurements. No existing capture/attribution engine or budget was rewritten.
- Baseline: 214 focused tests passed. Corrected full suite: 1,461 passed, 5 skipped and 18
  subtests passed; Dev Flow release suite: 362 passed. Marketplace/all ten plugin manifests,
  configuration lint, map freshness, setup-artifact freshness and doc idempotence passed.
  Packaged failure/recovery exercises do not establish native-host activation.
- Full-suite concurrency testing reproduced macOS ENOENT during simultaneous O_CREAT|O_NOFOLLOW
  lock creation. Exclusive creation followed by no-create reopening preserves no-follow safety;
  25 repeated concurrent first-create/dedup cycles passed. Process-inspection and Git-hardlink
  tests require execution outside the restricted sandbox; both pass with required access.
- General rule: passive measurements may let user work continue, but failure must remain observable.
  A worker that retains a host pipe can block the host despite start_new_session; disconnect all
  stdio and validate the inherited lock. A/B receipt completeness is separate from runtime health.

- Fable implementation review found no security/data-integrity blocker; its minor warning-cadence
  correction, active-worker eviction protection, long-running status advisory and detached fixture
  cleanup were incorporated. Runner success returns0 and resolved installation identity match
  were verified directly. No new worker watchdog can orphan separate native process groups.

## Skylos advisory integration — 2026-09-19

- Devflow can consume an explicitly provided, source/base/policy-bound Skylos 4.38.0 report.
  Scanner execution is optional and isolated on macOS with a dedicated runtime; no automatic
  installation, hooks, uploads, source execution or cleanup is added. Context Pack remains WATCH.
- The approved inert sentinel verified selected-source reads, unrelated-content denial, denied
  source writes/networking, scratch writes and unchanged source. Serial scanning avoids IPC
  permissions; direct Command Line Tools Git avoids Apple's launcher shim in the sandbox.
- All 13 real fixture pairs ran. Seven Arm B cases had findings, four were incomplete and two had
  no findings. Strict rule/location matching detected 5/9 targets; two expectation mismatches and
  two missing-test-impact targets remain explicit in evals/skylos/RESULTS.md. No task-benefit claim.
- The 407-test Devflow suite passed. Independent implementation review passed after fixing malformed
  input handling, failed/missing coverage, non-Python behavior gaps and read-only Git boundaries.
- General rule: schema/digest acceptance is consistency and freshness, never an execution
  attestation. Static findings cannot prove regression coverage or approve release. Required
  checks must complete; non-applicable language checks must be explicit.
- Runtime support is initially macOS/Apple Command Line Tools. Other hosts fail closed.
  The existing test-evidence runner still reports execution_unavailable.
- Final merged-tree validation: 1,507 tests passed, 5 skipped and 18 subtests passed. All ten plugin
  manifests, marketplace, configuration lint, skill-map/setup freshness and doctor passed. Tests
  using temporary HOME must use the real Node binary rather than the mise shim.
