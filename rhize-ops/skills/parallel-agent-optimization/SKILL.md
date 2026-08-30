---
name: parallel-agent-optimization
tier: custom
domain: ops
maturity: sapling
provenance: parallel-agent-optimization
description: |
  Required whenever parallel or multi-agent work is mentioned, discussed, proposed, planned, reviewed, benchmarked, optimized, or employed—including subagents, agent dispatch, concurrent agents, or delegation to multiple agents. Invoke before spawning or dispatching any agent. Use `assess` for discussion or planning without execution or receipts. For real work, apply Rhize's self-contained routing strategy when two or more genuinely independent, bounded lanes justify the coordination cost; otherwise choose sequential or gated execution. Comparisons evaluate baseline versus Rhize routing only in isolated replayable fixtures.
metadata:
  rhize:
    topics: [automation, observability, workflow-patterns]
    stacks: [testing]
---

# Parallel Agent Optimization

Choose the smallest safe execution graph, give every lane a bounded contract, and verify the joined
result. This is the self-contained Rhize strategy; do not load another parallel-agent skill at
runtime.

Read [references/modes.md](references/modes.md) before execution. For a non-trivial dispatch, also
read [references/task-graph-contract.md](references/task-graph-contract.md) and validate the ephemeral
graph with `scripts/validate_task_graph.py` before dispatch. Read
[references/receipt-contract.md](references/receipt-contract.md) before recording evidence.
[references/provenance.md](references/provenance.md) records the authorized upstream consolidation
and the update-review boundary. Resolve the canonical plugin root through the current host's skill
discovery, then set a process-local `RHIZE_OPS_ROOT` for the examples below. In Claude Code that
root is `CLAUDE_PLUGIN_ROOT`; in Codex it is the root containing the discovered skill and
`.codex-plugin/plugin.json`.

## Required trigger

Invoke this skill whenever parallel agents are part of the conversation or execution, even when the
user does not name it. Discussion-only requests use `assess` and create no receipt. Before the
first dispatch, classify dependencies, declare lane ownership and protected state, name the join
point, and assign final verification to the coordinator.

Host authorization and agent-tool policy still apply. This skill never creates permission to
dispatch agents, mutate external state, commit, push, merge, deploy, or bypass an approval gate.

## Non-negotiable boundaries

- Never duplicate a live task to create evidence. Real work uses `apply` once.
- Never run controlled arms against production, shared external state, the current checkout, or an irreversible action.
- Enforce one writer per checkout. Isolate concurrent writers in separate worktrees or copies with non-overlapping territories.
- Keep dependency chains, shared mutable state, approval gates, integration, and final interpretation sequential.
- Stop or replan dependent lanes when a discovered blocker invalidates their inputs.
- Poll dispatched work deliberately; do not let a background process outlive the turn unless the user requested a continuing service.
- Telemetry must not contain prompts, code, commands, paths, project/user/agent/host names, URLs, session/thread IDs, or issue IDs.
- Prove concurrency from overlapping intervals, never from agent count.
- Leave unavailable tool and token counts null with an allowed reason; never estimate them.
- Keep observational, v2 controlled, and legacy-v1 screening evidence separate.

## Modes

Interpret `$ARGUMENTS` using this grammar:

```text
assess <parallel-agent question or candidate task>
apply <task>
compare <replayable task or fixture>
report [observational|controlled|all]
audit-pending
```

### Assess

Classify the task using `references/modes.md`. State objective and done signal, proposed lanes,
dependencies, write boundaries, protected state, join point, and verification owner. Do not dispatch
agents, reserve a run, or write a receipt.

### Apply

Run the Rhize strategy exactly once on the real task. First render the bounded nodes, dependencies,
read/write territories, resource capacities, authority gates, output contracts, and
coordinator-owned verification into an ephemeral graph. Supply a verified-or-unknown Claude Code
or Codex host profile and validate it before dispatch. Unknown concurrency degrades to sequential
guidance; an unordered write collision, conflicting resource declaration, missing coordinator
slot, invalid retry, or incomplete authority gate fails before dispatch. The host remains the
scheduler and executor:

```bash
python3 "${RHIZE_OPS_ROOT}/skills/parallel-agent-optimization/scripts/validate_task_graph.py" \
  validate --graph /private/path/to/task-graph.json \
  --capabilities /private/path/to/host-capabilities.json
```

After validation and before work, reserve the observational run:

```bash
python3 "${RHIZE_OPS_ROOT}/skills/parallel-agent-optimization/scripts/parallel_metrics.py" \
  begin --input /private/path/to/privacy-safe-begin.json
```

Use the returned random `run_id`. In a `finally` path, finalize it as `completed`, `failed`, or
`incomplete`; never silently abandon an accepted run. If the normal result cannot be captured,
finalize the known partial facts as `incomplete` rather than inventing counts.

### Compare

Use only when the user explicitly requests comparison and a deterministic fixture can be replayed
without live effects. Create a two-arm counterbalanced reservation:

```bash
python3 "${RHIZE_OPS_ROOT}/skills/parallel-agent-optimization/scripts/parallel_metrics.py" new-comparison
```

Run `baseline` and `rhize` sequentially in the reserved order, each in a fresh environment from the
same seed. Baseline uses standing host/task instructions; Rhize uses this strategy. Use identical
checks, reserve and finalize each arm, and never convert archived ECC/Superpowers smoke into v2.

### Report and audit

```bash
python3 "${RHIZE_OPS_ROOT}/skills/parallel-agent-optimization/scripts/parallel_metrics.py" \
  report --evidence all --format markdown
python3 "${RHIZE_OPS_ROOT}/skills/parallel-agent-optimization/scripts/parallel_metrics.py" \
  audit-pending
```

Report required readiness metrics separately from optional token/tool coverage. Treat stale pending
reservations as evidence failures requiring factual terminal finalization, not as completed runs.

## Finish every execution

1. Validate every required result and output contract. Missing/failed required results or cleanup
   failures block synthesis; optional omissions remain visible. Use bounded hierarchical fan-in when
   the graph's item budget requires it.
2. Verify the task with the predeclared checks.
3. Finalize the accepted reservation with receipt v2's aggregate task-graph counts and factual
   terminal status. Never persist the graph, node ids, descriptions, paths, or raw outputs. Receipt
   validation failure is a visible run failure; fix the structured input rather than weakening the
   schema.
4. Report terminal status, routing decision, actual overlap, verification, collisions/rework, and
   missing optional coverage.
5. For controlled evidence, compare only matched v2 baseline/Rhize receipts that satisfy the same
   fixture contract. Do not treat observational medians as causal evidence.
