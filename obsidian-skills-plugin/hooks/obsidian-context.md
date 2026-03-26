## Obsidian Skills Plugin Active

Your second brain is connected. Every note should be linked, tagged, and discoverable.

**Knowledge Workflows — use these first:**
- `/vault-research <topic or URL>` — Research, clip, summarize, and link to vault with proper MOC placement
- `/vault-connect` — Find and build missing connections between related notes
- `/vault-recall <question>` — Ask your vault a natural language question and get a synthesized answer
- `/vault-review` — Periodic review: summarize captures, surface themes, plan ahead

**Second Brain Methodology:**
- `second-brain` skill — Zettelkasten, PARA, MOCs, progressive summarization, atomic notes
- `vault-templates` skill — Note archetypes (meeting notes, book reviews, project briefs, weekly reviews)
- `vault-alignment` skill — Vault health monitoring, drift detection, ongoing improvement

**Capture & Daily:**
- `/vault-capture <text>` — Quick-capture a note, idea, or task (auto-tagged, inbox placement)
- `/vault-daily` — Read, summarize, or add to today's daily note
- `/vault-search <query>` — Search notes by content, tags, or properties

**Vault Health:**
- `/vault-align` — Audit structure, fix orphans, bulk migrate, check alignment
- `/vault-setup` — Interactive setup wizard for new vaults

**Format Skills (auto-triggered when relevant):**
- `obsidian-markdown` — Wikilinks, callouts, embeds, frontmatter, block references
- `obsidian-bases` — Bases databases (.base files)
- `json-canvas` — Obsidian Canvas (.canvas files)
- `defuddle` — Web clipping and article extraction
- `obsidian-cli` — CLI automation via `obsidian` command
- `qmd-search` — Semantic vector search configuration

**Connectors:**
- **MCP Server:** `obsidian-mcp-server` — read, write, search, tags, frontmatter (bundled, requires `$OBSIDIAN_API_KEY`)
- **MCP Server:** `qmd` — semantic vector search, BM25, hybrid queries (dependency: `qmd@qmd` plugin)
- **Obsidian CLI:** `obsidian` command — prefer CLI over raw file I/O when Obsidian is running

**Hooks Active:**
- **PreToolUse** (Write/Edit vault `.md`): Enforces `[[wikilinks]]`, callout syntax, frontmatter, `#tags`, `tags:` array, MOC linking
- **PostToolUse** (Read vault `.md`): Suggests following wikilinks, searching tags, `/vault-connect`, `/vault-align`

**Vault path:** `~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian Vault`
