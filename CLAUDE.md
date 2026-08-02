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

## Headroom Learned Patterns
*Auto-generated by `headroom learn` on 2026-06-16 — do not edit manually*

### Fact-Forcing Gate: Edit Commands
*~2,800 tokens/session saved*
- **Before every Edit, run `grep -rl "<basename>" .` to enumerate all files that import/require it**, then present that list in a preceding Bash FACTS echo — the gate blocks any Edit that omits this step.
- Four blocked Edits in one session (SKILL.md, monitor.py, CLAUDE.md, MEMORY.md) — always satisfy the gate before the Edit tool call, not after.

### Repo Structure: skill-monitor Consolidation
*~2,000 tokens/session saved*
- `skill-monitor` has been consolidated into the rhize-ops plugin at `rhize-ops/skill-monitor/monitor.py`. The old standalone repo `~/dev-local/skill-monitor/` is archived on GitHub and deleted locally — never reference the old path.
- The weekly-skill-audit scheduled task has been repointed to `rhize-ops/skill-monitor/monitor.py`; data paths inside monitor.py are `__file__`-relative.

### Fact-Forcing Gate: Bash Commands
*~1,400 tokens/session saved*
- **Prefix every first Bash command each session (and after any `mcp__ccd_session__mark_chapter` call) with an inline FACTS echo**: `echo "FACTS: (1) <user request in one sentence>; (2) <what this command verifies/produces>" &&` — skipping this blocks the command and wastes a round-trip.
- The gate re-arms after each chapter mark, so the first Bash after each new phase also needs the FACTS prefix.
- Bypass for pure repair/setup work: set `ECC_GATEGUARD=off`.

### Fact-Forcing Gate: Write (New Files)
*~1,400 tokens/session saved*
- **Before creating a new file with Write, identify which existing files will call or reference it** and state them in a Bash FACTS echo first — the gate demands: "Name the file(s) and line(s) that will call this file."
- If no existing caller yet, state that explicitly: `echo "FACTS: new entry point — no existing caller."`

## Headroom Learned Patterns
*Auto-generated by `headroom learn` on 2026-06-29 — do not edit manually*

### Fact-Forcing Gate
*~4,000 tokens/session saved*
- A [Fact-Forcing Gate] hook fires before the **first** Bash command of a new user request and before any Edit/Write to a file. Satisfy it by prepending an `echo "FACTS: (1) <user request in one sentence> (2) <what this command verifies/produces>..."` line to the first Bash, or by stating the required facts in the tool call for Edit/Write.
- For Edit/Write gates: state all files that import/require the target file (use Grep first if unknown) and the exact lines being changed and why.
- Failing to satisfy the gate returns an error and wastes a full round-trip; always satisfy proactively.

### Repository Layout
*~2,500 tokens/session saved*
- Main repo: `/Users/jamesdeola/dev-local/RHIZE/rhize-plugins` (branch `main`)
- Plugin registry: `.claude-plugin/marketplace.json` at repo root
- Rhize-ops plugin lives under `rhize-ops/` with skills at `rhize-ops/skills/<skill-name>/SKILL.md`
- `skill-monitor` tool has been consolidated into `rhize-ops/skill-monitor/monitor.py`; the standalone `~/dev-local/skill-monitor` repo is retired (GitHub-archived, local dir deleted).

### Git Workflow
*~800 tokens/session saved*
- Stale `.git/index.lock` can appear mid-session; resolve with `rm -f .git/index.lock` before retrying `git add/commit`.
- Always `cd` to the target repo root explicitly before git commands when working across multiple repos in the same session.

### Edit Before Read
*~600 tokens/session saved*
- Always `Read` a file before issuing an `Edit` to it; attempting Edit without a prior Read in the same session triggers `<tool_use_error>File has not been read yet`.

## Headroom Learned Patterns
*Auto-generated by `headroom learn` on 2026-07-11 — do not edit manually*

### Fact-Forcing Gate
*~500 tokens/session saved*
- The project enforces a Fact-Forcing Gate on the first `Bash` command of each chapter and on every `Edit`/`Write`. Before running, state: (1) the user request in one sentence, (2) what the command produces or verifies. Failure to do so triggers an error and a wasted retry.
- For `Edit`/`Write`, also present: all files that import/require the target, and the callers/line numbers of the new file.

### Repository Structure
*~400 tokens/session saved*
- The `skill-monitor` tool has been consolidated from `~/dev-local/skill-monitor/` into `rhize-ops/skill-monitor/` inside this repo. The old local directory has been deleted and the GitHub repo archived.
- Scheduled tasks that previously referenced `~/dev-local/skill-monitor/monitor.py` now point to the new repo-relative path inside `rhize-ops/skill-monitor/monitor.py`.

### Git Workflow
*~300 tokens/session saved*
- If `git commit` fails with `index.lock: File exists`, check for stale lock files with `rm -f .git/index.lock` before retrying — do not assume another git process is running without verifying via `ps`.

### Edit Guardrails
*~240 tokens/session saved*
- Always `Read` a file before attempting to `Edit` it in the same session; skipping the read causes an immediate `File has not been read yet` error and wastes a round-trip (seen with `skill-monitor/monitor.py`).
- Before editing any file, use `Grep` to list all files that import or reference it — the Fact-Forcing Gate will block the edit otherwise and force a retry.

## Headroom Learned Patterns
*Auto-generated by `headroom learn` on 2026-07-20 — do not edit manually*

### Screenshots — browser MCP loop guard
*~27,373 tokens/session saved*
- `mcp__Claude_Browser__computer screenshot` can repeat 6+ times if the page hasn't loaded or the tab ID is wrong. Verify the tab is active and fully loaded before taking more than 2 screenshots in a row; if still failing after 2 attempts, report the issue rather than looping.

### File paths — frequently re-read
*~12,000 tokens/session saved*
- `/Users/jamesdeola/dev-local/RHIZE/skill-forge/test/e2e.test.ts` — large, often re-read; read once and cache mentally.
- `/Users/jamesdeola/dev-local/RHIZE/rhize-plugins/rhize-ops/skills/delegate-to-teammate/SKILL.md` — large (~18KB); read once per session.
- `/Users/jamesdeola/dev-local/RHIZE/rhize-plugins/rhize-devflow/GUIDE.md` — re-read 5+ times per session; read once.

### Scratchpad — worktree paths
*~7,456 tokens/session saved*
- Claude agent scratchpad base: `/private/tmp/claude-501/-Users-jamesdeola-dev-local-RHIZE-rhize-plugins/<session-uuid>/scratchpad/`
- When running iterative cd+command loops in the scratchpad worktree, set `SCRATCH=<path>` once at the top and reuse; avoid re-expanding the full path 34+ times per session.

### Repo layout — skill-forge
*~7,456 tokens/session saved*
- CLI repo: `/Users/jamesdeola/dev-local/RHIZE/skill-forge`
- Build: `npm run build` (tsup). Tests: `npm test` or `npx vitest run`. Pack check: `npm pack --dry-run`.
- Key source files: `src/gate/{profile,safety,overlap,mcpSafety,mcpCapabilities,mcpOverlap}.ts`, `src/commands/{add,scan,gatePipeline,init}.ts`, `src/install/{resolve,quarantine,promote,promoteMcp}.ts`
- CLAUDE.md at repo root contains conventions — always read it before starting work.

### Repo layout — rhize-plugins
*~7,456 tokens/session saved*
- Root: `/Users/jamesdeola/dev-local/RHIZE/rhize-plugins`
- Plugin dirs: `seo-aeo-geo/`, `obsidian-second-brain/`, `project-launcher/`, `rhize-devflow/`, `rhize-ops/`, `rhize-meta/`, `rhize-context-manager/`
- Marketplace manifest: `.claude-plugin/marketplace.json` (root-level)
- Version bumping: use `python3 scripts/bump_version.py --plugin <name> --level minor|patch|major`

### Subagent tasks — undefined repo path
*~6,079 tokens/session saved*
- Many subagent task specs have `REPO: undefined` due to a template bug. When this occurs, immediately locate the repo with: `find /Users/jamesdeola/dev-local/RHIZE -maxdepth 3 -iname 'package.json' | xargs grep -l 'skill-forge' 2>/dev/null` — the answer is always `/Users/jamesdeola/dev-local/RHIZE/skill-forge`.

### Edit workflow — read before edit
*~5,000 tokens/session saved*
- The Edit tool requires the file to have been Read in the same session first, or it throws `File has not been read yet`. Always Read before the first Edit on any file.
- When `String to replace not found` errors occur, re-Read the file to get the current content before retrying the Edit.

### Environment — find command
*~4,000 tokens/session saved*
- `find` via rtk is an alias that **does not support** `-not`, `-exec`, or compound predicates. Always use `/usr/bin/find` or `\find` for complex find invocations with `-not -path`, `-exec`, or combined `-o` conditions.
- Pattern: `\find /path -name '*.ts' -not -path '*/node_modules/*' | sort`

### Sanity MCP — query loop guard
*~3,234 tokens/session saved*
- `mcp__2475bd27-....__query_documents` with the same GROQ query repeats when results are empty or schema mismatches. Run `get_schema` first to confirm field names, then query once; do not retry the same query more than twice.

### Environment — vitest
*~3,000 tokens/session saved*
- Run tests with `npx vitest run` (not `npm test | tail`) when you need visible output; `npm test` output is truncated by rtk tee. Redirect full output: `npx vitest run > /tmp/vitest.log; tail -150 /tmp/vitest.log`.
- `npx vitest run --reporter=basic` fails (unknown reporter); use `--reporter=verbose` or omit the flag.

### Environment — tsc type-checking
*~2,500 tokens/session saved*
- `npx tsc --noEmit` frequently reports pre-existing `Cannot find name 'node:fs'` / `@types/node` errors that are environmental, not caused by edits. Use `npm run build` (tsup) as the authoritative build check; tsup suppresses those errors.
- Confirm tsc errors are pre-existing before reverting changes: `git stash && node_modules/.bin/tsc --noEmit; git stash pop`.

### Git workflow
*~2,000 tokens/session saved*
- Always run `git status --short` before staging to confirm scope; avoid staging unintended files.
- Commit message convention: `feat(v0.x): ...` for features, `refactor(phase-N): ...` for simplify passes, `docs(...): ...` for doc changes.
- Use `python3 scripts/bump_version.py` in rhize-plugins (not manual JSON edits) to bump plugin versions and update marketplace.json + CHANGELOG.md atomically.

### Environment — CI workflow files
*~800 tokens/session saved*
- `.github/workflows/ci.yml` and `.github/workflows/release.yml` are **protected files** — edits are blocked by the `protect-files.sh` hook. Do not attempt to Edit them; inform the user instead.

## Headroom Learned Patterns
*Auto-generated by `headroom learn` on 2026-07-27 — do not edit manually*

### Screenshot Loop — Browser MCP
*~27,373 tokens/session saved*
- Taking repeated `mcp__Claude_Browser__computer` screenshots to check page state is expensive (~27 K tokens per loop). Take one screenshot, act on what is visible, and only take another if you made a change and need to verify the result.

### Repeated File Reads — Large Files
*~25,000 tokens/session saved*
- `test/e2e.test.ts` (skill-forge) was re-read 13× in one session (~6 K tokens). Read it once, store key facts in your scratchpad, and refer back to the scratchpad.
- `src/commands/gatePipeline.ts`, `src/gate/mcpSafety.ts`, `src/gate/safety.ts`, `src/commands/add.ts`, `GUIDE.md` (rhize-devflow), and `rhize-ops/skills/delegate-to-teammate/SKILL.md` are each re-read 6–7× per session. Read once per session and take notes.

### Scratch/Worktree cd Loop
*~7,456 tokens/session saved*
- The pattern `cd /private/tmp/claude-501/-Users-jamesdeola-dev-local-RHIZE-rhize-plugins/<uuid>/...` repeated 34× in a single session (~7 456 tokens). Set the path once as a shell variable (`SCRATCH=...`) and reuse it — do NOT reconstruct the full path on every Bash call.

### Repository Paths — Key Files
*~7,456 tokens/session saved*
- rhize-plugins marketplace: `.claude-plugin/marketplace.json`
- rhize-meta skill-forge SKILL.md: `rhize-meta/skills/rhize-skill-forge/SKILL.md` (large — ~18–25 KB)
- skill-forge CLAUDE.md: `/Users/jamesdeola/dev-local/RHIZE/skill-forge/CLAUDE.md`
- rhize-review gate SKILL: `/Users/jamesdeola/dev-local/RHIZE/rhize-plugins/skills/rhize-review/SKILL.md` (also at `~/.claude/skills/rhize-review/SKILL.md`)
- delegate-to-teammate SKILL.md: `rhize-ops/skills/delegate-to-teammate/SKILL.md` (~18 KB; do not re-read unless diffing)

### Repository Paths
*~7,456 tokens/session saved*
- skill-forge CLI repo: `/Users/jamesdeola/dev-local/RHIZE/skill-forge`
- rhize-plugins repo: `/Users/jamesdeola/dev-local/RHIZE/rhize-plugins`
- skill-forge scratch/worktree: `/private/tmp/claude-501/-Users-jamesdeola-dev-local-RHIZE-rhize-plugins/a87efbcc-86c9-4667-acf1-ade4676fb660/`
- When a build-agent task passes `undefined` as the repo path, search for the repo at the paths above — do NOT attempt to operate on the literal string `undefined`.

### skill-forge Build Commands
*~6,079 tokens/session saved*
- Build: `cd /Users/jamesdeola/dev-local/RHIZE/skill-forge && npm run build` (uses tsup, not tsc directly)
- Test: `npm test` (alias for `npx vitest run`); targeted: `npx vitest run test/foo.test.ts`
- Type-check: `npm run build` is the canonical check; `npx tsc --noEmit` will show pre-existing `@types/node` errors that are NOT caused by local changes — ignore them.
- Version bump: edit `package.json` manually, then `npm run build && npm test && node dist/cli.js --version`

### rhize-plugins Plugin Structure
*~4,878 tokens/session saved*
- Plugins: `seo-aeo-geo`, `obsidian-second-brain`, `project-launcher`, `rhize-devflow`, `rhize-ops`, `rhize-meta`, `rhize-context-manager` (new)
- Each plugin must have: `README.md`, `GUIDE.md`, `.claude-plugin/plugin.json`, skills under `skills/*/SKILL.md`, commands under `commands/*.md`
- `seo-aeo-geo` and `project-launcher` do NOT have a `GUIDE.md` by default (they were created in the doc-restructure sprint)
- Version bumping: use `python3 scripts/bump_version.py --plugin <name> --level minor|patch|major` — this updates `plugin.json` AND `marketplace.json` AND `CHANGELOG.md` atomically

### Sanity / Marketplace MCP Query Loop
*~3,234 tokens/session saved*
- The `mcp__2475bd27-8b1f-4571-8c95-a3e69be8c345__query_documents` call for `projectId: '3g5yoen6', dataset: 'production'` repeated 8× (~3 234 tokens). Cache results locally in the session scratchpad; only re-query if you need fresh data after a mutation.

### Environment — find Command
*~3,000 tokens/session saved*
- `rtk find` does NOT support compound predicates (`-not`, `-exec`, `-o` with `-prune`). Use `/usr/bin/find` or prefix with `\find` to bypass the rtk shim when compound predicates are needed.
- Pattern: `\find /path -iname '*.ts' -not -path '*/node_modules/*'` or `/usr/bin/find /path ...`

### Environment — vitest Output
*~2,500 tokens/session saved*
- `npx vitest run` output is fully captured by rtk tee; when the inline output is truncated/empty, read the full log: `cat "$HOME/Library/Application Support/rtk/tee/$(ls -t "$HOME/Library/Application Support/rtk/tee/" | head -1)"` — do NOT re-run vitest just to see output.
- `--reporter=basic` is not a valid vitest reporter; use `--reporter=verbose` or omit the flag.

### Edit Tool — Pre-read Requirement
*~1,500 tokens/session saved*
- The Edit tool requires the file to have been Read in the same session before writing. If an Edit fails with `File has not been read yet`, do a Read first — do NOT retry the Edit blind.

### Git Workflow
*~1,500 tokens/session saved*
- Protected files: `.github/workflows/ci.yml` and `.github/workflows/release.yml` are blocked by the `protect-files.sh` hook — do NOT attempt to Edit them; instead leave a note for the user.
- `git status --short` repeated 3× in a session is a sign of lost context; check git state once at the start of a session and track your own changes.
- `git worktree remove --force /private/tmp/claude-501/...` repeated 4× across sessions — check if the worktree still exists before trying to remove it.
