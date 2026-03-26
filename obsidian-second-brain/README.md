# Obsidian Second Brain

A second brain toolkit for Obsidian vaults — knowledge workflows, research pipelines, connection discovery, and vault health management, backed by semantic search (qmd), MCP server, and CLI integration.

## Knowledge Workflows

The core of this plugin. These skills and commands turn your vault into an active thinking tool, not just a file store.

### Skills — Second Brain

| Skill | Purpose |
|-------|---------|
| **second-brain** | Zettelkasten, PARA, MOCs, progressive summarization, atomic notes — the methodology behind effective knowledge management |
| **vault-templates** | Note archetypes — meeting notes, book reviews, project briefs, weekly reviews, literature notes |
| **vault-alignment** | Vault health assessment, drift detection, structural improvement strategies |
| **qmd-search** | Semantic vector search setup and configuration (BM25, vector, hybrid modes) |
| **defuddle** | Web clipping and article extraction — bring external knowledge into your vault |

### Commands — Research & Connect

| Command | Description |
|---------|-------------|
| `/vault-research <url or topic>` | Research pipeline — clip, summarize, link to vault with MOC placement and tags |
| `/vault-connect [note\|topic\|recent]` | Find and build missing links between related notes (qmd-enhanced) |
| `/vault-recall <question>` | Ask your vault a natural language question and get a synthesized answer |
| `/vault-review [daily\|weekly\|monthly]` | Periodic review — summarize activity, surface themes, plan ahead |

### Commands — Capture & Daily

| Command | Description |
|---------|-------------|
| `/vault-capture <content>` | Quick-capture a note, idea, or task (auto-tagged, inbox placement) |
| `/vault-daily [read\|add\|summarize]` | Read, append to, or summarize today's daily note |
| `/vault-search <query>` | Search vault for notes, tags, or content (semantic search when qmd available) |

### Commands — Vault Health

| Command | Description |
|---------|-------------|
| `/vault-align [check\|fix\|migrate\|plugins]` | Vault health monitor — audit structure, fix orphans, bulk migrate |
| `/vault-setup [new\|existing\|resume]` | Interactive setup wizard — personalized folders, templates, dashboards, plugins, qmd |

## Format Skills

Lower-level skills that auto-trigger when you're working with specific Obsidian file types or syntax. You rarely invoke these directly — they activate when needed.

| Skill | Triggers on |
|-------|-------------|
| **obsidian-markdown** | Wikilinks, embeds, callouts, frontmatter, block references, Obsidian formatting |
| **obsidian-bases** | .base files, database views, filters, formulas, summaries, task trackers |
| **json-canvas** | .canvas files, visual boards, node diagrams, mind maps |
| **obsidian-cli** | CLI commands, terminal vault operations, shell automation, cron jobs |

## Hooks

| Hook | Matcher | Behavior |
|------|---------|----------|
| **SessionStart** | All sessions | Loads knowledge workflow commands, skills, connectors, and vault path into context |
| **PreToolUse** | `Write\|Edit` on vault `.md` files | Enforces second-brain practices: `[[wikilinks]]` (not markdown links), callout syntax (`> [!type]`), frontmatter preservation, `#tags`, `tags:` array in frontmatter, and parent MOC linking |
| **PostToolUse** | `Read` on vault `.md` files | Suggests following `[[wikilinks]]`, searching tags, `/vault-connect` for related notes, and `/vault-align` for orphan detection and health checks |

All hooks are scoped to the vault path — files outside the vault pass through silently. Hooks fail silently on error (3s timeout) and never block operations.

## Connectors

### Obsidian MCP Server (bundled)

The plugin bundles an `obsidian-mcp-server` connector via `.mcp.json`. This provides read, write, search, tag management, and frontmatter operations through the Obsidian REST API.

**Required env var:**
```bash
export OBSIDIAN_API_KEY=your_api_key_here
```

Get your API key from Obsidian: Settings → Community plugins → Local REST API → Copy API Key.

The server connects to `https://127.0.0.1:27124/` (Obsidian's local REST API). Obsidian must be running.

### Obsidian CLI

The Obsidian CLI (`obsidian` command, v1.12.4+) provides direct vault operations from the terminal. **Prefer CLI over raw file I/O** whenever Obsidian is running — it respects plugins, templates, and link resolution.

**Setup:**
1. Enable CLI: Obsidian → Settings → General → Command line interface → Register CLI
2. Restart your terminal so `obsidian` is on PATH
3. Verify: `obsidian --version`

**Key operations:**
```bash
obsidian read file="Note Name"              # Read note by wikilink name
obsidian create name="New Note"             # Create note
obsidian search query="keyword"             # Full-text search
obsidian properties file="Note" format=json # Read frontmatter
obsidian tags                               # List all tags
obsidian daily                              # Today's daily note
obsidian files folder=Projects format=json  # List files in folder
```

### qmd Semantic Search (dependency: `qmd@qmd` plugin)

qmd adds local vector embeddings and LLM re-ranking — no cloud services required. It is a **plugin dependency** — enable the `qmd@qmd` plugin alongside this plugin for full semantic search support. The `qmd@qmd` plugin registers its own MCP server (`qmd mcp`).

**Setup:**
```bash
npm install -g qmd
qmd collection add vault /path/to/your/vault --include "*.md"
qmd embed vault
qmd status vault
```

Once installed and the `qmd@qmd` plugin is enabled, `/vault-search`, `/vault-connect`, and `/vault-recall` automatically use semantic search. All commands gracefully fall back to MCP/CLI keyword search when qmd is not available.

## Setup

### Prerequisites

- **Obsidian** running with Local REST API plugin enabled (for MCP server)
- **`$OBSIDIAN_API_KEY`** env var set (from Local REST API plugin)
- **Obsidian CLI** (v1.12.4+) registered and on PATH
- **Defuddle** (`npm install -g defuddle`) for the web clipping skill
- **qmd** (`npm install -g qmd`) + **`qmd@qmd` plugin** enabled — for semantic search

### Installation

Accept the plugin when presented in chat, or install the `.plugin` file from your vault's SKILLS REPO folder. The `.mcp.json` bundled with the plugin will auto-register the Obsidian MCP server.

## Architecture

```
obsidian-second-brain/
├── .claude-plugin/plugin.json
├── .mcp.json                          # Obsidian MCP server connector
├── commands/                          # 9 slash commands
│   ├── vault-research.md              # Research pipeline
│   ├── vault-connect.md               # Connection discovery
│   ├── vault-recall.md                # Natural language recall
│   ├── vault-review.md                # Periodic review
│   ├── vault-capture.md               # Quick capture
│   ├── vault-daily.md                 # Daily notes
│   ├── vault-search.md                # Search
│   ├── vault-align.md                 # Vault health
│   └── vault-setup.md                 # Setup wizard
├── skills/
│   ├── second-brain/                  # PKM methodology
│   ├── vault-templates/               # Note archetypes
│   ├── vault-alignment/               # Health monitoring
│   ├── qmd-search/                    # Semantic search config
│   ├── defuddle/                      # Web clipping
│   ├── obsidian-markdown/             # Markdown syntax
│   ├── obsidian-bases/                # Bases databases
│   ├── json-canvas/                   # Canvas files
│   └── obsidian-cli/                  # + references/cli-commands.md
├── hooks/
│   ├── hooks.json                     # SessionStart + PreToolUse + PostToolUse
│   └── obsidian-context.md            # Session context (knowledge-first ordering)
└── README.md
```

## Sources

- [Official Obsidian CLI docs](https://help.obsidian.md/cli)
- [kepano/obsidian-skills](https://github.com/kepano/obsidian-skills) (MIT License)
- [JSON Canvas Spec](https://jsoncanvas.org)
- [qmd — local-first search engine](https://github.com/tobi/qmd)
