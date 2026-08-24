# Skill Foundations Index

> **Status:** Stable — reference layer for `dev-flow-foundations`
> **Primary entry point:** [SKILL.md](SKILL.md) (routing table, interconnection diagram,
> and the mapping from each foundation to its executable command)

This file is a secondary, quick-reference index over the six foundation documents. Read
[SKILL.md](SKILL.md) first — it owns the authoritative mapping to `/rhize-devflow:impact-map`,
`/rhize-devflow:check`, and `/rhize-devflow:review`.

## Pain Points → Foundation Documents

| Pain Point | Primary Foundation | Supporting Foundation |
|------------|---------------------|------------------------|
| Incomplete implementations across files | Dependency Graph | Component Registry |
| Code duplication | Component Registry | Anti-Pattern Agent |
| Outdated documentation | Context Hygiene | Skill Refinement |
| Context window exhaustion | Context Hygiene | — |
| Circular debugging | Regression Prevention | Skill Refinement |
| Anti-patterns slipping through | Anti-Pattern Agent | Skill Refinement |

## Foundation Documents

| File | Purpose | Executable workflow it feeds |
|------|---------|-------------------------------|
| [SKILL-dependency-graph-v1.md](SKILL-dependency-graph-v1.md) | Impact analysis before implementation | `/rhize-devflow:impact-map` |
| [SKILL-component-registry-v1.md](SKILL-component-registry-v1.md) | Living component/hook/utility index, reuse-first | context-engineering duplicate-check hook |
| [SKILL-context-hygiene-v1.md](SKILL-context-hygiene-v1.md) | Documentation and session-boundary management | `/rhize-context-manager:start` / `:done` |
| [SKILL-regression-prevention-v1.md](SKILL-regression-prevention-v1.md) | Root-cause analysis and fix verification | `/rhize-devflow:check`, `/rhize-devflow:review` |
| [SKILL-anti-pattern-agent-v1.md](SKILL-anti-pattern-agent-v1.md) | Deprecated-pattern detection at write-time | error-lifecycle-management validation scripts |
| [SKILL-refinement-meta-v1.md](SKILL-refinement-meta-v1.md) | Capture and formalize patterns discovered during work | `/rhize-context-manager:skill-refine` |

## Foundation Interconnections

See [SKILL.md § Interconnections](SKILL.md#interconnections) for the current diagram — this
file does not duplicate it to avoid drift between two copies.

## Using These Documents

**For learning:** read a foundation to understand the "why" behind a workflow pattern before
using the command that implements it.

**For implementation:** the commands and hooks listed in the table above are the executable
surface; these documents are reference guidance for how to use them well, not a replacement
for them.

**For iteration:** if a pattern in one of these documents stops matching real usage, update the
document in the same change that changes the behavior — do not let guidance drift from the
commands it describes.
