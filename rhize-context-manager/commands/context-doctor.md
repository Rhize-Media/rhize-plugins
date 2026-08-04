---
description: Health-check the full Rhize context stack — Headroom, claude-mem, OpenWolf, Serena/CodeGraph, RTK — and flag overlap, drift, or dead layers
model: sonnet
---

# /context-doctor

Run a structured health check of every context layer, report a per-layer status table,
and flag coexistence problems. Read-only on configuration — diagnose and report; never
change `stack.config.json` or any tool's config yourself (that's `/context-setup`). The
**only** write this command makes is persisting its own run result (Step 2 below), so a
later run — or another tool — can see what changed.

## Step 1 — Run the checks

1. **Headroom (wire proxy)**
   - Process/port: `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8787/health || true` (any response beats connection-refused)
   - Recent errors: `tail -20 ~/.headroom/guard.log 2>/dev/null`
   - Current repo wired? Check `.claude/settings.local.json` for the proxy config.
2. **RTK (CLI compression)**
   - `rtk --version` and `rtk gain | head -20` (savings analytics; zero recent savings in an active repo = hook may be dead).
3. **claude-mem (global memory)**
   - Dashboard: `curl -s -o /dev/null -w "%{http_code}" http://localhost:37777 || true`
   - Confirm recall context appeared this session (look for the observation digest in session start).
4. **OpenWolf (per-repo)**
   - `.wolf/` present in cwd? If yes: `cat .wolf/config.json` and check token ledger freshness; note last cron-state timestamp.
5. **Serena / CodeGraph (code nav)**
   - `.codegraph/` present? If yes, one `codegraph_explore` smoke query (or `codegraph explore` CLI).
   - Serena MCP connected? (ToolSearch for `serena` tools.)
   - Flag if BOTH are active in the same repo — redundant indexing.
6. **Graphiti (opt-in)**
   - Only if configured: check the graphiti MCP server responds. Otherwise report "not adopted yet (by design)".
7. **Coexistence scan**
   - SessionStart wall-time subjectively slow? Duplicated context injected this session (claude-mem recall vs OpenWolf index)? Report per the context-stack skill's watch list.

## Step 2 — Persist this run

Write the result as machine-readable JSON to
`~/.claude/context-manager/doctor/<YYYY-MM-DD-HHMM>.json` (local time, e.g.
`2026-08-04-1248.json`; create the `doctor/` directory if it doesn't exist). This is the
only file this command ever writes — it is a log of this command's own output, not
configuration.

Shape:
```json
{
  "timestamp": "2026-08-04T12:48:00-05:00",
  "repo": "<CLAUDE_PROJECT_DIR basename>",
  "layers": [
    { "name": "Headroom", "layer": "wire", "status": "OK", "note": "proxy responding, wired in .claude/settings.local.json" },
    { "name": "RTK", "layer": "cli", "status": "OK", "note": "..." }
  ],
  "flags": [
    "Serena and CodeGraph both active in this repo — redundant indexing, prefer CodeGraph (.codegraph/ present)"
  ]
}
```
`status` is one of `OK`, `degraded`, `dead`, `not_installed` — matching the Step 1 table.

## Step 3 — Delta against the previous run

Before persisting, check `~/.claude/context-manager/doctor/` for an existing run file
(the most recent by filename — the `YYYY-MM-DD-HHMM` naming sorts chronologically). If
one exists, diff its `layers[].status` and `flags` against this run's, and print a short
**Delta** section: layers whose status changed, and flags that are new or resolved since
last time. If no previous run exists, skip this section — don't report "no changes" as a
false delta.

## Step 4 — Harness audit handoff (if available)

As a final step, check whether the `ecc` plugin's `harness-audit` skill is available
(look for `ecc:harness-audit` in the available-skills listing). If it is, invoke it via
the Skill tool as a complementary deeper pass over the harness configuration. If it
isn't installed/enabled, print one line — `ecc:harness-audit not available — skipping`
— and stop. Never treat its absence as an error.

## Output

A compact table: layer | scope | status (OK / degraded / dead / not installed) | note.
Then a short "Flags" section listing overlap/conflict findings with the recommended
action (per the `context-stack` skill). Then, if applicable, the "Delta" section from
Step 3. Then the one-line harness-audit outcome from Step 4. If everything is clean and
unchanged, say so in one line instead of an empty table.

To act on any flag raised here (enable/disable a layer, wire a hook), use
`/context-setup` — this command only diagnoses and persists its own run log.

## Cadence

Scheduled weekly via the standalone `weekly-context-doctor` routine
(`~/Documents/Claude/Scheduled/weekly-context-doctor/SKILL.md`, Thursday mornings —
deliberately a different day than the Monday `weekly-skill-audit` routine so the two
weekly signals don't blur). That routine runs this command drift-only: a one-line "no
drift" report unless the Step 3 delta actually found a change. On-demand runs of
`/context-doctor` remain fine any time.
