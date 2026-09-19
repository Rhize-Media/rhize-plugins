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
  stderr as a continuation request. The paired measurement commands now swallow entrypoint/runtime
  failures and return success without output.

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
