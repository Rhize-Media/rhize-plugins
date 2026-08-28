# Provenance — parallel-agent-optimization

The machine-readable Forge ledger entry is `../../SOURCES.md#parallel-agent-optimization--2026-08-27`.
This file explains that entry without replacing it.

| Field | Value |
| --- | --- |
| Forge decision | DEFER+wrap, recorded as DEFER; no upstream code or prose copied |
| Decision date | 2026-08-27 |
| Human gate | Confirmed before implementation |
| Investigation | RT-129 and `.claude/plans/parallel-agent-skill-forge-investigation.md` |
| Controlled smoke | `evals/parallel-agent-skills/` |
| Graph semantics | `consumes` in the Forge ledger plus two `depends-on` relations; never `fork-of` |

## Consumed resources

1. `ecc:parallel-execution-optimizer`
   - Installed baseline: ECC 2.2.0
   - Source: https://github.com/affaan-m/ECC/tree/main/skills/parallel-execution-optimizer
   - License: MIT
   - Use: optional dependency-graph and lane-planning resource
2. `superpowers:dispatching-parallel-agents`
   - Installed baseline: Superpowers 6.3.0
   - Source: https://github.com/obra/superpowers/tree/main/skills/dispatching-parallel-agents
   - License: MIT
   - Use: optional focused independent-domain dispatch resource

Rhize owns only the apply-versus-compare mode split, safety envelope, one-writer rule, routing policy,
privacy-safe receipt schema, and observational-versus-controlled evidence separation. The upstream
skills remain installed dependencies. They are not vendored, paraphrased into replacements, or
loaded together in one arm.

## Drift boundary

The existing `ai-stack-version-drift` Forge/AI-stack routine is the sole version sensor. When it
reports movement in either installed plugin, rerun the isolated comparison harness before changing
this wrapper. Do not add a separate scheduler.
