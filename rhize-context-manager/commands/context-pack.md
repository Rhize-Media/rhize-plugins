---
description: Build and inspect a private, source-bound context pack without injecting it
model: sonnet
---

# /context-pack

Build a deterministic preview. The default `native` provider is local-only and supports Python,
JavaScript, TypeScript, and mixed-language repositories. It selects FULL targets, INTERFACE
dependencies, related tests, and nearby configuration under a declared token budget. The pinned
upstream Python Context Compiler remains available for reproduction of the Phase 3 evidence.

Use the canonical `context-pack` skill. This Claude command is only a thin adapter over its
self-relative launcher:

```bash
# Native provider with an explicit target (repeat --target for a mixed-language task)
"${CLAUDE_PLUGIN_ROOT}/skills/context-pack/scripts/context-pack.sh" pack \
  --provider native \
  --repo /absolute/path/to/repository \
  --target src/app.ts

# Native target discovery. A healthy existing CodeGraph is tried first; otherwise the
# provider uses deterministic rg discovery and records that strategy.
"${CLAUDE_PLUGIN_ROOT}/skills/context-pack/scripts/context-pack.sh" pack \
  --provider native \
  --repo /absolute/path/to/repository \
  --query "implement the account synchronization behavior"

# Optional semantic bridge from a repository-local impact-map/plan. The manifest records
# content/term hashes and a seed count, never the plan path or text.
"${CLAUDE_PLUGIN_ROOT}/skills/context-pack/scripts/context-pack.sh" pack \
  --provider native \
  --repo /absolute/path/to/repository \
  --query "implement the account synchronization behavior" \
  --impact-map /absolute/path/to/repository/.claude/plans/account-sync.md

# Pinned upstream Python comparison
"${CLAUDE_PLUGIN_ROOT}/skills/context-pack/scripts/context-pack.sh" pack \
  --provider upstream-python \
  --repo /absolute/path/to/repository \
  --target module.py
```

The preview never arms an experiment, injects context, or records a completed receipt. Inspect
`acceptedForUse`, every entry's role/reason, and all warnings before opening the private prompt.
Dynamic dependency edges, ambiguous targets, unsupported syntax, or a required target outside the
budget reject use. Optional budget truncation remains visible even when the required pack is safe.
An impact map expands discovery but never converts a planned edge into structural fact: dynamic,
generated, or unsupported edges still reject the pack and require targeted `rg`/manual evidence.

Both manifest and prompt are mode `0600` under the configured private context data root. The
manifest contains hashes and
repository-relative paths, never source text or an absolute repository path. Verify a native pack
immediately before reuse:

```bash
"${CLAUDE_PLUGIN_ROOT}/skills/context-pack/scripts/context-pack.sh" verify-pack \
  --repo /absolute/path/to/repository \
  --manifest /absolute/path/to/pack.json \
  --prompt /absolute/path/to/pack.md
```

Any source edit, snapshot change, manifest edit, or prompt edit makes verification fail and requires
recompilation. Repeating
an unchanged request reuses the same immutable pack ID.

When the opt-in selector is explicitly armed for `compiledContext`, it runs this native provider
on the next eligible prompt. A rejected discovery stays silent and does not consume the arm. An
accepted pack is built before discovery, its path is added to the Claude Code session, and the Stop
hook writes an Arm A/B receipt. Codex uses this same native provider through explicit skill/runner
invocation; it does not auto-run the Claude hook lifecycle. The receipt deliberately warns that task
correctness and follow-up reads still require human review; estimated token reduction is not an
adoption decision by itself.
