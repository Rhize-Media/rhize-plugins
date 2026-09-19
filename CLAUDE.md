# Rhize Plugins

Marketplace of 10 plugins: rhize-core, seo-aeo-geo, obsidian-second-brain, project-launcher,
rhize-devflow, rhize-ops, rhize-context-manager, rhize-tasks, rhize-cowork, procedural-memory. Registry:
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

Full skill inventory (covers all 10 plugins, not a hand list): `generated/SKILL-CATALOG.md`.
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
- `claude plugin eval` became available here in September 2026. Keep native routing/procedure evals separate from controlled task-benefit benchmarks; see `procedural-memory/evals/README.md`.
- Executors/agent sessions never `git push` — the orchestrator does.

## Required operational checks

- Respect the active `protect-files` policy for `.github/workflows/*`, including
  `version-check.yml` and `tag-release.yml`; inspect the current instructions before editing.
- Before source changes, persist the intended semantic delta, invariants and acceptance tests
  in an impact map. Reconcile the actual changed paths before the final release gate.
- Read a file before its first edit; re-read after a replacement fails to match.
- Use subprocess deadlines when the host lacks `timeout`. Use `/usr/bin/find` for compound
  filesystem predicates and `/usr/bin/grep` for exit-code conditionals affected by RTK.
- Process large `.jsonl` evidence with bounded Python/jq reads instead of loading it wholesale.
  Skill-map validators support a standard-library fallback when `jsonschema` is unavailable.
- `pytest.ini` declares `testpaths = tests evals`. Run the relevant tests plus required release
  checks; select the actual Node binary for fixtures that replace HOME so mise does not resolve
  a different installation. Regenerate managed documentation after version bumps.
