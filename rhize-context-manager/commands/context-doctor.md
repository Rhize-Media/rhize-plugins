---
description: Health-check the full Rhize context stack — Headroom, claude-mem, OpenWolf, Serena/CodeGraph, RTK — and flag overlap, drift, or dead layers
---

# /context-doctor

Run a structured health check of every context layer, report a per-layer status table,
and flag coexistence problems. Read-only — diagnose and report; do not change any
configuration unless the user asks afterward.

## Checks

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

## Output

A compact table: layer | scope | status (OK / degraded / dead / not installed) | note.
Then a short "Flags" section listing overlap/conflict findings with the recommended
action (per the `context-stack` skill), and nothing else. If everything is clean, say so
in one line.
