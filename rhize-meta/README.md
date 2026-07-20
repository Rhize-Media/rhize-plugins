# rhize-meta

Rhize Media's **meta-skills** plugin — the tools that manage the Rhize skill set itself. Commands
namespace as `/rhize-meta:<command>`.

## Skills

| Skill | What it does |
|-------|--------------|
| `skill-refinement` | Improve *your own* skills from usage feedback (patches + generalization) |

## Commands

`/rhize-meta:` refine-skills · apply-generalization · review-patterns

## Install

```
/plugin marketplace add https://github.com/Rhize-Media/rhize-plugins
/plugin install rhize-meta@rhize-plugins
```

## Skill vetting moved

Investigating and absorbing *external* skills or MCP servers — profiling, safety scanning, overlap
analysis, provenance tracking, discovery, and drift-watching — now lives in the `@rhize/skill-forge`
npm package: `npx @rhize/skill-forge` (commands: `add`, `scan`, `find`, `ingest`, `watch`,
`organize`, `audit`, `evolve`). `rhize-meta` here only refines skills you already own.

## Lineage

Promoted out of `rhize-devflow` (2026-06-15) so the coupled skill-governance toolchain lived in one
plugin. The external-skill-absorption half was retired from this plugin (2026-07-20) once its
functionality was fully ported to the `@rhize/skill-forge` npm package — see "Skill vetting moved"
above.
