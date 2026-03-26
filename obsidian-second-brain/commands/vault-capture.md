---
description: Quick-capture a note, idea, or task to your Obsidian vault
allowed-tools: ["mcp__obsidian-mcp-server__obsidian_update_note", "mcp__obsidian-mcp-server__obsidian_manage_frontmatter", "mcp__obsidian-mcp-server__obsidian_manage_tags", "Bash"]
argument-hint: <content to capture>
---

Quick-capture content to the user's Obsidian vault. Use CLI commands where they provide a cleaner path — they handle daily note resolution, task creation, and template application automatically.

Analyze "$ARGUMENTS" and determine the best capture method:

**If it's a task** (contains "todo", "task", "remind", or starts with action verb):
- Run `obsidian task:create content="<task text>"` to create a tracked task.
- Add tags if context suggests them: `obsidian task:create content="<task>" tags="work,urgent"`
- For appending to the daily note instead: `obsidian daily:append content="- [ ] <task>"`

**If it's an idea or thought** (short, conceptual):
- Run `obsidian daily:append content="## Ideas\n- <idea>"` to add under an Ideas heading in today's note.
- If the user prefers a separate note, use `obsidian create name="<idea title>" content="<content>"`.

**If it's substantial content** (multiple paragraphs, structured):
- Run `obsidian create name="<descriptive title>" content="<content>"` to create a standalone note.
- Set properties after creation: `obsidian properties:set file="<title>" tags="<relevant,tags>" type=tags`
- If a template is appropriate: `obsidian create name="<title>" template="<template name>"`
- Fall back to obsidian_update_note with obsidian_manage_frontmatter if CLI is unavailable.

**If it's a web URL** (starts with http):
- Extract clean content first: `defuddle parse <url> --md`
- Pipe to Obsidian: `obsidian create name="<page title>" content="$(defuddle parse <url> --md)"`
- Or use `defuddle parse <url> -p title` to auto-name the note.

Always confirm what was captured and where it was saved.
