---
description: Periodic review — summarize captures, surface themes, plan ahead
allowed-tools: ["mcp__obsidian-mcp-server__obsidian_global_search", "mcp__obsidian-mcp-server__obsidian_read_note", "mcp__obsidian-mcp-server__obsidian_update_note", "mcp__obsidian-mcp-server__obsidian_list_notes", "mcp__obsidian-mcp-server__obsidian_manage_frontmatter", "Bash"]
argument-hint: [daily|weekly|monthly]
---

Run a periodic review of the vault — summarize recent activity, surface patterns, flag stale items, and resurface forgotten notes worth revisiting. This is the "spaced repetition for your notes" workflow that keeps a vault alive.

Parse "$ARGUMENTS" to determine the review scope:

**"daily" or no arguments:**
1. **Read today's daily note** — Run `obsidian daily:read`.
2. **Summarize** — List what was captured today: tasks created, notes added, ideas logged.
3. **Task status** — Count open vs. completed tasks from the daily note.
4. **Unprocessed captures** — Identify fleeting notes or quick captures that haven't been turned into permanent notes or linked into the vault.
5. **Suggest next actions** — "You captured an idea about X — want to develop that into a permanent note?" or "The meeting note from today has 3 action items with no due dates."

**"weekly":**
1. **Gather the week's daily notes** — Run `obsidian daily:open date=<date>` for each day of the past 7 days (or use `obsidian search query="[type:daily]"` with date filters). Read each one.
2. **Activity summary:**
   - Notes created this week: `obsidian files sort=created limit=20 format=json` filtered to the last 7 days
   - Notes modified this week: `obsidian files sort=modified limit=20 format=json` filtered to the last 7 days
   - Tasks completed vs. still open across all daily notes
3. **Theme detection** — Across all captures, notes, and daily entries, identify the 3-5 dominant topics or themes of the week.
4. **Stale items** — Find:
   - Tasks older than 7 days that are still open: search for unchecked `- [ ]` in recent notes
   - Notes with `status: processing` or `status: review` that haven't been touched in 7+ days
   - Draft notes that were started but not completed
5. **Connection opportunities** — Among notes created this week, identify any that should be linked to each other or to existing vault content but aren't yet.
6. **Forgotten notes** — Surface 2-3 random notes from the vault that haven't been modified in 30+ days. Present them as "worth revisiting?" — this mimics spaced repetition and prevents knowledge from going stale.
7. **Weekly review note** — Offer to create a weekly review note using the weekly review template (from the vault-templates skill) pre-filled with the findings above.

**"monthly":**
1. **Run the weekly review scope** for the past 30 days (summarized, not day-by-day).
2. **Growth stats:**
   - Total notes in vault: `obsidian files total`
   - Notes created this month vs. last month
   - Most active folders and tags
3. **Knowledge graph health:**
   - Run `obsidian orphans` — how many disconnected notes exist?
   - Run `obsidian unresolved` — how many broken links?
   - Average link density — are notes getting more or less connected over time?
4. **MOC audit** — List existing MOCs and check:
   - Are any MOCs getting too large? (>20 links — suggest splitting)
   - Are there topic clusters with no MOC? (suggest creating one)
   - Are any MOCs stale? (not updated in 30+ days despite new notes in their topic)
5. **Progressive summarization check** — Find notes with `summarization-layer: 1` that were created 30+ days ago. These are candidates for a second pass of progressive summarization.
6. **Neglected areas** — Identify tags or folders with no new activity in the past month. Are they still relevant, or should they be archived?
7. **Monthly review note** — Offer to create a monthly review note with vault statistics, themes, and goals for next month.

For all review types, present findings as a clean report with actionable recommendations. Don't just list problems — suggest specific next steps for each finding. Confirm with the user before creating review notes or making any modifications.
