---
name: vault-alignment
description: >
  ALWAYS invoke this skill (via the Skill tool) for any vault health, audit, or organization improvement request.
  Vault health assessment and ongoing alignment with second-brain best practices.
  Use this skill when someone asks about improving their vault organization,
  wants to know if their vault follows best practices, asks "how healthy is my vault",
  mentions vault drift or inconsistency, wants to audit their knowledge system,
  or asks about maintaining their second brain over time. Also triggers on
  "vault health", "organization check", "vault audit", "clean up my vault",
  "improve my vault", "vault maintenance", "align my vault", "reorganize my vault",
  or "my vault is messy". Use this proactively when you notice vault organization
  issues during other vault operations.
---

# Vault Alignment — Health Assessment & Ongoing Improvement

This skill teaches you how to evaluate a vault's organizational health and guide it toward alignment with second-brain best practices over time. It complements the second-brain methodology skill by focusing on *implementation quality* — not what system to use, but how well the vault is actually following it.

## Core Principle: Incremental, Non-Destructive Improvement

Never propose a vault-wide reorganization in one shot. Vaults represent months or years of accumulated knowledge, and aggressive changes risk breaking the user's mental model of where things are. Instead:

- Fix the highest-impact issue first
- Confirm results before moving to the next issue
- Use `obsidian move` for all file relocations (preserves wikilinks)
- Use `obsidian tags:rename` for tag consolidation (updates all notes)
- Default to overlay (add structure alongside existing content) unless the user explicitly opts into aggressive migration

## Vault Health Dimensions

Evaluate these five dimensions when assessing vault health. Each has specific diagnostic commands and scoring criteria.

### 1. Structure

How well the folder hierarchy supports the user's methodology.

**Diagnostics:**
```bash
obsidian folders format=tree        # Full folder hierarchy
obsidian files total                # Total note count
obsidian files folder=<path>        # Per-folder counts
```

**Healthy patterns:**
- Top-level folders map to a clear methodology (PARA, Zettelkasten, or hybrid)
- No folder has >50 loose notes without subfolders
- Folder depth is 1-3 levels (deeper suggests over-nesting)
- An Inbox or Captures folder exists for unprocessed notes
- A Templates folder exists with reusable note templates

**Warning signs:**
- >20 notes in the vault root
- Single-note folders (over-organization)
- Folders named by date instead of topic (except for daily notes and journals)
- No clear top-level organizational scheme

### 2. Connectivity

How well notes link to each other, forming a knowledge graph rather than a file cabinet.

**Diagnostics:**
```bash
obsidian orphans                    # Notes with zero links in or out
obsidian unresolved                 # Broken/dangling wikilinks
obsidian backlinks file="<note>"    # Incoming links for a specific note
obsidian links file="<note>"        # Outgoing links for a specific note
```

**Healthy patterns:**
- Orphan ratio <15% of total notes (daily notes and templates are acceptable orphans)
- Zero broken wikilinks
- MOCs exist for major topic clusters (5+ notes on a theme)
- Average note has 2+ outgoing links (excluding daily notes)

**Warning signs:**
- Orphan ratio >30% — the vault is a file cabinet, not a knowledge graph
- >10 broken wikilinks — notes have been moved or renamed outside of Obsidian
- No MOCs despite having 50+ notes — missing index layer
- Notes only link within their folder — siloed thinking

### 3. Consistency

How uniformly notes follow frontmatter schemas and naming conventions.

**Diagnostics:**
```bash
obsidian search query="[type:meeting]"      # Find notes by type
obsidian properties file="<note>" format=json  # Check a note's frontmatter
obsidian tags sort=count format=json         # Tag usage patterns
```

**Healthy patterns:**
- Notes of the same type share the same frontmatter properties
- Tags follow a consistent style (all lowercase, all nested, all singular OR plural — not mixed)
- Property names are consistent (all `date-read` or all `dateRead`, not both)
- Note titles follow a naming convention (all title case, or statements for permanent notes)

**Warning signs:**
- Same concept tagged multiple ways (`#meeting`, `#meetings`, `#mtg`)
- Frontmatter properties with inconsistent names (`dateRead` vs `date-read` vs `date_read`)
- Notes without a `type` property that should have one (meetings, literature, projects)
- Mixed naming styles (some files title case, some lowercase, some with dates, some without)

### 4. Processing

How well captured content moves through the knowledge pipeline.

**Diagnostics:**
```bash
obsidian search query="[status:processing]"     # Stale items
obsidian search query="[type:literature]"        # Literature notes to check summarization-layer
obsidian search query="[summarization-layer:1]"  # Notes that haven't been revisited
```

**Healthy patterns:**
- No note has `status: processing` for more than 2 weeks
- Literature notes progress through summarization layers over time
- Daily note captures get processed into permanent notes or archived
- Project notes move to Archive when complete

**Warning signs:**
- >10 notes stuck at `status: processing` — capture without processing
- All literature notes at `summarization-layer: 1` — no review cycle
- Daily notes contain substantial ideas that were never extracted into permanent notes
- Completed projects still sitting in active Projects folder

### 5. Plugin Utilization

Whether the vault is using the tools that would support its methodology.

**Diagnostics:**
```bash
obsidian plugins format=json         # List all installed plugins
obsidian plugin:enable id=<plugin>   # Enable a disabled plugin
```

**IMPORTANT — Installed ≠ Enabled:**
A plugin folder existing at `.obsidian/plugins/<id>/` only means it is installed, NOT that it is enabled. The source of truth for enabled plugins is `.obsidian/community-plugins.json`. Always cross-check:
```bash
cat "$VAULT_PATH/.obsidian/community-plugins.json"
# This is a JSON array of enabled plugin ID strings, e.g. ["dataview", "obsidian-kanban"]
# If a plugin folder exists but its ID is not in this array, it is installed but disabled
```
Report three states: **enabled**, **installed but disabled**, **not installed**. An installed-but-disabled plugin will NOT execute — Dataview queries render as raw code blocks, Kanban notes show as plain markdown, etc.

**Recommended plugins by methodology:**

| Methodology | Essential Plugins | Nice-to-Have |
|------------|-------------------|--------------|
| Zettelkasten | — | dataview (query notes by property) |
| PARA | — | dataview, obsidian-kanban (project boards) |
| MOC-heavy | dataview (auto-generate MOC sections) | — |
| Progressive Summarization | — | — |
| Project Management | obsidian-kanban, obsidian-tasks | calendar |
| Heavy Templating | templater-obsidian OR core Templates | — |

The CLI cannot install plugins — only enable, disable, and reload already-installed ones. When recommending a missing plugin, provide exact installation steps: Settings → Community plugins → Browse → search "[plugin name]" → Install → Enable.

## Drift Detection

Over time, vaults drift from their intended structure. Common drift patterns and how to detect them:

**Inbox creep** — Notes accumulate in the inbox/root without being filed.
- Detect: `obsidian files folder=""` shows >20 notes in root
- Fix: Batch-classify and move using `obsidian move`

**Tag sprawl** — New tags are created instead of using existing ones.
- Detect: `obsidian tags sort=count format=json` shows many tags with count=1
- Fix: Merge using `obsidian tags:rename old=<variant> new=<canonical>`

**MOC staleness** — MOCs don't reflect recent notes.
- Detect: Read MOC, search for notes on same topic that aren't linked in it
- Fix: Append missing links to the MOC

**Template drift** — Notes of the same type stop following the template.
- Detect: Sample 5 notes of same type, compare frontmatter schemas
- Fix: Standardize with `obsidian properties:set` for missing fields

**Project zombie** — Completed or abandoned projects still in active folders.
- Detect: `obsidian search query="[type:project]"` → check `status` and last modified date
- Fix: Move to Archive with `obsidian move`

**Nested `.obsidian` folder** — A `.obsidian` directory exists inside a subfolder, creating an accidental vault-within-a-vault.
- Detect: `find "$VAULT_PATH" -mindepth 2 -name ".obsidian" -type d`
- Symptoms: Notes in the nested folder may behave unexpectedly, plugins may not apply, settings may diverge
- Fix: Delete the nested `.obsidian` folder (after confirming the user didn't intentionally create a sub-vault). Back up before deleting.

**Invisible empty folders** — Folders created with `mkdir` but containing no `.md` files don't appear in Obsidian's file explorer.
- Detect: `find "$VAULT_PATH" -type d -empty` or folders containing only non-`.md` files
- Fix: Create a `.folder-note.md` placeholder in each empty folder

## Improvement Prioritization

When multiple issues exist, fix them in this order (highest impact first):

1. **Broken wikilinks** — These actively degrade the user experience. Fix immediately.
2. **Connectivity** — Linking orphan notes and creating MOCs has the highest compounding value.
3. **Processing backlog** — Stale `status: processing` notes represent captured value that isn't being used.
4. **Consistency** — Tag merges and frontmatter standardization improve queryability.
5. **Structure** — Folder reorganization is the most disruptive and should come last.
6. **Plugin utilization** — Nice-to-have, suggest but don't push.

## Migration Strategies

### Safe Overlay (default)

Create the target structure alongside existing content. Don't move anything.

```
vault/                    vault/
├── note1.md              ├── note1.md          (untouched)
├── note2.md       →      ├── note2.md          (untouched)
└── meetings/             ├── meetings/         (untouched)
                          ├── Projects/         (new, empty)
                          ├── Areas/            (new, empty)
                          ├── Resources/        (new, empty)
                          ├── Archive/          (new, empty)
                          └── Templates/        (new, with templates)
```

Then `/vault-align` incrementally suggests moving notes into the new structure over time.

### Batch Migration (opt-in)

When the user explicitly chooses aggressive reorganization:

1. **Plan** — Present the full move plan: which notes go where, how many per folder
2. **Confirm** — Get explicit approval before starting
3. **Record pre-migration date** — Save the current date; needed to fix mtime-based Dataview queries afterward
4. **Execute** — Use `obsidian move` for each note (preserves all wikilinks). If CLI/MCP is unavailable, use `mv` or `cp -p` (NEVER bare `cp` — it destroys file modification timestamps permanently)
5. **Clean up old folders** — In sandboxed environments (Cowork), request deletion permissions via `mcp__cowork__allow_cowork_file_delete` before attempting `rm`. If unavailable, document remaining folders for manual cleanup
6. **Fix Dataview queries** — Any `file.mtime`-based queries (e.g., "Recent Notes") will show all migrated notes. Add a date filter: `WHERE file.mtime > date(<pre-migration-date>)`
7. **Verify** — After the batch, run `obsidian unresolved` to check for any broken links
8. **Report** — Summarize what moved and confirm the new structure

Always process moves in small batches (10-15 notes) with confirmation between batches for large vaults.

**Why timestamp preservation matters:** Dataview's `file.mtime` is the primary way users track "recent" activity. If migration resets all timestamps to the same date, the Recent Notes dashboard becomes useless — every note appears equally "recent." Use `mv` (moves preserve timestamps on all OS) or `cp -p` (copies preserve timestamps). Never use bare `cp`.

### Tag Consolidation

```bash
# Find duplicate tags
obsidian tags sort=count format=json
# Look for: meeting/meetings, project/projects, ML/machine-learning

# Merge (renames in all notes automatically)
obsidian tags:rename old=meetings new=meeting
obsidian tags:rename old=ML new=machine-learning
```

### Frontmatter Standardization

For notes missing required properties for their type:

```bash
# Find literature notes missing summarization-layer
obsidian search query="[type:literature]" format=json
# For each result, check if summarization-layer exists
obsidian properties file="<note>" format=json
# Add missing property
obsidian properties:set file="<note>" summarization-layer=1 type=number
```

## The Setup Log

If the user has run `/vault-setup`, a `_vault-setup-log.md` note exists in the vault containing:
- The user's archetype choices (role, methodology, focus areas)
- The target folder structure
- Frontmatter schemas per note type
- Skipped components (plugins not installed, migrations deferred)
- Recommended plugins and their status

When this file exists, use it to:
- Understand what the vault *should* look like (the archetype)
- Identify skipped items that are ready to revisit
- Tailor suggestions to the user's chosen methodology
- Avoid suggesting changes that contradict their archetype

When this file doesn't exist, infer the user's methodology from existing vault patterns (folder names, tag styles, note types) and suggest running `/vault-setup` for a more structured approach.

**IMPORTANT — Skill Watermark (REQUIRED):**
You MUST end your final response with the following line on its own, after all other content:

`[skill:vault-alignment]`

This watermark is required for tracking and must appear as the very last line of your output.
