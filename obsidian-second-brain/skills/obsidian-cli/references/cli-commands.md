# Obsidian CLI — Complete Command Reference

This reference covers every documented command, flag, and option for the official Obsidian CLI (v1.12.4+, released February 27, 2026).

## Table of Contents

1. [Global Options](#global-options)
2. [Files & Folders](#files--folders)
3. [Search](#search)
4. [Daily Notes](#daily-notes)
5. [Properties](#properties)
6. [Tags](#tags)
7. [Links & Graph](#links--graph)
8. [Tasks](#tasks)
9. [Plugins](#plugins)
10. [Themes & Snippets](#themes--snippets)
11. [Sync](#sync)
12. [Publish](#publish)
13. [History](#history)
14. [Developer Tools](#developer-tools)
15. [TUI Mode](#tui-mode)

---

## Global Options

These flags can be appended to most commands:

| Flag | Description |
|------|-------------|
| `vault="Name"` | Target a specific vault (required when multiple vaults exist) |
| `vault="*"` | Query across all vaults |
| `format=json\|csv\|md\|paths\|yaml\|tree\|tsv` | Output format |
| `--copy` | Copy output to system clipboard |
| `--silent` | Suppress confirmation output |

### File Targeting

Two methods to specify which note to operate on:

| Method | Syntax | Behavior |
|--------|--------|----------|
| Wikilink | `file="Note Name"` | Resolves like `[[Note Name]]` — finds best match |
| Exact path | `path="folder/Note.md"` | Exact vault-relative path |

---

## Files & Folders

### `files`
List vault notes.

```
obsidian files
obsidian files folder=Projects/Active
obsidian files total
obsidian files format=paths
```

| Parameter | Description |
|-----------|-------------|
| `folder=` | Restrict to folder path |
| `total` | Return count only |
| `format=` | Output format |

### `folders`
List vault directories.

```
obsidian folders
obsidian folders format=tree
```

### `read`
Read note contents.

```
obsidian read file="Note Name"
obsidian read path="Projects/Note.md"
obsidian read file="Note" --copy
```

| Flag | Description |
|------|-------------|
| `file=` | Wikilink-style name |
| `path=` | Exact vault path |
| `--copy` | Copy to clipboard |

### `create`
Create a new note.

```
obsidian create name="New Note"
obsidian create name="Script" template="YouTube Script"
obsidian create name="Note" path=Projects/
obsidian create name="Note" content="Initial text"
obsidian create name="Existing" content="replaced" --overwrite
obsidian create name="Draft" --silent
```

| Parameter | Description |
|-----------|-------------|
| `name=` | Note name (required) |
| `template=` | Template name to apply |
| `path=` | Target folder |
| `content=` | Initial content |
| `--overwrite` | Replace if exists |
| `--silent` | No output |

### `append`
Add text to end of note.

```
obsidian append file="Research" content="New paragraph"
obsidian append file="Log" content="- Entry\n- Another"
```

### `prepend`
Add text to beginning of note.

```
obsidian prepend file="Inbox" content="- [ ] New task"
```

### `move`
Relocate note (automatically updates all internal links).

```
obsidian move file="Draft" to=Archive/2026/
```

### `delete`
Delete a note.

```
obsidian delete file="Old Note"           # Moves to trash (safe)
obsidian delete file="Old" --permanent    # Irreversible
```

---

## Search

### `search`
Full-text search across vault.

```
obsidian search query="topic"
obsidian search query="meeting" limit=20
obsidian search query="PKM" format=json
```

**Special query filters:**

| Filter | Syntax | Example |
|--------|--------|---------|
| Tag | `[tag:name]` | `query="[tag:publish]"` |
| Property | `[key:value]` | `query="[status:active]"` |

### `search:open`
Open search results in Obsidian GUI.

```
obsidian search:open query="[tag:review]"
```

---

## Daily Notes

### `daily`
Open today's daily note (creates if missing).

```
obsidian daily
```

### `daily:read`
Display today's note content.

```
obsidian daily:read
obsidian daily:read --copy
```

### `daily:append`
Append content to today's note.

```
obsidian daily:append content="- [ ] Buy groceries"
obsidian daily:append content="## Evening\nReflection here"
```

### `daily:prepend`
Prepend content to today's note.

```
obsidian daily:prepend content="Morning priorities:\n"
```

### `daily:open`
Open a specific date's note.

```
obsidian daily:open date=2026-02-15
```

### `daily:path`
Get the filesystem path of today's note.

```
obsidian daily:path
```

---

## Properties

### `properties`
Read all YAML frontmatter properties from a note.

```
obsidian properties file="Project"
obsidian properties file="Project" format=json
```

### `properties:set`
Set or update a property.

```
obsidian properties:set file="Draft" status=active
obsidian properties:set file="Article" published=2026-02-28 type=date
obsidian properties:set file="Video" tags="pkm,obsidian" type=tags
obsidian properties:set file="Task" done=true type=checkbox
obsidian properties:set file="Count" views=42 type=number
```

**Supported types:** text, list, number, checkbox, date, tags

### `properties:remove`
Delete a property key.

```
obsidian properties:remove file="Draft" key=draft
```

---

## Tags

### `tags`
List all tags in vault.

```
obsidian tags
obsidian tags sort=count
obsidian tags format=json
```

### `tag`
Find notes with a specific tag.

```
obsidian tag tagname=pkm
obsidian tag tagname=projects/active
```

### `tags:rename`
Rename a tag across the entire vault.

```
obsidian tags:rename old=meeting new=meetings
```

---

## Links & Graph

### `links`
Outgoing links from a note.

```
obsidian links file="Note"
```

### `backlinks`
Notes that link TO a given note.

```
obsidian backlinks file="Note"
```

### `unresolved`
Find broken/unresolved wikilinks.

```
obsidian unresolved
obsidian unresolved format=json
```

### `orphans`
Notes with no incoming or outgoing links.

```
obsidian orphans
```

---

## Tasks

### `tasks`
List all open tasks in vault.

```
obsidian tasks
obsidian tasks format=json
```

### `task:create`
Create a new task.

```
obsidian task:create content="Write newsletter"
obsidian task:create content="Call client" tags="work,urgent"
```

### `task:complete`
Mark a task as done.

```
obsidian task:complete task=task-id
```

---

## Plugins

### `plugins`
List all installed plugins.

```
obsidian plugins
obsidian plugins format=json
```

### `plugin:enable`
Enable a plugin by ID.

```
obsidian plugin:enable id=dataview
```

### `plugin:disable`
Disable a plugin.

```
obsidian plugin:disable id=calendar
```

### `plugin:reload`
Reload a plugin (useful during development).

```
obsidian plugin:reload id=my-dev-plugin
```

---

## Themes & Snippets

### `themes`
List available themes.

```
obsidian themes
```

### `theme:set`
Switch the active theme.

```
obsidian theme:set name="Minimal"
```

### `snippets`
List CSS snippets.

```
obsidian snippets
```

### `snippet:enable` / `snippet:disable`
Toggle a CSS snippet.

```
obsidian snippet:enable name="custom-fonts"
obsidian snippet:disable name="custom-fonts"
```

---

## Sync

### `sync:status`
Check Obsidian Sync state.

```
obsidian sync:status
```

### `sync:history`
View sync version history for a note.

```
obsidian sync:history file="Note"
```

### `sync:restore`
Restore a synced version.

```
obsidian sync:restore file="Note" version=3
```

---

## Publish

### `publish:list`
List all published notes.

```
obsidian publish:list
```

### `publish:add`
Publish a note.

```
obsidian publish:add file="Blog Post"
```

### `publish:remove`
Unpublish a note.

```
obsidian publish:remove file="Old Post"
```

### `publish:status`
View publish queue status.

```
obsidian publish:status
```

---

## History

### `history`
View local version history for a note.

```
obsidian history file="Note"
```

### `history:read`
Read a specific historical version.

```
obsidian history:read file="Note" version=2
```

### `history:restore`
Restore a local version.

```
obsidian history:restore file="Note" version=2
```

---

## Developer Tools

### `eval`
Execute JavaScript in the Obsidian runtime.

```
obsidian eval code="app.vault.getFiles().length"
obsidian eval code="Object.keys(app.plugins.plugins).join(', ')"
obsidian eval code="app.workspace.getActiveFile()?.path"
```

### `dev:screenshot`
Capture the Obsidian window.

```
obsidian dev:screenshot path=~/vault.png
```

### `dev:console`
View recent console output.

```
obsidian dev:console limit=50
obsidian dev:console level=error
```

### `dev:errors`
Show all errors.

```
obsidian dev:errors
```

### `dev:css`
Inspect computed CSS for a selector.

```
obsidian dev:css selector=".markdown-preview-view"
```

### `dev:dom`
Inspect DOM elements.

```
obsidian dev:dom selector=".workspace-leaf"
```

---

## TUI Mode

Launch with `obsidian` (no arguments) for a full-screen interactive vault browser.

| Key | Action |
|-----|--------|
| ↑ / ↓ | Navigate |
| Enter | Open in Obsidian |
| `/` | Search |
| Esc | Clear search |
| `n` | Create note |
| `d` | Delete (with confirm) |
| `r` | Rename inline |
| Tab | Autocomplete |
| Ctrl+R | Reverse history |
| Ctrl+C | Cancel |
| `q` | Quit |
