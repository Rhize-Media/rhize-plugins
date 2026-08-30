---
description: Preview, apply, inspect, or rebuild evidence-bound compiled vault knowledge
allowed-tools: ["Bash", "Read"]
argument-hint: preview|apply|status|rebuild [arguments]
---

Use the canonical `knowledge-compiler` skill for `$ARGUMENTS`. This command is a thin Claude Code
adapter: load that skill, preserve its approval and privacy boundaries, and invoke the shared
`scripts/compiled_knowledge.py` implementation. Do not implement compilation in the command prompt.

For `preview`, show the named preview's change brief and exact diff. For `apply`, require explicit
approval of that preview id in the current conversation before invoking the mutation. `status`
never authors new compiled content; after an interrupted authorized apply, it may restore the
journaled pre-transaction bytes before reporting. `rebuild` creates a new preview and never applies
it. Scheduled or automatic apply is not available.
