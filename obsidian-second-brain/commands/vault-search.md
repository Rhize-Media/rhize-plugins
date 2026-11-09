---
description: Search your Obsidian vault for notes, tags, or content
allowed-tools: ["mcp__obsidian-mcp-server__obsidian_search_notes", "mcp__obsidian-mcp-server__obsidian_get_note", "mcp__obsidian-mcp-server__obsidian_list_notes", "Bash", "Read", "Glob", "Grep"]
argument-hint: <search query>
model: haiku
---

Search the user's Obsidian vault for "$ARGUMENTS". Use qmd for semantic search when available, with MCP and CLI as fallbacks and for structured queries.

## Step 1: Detect qmd Availability

Load `qmd-search` and its [approved indexing procedure](../skills/qmd-search/references/approved-indexing.md).
Read `QMD_INDEX` and `QMD_COLLECTION` from the approved setup record; verify installed CLI,
actual collection path/mask, indexed members and embedding readiness before choosing qmd.
Never guess a default `vault` collection, create an index while searching, or treat status's
exit code as evidence of scope/freshness. Keep compiler output and private state unindexed.
If qmd is unavailable or scope cannot be verified, use MCP/CLI/filesystem search bounded to the
same authorized note scope. Never silently broaden fallback search to the whole vault.

## Step 2: Determine Search Strategy

**General text / concept search** (qmd available):
- Use `qmd --index "${QMD_INDEX:?set approved index}" search "<query>" -c "${QMD_COLLECTION:?set approved collection}"` for keyword-precise searches (BM25). Best when the user knows the exact terms.
- Use `qmd --index "${QMD_INDEX:?set approved index}" vsearch "<query>" -c "${QMD_COLLECTION:?set approved collection}"` for conceptual/semantic searches. Best when the user describes an idea rather than exact words.
- Use `qmd --index "${QMD_INDEX:?set approved index}" query "<query>" -c "${QMD_COLLECTION:?set approved collection}"` for natural language questions. Best for "what do I know about X?" or "find notes related to Y". This uses LLM re-ranking and adds ranking work and may be slower.
- **Choosing the right mode**: If the query contains specific terms, names, or property values → BM25 (`search`). If the query is a concept, idea, or question → vector (`vsearch`). If the query is a complex question where ranking matters → hybrid (`query`).

**Tag search** (query starts with # or user says "tag"):
- Tags are structured metadata — always use MCP/CLI for these, even when qmd is available.
- Run `obsidian tag tagname=<tagname>` to find all notes with that tag.
- For tag hierarchy exploration: `obsidian tags sort=count` shows all tags ranked by frequency.

**Property/metadata search** (user asks about status, type, date, or any frontmatter field):
- Properties are structured data — always use MCP/CLI for these.
- Run `obsidian search query="[<property>:<value>]"` — this filters by frontmatter properties.
- Examples: `obsidian search query="[status:active]"`, `obsidian search query="[type:project]"`

**Link-based search** (user asks "what links to X" or "what does X link to"):
- Run `obsidian backlinks file="<note>"` for incoming links.
- Run `obsidian links file="<note>"` for outgoing links.

**Finding broken or missing content:**
- `obsidian unresolved` for broken wikilinks.
- `obsidian orphans` for disconnected notes.

## Fallback Search (no qmd)

When qmd is not available, use the original MCP/CLI search stack:

**General text search:**
- Use obsidian_search_notes (`mode: "text"`) for full-text search — it returns context snippets around each match.
- Alternatively, `obsidian search query="<query>" format=json` provides structured output for processing.

All tag, property, link-based, and broken content searches work the same regardless of qmd availability.

## Step 3: Present Results

After running the search:
1. Summarize the top 5 most relevant results — show file path, a snippet of the match context, and any relevant properties.
2. If qmd was used, mention the search mode (BM25 / vector / hybrid) so the user knows they can refine.
3. Mention total result count and offer to show more.
4. Offer to read the full content of any specific result the user is interested in.
5. If qmd returned poor results for a keyword search, suggest trying `vsearch` (semantic) instead, and vice versa.
