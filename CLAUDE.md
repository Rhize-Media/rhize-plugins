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

## Headroom Learned Patterns (consolidated)
*Five auto-generated sections (2026-06-16 → 2026-07-27) deduped into one on 2026-08-03.
New `headroom learn` output now flows into the refinement queue
(`/rhize-context-manager:learn-harvest`), not this file.*

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

### Git workflow
- Stale `.git/index.lock` mid-session: `rm -f .git/index.lock` (verify no live git process
  via `ps` first), then retry.
- `git status --short` once at session start; track your own changes after that.
- Commit conventions: `feat(...)`/`fix(...)`/`docs(...)`/`refactor(...)`; multi-line `-F -`
  heredoc messages for non-trivial changes.
- `.github/workflows/ci.yml` and `release.yml` are PROTECTED (protect-files.sh hook) — do
  not Edit; leave a note for Jim instead.
- Before removing a scratch worktree, check it still exists.

### Edit/Read discipline
- Read a file before its first Edit in a session (`File has not been read yet` otherwise);
  on `String to replace not found`, re-Read before retrying.
- Large frequently-re-read files (e.g. skill-forge `test/e2e.test.ts`, big SKILL.md files):
  read ONCE, note key facts, refer to notes — some were re-read 6–13× per session.

### Environment quirks
- rtk `find` shim lacks `-not`/`-exec`/compound predicates — use `/usr/bin/find` or `\find`.
- vitest: output is captured by rtk tee; read the newest file in
  `~/Library/Application Support/rtk/tee/` instead of re-running. `--reporter=basic` is
  invalid (use `--reporter=verbose` or omit).
- `npx tsc --noEmit` in skill-forge shows pre-existing `@types/node` errors — `npm run build`
  is the authoritative check; confirm errors are pre-existing via `git stash` before reverting.
- Browser MCP screenshots: max 2 attempts per state; verify tab/load state instead of looping.
- Sanity `query_documents`: run `get_schema` first; never retry an identical GROQ query more
  than twice — cache results in the scratchpad.
