# Obsidian Second Brain

A second brain toolkit for Obsidian vaults — knowledge workflows, research pipelines, connection discovery, and vault health management, backed by semantic search (qmd), MCP server, and CLI integration.

## Knowledge Workflows

The core of this plugin. These skills and commands turn your vault into an active thinking tool, not just a file store.

### Skills — Second Brain

<!-- SKILL-MAP:BEGIN -->
| Skill | Description | Topics |
| --- | --- | --- |
| `defuddle` | ALWAYS invoke this skill (via the Skill tool) for any web clipping or article extraction request. | content-authoring, obsidian, web-clipping |
| `qmd-search` | ALWAYS invoke this skill (via the Skill tool) for any qmd semantic search, vector search, or vault indexing request. | knowledge-management, obsidian, search |
| `second-brain` | ALWAYS invoke this skill (via the Skill tool) for any PKM methodology or vault organization request. | knowledge-management, obsidian, workflow-patterns |
| `vault-alignment` | ALWAYS invoke this skill (via the Skill tool) for any vault health, audit, or organization improvement request. | knowledge-management, observability, obsidian |
| `vault-templates` | ALWAYS invoke this skill (via the Skill tool) for any Obsidian note template or archetype request. | content-authoring, knowledge-management, obsidian |
<!-- SKILL-MAP:END -->

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
| **PreToolUse** | `Write\|Edit` on vault `.md` files | Enforces second-brain practices: `[[wikilinks]]` (not markdown links), callout syntax (`> [!type]`), frontmatter preservation, `#tags`, `tags:` array in frontmatter, and parent MOC linking |
| **PostToolUse** | `Read` on vault `.md` files | Suggests following `[[wikilinks]]`, searching tags, `/vault-connect` for related notes, and `/vault-align` for orphan detection and health checks |

> **SessionStart banner removed (2026-08-09):** the unconditional command-menu banner moved
> to [`rhize-context-manager`'s `session-disclosure.js`](../rhize-context-manager/README.md#hooks)
> — Phase 3 of the skill-map plan (`docs/skill-map.md`). It surfaces this plugin's skills only
> when a `.obsidian/` vault is detected in the repo, instead of on every session.

All hooks are scoped to the vault path — files outside the vault pass through silently. Hooks fail silently on error (3s timeout) and never block operations.

The PreToolUse and PostToolUse hooks are implemented in `hooks/scripts/vault-write-hint.py` and
`hooks/scripts/vault-read-hint.py`. They read the tool-call payload from stdin (as Claude Code
delivers it — `{"tool_name": ..., "tool_input": {...}}`) and emit advisory context via the
standard `hookSpecificOutput` contract; both are auto-wired through `hooks/hooks.json`, so no
setup step is required to use them.

## Setup Manifest

`setup/manifest.json` lists opt-in capabilities this plugin could offer beyond what's
auto-wired in `hooks/hooks.json` — read by the `/rhize-setup` wizard (in the `rhize-ops`
plugin) so a project can pick which ones to wire into its `.claude/settings.json`. It's
currently empty: this plugin's hooks are already scoped to the vault path, advisory-only, and
auto-wired, so there's nothing here that needs to be opt-in rather than on-by-default. It does
declare a `dependencies` array (obsidian-mcp-server, Obsidian CLI, Defuddle, qmd) that the
wizard's dependency check reads.

**Fleet setup:** `/rhize-ops:rhize-setup` is what actually wires opt-in items and checks
`dependencies` for you — it requires the `rhize-ops` plugin. Without it, wire an item
manually per the snippet in [rhize-ops/README.md § Setup manifest
schema](../rhize-ops/README.md#setup-manifest-schema).

## Connectors

### Obsidian MCP Server (bundled)

The plugin bundles an `obsidian-mcp-server` connector via `.mcp.json`. This provides read, write, search, tag management, and frontmatter operations through the Obsidian REST API.

The server connects to `https://127.0.0.1:27124/` (Obsidian's local REST API). Obsidian must be running.

**Credential delivery:** `.mcp.json` does not put `OBSIDIAN_API_KEY` directly in the server's
`env` block. `${VAR}` substitution in an MCP config only works when the variable happens to be
present in whatever environment Claude Code was launched from — when it's absent, Claude Code
passes the literal string `${OBSIDIAN_API_KEY}` through to the server, which then fails
authentication with a confusing 401/403 even though a valid key may already be sitting in the
macOS keychain. Instead, `.mcp.json` invokes a bundled shim:

```json
"command": "${CLAUDE_PLUGIN_ROOT}/scripts/mcp-secret-launcher.sh",
"args": ["OBSIDIAN_API_KEY", "--", "npx", "obsidian-mcp-server"]
```

`scripts/mcp-secret-launcher.sh` resolves `OBSIDIAN_API_KEY` in this order:
1. **macOS keychain**, via the `mcp-secret-launcher` helper (installed on PATH, or at
   `~/.local/bin/mcp-secret-launcher`) — reads the value from the login keychain at service
   `claude-code:OBSIDIAN_API_KEY` and exports it into the server's process only.
2. **Plain environment inheritance** — if `OBSIDIAN_API_KEY` is already exported in the shell
   Claude Code inherits from, the server runs with it. This is the path that makes the plugin
   work on Linux, in Claude Cowork, or on a teammate's machine without the keychain helper.
3. **Neither available** — the shim refuses to start the server and exits 78, printing a
   message naming the missing variable and both remedies below. It never launches a server it
   knows cannot authenticate.

**Supplying the key — two supported ways:**

macOS with the keychain helper installed:
```bash
security add-generic-password -a "$USER" -s "claude-code:OBSIDIAN_API_KEY" -l "OBSIDIAN_API_KEY" -w '<your-api-key>' -U
```

Anywhere (plain env var, no keychain):
```bash
export OBSIDIAN_API_KEY=your_api_key_here
```

Get your API key from Obsidian: Settings → Community plugins → Local REST API → Copy API Key.

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

### qmd Semantic Search (optional: `qmd@qmd` plugin)

qmd adds local vector embeddings and LLM re-ranking — no cloud services required. It is an **optional plugin** — enable the `qmd@qmd` plugin alongside this plugin for full semantic search support. The `qmd@qmd` plugin registers its own MCP server (`qmd mcp`). This plugin has no hard dependency on qmd and loads and works fully without it.

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
- **`OBSIDIAN_API_KEY`** available to the MCP server — via the macOS keychain (see Connectors
  above) or as a plain exported env var
- **Obsidian CLI** (v1.12.4+) registered and on PATH
- **Defuddle** (`npm install -g defuddle`) for the web clipping skill
- **qmd** (`npm install -g qmd`) + **`qmd@qmd` plugin** enabled — optional, for semantic search only

### Installation

Accept the plugin when presented in chat, or install the `.plugin` file from your vault's SKILLS REPO folder. The `.mcp.json` bundled with the plugin will auto-register the Obsidian MCP server.

## Architecture

```
obsidian-second-brain/
├── .claude-plugin/plugin.json
├── .mcp.json                          # Obsidian MCP server connector (via mcp-secret-launcher.sh)
├── scripts/
│   └── mcp-secret-launcher.sh         # Resolves OBSIDIAN_API_KEY (keychain, then env fallback)
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
│   └── scripts/
│       ├── vault-write-hint.py        # PreToolUse Write|Edit implementation
│       └── vault-read-hint.py         # PostToolUse Read implementation
├── setup/
│   └── manifest.json                  # Opt-in capabilities for /rhize-setup (currently empty)
└── README.md
```

## Sources

- [Official Obsidian CLI docs](https://help.obsidian.md/cli)
- [kepano/obsidian-skills](https://github.com/kepano/obsidian-skills) (MIT License)
- [JSON Canvas Spec](https://jsoncanvas.org)
- [qmd — local-first search engine](https://github.com/tobi/qmd)
