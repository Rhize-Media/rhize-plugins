---
name: rhize-typed-decision
description: Use the project-local Jev or Laya typed decision client at GSD planning, execution, and verification checkpoints.
---

# Typed decision layer for GSD

At the start of each `gsd-planner`, `gsd-executor`, and `gsd-verifier` assignment, run a bounded typed decision through `.claude/rhize-decision/typed_decision.py`. Use only the current phase's summary, options, and evidence. Do not send secrets, source files, private customer data, or full PRDs to a hosted provider.

Write a temporary JSON request outside the repository, then pipe it to the project-local client. The `SubagentStart` hook supplies your `agent_id`; include it exactly so the `SubagentStop` hook can verify this agent's own call:

```bash
python3 "${CLAUDE_PROJECT_DIR}/.claude/rhize-decision/typed_decision.py" decide --project "${CLAUDE_PROJECT_DIR}" --checkpoint gsd-planner --agent-id "<agent_id from SubagentStart>" < "<temporary JSON request path>"
```

Use the matching checkpoint (`gsd-planner`, `gsd-executor`, or `gsd-verifier`). The request must follow Jev's `state` and named `questions` contract:

```json
{"state":"Short phase summary and relevant evidence","questions":{"next_step":{"type":"choice","criteria":{"proceed":"Evidence supports this plan or execution step","investigate":"A material uncertainty needs investigation","escalate":"Human or stronger-model judgment is required"}}}}
```

Read the JSON output. A recommendation is advisory; check it against the PRD, repo rules, tests, and human approval gates. If the response is unavailable or abstains, record the fallback in the phase notes and continue with the existing GSD judgment process. Never claim the decision layer ran if no receipt exists in `.planning/decision-layer/receipts.jsonl` for this checkpoint. Do not expose the API key in the request, logs, or GSD plan.
