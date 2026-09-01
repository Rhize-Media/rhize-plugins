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

### Why (measured, 2026-07-28)

Four skills were ingested here from `everything-claude-code` — `strategic-compact`,
`context-budget`, `iterative-retrieval`, `token-budget-advisor`. With `ecc@everything-claude-code`
enabled, all four were duplicates competing for the same invocations. On inspection:

- Three differed from upstream **only in frontmatter indentation** — zero Rhize value.
- `strategic-compact` had **drifted behind**: ecc 2.0.0 had gained a context-size primary
  signal with window-scaled thresholds (160k on a 200k window, 250k on 1M) and
  `COMPACT_CONTEXT_THRESHOLD`/`INTERVAL`. The fork still carried the old tool-count-only
  logic. **The copy was strictly worse than the thing it copied**, and nobody noticed,
  because a fork's staleness is invisible until someone diffs it.

All four were retired (entries kept and annotated in `SOURCES.md`). The duplication cost
was pure: maintenance surface, skill-listing bloat, ambiguous invocation, and a silently
degraded skill.

**The same failure at the plugin layer:** both `everything-claude-code@everything-claude-code`
(1.8.0) and `ecc@everything-claude-code` (2.0.0) were enabled simultaneously, so every
overlapping ECC hook — `governance-capture`, `quality-gate`, `mcp-health-check`,
`doc-file-warning`, `pre-compact`, `post-edit-console-warn` — fired **twice on every
matching tool call**. Enabling two versions of one plugin is the plugin-level form of
duplicating a skill. Check for it whenever adding to `enabledPlugins`.

*This rule is a candidate for `@rhize/skill-forge` enforcement: the ingest gate should
refuse, or require an explicit override, when a candidate skill's name or capability
already exists in an enabled plugin.*

**Update (2026-08-10):** this enforcement has shipped. `skill-forge add`/`scan --skill-map
<path>` ranks a candidate against every skill in this repo's compiled skill map
(`generated/skill-map.static.json`) and escalates a near-duplicate to a blocking safety
finding instead of a silent promote — see `docs/skill-map.md` and skill-forge's own
CLAUDE.md for the mechanics. A deliberate specialization declares
`metadata.rhize.extends` in its SKILL.md frontmatter to get an exemption from that
specific match, rather than being blocked outright — so this rule's "author a genuinely
additive skill next to it" escape hatch is now machine-checked, not just written down.

See the `learning-curation` skill in `rhize-context-manager` for the general procedure.

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
4. If the change is user-visible, add a `CHANGELOG.md` entry.

A skill/command/plugin change that ships without its README and GUIDE updated is incomplete — treat undocumented capability the same as an untested one.

## Headroom Learned Patterns
*Auto-generated by `headroom learn` (consolidated; one section per sub-heading, newest entry wins) — do not edit manually*

*Five auto-generated sections (2026-06-16 → 2026-07-27) deduped into one on 2026-08-03.
New `headroom learn` output now flows into the refinement queue
(`/rhize-context-manager:learn-harvest`), not this file — the scheduled routine is barred
from editing CLAUDE.md. Exception, 2026-08-12: Jim directed nine queue entries carrying
repo-environment facts (no legal skill target) to be folded in here by hand; they were
deduped to the five facts below and marked `consumed`. Exception, 2026-08-14: a
human-invoked `/skill-refine review` folded in three more such facts (python3-vs-python,
the large-`.jsonl` Read limit, and SOURCES.md normalization) and marked them `consumed`.
The bar on the unattended routine is unchanged.*

### Fact-Forcing Gate (ECC GateGuard)
- Prefix the FIRST Bash command of each user request/chapter with an inline FACTS echo:
  `echo "FACTS: (1) <request in one sentence>; (2) <what this command verifies/produces>" && …`.
  The gate re-arms after every `mark_chapter` call. Bypass for pure repair/setup: `ECC_GATEGUARD=off`.
- Before any Edit/Write: state the files that import/require the target (Grep first if
  unknown) and the exact lines being changed and why. For a NEW file, name the caller(s)
  — or state explicitly "new entry point — no existing caller."
- Failing the gate wastes a full round-trip; satisfy it proactively.

### Repository layout & key paths
- rhize-plugins root: `/Users/jamesdeola/dev-local/RHIZE/rhize-plugins`; registry at
  `.claude-plugin/marketplace.json`; plugins: `seo-aeo-geo/`, `obsidian-second-brain/`,
  `project-launcher/`, `rhize-devflow/`, `rhize-ops/`, `rhize-context-manager/`.
- skill-forge CLI repo: `/Users/jamesdeola/dev-local/RHIZE/skill-forge` (read its CLAUDE.md
  before working there). Build `npm run build` (tsup); tests `npx vitest run`; pack check
  `npm pack --dry-run`.
- `skill-monitor` lives at `rhize-ops/skill-monitor/monitor.py` (standalone repo retired:
  GitHub-archived, local dir deleted; scheduled task repointed). Data paths are `__file__`-relative.
- Version bumps: `python3 scripts/bump_version.py --plugin <name> --level minor|patch|major`
  — updates plugin.json + marketplace.json + CHANGELOG atomically; never hand-edit JSON alone.
- Subagent tasks sometimes arrive with `REPO: undefined` (template bug) — the answer is
  `/Users/jamesdeola/dev-local/RHIZE/skill-forge`; spend at most one Bash call on discovery.
- Scratchpad worktree: set `SCRATCH=<path>` once per session and reuse; never re-expand the
  full `/private/tmp/claude-501/...` path per command.
- External upstream references are tracked centrally in
  `rhize-context-manager/skills/SOURCES.md` and normalized by `scripts/sources_md.py` to
  canonical remote raw URLs — add a source there rather than inline in a SKILL.md.
- The installed plugin cache `~/.claude/plugins/marketplaces/rhize-plugins` is a git clone that
  pins BEHIND this repo. When it goes stale, `rhize-context-manager:*` skills report
  "Unknown skill" and **scheduled tasks fail silently**. Refresh with
  `claude plugin marketplace update rhize-plugins` then `claude plugin update`. (Diagnosed
  2026-08-05; `ai-stack-version-drift` now auto-updates marketplaces + plugins twice weekly.)

### Git workflow
- Stale `.git/index.lock` mid-session: `rm -f .git/index.lock` (verify no live git process
  via `ps` first), then retry.
- `git status --short` once at session start; track your own changes after that.
- Commit conventions: `feat(...)`/`fix(...)`/`docs(...)`/`refactor(...)`; multi-line `-F -`
  heredoc messages for non-trivial changes.
- `.github/workflows/ci.yml` and `release.yml` are PROTECTED (protect-files.sh hook) — do
  not Edit; leave a note for Jim instead.
- Before removing a scratch worktree, check it still exists.
- `.gitignore` here uses an **ALLOWLIST** for `scripts/` — a newly created `scripts/*.py` is
  invisible to `git status` until you add a `!scripts/<name>.py` exception. When a file you
  just wrote doesn't show up, run `git check-ignore -v <path>` before assuming the write failed.

### Edit/Read discipline
- Read a file before its first Edit in a session (`File has not been read yet` otherwise);
  on `String to replace not found`, re-Read before retrying.
- Large frequently-re-read files (e.g. skill-forge `test/e2e.test.ts`, big SKILL.md files):
  read ONCE, note key facts, refer to notes — some were re-read 6–13× per session.
- Hot files measured since that list was written — read ONCE, then `grep -n` for edit sites:
  - skill-map pipeline: `scripts/build_skill_map.py` (~25–30KB, hit 16× in one session),
    `scripts/build_local_skill_map.py` (~28KB), `scripts/validate_skill_map.py`,
    `docs/skill-map.md` (~13–21KB), `catalog/{tags,skill-relations,queries}.json`,
    `rhize-ops/skill-monitor/monitor.py` (~48–55KB).
  - skill-forge: `src/commands/gatePipeline.ts`, `src/gate/{skillMapDrift,skillMap,mapOverlap}.ts`,
    `test/{agents,skillMapDrift}.test.ts`. There is no root `CHANGELOG.md` — version history
    lives in `README.md` + `docs/BUILD-REPORT.md`.

### Environment quirks
- rtk `find` shim lacks `-not`/`-exec`/compound predicates — use `/usr/bin/find` or `\find`.
- Always invoke `python3`, never bare `python` — `python` is not on PATH and exits 127
  (`command not found`), which reads like a script error but is not.
- Never `Read` a large `.jsonl` (observer/analysis logs, session transcripts) directly —
  they exceed the 256KB / 25,000-token tool limit and the call fails outright. Process them
  in Bash with `python3` or `jq` in a single pass and emit only what you need.
- System `python3` (3.14) has **no `jsonschema`** — `import jsonschema` fails every time and
  burned a round-trip in 5+ sessions. The skill-map validators are written to run without it,
  so just run `scripts/validate_skill_map.py` / `tests/skill-map/validate_fixtures.py` — do not
  probe the import first. `yaml` (PyYAML 6.0.3) IS available. If genuinely needed:
  `python3 -m pip install --quiet --user jsonschema`.
- vitest: output is captured by rtk tee; read the newest file in
  `~/Library/Application Support/rtk/tee/` instead of re-running. `--reporter=basic` is
  invalid (use `--reporter=verbose` or omit).
- `npx tsc --noEmit` in skill-forge shows pre-existing `@types/node` errors — `npm run build`
  is the authoritative check; confirm errors are pre-existing via `git stash` before reverting.
- Browser MCP screenshots: max 2 attempts per state; verify tab/load state instead of looping.
- Sanity `query_documents`: run `get_schema` first; never retry an identical GROQ query more
  than twice — cache results in the scratchpad.

### Screenshot / Browser loops
*~27,373 tokens/session saved*
- **Browser screenshot loops**: taking repeated screenshots waiting for a page state wastes tokens. Before looping, check whether the page has finished loading (network idle) with a single screenshot + explicit wait, then proceed. Do not take more than 2 screenshots for the same state check.

### skill-forge repo
*~800 tokens/session saved*
- **Edit tool requires prior Read** — always `Read` a file before attempting `Edit` or `Write` (overwrite). Skipping this causes `File has not been read yet` errors and wastes a round-trip.
- **skill-forge repo path**: `/Users/jamesdeola/dev-local/RHIZE/skill-forge` (npm CLI `@rhize/skill-forge`). When tasks pass the repo path as `'undefined'`, search here first. Run tests with `npm test` (alias for `npx vitest run`). Build with `npm run build` (tsup). Type-check with `npm run build` — do NOT use `npx tsc --noEmit` directly (pre-existing `node:fs` type errors exist in the environment; not caused by local changes). `ECC_GATEGUARD=off` prefix suppresses the ECC gate hook during local builds when needed. *(ported 2026-08-26 — dropped by newest-wins title collision on "skill-forge repo")*
- **Key large/frequently-read files** (read once per session, cache mentally): `src/agents.ts` — 73-entry agent matrix (~15K bytes); `src/gate/profile.ts` — MCP + skill profiler (~14-18K bytes); `src/gate/mcpSafety.ts` — MCP safety ruleset (~12K bytes); `test/e2e.test.ts` — E2E test suite (~10-20K bytes, grows each version); `README.md` — updated every version bump (~8-12K bytes). *(ported 2026-08-26 — dropped by newest-wins title collision on "skill-forge repo")*

### rhize-plugins repo
*~7,456 tokens/session saved*
- **rhize-plugins repo**: `/Users/jamesdeola/dev-local/RHIZE/rhize-plugins`. Plugin layout: each plugin dir has `.claude-plugin/plugin.json`, `README.md`, `GUIDE.md`, `skills/*/SKILL.md`, `commands/*.md`, `hooks/hooks.json`.
- **`seo-aeo-geo` has no `GUIDE.md`** at top level — do not attempt to read it.
- Version bumping script: `python3 scripts/bump_version.py --plugin <name> --level minor`.
- **Frequently re-read stable files** — read these once per session and do not re-read unless editing: `rhize-ops/skills/delegate-to-teammate/SKILL.md` (~17-18K bytes); `rhize-devflow/GUIDE.md` (~28K bytes when fully written); `.claude-plugin/marketplace.json` — always validate JSON after edits with `python3 -m json.tool <file>`. *(ported 2026-08-26 — dropped by newest-wins title collision on "rhize-plugins repo")*

### Scratchpad pattern
*~8,000 tokens/session saved*
- **Scratchpad path**: subagents write to `/private/tmp/claude-501/-Users-jamesdeola-dev-local-RHIZE-rhize-plugins/<session-id>/scratchpad/`. Read the latest scratchpad file with `cat "$(ls -t /private/tmp/claude-501/.../scratchpad/ | head -1)"` rather than re-reading it by name multiple times.

### Sanity / MCP queries
*~5,817 tokens/session saved*
- **Sanity MCP repeated queries**: `query_documents` and `get_schema` calls on `projectId: '3g5yoen6', dataset: 'production'` are expensive. Cache the result in a scratchpad file and read it instead of re-querying.

### Commands
*~500 tokens/session saved*
- **`timeout` is not available on this macOS** — do not use `timeout <N> <cmd>` in bash scripts; it will fail with `command not found`. Use background processes with `sleep` + `kill` if a timeout is needed.
- **Vitest output is truncated** when run via `npx vitest run 2>&1 | tail -N` — full output goes to `~/Library/Application Support/rtk/tee/<timestamp>_vitest_run.log`. If output is empty/truncated, read the latest tee log: `tail -150 "$HOME/Library/Application Support/rtk/tee/$(ls -t ~/Library/Application\ Support/rtk/tee/ | head -1)"`. Do NOT use `--reporter=basic` (unsupported); use default or `--reporter=verbose`. *(ported 2026-08-26 — dropped by newest-wins title collision on "Commands"; the sibling `find -not/-exec` tip from the same collision is already preserved verbatim under "Shell / Bash Commands" below, no porting needed there)*

### Scratchpad / Temp Directory Loops
*~235,000 tokens/session saved*
- **Reading `/private/tmp/claude-501/-Users-jamesdeola-.../scratchpad/`** repeated 5x in one session (~227k tokens wasted). Write the scratchpad once with all needed content; do not re-read it to verify — trust what you wrote or use a checksum.
- **`SCRATCH=...` bash setup blocks** are run 40–46x per session to re-establish the scratch environment. Set SCRATCH once in a variable and reuse it; do not re-source the block.

### Critical File Re-fetch Loops — Guardrails
*~48,000 tokens/session saved*
- **`procedural-memory/STATE.md`** is re-read up to 31x per session (~14k tokens wasted). Read it once at session start; do not re-read in a loop — make targeted `grep`/`sed` queries for specific sections instead.
- **`Documents/Claude/Scheduled/vault-inbox-processor/SKILL.md`** is re-read up to 13x per session (~22k tokens wasted). Read once and keep in working memory.
- **`rhize-tasks/tests/connectors/reminders-process.test.mjs`** is re-read up to 12x per session (~12k tokens wasted). Read once before editing.
- **`src/rhize_skill/runner.py`** is re-read up to 38x per session (~45k tokens wasted); **`rhize-tasks/installer/install.mjs`** re-read up to 33x (~44k tokens wasted); **`scripts/build_skill_map.py`** re-read up to 44x AND edited up to 60x (~38k tokens wasted). Read each once; batch edits. *(ported 2026-08-26 — dropped by newest-wins title collision on "Critical File Re-fetch Loops — Guardrails"; largely overlaps "Key Large/Hot Files" below but preserves the specific re-read/edit counts and token-waste figures that entry omits)*

### Test Execution — Avoid Re-run Loops
*~45,487 tokens/session saved*
- **`cd /Users/jamesdeola/dev-local/RHIZE/procedural-memory && .venv/bin/python -m pytest -q 2>&1 | tail ...`** is run up to 51x per session (~10k tokens wasted). Run the full suite once after a batch of edits, not after every single change.
- **`node --test tests/connectors/reminders-process.test.mjs 2>&1 | tail -20`** is run up to 13x per session (~8.6k tokens wasted). Batch fixes before re-running.
- **`node --test tests/e2e/lifecycle-fix-round-1.test.mjs 2>&1 | tail -20`** repeated 11x (~10k tokens wasted). Run test suites after completing a logical change group, not incrementally.

### Python Environment
*~45,487 tokens/session saved*
- Always use `.venv/bin/python` (not `python3`) in `/Users/jamesdeola/dev-local/RHIZE/procedural-memory`. The system `python3` does not have project dependencies (`psycopg`, `click`, `jsonschema`) installed.
- Use `PYTHONDONTWRITEBYTECODE=1` when running scripts in `registry/skills/*/scripts/` to avoid `__pycache__` noise in fixture directories.

### Key Large/Hot Files
*~44,345 tokens/session saved*
- `src/rhize_skill/runner.py` — frequently large (24k–40k tokens). Use targeted `grep`/`sed -n` for specific sections rather than full reads.
- `src/rhize_skill/assertions.py` — ~23k tokens. Read once per session.
- `rhize-tasks/installer/install.mjs` — read 33x in one session; read once and batch all edits.
- `scripts/build_skill_map.py` — edited 60x in one session; plan all changes before starting edits.

### PostgreSQL
*~14,402 tokens/session saved*
- When restarting PostgreSQL@18 on this machine, always set `LC_ALL=C` (or `LC_ALL=en_US.UTF-8`): `LC_ALL=C pg_ctl -D /opt/homebrew/var/postgresql@18 start`. Without it, the server fails to start due to Homebrew/macOS locale detection issues.
- Postgres data directory: `/opt/homebrew/var/postgresql@18`. DSN: `postgresql://jamesdeola@localhost:5432/procedural_memory`.

### Edit Tool — Read Before Write
*~4,000 tokens/session saved*
- The Edit/Write tools require the file to be Read first in the same session. Attempting to edit without reading first produces `<tool_use_error>File has not been read yet`. Always Read before Edit, especially for files not touched earlier in the session.

### rhize-skill CLI
*~3,000 tokens/session saved*
- `rhize-skill promote` requires an absolute path: use `"$(pwd)/registry/skills/..."` not a relative path. Relative paths cause `'path' is not in the subpath of '...registry'` errors.
- `rhize-skill run` does not accept `--vault-root` as a direct option; pass arguments after `--` separator.

### Shell / Bash Commands
*~2,500 tokens/session saved*
- The `rtk find` wrapper does NOT support `-not`, `-exec`, or compound predicates. Always use `/usr/bin/find` directly for complex find operations.
- `cat` on macOS does not support `-A` flag; use `cat -v` or `cat -e` instead.
