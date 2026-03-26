# Obsidian Skills Plugin

Skills and commands for working with Obsidian vaults in Claude Desktop, Cowork, and Claude Code.

## What's Included

### Skills (9)

| Skill | Triggers on |
| ------- | ------------- |
| **obsidian-cli** | CLI commands, terminal vault operations, shell automation, cron jobs |
| **obsidian-markdown** | Wikilinks, embeds, callouts, frontmatter, block references, Obsidian formatting |
| **obsidian-bases** | .base files, database views, filters, formulas, summaries, task trackers |
| **json-canvas** | .canvas files, visual boards, node diagrams, mind maps |
| **defuddle** | Web clipping, article extraction, saving URLs to vault |
| **second-brain** | Zettelkasten, PARA, MOCs, progressive summarization, PKM methodology |
| **vault-templates** | Note archetypes — meeting notes, book reviews, project briefs, weekly reviews |
| **vault-alignment** | Vault health assessment, drift detection, ongoing improvement strategies |
| **qmd-search** | qmd semantic search setup, search modes (BM25/vector/hybrid), indexing, MCP server |

### Commands (9)

| Command | Description |
| --------- | ------------- |
| `/vault-search <query>` | Search vault for notes, tags, or content (uses qmd semantic search when available) |
| `/vault-capture <content>` | Quick-capture a note, idea, or task |
| `/vault-daily [read\|add\|summarize]` | Read, append to, or summarize today's daily note |
| `/vault-research <url or topic>` | Research pipeline — clip, summarize, and connect to vault |
| `/vault-connect [note\|topic\|recent]` | Find and build missing links between related notes (qmd-enhanced) |
| `/vault-recall <question>` | Ask your vault a natural language question and get a synthesized answer |
| `/vault-review [daily\|weekly\|monthly]` | Periodic review — summarize activity, surface themes, plan ahead |
| `/vault-setup [new\|existing\|resume]` | Interactive setup wizard — personalized folders, templates, dashboards, plugins, qmd |
| `/vault-align [check\|fix\|migrate\|plugins]` | Vault health monitor — check alignment, analyze areas, fix issues, bulk migrate |

## Hooks

| Hook | Matcher | Behavior |
|------|---------|----------|
| **SessionStart** | All sessions | Loads command menu, skills list, MCP servers, and vault path into context |
| **PreToolUse** | `Write\|Edit` on vault `.md` files | Enforces Obsidian-native formatting: `[[wikilinks]]` (not markdown links), callout syntax (`> [!type]`), frontmatter preservation, `#tags`, `tags:` array in frontmatter, and parent MOC linking |
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
obsidian-skills-plugin/
├── .claude-plugin/plugin.json
├── .mcp.json                          # Obsidian MCP server connector
├── commands/                          # 9 slash commands
│   ├── vault-search.md
│   ├── vault-capture.md
│   ├── vault-daily.md
│   ├── vault-research.md
│   ├── vault-connect.md
│   ├── vault-recall.md
│   ├── vault-review.md
│   ├── vault-setup.md
│   └── vault-align.md
├── skills/
│   ├── obsidian-cli/                  # + references/cli-commands.md
│   ├── obsidian-markdown/
│   ├── obsidian-bases/
│   ├── json-canvas/
│   ├── defuddle/
│   ├── second-brain/
│   ├── vault-templates/
│   ├── vault-alignment/
│   └── qmd-search/
├── hooks/
│   ├── hooks.json                     # SessionStart + PreToolUse + PostToolUse
│   └── obsidian-context.md            # Session context with connectors + hooks reference
└── README.md
```

## Sources

- [Official Obsidian CLI docs](https://help.obsidian.md/cli)
- [kepano/obsidian-skills](https://github.com/kepano/obsidian-skills) (MIT License)
- [JSON Canvas Spec](https://jsoncanvas.org)
- [qmd — local-first search engine](https://github.com/tobi/qmd)
