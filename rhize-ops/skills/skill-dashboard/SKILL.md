---
name: skill-dashboard
tier: custom
domain: meta
maturity: stable
description: Render the live skill-monitor audit dashboard. Aggregates every per-run snapshot in ~/dev-local/RHIZE/rhize-plugins/rhize-ops/skill-monitor/data/snapshots/ into one interactive view (weekly trend, top skills with rank deltas, direct/indirect leverage, prune candidates, subagent-type breakdown, project rollup, host/Cowork split, week-over-week delta). Use when the user says "show the skill dashboard", "render the audit dashboard", "skill usage dashboard", "/skill-dashboard", or asks to visualize skill-monitor data.
allowed-tools: Bash mcp__chrome-devtools__new_page
---

# skill-dashboard

Render the live skill-monitor dashboard from accumulated weekly-audit snapshots. Two render paths — pick based on the chat surface.

The skill-monitor tool lives alongside this skill in the `rhize-ops` plugin at `~/dev-local/RHIZE/rhize-plugins/rhize-ops/skill-monitor/`.

## Pick the render path first

- **You can emit Claude Artifacts** (Claude Desktop, claude.ai, or any chat UI with the right-hand artifact panel) → use **Path A: artifact**. This is what the user sees in the artifacts column.
- **You're in Claude Code (terminal CLI)** or any environment without artifact rendering → use **Path B: external HTML**. Opens in the user's browser.

If unsure which surface you're on, default to Path A and verify the artifact renders. Only fall back to Path B if artifact emission fails or the user says they don't see it.

## Path A — Claude Artifact (primary)

1. Generate ready-to-paste JSX source. Snapshots and keep-list are inlined into the source as module-level constants:

   ```
   python3 ~/dev-local/RHIZE/rhize-plugins/rhize-ops/skill-monitor/dashboard.py --out artifact --json-out /tmp/skill-dashboard.jsx
   ```

   If the script errors (e.g. "no snapshots found"), stop and tell the user to run `python3 ~/dev-local/RHIZE/rhize-plugins/rhize-ops/skill-monitor/monitor.py --days 0` first to seed at least one snapshot. Don't fabricate.

2. Read the file (`/tmp/skill-dashboard.jsx`) and emit its contents inside an `<antArtifact>` block:

   ```
   <antArtifact identifier="skill-audit-dashboard" type="application/vnd.ant.react" title="Skill Audit Dashboard">
   [paste the entire contents of /tmp/skill-dashboard.jsx here]
   </antArtifact>
   ```

   The file already contains the imports (`react`, `recharts`), inlined data, and a default `App` export — paste it verbatim. The artifact runtime mounts the dashboard automatically.

3. After emitting the artifact, send a one-line summary in chat: how many snapshots are inlined and the date range they cover. Parse this from the `dashboard.py` stdout (`N snapshots, K KB`).

## Path B — external HTML (fallback)

1. Generate the HTML to a temp path. Always render to `/tmp` first — never overwrite the vault copy from inside this skill (the weekly scheduled task owns that path):

   ```
   python3 ~/dev-local/RHIZE/rhize-plugins/rhize-ops/skill-monitor/dashboard.py --out html --html-path /tmp/skill-dashboard.html
   ```

2. Open the generated file. Two options, in priority order:

   - **Preferred — chrome-devtools MCP.** Call `mcp__chrome-devtools__new_page` with `url: "file:///tmp/skill-dashboard.html"`.
   - **Fallback — `open(1)`.** Run `open /tmp/skill-dashboard.html` (macOS) so it loads in the default browser.

3. Report to the user, in two lines:
   - Path to the rendered HTML
   - Number of snapshots inlined and the date range they cover

## Optional: refresh data first

If the user asks to "refresh" / "rerun" / "update" the dashboard with current data, run `python3 ~/dev-local/RHIZE/rhize-plugins/rhize-ops/skill-monitor/monitor.py --days 0` first — that captures a new all-time snapshot. Then proceed with Path A or B above. This is an explicit-request-only behavior; do not run monitor.py on every dashboard render.

## Notes

- Sources: `~/dev-local/RHIZE/rhize-plugins/rhize-ops/skill-monitor/SkillDashboard.jsx` (component), `~/dev-local/RHIZE/rhize-plugins/rhize-ops/skill-monitor/dashboard.py` (emitter and JSX transform).
- Snapshots accumulate weekly via the `weekly-skill-audit` scheduled task. Backfilled snapshots (`_backfilled_from_markdown: true`) have empty `events` arrays; the dashboard handles them gracefully.
- The vault HTML at `~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian Vault/Projects/Skill-Audit-and-Monitoring/dashboard.html` is the long-lived copy — refreshed every Monday by the scheduled task. This skill renders to `/tmp` (Path B) or emits inline (Path A) to avoid stomping it.
- Don't push git commits.
