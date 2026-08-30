---
name: context-pack
description: >-
  Build or verify a private, deterministic source-bound code context preview for a specific
  implementation, diagnosis, impact-analysis, or review task. Use when a bounded dependency-aware
  pack may reduce targeted reads without hiding critical contracts. Do not use for trivial lookups,
  highly dynamic code, automatic prompt injection, or as a replacement for exact source verification.
metadata:
  rhize:
    topics: [context-engineering, search]
    stacks: []
---

# Context pack

Use the self-relative launcher in `scripts/context-pack.sh`; it invokes the same host-neutral runner
from Claude Code and Codex. Build an explicit preview with one or more `--target` paths, or a bounded
`--query` when target discovery is actually needed:

```bash
scripts/context-pack.sh pack --provider native --repo /absolute/repo --target src/app.ts
scripts/context-pack.sh pack --provider native --repo /absolute/repo --query "account sync behavior"
scripts/context-pack.sh verify-pack --repo /absolute/repo --manifest /absolute/private/pack.json
```

Inspect `acceptedForUse`, `rejectionReasons`, every entry role/reason, and warnings. A safe pack may
contain FULL targets and parser-rendered INTERFACE dependencies. Unsupported class or syntax analysis
widens to FULL source; unresolved internal imports, dynamic edges, incomplete traversal, insufficient
benefit, or repository scan-budget overflow reject use visibly. Follow-up reads remain allowed and are
evidence of a pack miss.

An existing healthy `.codegraph/` index may expand targets and dependencies. Never initialize, sync,
or repair CodeGraph for this workflow. Without a healthy existing index, the provider records the
fallback and uses local Python/JavaScript/TypeScript resolution, including configured Python source
roots, JS/TS path aliases, package imports, workspaces, and package exports.

The manifest is source-free; repository-relative paths and bounded reason counts are retained for
inspection. Source-location details appear only in the private mode-`0600` prompt pack. Never publish
the prompt pack, treat estimated token reduction as task correctness, or inject it automatically.
Re-run verification immediately before reuse; any snapshot or source-hash drift requires a rebuild.
