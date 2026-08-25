---
name: skill-not-invoked
type: tool_used
tool: Skill
input_match: 'procedural-memory'
min: 0
max: 0
arm: both
---

A trivial, one-off task with an obvious, cheap native solution should never trigger a registry
lookup — recall has real cost (an embedding query against Postgres) and the skill's own
description scopes it to tasks that plausibly have already been solved and captured, not
anything a task-shaped sentence could describe. This is the "don't over-fire" companion to
evals/negative-memory-search's "don't fire for a different domain."

Manually confirmed correct on this exact prompt (2026-08-24, via `claude -p --plugin-dir`,
since `claude plugin eval` itself is org-gated here — see evals/README.md): the agent answered
directly with `rev`/bash one-liners and never touched procedural-memory.
