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
  Choose whether a task should use parallel agents, run one bounded execution strategy, and record privacy-safe evidence. Use when the user invokes `/rhize-ops:parallel-optimize`, asks to optimize parallel-agent execution, wants to benchmark ECC versus Superpowers versus the Rhize policy, or wants a controlled comparison of parallel-agent approaches. Ordinary work runs exactly one strategy and records observational evidence; multi-arm comparisons are explicit, isolated, replayable, and never duplicate a live task. Never load ECC and Superpowers together for one arm.
metadata:
  rhize:
    topics: [automation, observability, workflow-patterns]
    stacks: [testing]
---

# Parallel Agent Optimization

Use the smallest safe execution shape for the task, then record enough structured evidence to learn from the run without retaining task content.

Read [references/modes.md](references/modes.md) before choosing or executing a mode. Read [references/receipt-contract.md](references/receipt-contract.md) before recording or reporting evidence. [references/provenance.md](references/provenance.md) records the two maintained dependencies and Forge decision. The deterministic helper is `scripts/parallel_metrics.py` relative to this skill directory.

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
apply [--variant baseline|ecc|superpowers|rhize] <task>
compare <replayable task or fixture>
report [observational|controlled|all]
```

A bare task means `apply <task>`.

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
