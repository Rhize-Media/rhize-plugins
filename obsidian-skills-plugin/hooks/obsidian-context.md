## Obsidian Skills Plugin Active

Your vault tools are loaded. Use them whenever working with notes, markdown, or knowledge management.

**Quick Capture & Daily:**
- `/vault-capture <text>` — Quick-capture a note, idea, or task
- `/vault-daily` — Read, summarize, or add to today's daily note

**Search & Recall:**
- `/vault-search <query>` — Search notes by content, tags, or properties
- `/vault-recall <question>` — Ask your vault a natural language question (qmd semantic search)

**Research & Connect:**
- `/vault-research <topic or URL>` — Research, clip, summarize, and link to vault
- `/vault-connect` — Find and build missing connections between notes

**Review & Maintain:**
- `/vault-review` — Periodic review: summarize captures, surface themes
- `/vault-align` — Vault health: audit structure, fix issues, bulk migrate
- `/vault-setup` — Interactive setup wizard for new vaults

**Skills (auto-triggered):**
- `obsidian-markdown` — Obsidian-flavored markdown syntax (wikilinks, callouts, embeds)
- `obsidian-bases` — Bases databases (.base files)
- `json-canvas` — Obsidian Canvas (.canvas files)
- `obsidian-cli` — CLI automation via `obsidian` command
- `qmd-search` — Semantic vector search via qmd
- `defuddle` — Web clipping and article extraction
- `second-brain` — PKM methodology (Zettelkasten, MOCs, progressive summarization)
- `vault-templates` — Note templates and archetypes
- `vault-alignment` — Vault health monitoring and optimization

**MCP Servers:** `obsidian-mcp-server` (read/write/search/tags/frontmatter), `qmd` (semantic search)

**Hooks Active:**
- **PreToolUse** (Write/Edit vault `.md`): Enforces `[[wikilinks]]`, callout syntax, frontmatter preservation, `#tags`, `tags:` array, and MOC linking
- **PostToolUse** (Read vault `.md`): Suggests following wikilinks, searching tags, `/vault-connect` for related notes, `/vault-align` for orphan/health checks

**Vault path:** `~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian Vault`
