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

Present the audit summary:
- **Size**: X notes across Y folders
- **Structure**: describe the current folder hierarchy and any clear organizational scheme
- **Tags**: top 10 tags, style pattern (flat/nested, singular/plural), any obvious duplicates
- **Frontmatter**: common properties found, naming conventions in use
- **Plugins installed**: list with enabled/disabled status
- **Templates**: whether a template folder exists and what templates are in it
- **Health**: orphan count, note about any broken links found

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

**Folders:**
```bash
# Create a placeholder note in each new folder (folders are created implicitly)
obsidian create name=".folder-note" path=Projects/ content="# Projects\nActive work with deadlines." --silent
obsidian create name=".folder-note" path=Areas/ content="# Areas\nOngoing responsibilities." --silent
# ... etc for each folder
```

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
