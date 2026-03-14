# Obsidian Skills Plugin

Skills and commands for working with Obsidian vaults in Claude Desktop, Cowork, and Claude Code.

## What's Included

### Skills (7)

| Skill | Triggers on |
| ------- | ------------- |
| **obsidian-cli** | CLI commands, terminal vault operations, shell automation, cron jobs |
| **obsidian-markdown** | Wikilinks, embeds, callouts, frontmatter, block references, Obsidian formatting |
| **obsidian-bases** | .base files, database views, filters, formulas, summaries, task trackers |
| **json-canvas** | .canvas files, visual boards, node diagrams, mind maps |
| **defuddle** | Web clipping, article extraction, saving URLs to vault |
| **second-brain** | Zettelkasten, PARA, MOCs, progressive summarization, PKM methodology |
| **vault-templates** | Note archetypes — meeting notes, book reviews, project briefs, weekly reviews |

### Commands (7)

| Command | Description |
| --------- | ------------- |
| `/vault-search <query>` | Search vault for notes, tags, or content |
| `/vault-capture <content>` | Quick-capture a note, idea, or task |
| `/vault-daily [read\|add\|summarize]` | Read, append to, or summarize today's daily note |
| `/vault-organize [tags\|structure\|recent]` | Analyze vault health and organization |
| `/vault-research <url or topic>` | Research pipeline — clip, summarize, and connect to vault |
| `/vault-connect [note\|topic\|recent]` | Find and build missing links between related notes |
| `/vault-review [daily\|weekly\|monthly]` | Periodic review — summarize activity, surface themes, plan ahead |

## Setup

### Prerequisites

- **Obsidian MCP Server** connected for commands to work (the commands use `obsidian-mcp-server` tools)
- **Obsidian CLI** (v1.12.4+) for the CLI skill's terminal commands — enable in Settings → General → CLI
- **Defuddle** (`npm install -g defuddle`) for the web clipping skill

### Installation

Accept the plugin when presented in chat, or install the `.plugin` file from your vault's SKILLS REPO folder.

## Sources

- [Official Obsidian CLI docs](https://help.obsidian.md/cli)
- [kepano/obsidian-skills](https://github.com/kepano/obsidian-skills) (MIT License)
- [JSON Canvas Spec](https://jsoncanvas.org)
