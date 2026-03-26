---
description: Research a topic or URL — clip, summarize, and connect to your vault
allowed-tools: ["mcp__obsidian-mcp-server__obsidian_global_search", "mcp__obsidian-mcp-server__obsidian_update_note", "mcp__obsidian-mcp-server__obsidian_read_note", "mcp__obsidian-mcp-server__obsidian_manage_frontmatter", "mcp__obsidian-mcp-server__obsidian_manage_tags", "Bash", "WebFetch", "WebSearch"]
argument-hint: <url or topic to research>
---

End-to-end research pipeline: capture source material, summarize it, and connect it to existing vault knowledge. This command orchestrates the full "capture → process → connect" workflow that turns raw information into linked knowledge.

Parse "$ARGUMENTS" to determine the research type:

**If it's a URL:**
1. **Extract** — Run `defuddle parse <url> --md` to get clean markdown content. Also extract the title: `defuddle parse <url> -p title`. If defuddle fails (e.g., JS-heavy site), fall back to WebFetch.
2. **Create the note** — Run `obsidian create name="<title>" content="<extracted content>"`. Save to a Research or Resources folder if one exists.
3. **Add metadata** — Set properties:
   ```bash
   obsidian properties:set file="<title>" type=literature
   obsidian properties:set file="<title>" source="<url>"
   obsidian properties:set file="<title>" date-clipped={{today}} type=date
   obsidian properties:set file="<title>" status=processing
   obsidian properties:set file="<title>" tags="research,<inferred-topic>" type=tags
   ```
4. **Summarize** — Read the extracted content and write a 3-5 sentence summary. Prepend it as a callout at the top of the note:
   ```
   > [!abstract] Summary
   > The summary goes here.
   ```
5. **Find connections** — Run `obsidian search query="<key terms from the content>"` and `obsidian search query="[tag:<relevant-tag>]"` to find existing vault notes that relate to this content.
6. **Suggest links** — Present the top 3-5 related notes and ask the user which connections to make. For each confirmed connection, append a `[[wikilink]]` to a Connections section at the bottom of the new note.
7. **Daily note reference** — Run `obsidian daily:append content="- Researched: [[<title>]]"` to log the research in today's daily note.

**If it's a topic (not a URL):**
1. **Search the web** — Use WebSearch to find 3-5 high-quality sources on the topic.
2. **Present sources** — Show titles, URLs, and brief descriptions. Ask the user which sources to process.
3. **Process each selected source** — Follow the URL pipeline above for each one.
4. **Synthesize** — After processing all sources, offer to create a synthesis note or MOC that links them together with the user's own observations.

**If it's a topic that should search the vault first:**
If the user says something like "research what I already have on X" or "pull together my notes on X":
1. **Search vault** — Run `obsidian search query="<topic>"` and `obsidian tag tagname=<topic>` to find existing notes.
2. **Read and summarize** — Read the top results and synthesize key themes.
3. **Identify gaps** — Note what the vault covers well and what's missing.
4. **Offer next steps** — Suggest creating a MOC, filling gaps with web research, or writing permanent notes from the material.

After completing any research flow, always:
- Confirm what was saved and where
- Show the connections that were made
- Suggest next processing steps (e.g., "You could write a permanent note about the key insight on X")
