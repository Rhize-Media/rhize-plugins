---
description: Analyze vault health — find orphans, broken links, tag stats
allowed-tools: ["mcp__obsidian-mcp-server__obsidian_global_search", "mcp__obsidian-mcp-server__obsidian_list_notes", "mcp__obsidian-mcp-server__obsidian_read_note", "mcp__obsidian-mcp-server__obsidian_manage_tags", "Bash"]
argument-hint: [tags|structure|orphans|links|full]
---

Analyze and report on vault organization. Use the Obsidian CLI for vault-level analysis commands — they are faster and more complete than searching manually.

Parse "$ARGUMENTS" to determine scope:

**"tags" or "tag stats":**
- Run `obsidian tags sort=count format=json` to get all tags ranked by frequency.
- Report: most-used tags, tag hierarchy structure, potential duplicates or inconsistencies (e.g., "meeting" vs "meetings").
- Suggest tag renames using `obsidian tags:rename old=<old> new=<new>` (confirm with user first).

**"orphans":**
- Run `obsidian orphans` to find notes with zero incoming or outgoing links.
- Present the list grouped by folder and suggest whether each orphan should be linked, archived, or deleted.

**"links" or "broken links":**
- Run `obsidian unresolved` to find all broken/unresolved wikilinks across the vault.
- Report each broken link with its source note so the user can fix or remove them.

**"structure" or no arguments:**
- Run `obsidian folders format=tree` for the directory hierarchy.
- Run `obsidian files total` for the vault-wide note count.
- Use obsidian_list_notes at the root with recursionDepth=1 for per-folder file counts.
- Report folder sizes, identify very large or very small folders, and suggest organizational improvements.

**"full" or "audit":**
- Run all of the above in sequence: structure → tags → orphans → links.
- Present a comprehensive vault health report with actionable recommendations.

Always present findings in a clean summary. When suggesting changes (tag renames, orphan cleanup), confirm with the user before executing any modifications.
