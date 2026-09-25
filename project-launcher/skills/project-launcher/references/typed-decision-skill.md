---
name: rhize-typed-decision
description: Use the project-local Jev or Laya typed decision client at GSD planning, execution, and verification checkpoints.
---

# Typed decision layer for GSD

Planner checks also cover skill/workflow fit, graph context relevance and retention
safety. Executor checks include authorized model/worker fit and tool trace risk;
verifier checks include browser QA coverage. All remain observational and use the
same single bounded call per agent checkpoint. See
[the full pilot](../../../../docs/typed-decision-layer.md).

At a meaningful checkpoint in each `gsd-planner`, `gsd-executor`, and `gsd-verifier` assignment, run the fixed, bounded supervision questions through `.claude/rhize-decision/typed_decision.py`. Use only the current phase's summary and evidence. Do not send secrets, source files, private customer data, or full PRDs to a hosted provider.

Write a temporary JSON evidence object outside the repository, then pipe it to the project-local client. The `SubagentStart` hook supplies your `agent_id`; include it exactly so the `SubagentStop` hook can verify this agent's own call:

```bash
python3 "${CLAUDE_PROJECT_DIR}/.claude/rhize-decision/typed_decision.py" supervise --project "${CLAUDE_PROJECT_DIR}" --checkpoint gsd-planner --agent-id "<agent_id from SubagentStart>" < "<temporary JSON evidence path>"
```

Use the matching checkpoint (`gsd-planner`, `gsd-executor`, or `gsd-verifier`). Summarize bounded evidence, including actual check and review status where known:

```json
{"phase":"verification","summary":"Short phase summary and relevant evidence","required_checks_passed":true,"independent_review_passed":false}
```

The client sends fixed Foreman-style questions for the current agent: plan coverage and uncertainty; implementation progress, stuckness and drift; or completion, test sufficiency and verification need. It returns a `candidate_directive` for measurement. This directive does not execute any worker action or approve completion. Check it against the PRD, repo rules, tests, and human approval gates. If the response is unavailable, record the fallback in phase notes and continue with existing GSD judgment. Never claim the layer ran without this agent's receipt in `.planning/decision-layer/receipts.jsonl`. Do not expose an API key in the state, logs, or GSD plan. The generic `decide` command remains available for explicitly defined choice questions and requires a nonempty `instructions` string on each question.
