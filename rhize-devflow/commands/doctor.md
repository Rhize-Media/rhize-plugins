---
description: Read-only plugin/install health check — manifests, canonical commands, referenced assets, duplicate bodies, stale tokens, script/hook integrity, and capability dependencies
---
<!-- canonical: rhize-devflow:doctor -->

# Doctor

Validate Dev Flow's own install health. This is a thin adapter over
`scripts/devflow.py doctor` — that CLI is the canonical implementation; this command runs it
and interprets the result.

## Core Contract

- **Read-only.** Never writes, edits, or deletes anything — inspection only.
- **Works from either install shape.** Resolves `$CLAUDE_PLUGIN_ROOT` at runtime, so the same
  invocation is correct from a source checkout and an installed plugin cache.
- **Capabilities degrade independently.** A missing dependency (e.g. no Chrome DevTools MCP)
  is reported as that one capability degraded — never rolled up into a plugin-wide failure.
  Report each degraded capability by name.
- **MCP server detection checks more than the repo's own `.mcp.json`.** By default it scans,
  in order: the repo-local `.mcp.json`; `~/.claude.json` (its top-level `mcpServers` map plus
  the per-project `projects.<repo path>.mcpServers` entry for the inspected repo); and
  `~/.codex/config.toml`'s `mcp_servers` table (best-effort — skipped silently if absent or
  unparsable). Only server *names* are ever read from the user-level files — never configs or
  credential values — and `--json` output never contains an absolute path to either file, only
  which source category matched (`repo` / `claude-user` / `codex-user`). Set
  `DEVFLOW_MCP_CONFIG_PATHS` (an `os.pathsep`-separated list of JSON config files) to replace
  this default search entirely.

## Run

```bash
python3 "$CLAUDE_PLUGIN_ROOT/scripts/devflow.py" doctor
```

For structured output (e.g. to compare against a prior run, or to hand to another tool):

```bash
python3 "$CLAUDE_PLUGIN_ROOT/scripts/devflow.py" doctor --json
```

## Interpreting Results

- **Exit 0 / `HEALTHY`** — no finding above `info` severity. Report healthy; still surface any
  `info`-level findings present.
- **Exit 1 / `FINDINGS`** — at least one `error` or `warning` finding. List every finding with
  its severity, id, message, and path (when present) — never summarize away a specific finding.
- **Degraded capability** — reported inside `capabilities` (`status: "degraded"`), independent
  of `healthy`. Name the capability, its missing dependency, and which command/skill it gates
  (e.g. a missing browser MCP degrades `browser-qa` only, not `check` or `review`).
- **Exit 2** — usage or internal error (bad `--plugin-root`, not a git checkout, etc.). Report
  this as a blocked run, not as a clean result.

The `doctor --json` output contract (`devflow-doctor-v1`) is documented in
`scripts/devflow.py`'s own module docstring.

## Related Workflows

- `/rhize-devflow:check` — mid-implementation evidence-driven validation for a repository under
  development (not this plugin's own health).
- `/rhize-devflow:review` — production merge/release gate.
- `rhize-context-manager:context-doctor` — session/context-layer health; a different surface
  from this command's plugin-install health.
