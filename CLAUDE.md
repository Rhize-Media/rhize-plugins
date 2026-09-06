# Rhize Plugins

Marketplace of 9 plugins: seo-aeo-geo, obsidian-second-brain, project-launcher, rhize-devflow,
rhize-ops, rhize-context-manager, rhize-tasks, rhize-cowork, procedural-memory. Registry:
`.claude-plugin/marketplace.json`. Start at `START-HERE.md`. Repo is CodeGraph-indexed
(`.codegraph/`) — see global CLAUDE.md for usage.

## Curation

A Rhize skill closes a gap an upstream plugin leaves open; it never re-ships one already
provided. A fork must declare `metadata.rhize.extends` in the plugin's `skills/SOURCES.md`, or
skill-forge (`/Users/jamesdeola/dev-local/RHIZE/skill-forge`) escalates it to a blocking finding.
Procedure: `rhize-context-manager:learning-curation` skill. Why: `docs/session-guardrails.md`.

Plugins are islands: shared code (e.g. `scripts/mcp-secret-launcher.sh`) is duplicated
byte-identical across plugins rather than imported cross-plugin, and drift-tested by
`tests/config-lint/test_shared_shims.py`. See `docs/mcp-secret-launcher.md`.

Full skill inventory (covers all 9 plugins, not a hand list): `generated/SKILL-CATALOG.md`.
Rebuild with `python3 scripts/build_skill_map.py`; ask it questions with
`python3 scripts/query_skill_map.py <query> <arg>` (see `docs/skill-map/query-layer.md` for the
query catalog).

## Docs and releases

- A skill/command/plugin change ships with its plugin's `README.md` + `GUIDE.md` update and a
  `CHANGELOG.md` entry in the same commit — see root `README.md#documentation-hierarchy`.
- A plugin's `description` is canonical in its own `plugin.json`; the `marketplace.json` and
  `.codex-plugin/plugin.json` copies must match it character-for-character
  (`tests/config-lint/test_description_parity.py`).
- Version bumps only via `python3 scripts/bump_version.py --plugin <name> --level
  minor|patch|major` — never hand-edit `plugin.json`/`marketplace.json`/CHANGELOG.
- `docs/README.md`'s SKILL-MAP block is rendered by `scripts/render_skill_map_docs.py`; never
  hand-edit it.

## Gotchas

- Tests live under `tests/<plugin>/`, never a plugin-local `tests/` dir; `procedural-memory`
  uses `.venv/bin/python`/`.venv/bin/pytest`, not bare `python3`.
- skill-forge's authoritative type check is `npm run build`, not `npx tsc --noEmit` (that repo
  has pre-existing environmental `@types/node`/`node:fs` errors).
- vitest output is teed to `~/Library/Application Support/rtk/tee/` — read the newest file there,
  never pass `--reporter=basic`. Git fixture repos need `-c core.excludesFile=/dev/null`.
- `claude plugin eval` is org-gated on this machine — build static validators instead.
- Executors/agent sessions never `git push` — the orchestrator does.
