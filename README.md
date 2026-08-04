# Rhize Plugins

A curated collection of Claude plugins by [Rhize Media](https://rhize.media) — web development, SEO, knowledge management, development workflow, and internal operations tooling for Claude Code and Cowork.

## Quick Start

Add this marketplace in Cowork via **Settings > Plugins > Add Marketplace**, or in Claude Code with `/plugin marketplace add`, using the repository URL:

```
https://github.com/Rhize-Media/rhize-plugins
```

All plugins below will become available for installation. Each plugin may need its own environment variables or MCP server credentials — check that plugin's `README.md` **Setup**/**Installation** section before first use.

## Plugin Catalog

| Plugin | What it's for | Docs |
| --- | --- | --- |
| [seo-aeo-geo](./seo-aeo-geo) | SEO, AEO, and GEO auditing/optimization powered by DataForSEO, plus Next.js + Sanity SEO code review | [README](./seo-aeo-geo/README.md) · [GUIDE](./seo-aeo-geo/GUIDE.md) |
| [obsidian-second-brain](./obsidian-second-brain) | Second brain toolkit for Obsidian vaults — knowledge workflows, research pipelines, connection discovery, vault health, semantic search | [README](./obsidian-second-brain/README.md) · [GUIDE](./obsidian-second-brain/GUIDE.md) |
| [project-launcher](./project-launcher) | End-to-end project launcher — research, PRD, gap analysis, visual plan review, scaffolding, GSD v2 handoff | [README](./project-launcher/README.md) · [GUIDE](./project-launcher/GUIDE.md) |
| [rhize-devflow](./rhize-devflow) | Development-workflow skill set — production error lifecycle, data-mutation consistency, Sentry, Chrome DevTools, Sanity house style | [README](./rhize-devflow/README.md) · [GUIDE](./rhize-devflow/GUIDE.md) |
| [rhize-context-manager](./rhize-context-manager) | Context engineering & optimization — compression, management, retrieval, storage; orchestrates Headroom/claude-mem/OpenWolf/Serena/CodeGraph/graphify (+ opt-in Graphiti), session-lifecycle commands, curated gated skill library | [README](./rhize-context-manager/README.md) · [GUIDE](./rhize-context-manager/GUIDE.md) |
| [rhize-ops](./rhize-ops) ⭐ **hub — recommended base install** | Internal operations — session hand-offs (Jira/Slack/Fireflies), skill-usage health monitoring, and fleet setup | [README](./rhize-ops/README.md) · [GUIDE](./rhize-ops/GUIDE.md) |

**Why rhize-ops is the hub:** it hosts `/rhize-setup`, the only wizard that wires any other
plugin's opt-in `setup/manifest.json` hooks and dependencies into a project — without it those
manifests are documentation only, and you'd hand-edit `.claude/settings.json` yourself following
the snippets each plugin's README shows. It also hosts the cost/ROI reporting (`savings_scorecard.py`,
`skill_roi.py`) that the other plugins' value story leans on. Every other plugin still installs,
loads, and works fully without rhize-ops — it just means doing setup and cost visibility by hand.

### Plugin-specific prerequisites

**seo-aeo-geo** needs DataForSEO credentials. Add to your `~/.zshrc`:
```bash
export DATAFORSEO_USERNAME="your_email"
export DATAFORSEO_PASSWORD="your_api_password"
```

**obsidian-second-brain** needs Obsidian running with the Local REST API plugin, an `OBSIDIAN_API_KEY` env var, the Obsidian CLI (v1.12.4+), Defuddle, and qmd. See its [README](./obsidian-second-brain/README.md#setup) for full setup.

The other plugins (project-launcher, rhize-devflow, rhize-context-manager, rhize-ops) have no required external credentials beyond the MCP servers/tools each plugin's README calls out. rhize-context-manager orchestrates externally installed tools (Headroom, claude-mem, OpenWolf, Serena, CodeGraph, RTK) — each is optional and documented in its [README](./rhize-context-manager/README.md).

### Dependency matrix

Each plugin's `setup/manifest.json` now carries a machine-readable `"dependencies"` array (see
[rhize-ops/README.md § Setup manifest schema](./rhize-ops/README.md#setup-manifest-schema)) that
`/rhize-setup` probes and reports on before its opt-in hook menu. This table is the human-readable
summary — one row per *required* or structurally central dependency; see each manifest for the
full list including optional numerator/orchestration sources.

| Plugin | External dependency | Kind | Required? | Without it |
| --- | --- | --- | --- | --- |
| seo-aeo-geo | DataForSEO MCP server (+ credentials) | mcp | Yes | Live-data skills/commands fail; `code-seo-review`, `content-optimize`, and the `content-seo`/`nextjs-sanity-seo` skills still work |
| obsidian-second-brain | obsidian-mcp-server (Obsidian + Local REST API) | mcp | Yes | Most vault commands can't reach the vault |
| obsidian-second-brain | Obsidian CLI (v1.12.4+) | cli | Yes | CLI-backed commands fail; only overlapping MCP ops still work |
| obsidian-second-brain | Defuddle | cli | No | The web-clipping skill can't extract articles; nothing else affected |
| obsidian-second-brain | qmd (+ `qmd@qmd` plugin) | plugin | No | Falls back to MCP/CLI keyword search (documented, automatic) |
| rhize-devflow | Sentry MCP server | mcp | Yes | `error-lifecycle-management` can't fetch issues/events/perf data |
| rhize-devflow | Vercel MCP server | mcp | Yes | Can't correlate an error with its causing deployment |
| rhize-devflow | GitHub MCP server | mcp | Yes | Can't identify the causing commit/PR or auto-file a ticket |
| rhize-devflow | Chrome DevTools MCP server | mcp | Yes | `chrome-devtools-mcp` skill can't run at all |
| rhize-devflow | `@rhize/skill-forge` (npm) | cli | No | Opt-in refinement hooks still fire; the suggested command fails |
| rhize-context-manager | `@rhize/skill-forge` (npm) | cli | Yes | `/skill-refine run` cannot execute |
| rhize-context-manager | headroom (CLI) | cli | Yes | `/learn-harvest`'s headroom-learn source step fails |
| rhize-context-manager | ecc:harness-audit | plugin | No | `/context-doctor` prints a one-line skip (documented, graceful) |
| rhize-context-manager | claude-mem, OpenWolf, Serena, CodeGraph, Graphiti | plugin/cli/mcp | No | Each layer is marked inactive; the other layers are unaffected |
| project-launcher | 13 integrated MCP servers (Obsidian, Firecrawl, Context7, DataForSEO, Slack, Google Drive, Atlassian, Sentry, PostHog, Sequential Thinking, Serena, n8n-builder, n8n-executor) | mcp | No | The corresponding phase proceeds without that data source |
| project-launcher | 12 integrated external skills (obsidian-second-brain, grill-me, write-a-prd, seo-aeo-geo, brand-voice, n8n-automation, engineering, tdd, prd-to-issues, simplify) | plugin | No | That phase's step is skipped or done with generic prompting |
| rhize-ops | ecc (cost-tracker Stop hook → `costs.jsonl`) | plugin | No | Scorecard/ROI reports lose their measured-spend denominator |
| rhize-ops | rtk, Headroom, claude-mem, OpenWolf | cli/plugin | No | Each is one numerator source in the scorecard; missing ones show "no data" |

## Documentation Hierarchy

This repo uses one convention consistently across every plugin — know it once, and every plugin's docs are predictable:

| File | Audience | Contains |
| --- | --- | --- |
| **This README** | Anyone browsing the marketplace | Repo-wide navigation: what plugins exist, how to install, how the docs are organized |
| **Plugin `README.md`** | Someone setting up or maintaining a plugin | Technical reference — installation, env vars, the full skill/command inventory, architecture, hooks |
| **Plugin `GUIDE.md`** | Someone using a plugin day-to-day | Plain-language walkthrough — what problem it solves, when to reach for which skill/command, example prompts, tips, troubleshooting |
| **`SKILL.md`** (inside `skills/*/`) | Claude, at runtime | The actual instructions a skill executes when triggered — not primary human documentation, though readable if you're curious how a skill works |
| **`ROADMAP.md`** | Contributors | Active and planned future work, organized by plugin |
| **`CHANGELOG.md`** | Anyone tracking releases | What shipped, by version |

**Rule of thumb:** if you're asking "how do I install/configure this" or "what does this plugin ship," read the README. If you're asking "how do I actually use this to get something done," read the GUIDE.

**Local/personal config:** a skill should never hardcode a real name, credential, ID, or other installer-specific value. Two patterns are used depending on lifetime: durable personal config that must survive plugin reinstalls (e.g. `rhize-ops`'s `delegate-to-teammate` recipient/credentials) lives in `$HOME/.claude/<plugin>/...`, generated by a setup wizard, with a committed JSON Schema documenting the shape; disposable repo-local reference material that's just extracted example content (e.g. `rhize-devflow`'s `.claude/*.local.md` files) lives inside the repo under `.claude/`, already covered by the root `.gitignore`. Pick based on whether the data needs to outlive this git checkout.

## Repository Tooling

- **[`evals/`](./evals/README.md)** — a Python eval harness that measures trigger accuracy (does the right skill fire on the right prompt) and output quality for plugins. Coverage is currently partial: `seo-aeo-geo` and `obsidian-second-brain` have eval suites; the other plugins don't yet (see `ROADMAP.md`).
- **[`skills/rhize-review/SKILL.md`](./skills/rhize-review/SKILL.md)** — a standalone merge-gate review skill that lives at the repo root, outside any plugin. It isn't installed through the marketplace and isn't listed in `marketplace.json`; it's a repo-local tool that dispatches specialist reviewer subagents before a production merge.

## Repository Layout

```
rhize-plugins/
├── .claude-plugin/
│   └── marketplace.json          # Plugin registry — source of truth for what's installable
├── seo-aeo-geo/                   # Plugin: SEO/AEO/GEO
├── obsidian-second-brain/         # Plugin: Obsidian vault toolkit
├── project-launcher/              # Plugin: project research → PRD → scaffold
├── rhize-devflow/                 # Plugin: dev workflow
├── rhize-context-manager/         # Plugin: context engineering & optimization
├── rhize-ops/                     # Plugin: internal ops
├── skills/rhize-review/           # Standalone repo-root skill (not a plugin)
├── evals/                         # Trigger/quality eval harness
├── scripts/                       # Maintainer scripts (e.g. version bump)
├── ROADMAP.md                     # Active + planned work
├── CHANGELOG.md                   # Released changes
└── README.md                      # You are here
```

Each plugin follows the same internal structure:

```
your-plugin-name/
├── .claude-plugin/
│   └── plugin.json
├── .mcp.json          (optional — if the plugin needs an MCP server)
├── skills/
│   └── your-skill/
│       └── SKILL.md
├── commands/
│   └── your-command.md
├── hooks/             (optional)
├── README.md           # technical reference
└── GUIDE.md            # user-facing walkthrough
```

## Contributing

To add a new plugin:

1. Create a subdirectory with the standard plugin structure above.
2. Write both a `README.md` (technical) and a `GUIDE.md` (user-facing) — see the [Documentation Hierarchy](#documentation-hierarchy) rule above for what goes where.
3. Register the plugin in `.claude-plugin/marketplace.json`, keeping its `version` in sync with the plugin's own `.claude-plugin/plugin.json`.
4. Add an entry to the Plugin Catalog table above.
5. Add a `CHANGELOG.md` entry.
6. Consider adding eval coverage under `evals/` (see `evals/README.md`).

## License

Proprietary — Rhize Media. All rights reserved.
