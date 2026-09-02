# CodeGraph setup

CodeGraph is a separate CLI (`@colbymchenry/codegraph` on npm, installed as the `codegraph`
binary) that pre-indexes a repository's code graph — symbols, callers, call paths, including
dynamic-dispatch hops a text search can't follow — into a local `.codegraph/` directory for
fast structural lookups. It is an **optional CLI dependency** of this plugin (declared in
`setup/manifest.json` with `"kind": "cli"`, `"binary": "codegraph"`, capability
`codegraph-index`): every consumer below documents an explicit `rg`-based fallback, so its
absence never blocks a command — it only loses structural precision.

## Install and initialize (per client repo)

```bash
npm install -g @colbymchenry/codegraph   # once per machine
codegraph init -y                        # once per repo clone — builds the initial index
codegraph status                         # before trusting the index — confirms it's present and healthy
codegraph sync                           # after source changes, when status reports pending/stale
```

`codegraph init -y` is non-interactive (skips prompts, takes defaults — suitable for scripts
and CI). Re-running `init` is unnecessary after the first run; use `sync` to catch up an
existing index instead.

## What `.codegraph/` is

`.codegraph/` holds a local SQLite database (roughly 30 MB for a mid-size repository) plus a
`.gitignore`. The database is **regenerable local state, not a repository artifact** — it must
never be committed. Only the directory's own `.gitignore` (already tracked wherever CodeGraph
is adopted) should ever be checked in. If a `.codegraph/` database ends up staged, remove it
from the index rather than committing it; re-running `codegraph init -y` rebuilds it from
scratch at any time.

## Fallback behavior when absent or stale

Every rhize-devflow consumer treats CodeGraph as optional and falls back to `rg`-based text
search when the CLI is missing, the index is absent, or `codegraph status` reports it stale:

- **`/rhize-devflow:impact-map`** queries CodeGraph first for structural discovery and falls
  back to `rg` with no index creation of its own.
- **`scripts/devflow.py evidence`** records CodeGraph index presence and freshness in its
  output packet (`codegraph.exists`, `codegraph.stale`, ...) but never creates or initializes
  an index itself — see `schemas/devflow-evidence-v1.schema.json`.
- **`scripts/refactor_gate.py prepare`/`reconcile`** run an existing healthy index when present
  and record the `rg` fallback in the receipt otherwise; a missing or stale index is never
  treated as an error.
- **`scripts/devflow.py doctor`** reports the `codegraph-index` capability as `ok` or
  `degraded` (never as a blocking finding) based on whether the `codegraph` binary is on
  `PATH` — see the [capability-scoped dependencies table](../README.md#capability-scoped-dependencies-setupmanifestjson)
  in the main README.

None of these commands install, initialize, or sync CodeGraph on your behalf — that stays a
deliberate, explicit step per the instructions above.
