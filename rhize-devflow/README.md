# rhize-devflow

Rhize Media's development-workflow plugin — the consolidated home for the skills that used to live
in the standalone `CLAUDE-SKILLS` repo (now archived). Everything namespaces as
`rhize-devflow:<skill>` and `/rhize-devflow:<command>`.

## Skills

<!-- SKILL-MAP:BEGIN -->
| Skill | Description | Topics |
| --- | --- | --- |
| `chrome-devtools-mcp` | Browser automation, debugging, and performance analysis via the official Google Chrome DevTools MCP server (Puppeteer-backed, wait-aware). | automation, nextjs, observability, testing |
| `data-mutation-consistency` | Enforce consistent data-mutation patterns across Next.js apps on Vercel with Supabase, Sanity, and Payload CMS — so cache tags, query keys,… | data-consistency, nextjs, sanity, sentry, vercel, workflow-patterns |
| `dev-flow-foundations` | Foundational workflow patterns for large-codebase development — CodeGraph-first structural discovery paired with semantic impact mapping, c… | project-planning, workflow-patterns |
| `error-lifecycle-management` | End-to-end production error lifecycle for Next.js/TypeScript on Vercel — triage, root-cause analysis, deployment correlation, and fix verif… | nextjs, observability, sentry, vercel, workflow-patterns |
| `sanity-development` | Rhize-opinionated best practices for Sanity Studio config, schema design, GROQ queries, TypeGen, Portable Text, visual editing, page builde… | cms-development, content-authoring, nextjs, sanity, sentry |
| `sentry-instrumentation` | Rhize conventions for instrumenting Next.js/TypeScript code with Sentry — exception capture (captureException), custom performance spans (s… | nextjs, observability, sentry, workflow-patterns |
<!-- SKILL-MAP:END -->

> The `skill-refinement` meta-skill moved to the `rhize-meta` plugin (2026-06-15), then on to the
> `@rhize/skill-forge` npm package as `skill-forge refine` (2026-07-20); external-skill vetting made
> the same npm-package move earlier the same day. The `rhize-meta` plugin is retired.

## Commands

`/rhize-devflow:` mutation-analyze · mutation-check ·
mutation-fix · browser-debug · browser-help · browser-perf · browser-test · devflow-setup

> **Moved:** context/session engineering (the `context-engineering` skill and its `start`, `done`,
> `context-hygiene`, and `impact-map` commands) now lives in the
> [`rhize-context-manager`](../rhize-context-manager/README.md) plugin.

`dev-flow-foundations` still owns the impact-analysis discipline: use CodeGraph first for current
symbols, callers, tests, and dependency paths; use the semantic impact map for intended behavior,
invariants, operational risk, planned code, and acceptance criteria; then sync CodeGraph and
reconcile both after implementation. The executable `/rhize-context-manager:impact-map` command
implements that contract so the two plugins do not ship competing copies.
The compiled skill graph records the command's dependency on the shared foundation, and the
existing version/CI gate runs the shared contract test whenever either owning plugin changes.

### `/rhize-devflow:devflow-setup` — local-tenant-file convention

Sets up the per-machine `.claude/*.local.md` tenant store for a client repo — see the
command's own doc (`commands/devflow-setup.md`) for what the convention is and how the setup
works. `rhize-devflow/.claude/error-patterns.local.md` is a filled-in example (not tracked in
this repo — gitignored, as the convention requires).

## Install

For the complete CodeGraph + semantic impact-map workflow, install both plugins. Dev Flow alone
still supplies the reference skill, but it deliberately does not register a duplicate
`/impact-map` command.

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

Start a new Claude/Codex session after installing or updating so the refreshed skills, command,
and compiled cross-plugin relationship are loaded. Do not append a local cachebuster suffix
(a throwaway branch ref, a `?v=` query string, a re-cloned temp path) to force a refresh for a
published release — resolve through the named `rhize-plugins` marketplace entry and the update
commands above.

### Cache/reinstall smoke test

Plugin caches only refresh on session start, so an update can silently fail to take effect until
you verify it. After any install or update:

1. Start a **fresh** Claude Code session (not a resumed one).
2. Confirm the `/rhize-devflow:` commands appear in the slash-command list (`mutation-check`,
   `mutation-analyze`, `mutation-fix`, `browser-debug`, `browser-help`, `browser-perf`,
   `browser-test`, `devflow-setup`) — or run `claude plugin details rhize-devflow` for a
   non-interactive check of the installed component inventory.
3. Confirm the six skills above (`dev-flow-foundations`, `data-mutation-consistency`,
   `error-lifecycle-management`, `sentry-instrumentation`, `sanity-development`,
   `chrome-devtools-mcp`) are discoverable in that session.
4. Start a **fresh** Codex session and confirm the same skills load from
   `.codex-plugin/plugin.json`'s `skills: "./skills/"` path.
5. If a command or skill is missing after an update, the installed plugin cache is likely pinned
   behind this repo — re-run `claude plugin marketplace update rhize-plugins` then
   `claude plugin update rhize-devflow`, then repeat steps 1–3 in a new session.

## Hooks

This plugin auto-wires no hooks (`hooks/hooks.json` is `{"hooks": {}}`). Four heavier guard
scripts ship bundled under `hooks/` but are **deliberately opt-in** — wire the ones you want
into a project's `.claude/settings.json`, so nothing untested fires automatically on every
session:

| Script | Event | Matcher | Tier | Behavior |
|--------|-------|---------|------|----------|
| `data-mutation-consistency__mutation-detector.sh` | UserPromptSubmit | — | T3 | Suggests `@analyze-mutations`/`@check-mutation` when the prompt combines a mutation/cache keyword with a bug/error keyword. |
| `data-mutation-consistency__prewrite-check.sh` | PreToolUse | `Write\|Edit` | T3 | Warns on Supabase mutations missing error handling/revalidation, `useMutation` calls missing `onError`/`onSettled`, or Payload collections missing `afterChange`/`afterDelete`. |
| `data-mutation-consistency__sentry-stale-data.sh` | UserPromptSubmit | — | T3 | Prints a stale-data investigation checklist on Sentry URLs or stale-data phrasing. |
| `protect-files.sh` | PreToolUse | `Edit\|Write\|MultiEdit\|NotebookEdit` | T4 (blocks) | Blocks edits to CI workflows/`.env*`/billing paths and leaked `NEXT_PUBLIC_*` secrets or client-side Supabase service-role keys. Local copy of the same gate the global `~/.claude/hooks/protect-files.sh` already runs for every session — wire this one in only for environments without that global hook installed. |

> **SessionStart banner removed (2026-08-09):** the conditional dev-file-detection banner
> that used to live here moved to
> [`rhize-context-manager`'s `session-disclosure.js`](../rhize-context-manager/README.md#hooks)
> — Phase 3 of the skill-map plan (`docs/skill-map.md`). It fingerprints the repo against the
> compiled skill map's stack tags instead of this plugin's fixed dev-file signal list.

> **Moved (2026-08-09):** the `context-engineering__*` hooks (`duplicate-check`,
> `pre-commit-guard`, `session-init`, `skill-suggester`) had already been superseded by
> identical/newer copies living in
> [`rhize-context-manager/skills/context-engineering/hooks/`](../rhize-context-manager/README.md#hooks)
> since the 2.5.0 command migration — the copies here were stale duplicates and have been
> removed rather than relocated a second time. The `skill-refinement__*` hooks
> (`refinement-detector`, `session-end`) were genuinely still stranded here and have moved to
> [`rhize-context-manager/hooks/`](../rhize-context-manager/README.md#hooks), renamed
> `refinement-pipeline__*` to match the skill that now owns them.

Full metadata (id, exact command, description) for the four hooks above lives in
**`setup/manifest.json`**, read by the `/rhize-setup` wizard (in the `rhize-ops` plugin) so a
project can pick which guard hooks to wire in without hand-editing `.claude/settings.json`. The
manifest also declares a `dependencies` array (Sentry/Vercel/GitHub/Chrome DevTools MCP servers)
that the wizard's dependency check reads.

**Fleet setup:** `/rhize-ops:rhize-setup` is what actually wires opt-in items and checks
`dependencies` for you — it requires the `rhize-ops` plugin. Without it, wire an item
manually per the snippet in [rhize-ops/README.md § Setup manifest
schema](../rhize-ops/README.md#setup-manifest-schema).

**Fixed 2026-08-04** (all remaining scripts already read stdin correctly except these two,
which were silently dead or non-portable):
- `data-mutation-consistency__sentry-stale-data.sh` read the prompt from a positional `$1`
  argument; Claude Code delivers hook payloads as JSON on stdin, never as command-line args —
  same failure mode, the hook never fired.
- `data-mutation-consistency__prewrite-check.sh` extracted fields with GNU-only `grep -oP`,
  which macOS's default BSD grep rejects outright — the hook never matched on macOS.

## Lineage

Migrated from `~/dev-local/CLAUDE-SKILLS` (archived 2026-06). The `skill-refinement` meta-skill
was promoted to the `rhize-meta` plugin (2026-06-15), then, along with `rhize-meta`'s external-skill
vetting, moved on to the `@rhize/skill-forge` npm package (2026-07-20 — `skill-forge refine` /
`npx @rhize/skill-forge`). `rhize-meta` no longer exists in this marketplace.

## Compounding Persistence Layer (v2.4.0)

From the "self-improving agent system" pattern — no run is complete until it leaves the next run better prepared.

- **`agents/verifier.md`** — independent verifier, pinned to the capable-tier model as the final commit gate (read-only: Read/Bash/Glob/Grep). `/done` delegates to it before any commit; verdicts PASS / FAIL_WITH_FIXABLE_GAPS / FAIL_REQUIRES_HUMAN. The maker never grades its own work.
- **STATE.md contract** — `/start` reads `STATE.md` (Verified facts · General rules · Open failures · Lessons learned · Last session) first; `/done` requires persisting at least one fact/failure/lesson back to it.
- **`hooks/protect-files.sh`** — OPT-IN PreToolUse gate; see the Hooks section above and `setup/manifest.json` for matcher, tier, and wiring details.
- **`templates/hookify/`** — warn-level hookify rules for Next.js/Sanity repos (stop-checks, sanity-schema hint, seo hint, pr-review-on-create). Copy the relevant ones into a repo's `.claude/` as `hookify.<name>.local.md`.
- **`templates/rules/openwolf.md`** — canonical OpenWolf protocol rule (previously copy-pasted per repo, had drifted). Copy into `.claude/rules/` ONLY in repos that have a `.wolf/` directory.
