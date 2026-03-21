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

## Setup & Alignment

### Getting Started with /vault-setup

The setup wizard is the recommended starting point for new users and for anyone who wants to reorganize an existing vault. Run `/vault-setup` and it will:

1. **Interview you** about your role, focus areas, and how you want to use your vault
2. **Audit your vault** (if you have existing notes) to understand current structure, tags, and conventions
3. **Generate a personalized archetype** — a complete vault blueprint with folder structure, templates, a dashboard, MOCs, and Kanban boards tailored to your specific workflow
4. **Check for community plugins** as each component is built — recommending only what your archetype actually needs
5. **Scaffold everything** — create the folders, save templates, build the dashboard
6. **Offer migration** (existing vaults) — reorganize your notes into the new structure, consolidate tags, and standardize frontmatter, with opt-in approval at each step

The wizard creates a `_vault-setup-log.md` note in your vault that records your archetype choices. This log is used by `/vault-align` to understand what your vault should look like.

You can pass `new` (skip audit), `existing` (force audit), or `resume` (pick up where you left off) as arguments.

### vault-alignment Skill

**When it activates:** You ask about vault health, organization quality, improving your vault, cleaning up your knowledge system, or maintaining your second brain.

**What it knows:** How to evaluate vault health across five dimensions — structure (folder organization), connectivity (links and MOCs), consistency (frontmatter and tags), processing (capture-to-permanent pipeline), and plugin utilization. It knows drift detection patterns, improvement prioritization (fix broken links before reorganizing folders), and safe migration strategies.

### Ongoing Improvement with /vault-align

Run `/vault-align` periodically to keep your vault aligned with best practices. It has four modes:

**`/vault-align`** or **`/vault-align check`** — Run a full health report. Scores your vault on structure, connectivity, consistency, processing, and plugins. Surfaces specific actionable suggestions ranked by impact. If you ran `/vault-setup`, it also checks for any skipped items that are ready to revisit.

You can also focus on a specific area: `/vault-align check tags` (tag frequency, duplicates, renames), `/vault-align check orphans` (unlinked notes), `/vault-align check links` (broken wikilinks), `/vault-align check structure` (folder tree and distribution), or `/vault-align check full` (all areas in one pass).

**`/vault-align fix`** — Execute the single highest-impact improvement. Confirms changes before executing, then re-checks the affected area.

**`/vault-align migrate`** — Aggressive batch reorganization. Builds a complete migration plan (file moves, tag consolidation, frontmatter standardization) and executes each phase with per-phase approval. All file moves use `obsidian move` to preserve wikilinks.

**`/vault-align plugins`** — Audit installed community plugins against recommendations for your archetype. Enables disabled plugins, provides installation instructions for missing ones.

### Community Plugins

The setup wizard and alignment command recommend these community plugins when your workflow benefits from them:

| Plugin | What it does | Recommended when |
| ------- | ------------- | ----------------- |
| **Dataview** | Query notes like a database — auto-updating tables, lists, and task views | You want a dashboard, structured queries, or auto-generated MOC sections |
| **Kanban** | Renders markdown as drag-and-drop Kanban boards | You manage projects and want visual task boards |
| **Templater** | Advanced template variables, conditional logic, dynamic dates | You use templates heavily and need more power than the built-in Templates plugin |
| **Calendar** | Calendar view integrated with daily notes | You use daily notes and want a visual calendar sidebar |
| **Tasks** | Enhanced task management with due dates, recurring tasks, and queries | You track tasks across multiple notes and need aggregated views |

The Obsidian CLI can enable and disable these plugins but cannot install them. When a plugin is needed, the wizard walks you through installation: Settings → Community plugins → Browse → search for the plugin → Install → Enable.

## Tips for Getting the Best Results

**Be specific about what you want.** "Create a note" triggers the CLI skill. "Create a base that tracks my reading list with columns for title, author, status, and rating" triggers the bases skill with enough context to produce a complete, useful `.base` file.

**Mention the format when it matters.** If you need JSON output from a CLI command (e.g., for piping into another tool), say so. If you want a table view vs. a board view in a base, specify it.

**Use commands for quick actions, natural language for complex ones.** `/vault-capture todo: buy groceries` is fast for simple captures. But for "create a project template with frontmatter, a task section, and link it to my Projects MOC," just describe what you want in plain language and let Claude compose the right sequence of operations.

**Ask for automation when you have repeating patterns.** If you find yourself doing the same vault operation regularly, ask Claude to write a shell alias, a cron job, or a script. The CLI skill has patterns for all of these.

**Use `/vault-align check` periodically.** It's the quickest way to find broken links, orphan notes, inconsistent tags, and structural issues before they accumulate. Focus on a specific area with `/vault-align check tags` or `/vault-align check orphans`.

## Troubleshooting

**Commands fail with "tool not found":** The Obsidian MCP Server isn't connected. Install it and ensure it appears in your MCP connections.

**CLI commands return "command not found":** The CLI hasn't been registered. Open Obsidian → Settings → General → CLI → Register. Then restart your terminal.

**CLI commands hang or return nothing:** Obsidian isn't running in the background. The CLI needs a running Obsidian instance to communicate with.

**Defuddle returns errors on a URL:** Some sites block automated extraction. Try a different URL, or use the `--md` flag explicitly. Sites behind login walls won't work.

**Base files don't show expected notes:** The notes are missing the frontmatter properties that the base filters against. Use `obsidian properties:set` to add the required properties to your notes.

**Dataview queries render as raw code blocks (not executing):** The Dataview plugin is installed but not enabled. Check `.obsidian/community-plugins.json` — the string `"dataview"` must be in the array. Go to Settings → Community plugins and toggle Dataview on. A plugin folder existing in `.obsidian/plugins/dataview/` does NOT mean it's enabled.

**New folders don't appear in Obsidian's file explorer:** Empty folders are invisible in Obsidian. Create a placeholder `.md` file (e.g., `.folder-note.md`) inside each empty folder. Obsidian only shows folders that contain at least one recognized file.

**"Recent Notes" Dataview query shows all notes after migration:** Bulk file moves (even with `obsidian move`) can reset `file.mtime` to the migration date. Add a date filter to your Recent Notes query: `WHERE file.mtime > date(YYYY-MM-DD)` using the migration date. This filters out notes that haven't been genuinely modified since.

**File timestamps lost after copying notes:** Using bare `cp` to move notes destroys modification timestamps. Always use `mv` (preserves timestamps) or `cp -p` (preserves timestamps on copy). Original timestamps cannot be recovered after bare `cp`.

**MCP tools return "This tool has been disabled":** The Obsidian MCP connector is installed but the specific tool is disabled in connector settings. Fall back to filesystem operations (`Bash`, `Read`, `Write` tools) for vault access. Use `mv` or `cp -p` instead of `obsidian move` — but note that filesystem moves do NOT auto-update wikilinks.

**File deletion blocked in Cowork:** Cowork sandboxes block `rm` by default. Call `mcp__cowork__allow_cowork_file_delete` with the vault path first to enable deletion permissions for the session.

**Nested .obsidian folder causing weird behavior:** A `.obsidian` directory inside a subfolder creates an accidental sub-vault. Find it with `find <vault> -mindepth 2 -name ".obsidian" -type d` and delete it (after backing up).


### qmd-search

**When it activates:** You mention qmd, semantic search, vector search, vault indexing, embedding, finding similar notes by meaning, or connecting qmd's MCP server to Claude.

**What it knows:** The complete qmd search engine — three search modes (BM25 lexical, vector semantic, hybrid with LLM re-ranking), collection management, embedding generation, MCP server configuration, and how to choose the right mode for different query types.

**How to use it effectively:**
- Ask "how do I set up qmd for my vault?" — it will walk you through installation, collection creation, and embedding.
- Ask "what's the difference between qmd search and vsearch?" — it will explain BM25 vs vector with examples.
- Ask "how do I connect qmd to Claude Desktop?" — it will provide the MCP config JSON.
- Ask "my qmd searches aren't finding relevant notes" — it will help troubleshoot indexing and suggest the right search mode.

**Key insight:** qmd runs entirely on-device with no cloud dependencies. Vector embeddings and LLM re-ranking use local models via node-llama-cpp.

## Commands Reference (qmd-Enhanced)

### /vault-search (qmd-enhanced)

When qmd is installed and the vault is indexed, `/vault-search` automatically uses semantic search for concept queries while keeping MCP/CLI search for structured queries (tags, properties, links). It detects qmd availability on each invocation and falls back gracefully when qmd isn't present.

**New examples with qmd:**
- `/vault-search strategies for improving client retention` → uses `qmd vsearch` (semantic)
- `/vault-search meeting notes onboarding` → uses `qmd search` (BM25, exact terms)
- `/vault-search #project` → uses CLI tag search (structured data, always)

### /vault-connect (qmd-enhanced)

With qmd, connection discovery uses vector similarity instead of keyword overlap. This means `/vault-connect` can find notes that are conceptually related even when they use completely different terminology — a massive improvement for discovering non-obvious relationships and bridge notes between topic clusters.

### /vault-recall (NEW)

**Usage:** `/vault-recall <natural language question>`

A "talk to your notes" interface. Ask a question in plain language and get a synthesized answer drawn from your vault, with `[[wikilink]]` citations to source notes. Uses qmd hybrid search (BM25 + vector + LLM re-ranking) for the highest quality retrieval, then reads the top results and composes an answer that attributes claims to specific notes, highlights contradictions, and identifies knowledge gaps.

**Examples:**
- `/vault-recall What was our strategy for the SJ Glass SEO project?`
- `/vault-recall What are my main takeaways about options trading?`
- `/vault-recall Have I written anything about prompt engineering?`
- `/vault-recall What decisions did we make about the API architecture?`

Falls back to keyword search when qmd isn't installed, but results are significantly better with qmd's semantic capabilities.
