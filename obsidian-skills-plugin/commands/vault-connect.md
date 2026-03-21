---
description: Find and build missing connections between related vault notes
allowed-tools: ["mcp__obsidian-mcp-server__obsidian_global_search", "mcp__obsidian-mcp-server__obsidian_read_note", "mcp__obsidian-mcp-server__obsidian_update_note", "mcp__obsidian-mcp-server__obsidian_list_notes", "mcp__obsidian-mcp-server__obsidian_manage_frontmatter", "Bash"]
argument-hint: [note name|topic|recent]
---

Actively build connections in the vault's knowledge graph. While `/vault-organize` diagnoses disconnection, this command fixes it — finding semantically related notes that should be linked and offering to weave them together.

**Uses qmd vector search when available** for dramatically better connection discovery. Instead of relying on keyword overlap alone, qmd's `vsearch` finds notes that are conceptually related even when they use different terminology.

## Step 0: Detect qmd Availability

```bash
command -v qmd >/dev/null 2>&1 && QMD_AVAILABLE=true || QMD_AVAILABLE=false
if [ "$QMD_AVAILABLE" = true ]; then
  qmd status vault 2>/dev/null && QMD_INDEXED=true || QMD_INDEXED=false
fi
```

Parse "$ARGUMENTS" to determine the starting point:

## If a specific note is named:

1. **Read the note** — Use obsidian_read_note to get its full content and properties.
2. **Extract key concepts** — Identify the main topics, claims, and entities in the note.
3. **Search for related notes** — Cast a wide net using the best available tools:

   **With qmd (preferred):**
   - `qmd vsearch vault "<summary of the note's core ideas>"` — finds semantically similar notes regardless of keyword overlap. This is the primary connection discovery mechanism.
   - `qmd vsearch vault "<key concept 1>"` and `qmd vsearch vault "<key concept 2>"` — targeted semantic searches for specific themes within the note.
   - Then supplement with MCP for structured data: `obsidian backlinks file="<note>"` to see what already links here, and `obsidian links file="<note>"` to see what it already links to.

   **Without qmd (fallback):**
   - `obsidian search query="<key concept 1>"` for content matches
   - `obsidian search query="<key concept 2>"` for additional concept matches
   - `obsidian tag tagname=<relevant-tag>` for notes sharing the same tags
   - `obsidian backlinks file="<note>"` to see what already links here
   - `obsidian links file="<note>"` to see what it already links to

4. **Filter out existing connections** — Remove notes that are already linked (via wikilinks or backlinks).
5. **Rank by relevance** — With qmd, results are already ranked by semantic similarity. Without qmd, read the top candidate notes and assess genuine semantic connection, not just keyword overlap.
6. **Present suggestions** — Show each suggested connection with:
   - The note name
   - A one-sentence explanation of why they're related
   - The similarity signal (qmd score if available, or the reasoning behind the connection)
   - A suggested link direction (which note should reference which)
7. **Apply connections** — For each connection the user approves, append a wikilink to the appropriate section of both notes (or just one, based on user preference). Use `obsidian append` for the target note.
8. **Check for MOC opportunity** — If 5+ notes are now clustered around a theme with no existing MOC, suggest creating one.

## If "recent" or no arguments:

1. **Get recent notes** — Run `obsidian files sort=modified limit=10 format=json` to find the 10 most recently modified notes.
2. **Filter out daily notes and MOCs** — Focus on content notes that might be under-linked.
3. **Check link density** — For each note, run `obsidian backlinks file="<note>"` and `obsidian links file="<note>"`. Flag notes with 0-1 connections as candidates.
4. **Process the most isolated notes** — For the top 3-5 under-linked notes, follow the "specific note" workflow above (including qmd vsearch if available).
5. **Report** — Summarize what was found and connected.

## If a topic is given:

1. **Find all notes on the topic:**
   - **With qmd**: Run `qmd vsearch vault "<topic>"` to find all semantically related notes — this catches notes that discuss the topic using different terminology.
   - **Without qmd**: Combine `obsidian search` and tag queries to find the cluster.
2. **Map existing connections** — For each note in the cluster, check which other cluster notes it already links to.
3. **Identify missing links** — Find pairs of notes that discuss related aspects of the topic but don't link to each other.
4. **Suggest a connection plan** — Present the missing links as a batch, grouped by relatedness.
5. **Check for MOC** — If a MOC exists for this topic, suggest adding any unlinked notes to it. If no MOC exists and there are 5+ notes, suggest creating one.

## Bridge Notes (for any mode)

After finding connections, look for "bridge" opportunities — notes that could connect two otherwise isolated clusters. **qmd makes this dramatically easier**: run `qmd vsearch` with a concept that spans two domains (e.g., "persuasion techniques" to bridge "marketing" and "psychology" clusters). Without qmd, bridge discovery relies on finding notes with tags or keywords from both clusters.

Surface bridge opportunities when found — these are among the highest-value connections in a knowledge graph.

## Always:
- Show proposed connections before making changes
- Explain why each connection is suggested (not just "these share keywords" — with qmd, explain the semantic relationship)
- Confirm with the user before modifying any notes
- Report a summary of connections made at the end
