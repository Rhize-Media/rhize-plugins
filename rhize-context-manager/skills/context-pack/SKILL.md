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
scripts/context-pack.sh verify-pack --repo /absolute/repo \
  --manifest /absolute/private/pack.json --prompt /absolute/private/pack.md
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

## Optional local Laya relevance shadow

Set `RHIZE_LAYA_GRAPH_SHADOW=1` and pass a redacted one-line `--decision-task` on a native `pack` call to score up to eight already selected entries. The runner first verifies the exact pack against current source, then asks the pinned local `typed-decisions` checkpoint about candidate metadata. It writes an immutable private mode-0600 `.relevance.<id>.json` receipt and returns `decisionShadow` with Arm A inclusion, ranked scores, latency, usage, source snapshot and model route. A stale/rejected pack, model error, or missing task summary returns unavailable without changing the pack or existing fallback. Scores do not exclude required targets, alter CodeGraph, or establish context recall. Use human-adjudicated relevance labels and accepted-task follow-up reads for evaluation.

```bash
RHIZE_LAYA_GRAPH_SHADOW=1 TYPESAFE_DEFAULT_MODEL=typed-decisions scripts/context-pack.sh pack \
  --provider native --repo /absolute/repo --query "account sync behavior" \
  --decision-task "Implement account synchronization safely"
```
