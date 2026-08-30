# Rhize Plugins

A curated collection of Claude and Codex plugins by [Rhize Media](https://rhize.media) — web development, SEO, knowledge management, development workflow, local-first planning, and internal operations tooling.

## Quick Start

Add this marketplace in Cowork via **Settings > Plugins > Add Marketplace**, or in Claude Code with `/plugin marketplace add`, using the repository URL:

```
https://github.com/Rhize-Media/rhize-plugins
```

All plugins below will become available for installation. Each plugin may need its own environment variables or MCP server credentials — check that plugin's `README.md` **Setup**/**Installation** section before first use.

## Plugin Catalog

<!-- SKILL-MAP:BEGIN -->
| Plugin | Version | Skill Count | Description | Docs |
| --- | --- | --- | --- | --- |
| [seo-aeo-geo](./seo-aeo-geo) | 1.4.3 | 7 | Comprehensive SEO, AEO, and GEO plugin for auditing, analyzing, and optimizing codebases and websites | [README](./seo-aeo-geo/README.md) · [GUIDE](./seo-aeo-geo/GUIDE.md) |
| [obsidian-second-brain](./obsidian-second-brain) | 1.4.4 | 9 | Second brain toolkit for Obsidian vaults — knowledge workflows, research pipelines, connection discovery, vault health, Zettelkasten/PARA/MOC methodology, semantic search, MCP server, and CLI integration | [README](./obsidian-second-brain/README.md) · [GUIDE](./obsidian-second-brain/GUIDE.md) |
| [project-launcher](./project-launcher) | 1.7.3 | 2 | End-to-end project launcher — research, PRD generation, critical gap analysis, project scaffolding, and GSD v2 handoff for autonomous development. Phase 3 renders the PRD into a rhize-visual-plan .mdx review/approval surface (diagrams, wireframes, file maps, data/API contracts) in Next.js and Obsidian; the PRD remains the GSD machine spec | [README](./project-launcher/README.md) · [GUIDE](./project-launcher/GUIDE.md) |
| [rhize-devflow](./rhize-devflow) | 2.15.0 | 7 | Rhize Media's engineering control-plane plugin — impact-map → implement → simplify → check → review → release. Adds exact-diff behavior-preserving simplification for Claude and Codex, evidence-driven validation, an independent production merge/release gate, production error lifecycle (Sentry + Vercel), data-mutation consistency, browser QA, Sentry instrumentation, and Sanity house style. Session/context engineering lives in rhize-context-manager. | [README](./rhize-devflow/README.md) · [GUIDE](./rhize-devflow/GUIDE.md) |
| [rhize-context-manager](./rhize-context-manager) | 0.19.1 | 13 | Context engineering and optimization — compression, management, retrieval, and storage. Orchestrates the Rhize context stack, ships a disabled-by-default real-provider retrieval/compiled-context dogfood harness, and adds a local mixed-language native context pack with explicit provenance and stale-pack verification. The pinned upstream Python compiler remains an eval provider. | [README](./rhize-context-manager/README.md) · [GUIDE](./rhize-context-manager/GUIDE.md) |
| [rhize-ops](./rhize-ops) ⭐ **hub — recommended base install** | 0.13.5 | 3 | Operations skill set for delegation, hand-offs, team workflow automation, and privacy-safe parallel-agent optimization. Includes one-strategy live execution plus explicit isolated comparisons of baseline, ECC, Superpowers, and the Rhize routing policy. | [README](./rhize-ops/README.md) · [GUIDE](./rhize-ops/GUIDE.md) |
| [rhize-tasks](./rhize-tasks) | 0.3.0 | 6 | Local-first unified planning for approved Jira work across Google Calendar and Apple Reminders, with structured Slack fallback, bounded replanning, and human approval controls | [README](./rhize-tasks/README.md) · [GUIDE](./rhize-tasks/GUIDE.md) |
| [rhize-cowork](./rhize-cowork) | 0.1.0 | 1 | Cowork project skill set — client/project context scaffolding. Houses project-kickoff: stand up the standard four context files (CLAUDE.md, BUSINESS.md, PERSONALITY.md, INFO.md) for any new Cowork project from a website, strategy docs, or a guided interview — with strict no-fabrication rules ([inferred] / [TBD — confirm] tagging). | [README](./rhize-cowork/README.md) · [GUIDE](./rhize-cowork/GUIDE.md) |
| [procedural-memory](./procedural-memory) | 0.3.1 | 1 | Executes proven, working code from the procedural-memory registry (Rhize-Media/procedural-memory) instead of recomposing a workflow from scratch. Wraps the `rhize-skill` CLI: /recall finds an artifact whose description matches a task (Postgres + pgvector semantic search), /run executes it (registry-only, digest-checked, trust-gated), /promote lands a new one, /verify re-runs its sandboxed smoke test. Every artifact carries a provenance contract (input schema, declared env/secrets, verification spec, trust tier); this plugin never bypasses that gate. Distinct from claude-mem/session-search skills — those retrieve what happened, this executes what already works. | [README](./procedural-memory/README.md) · [GUIDE](./procedural-memory/GUIDE.md) |
<!-- SKILL-MAP:END -->

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

**rhize-tasks** is a macOS-local service and requires macOS 14+, Node.js 22+, a compatible Swift/Xcode toolchain, Apple Reminders permission, and credentials for the connector scopes Tom approves. It stores secrets only in Keychain and keeps Calendar/Reminders writes inside dedicated approved containers. See its [technical README](./rhize-tasks/README.md) and [Tom-facing guide](./rhize-tasks/GUIDE.md).

**procedural-memory** needs a built `rhize-skill` CLI (from `Rhize-Media/procedural-memory`, not published to PyPI) and a local Postgres + pgvector instance. It never hardcodes a path to the CLI — resolve it via `RHIZE_SKILL_BIN`, `PATH`, or the documented convenience default. See its [README](./procedural-memory/README.md#setup) for full setup.

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
| rhize-devflow | Sentry MCP server | mcp | No | `error-lifecycle-management` can't fetch issues/events/perf data (capability: `error-lifecycle`) |
| rhize-devflow | Vercel MCP server | mcp | No | Can't correlate an error with its causing deployment (capability: `deploy-correlation`) |
| rhize-devflow | GitHub MCP server | mcp | No | Can't identify the causing commit/PR or auto-file a ticket (capability: `commit-pr-correlation`) |
| rhize-devflow | Chrome DevTools MCP server | mcp | No | `chrome-devtools-mcp` skill can't run at all (capability: `browser-qa`; `/rhize-devflow:browser-qa` itself still degrades gracefully across whichever browser tool is connected) |
| rhize-devflow | `@rhize/skill-forge` (npm) | cli | No | Opt-in refinement hooks still fire; the suggested command fails |
| rhize-context-manager | `@rhize/skill-forge` (npm) | cli | Yes | `/skill-refine run` cannot execute |
| rhize-context-manager | headroom (CLI) | cli | Yes | `/learn-harvest`'s headroom-learn source step fails |
| rhize-context-manager | ecc:harness-audit | plugin | No | `/context-doctor` prints a one-line skip (documented, graceful) |
| rhize-context-manager | claude-mem, OpenWolf, Serena, CodeGraph, Graphiti | plugin/cli/mcp | No | Each layer is marked inactive; the other layers are unaffected |
| project-launcher | 13 integrated MCP servers (Obsidian, Firecrawl, Context7, DataForSEO, Slack, Google Drive, Atlassian, Sentry, PostHog, Sequential Thinking, Serena, n8n-builder, n8n-executor) | mcp | No | The corresponding phase proceeds without that data source |
| project-launcher | 12 integrated external skills (obsidian-second-brain, grill-me, write-a-prd, seo-aeo-geo, brand-voice, n8n-automation, engineering, tdd, prd-to-issues, simplify) | plugin | No | That phase's step is skipped or done with generic prompting |
| rhize-ops | ecc (cost-tracker Stop hook → `costs.jsonl`) | plugin | No | Scorecard/ROI reports lose their measured-spend denominator |
| rhize-ops | rtk, Headroom, claude-mem, OpenWolf | cli/plugin | No | Each is one numerator source in the scorecard; missing ones show "no data" |
| rhize-tasks | macOS 14+, Node.js 22+, Swift/Xcode toolchain | platform/runtime | Yes | The local service and signed EventKit helper cannot be installed |
| rhize-tasks | Jira, Google Calendar, Apple Reminders | direct connector | Yes | The affected source remains offline and its writes stay paused |
| rhize-tasks | Slack bot in approved `#tom-tasks` scope | direct connector | No | Structured delegation fallback is disabled; Jira planning continues |

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

## Skill Map

This repo compiles a graph of every skill, plugin, MCP server, and their relationships
(`follows`, `extends`, `augments`, `remediates`, `precedes`, third-party `fork-of` edges)
into `generated/skill-map.static.json`, installed per-machine to
`~/.claude/context-manager/`. Four `rhize-context-manager` hooks read it at runtime
(session-start disclosure, failure remediation, next-step suggestion, and — opt-in —
prompt routing); `skill-forge`'s `--skill-map` flag reads it for overlap-gating and
upstream drift checks. See **[`docs/skill-map.md`](./docs/skill-map.md)** for the full
artifact/schema/tagging reference, and query it directly with
`python3 scripts/query_skill_map.py --list` (declarative named queries over
`catalog/queries.json`) rather than re-deriving a traversal by hand. For a visual view,
`scripts/publish_skill_map_vault.py` renders the same map into an Obsidian `Skill Map.base`
and `Skill Map.canvas` — regenerate rather than hand-edit either. Design specs for major
skill-map changes live under [`docs/superpowers/specs/`](./docs/superpowers/specs/).

## Repository Tooling

- **[`evals/`](./evals/README.md)** — Python eval harnesses for trigger/output quality plus real-provider context-tool dogfood. Coverage remains partial; `evals/context-tools` keeps real benchmark rows separate from test-local failure doubles.
- **[`skills/rhize-review/SKILL.md`](./skills/rhize-review/SKILL.md)** — a standalone merge-gate review skill that lives at the repo root, outside any plugin. It isn't installed through the marketplace and isn't listed in `marketplace.json`; it's a repo-local tool that dispatches specialist reviewer subagents before a production merge.
- **`scripts/validate_plugin_configs.py`** — dependency-free lint over every plugin's `hooks/hooks.json` and `.mcp.json`, written after three separate 2026-08 incidents (unquoted `${CLAUDE_PLUGIN_ROOT}` word-splitting a hook command, a secret-shaped `${VAR}` left in a stdio MCP server's `env` block, a trailing-slash `*_BASE_URL` doubling every request path). Registered in `scripts/bump_version.py`'s `REPOSITORY_CONTRACTS` in default (warning) mode — only genuine errors block a release; run with `--strict` to promote warnings, or see the script's docstring for the per-finding suppression mechanism.

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
├── rhize-tasks/                   # Plugin: local-first unified task planning
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

Opening a pull request? The PR template (`.github/PULL_REQUEST_TEMPLATE.md`) walks through
the curation and documentation checks above. Filing a bug or proposing a new plugin/skill?
Use the issue templates under `.github/ISSUE_TEMPLATE/` — the plugin-request template
includes the same "which enabled plugin already does this" gate as the Curation Rule.

### Security

Found a vulnerability — especially in a plugin's hooks, since they run local shell commands
once wired up? See [`SECURITY.md`](./SECURITY.md) for how to report it privately and what to
review before enabling a plugin's hooks.

## License

Proprietary — Rhize Media. All rights reserved.
