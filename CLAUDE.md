# Rhize Plugins

## Curation Rule — close gaps, never duplicate (IMPORTANT)

**A Rhize skill exists to close a gap a proven plugin leaves open. It must never re-ship
a skill that an enabled upstream plugin already provides.**

Before adding or ingesting any skill into this marketplace:

1. **Check whether an enabled plugin already ships it** — by name and by capability. If it
   does, the correct outcome is *no new skill*. Write down the gap instead, and either
   contribute upstream or author a genuinely additive skill next to it.
2. **If you must fork, record why the fork is load-bearing** in `SOURCES.md`, and define a
   real `Drift check`. A fork with no stated reason is a duplicate with extra steps.
3. **Prefer depending on upstream over vendoring it.** A plugin that orchestrates proven
   tools stays small and stops drifting; one that copies them inherits their whole
   maintenance surface and gains nothing.

Measured 2026-07-28: four skills forked from `everything-claude-code` were pure duplicates
(one had drifted strictly worse than the upstream it copied), and two versions of the same
ECC plugin were enabled at once, double-firing every overlapping hook. Enforcement shipped
2026-08-10 in `@rhize/skill-forge` (`add`/`scan --skill-map`): a near-duplicate candidate is
escalated to a blocking safety finding unless it declares `metadata.rhize.extends`. Full
narrative: `docs/session-guardrails.md`.

See the `learning-curation` skill in `rhize-context-manager` for the general procedure.

### Cross-plugin sharing rule

Plugins are islands. Shared code (e.g. `scripts/mcp-secret-launcher.sh`) is duplicated
deliberately, byte-identical, across plugins — document the shared copy where it is owned
(`docs/mcp-secret-launcher.md` for the launcher shim), and it is covered by the drift test
`tests/config-lint/test_shared_shims.py`. A plugin may import
another plugin's file only by a discovered path (never a hardcoded cross-plugin path), and
only with a documented degraded mode for when that file is absent.

## Skill Usage (IMPORTANT)

This project contains Claude Code skills (plugins). When a user's request matches an available skill's description, you MUST invoke it using the Skill tool rather than handling the request with general knowledge and native tools.

**Rules:**
- Check the available skills list before responding to any user request
- If a skill's trigger description matches the user's intent, invoke it with the Skill tool immediately
- Do NOT attempt to replicate skill functionality using WebFetch, Bash, or other tools when a matching skill exists
- Skills contain specialized workflows, API integrations, and output formats that general-purpose tool use cannot replicate

**Available skill categories:**

*SEO/AEO/GEO plugin:*
- SEO auditing and analysis (`seo-site-audit`)
- Keyword research and intelligence (`keyword-intelligence`)
- Backlink analysis (`backlink-intelligence`)
- SERP checking and monitoring (`serp-intelligence`)
- Content SEO optimization (`content-seo`)
- AI/Answer Engine Optimization (`aeo-geo-optimization`)
- Next.js + Sanity SEO review (`nextjs-sanity-seo`)

*Obsidian Skills plugin:*
- Obsidian CLI operations (`obsidian-cli`)
- Obsidian markdown syntax (`obsidian-markdown`)
- Obsidian Bases database views (`obsidian-bases`)
- JSON Canvas visual boards (`json-canvas`)
- Web clipping with Defuddle (`defuddle`)
- Second brain / PKM methodology (`second-brain`)
- Vault note templates (`vault-templates`)
- Vault health and alignment (`vault-alignment`)

*Project Launcher plugin:*
- Full project launch pipeline — research, PRD, gap analysis, scaffold, GSD v2 handoff (`project-launcher`)
- Commands: `/launch-project`, `/write-prd`, `/scaffold-gsd`, `/grill-prd`

## CodeGraph Repository Index (IMPORTANT)

This repository is intentionally CodeGraph-indexed. Use CodeGraph before `rg` or broad manual
reads when locating supported source symbols, callers, callees, or affected tests:

```bash
codegraph status
codegraph sync                 # only when status reports pending/stale source
codegraph explore "<question>"
codegraph affected <files...>
```

The SQLite database under `.codegraph/` is local, regenerable state and must never be committed;
the tracked `.codegraph/.gitignore` is the only repository artifact. On a fresh clone, install the
documented CodeGraph CLI and run `codegraph init -y` once. If status is unhealthy or the relevant
edge is Markdown, JSON, generated, dynamic, or external, record that limitation and use `rg` plus
targeted reads. Do not initialize other repositories without their owner's explicit decision, and
do not run Serena for the same code-navigation question while CodeGraph is active here.

## Documentation Maintenance (IMPORTANT)

This repo follows a strict README-vs-GUIDE.md convention, defined in full in the root [README.md](./README.md#documentation-hierarchy):

- **`README.md`** (root and per-plugin) = technical reference: install/setup, env vars, the full skill/command inventory, architecture, hooks.
- **`GUIDE.md`** (per-plugin) = user-facing walkthrough: what problem it solves, when to reach for which skill/command, example prompts, tips, troubleshooting.

**Whenever you add, remove, or materially change a skill, command, hook, MCP connector, or plugin, update the docs in the same change — do not leave it for a follow-up:**

1. Update the plugin's own `README.md` (skill/command tables, architecture tree, setup steps) to match reality.
2. Update the plugin's `GUIDE.md` (or create one if the plugin doesn't have one yet) so the new/changed capability is discoverable in plain language, with an example prompt.
3. If you added or removed a whole plugin, update the root `README.md`'s Plugin Catalog table and `.claude-plugin/marketplace.json`, keeping the plugin's `version` in sync between its own `plugin.json` and the marketplace entry.
4. If the change is user-visible, add an entry to the plugin's own `CHANGELOG.md`; marketplace-level changes (version bumps, cross-plugin programs) go in the root `CHANGELOG.md`. Full dated history lives in `docs/release/CHANGELOG-history.md`.
5. If the change affects what a first-time reader needs to know — a new plugin, a changed
   install/setup step, a new cross-plugin mechanism — update `START-HERE.md` and/or
   `docs/README.md` in the same change. `docs/README.md`'s managed section (between the
   `SKILL-MAP` markers) is rendered by `scripts/render_skill_map_docs.py` from
   `marketplace.json` and the skill map — never hand-edit it; the render runs after
   `scripts/bump_version.py`, as part of the same release flow that refreshes the root
   README's Plugin Catalog table and `generated/SKILL-CATALOG.md`.

A skill/command/plugin change that ships without its README and GUIDE updated is incomplete — treat undocumented capability the same as an untested one.

**A plugin's `description` is canonical in its own `.claude-plugin/plugin.json`.** The copy in
`.claude-plugin/marketplace.json`'s entry for that plugin, and the copy in
`.codex-plugin/plugin.json` where the plugin ships one, must be identical to it, character for
character — `tests/config-lint/test_description_parity.py` enforces this. Changing a plugin's
description means updating every copy in the same change, not just the one you happened to open.

**Progressive disclosure is required, not optional** (see [Progressive disclosure](./README.md#progressive-disclosure)). Every doc is a front door, not a warehouse: lead with what it is and how to start, then link to depth instead of inlining it. Deep mechanics (schemas, gate internals, per-command option matrices, rationale) live in a `docs/` or `references/` file linked at the point of need. **A README or reference doc past roughly 400–500 lines is a split candidate**; move content to the document that owns it and link from where the reader was — never delete, and never leave an overview that can't stand alone.

## Environment and workflow rules

- Prefix the first Bash command of each user request/chapter with an inline FACTS echo
  (`echo "FACTS: (1) <request>; (2) <what this verifies/produces>" && …`); before any
  Edit/Write, state the caller(s) of the target or "new entry point — no existing caller."
- Version bumps only via `python3 scripts/bump_version.py --plugin <name> --level
  minor|patch|major` — never hand-edit `plugin.json`/`marketplace.json`/CHANGELOG alone.
- `.github/workflows/*` (`version-check.yml`, `tag-release.yml`, `validate.yml`) may be edited
  directly — Jim lifted the `protect-files` CI gate on 2026-09-04; `.github/ci-proposed/` remains
  available for drafting a workflow change you want reviewed before it goes live. Every push to
  main runs `validate.yml`; keep it green.
- The refactor gate (`rhize-devflow/scripts/refactor_gate.py`) requires a plan containing
  five substrings — `current behavior`, `intended semantic delta`, `invariants`,
  `acceptance tests`, `implementation order` — reconciles changed paths by full path or
  basename, and its Stop hook closes a `reconciled` receipt as `completed`; one receipt is
  shared per workspace path across concurrent sessions, so use a worktree when another
  session is active there.
- Git: feature branches; `-F -` heredoc commit messages for non-trivial changes; a stale
  `.git/index.lock` is `rm -f` after confirming no live git process.
- Always invoke `python3`, never bare `python` (not on PATH, exits 127).
- `timeout` is unavailable on this macOS — use a background `sleep`+`kill` pair instead.
- rtk's `find`/`grep` shims break compound predicates and exit-code conditionals — use
  `/usr/bin/find` for compound finds, and `/usr/bin/grep` inside `until`/`while`/`if`.
- Read a file before its first Edit in a session, or Edit fails with `File has not been
  read yet`; on `String to replace not found`, re-Read before retrying.
- Never `Read` a large `.jsonl` directly — it exceeds the 256KB/25,000-token tool limit;
  process it with `python3`/`jq` in Bash instead.
- System `python3` has no `jsonschema` (`yaml` is available) — the skill-map validators
  run without it, so don't probe the import first.
- vitest output is captured by the rtk tee — read the newest file under
  `~/Library/Application Support/rtk/tee/`; never pass `--reporter=basic`.
- `npm run build` is the authoritative skill-forge type check, not `npx tsc --noEmit`
  (pre-existing `@types/node`/`node:fs` errors there are environmental).
- Git fixtures that build repos need `-c core.excludesFile=/dev/null` — the machine's
  global excludes file hides fixture content and `GIT_CONFIG_GLOBAL` does not override it.
- `claude plugin eval` is org-gated on this machine — build static validators instead.
- `procedural-memory` always uses `.venv/bin/python`/`.venv/bin/pytest`, never bare `python3`.
- The installed plugin cache (`~/.claude/plugins/marketplaces/rhize-plugins`) can pin
  behind this repo — refresh with `claude plugin marketplace update rhize-plugins` then
  `claude plugin update`.
- Tests live under `tests/<plugin>/`, never a plugin-local `tests/` dir; `pytest.ini` sets
  `testpaths = tests evals`.
- Never `git push` from an executor/agent session — the orchestrator handles pushes.
- The scratchpad path resolves per session
  (`/private/tmp/claude-501/.../<session-id>/scratchpad/`) — resolve it once and reuse.

## Repository layout & key paths

- rhize-plugins root: `/Users/jamesdeola/dev-local/RHIZE/rhize-plugins`; marketplace
  registry at `.claude-plugin/marketplace.json`.
- Plugins: `seo-aeo-geo/`, `obsidian-second-brain/`, `project-launcher/`, `rhize-devflow/`,
  `rhize-ops/`, `rhize-context-manager/`, `rhize-tasks/`, `rhize-cowork/`,
  `procedural-memory/`.
- skill-forge CLI repo: `/Users/jamesdeola/dev-local/RHIZE/skill-forge` (read its own
  CLAUDE.md before working there).
- `skill-monitor` is a standalone repo, `Rhize-Media/rhize-skill-monitor`, cloned locally at
  `~/dev-local/RHIZE/rhize-skill-monitor` by default (override with `RHIZE_SKILL_MONITOR_ROOT`);
  `rhize-ops/scripts/skill_monitor_root.sh` resolves it for the `skill-dashboard` skill.
- External upstream references live in `rhize-context-manager/skills/SOURCES.md`,
  normalized by `scripts/sources_md.py`.
- Start at `START-HERE.md` for orientation on a fresh clone.

Session-level loop guardrails (hot files, re-read counts, token figures) live in
`docs/session-guardrails.md` — read it when a session is looping on re-reads or re-runs.

## Governance utility integration (2026-09-05)

`rhize-ops/scripts/host_inventory.py` exports static Codex user config/cache evidence
using Python 3.11 stdlib TOML; ambiguous versions/project trust remain unknown. Skill
Forge 0.19 imports this inventory and manages explicit host/project keep rationale.
Plugin-prune must never join Claude snapshots or call Claude disable for Codex rows.
`/skill-refine capture` uses explicit project activation and hash/backup read-back;
queue consumption still requires actual host invocation and original-scenario evidence.
Caches are never write targets. See both plugins' guides and command documentation.
