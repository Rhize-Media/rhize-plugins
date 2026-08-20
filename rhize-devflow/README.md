# rhize-devflow

Rhize Media's engineering control-plane plugin. It makes Rhize engineering policy executable
and enforceable across the whole lifecycle of a change:

```text
impact-map → check → review → release
```

Everything namespaces as `rhize-devflow:<skill>` and `/rhize-devflow:<command>`.

## Product boundary

| Owner | Responsibility |
|---|---|
| **Rhize Dev Flow** (this plugin) | Change impact analysis, implementation validation, regression checks, production merge/release review, mutation and browser acceptance workflows. |
| **Rhize Context Manager** | Session state, context retrieval/compression, memory, checkpoints, context health, learning persistence — `/start`, `/done`, `/context-hygiene`, `/context-doctor`. |
| **Official/specialist plugins** | Platform API documentation and specialist analysis (Sentry, Sanity, browser, ECC). This plugin layers Rhize-specific conventions on top of them rather than re-shipping their docs. |

`rhize-context-manager`'s `/done` delegates code-change review to `/rhize-devflow:review` when
Dev Flow is installed and code changed this session; otherwise it runs a disclosed local
fallback checklist. See [rhize-context-manager's README](../rhize-context-manager/README.md) for
the session-lifecycle side of this boundary.

## Commands

### Canonical control-plane workflow

| Command | Stage | Purpose |
|---|---|---|
| `/rhize-devflow:impact-map` | 1 — map | CodeGraph-first structural discovery paired with a semantic impact map (intended behavior, invariants, planned code, operational effects, acceptance tests, unaffected paths); reconciles graph/diff/map after implementation. |
| `/rhize-devflow:check` | 2 — validate | Evidence-driven mid-implementation validation. Builds a deterministic evidence packet (`devflow.py evidence`), selects checks only from repository instructions and known-safe declared package scripts, runs focused tests then repository-mandated gates, returns `PASS` / `PASS_WITH_WARNINGS` / `BLOCKED`. Never executes shell text parsed from prose. |
| `/rhize-devflow:review` | 3 — gate | Read-only production merge/release gate. Resolves the exact base/head comparison range, builds a risk map from actual diff evidence (deployment, data, security, authorization, billing, migration, cache, external-write), routes only relevant specialists, requires an independent skeptical reviewer for non-trivial work, returns `PASS` / `FAIL_WITH_FIXABLE_GAPS` / `FAIL_REQUIRES_HUMAN`. Never commits, pushes, merges, or deploys. |
| `/rhize-devflow:mutation-check` | overlay | Read-only data-mutation consistency check — `PATH...` (scoped file(s)), `--all` (whole codebase), or `--fix-plan` (proposed changes only, never edits source). |
| `/rhize-devflow:browser-qa` | overlay | Scenario-driven browser acceptance check (functional path, console/network errors, accessibility smoke, responsive layout, performance on request) against whichever browser tool is actually connected. |
| `/rhize-devflow:doctor` | overlay | Read-only plugin/install health check — thin adapter over `scripts/devflow.py doctor`. Manifests, canonical commands, referenced assets, duplicate bodies, stale tokens, script/hook integrity, and capability dependencies, reported independently per capability. |
| `/rhize-devflow:devflow-setup` | setup | Interview-driven wizard for the per-machine `.claude/*.local.md` tenant-file convention. |

Release itself (the actual push/merge/deploy) stays outside this plugin — it's governed by
each repository's own push policy, never performed by `check` or `review`.

See [Doctor and evidence CLI](#doctor-and-evidence-cli-scriptsdevflowpy) below for the CLI
`/rhize-devflow:doctor` wraps, and for the separate `evidence` subcommand `check`/`review` use.

### Deprecated (2.12.0 compatibility window)

These are one-line adapters — `> **Deprecated:**` plus the canonical target — not duplicated
workflow bodies. They remain until Dev Flow 3.0.0 at the earliest; see the
[Migration table](#migration-table) for the full old→new mapping.

`/rhize-devflow:` browser-debug · browser-help · browser-perf · browser-test ·
mutation-analyze · mutation-fix

## Migration table

| Old command | Canonical replacement | Notes |
|---|---|---|
| `/rhize-context-manager:impact-map` | `/rhize-devflow:impact-map` | Canonical body moved to Dev Flow; the Context Manager command is now a deprecation adapter only. |
| `/rhize-devflow:mutation-analyze` | `/rhize-devflow:mutation-check --all` | Full-codebase mode of the consolidated command. |
| `/rhize-devflow:mutation-check <file>` | `/rhize-devflow:mutation-check <file>` | Same name; now the scoped mode of the consolidated command (no behavior change). |
| `/rhize-devflow:mutation-fix` | `/rhize-devflow:mutation-check --fix-plan` | `--add-todos`/`--apply` are gone — the consolidated command never writes to source. |
| `/rhize-devflow:browser-debug` | `/rhize-devflow:browser-qa` | Console/network scenario. |
| `/rhize-devflow:browser-help` | `/rhize-devflow:browser-qa` | Tool reference now lives in the `chrome-devtools-mcp` skill and the command's own scenario list. |
| `/rhize-devflow:browser-perf` | `/rhize-devflow:browser-qa` | Performance scenario (on request or when relevant, not run by default). |
| `/rhize-devflow:browser-test` | `/rhize-devflow:browser-qa` | Functional/responsive/accessibility scenarios. |
| *(new, no predecessor)* | `/rhize-devflow:check` | Mid-implementation evidence-driven validation. |
| *(new, no predecessor)* | `/rhize-devflow:review` | Production merge/release gate — the executable successor to the retired `rhize-review` skill workflow. |
| *(new, no predecessor)* | `/rhize-devflow:doctor` | Thin slash-command adapter over `scripts/devflow.py doctor` — plugin/install health. |

## Skills

<!-- SKILL-MAP:BEGIN -->
| Skill | Description | Topics |
| --- | --- | --- |
| `chrome-devtools-mcp` | DevTools-protocol mechanics reference for the `chrome-devtools` MCP server, used by `/rhize-devflow:browser-qa` when that server is the act… | automation, nextjs, observability, testing |
| `data-mutation-consistency` | Enforce consistent data-mutation patterns across Next.js apps on Vercel with Supabase, Sanity, and Payload CMS — so cache tags, query keys,… | data-consistency, nextjs, sanity, sentry, vercel, workflow-patterns |
| `dev-flow-foundations` | Foundational workflow patterns for large-codebase development — CodeGraph-first structural discovery paired with semantic impact mapping, c… | project-planning, workflow-patterns |
| `error-lifecycle-management` | End-to-end production error lifecycle for Next.js/TypeScript on Vercel — triage, root-cause analysis, deployment correlation, and fix verif… | nextjs, observability, sentry, vercel, workflow-patterns |
| `sanity-development` | Rhize-opinionated best practices for Sanity Studio config, schema design, GROQ queries, TypeGen, Portable Text, visual editing, page builde… | cms-development, content-authoring, nextjs, sanity, sentry |
| `sentry-instrumentation` | Rhize conventions for instrumenting Next.js/TypeScript code with Sentry — exception capture (captureException), custom performance spans (s… | nextjs, observability, sentry, workflow-patterns |
<!-- SKILL-MAP:END -->

Each of these five overlay skills carries only Rhize-specific policy or convention, not
platform API reference — `sentry-instrumentation` and `sanity-development` explicitly defer to
the official `sentry:*`/`sanity:*` plugins for SDK setup and exhaustive API docs, and
`chrome-devtools-mcp` shrinks to DevTools-protocol mechanics for `/rhize-devflow:browser-qa`
rather than general browser automation guidance. `dev-flow-foundations` is the reference layer
behind `/rhize-devflow:impact-map`/`check`/`review` — not a command surface itself.

> The `skill-refinement` meta-skill moved to the `rhize-meta` plugin (2026-06-15), then on to the
> `@rhize/skill-forge` npm package as `skill-forge refine` (2026-07-20); external-skill vetting made
> the same npm-package move earlier the same day. The `rhize-meta` plugin is retired.

### `/rhize-devflow:devflow-setup` — local-tenant-file convention

Sets up the per-machine `.claude/*.local.md` tenant store for a client repo — see the
command's own doc (`commands/devflow-setup.md`) for what the convention is and how the setup
works. `rhize-devflow/.claude/error-patterns.local.md` is a filled-in example (not tracked in
this repo — gitignored, as the convention requires).

## Doctor, evidence, and refactor-gate CLIs

Stdlib-only, installed-root-safe (works identically from a source checkout and an installed
plugin cache):

```bash
python3 "$CLAUDE_PLUGIN_ROOT/scripts/devflow.py" doctor [--json] [--plugin-root PATH]
python3 "$CLAUDE_PLUGIN_ROOT/scripts/devflow.py" evidence [--json] [--repo PATH] [--base REF]
python3 "$CLAUDE_PLUGIN_ROOT/scripts/refactor_gate.py" status --workspace PATH [--json]
python3 "$CLAUDE_PLUGIN_ROOT/scripts/refactor_gate.py" prepare --workspace PATH --plan PATH --query TEXT
python3 "$CLAUDE_PLUGIN_ROOT/scripts/refactor_gate.py" reconcile --workspace PATH
```

- **`doctor`** validates plugin health — manifests, canonical commands, referenced assets,
  duplicate command bodies, stale tokens, Python-script importability, hook syntax, and
  capability dependencies. Reports each capability independently (a missing Chrome DevTools MCP
  server degrades `browser-qa` only, not `check`/`review`). Read-only; run it from either the
  source checkout or an installed plugin cache. `/rhize-devflow:doctor` is a thin slash-command
  adapter over this same CLI invocation.
- **`evidence`** collects a deterministic Git/repo-state packet — base/head resolution, changed
  files, protected-file matches, detected package manager and declared package-script names/text,
  repository instruction-file presence, and existing-CodeGraph-index presence/health. `/check` and
  `/review` treat this output as facts, not permission: it never executes anything (no package
  script, no shell text parsed from prose) on its own.
- **`refactor_gate.py`** is the stateful Claude/Codex enforcement runtime. A material-change prompt
  creates pending workspace state; `prepare` validates and hashes the semantic map, discovers
  nested Git roots, runs an existing healthy CodeGraph index (or records the `rg` fallback), and
  reads/hashes any component registry. `reconcile` repeats the same structural branch and refuses
  `OUT_OF_SYNC` changed files. Re-preparing after an impact-map correction preserves the original
  Git/dirty baseline, so already-written implementation cannot be silently blessed as pre-existing.
  Receipts live under
  `~/.claude/rhize-devflow/refactor-gate/`, keyed by canonical workspace path, so both harnesses
  share them. The CLI never initializes CodeGraph or invents a registry. Reconciliation stays live
  for the remainder of the turn so a late source write invalidates it; the successful Stop boundary
  closes it as `completed`, preventing an old receipt from locking an unrelated future task. A
  later material prompt always starts a fresh pending receipt.

`evidence --json`'s output contract is `schemas/devflow-evidence-v1.schema.json`
(`devflow-evidence-v1`); `doctor --json`'s shape is documented in the CLI module's own docstring
rather than a separate schema, since it describes plugin health rather than repository evidence.

Invoke the CLI directly, via `/rhize-devflow:doctor`, or through `/context-doctor`
(`rhize-context-manager`) if that plugin chains into it.

### Capability-scoped dependencies (`setup/manifest.json`)

All dependencies are optional at the plugin level; each is scoped to exactly the capability it
enables, so a missing tool degrades only that capability:

| Dependency | Capability | Missing → | Command/skill it gates |
|---|---|---|---|
| Sentry MCP server | `error-lifecycle` | Can't fetch issues/events/perf data | `error-lifecycle-management` |
| Vercel MCP server | `deploy-correlation` | Can't correlate an error with its causing deployment | `error-lifecycle-management` |
| GitHub MCP server | `commit-pr-correlation` | Can't identify the causing commit/PR or auto-file a ticket | `error-lifecycle-management` |
| Chrome DevTools MCP server | `browser-qa` | The `chrome-devtools-mcp` skill can't run at all (no documented non-MCP fallback for it specifically — `/rhize-devflow:browser-qa` itself degrades gracefully across whichever browser tool is connected) | `chrome-devtools-mcp`, one candidate for `/rhize-devflow:browser-qa` |

Full purpose/degraded-behavior/replacement text for each entry lives in `setup/manifest.json`,
read by the `/rhize-setup` wizard (in the `rhize-ops` plugin).

MCP-kind dependencies are detected across the repo-local `.mcp.json`, `~/.claude.json`
(top-level `mcpServers` plus the per-project entry for the inspected repo), and
`~/.codex/config.toml`'s `mcp_servers` table — see `/rhize-devflow:doctor`'s command doc for
the full source list, redaction rules, and the `DEVFLOW_MCP_CONFIG_PATHS` override.

## Install

For the complete CodeGraph + semantic impact-map workflow, install both this plugin and
`rhize-context-manager`.

**Claude Code — first time on this machine (marketplace not yet configured):**

```text
/plugin marketplace add https://github.com/Rhize-Media/rhize-plugins
/plugin install rhize-devflow@rhize-plugins
/plugin install rhize-context-manager@rhize-plugins
```

**Claude Code — `rhize-plugins` marketplace already configured (the common case on a Rhize dev
machine):**

```bash
claude plugin install rhize-devflow@rhize-plugins
claude plugin install rhize-context-manager@rhize-plugins
```

**Claude Code — updating an existing install:**

```bash
claude plugin marketplace update rhize-plugins
claude plugin update rhize-devflow
claude plugin update rhize-context-manager
```

`claude plugin marketplace update` refreshes the local `rhize-plugins` marketplace snapshot to
the latest commit; `claude plugin update` then pulls each installed plugin up to that snapshot's
version. Running only the second command against a stale snapshot silently no-ops.

**Codex:**

```bash
codex plugin marketplace add https://github.com/Rhize-Media/rhize-plugins
codex plugin add rhize-devflow@rhize-plugins
codex plugin add rhize-context-manager@rhize-plugins
```

Codex reaches the same canonical command bodies as Claude through `.codex-plugin/plugin.json`'s
`skills: "./skills/"` router — there is no separate Codex-specific workflow body to keep in sync.

Start a new Claude/Codex session after installing or updating so the refreshed skills, commands,
and compiled cross-plugin relationship are loaded. Do not append a local cachebuster suffix
(a throwaway branch ref, a `?v=` query string, a re-cloned temp path) to force a refresh for a
published release — resolve through the named `rhize-plugins` marketplace entry and the update
commands above.

### Cache/reinstall smoke test

Plugin caches only refresh on session start, so an update can silently fail to take effect until
you verify it. After any install or update:

1. Start a **fresh** Claude Code session (not a resumed one).
2. Confirm the `/rhize-devflow:` commands appear in the slash-command list (`impact-map`, `check`,
   `review`, `mutation-check`, `browser-qa`, `devflow-setup`, and the six deprecated adapters) —
   or run `claude plugin details rhize-devflow` for a non-interactive check of the installed
   component inventory.
3. Confirm the six skills above (`dev-flow-foundations`, `data-mutation-consistency`,
   `error-lifecycle-management`, `sentry-instrumentation`, `sanity-development`,
   `chrome-devtools-mcp`) are discoverable in that session.
4. Start a **fresh** Codex session and confirm the same skills load from
   `.codex-plugin/plugin.json`'s `skills: "./skills/"` path.
5. Run `python3 "$CLAUDE_PLUGIN_ROOT/scripts/devflow.py" doctor` — it should report `HEALTHY`
   (informational findings are fine; anything else means the cache is stale or the install is
   incomplete).
6. If a command or skill is missing after an update, the installed plugin cache is likely pinned
   behind this repo — re-run `claude plugin marketplace update rhize-plugins` then
   `claude plugin update rhize-devflow`, then repeat steps 1–3 in a new session.

## Hooks

The refactor-evidence workflow is auto-wired for every project that installs this plugin. Its
state is shared by Claude and Codex:

| Runtime | Event | Matcher | Tier | Behavior |
|--------|-------|---------|------|----------|
| `scripts/refactor_gate.py hook-prompt` | UserPromptSubmit | — | T3 | Classifies explicit material implementation/refactor prompts and creates a pending receipt. Review, audit, investigation, and plan-only prompts remain read-only. |
| `scripts/refactor_gate.py hook-write` | PreToolUse | `Edit\|Write\|MultiEdit\|NotebookEdit\|apply_patch` | T4 (blocks) | Allows plan/instruction artifacts but blocks source writes until `prepare`; invalidates reconciliation after later edits. |
| `scripts/refactor_gate.py hook-command` | PreToolUse | `Bash\|exec_command\|functions.exec` | T4 (blocks) | Applies the same source-write gate to patch text carried through Codex/functions.exec, then blocks commit, push, and merge until reconciliation. |
| `scripts/refactor_gate.py hook-stop` | Stop | — | T4 (blocks) | Prevents completion before reconciliation; closes a reconciled receipt so it cannot contaminate a later task. |

The hook output prints the installed gate-script path. `/rhize-devflow:impact-map` provides the
exact `prepare`/`reconcile` commands. Missing CodeGraph or component-registry artifacts are not
errors: the receipt records the documented fallback. False positives are released with `dismiss
--reason "..."`; `RHIZE_REFACTOR_GATE=off` is the explicit operator emergency bypass.

Four heavier specialist guards still ship bundled under `hooks/` and remain **deliberately
opt-in** through `setup/manifest.json`:

| Script | Event | Matcher | Tier | Behavior |
|--------|-------|---------|------|----------|
| `data-mutation-consistency__mutation-detector.sh` | UserPromptSubmit | — | T3 | Suggests `/rhize-devflow:mutation-check` when the prompt combines a mutation/cache keyword with a bug/error keyword. |
| `data-mutation-consistency__prewrite-check.sh` | PreToolUse | `Write\|Edit` | T3 | Warns on Supabase mutations missing error handling/revalidation, `useMutation` calls missing `onError`/`onSettled`, or Payload collections missing `afterChange`/`afterDelete`. |
| `data-mutation-consistency__sentry-stale-data.sh` | UserPromptSubmit | — | T3 | Prints a stale-data investigation checklist on Sentry URLs or stale-data phrasing. |
| `protect-files.sh` | PreToolUse | `Edit\|Write\|MultiEdit\|NotebookEdit` | T4 (blocks) | Blocks edits to CI workflows/`.env*`/billing paths and leaked `NEXT_PUBLIC_*` secrets or client-side Supabase service-role keys. Local copy of the same gate the global `~/.claude/hooks/protect-files.sh` already runs for every session — wire this one in only for environments without that global hook installed. |

Full metadata (id, exact command, description) for the four opt-in hooks above lives in
**`setup/manifest.json`**, read by the `/rhize-setup` wizard (in the `rhize-ops` plugin) so a
project can pick which guard hooks to wire in without hand-editing `.claude/settings.json`. The
manifest also declares the capability-scoped `dependencies` array documented above.

**Fleet setup:** `/rhize-ops:rhize-setup` is what actually wires opt-in items and checks
`dependencies` for you — it requires the `rhize-ops` plugin. Without it, wire an item
manually per the snippet in [rhize-ops/README.md § Setup manifest
schema](../rhize-ops/README.md#setup-manifest-schema).

## Lineage

Migrated from `~/dev-local/CLAUDE-SKILLS` (archived 2026-06). The `skill-refinement` meta-skill
was promoted to the `rhize-meta` plugin (2026-06-15), then, along with `rhize-meta`'s external-skill
vetting, moved on to the `@rhize/skill-forge` npm package (2026-07-20 — `skill-forge refine` /
`npx @rhize/skill-forge`). `rhize-meta` no longer exists in this marketplace. Session/context
engineering (the `context-engineering` skill and its `start`/`done`/`context-hygiene` commands)
moved to `rhize-context-manager` in the 2.5.0 command migration; `impact-map`'s canonical body
moved back here in this control-plane narrowing (`rhize-context-manager` keeps only a
deprecation adapter, see the [Migration table](#migration-table)).

## Compounding Persistence Layer

From the "self-improving agent system" pattern — no run is complete until it leaves the next run better prepared.

- **`agents/verifier.md`** — independent verifier, pinned to the capable-tier model as the final commit gate (read-only: Read/Bash/Glob/Grep). `/rhize-devflow:review` routes to it for non-trivial work; `rhize-context-manager`'s `/done` delegates to `/rhize-devflow:review` before any commit. Verdicts PASS / FAIL_WITH_FIXABLE_GAPS / FAIL_REQUIRES_HUMAN. The maker never grades its own work.
- **STATE.md contract** — `/start` (rhize-context-manager) reads `STATE.md` (Verified facts · General rules · Open failures · Lessons learned · Last session) first; `/done` requires persisting at least one fact/failure/lesson back to it.
- **`hooks/protect-files.sh`** — OPT-IN PreToolUse gate; see the Hooks section above and `setup/manifest.json` for matcher, tier, and wiring details.
- **`templates/hookify/`** — warn-level hookify rules for Next.js/Sanity repos (stop-checks, sanity-schema hint, seo hint, pr-review-on-create). Copy the relevant ones into a repo's `.claude/` as `hookify.<name>.local.md`.
- **`templates/rules/openwolf.md`** — canonical OpenWolf protocol rule (previously copy-pasted per repo, had drifted). Copy into `.claude/rules/` ONLY in repos that have a `.wolf/` directory.
