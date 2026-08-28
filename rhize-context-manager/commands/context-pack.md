---
description: Build and inspect a private, source-bound context pack without injecting it
model: sonnet
---

# /context-pack

Build a deterministic preview. The default `native` provider is local-only and supports Python,
JavaScript, TypeScript, and mixed-language repositories. It selects FULL targets, INTERFACE
dependencies, related tests, and nearby configuration under a declared token budget. The pinned
upstream Python Context Compiler remains available for reproduction of the Phase 3 evidence.

Resolve the runner from the installed plugin root and use one of these forms:

```bash
# Native provider with an explicit target (repeat --target for a mixed-language task)
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/context_experiments/runner.py" pack \
  --provider native \
  --repo /absolute/path/to/repository \
  --target src/app.ts

# Native target discovery. If .codegraph/ exists, CodeGraph is tried first; otherwise the
# provider uses its deterministic baseline discovery and records that strategy.
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/context_experiments/runner.py" pack \
  --provider native \
  --repo /absolute/path/to/repository \
  --query "implement the account synchronization behavior"

# Pinned upstream Python comparison
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/context_experiments/runner.py" pack \
  --provider upstream-python \
  --repo /absolute/path/to/repository \
  --target module.py
```

The preview never arms an experiment, injects context, or records a completed receipt. Inspect
`acceptedForUse`, every entry's role/reason, and all warnings before opening the private prompt.
Dynamic dependency edges, ambiguous targets, unsupported syntax, or a required target outside the
budget reject use. Optional budget truncation remains visible even when the required pack is safe.

Both manifest and prompt are mode `0600` under
`~/.claude/rhize-context-manager/experiments/packs/` by default. The manifest contains hashes and
repository-relative paths, never source text or an absolute repository path. Verify a native pack
immediately before reuse:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/context_experiments/runner.py" verify-pack \
  --repo /absolute/path/to/repository \
  --manifest /absolute/path/to/pack.json
```

Any source edit or snapshot change makes verification fail and requires recompilation. Repeating
an unchanged request reuses the same immutable pack ID.

When the opt-in selector is explicitly armed for `compiledContext`, it runs this native provider
on the next eligible prompt. A rejected discovery stays silent and does not consume the arm. An
accepted pack is built before discovery, its path is added to the session, and the Stop hook writes
an Arm A/B receipt. The receipt deliberately warns that task correctness and follow-up reads still
require human review; estimated token reduction is not an adoption decision by itself.
