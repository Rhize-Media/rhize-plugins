---
description: Interactive setup wizard — build a personalized vault system with folders, templates, dashboards, and recommended plugins
allowed-tools: ["mcp__obsidian-mcp-server__obsidian_global_search", "mcp__obsidian-mcp-server__obsidian_read_note", "mcp__obsidian-mcp-server__obsidian_update_note", "mcp__obsidian-mcp-server__obsidian_list_notes", "mcp__obsidian-mcp-server__obsidian_manage_frontmatter", "mcp__obsidian-mcp-server__obsidian_manage_tags", "Bash"]
argument-hint: [new|existing|resume]
---

Interactive setup wizard that interviews you, understands your workflow, and builds a complete personalized knowledge system — folder structure, templates, dashboards, MOCs, and community plugin recommendations — tailored to how you actually work.

This wizard has 6 phases. At each phase, present results and get confirmation before proceeding. The user can skip any phase, and skipped items are logged for `/vault-align` to revisit later.

Parse "$ARGUMENTS":
- `new` → skip vault audit, go straight to interview
- `existing` → run full audit before generating archetype
- `resume` → read `_vault-setup-log.md` and pick up from the last incomplete phase
- No arguments → auto-detect based on vault size

---

## Phase 1: Discovery Interview

First, detect whether this is a fresh or existing vault:

```bash
obsidian files total
obsidian folders format=tree
```

If the vault has >10 notes, treat it as an existing vault (run Phase 2 after the interview). If ≤10 or empty, treat it as fresh.

Then interview the user ONE question at a time. Wait for each answer before asking the next. These questions shape the entire archetype — take time to understand the answers.

**Question 1 — Role:**
"What best describes your primary role? This helps me tailor the vault structure to your workflow."
- Researcher / Academic
- Software Developer / Engineer
- Writer / Content Creator
- Student
- Manager / Team Lead
- Designer / Creative
- Entrepreneur / Founder
- Other (describe)

**Question 2 — Focus Areas:**
"What are your 3-5 main areas of focus or interest? These become the backbone of your vault. For example: 'machine learning, product management, fitness, cooking'."

**Question 3 — Vault Purpose:**
"What do you most want your vault to help you with?"
- Build a long-term knowledge base (→ leans Zettelkasten + MOCs)
- Manage projects and tasks (→ leans PARA + Kanban)
- Process and retain what I read (→ leans literature notes + progressive summarization)
- Journal and reflect (→ leans daily notes + weekly reviews)
- All of the above (→ hybrid approach)

**Question 4 — Organization Style:**
"When you save information, do you think about it more in terms of what project/action it relates to, or what topic/idea it connects to?"
- By project or action (→ PARA-first)
- By topic or idea (→ Zettelkasten-first)
- Both equally (→ hybrid: PARA folders + Zettelkasten notes)

**Question 5 — Active Projects:**
"Do you have any active projects right now? Name 2-3 and I'll seed your vault with project folders."
(If they say no or aren't sure, that's fine — skip project seeding.)

After all questions are answered, summarize the profile back to the user and confirm before proceeding:
"Based on your answers, here's the archetype I'll build: [role], focusing on [areas], using a [methodology] approach with emphasis on [primary purpose]. Does this sound right?"

---

## Phase 2: Vault Audit (existing vaults only)

Run these diagnostics to understand the current vault state:

```bash
obsidian folders format=tree
obsidian files total
obsidian tags sort=count format=json
obsidian orphans
obsidian plugins format=json
```

**MCP/CLI Fallback:** If `obsidian` CLI commands or MCP tools fail (disabled connectors, CLI not registered, Obsidian not running), fall back to direct filesystem operations:
```bash
# Filesystem fallback for vault structure
find "$VAULT_PATH" -name "*.md" | wc -l                    # total notes
find "$VAULT_PATH" -type d | head -30                       # folder tree
find "$VAULT_PATH" -name "*.md" -path "*/templates/*"       # templates
find "$VAULT_PATH" -name "*.md" -path "*/Templates/*"       # templates (alt)
```
Log which method was used so later phases know whether `obsidian move` (link-safe) or `mv`/`cp -p` (requires manual link checking) should be used for migration.

Then sample 5-10 representative notes to check frontmatter conventions:
```bash
obsidian properties file="<note1>" format=json
obsidian properties file="<note2>" format=json
# ... etc for a mix of note types
```

Check for an existing templates folder:
```bash
obsidian files folder=Templates
obsidian files folder=templates
obsidian files folder="_templates"
```

**Plugin enabled-vs-installed check (CRITICAL):**
A plugin folder existing in `.obsidian/plugins/<plugin>/` does NOT mean the plugin is enabled. The source of truth is `.obsidian/community-plugins.json`, which lists only the enabled plugin IDs. Always verify both:
```bash
# Check if plugin folder exists (installed)
ls "$VAULT_PATH/.obsidian/plugins/dataview/" 2>/dev/null && echo "installed" || echo "not installed"
# Check if plugin is actually enabled (in the enabled list)
cat "$VAULT_PATH/.obsidian/community-plugins.json" 2>/dev/null
# Look for the plugin ID string in the JSON array — if absent, the plugin is installed but NOT enabled
```
When reporting plugin status, use three states: **enabled**, **installed but disabled**, or **not installed**. If a plugin is installed but disabled, tell the user: "I found [plugin] installed but not enabled. You can enable it in Settings → Community plugins → toggle it on. Want to pause and do that now?"

**Nested `.obsidian` detection:**
Check for `.obsidian` folders inside subfolders — these indicate an accidentally nested vault and should be flagged as a health issue:
```bash
find "$VAULT_PATH" -mindepth 2 -name ".obsidian" -type d
```
If found, warn the user: "I found a nested .obsidian folder inside [path], which means Obsidian may treat that subfolder as a separate vault. This can cause unexpected behavior. You should delete or move that nested .obsidian folder."

Present the audit summary:
- **Size**: X notes across Y folders
- **Structure**: describe the current folder hierarchy and any clear organizational scheme
- **Tags**: top 10 tags, style pattern (flat/nested, singular/plural), any obvious duplicates
- **Frontmatter**: common properties found, naming conventions in use
- **Plugins**: list with three-state status (enabled / installed-but-disabled / not installed)
- **Templates**: whether a template folder exists and what templates are in it
- **Health**: orphan count, broken links, and any nested `.obsidian` folders found
- **Tool availability**: which tools are available (MCP, CLI, filesystem-only) — this affects migration strategy in Phase 6

Then say: "I'll design the new structure to work with what you already have — preserving your existing folders and conventions where they make sense."

---

## Phase 3: Archetype Generation

Based on the interview answers (and audit results for existing vaults), generate each component of the archetype. Present each section to the user, confirm it, then move to the next. Keep each presentation to 200-300 words.

### 3a: Folder Structure

Generate a personalized folder tree using the user's actual domains, not generic labels. For existing vaults, mark which folders already exist and which are new.

Example for a developer focused on ML, side projects, and fitness (hybrid approach):
```
vault/
├── Projects/           ← Active work with deadlines
│   ├── ML Pipeline/
│   └── Side Project X/
├── Areas/              ← Ongoing responsibilities
│   ├── Career/
│   ├── Health & Fitness/
│   └── Finance/
├── Resources/          ← Reference by topic
│   ├── Machine Learning/
│   ├── Software Architecture/
│   └── Cooking/
├── Archive/            ← Completed/inactive
├── Inbox/              ← Unprocessed captures
├── Templates/          ← Note templates
└── Daily/              ← Daily notes (if not already configured)
```

Present the proposed structure and ask: "Does this folder structure work for you? I can adjust any folder names or add/remove sections."

### 3b: Templates

Generate actual template files tailored to the user's needs. Each template uses Obsidian's `{{date}}` and `{{title}}` variables so they work with the core Templates plugin.

Choose templates based on the interview:
- Everyone gets: Daily Note, Permanent Note
- Knowledge focus: Literature Note, MOC template
- Project focus: Project Brief, Meeting Notes
- Reading focus: Book Review (literature note variant with rating)
- Reflection focus: Weekly Review, Monthly Review

For each template, show the user the frontmatter schema and section structure. Example:

"Here's your Meeting Notes template. It includes attendees, decisions, and action items sections, with frontmatter for date, attendees, and status:"
```
[show the template]
```
"Look good? I can adjust the sections or add/remove properties."

**Plugin check (woven):** Before saving templates, check if Templater is installed:
```bash
obsidian plugins format=json
```
If `templater-obsidian` is found → mention that the templates also work with Templater's advanced features. If not found and the user chose complex templating needs → say: "These templates work with Obsidian's built-in Templates plugin. If you want more powerful features like dynamic dates and conditional sections, you can install the Templater plugin: Settings → Community plugins → Browse → search 'Templater'. Want to pause and install it, or continue with the built-in plugin?"

### 3c: Dashboard

Generate a "Home" note that serves as the vault's landing page. Include Dataview queries when possible, with static alternatives when Dataview isn't available.

**Plugin check (woven):** Check for `dataview` plugin.

If Dataview is installed, generate queries like:
````markdown
## Active Projects
```dataview
TABLE status, priority, due-date
FROM "Projects"
WHERE status = "active"
SORT priority ASC
```

## Recent Notes
```dataview
LIST
FROM ""
WHERE type != "daily"
SORT file.mtime DESC
LIMIT 10
```

## Reading Queue
```dataview
TABLE author, status, summarization-layer as "Progress"
FROM #literature
WHERE status = "processing"
SORT file.ctime ASC
```

## Tasks Due
```dataview
TASK
WHERE !completed
WHERE due <= date(today) + dur(7 days)
SORT due ASC
```
````

If Dataview is NOT installed → say: "This dashboard is most powerful with Dataview queries that auto-update. Without Dataview, I'll create a static dashboard with manual links. You can install Dataview anytime (Settings → Community plugins → Browse → 'Dataview') and I'll upgrade the dashboard with `/vault-align`. Want to pause and install it, or continue with the static version?"

Static alternative: create the dashboard with manual wikilink lists organized by section, which the user maintains by hand.

### 3d: Starter MOCs

Create one MOC per declared focus area. For existing vaults, search for notes that belong in each MOC:

```bash
obsidian search query="<focus area term>" format=json
obsidian search query="[tag:<focus-area>]" format=json
```

Pre-populate MOCs with any matching existing notes as wikilinks. For fresh vaults, create empty MOC structures with section headings and an "Open Questions" section.

### 3e: Kanban Boards (if applicable)

Only generate if the user selected project management or "all of the above" for vault purpose.

**Plugin check (woven):** Check for `obsidian-kanban` plugin.

If installed, generate a Kanban-formatted .md file:
```markdown
---
kanban-plugin: basic
---
## Backlog

## In Progress

## Review

## Done
```

Pre-populate with any active projects the user named in the interview.

If NOT installed → say: "Project boards work best with the Kanban plugin, which renders markdown as a drag-and-drop board. Want to install it? Settings → Community plugins → Browse → 'Kanban'. Or I can skip this and note it for later."

---

## Phase 4: Plugin Summary

After all archetype components have been presented and confirmed, summarize the plugin situation:

"Here's a summary of the community plugins your vault setup uses:"
- [Plugin name] — [purpose] — [installed/not installed/installed but disabled]

For not-installed plugins, remind the user they can install them anytime and run `/vault-align plugins` to check status and enable them.

---

## Phase 5: Scaffolding

Execute the confirmed archetype. Create everything using CLI commands:

**Folders (CRITICAL — placeholder notes required):**
Empty folders are invisible in Obsidian's file explorer. Every new folder MUST contain at least one `.md` file or it will not appear to the user. Create a `.folder-note.md` placeholder in each new folder:
```bash
# Create a placeholder note in each new folder (folders are created implicitly)
obsidian create name=".folder-note" path=Projects/ content="# Projects\nActive work with deadlines." --silent
obsidian create name=".folder-note" path=Areas/ content="# Areas\nOngoing responsibilities." --silent
# ... etc for each folder
```

**Filesystem fallback for folder creation:**
If the CLI/MCP is unavailable, use `mkdir -p` followed by creating a placeholder file in every folder:
```bash
mkdir -p "$VAULT_PATH/Projects"
echo "# Projects\nActive work with deadlines." > "$VAULT_PATH/Projects/.folder-note.md"
# Repeat for EVERY new folder — do not skip this step
```
Never use `mkdir -p` alone without also creating a placeholder `.md` file — the folder will be invisible in Obsidian.

**Templates:**
```bash
obsidian create name="Meeting Notes" path=Templates/ content="<template content>"
obsidian create name="Literature Note" path=Templates/ content="<template content>"
# ... etc for each confirmed template
```

**Dashboard:**
```bash
obsidian create name="Home" content="<dashboard content>"
```

**MOCs:**
```bash
obsidian create name="<Focus Area>" path=Resources/<Area>/ content="<MOC content>"
```

**Kanban boards (if confirmed):**
```bash
obsidian create name="Project Board" content="<kanban content>"
```

After scaffolding, confirm what was created: "Setup complete. I created X folders, Y templates, your Home dashboard, and Z MOCs. Here's a summary of your new vault structure."

---

## Phase 6: Migration (existing vaults only, opt-in)

For existing vaults, after scaffolding the overlay structure, offer to reorganize existing notes. Present each migration opportunity separately — the user can accept or skip each one independently.

**Record the pre-migration timestamp** before any moves begin:
```bash
PRE_MIGRATION_DATE=$(date +%Y-%m-%d)
echo "Migration started: $PRE_MIGRATION_DATE"
```
This date is needed later to fix Dataview `file.mtime` queries that break after bulk moves.

**Note relocation:**
Analyze notes in the root and suggest where they should go:
```bash
obsidian files folder="" format=json
```

For each batch: "I found X notes in your vault root. Based on their content and properties, here's where I'd suggest moving them:"
- 12 notes → Projects/ (they have `type: project` or project-related content)
- 8 notes → Areas/ (ongoing topics like Health, Finance)
- 14 notes → Resources/ (reference material)
- 5 notes → unclear (leave in place for now)

"Want me to move these now? I'll use `obsidian move` which automatically updates all wikilinks. Or skip this — `/vault-align` will suggest it later."

If the user approves, move in batches of 10-15:
```bash
obsidian move file="<note>" to=Projects/
obsidian move file="<note>" to=Areas/Health/
# ... etc
```

**Filesystem fallback — TIMESTAMP PRESERVATION (CRITICAL):**
When the CLI/MCP `obsidian move` is unavailable and you must use filesystem commands, ALWAYS use `mv` (which preserves timestamps) or `cp -p` (which preserves modification times). NEVER use bare `cp` — it resets `mtime` to the current time, permanently destroying the original modification dates. This breaks Dataview queries that sort or filter by `file.mtime`, and the original timestamps cannot be recovered.
```bash
# CORRECT — preserves timestamps:
mv "$VAULT_PATH/old/note.md" "$VAULT_PATH/new/note.md"
# CORRECT — preserves timestamps when copying:
cp -p "$VAULT_PATH/old/note.md" "$VAULT_PATH/new/note.md"
# WRONG — destroys timestamps (NEVER DO THIS):
# cp "$VAULT_PATH/old/note.md" "$VAULT_PATH/new/note.md"
```

**Deletion permissions in Cowork/sandboxed environments:**
When running in Cowork or other sandboxed environments, file deletion may be blocked by default. Before attempting to remove old folders/files after migration, request deletion permissions first:
```
Call: mcp__cowork__allow_cowork_file_delete with the vault path
```
If deletion is not available, leave old folders in place and note them in the setup log as "pending cleanup — user should delete manually."

**Old folder cleanup strategy:**
After migration, the old folders should be removed to avoid confusion (users seeing duplicate structure). Always:
1. Verify 100% of files were successfully moved (compare file counts)
2. Request deletion permissions if in a sandboxed environment
3. Delete old empty folders
4. If deletion fails, document remaining cleanup in the setup log

**Tag consolidation:**
If the audit found duplicate tags:
"I found these tag duplicates: `#meeting` (45 uses) and `#meetings` (12 uses). Want me to merge `#meetings` into `#meeting`?"
```bash
obsidian tags:rename old=meetings new=meeting
```

**Frontmatter standardization:**
If the audit found inconsistent properties:
"I found 23 notes with `type: meeting` but missing the `status` property. Want me to add `status: open` to all of them?"
```bash
obsidian properties:set file="<note>" status=open
# ... for each note
```

**Post-migration Dataview query fix (CRITICAL):**
After bulk file moves (even with `obsidian move`), `file.mtime` values may be updated to the migration timestamp. This means any Dataview query using `file.mtime` for "Recent Notes" will show ALL migrated notes as recently modified, rendering the query useless. Fix this by adding a date filter to mtime-based queries:
````markdown
## Recent Notes
```dataview
LIST
FROM ""
WHERE file.name != "Home" AND file.name != ".folder-note"
  AND file.mtime > date(<PRE_MIGRATION_DATE>)
SORT file.mtime DESC
LIMIT 10
```
````
Replace `<PRE_MIGRATION_DATE>` with the actual date recorded at the start of Phase 6. This ensures only notes modified AFTER migration appear in "Recent Notes." Mention this to the user: "I've set the Recent Notes query to only show notes modified after today's migration. As you edit notes going forward, they'll appear here naturally."

---

## Setup Log

At the end of the wizard (or whenever the user exits early), create or update `_vault-setup-log.md` in the vault root:

```markdown
---
type: vault-config
created: {{date}}
last-updated: {{date}}
---

# Vault Setup Log

## Profile
- **Role**: [from interview]
- **Focus Areas**: [from interview]
- **Purpose**: [from interview]
- **Methodology**: [PARA / Zettelkasten / Hybrid]

## Archetype
### Folder Structure
[The confirmed folder tree]

### Frontmatter Schemas
[Per note type: which properties are expected]

### Templates Created
[List of template files and their locations]

## Plugin Status
| Plugin | Status | Purpose |
|--------|--------|---------|
| dataview | installed | Dashboard queries, note filtering |
| obsidian-kanban | skipped | Project boards |
| ... | ... | ... |

## Skipped Items
- [ ] Install Kanban plugin and create project board
- [ ] Migrate 34 root notes into folder structure
- [ ] Consolidate duplicate tags (#meeting vs #meetings)

## Completed
- [x] Folder structure created
- [x] 5 templates saved
- [x] Home dashboard created
- [x] 3 MOCs seeded
```

This log is read by `/vault-align` to understand the vault's intended state and track what still needs attention.


---

## Phase 7: qmd Semantic Search Setup (Optional)

After all other phases, offer to set up qmd for enhanced search, connection discovery, and natural language recall.

"Would you like to enable semantic search for your vault? qmd is a local-first search engine that lets you search by concept (not just keywords), find hidden connections between notes, and ask natural language questions about your vault. Everything runs on your machine — no cloud services."

### If the user says yes:

**Step 1: Check prerequisites**
```bash
# Check Node.js
node --version 2>/dev/null || echo "Node.js not found — install from https://nodejs.org"

# Check if qmd is already installed
command -v qmd >/dev/null 2>&1 && echo "qmd already installed" || echo "qmd not installed"
```

**Step 2: Install qmd** (if not already installed)
```bash
npm install -g qmd
```

**Step 3: Create vault collection and index**
```bash
# Add the vault as a qmd collection
qmd collection add vault "/path/to/vault" --include "*.md"

# Generate vector embeddings (this may take a few minutes for large vaults)
qmd embed vault

# Verify indexing
qmd status vault
```

Tell the user: "Indexing is complete. Your vault now has [X] documents indexed for semantic search. The commands `/vault-search`, `/vault-connect`, and `/vault-recall` will automatically use qmd when available."

**Step 4: Document in setup log**
Add to the Plugin Status table in `_vault-setup-log.md`:
```markdown
| qmd | installed | Semantic search, connection discovery, vault recall |
```

### Keeping the index fresh

Tell the user: "After adding or editing notes, run `qmd embed vault` to update the index. You can also add this to a cron job or alias for convenience:
```bash
alias qmd-reindex='qmd embed vault'
```
The `/vault-align` command will check if your qmd index is stale and remind you to re-embed."

### If the user declines:

Add to the Skipped Items in the setup log:
```markdown
- [ ] Install qmd for semantic search (`npm install -g qmd`)
```

Say: "No problem — all commands work without qmd using keyword search. You can set it up anytime by running `npm install -g qmd` and then `/vault-setup resume` to pick up where we left off."
