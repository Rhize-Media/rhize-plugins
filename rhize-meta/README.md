# rhize-meta

Rhize Media's **meta-skills** plugin — the tools that manage the Rhize skill set itself. Commands
namespace as `/rhize-meta:<command>`.

## Skills

| Skill | What it does |
|-------|--------------|
| `rhize-skill-forge` | Investigate & absorb *external* skills (profile → decide → verify → provenance), plus the set-level organizer (capability registry, N-way overlap, dependency graph) |
| `skill-refinement` | Improve *your own* skills from usage feedback (patches + generalization) |

## Commands

`/rhize-meta:` forge-ingest · forge-scan · forge-watch · refine-skills · apply-generalization · review-patterns · skill-find · skill-doctor

## Install

```
/plugin marketplace add https://github.com/Rhize-Media/rhize-plugins
/plugin install rhize-meta@rhize-plugins
```

## Skill discovery & safety

`rhize-skill-forge` can **discover** skills (skills.sh) and **prove them safe** (NVIDIA SkillSpector)
before anything is adopted. Run `/rhize-meta:skill-doctor` to check setup.

- **Safety (SkillSpector) needs no Vercel.** Install once — `github.com/NVIDIA/skillspector`
  (Python 3.12+). Static scanning needs no API key; the optional LLM stage takes an OpenAI / Anthropic
  / NVIDIA key. This is the core, always-available gate (BLOCK on HIGH/CRITICAL).
- **Discovery (skills.sh) is optional** and authenticates with a **Vercel OIDC token**
  (`VERCEL_OIDC_TOKEN`). Team setup: one empty Vercel project with OIDC Federation enabled as an
  *auth anchor* (it deploys nothing), then `vercel link` + `vercel env pull` per developer. Clients
  without Vercel keep the safety gate; discovery is opt-in. Rationale + the client model:
  vault `ADR-001-skills-sh-vercel-auth`.

## Lineage

Promoted out of `rhize-devflow` (2026-06-15) so the coupled skill-governance toolchain lives in one
plugin. `rhize-skill-forge` consumes `skill-refinement`'s patch machinery for ABSORB; provenance is
tracked in `rhize-skill-forge/SOURCES.md`.
