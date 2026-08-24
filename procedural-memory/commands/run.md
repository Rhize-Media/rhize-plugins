---
description: Execute a promoted procedural-memory registry artifact by name — registry-only resolution, content-digest check, trust gate, health gate
argument-hint: <artifact-name> [args...] [--offline]
allowed-tools: Bash
---

Execute a procedural-memory registry artifact: $ARGUMENTS

Run:

    ${CLAUDE_PLUGIN_ROOT}/scripts/rhize-skill-launcher.sh run $ARGUMENTS

This resolves the artifact from the registry only (never an arbitrary filesystem path),
recomputes its content digest transitively over anything it pins, and refuses if trust or
health don't clear the gate.

**Never add `--approve-unreviewed` on the user's behalf.** It is a one-shot bypass of the trust
gate for that single invocation and is the user's call, not this command's — if they want a
durable, revocable authorization instead, point them at `rhize-skill approve <name>` (not
wrapped by a slash command here; run it directly via Bash if they ask for it).

If the CLI refuses, show its refusal message verbatim — it names the exact reason (trust,
digest mismatch, degraded/missing/corrupt health) and the remediation command. Don't retry with
a bypass flag or a different invocation shape.
