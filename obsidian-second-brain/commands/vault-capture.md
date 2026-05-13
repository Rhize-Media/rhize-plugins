---
description: Quick-capture a note, idea, or task to your Obsidian vault
allowed-tools: ["mcp__obsidian-mcp-server__obsidian_update_note", "mcp__obsidian-mcp-server__obsidian_manage_frontmatter", "mcp__obsidian-mcp-server__obsidian_manage_tags", "Bash", "Read", "Write", "Edit", "Glob", "Grep", "mcp__workspace__web_fetch", "WebFetch", "WebSearch"]
argument-hint: <content to capture>
---

Quick-capture content to the user's Obsidian vault. Use CLI commands where they provide a cleaner path — they handle daily note resolution, task creation, and template application automatically.

## Tool Availability & Fallback Strategy

Before invoking any tool, follow this preference order — drop to the next tier if a tool is missing:

1. **Obsidian MCP** (`mcp__obsidian-mcp-server__*`) — preferred for structured operations (tags, frontmatter, note management). Skip silently if not connected.
2. **Obsidian CLI** (`obsidian` Bash command) — preferred for daily-note operations and template-aware creation. Probe with `command -v obsidian >/dev/null 2>&1` first.
3. **Defuddle CLI** (`defuddle` Bash command) — preferred for web URL extraction. Probe with `command -v defuddle >/dev/null 2>&1` first.
4. **Native tools** (`Write`, `Edit`, `Read`, `Glob`, `mcp__workspace__web_fetch`) — **ALWAYS AVAILABLE** universal fallback. Use these when MCP/CLI aren't available so the command never silently fails.

**Vault path resolution (when using native tools):** the vault root is `~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian Vault`. Use `Glob` to discover folder structure (`Areas/`, `Resources/`, `Projects/`, etc.) and pick the most semantically appropriate destination based on content type. For reference material like articles, prefer `Areas/<Domain>/Resources/<Topic>/` over `Projects/`.

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
- **Preferred:** Extract with `defuddle parse <url> --md` and create with `obsidian create name="<page title>" content="$(defuddle parse <url> --md)"`. Use `defuddle parse <url> -p title` to auto-name.
- **Fallback (defuddle missing):** Use `mcp__workspace__web_fetch` with the URL, parse the returned markdown for title and content, then `Write` the file directly to the appropriate vault folder (use `Glob` to discover folder structure first).
- **Fallback (obsidian CLI missing):** Use `Write` to create the note as a `.md` file with YAML frontmatter (`type: literature-note`, `source: <url>`, `captured: <date>`, `tags: [...]`) directly under the appropriate `Areas/<Domain>/Resources/<Topic>/` folder. Update any `_index.md` MOC in that folder using `Edit` to add a link to the new note.

Always confirm what was captured and where it was saved.
