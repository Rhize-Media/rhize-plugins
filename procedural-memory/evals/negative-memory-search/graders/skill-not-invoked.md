---
name: skill-not-invoked
type: tool_used
tool: Skill
input_match: 'procedural-memory'
min: 0
max: 0
arm: both
---

"What did we discuss last week" is a past-conversation recall question — claude-mem's job, per
SKILL.md's own routing table ("Recall what happened in a past session/conversation" ->
claude-mem's search/recall skills, not this skill). The procedural-memory skill and its slash
commands must stay completely quiet here — `max: 0` fails the case if it fires at all, however
plausible the artifact-retrieval framing might look on the surface.

Manually confirmed correct on this exact prompt (2026-08-24, via `claude -p --plugin-dir`
against the real marketplace of competing plugins, since `claude plugin eval` itself is
org-gated here — see evals/README.md): the agent correctly used claude-mem ("Searching our
memory (claude-mem) for...") and never touched procedural-memory.
