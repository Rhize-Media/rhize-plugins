---
description: Search your Obsidian vault for notes, tags, or content
allowed-tools: ["mcp__obsidian-mcp-server__obsidian_global_search", "mcp__obsidian-mcp-server__obsidian_read_note", "mcp__obsidian-mcp-server__obsidian_list_notes", "Bash"]
argument-hint: <search query>
---

Search the user's Obsidian vault for "$ARGUMENTS". Use both MCP and CLI tools depending on the query type — the CLI offers powerful filters for tags and properties that MCP search doesn't expose.

Determine the best search strategy:

**General text search:**
- Use obsidian_global_search for full-text search — it returns rich context snippets.
- Alternatively, `obsidian search query="<query>" format=json` provides structured output for processing.

**Tag search** (query starts with # or user says "tag"):
- Run `obsidian tag tagname=<tagname>` to find all notes with that tag.
- For tag hierarchy exploration: `obsidian tags sort=count` shows all tags ranked by frequency.

**Property/metadata search** (user asks about status, type, date, or any frontmatter field):
- Run `obsidian search query="[<property>:<value>]"` — this filters by frontmatter properties.
- Examples: `obsidian search query="[status:active]"`, `obsidian search query="[type:project]"`

**Link-based search** (user asks "what links to X" or "what does X link to"):
- Run `obsidian backlinks file="<note>"` for incoming links.
- Run `obsidian links file="<note>"` for outgoing links.

**Finding broken or missing content:**
- `obsidian unresolved` for broken wikilinks.
- `obsidian orphans` for disconnected notes.

After running the search:
1. Summarize the top 5 most relevant results — show file path, a snippet of the match context, and any relevant properties.
2. Mention total result count and offer to show more.
3. Offer to read the full content of any specific result the user is interested in.
