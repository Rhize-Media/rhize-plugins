---
description: Vault health monitor — check alignment, analyze specific areas, fix issues, bulk migrate, audit plugins
allowed-tools: ["mcp__obsidian-mcp-server__obsidian_global_search", "mcp__obsidian-mcp-server__obsidian_read_note", "mcp__obsidian-mcp-server__obsidian_update_note", "mcp__obsidian-mcp-server__obsidian_list_notes", "mcp__obsidian-mcp-server__obsidian_manage_frontmatter", "mcp__obsidian-mcp-server__obsidian_manage_tags", "Bash"]
argument-hint: [check|check tags|check orphans|check links|check structure|check full|fix|migrate|plugins]
---

Ongoing vault health monitor and improvement engine. Analyzes the vault against second-brain best practices and the user's chosen archetype (if `/vault-setup` has been run), then surfaces specific actionable suggestions ranked by impact.

This command replaces `/vault-organize` — all vault analysis and organization lives here.

Parse "$ARGUMENTS" to determine the mode:

---

## "check" or no arguments — Health Report

The "check" mode supports optional focus areas. If `$ARGUMENTS` matches one of the focused forms below, run only that specific analysis. Otherwise, run the full health report.

### Step 1: Load context

Check if `_vault-setup-log.md` exists in the vault:
```bash
obsidian search query="_vault-setup-log"
```

If found, read it to understand the user's archetype — their intended methodology, folder structure, frontmatter schemas, and any skipped items from setup. This is the reference point for alignment.

If not found, note that no archetype is configured and suggest running `/vault-setup` for a more tailored experience. Still proceed with the health check using general best practices.

### Focused check modes

If `$ARGUMENTS` contains a focus keyword after "check", run only that analysis and skip the full report:

**"check tags" or "check tag":**
- Run `obsidian tags sort=count format=json` to get all tags ranked by frequency.
- Report: most-used tags, tag hierarchy structure (nested vs flat), potential duplicates or inconsistencies (e.g., "meeting" vs "meetings", case mismatches).
- Suggest tag renames using `obsidian tags:rename old=<old> new=<new>` — always confirm with user first.

**"check orphans":**
- Run `obsidian orphans` to find notes with zero incoming or outgoing links.
- Present the list grouped by folder.
- For each orphan, suggest whether it should be linked to existing notes, archived, or deleted.

**"check links" or "check broken":**
- Run `obsidian unresolved` to find all broken/unresolved wikilinks across the vault.
- Report each broken link with its source note so the user can fix or remove them.
- Suggest whether the target was likely renamed (offer to fix) or deleted (offer to remove the link).

**"check structure":**
- Run `obsidian folders format=tree` for the directory hierarchy.
- Run `obsidian files total` for the vault-wide note count.
- Use obsidian_list_notes at the root with recursionDepth=1 for per-folder file counts.
- Report folder sizes, identify very large (>50 notes) or very small (1-2 notes) folders, and suggest organizational improvements.

**"check full" or "check audit":**
Run all focused analyses in sequence: structure → tags → orphans → links. Present a comprehensive report with actionable recommendations.

If none of these focus keywords are present (just "check" or no arguments), proceed to the full health report below.

### Step 2: Run diagnostics

Execute these in sequence and collect results:

**Structure:**
```bash
obsidian folders format=tree
obsidian files total
obsidian files folder="" format=json    # Root-level notes (should be minimal)
```

**Connectivity:**
```bash
obsidian orphans
obsidian unresolved
```

**Consistency:**
Sample 5-10 notes across different types and check frontmatter:
```bash
obsidian search query="[type:meeting]" format=json
obsidian search query="[type:literature]" format=json
obsidian search query="[type:project]" format=json
obsidian tags sort=count format=json
```
For each type found, read properties from 2-3 examples:
```bash
obsidian properties file="<note>" format=json
```

**Processing:**
```bash
obsidian search query="[status:processing]" format=json
obsidian search query="[summarization-layer:1]" format=json
```

**Plugins:**
```bash
obsidian plugins format=json
```

### Step 3: Score and report

Present a health report with scores for each dimension. Use a simple scale:

- **Structure**: [Good / Needs attention / Needs work] — based on folder organization, root clutter, depth
- **Connectivity**: [Good / Needs attention / Needs work] — based on orphan ratio, broken links, MOC coverage
- **Consistency**: [Good / Needs attention / Needs work] — based on frontmatter adherence, tag style uniformity
- **Processing**: [Good / Needs attention / Needs work] — based on stale items, summarization progress
- **Plugins**: [Fully equipped / Missing recommended / Not checked]

For each dimension that needs attention, provide 1-3 specific, actionable suggestions:

Example output:
```
## Vault Health Report

| Dimension | Status | Details |
|-----------|--------|---------|
| Structure | Needs attention | 23 notes in root, no Inbox folder |
| Connectivity | Needs work | 45% orphan ratio, 3 broken links, no MOCs |
| Consistency | Good | Tags consistent, frontmatter mostly uniform |
| Processing | Needs attention | 8 notes stuck at status:processing for >2 weeks |
| Plugins | Missing recommended | Dataview not installed (would enable dashboard queries) |

## Recommended Actions (by impact)

1. **Fix 3 broken wikilinks** — These notes reference deleted or renamed files.
   Run: `/vault-align fix` to resolve them.

2. **Connect 15 orphan notes** — These notes have zero links in or out.
   Run: `/vault-connect recent` to find and build missing connections.

3. **Process 8 stale items** — Notes stuck at processing status.
   Review each and either promote to permanent note or update status.
```

End with: "Want me to start fixing any of these? You can also run `/vault-align fix` to tackle the highest-impact issue, or `/vault-align migrate` for bulk reorganization."

If a setup log exists with skipped items, also surface those: "From your vault setup, these items were deferred and are ready to revisit: [list skipped items]"

---

## "fix" — Execute Highest-Impact Fix

1. Run the same diagnostics as "check" (or use results from the most recent check if in the same session).
2. Identify the single highest-impact issue using this priority order:
   - Broken wikilinks (fix immediately)
   - Orphan notes with obvious connections (link them)
   - Stale processing items (prompt user to review)
   - Tag duplicates (merge them)
   - Frontmatter gaps (add missing properties)
   - Structural issues (suggest moves)

3. Present the fix clearly:
   "The highest-impact fix right now is [description]. Here's what I'll do: [specific changes]. This affects [N] notes."

4. Wait for user confirmation.

5. Execute the fix:
   - Broken links: read the source note, determine if the target was renamed or deleted, suggest correction or removal
   - Orphan notes: use the vault-connect workflow to find and suggest links
   - Tag duplicates: `obsidian tags:rename old=<variant> new=<canonical>`
   - Frontmatter gaps: `obsidian properties:set file="<note>" <property>=<value>`
   - Structural: `obsidian move file="<note>" to=<folder>/`

6. After the fix, re-check the affected dimension and report the improvement.

7. Ask: "Want me to continue with the next highest-impact fix?"

---

## "migrate" — Aggressive Reorganization

This mode is for users who want a comprehensive, batch reorganization of their vault. It's the aggressive option that `/vault-setup` offers to defer.

### Step 1: Audit and plan

Run the full diagnostic suite (same as "check"). Then build a migration plan organized into phases:

**Phase A — File Organization:**
Analyze all notes and propose folder assignments:
```bash
obsidian files format=json
```
For each note, determine the best target folder based on:
- `type` property (project → Projects/, literature → Resources/, etc.)
- Tag content (project-specific tags → that project's folder)
- Filename patterns (dates suggest daily notes, "Meeting" suggests meetings folder)
- Content analysis (read a sample if type/tags don't make it clear)

Present the plan as a table:
| Current Location | Note | Proposed Location | Reason |
|-----------------|------|-------------------|--------|
| root | "ML Pipeline" | Projects/ML Pipeline/ | type:project, status:active |
| root | "Gradient Descent" | Resources/Machine Learning/ | type:permanent, tag:ml |

**Phase B — Tag Consolidation:**
List all tag duplicates and propose merges:
| Merge From | Merge To | Notes Affected |
|-----------|----------|----------------|
| #meetings | #meeting | 12 |
| #ML | #machine-learning | 8 |

**Phase C — Frontmatter Standardization:**
List notes with missing or inconsistent properties:
| Note Type | Missing Property | Notes Affected | Proposed Value |
|-----------|-----------------|----------------|----------------|
| meeting | status | 23 | open |
| literature | summarization-layer | 15 | 1 |

**Phase D — Connectivity:**
Suggest MOC creation for unindexed clusters and orphan note connections.

### Step 2: Execute with per-phase approval

Present each phase separately. The user can approve, modify, or skip each one independently.

For file moves, always use `obsidian move` (preserves wikilinks). Process in batches of 10-15 notes with confirmation between batches.

After each phase, run `obsidian unresolved` to verify no links were broken.

### Step 3: Report

After migration, present a before/after summary:
- Notes moved: X
- Tags consolidated: Y merges affecting Z notes
- Properties standardized: W notes updated
- New MOCs created: N

---

## "plugins" — Plugin Audit

Check installed plugins against recommendations for the user's archetype.

```bash
obsidian plugins format=json
```

Cross-reference against the recommended plugin list. The recommendations depend on the user's methodology (read from `_vault-setup-log.md` if it exists, otherwise use general recommendations):

| Plugin | ID | Purpose | Recommended When |
|--------|-----|---------|-----------------|
| Dataview | `dataview` | Query notes like a database | Dashboard, MOC automation, any structured queries |
| Kanban | `obsidian-kanban` | Drag-and-drop project boards | Project management workflow |
| Templater | `templater-obsidian` | Advanced template variables | Heavy template usage |
| Calendar | `calendar` | Calendar view for daily notes | Active daily note usage |
| Tasks | `obsidian-tasks` | Enhanced task management | Task tracking across notes |

For each recommended plugin:
- **Installed and enabled** → "Dataview is installed and active."
- **Installed but disabled** → "Kanban is installed but disabled. Want me to enable it?" → `obsidian plugin:enable id=obsidian-kanban`
- **Not installed** → "Templater is recommended for your template-heavy workflow. To install: Settings → Community plugins → Browse → search 'Templater' → Install → Enable. Let me know when it's installed and I'll configure it."

After the audit, update the `_vault-setup-log.md` plugin status table if it exists.
