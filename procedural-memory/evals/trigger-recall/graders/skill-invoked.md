---
name: skill-invoked
type: tool_used
tool: Skill
input_match: 'procedural-memory'
min: 1
---

For "is there already a proven tool for X, check before building from scratch" — exactly the
skill's own trigger phrase ("has this been automated before") — the procedural-memory skill (or
one of its slash commands) must actually be invoked, not just discussed. This is the trigger-
accuracy half of the pair with evals/negative-memory-search and evals/negative-generic-task.

Manually confirmed correct on this exact prompt (2026-08-24, via `claude -p --plugin-dir`
against a live registry, since `claude plugin eval` itself is org-gated here — see
evals/README.md): recall found `n8n-safe-deploy@1.0.0` and correctly reported
trust=unreviewed/health=degraded/success_rate=0%, declining to recommend running it.
