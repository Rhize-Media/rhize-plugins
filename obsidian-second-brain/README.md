# Obsidian Second Brain

A second brain toolkit for Obsidian vaults — knowledge workflows, evidence-bound compilation,
research pipelines, connection discovery, and vault health management, backed by semantic search
(qmd), MCP server, CLI integration, and a deterministic local compiler.

## Setup

### Prerequisites

- **Obsidian** running with Local REST API plugin enabled (for MCP server)
- **`OBSIDIAN_API_KEY`** available to the MCP server — via the macOS keychain (see Connectors
  below) or as a plain exported env var
- **Obsidian CLI** (v1.12.4+) registered and on PATH
- **Defuddle** (`npm install -g defuddle`) for the web clipping skill
- **qmd** (`npm install -g qmd`) + **`qmd@qmd` plugin** enabled — optional, for semantic search only

### Installation

Accept the plugin when presented in chat, or install the `.plugin` file from your vault's SKILLS REPO folder. The `.mcp.json` bundled with the plugin will auto-register the Obsidian MCP server.

Claude Code discovers commands and skills from `.claude-plugin/plugin.json`; Codex discovers the
same canonical skills from `.codex-plugin/plugin.json` and each skill's `agents/openai.yaml`.
After an install or update, start a fresh Claude Code or Codex session before verifying discovery;
an already-running host may retain the previous plugin snapshot.

## Knowledge Workflows

The core of this plugin. These skills and commands turn your vault into an active thinking tool, not just a file store.

### Skills — Second Brain

<!-- SKILL-MAP:BEGIN -->
| Skill | Description | Topics |
| --- | --- | --- |
| `defuddle` | Pulls clean, readable text from a web page for saving into your Obsidian vault. | content-authoring, obsidian, web-clipping |
| `knowledge-compiler` | Compile captured Obsidian sources into cited, invalidatable knowledge-page previews and apply an exact reviewed diff. | knowledge-management, obsidian, provenance, python, workflow-patterns |
| `qmd-search` | Sets up and troubleshoots local semantic search over your Obsidian vault using qmd. | knowledge-management, obsidian, search |
| `second-brain` | Applies knowledge-management methods like Zettelkasten and PARA to organize your vault. | knowledge-management, obsidian, workflow-patterns |
| `vault-alignment` | Checks your Obsidian vault's health and organization against best practices. | knowledge-management, observability, obsidian |
| `vault-templates` | Provides ready-made note templates for meetings, book reviews, project briefs, and more. | content-authoring, knowledge-management, obsidian |
<!-- SKILL-MAP:END -->

### Commands — Research & Connect

| Command | Description |
|---------|-------------|
| `/vault-research <url or topic>` | Research pipeline — clip, summarize, link to vault with MOC placement and tags |
| `/vault-connect [note\|topic\|recent]` | Find and build missing links between related notes (qmd-enhanced) |
| `/vault-recall <question>` | Ask your vault a natural language question and get a synthesized answer |
| `/vault-review [daily\|weekly\|monthly]` | Periodic review — summarize activity, surface themes, plan ahead |
| `/vault-compile preview\|apply\|status\|rebuild` | Review and maintain evidence-bound compiled knowledge |

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

## Evidence-bound compiled knowledge

`knowledge-compiler` separates immutable captured sources from replaceable synthesis. Its
standard-library Python engine creates private preview artifacts—a strict manifest, rendered page,
exact diff, and change brief—then applies only the named approved preview under a per-vault lock and
compare-and-swap check. Claim citations use content-hash-bound line anchors, so source edits make
dependent pages stale instead of silently rebinding them.

The config explicitly binds project, tenant, scope, operator, allowed vault/source roots, ACL,
egress, retention, and adapter policy. Preview data, source snapshots, journals, and purge tombstones
remain under a private state root. qmd export is fail-closed in this first release: the compiler
rejects `qmd_enabled: true` and marks every compiled page ineligible because an ACL-aware indexing
adapter does not yet exist. Keep compiler output and private state outside every qmd collection.
Context packs, Graphify, Neo4j, live synthesis, and scheduled mutation are also disabled.

Privacy purge is a forward-recovering transaction: it deletes compiler-owned projections,
previews, and source snapshots before committing purged index/registration status. Any interrupted
authorized purge resumes under the vault lock. Its `rawSourceRetained` receipt records whether the
canonical human source note still existed at the terminal purge boundary; the compiler itself never
deletes that source.

The canonical engine is shared by Claude Code's thin `/vault-compile` command and Codex's
`knowledge-compiler` skill metadata. Run `python3 scripts/compiled_knowledge.py --help` for the exact
CLI. `init-config` prints a disabled-by-default template; it never guesses a personal vault path.

Obsidian remains the canonical semantic source for `rhize-context-manager:memory-context`.
Memory assembly may read only an explicit, versioned, source-bound adapter result; it must not scrape
vault prose, treat a compiled page as authority over its cited sources, or write retrieval feedback
back into the vault. Neo4j is a reversible derived projection, not a replacement source of truth.

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

All hooks are scoped to the vault path — files outside the vault pass through silently. The vault
path is resolved in order: (1) the `OBSIDIAN_VAULT_PATH` env var, if set (`:`-separated for
multiple vaults); (2) vaults registered in Obsidian's own config
(`~/Library/Application Support/obsidian/obsidian.json`); (3) the legacy iCloud default
(`iCloud~md~obsidian/Documents/Obsidian Vault`), as a fallback so existing setups are unaffected.
A local-only vault, a renamed vault, or a non-iCloud sync setup now triggers the hints as long as
it's registered with Obsidian or set via the env var — commands and skills are unaffected either
way. Resolution logic lives in `hooks/scripts/vault_resolve.py`, shared by both hook scripts.
Hooks fail silently on error (3s timeout) and never block operations.

The PreToolUse and PostToolUse hooks are implemented in `hooks/scripts/vault-write-hint.py` and
`hooks/scripts/vault-read-hint.py`. They read the tool-call payload from stdin (as Claude Code
delivers it — `{"tool_name": ..., "tool_input": {...}}`) and emit advisory context via the
standard `hookSpecificOutput` contract; both are auto-wired through `hooks/hooks.json`, so no
setup step is required to use them.

## Setup Manifest

`setup/manifest.json` lists opt-in capabilities this plugin could offer beyond what's
auto-wired in `hooks/hooks.json` — read by the `/rhize-core:setup` wizard (in the `rhize-core`
plugin) so a project can pick which ones to wire into its `.claude/settings.json`. It's
currently empty: this plugin's hooks are already scoped to the vault path, advisory-only, and
auto-wired, so there's nothing here that needs to be opt-in rather than on-by-default. It does
declare a `dependencies` array (obsidian-mcp-server, Obsidian CLI, Defuddle, qmd, Python 3) that the
wizard's dependency check reads.

**Fleet setup:** `/rhize-core:setup` is what actually wires opt-in items and checks
`dependencies` for you — it requires the `rhize-core` plugin. Without it, wire an item
manually per the snippet in [rhize-core/README.md § Setup manifest
schema](../rhize-core/README.md#setup-manifest-schema).

## Connectors

### Obsidian MCP Server (bundled)

The plugin bundles an `obsidian-mcp-server` connector via `.mcp.json`. This provides read, write, search, tag management, and frontmatter operations through the Obsidian REST API.

The server connects to `https://127.0.0.1:27124` (Obsidian's local REST API). Obsidian must be running.

> **`OBSIDIAN_BASE_URL` must not end in a trailing slash.** `obsidian-mcp-server` builds every
> request by plain string concatenation (`${baseUrl}${path}`, `dist/services/obsidian/obsidian-service.js`)
> and does not normalize the base URL, so a trailing slash produces `https://127.0.0.1:27124//tags/`.
> The Local REST API answers a doubled path with `404`, and the server reports it as
> `Not found: /tags/` — the *un-doubled* path, which makes the error look like a missing
> resource rather than a malformed URL. Every endpoint is affected, not just tags.

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
security add-generic-password -a "$USER" -s "claude-code:OBSIDIAN_API_KEY" -l "OBSIDIAN_API_KEY" -U -w
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
qmd collection add vault /path/to/your/vault/ApprovedForQmd --include "*.md"
qmd embed vault
qmd status vault
```

Point each collection at an explicitly approved note root. Do not index the whole vault, the
compiled-knowledge output root, or `.rhize/compiled-knowledge`; qmd does not enforce the compiler's
ACL, freshness, retention, or purge metadata. An ACL-aware compiled-knowledge adapter is deferred.

Once installed and the `qmd@qmd` plugin is enabled, `/vault-search`, `/vault-connect`, and `/vault-recall` automatically use semantic search. All commands gracefully fall back to MCP/CLI keyword search when qmd is not available.

## Architecture

```
obsidian-second-brain/
├── .claude-plugin/plugin.json
├── .codex-plugin/plugin.json          # Codex discovery for the same canonical skills
├── .mcp.json                          # Obsidian MCP server connector (via mcp-secret-launcher.sh)
├── scripts/
│   ├── compiled_knowledge.py          # Deterministic preview/apply/status/rebuild engine
│   └── mcp-secret-launcher.sh         # Resolves OBSIDIAN_API_KEY (keychain, then env fallback)
├── schemas/
│   └── compiled-knowledge-manifest-v1.schema.json
├── commands/                          # 10 slash commands
│   ├── vault-research.md              # Research pipeline
│   ├── vault-connect.md               # Connection discovery
│   ├── vault-recall.md                # Natural language recall
│   ├── vault-review.md                # Periodic review
│   ├── vault-capture.md               # Quick capture
│   ├── vault-daily.md                 # Daily notes
│   ├── vault-search.md                # Search
│   ├── vault-align.md                 # Vault health
│   ├── vault-compile.md               # Thin evidence-bound compiler adapter
│   └── vault-setup.md                 # Setup wizard
├── skills/
│   ├── second-brain/                  # PKM methodology
│   ├── vault-templates/               # Note archetypes
│   ├── vault-alignment/               # Health monitoring
│   ├── knowledge-compiler/            # Canonical Claude Code/Codex compilation contract
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
│       ├── vault-read-hint.py         # PostToolUse Read implementation
│       └── vault_resolve.py           # Shared vault-path resolution (env var → obsidian.json → iCloud)
├── setup/
│   └── manifest.json                  # Opt-in capabilities for /rhize-core:setup (currently empty)
└── README.md
```

Tests live at the repo root, not under this plugin: `tests/obsidian-second-brain/test_compiled_knowledge.py`
(policy, CAS, recovery, purge, parity fixtures) and `tests/obsidian-second-brain/test_vault_resolve.py`
(vault-path resolution + hook-script integration tests).

## Sources

- [Official Obsidian CLI docs](https://help.obsidian.md/cli)
- [kepano/obsidian-skills](https://github.com/kepano/obsidian-skills) (MIT License)
- [JSON Canvas Spec](https://jsoncanvas.org)
- [qmd — local-first search engine](https://github.com/tobi/qmd)
