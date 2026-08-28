---
name: parallel-agent-optimization
tier: custom
domain: ops
maturity: seedling
consumes:
  - ecc:parallel-execution-optimizer
  - superpowers:dispatching-parallel-agents
provenance: parallel-agent-optimization
description: |
  Required whenever parallel or multi-agent work is mentioned, discussed, proposed, planned, reviewed, benchmarked, optimized, or employed—including subagents, agent dispatch, concurrent agents, or delegation to multiple agents. Invoke before spawning or dispatching any agent. Use `assess` for discussion or planning without execution or receipts. For real work, prefer parallel execution when two or more genuinely independent, bounded lanes justify the coordination cost; otherwise choose sequential or gated execution. Ordinary work runs exactly one strategy and records observational evidence; comparisons are explicit, isolated, and replayable. Never duplicate a live task or load ECC and Superpowers together for one arm.
metadata:
  rhize:
    topics: [automation, observability, workflow-patterns]
    stacks: [testing]
---

# Parallel Agent Optimization

Use the smallest safe execution shape for the task, then record enough structured evidence to learn from the run without retaining task content.

Read [references/modes.md](references/modes.md) before choosing or executing a mode. Read [references/receipt-contract.md](references/receipt-contract.md) before recording or reporting evidence. [references/provenance.md](references/provenance.md) records the two maintained dependencies and Forge decision. The deterministic helper is `scripts/parallel_metrics.py` relative to this skill directory.

## Required trigger and default

Invoke this skill whenever parallel agents are part of the conversation or execution, even when the
user does not name this skill or command. This includes discussing whether parallel agents would
help, proposing or reviewing a multi-agent plan, mentioning subagents or agent dispatch, delegating
independent lanes to multiple agents, and actually spawning or managing agents. Invoke it before the
first dispatch so lane ownership and protected state are declared up front.

The invocation requirement is broader than the decision to parallelize. Discussion-only requests
use `assess` and create no receipt. For execution, parallel agents are the default when there are at
least two genuinely independent, bounded lanes; their inputs and outputs are clear; writes are
read-only, disjoint, or isolated; the host supports agent dispatch; and the likely gain exceeds
coordination overhead. If any condition fails, choose sequential or gated execution and say why.
Host-level authorization and agent-tool policies still apply; this skill does not create permission
to dispatch agents where the active environment forbids it.

## Non-negotiable boundaries

- Never duplicate a live task to create a benchmark. A live/current-worktree request may use only `apply` mode.
- Never run controlled arms against production, shared external state, the user's current checkout, or an irreversible action.
- Never load `ecc:parallel-execution-optimizer` and `superpowers:dispatching-parallel-agents` in the same arm. The Rhize arm selects at most one of them.
- Enforce one writer per checkout. Multiple writing agents require isolated worktrees or copies with declared, non-overlapping territories. The coordinator alone integrates results.
- Parallelize only independent work. Dependency chains, shared mutable state, approval gates, and final integration stay sequential.
- Telemetry must not contain prompts, code, command text, repository or file paths, project names, user names, agent names, host names, session/thread IDs, issue IDs, URLs, or free text.
- Do not infer parallelism from agent count. It occurred only when agent time intervals overlapped.
- Missing token or tool counts stay missing with an allowed reason; never estimate them.
- Keep observational and controlled evidence separate in storage and reports. Never pool them into one score.

## Mode selection

Interpret `$ARGUMENTS` using this grammar:

```text
assess <parallel-agent question or candidate task>
apply [--variant baseline|ecc|superpowers|rhize] <task>
compare <replayable task or fixture>
report [observational|controlled|all]
```

A discussion or planning request means `assess`. A bare task that asks to execute work means
`apply <task>`.

### Assess

Decide whether parallel agents are appropriate using the classification and eligibility rules in
`references/modes.md`. State the proposed lanes, dependencies, write boundaries, protected state,
join point, and verification owner. Do not dispatch agents, run a candidate strategy, assign an
observational variant, or write a receipt. If execution follows in the same request, complete the
assessment first and then continue in `apply` mode.

### Apply

Run exactly one strategy on the actual task. If `--variant` is absent, ask the helper for the least-used observational variant:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/parallel-agent-optimization/scripts/parallel_metrics.py" assign
```

This balancing is exploratory assignment, not randomization and not controlled evidence. Tell the user which variant was assigned before executing it. Follow the selected arm contract in `references/modes.md`, finish the task, verify it, and append one observational receipt.

If the selected external skill is unavailable, do not imitate or copy it. Continue with the safety envelope, record `resource_used: none`, and disclose the degraded run.

### Compare

Use only when the user explicitly requests comparison and the work can be replayed in isolated disposable environments with predeclared checks. If those conditions are absent, stop the comparison and explain what fixture or safe replay boundary is needed; do not downgrade the same live task into repeated arms.

Create a comparison ID and counterbalanced arm order:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/parallel-agent-optimization/scripts/parallel_metrics.py" new-comparison
```

Before generating it, confirm both upstream resource skills are installed and callable. If either
is missing, stop without writing controlled receipts; a degraded `resource_used: none` run is valid
only for observational `apply`, not as evidence about an unavailable candidate.

Run `baseline`, `ecc`, `superpowers`, and `rhize` as separate arms in the returned order. Use a fresh worktree/copy for every arm, run arms sequentially so their elapsed times do not compete for the same machine, and apply the same task input and checks to each. Never add a combined ECC+Superpowers arm. Record one controlled receipt per arm with the shared comparison ID.

### Report

Render stored results without running a task:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/parallel-agent-optimization/scripts/parallel_metrics.py" report --evidence all --format markdown
```

Pass the requested evidence class when specified. Present the two evidence classes separately and state coverage gaps, especially unavailable token/tool counts or incomplete verification.

## Finish every execution

1. Verify the task with the predeclared checks.
2. Record the outcome using the strict receipt contract. Receipt validation failure is a visible run failure; fix the structured input rather than weakening the schema.
3. Report the variant, resource actually used, whether work truly overlapped, verification completeness, collisions/rework, and the evidence class.
4. For controlled comparisons, compare only matched arms sharing a comparison ID. Do not treat observational medians as causal evidence.
