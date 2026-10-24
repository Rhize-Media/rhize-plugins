# Evaluation, cost and telemetry

Keep three claims separate:

1. **Authoring:** same normalized goal, fixtures, native model, authority, deadlines and final
   independent oracles; compare the existing procedure with and without this builder.
2. **Expansion:** fixed known membership versus progressively revealed membership, with the
   same final required outcomes. Score missed/duplicate children, invalid proposals rejected,
   unnecessary decomposition, fan-out/depth/attempt control, and expansion overhead.
3. **Scheduling:** reuse one frozen plan and executor model; compare one worker at a time
   (concurrency 2 including coordinator) with a bounded parallel run. Include worktree setup,
   dispatch, waits, integration, checkers, cleanup, capture and coordinator/native overhead.

Use the repository's `evals/graph-workflow-builder/` cross-domain fixtures and independent
oracles: research/content, software repair, operational reconciliation. Capture failures,
refusals, unavailable hosts and unmeasured values; they never become successful runs or zeros.
Run at least three matched repeats per task/arm before assessing task benefit. Reserve held-out
goals and prompt variants; freeze rubric/model/source digests before comparing. Report per-case
results, failure rates and variability, not only pooled averages. Three repeats are a smoke
floor, not statistical proof. Calibrate subjective judges with human-rated examples and score
evidence/output quality without showing arm labels. The author does not grade its own output
uncritically.

Native routing evals and deterministic skill-text contracts establish selection/coverage, not
task benefit. Use only a subscription-qualified harness for model and judge calls. An existing
harness with a USD budget or an API path is not proof of subscription billing. Do not run it
until mode is confirmed; record it unavailable and use native fixture sessions when warranted.
Full-suite source checks establish regression coverage, not installed activation.

Persist private run evidence with restrictive permissions: source/graph/runner/model-map
digests, attempt token/native handle, exact base/commit, node and join verdicts, dynamic proposal
digest/revision, retry disposition, terminal status, effect reconciliation and cleanup/capture
state. Keep prompts, code, raw failures, paths, and worker handles out of aggregate exports.
Do not log raw chain-of-thought. A failed export remains pending until reconciled.

The runtime's `workflow-state.json` is private recovery state and its derived
`workflow-telemetry.json` contains opaque run IDs, digests, timestamped state events and exposed
worker usage. Unknown native tokens are null; coordinator/native orchestration usage and
subscription USD conversion are unavailable. Measure total wall time independently. Require an
explicit cost/quality improvement before changing model routes; existing decision-layer shadow
lanes remain shadow-only. No new telemetry service or recurring schedule is required.
