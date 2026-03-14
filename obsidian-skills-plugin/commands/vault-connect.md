---
description: Find and build missing connections between related vault notes
allowed-tools: ["mcp__obsidian-mcp-server__obsidian_global_search", "mcp__obsidian-mcp-server__obsidian_read_note", "mcp__obsidian-mcp-server__obsidian_update_note", "mcp__obsidian-mcp-server__obsidian_list_notes", "mcp__obsidian-mcp-server__obsidian_manage_frontmatter", "Bash"]
argument-hint: [note name|topic|recent]
---

Actively build connections in the vault's knowledge graph. While `/vault-organize` diagnoses disconnection, this command fixes it — finding semantically related notes that should be linked and offering to weave them together.

Parse "$ARGUMENTS" to determine the starting point:

**If a specific note is named:**
1. **Read the note** — Use obsidian_read_note to get its full content and properties.
2. **Extract key concepts** — Identify the main topics, claims, and entities in the note.
3. **Search for related notes** — Run multiple searches to cast a wide net:
   - `obsidian search query="<key concept 1>"` for content matches
   - `obsidian search query="<key concept 2>"` for additional concept matches
   - `obsidian tag tagname=<relevant-tag>` for notes sharing the same tags
   - `obsidian backlinks file="<note>"` to see what already links here
   - `obsidian links file="<note>"` to see what it already links to
4. **Filter out existing connections** — Remove notes that are already linked (via wikilinks or backlinks).
5. **Rank by relevance** — Read the top candidate notes and assess genuine semantic connection, not just keyword overlap.
6. **Present suggestions** — Show each suggested connection with:
   - The note name
   - A one-sentence explanation of why they're related
   - A suggested link direction (which note should reference which)
7. **Apply connections** — For each connection the user approves, append a wikilink to the appropriate section of both notes (or just one, based on user preference). Use `obsidian append` for the target note.
8. **Check for MOC opportunity** — If 5+ notes are now clustered around a theme with no existing MOC, suggest creating one.

**If "recent" or no arguments:**
1. **Get recent notes** — Run `obsidian files sort=modified limit=10 format=json` to find the 10 most recently modified notes.
2. **Filter out daily notes and MOCs** — Focus on content notes that might be under-linked.
3. **Check link density** — For each note, run `obsidian backlinks file="<note>"` and `obsidian links file="<note>"`. Flag notes with 0-1 connections as candidates.
4. **Process the most isolated notes** — For the top 3-5 under-linked notes, follow the "specific note" workflow above.
5. **Report** — Summarize what was found and connected.

**If a topic is given:**
1. **Find all notes on the topic** — Combine search and tag queries to find the cluster.
2. **Map existing connections** — For each note in the cluster, check which other cluster notes it already links to.
3. **Identify missing links** — Find pairs of notes that discuss related aspects of the topic but don't link to each other.
4. **Suggest a connection plan** — Present the missing links as a batch, grouped by relatedness.
5. **Check for MOC** — If a MOC exists for this topic, suggest adding any unlinked notes to it. If no MOC exists and there are 5+ notes, suggest creating one.

**Bridge notes (for any mode):**
After finding connections, look for "bridge" opportunities — notes that could connect two otherwise isolated clusters. For example, if the user has a cluster about "marketing" and a cluster about "psychology" with no links between them, a note about "persuasion techniques" could bridge them. Surface these opportunities when found.

Always:
- Show proposed connections before making changes
- Explain why each connection is suggested (not just "these share keywords")
- Confirm with the user before modifying any notes
- Report a summary of connections made at the end
