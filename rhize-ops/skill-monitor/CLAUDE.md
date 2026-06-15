# skill-monitor — agent context

Project-level instructions for Claude (and other coding agents) working on this repo. The user's global CLAUDE.md still applies; this file adds project-specific context.

## What this project is

A small audit tool that walks every Claude Code transcript on the user's Mac, extracts `Skill` `tool_use` events, and produces:

1. A weekly **markdown report** in the user's Obsidian vault at `Projects/Skill-Audit-and-Monitoring/weekly-reports/YYYY-MM-DD-skill-usage.md`
2. A **JSON snapshot** at `data/snapshots/YYYY-MM-DD-skill-usage.json` (immutable per-run history)
3. A **live HTML dashboard** at `<vault>/Projects/Skill-Audit-and-Monitoring/dashboard.html` aggregating every snapshot into one interactive view

The thesis: skill libraries obey a power law (Anthropic data: ~300 skills installed, ~12 run weekly). You can't prune what you don't measure. This is the measurement.

## File map

| Path | Role |
|---|---|
| `monitor.py` | Stdlib-only walker. Extracts Skill tool_use events from `~/.claude/projects/` (host CLI) AND `~/Library/Application Support/Claude/local-agent-mode-sessions/` (Cowork desktop). Writes JSON + markdown report + per-run snapshot. |
| `dashboard.py` | Stdlib-only emitter. Reads `data/snapshots/*.json`, renders the dashboard HTML (`--out html`) into the vault, or a JSON envelope (`--out artifact`) for use as a Claude Artifact. |
| `SkillDashboard.jsx` | Single React component (no build step). Renders 10 sections: KPIs, weekly trend (stacked area), top 25 skills with rank-deltas, direct/indirect leverage scatter, prune candidates, indirect-by-subagent-type, top projects, host/Cowork donut, week-over-week delta, footer. |
| `dashboard-template.html` | HTML wrapper. Loads React 18 + prop-types + Recharts + Tailwind + Babel-standalone from CDNs. |
| `keep-list.yaml` | Optional skill allowlist. Filters the dashboard's prune-candidates table. |
| `data/skill-usage.json` | Rolling-latest payload. Overwritten each `monitor.py` run. *Gitignored.* |
| `data/snapshots/YYYY-MM-DD-skill-usage-{N}d.json` | Immutable per-run history. The `{N}d` suffix encodes the `--days` window so distinct windows for the same date coexist (`-7d` weekly, `-0d` all-time, etc.). ~100 KB to ~500 KB each. *Gitignored.* The dashboard dedupes same-date snapshots by keeping the widest window. |
| `.claude/plans/` | Implementation plans. Two so far: `skill-monitor-coverage-fixes.md` (Cowork tree integration), `live-artifact-dashboard.md` (this dashboard). |
| `../skills/skill-dashboard/` | Promoted to the `rhize-ops:skill-dashboard` plugin skill — renders the dashboard on demand from chat. |

## Hard constraints

- **Stdlib only.** `monitor.py` and `dashboard.py` must not introduce non-stdlib dependencies. The dashboard's React/Recharts/Tailwind come in via browser CDN, not via Python.
- **Single-file scripts.** Don't restructure into a package.
- **Don't change the existing CLI surface.** `python3 monitor.py --days 7`, `--days 28`, `--days 0`, `--report-dir`, `--json-out`, `--cowork-dir` must keep working — the scheduled task at `~/Documents/Claude/Scheduled/weekly-skill-audit/SKILL.md` depends on them.
- **Don't reorder existing markdown report sections.** Downstream readers parse positionally. Add new sections at the bottom or as subsections.
- **Don't push commits unless explicitly told.** Per the user's global CLAUDE.md.

## How to run

```bash
# Audit (default: last 7 days)
python3 monitor.py
python3 monitor.py --days 0          # all-time
python3 monitor.py --cowork-dir ""   # host CLI only, no Cowork

# Render dashboard
python3 dashboard.py --out html                    # → vault/.../dashboard.html
python3 dashboard.py --out html --html-path /tmp/d.html
python3 dashboard.py --out artifact > /tmp/d.json  # JSON envelope for Claude Artifact

# Render via the project skill (same effect, plus auto-opens in browser)
# Trigger phrases: "show the skill dashboard", "render the audit dashboard"
```

## Verification expectations

When making changes to `monitor.py` or `dashboard.py`, run both end-to-end before committing:

```bash
python3 monitor.py --days 0 && python3 dashboard.py --out html --html-path /tmp/d.html
```

For dashboard component changes, sanity-check in a real browser via the chrome-devtools MCP (`mcp__chrome-devtools__new_page`) — verify zero console errors and that all 10 sections render.

Idempotency: two consecutive `dashboard.py --out html` runs should produce byte-identical HTML.

## Data shape (latest)

`data/snapshots/<date>-skill-usage.json`:
```jsonc
{
  "events": [{ skill, source_type, uuid, session_id, agent_id, agent_slug, entrypoint, cwd, cowork_local_id, timestamp, transcript_file, ... }],
  "report": {
    generated_at, window_days, total_invocations, unique_skills_used,
    top_skills, direct_top, indirect_top, indirect_compaction_top,
    by_week, by_project, by_entrypoint, by_source_type, indirect_by_slug
  }
}
```

Backfilled snapshots (parsed from old markdown reports) carry `_backfilled_from_markdown: true` and have empty `events` arrays. The dashboard handles both shapes.

## Scheduled run

The user's `weekly-skill-audit` scheduled task fires Monday mornings and runs:

1. `python3 monitor.py --days 7` (writes the markdown report + snapshot)
2. The agent appends a "Week-over-week delta" section to the markdown
3. `python3 dashboard.py --out html` (refreshes the vault dashboard)
4. The agent posts a one-line summary

Source: `~/Documents/Claude/Scheduled/weekly-skill-audit/SKILL.md`. That file lives outside this repo by design (it's part of the user's home-dir scheduled tasks, not this project's source).

## Vault docs

The conceptual home for the project is in the user's Obsidian vault:

- `Projects/Skill-Audit-and-Monitoring/README.md` — the *why* (power-law thesis, tier strategy, 90-day prune plan)
- `Projects/Skill-Audit-and-Monitoring/Skill Audit and Monitoring System.md` — the *how* (technical design, data model, components)
- `Projects/Skill-Audit-and-Monitoring/Live Dashboard.md` — what `dashboard.html` is, when it refreshes, what each section means

When meaningful behavior changes here, update the vault System doc to match. When the dashboard's section list changes, update the vault Live Dashboard note too.
