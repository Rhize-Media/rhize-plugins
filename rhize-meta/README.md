# rhize-meta

Rhize Media's **meta-skills** plugin — the tools that manage the Rhize skill set itself. Commands
namespace as `/rhize-meta:<command>`.

## Skills

| Skill | What it does |
|-------|--------------|
| `rhize-skill-forge` | Investigate & absorb *external* skills (profile → decide → verify → provenance), plus the set-level organizer (capability registry, N-way overlap, dependency graph) |
| `skill-refinement` | Improve *your own* skills from usage feedback (patches + generalization) |

## Commands

`/rhize-meta:` forge-ingest · forge-scan · forge-watch · refine-skills · apply-generalization · review-patterns

## Install

```
/plugin marketplace add ~/dev-local/RHIZE/rhize-plugins
/plugin install rhize-meta@rhize-plugins
```

## Lineage

Promoted out of `rhize-devflow` (2026-06-15) so the coupled skill-governance toolchain lives in one
plugin. `rhize-skill-forge` consumes `skill-refinement`'s patch machinery for ABSORB; provenance is
tracked in `rhize-skill-forge/SOURCES.md`.
