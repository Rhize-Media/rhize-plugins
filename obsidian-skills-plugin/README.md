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

## Setup

### Prerequisites

- **Obsidian MCP Server** connected for commands to work (the commands use `obsidian-mcp-server` tools)
- **Obsidian CLI** (v1.12.4+) for the CLI skill's terminal commands — enable in Settings → General → CLI
- **Defuddle** (`npm install -g defuddle`) for the web clipping skill
- **qmd** (`npm install -g qmd`) — optional but recommended for semantic search, connection discovery, and natural language vault recall

### Installation

Accept the plugin when presented in chat, or install the `.plugin` file from your vault's SKILLS REPO folder.

### qmd Setup (Optional)

qmd adds semantic search powered by local vector embeddings and LLM re-ranking — no cloud services required. Once installed, `/vault-search`, `/vault-connect`, and `/vault-recall` automatically use it.

```bash
# Install qmd
npm install -g qmd

# Index your vault
qmd collection add vault /path/to/your/vault --include "*.md"
qmd embed vault

# Verify
qmd status vault
```

All commands gracefully fall back to MCP/CLI keyword search when qmd is not installed.

## Sources

- [Official Obsidian CLI docs](https://help.obsidian.md/cli)
- [kepano/obsidian-skills](https://github.com/kepano/obsidian-skills) (MIT License)
- [JSON Canvas Spec](https://jsoncanvas.org)
- [qmd — local-first search engine](https://github.com/tobi/qmd)
