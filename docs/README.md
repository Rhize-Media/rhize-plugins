# docs/

Cross-plugin reference material for maintainers — mechanics that span more than one plugin, or
predate the current plugin split. Each plugin's own day-to-day documentation stays beside it: its
`README.md` (setup and technical reference) and `GUIDE.md` (how to actually use it day-to-day).

## Plugins

<!-- SKILL-MAP:BEGIN -->
### seo-aeo-geo

Version 1.5.1. Audits and improves how a website ranks in search engines and shows up in AI answers like ChatGPT and Google AI Overviews, using live search data — for SEO practitioners, content teams, marketers, and developers.

[README](../seo-aeo-geo/README.md) · [GUIDE](../seo-aeo-geo/GUIDE.md) · [7 skills](../generated/SKILL-CATALOG.md#seo-aeo-geo)

### obsidian-second-brain

Version 1.7.1. Teaches Claude to read, write, organize, and search notes in your Obsidian vault — for anyone who keeps their notes, research, and knowledge base in Obsidian.

[README](../obsidian-second-brain/README.md) · [GUIDE](../obsidian-second-brain/GUIDE.md) · [10 skills](../generated/SKILL-CATALOG.md#obsidian-second-brain)

### project-launcher

Version 1.8.1. Walks a new project from a rough idea through research, requirements, a written plan, and a ready-to-build project folder — for anyone starting a new software or automation project.

[README](../project-launcher/README.md) · [GUIDE](../project-launcher/GUIDE.md) · [2 skills](../generated/SKILL-CATALOG.md#project-launcher)

### rhize-devflow

Version 2.20.0. Rhize Media's software delivery workflow — plan a change, build it, test it, and get it independently reviewed before shipping — for developers building production Next.js, Sanity, and Vercel applications.

[README](../rhize-devflow/README.md) · [GUIDE](../rhize-devflow/GUIDE.md) · [9 skills](../generated/SKILL-CATALOG.md#rhize-devflow)

### rhize-context-manager

Version 0.24.0. Keeps Claude's memory and working context organized across long sessions so information isn't lost or repeated — for anyone running long or complex Claude sessions.

[README](../rhize-context-manager/README.md) · [GUIDE](../rhize-context-manager/GUIDE.md) · [16 skills](../generated/SKILL-CATALOG.md#rhize-context-manager)

### rhize-ops

Version 0.16.0. Rhize Media's internal operations toolkit — hands off work to teammates with full context, tracks which skills are actually earning their keep, and helps run multiple Claude agents safely at once.

[README](../rhize-ops/README.md) · [GUIDE](../rhize-ops/GUIDE.md) · [3 skills](../generated/SKILL-CATALOG.md#rhize-ops)

### rhize-tasks

Version 0.4.2. Turns your approved Jira work into a realistic daily plan on your Mac by blocking time on your calendar and creating reminders — for anyone juggling Jira tickets against their own schedule.

[README](../rhize-tasks/README.md) · [GUIDE](../rhize-tasks/GUIDE.md) · [6 skills](../generated/SKILL-CATALOG.md#rhize-tasks)

### rhize-cowork

Version 0.2.1. Sets up the starter files describing a new Cowork client's business, voice, and key facts, so Claude's first draft for that client is already on-brand.

[README](../rhize-cowork/README.md) · [GUIDE](../rhize-cowork/GUIDE.md) · [1 skill](../generated/SKILL-CATALOG.md#rhize-cowork)

### procedural-memory

Version 0.5.1. Lets Claude find and reuse previously verified scripts and automations instead of rebuilding them from scratch each time — for developers who want proven code reused safely.

[README](../procedural-memory/README.md) · [GUIDE](../procedural-memory/GUIDE.md) · [2 skills](../generated/SKILL-CATALOG.md#procedural-memory)
<!-- SKILL-MAP:END -->

## Cross-plugin references

- [`skill-map.md`](./skill-map.md) — how the generated skill-map graph works: schema, edge
  types, the query layer, generated docs, and the Obsidian vault publish. Deep-reference subdocs
  live under [`skill-map/`](./skill-map/): [`edge-semantics.md`](./skill-map/edge-semantics.md),
  [`query-layer.md`](./skill-map/query-layer.md),
  [`generated-docs.md`](./skill-map/generated-docs.md), and
  [`agent-dispatch-surface.md`](./skill-map/agent-dispatch-surface.md).
- [`mcp-secret-launcher.md`](./mcp-secret-launcher.md) — how plugins deliver a credential to an
  MCP server without ever writing it into a file.

## Design records

Dated proposals and specs, preserved as written at the time they were approved — not living
documentation, so they are not restructured or kept in sync with later changes:

- [`superpowers/specs/`](./superpowers/specs/) — approved design specs (skill-map relationships
  v2, skill-graph evals, three-way drift reconciliation, the rhize-tasks plugin).
- [`superpowers/plans/`](./superpowers/plans/) — implementation plans written against those specs.
- [`release/`](./release/) — release write-ups (e.g. the rhize-tasks PR body).

## Archive

Superseded proposals kept for history only — not accurate to current plugin behavior:

- [`archive/error-lifecycle-management-ARCHITECTURE-PROPOSAL.md`](./archive/error-lifecycle-management-ARCHITECTURE-PROPOSAL.md)
