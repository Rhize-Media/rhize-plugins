# rhize-devflow

Rhize Media's development-workflow plugin — the consolidated home for the skills that used to live
in the standalone `CLAUDE-SKILLS` repo (now archived). Everything namespaces as
`rhize-devflow:<skill>` and `/rhize-devflow:<command>`.

## Skills

| Skill | What it does |
|-------|--------------|
| `context-engineering` | Session/memory lifecycle, context hygiene, impact mapping |
| `error-lifecycle-management` | Production error triage, RCA, Sentry↔Vercel deploy correlation |
| `data-mutation-consistency` | Cache-tag ↔ query-key alignment across Next.js/Sanity/Payload/Supabase |
| `sentry-instrumentation` | Rhize conventions for captureException, spans, structured logging |
| `chrome-devtools-mcp` | Browser automation, perf traces, network/console debugging |
| `sanity-development` | Rhize house style for Sanity schema/GROQ/TypeGen/next-sanity |
| `dev-flow-foundations` | Dependency graphs, component registry, regression prevention |

> The `skill-refinement` and `rhize-skill-forge` meta-skills moved to the **`rhize-meta`** plugin (2026-06-15).

## Commands

`/rhize-devflow:` start · done · impact-map · context-hygiene · mutation-analyze · mutation-check ·
mutation-fix · browser-debug · browser-help · browser-perf · browser-test

## Install

```
/plugin marketplace add ~/dev-local/RHIZE/rhize-plugins
/plugin install rhize-devflow@rhize-plugins
```

## Hooks

A light SessionStart banner is enabled by default. The heavier guard hooks (duplicate-check,
prewrite mutation check, RCA enforcer, regression guard) ship bundled under `hooks/` and inside
each skill but are **opt-in** — wire them into a project's `.claude/settings.json` when you want
them, so nothing untested fires automatically.

## Lineage

Migrated from `~/dev-local/CLAUDE-SKILLS` (archived 2026-06). The `rhize-skill-forge` and
`skill-refinement` meta-skills were promoted to the `rhize-meta` plugin (2026-06-15).
