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

## Compounding Persistence Layer (v2.4.0)

From the "self-improving agent system" pattern — no run is complete until it leaves the next run better prepared.

- **`agents/verifier.md`** — independent Haiku verifier (read-only: Read/Bash/Glob/Grep). `/done` delegates to it before any commit; verdicts PASS / FAIL_WITH_FIXABLE_GAPS / FAIL_REQUIRES_HUMAN. The maker never grades its own work.
- **STATE.md contract** — `/start` reads `STATE.md` (Verified facts · General rules · Open failures · Lessons learned · Last session) first; `/done` requires persisting at least one fact/failure/lesson back to it.
- **`hooks/protect-files.sh`** — OPT-IN PreToolUse gate (matcher `Edit|Write|MultiEdit|NotebookEdit`): blocks edits to `.github/workflows/*`, `.env*`, billing/payment paths, plus content gates for `NEXT_PUBLIC_*` secret-named vars and Supabase service-role references in `'use client'` files. Wire it into a project's `.claude/settings.json` like the other guard hooks.
- **`templates/hookify/`** — warn-level hookify rules for Next.js/Sanity repos (stop-checks, sanity-schema hint, seo hint, pr-review-on-create). Copy the relevant ones into a repo's `.claude/` as `hookify.<name>.local.md`.
- **`templates/rules/openwolf.md`** — canonical OpenWolf protocol rule (previously copy-pasted per repo, had drifted). Copy into `.claude/rules/` ONLY in repos that have a `.wolf/` directory.
