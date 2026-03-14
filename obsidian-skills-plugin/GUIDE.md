# Obsidian Skills Plugin — User Guide

This guide explains what the Obsidian Skills plugin does, how each piece works, and how to get the most out of it across Claude Desktop Chat, Cowork, and Claude Code.

## What This Plugin Does

The plugin teaches Claude how to work with your Obsidian vault. Without it, Claude has no knowledge of Obsidian's syntax, file formats, or CLI. With it, Claude can create properly-formatted notes, build database views, design visual canvases, clip web content, automate vault operations from the terminal, and answer questions about Obsidian's features with accurate, up-to-date information.

The plugin contains two types of components:

**Skills** are reference knowledge that Claude loads automatically when your request matches certain trigger phrases. You don't invoke them directly — Claude reads them behind the scenes to produce better output. Think of skills as "expertise modules."

**Commands** are actions you invoke explicitly with a slash prefix (e.g., `/vault-search`). They execute a specific workflow using your connected tools (Obsidian MCP Server, CLI, or both).

## Prerequisites

Before using this plugin, make sure the following are set up:

**Required for commands:**
The Obsidian MCP Server must be connected. This is the bridge that lets Claude read, search, and modify your vault in real time. Without it, the four slash commands will not function. You can install it from the MCP registry or via the Obsidian community plugins directory.

**Required for CLI skill:**
Obsidian v1.12.4 or later, with the CLI registered. Go to Settings → General → Command line interface → Register CLI. After registering, restart your terminal so the `obsidian` binary is on your PATH. Obsidian must be running in the background for CLI commands to execute — the CLI communicates with the running Obsidian instance over a local socket.

**Required for web clipping:**
The Defuddle CLI must be installed globally: `npm install -g defuddle`. This is only needed if you want to save web content into your vault.

## Skills Reference

### obsidian-cli

**When it activates:** You mention CLI commands, terminal operations, shell scripts, cron jobs, automation, or developer tools in the context of Obsidian.

**What it knows:** The complete Obsidian CLI command set — over 100 commands organized into files & folders, search, daily notes, properties, tags, links, tasks, plugins, themes, sync, publish, history, developer tools, and TUI mode. It includes a full command reference file (`references/cli-commands.md`) with every flag and option.

**How to use it effectively:**
- Ask Claude to "create a shell script that captures my clipboard to today's daily note" — it will use `obsidian daily:append`.
- Ask "how do I search for all notes tagged #project that have status:active" — it will combine `obsidian search query="[tag:project]"` with property filters.
- Ask "set up a cron job to check for orphan notes every Monday" — it will write the crontab entry using `obsidian orphans`.
- When building automations, tell Claude to use `format=json` for structured output that pipes cleanly into other tools.

**Key insight:** The CLI's `move` command updates all internal wikilinks automatically via the Obsidian runtime. This is a major advantage over file-system-level moves, which would break links.

### obsidian-markdown

**When it activates:** You mention wikilinks, embeds, callouts, frontmatter, properties, block references, comments, or any Obsidian formatting question.

**What it knows:** The full Obsidian-flavored Markdown spec — frontmatter/properties, wikilinks (`[[Note]]`), embed syntax (`![[Note]]`), heading/block references, callout types, comments, tags, math blocks, Mermaid diagrams, and how these differ from standard Markdown.

**How to use it effectively:**
- Ask Claude to "create a note with frontmatter for a book review" — it will produce properly-structured YAML with the right property types.
- Ask "embed a specific section of my Research note" — it will use `![[Research#Section Name]]`.
- Ask "what callout types does Obsidian support?" — it will list all built-in types with their icons and folding behavior.
- This skill also knows CLI commands for vault operations, so if you ask Claude to "create a new note with these properties," it can write the markdown AND execute the CLI command to save it.

### obsidian-bases

**When it activates:** You mention `.base` files, database views, filters, formulas, summaries, task trackers, reading lists, project dashboards, or structured data views.

**What it knows:** The complete `.base` file format — YAML structure, filter syntax (operators like `=`, `!=`, `contains`, `starts-with`, `is-empty`, date operators), formula expressions, property column configuration, summary aggregations (count, sum, average, min, max, etc.), and view types (table, board, gallery, calendar, list).

**How to use it effectively:**
- Ask "create a project tracker base that shows active projects sorted by due date" — it will generate a complete `.base` file with filters, column config, and sorting.
- Ask "build a reading list with a board view grouped by status" — it will create a Kanban-style board base.
- Ask "add a formula column that calculates days until deadline" — it will write the formula expression.
- For bulk data entry, this skill knows how to use CLI commands like `obsidian properties:set` to populate the frontmatter that bases query against.

### json-canvas

**When it activates:** You mention `.canvas` files, visual boards, node diagrams, mind maps, knowledge maps, or Obsidian whiteboard.

**What it knows:** The JSON Canvas Spec 1.0 — text nodes, file nodes, link nodes, group nodes, edges (connections) with labels and directional arrows, color coding, and spatial layout conventions.

**How to use it effectively:**
- Ask "create a canvas mapping my project architecture" — it will generate a `.canvas` file with properly-positioned nodes and labeled connections.
- Ask "build a mind map for my content strategy" — it will create a radial layout with a central node and branching topics.
- Ask "add a group around these related nodes" — it will wrap them in a group node with appropriate dimensions.
- Provide approximate positions (e.g., "put the database node on the left, the API in the middle, the frontend on the right") and Claude will translate those into x/y coordinates.

### defuddle

**When it activates:** You mention web clipping, saving articles, extracting web pages, converting URLs to markdown, or "clean HTML."

**What it knows:** The Defuddle CLI — parsing URLs to clean markdown, extracting metadata (title, author, date, description, word count), and piping extracted content into Obsidian via the CLI.

**How to use it effectively:**
- Ask "save this article to my vault: https://example.com/article" — it will extract clean markdown and create a note with proper frontmatter.
- Ask "clip this page and add it to today's daily note" — it will pipe the extraction through `obsidian daily:append`.
- For batch operations, ask "save all these URLs as separate notes" — it will loop through them using the `defuddle → obsidian create` pipeline.
- The `--md` flag gets markdown output; `-p title` extracts just the page title (useful for auto-naming notes).

## Commands Reference

### /vault-search

**Usage:** `/vault-search <query>`

Searches your vault using the best strategy for the query type. Full-text queries use the MCP global search. Tag queries (prefix with `#`) use `obsidian tag`. Property queries (like "status:active") use `obsidian search` with bracket syntax. You can also ask for backlinks, outgoing links, broken links, or orphan notes.

**Examples:**
- `/vault-search meeting notes from last week`
- `/vault-search #project`
- `/vault-search what links to my "Product Roadmap" note`
- `/vault-search broken links`

### /vault-capture

**Usage:** `/vault-capture <content>`

Captures content to your vault using the most appropriate method. Tasks get created with `obsidian task:create`. Short ideas append to the daily note. Substantial content becomes a standalone note. URLs get extracted with Defuddle first.

**Examples:**
- `/vault-capture todo: review the Q2 budget proposal`
- `/vault-capture Idea: what if we used a graph database for the recommendations engine?`
- `/vault-capture https://example.com/interesting-article`

### /vault-daily

**Usage:** `/vault-daily [read|add <content>|summarize|yesterday|path]`

Works with your daily note. The CLI resolves the correct daily note automatically regardless of your folder structure or date format settings, so this command works without any configuration.

**Examples:**
- `/vault-daily` or `/vault-daily read` — show today's note
- `/vault-daily add Met with Sarah about the rebrand timeline`
- `/vault-daily summarize` — get a concise summary of today's entries
- `/vault-daily yesterday` — read yesterday's note
- `/vault-daily path` — show where the daily note file lives on disk

### /vault-organize

**Usage:** `/vault-organize [tags|orphans|links|structure|full]`

Analyzes your vault health and organization. Each mode focuses on a different aspect; use `full` to run everything at once.

**Examples:**
- `/vault-organize tags` — tag frequency, hierarchy, duplicates
- `/vault-organize orphans` — notes with zero connections
- `/vault-organize links` — broken/unresolved wikilinks
- `/vault-organize structure` — folder tree, note counts, size distribution
- `/vault-organize full` — comprehensive audit with all of the above

## How the Skills Work Together

The skills are designed to cross-reference each other rather than operate in isolation. Here's how they connect:

**Markdown + CLI:** The markdown skill teaches Claude the correct syntax for notes, and the CLI skill teaches it how to execute operations. When you ask "create a note with callouts and tags for my meeting notes," Claude uses markdown knowledge to format the content correctly and CLI knowledge to run `obsidian create` and `obsidian properties:set`.

**Bases + CLI:** The bases skill teaches the `.base` file format, and the CLI skill provides the commands to populate the data. When you ask "set up a project tracker," Claude creates the `.base` file AND can use `obsidian properties:set` in a loop to add frontmatter to your existing notes so they appear in the base view.

**Defuddle + CLI + Markdown:** When you clip web content, Defuddle extracts it, the CLI saves it to a note, and the markdown skill ensures the resulting note has proper frontmatter, tags, and formatting.

**Commands use everything:** Each slash command draws on multiple skills. `/vault-capture` uses markdown formatting, CLI execution, and Defuddle extraction depending on what you're capturing.

**Second Brain + Templates + Everything:** The second-brain skill provides the *methodology* (Zettelkasten, PARA, MOCs, progressive summarization) while vault-templates provides the *structures*. When you ask "create a literature note for this book," Claude uses second-brain methodology to decide the note type, vault-templates for the structure, markdown for the formatting, and CLI to create it. The new commands compose these skills: `/vault-research` uses defuddle + second-brain + templates + CLI to run a full research pipeline. `/vault-connect` uses second-brain's linking philosophy to make intelligent connection suggestions. `/vault-review` uses second-brain's periodic review patterns to surface what needs attention.

## Skills Reference (New)

### second-brain

**When it activates:** You mention knowledge management methodology, Zettelkasten, PARA, MOCs, Maps of Content, progressive summarization, atomic notes, evergreen notes, fleeting notes, literature notes, permanent notes, or ask how to organize your vault as a second brain.

**What it knows:** The major PKM methodologies — Zettelkasten note types and processing workflows, PARA folder organization by actionability, Maps of Content design principles, progressive summarization layers, and atomic note standards. It also knows when to recommend each approach and how to combine them.

**How to use it effectively:**

- Ask "how should I organize my vault?" — it will recommend an approach based on your goals.
- Ask "create a MOC for my machine learning notes" — it will build a curated map with grouped links and open questions.
- Ask "help me process this article into permanent notes" — it will walk you through the Zettelkasten workflow.
- Ask "should I use PARA or Zettelkasten?" — it will explain the tradeoffs and suggest a hybrid if appropriate.

### vault-templates

**When it activates:** You ask to create a specific type of note (meeting notes, book review, project brief, weekly review), want a template for a recurring note type, or ask about frontmatter conventions for different note types.

**What it knows:** Proven note archetypes with complete frontmatter schemas, section structures, and linking conventions — meeting notes, literature notes, project briefs, weekly reviews, permanent/evergreen notes, daily note sections, and person/contact notes.

**How to use it effectively:**

- Ask "create a meeting note for today's standup" — it will scaffold the full template with attendees, decisions, and action items sections.
- Ask "set up a book review template" — it will create a literature note structure with progressive summarization support.
- Ask "what properties should a project note have?" — it will recommend the frontmatter schema.
- The skill adapts to your existing conventions — it checks your vault for existing patterns before applying templates.

## Commands Reference (New)

### /vault-research

**Usage:** `/vault-research <url or topic>`

Full research pipeline that turns raw sources into connected vault knowledge. Give it a URL and it clips the content, creates a properly-formatted note with metadata, writes a summary, searches your vault for related notes, suggests connections, and logs the research in your daily note. Give it a topic and it searches the web, lets you pick sources, processes each one, and offers to create a synthesis note.

**Examples:**

- `/vault-research https://example.com/interesting-article`
- `/vault-research transformer architecture advances`
- `/vault-research what I already have on machine learning`

### /vault-connect

**Usage:** `/vault-connect [note name|topic|recent]`

Actively builds missing connections in your knowledge graph. Point it at a note and it finds semantically related notes that aren't yet linked, explains why they're related, and offers to weave them together. Use `recent` to find your most isolated recent notes and connect them. Give it a topic to map and strengthen an entire cluster.

**Examples:**

- `/vault-connect "My Research Note"`
- `/vault-connect machine learning`
- `/vault-connect recent`

### /vault-review

**Usage:** `/vault-review [daily|weekly|monthly]`

Periodic review that summarizes recent vault activity, surfaces patterns, and flags items needing attention. Daily reviews summarize captures and open tasks. Weekly reviews detect themes, find stale items, and resurface forgotten notes. Monthly reviews audit knowledge graph health, MOC coverage, and progressive summarization progress.

**Examples:**

- `/vault-review` or `/vault-review daily`
- `/vault-review weekly`
- `/vault-review monthly`

## Tips for Getting the Best Results

**Be specific about what you want.** "Create a note" triggers the CLI skill. "Create a base that tracks my reading list with columns for title, author, status, and rating" triggers the bases skill with enough context to produce a complete, useful `.base` file.

**Mention the format when it matters.** If you need JSON output from a CLI command (e.g., for piping into another tool), say so. If you want a table view vs. a board view in a base, specify it.

**Use commands for quick actions, natural language for complex ones.** `/vault-capture todo: buy groceries` is fast for simple captures. But for "create a project template with frontmatter, a task section, and link it to my Projects MOC," just describe what you want in plain language and let Claude compose the right sequence of operations.

**Ask for automation when you have repeating patterns.** If you find yourself doing the same vault operation regularly, ask Claude to write a shell alias, a cron job, or a script. The CLI skill has patterns for all of these.

**Use `/vault-organize full` periodically.** It's the quickest way to find broken links, orphan notes, inconsistent tags, and structural issues before they accumulate.

## Troubleshooting

**Commands fail with "tool not found":** The Obsidian MCP Server isn't connected. Install it and ensure it appears in your MCP connections.

**CLI commands return "command not found":** The CLI hasn't been registered. Open Obsidian → Settings → General → CLI → Register. Then restart your terminal.

**CLI commands hang or return nothing:** Obsidian isn't running in the background. The CLI needs a running Obsidian instance to communicate with.

**Defuddle returns errors on a URL:** Some sites block automated extraction. Try a different URL, or use the `--md` flag explicitly. Sites behind login walls won't work.

**Base files don't show expected notes:** The notes are missing the frontmatter properties that the base filters against. Use `obsidian properties:set` to add the required properties to your notes.
