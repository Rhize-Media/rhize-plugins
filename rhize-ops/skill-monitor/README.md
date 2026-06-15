# skill-monitor

Tracks which Claude skills actually get invoked across all Claude Code / Cowork / VSCode sessions on this Mac.

## Why

Per [[Anthropic Runs Hundreds of Skills - Only 12 Run Weekly]]: most published skills never get invoked. You can't prune what you can't measure. This script measures.

## What it does

Walks two transcript trees, extracting every `tool_use` block where `name == "Skill"`:

- `~/.claude/projects/<encoded-proj>/**/*.jsonl` — host CLI sessions
- `~/Library/Application Support/Claude/local-agent-mode-sessions/**/*.jsonl` — Cowork desktop-app sessions (mapped back to the user-side `originCwd` via session metadata in `~/Library/Application Support/Claude/claude-code-sessions/`)

Aggregates:

- Total invocations + unique skills used
- **Two invocation channels:** the **Skill tool** (`tool_use`, `name:"Skill"`) and
  **slash commands** (`/name` typed in a `type:"user"` turn). Slash commands often
  fire no Skill tool_use, so they were historically invisible; they are now captured
  on the `slash_command` channel. Built-in CLI commands (`/clear`, `/model`, …) are
  filtered via a denylist; hook-triggered skills are out of scope (measured as
  effectively non-existent). The headline total is **reconciled**: a `(session, skill)`
  pair recorded on both channels is counted once. See the *By invocation channel*
  report section and `.claude/plans/capture-slash-command-skill-invocations.md`.
- Top skills (rank table)
- Direct (main-session) vs. indirect (real subagent work) vs. auto-compaction split
- By project (cwd-based), by entrypoint, week-by-week
- Indirect skill use grouped by `subagent_type` (resolved from each main session's `toolUseResult.agentType`)
- Writes a timestamped markdown report into the Obsidian vault at
  `Projects/Skill-Audit-and-Monitoring/weekly-reports/YYYY-MM-DD-skill-usage.md`. Only
  the canonical `--days 7` weekly keeps that plain name; any other window self-suffixes
  (e.g. `YYYY-MM-DD-skill-usage-28d.md`, `-0d` for all-time), mirroring the snapshot
  naming so a same-day `--days 28` run can't overwrite the weekly report.
- Writes raw JSON to `~/dev-local/RHIZE/rhize-plugins/rhize-ops/skill-monitor/data/skill-usage.json` (rolling latest, overwritten each run) and an immutable per-run snapshot to `~/dev-local/RHIZE/rhize-plugins/rhize-ops/skill-monitor/data/snapshots/YYYY-MM-DD-skill-usage-{N}d.json` (used by the live dashboard). The `-{N}d` suffix encodes the `--days` window so an ad-hoc `--days 0` run doesn't overwrite the canonical `--days 7` weekly snapshot.

## Usage

```bash
# Default: last 7 days, writes MD report into the vault
python3 monitor.py

# All-time
python3 monitor.py --days 0

# Last 28 days (recommended monthly pruning cadence)
python3 monitor.py --days 28

# Dry run outside the vault
python3 monitor.py --report-dir ./out --json-out ./out/data.json

# Skip the Cowork tree (host CLI only)
python3 monitor.py --cowork-dir ""
```

## Live dashboard

`dashboard.py` reads every `data/snapshots/*.json` and renders a single self-contained HTML dashboard with charts (weekly trend, top skills, direct/indirect leverage scatter, prune candidates, subagent-type breakdown, project rollup, host-vs-Cowork split, week-over-week delta).

By default the HTML is **fully offline**: the React/Recharts/Babel/Tailwind CDN
bundles are downloaded once (cached under `data/cdn-cache/`, gitignored) and inlined
into the output, so the dashboard renders inside Obsidian's HTML preview and other
sandboxed iframes that block external `<script src>`. Pass `--online` to keep remote
`<script src>` tags instead (smaller file, needs network at view time).

```bash
# Render to the default vault path (offline, CDN inlined):
#   <vault>/Projects/Skill-Audit-and-Monitoring/dashboard.html
python3 dashboard.py --out html

# Keep remote CDN tags instead of inlining (smaller, needs network to view)
python3 dashboard.py --out html --online

# Render somewhere else for testing
python3 dashboard.py --out html --html-path /tmp/dashboard.html

# Emit a JSON envelope (component source + inlined snapshots) for use as a
# Claude Artifact — consumed by the skill-dashboard skill (Phase 3).
python3 dashboard.py --out artifact > /tmp/dashboard-payload.json
```

The HTML file is ~500 KB, opens in any browser, and pulls React + Recharts + Tailwind from public CDNs (no install). `keep-list.yaml` (one skill name per line) seeds the prune-candidates filter.

## Data model

A skill invocation looks like this in the transcript JSONL:

```json
{
  "type": "tool_use",
  "name": "Skill",
  "input": { "skill": "obsidian-second-brain:vault-recall", "args": "..." },
  "caller": { "type": "direct" }
}
```

- **Direct** = line appears in `<projects>/<proj>/<sessionId>.jsonl` (either tree)
- **Indirect (real subagent work)** = line appears in `<projects>/<proj>/<sessionId>/subagents/<agent>.jsonl` and the agent is *not* an `acompact-*` background compaction agent
- **Indirect (auto-compaction)** = same path but `agentId` starts with `acompact-`. Bucketed separately so background context-compaction noise doesn't pollute the real subagent-delegation signal.

## Scheduled runs

Wired into the `scheduled-tasks` MCP (skill: `weekly-skill-audit`). Fires Monday mornings. See `/Users/jamesdeola/Documents/Claude/Scheduled/weekly-skill-audit/SKILL.md`.

## Workflow — using the dashboard with the weekly audit

### Monday morning (no action required)

At 08:30 the `weekly-skill-audit` scheduled task runs through six steps:

1. `monitor.py --days 7` walks every transcript on the Mac, writes the markdown report into the vault, and drops a fresh `YYYY-MM-DD-skill-usage-7d.json` into `data/snapshots/`.
2–4. The agent diffs this week vs. last week, appends a "Week-over-week delta" section to the markdown, and on every 4th Monday additionally runs `--days 28` for the rolling-window prune view.
5. `dashboard.py --out html` rebuilds `dashboard.html` from the accumulated snapshots — the new data point lands in the trend chart, rank-delta arrows update.
6. A one-line summary lands in your main session.

By the time you sit down Monday, both artifacts (markdown report + HTML dashboard) are in the vault and synced to iCloud.

### What to read, in what order

For a 30-second pulse check, **open the dashboard first**. The KPI tiles tell you whether anything material moved. Scan the trend chart — flat means no action; spike or crater means drop into the relevant detail section.

For decisions, **read the markdown report**. The scheduled task curates "Newly-used / Dropped / Big movers" textually with context Claude already extracted. The dashboard shows the same data visually but doesn't write commentary.

The two artifacts are complementary: dashboard for at-a-glance pattern recognition, markdown for "what should I actually do this week."

### Specific signals each section is built to surface

- **Direct vs. indirect leverage scatter** (dashboard §4): any skill above the diagonal — your subagents reach for it more than you do directly. That's a trigger description weakness in your main session, not a skill problem. Open the skill's `description:` field and tighten the trigger phrases.
- **Prune candidates table** (dashboard §5): skills that fired historically but aren't in the latest snapshot. This is your disable list — once a skill has been on it for 28 consecutive days and isn't in `keep-list.yaml`, it's safe to remove.
- **Indirect by subagent type** (dashboard §6): which subagents are actually doing skill-leveraged work. If `code-reviewer` shows zero or near-zero, your code-review subagent isn't picking up your project skills.
- **Week-over-week delta** (dashboard §9 / markdown bottom): "Lost this week" plus a big-movers row. Short-term, ignore single-week drops on Tier A skills (the 30-day-tactic rule). On Tier E plugins, even one week of zero is a confirmation.

### Mid-week — on-demand views

You don't have to wait for Monday:

- In a Claude chat, `/skill-dashboard` (or "show the skill dashboard") fires the project skill. It re-renders dashboard HTML to `/tmp` from the **current** `data/snapshots/` and opens it. No transcript rescan — just a fresh render of accumulated data, ~1 second.
- For fresh data mid-week, `python3 monitor.py --days 0` captures a new all-time snapshot (lands as `<date>-skill-usage-0d.json`, doesn't clobber the canonical `-7d`). Then re-render.
- For an ad-hoc window, `--days 14` writes `-14d.json`, all snapshots accumulate, and the dashboard shows the widest-window view per date.

### Keep-list workflow

`keep-list.yaml` is your "don't suggest pruning this even when it's idle" allowlist. Edit it whenever the prune-candidates table flags a skill you actually want to keep around (rare-but-strategic). The dashboard re-reads it on every render, so the change shows immediately.

Suggested cadence: do a 5-minute pass once a month after the 28-day report run. Anything in the prune table that you'd actually defend belongs on the keep-list; anything you wouldn't, mark for disable.

### Three failure modes to know

- **Dashboard renders empty.** No snapshots yet — run `monitor.py --days 0` to seed one.
- **Trend chart shows only one data point.** You only have today's snapshot, OR all snapshots are from the same date. Wait for next Monday or let history accumulate.
- **Cowork projects show as `[Cowork: /sessions/<name>]`.** That session's metadata file isn't on disk (only ~38% of Cowork sessions have one). The data still counts; the project label is just unmapped. Nothing to fix on your side.

## Roadmap

- [ ] Add slash-command detection (user messages starting with `/<cmd>` that map to skill commands)
- [ ] Track *skill loads* (the `Skill tool loaded` marker) separately from *skill invocations*
- [x] ~~Join Cowork session transcripts into the same dataset~~ — done 2026-05-08
- [x] ~~Tag skills as keep / prune / watch based on a YAML allowlist~~ — partial; `keep-list.yaml` filters prune candidates in the dashboard. Watch/regression alerting still TODO.
- [x] ~~Emit a weekly delta~~ — done; rendered in the live dashboard's "Week-over-week" section.
- [ ] Wire `dashboard.py --out html` into the weekly scheduled task (Phase 4 of the dashboard plan).
- [ ] Add a project-local `skill-dashboard` skill so Claude can render the dashboard as a chat artifact on demand (Phase 3 of the dashboard plan).
