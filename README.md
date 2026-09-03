# Rhize Plugins

New here? Read **[START-HERE.md](./START-HERE.md)** first.

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
| [seo-aeo-geo](./seo-aeo-geo) | 1.5.2 | 7 | Audits and improves how a website ranks in search engines and shows up in AI answers like ChatGPT and Google AI Overviews, using live search data — for SEO practitioners, content teams, marketers, and developers. | [README](./seo-aeo-geo/README.md) · [GUIDE](./seo-aeo-geo/GUIDE.md) |
| [obsidian-second-brain](./obsidian-second-brain) | 1.7.3 | 10 | Teaches Claude to read, write, organize, and search notes in your Obsidian vault — for anyone who keeps their notes, research, and knowledge base in Obsidian. | [README](./obsidian-second-brain/README.md) · [GUIDE](./obsidian-second-brain/GUIDE.md) |
| [project-launcher](./project-launcher) | 1.8.2 | 2 | Walks a new project from a rough idea through research, requirements, a written plan, and a ready-to-build project folder — for anyone starting a new software or automation project. | [README](./project-launcher/README.md) · [GUIDE](./project-launcher/GUIDE.md) |
| [rhize-devflow](./rhize-devflow) | 2.20.1 | 9 | Rhize Media's software delivery workflow — plan a change, build it, test it, and get it independently reviewed before shipping — for developers building production Next.js, Sanity, and Vercel applications. | [README](./rhize-devflow/README.md) · [GUIDE](./rhize-devflow/GUIDE.md) |
| [rhize-context-manager](./rhize-context-manager) | 0.25.0 | 16 | Keeps Claude's memory and working context organized across long sessions so information isn't lost or repeated — for anyone running long or complex Claude sessions. | [README](./rhize-context-manager/README.md) · [GUIDE](./rhize-context-manager/GUIDE.md) |
| [rhize-ops](./rhize-ops) ⭐ **hub — recommended base install** | 0.18.0 | 3 | Rhize Media's internal operations toolkit — hands off work to teammates with full context, tracks which skills are actually earning their keep, and helps run multiple Claude agents safely at once. | [README](./rhize-ops/README.md) · [GUIDE](./rhize-ops/GUIDE.md) |
| [rhize-tasks](./rhize-tasks) | 0.4.4 | 6 | Turns your approved Jira work into a realistic daily plan on your Mac by blocking time on your calendar and creating reminders — for anyone juggling Jira tickets against their own schedule. | [README](./rhize-tasks/README.md) · [GUIDE](./rhize-tasks/GUIDE.md) |
| [rhize-cowork](./rhize-cowork) | 0.2.2 | 1 | Sets up the starter files describing a new Cowork client's business, voice, and key facts, so Claude's first draft for that client is already on-brand. | [README](./rhize-cowork/README.md) · [GUIDE](./rhize-cowork/GUIDE.md) |
| [procedural-memory](./procedural-memory) | 0.5.2 | 2 | Lets Claude find and reuse previously verified scripts and automations instead of rebuilding them from scratch each time — for developers who want proven code reused safely. | [README](./procedural-memory/README.md) · [GUIDE](./procedural-memory/GUIDE.md) |
<!-- SKILL-MAP:END -->

**Why rhize-ops is the hub:** it hosts `/rhize-setup`, the one wizard that reads every other
plugin's `setup/manifest.json`, lets you pick which installed plugins to set up, runs the shared
checks once (dependencies, whether your customizations are under version control, the skill-map
install), hands off to each selected plugin's own wizard, wires the opt-in hooks into
`.claude/settings.json`, and reports what was written where
([`rhize-ops/docs/setup-artifacts.md`](./rhize-ops/docs/setup-artifacts.md)) — without it those
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

**rhize-tasks** is a macOS-local service and requires macOS 14+, Node.js 22+, a compatible Swift/Xcode toolchain, Apple Reminders permission, and credentials for the connector scopes the end user approves. It stores secrets only in Keychain and keeps Calendar/Reminders writes inside dedicated approved containers. See its [technical README](./rhize-tasks/README.md) and [user guide](./rhize-tasks/GUIDE.md).

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
| rhize-tasks | Slack bot in the approved delegation-channel scope | direct connector | No | Structured delegation fallback is disabled; Jira planning continues |

## Documentation Hierarchy

This repo uses one convention consistently across every plugin — know it once, and every plugin's docs are predictable:

| File | Audience | Contains |
| --- | --- | --- |
| **[`START-HERE.md`](./START-HERE.md)** | First-time readers | Start here — what this repo is, what each plugin is for in plain words, which plugins to install for your situation, and how the context-file architecture fits together |
| **This README** | Anyone browsing the marketplace | Repo-wide navigation: what plugins exist, how to install, how the docs are organized |
| **Plugin `README.md`** | Someone setting up or maintaining a plugin | Technical reference — installation, env vars, the full skill/command inventory, architecture, hooks |
| **Plugin `GUIDE.md`** | Someone using a plugin day-to-day | Plain-language walkthrough — what problem it solves, when to reach for which skill/command, example prompts, tips, troubleshooting |
| **`SKILL.md`** (inside `skills/*/`) | Claude, at runtime | The actual instructions a skill executes when triggered — not primary human documentation, though readable if you're curious how a skill works |
| **[`docs/README.md`](./docs/README.md)** | Maintainers | Index into cross-plugin reference material and dated design records that don't belong to one plugin |
| **[`generated/SKILL-CATALOG.md`](./generated/SKILL-CATALOG.md)** | Anyone looking for a specific skill | Full cross-plugin skill catalog, generated from the skill map — never hand-edited |
| **[`rhize-ops/docs/setup-artifacts.md`](./rhize-ops/docs/setup-artifacts.md)** | Anyone who ran setup | Every file the plugins write on your machine — path, purpose, how to view it, sensitivity, Git tracking — rendered from each plugin's setup manifest |
| **`ROADMAP.md`** | Contributors | Active and planned future work, organized by plugin |
| **[`CHANGELOG.client.md`](./CHANGELOG.client.md)** | Anyone using the plugins | Plain-language highlights of what shipped |
| **`CHANGELOG.md`** | Maintainers and contributors | The full engineering record: every fix and version bump, with internal references |

**Rule of thumb:** if you're asking "how do I install/configure this" or "what does this plugin ship," read the README. If you're asking "how do I actually use this to get something done," read the GUIDE.

### Progressive disclosure

Every document above is a **front door, not a warehouse.** Answer "what is this, and how do I
start" in plain language at the top, then *link* to depth rather than inlining it. A reader should
be able to stop after the first screen and still be oriented; anyone who needs the mechanics
follows a link to the document that owns them.

- **Link, don't inline.** Deep mechanics — schemas, gate internals, per-command option matrices,
  design rationale — belong in a `docs/` or `references/` file linked at the point of need. This is
  the discipline `SKILL.md` files already use with `references/`; it applies to READMEs, GUIDEs, and
  `CLAUDE.md` files too.
- **Split threshold.** A README or reference doc past roughly **400–500 lines** is a split
  candidate, not a scrolling exercise. A GUIDE may run longer, since a walkthrough is read start to
  finish, but the same "overview first, detail behind a link" shape still applies.
- **One concept per document.** If a section could be replaced by three sentences and a link, it
  should be.

When splitting, nothing is deleted — content moves to the document that owns it and is linked from
where the reader was. What remains must stand on its own.

**Dated records are exempt.** Archived proposals, plan and spec snapshots, release notes, and the
engineering `CHANGELOG.md` are point-in-time records, not living front doors. They are preserved as
written regardless of length — restructuring them would falsify the record. The standard applies to
documents a reader lands on for orientation.

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

- **CodeGraph 1.6+** — this repository opts into a local structural code index for source
  navigation, impact mapping, compiled-context target discovery, and affected-test suggestions.
  Run `codegraph init -y` once per clone, `codegraph status` before trusting it, and
  `codegraph sync` after source changes when needed. The approximately 30 MB SQLite database under
  `.codegraph/` stays local and ignored; only `.codegraph/.gitignore` is committed. Existing Dev
  Flow and Context Manager consumers automatically use a healthy index first and retain their
  explicit `rg` fallback for unavailable, stale, unsupported, generated, or external edges.
- **[`evals/`](./evals/README.md)** — local/free coverage gates account for all 56 published plugin skills, alongside live trigger/output harnesses, real-provider context-tool dogfood, strict benefit-benchmark contracts, a separate Superpowers/Rhize guide comparison, and SkillForge safety/evolve integration. Complete deterministic inventory does not imply complete live evidence: pending cohorts stay explicit, and `evals/context-tools` keeps real benchmark rows separate from test-local failure doubles.
- **`scripts/validate_plugin_configs.py`** — dependency-free lint over every plugin's `hooks/hooks.json` and `.mcp.json`, catching known hook/MCP-config footguns (see the script's own docstring for the exact checks and the incidents behind them). Registered in `scripts/bump_version.py`'s `REPOSITORY_CONTRACTS` in default (warning) mode — only genuine errors block a release; run with `--strict` to promote warnings, or see the script's docstring for the per-finding suppression mechanism.

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
├── rhize-cowork/                  # Plugin: Cowork project context scaffolding
├── procedural-memory/             # Plugin: rhize-skill CLI wrapper (recall/promote/verify/run)
├── docs/                          # Cross-plugin reference material for maintainers
├── generated/                     # Generated artifacts (skill map, SKILL-CATALOG.md) — never hand-edited
├── evals/                         # Trigger/quality eval harness
├── scripts/                       # Maintainer scripts (e.g. version bump)
├── START-HERE.md                  # First-time-reader orientation
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
4. Do **not** hand-edit the Plugin Catalog table above or `generated/SKILL-CATALOG.md` — both are
   rendered from `marketplace.json` and the skill map by `scripts/render_skill_map_docs.py`.
   Registering the plugin in step 3 is what feeds them; the render itself runs as part of the
   version-bump release flow (see the root CLAUDE.md's Documentation Maintenance section).
5. Add a `CHANGELOG.md` entry.
6. Add complete eval coverage under `evals/` (see `evals/README.md`): routing cases, a local quality contract, and an exact benchmark applicability record for every new skill.

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
