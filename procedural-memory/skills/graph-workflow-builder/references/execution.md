# Native execution and recovery

The scheduler is provider-free. It returns durable requests; the current Codex or Claude Code
harness dispatches, waits, cancels, and supplies evidence through its own subscription tools.
It is a cooperative host loop, not a background scheduler or an API transport. Never use
`graph run --native` for this schema: that flag belongs to the older API graph lane.

Before execution, verify host subscription mode and available models, worktree/wait/cancel
support, total capacity including this coordinator, permission scope, and root/base behavior.
Use Rhize parallel-agent-optimization when available for the host task graph and receipt;
otherwise perform those checks directly. No extra user-facing chat is needed for an internal
worker. Every worker owns one worktree, checks its actual root/HEAD, and returns one clean
checkpoint commit or its unchanged base. Keep durable worktrees under the project's
`.claude/worktrees/` or the user's durable worktree root; never /tmp.

Admission inputs are local JSON files:

- Model map: template name to exact native host model ID for every agent/expand template.
- Run params: absolute `repository`, full `base_sha`, absolute `worktree_root`, and
  `host_profile: {host: "codex"|"claude-code", billing: "subscription", worktrees: true,
  waiting: true, cancellation: true, concurrency: integer}`. These are verified host claims,
  not an independently attested operating-system sandbox.

Use CLI help for the normal graph lifecycle. `graph preflight NAME --model-map FILE --input
FILE` freezes the graph, runner source, models and run parameters. `graph run RUN_ID` or
`graph workflow RUN_ID --action advance` returns the next wave. The run's frozen runner
remains hash-checked on resume; changes to the current source do not silently change old runs.

For each **new** request:

1. Claim its token once in the native harness, use its actual worktree and admitted model,
   and bind the returned native thread handle immediately through
   `graph workflow RUN_ID --action bind --input bind.json`.
2. Wait for terminal evidence with bounded waits. Keep the coordinator responsive.
   On timeout, cancellation request, subscription quota, or exhausted budget, stop dispatch
   and settle native workers. A cancellation request is not cancellation proof.
3. Submit the exact terminal result through `--action accept --input result.json`.
   Advance again only after observing the updated state. Successful siblings can be retained
   after a required failure. Do not start blocked dependents.

Binding input is `{"token":"…","native_id":"…"}`. Terminal result fields are exactly:
`token, native_id, status, output, commit, usage, model`. Status is completed, failed, quota,
or cancelled; output is an object; usage is
`{"input_tokens":null,"output_tokens":null}` when unavailable. Model is the host-reported
selected identity, with backend attestation limitations kept in the private evidence.
For a completed result, commit must match the worktree's actual HEAD, remain descended from
the admitted base, contain only declared writes, and leave no uncheckpointed files. Writers
return one checkpoint commit per attempt. The coordinator integrates each checked commit,
then joins recheck the combined repository. Passing worker checks alone cannot finish a run.

## Reconciliation

| Condition | Required handling |
| --- | --- |
| Reload after dispatch claim, no native handle | Inspect the native host's existing workers; bind the existing one. Never blindly redispatch. If absence cannot be proved, hold. |
| Worker failure / rejected evidence | Preserve checkpoint and private result. `--action repair --node ID` only after settlement and within limits; supply the worker the prior failure evidence. Two identical failure digests stop repair. |
| Interrupted worktree setup | `--action reconcile` verifies or finishes the recorded setup at the exact base. It cannot launch a model. |
| Git committed before coordinator acknowledgement | Reconcile recorded parent and stable patch identity; resubmit the same result. Never cherry-pick a second time. |
| Conflicted integration | Preserve worker branches. Reconcile only a matching committed patch, or explicitly use `--action abort-integration` to capture conflict evidence and abort the recorded cherry-pick. Repair from the new integration base, then rerun final checks. |
| Capture/export failure | Retry capture/reconcile from durable state; do not replay already completed work. |
| Changed graph/approval/health, ambiguous effect, lost worktree | Hold and preserve evidence; obtain valid admission or an explicit disposition. |
| Elapsed deadline / late result | Record settlement and retain output privately; do not integrate it as timely success. |

After completion and capture, `--action cleanup` removes only clean owned worker worktrees.
The integrated result and checkpoint refs remain reviewable. Dirty/failed worktrees remain
until an explicit disposition. Git worktrees do not isolate credentials, ports, caches,
databases, or external services. Apply native host permissions and declared resource locks.
V1 automates local artifact/code integration only; externally mutating actions stay under their
existing approval and reconciliation workflows.
