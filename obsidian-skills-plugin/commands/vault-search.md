---
description: Search your Obsidian vault for notes, tags, or content
allowed-tools: ["mcp__obsidian-mcp-server__obsidian_global_search", "mcp__obsidian-mcp-server__obsidian_read_note", "mcp__obsidian-mcp-server__obsidian_list_notes", "Bash"]
argument-hint: <search query>
---

Search the user's Obsidian vault for "$ARGUMENTS". Use qmd for semantic search when available, with MCP and CLI as fallbacks and for structured queries.

## Step 1: Detect qmd Availability

Before choosing a search strategy, check if qmd is installed and the vault is indexed:

```bash
# Check if qmd is installed
command -v qmd >/dev/null 2>&1 && QMD_AVAILABLE=true || QMD_AVAILABLE=false

# If installed, check if a vault collection exists
if [ "$QMD_AVAILABLE" = true ]; then
  qmd status vault 2>/dev/null && QMD_INDEXED=true || QMD_INDEXED=false
fi
```

If qmd is not available or not indexed, fall back to MCP/CLI search for all query types (see "Fallback Search" below).

## Step 2: Determine Search Strategy

**General text / concept search** (qmd available):
- Use `qmd search vault "<query>"` for keyword-precise searches (BM25). Best when the user knows the exact terms.
- Use `qmd vsearch vault "<query>"` for conceptual/semantic searches. Best when the user describes an idea rather than exact words.
- Use `qmd query vault "<query>"` for natural language questions. Best for "what do I know about X?" or "find notes related to Y". This uses LLM re-ranking and is the highest quality but slowest.
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
- Use obsidian_global_search for full-text search — it returns rich context snippets.
- Alternatively, `obsidian search query="<query>" format=json` provides structured output for processing.

All tag, property, link-based, and broken content searches work the same regardless of qmd availability.

## Step 3: Present Results

After running the search:
1. Summarize the top 5 most relevant results — show file path, a snippet of the match context, and any relevant properties.
2. If qmd was used, mention the search mode (BM25 / vector / hybrid) so the user knows they can refine.
3. Mention total result count and offer to show more.
4. Offer to read the full content of any specific result the user is interested in.
5. If qmd returned poor results for a keyword search, suggest trying `vsearch` (semantic) instead, and vice versa.
