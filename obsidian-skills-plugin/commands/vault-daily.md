---
description: Read, summarize, or add to today's daily note
allowed-tools: ["mcp__obsidian-mcp-server__obsidian_read_note", "mcp__obsidian-mcp-server__obsidian_update_note", "mcp__obsidian-mcp-server__obsidian_list_notes", "Bash"]
argument-hint: [read|add <content>|summarize]
---

Work with the user's daily note in Obsidian. Prefer the Obsidian CLI `daily:*` commands — they automatically resolve the correct daily note regardless of folder structure or date format settings.

Parse "$ARGUMENTS" to determine the action:

**"read" or no arguments:**
- Run `obsidian daily:read` to get today's note content. This resolves the daily note path automatically — no need to guess folder structures.
- If that fails, fall back to obsidian_list_notes to find the daily logs directory and obsidian_read_note to read the file.
- Present the content cleanly.

**"add <content>" or "append <content>":**
- Run `obsidian daily:append content="<the content>"` to append to today's note.
- Format tasks as checkboxes: `obsidian daily:append content="- [ ] <task>"`
- For multi-line content, use `\n` for line breaks in the content string.
- If CLI is unavailable, fall back to obsidian_update_note with wholeFileMode="append".

**"prepend <content>":**
- Run `obsidian daily:prepend content="<the content>"` to add content to the top.

**"summarize":**
- Run `obsidian daily:read` to get today's content.
- Provide a concise summary: key tasks (done/pending), main topics covered, any important notes or decisions.

**"yesterday" or "date <YYYY-MM-DD>":**
- Run `obsidian daily:open date=<date>` to access a specific day's note, then read its content.

**"path":**
- Run `obsidian daily:path` to show where the daily note lives on disk.

If the daily note doesn't exist yet, run `obsidian daily` to create it (this also applies the user's daily note template automatically).
