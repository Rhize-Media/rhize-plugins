# rhize-devflow Plugin — User Guide

This guide explains what the rhize-devflow plugin does, how its pieces fit together, and how to get the most out of it while building on Next.js/Sanity/Payload/Supabase stacks deployed on Vercel.

## What This Plugin Does

rhize-devflow is Rhize's engineering control plane: the executable workflow that takes a change
from "what will this touch" through "does it pass" to "is it safe to ship" —

```text
impact-map → implement → simplify → check → review → release
```

— plus the production-grade development discipline Rhize expects around that spine: triaging and
root-causing a production error, keeping cache tags and query keys from drifting apart,
instrumenting code with Sentry the Rhize way, driving a real browser for acceptance testing, and
writing Sanity schemas and GROQ queries in house style.

It's for developers (and Claude, acting as one) who are shipping to production — not prototyping
in a vacuum. The plugin assumes real stakes: an unmapped change breaks an unexpected consumer, a
stale cache means a client sees wrong data, an uninstrumented error means nobody finds out until a
user complains, and a merge without an independent review is a merge nobody actually checked.
Every command and skill here exists to prevent one of those failure modes.

The plugin has two kinds of components:

**Skills** are reference knowledge and workflows Claude and Codex load automatically when your request matches certain trigger phrases. You don't have to invoke them directly — the host reads them behind the scenes to produce better output. All seven overlay skills here (everything except `dev-flow-foundations`, which is pure reference) carry only Rhize-specific policy or convention — they defer to the official `sentry:*`/`sanity:*` plugins and the active browser tool's own skill for platform API reference.

**Commands** are actions you invoke explicitly with a slash prefix (e.g., `/rhize-devflow:check`). They drive a specific workflow, usually combining several skills and real tool calls (git, build commands, browser automation, subagents).

## Getting Started

If Dev Flow isn't installed yet, or you suspect a stale copy, see the [README's Install
section](./README.md#install) for the exact commands — the short version:

- **Claude Code**, marketplace already configured: `claude plugin install rhize-devflow@rhize-plugins`.
- **Claude Code**, updating: `claude plugin marketplace update rhize-plugins` then
  `claude plugin update rhize-devflow`.
- **Codex**: `codex plugin add rhize-devflow@rhize-plugins` (after `codex plugin marketplace add`
  once, the first time).

Then start a brand-new session (not a resumed one) — plugin caches only refresh at session
start. A quick way to tell it worked: ask "what `/rhize-devflow:` commands are available?" and
confirm you see `impact-map`, `simplify`, `check`, `test-evidence`, `review`, `mutation-check`, `browser-qa`,
`doctor`, and `devflow-setup` in the [Commands Reference](#commands-reference) below. If a command or skill is
missing after an update, run `/rhize-devflow:doctor` (or
`python3 "$CLAUDE_PLUGIN_ROOT/scripts/devflow.py" doctor` directly) — it names exactly what's
missing or stale — before assuming something is broken.

## Quick Mental Model

The control-plane sequence is the spine; eight overlay skills feed it or run alongside it:

| Stage/Cluster | Command or skills | Question it answers |
|---------|--------|----------------------|
| **1. Map** | `/rhize-devflow:impact-map` (backed by `dev-flow-foundations`) | "What already touches this area, and what's the intended change?" |
| **Post-implementation** | `/rhize-devflow:simplify` (backed by `simplify`) | "Can this exact change have fewer sources of truth or less duplication without changing behavior?" |
| **2. Validate** | `/rhize-devflow:check` | "Does this pass the tests and gates that actually apply to what changed?" |
| **Pre-review evidence** | `test-evidence`, `/rhize-devflow:test-evidence` | "Does this regression test protect behavior, an exact artifact, or only its current implementation?" |
| **3. Gate** | `/rhize-devflow:review` | "Is this safe to merge, and has someone other than me actually checked?" |
| **Release** | `completed-branch-promotion` | "The work is done and authorized; what exact PR/deployment sequence ships it safely?" |
| **Production errors** | `error-lifecycle-management`, `sentry-instrumentation` | "How do I instrument this so I find out when it breaks, and how do I triage it once it does?" |
| **Data-mutation consistency** | `data-mutation-consistency`, `/rhize-devflow:mutation-check` | "Will this mutation leave the cache and the UI in sync, or will someone have to hard-refresh?" |
| **Browser acceptance** | `chrome-devtools-mcp`, `/rhize-devflow:browser-qa` | "What does this actually look like/do in a real browser — network, console, accessibility, layout, performance?" |
| **CMS house style** | `sanity-development` | "What's the Rhize-opinionated way to model this in Sanity?" |

Session lifecycle (`/start`, `/done`, `/context-hygiene`) is owned by the paired
`rhize-context-manager` plugin, not this one — `/done` there delegates code-change review to
`/rhize-devflow:review` when Dev Flow is installed and code changed this session.

## Skills Reference

### dev-flow-foundations

**When it activates:** You mention "design patterns", "workflow optimization", "prevent regression", "anti-patterns", "dependency mapping", "impact map", "CodeGraph", "component registry", "why did this break again", or want to set up durable development guardrails.

**What it knows:** Six foundational workflow problems and their fixes — CodeGraph-first structural discovery paired with semantic impact mapping, a component/function registry to stop duplicate components from being built, context hygiene principles (CLAUDE.md as a <200-line router, not an essay), regression prevention (root-cause first, never patch blind), anti-pattern detection at write-time rather than at review, and a skill-refinement pattern for turning a repeated fix into a formal skill.

**How to use it effectively:**
- Run `/rhize-devflow:impact-map` before implementing or materially changing a feature, bug fix, refactor, schema, migration, cache path, authorization rule, or cross-repository contract — it uses CodeGraph for the current call/dependency surface, then records only the semantic delta, invariants, risks, and acceptance tests a graph cannot express.
- After implementation, the same command reconciles the completed graph and diff against the map (`IN_SYNC` / `IN_SYNC_WITH_EXCEPTIONS` / blocking `OUT_OF_SYNC`). A stale pre-change map is not completion evidence.
- The Stop hook closes a successfully reconciled receipt as `completed`. A same-turn late source write still invalidates reconciliation, while an unrelated later task cannot inherit the old map; a new material prompt starts a new pending receipt.
- Ask "why does this keep breaking every time we touch it?" — it applies the regression-prevention protocol: root cause before fix, test before deploy.
- This is the reference layer behind the executable command, not a command surface itself — `/rhize-devflow:impact-map` (this plugin) implements the Dependency Graph foundation directly; `error-lifecycle-management` implements the Regression Prevention foundation as its triage workflow.

### simplify

**When it activates:** You ask to simplify, consolidate, deduplicate, reduce complexity, apply
React best practices, remove redundant state/Effects, or check whether recent work has a cleaner
behavior-preserving form.

**What it knows:** How to resolve the exact task diff, protect unrelated dirty work, review through
reuse/quality/efficiency lenses, and reject changes that weaken product behavior, authorization,
tenancy, audit, concurrency, accessibility, schemas, errors, or external side effects. Its
React/Next.js checks cover derived state, external-system Effects, Server/Client boundaries,
mutation refresh lifecycle, semantic controls, and evidence-backed memoization. It treats an
evidence-backed no-op as success and never rewrites an applied migration for cleanup.

**How to use it effectively:**
- Ask for edits when you want safe candidates applied and validated.
- Add "read-only" when you want a candidate report without source changes.

### test-evidence

**When it activates:** Tests changed, a change claims regression coverage, or you ask whether a test
actually protects behavior. It does not activate for cache/data mutation consistency.

**What it knows:** The behavior, artifact, and structural contract classes; independent-oracle
requirements; exact Git/file binding; protected-target denials; and isolated mutation lifecycle.

**Example prompt:** "These new tests claim to prevent the query-key regression. Classify the
contract and produce test evidence before review."
- Name a range or files when the task boundary is broader than the current session's changes.
- Run `/rhize-devflow:check` after applied simplifications and `/rhize-devflow:review` before a
  production release.

**Key insight:** Simplification is a behavior-preserving reduction, not a license for redesign.
Fewer lines are useful only when the resulting ownership and safeguards are at least as clear.

### completed-branch-promotion

**When it activates:** Implementation is complete and you say "push to main", "push to dev and
main", or otherwise explicitly ask to ship/promote the completed feature or task branch.

**What it does:** Treats those phrases as the already-chosen release outcome, so it does not ask
you to restate the branch/PR menu. It verifies exact local and remote refs, protects unrelated
dirty work, runs the scoped simplify/check/review gates, publishes the task branch, uses a PR into
`dev` when the repository actually uses `dev`, verifies that deployment, then promotes through a
PR to `main` and correlates the exact production deployment and smoke checks. Repositories without
a `dev` flow use task branch -> PR -> `main`. A raw push or direct commit to a protected branch is
never the default meaning of "push to main".

Repository-specific manual/auto-push policy, migration order, merge method, deployment gates, and
an explicit different sequence still win. In a manual-push repository, either trigger phrase is
the explicit promotion authorization; without it, the skill does not invent permission. If Vercel
requires an authorized deployment commit author, the skill can use a content-neutral locally
authored release commit after verifying the local identity and identical tree, without rewriting
existing authors.

**Examples:**
- "The feature is finished. Push to main."
- "Everything is validated; push to dev and main."
- "Push to main, but skip dev for this repository-approved hotfix."

**Key insight:** This is the mutation-capable step after the read-only review gate. It builds on
Superpowers' generic branch-finishing mechanics, but Rhize owns the repository-policy-aware
promotion sequence and exact remote/deployment proof. If that maintained Superpowers skill is not
installed, promotion stops before mutation instead of duplicating its mechanics.

### error-lifecycle-management

**When it activates:** You mention an "error", "bug", "crash", "exception", "stack trace", "500/404", "timeout", "failed deployment", "production issue/incident", "memory leak", "bundle size", or say something is "slow" or "broken" — and especially when correlating an error spike to a recent deploy or commit.

**What it knows:** The full production error lifecycle for Next.js/TypeScript on Vercel — a decision tree for classifying an error as Runtime/Build/Performance, the Sentry → Vercel → GitHub correlation workflow (get the issue, check affected-user impact, correlate to recent commits, generate a fix), severity thresholds for triggering an incident response (>100 users affected, >20% performance regression, any data-corruption risk), and validation scripts for scanning error-handling and Server Action coverage.

**How to use it effectively:**
- Say "production is throwing 500s on checkout" — Claude runs the triage decision tree: identify source, fetch Sentry context, correlate to recent deploys, only then propose a fix.
- Say "did the last deploy cause this?" — it pulls Vercel deployment history and GitHub commits to correlate against the Sentry issue timeline.
- Say "check our error handling coverage" — it runs the validation scripts against Server Actions and React Query mutations to find silent-failure gaps before they hit production.

**Key insight:** This skill is the "respond to what Sentry told you" half of the pair. If you're writing the instrumentation itself (the try/catch, the span, the log line), that's `sentry-instrumentation` — this skill picks up once an alert has already fired.

### sentry-instrumentation

**When it activates:** You want to "add Sentry", "capture exception", "add tracing/spans", "instrument" an API call or user interaction, or "set up structured logging" in app code.

**What it knows:** Rhize's house conventions for the three pillars of Sentry instrumentation — `Sentry.captureException(error)` inside try/catch blocks, `Sentry.startSpan({ op, name }, ...)` for performance tracing on meaningful actions (clicks, API calls, nested operations), and `logger.fmt` template-literal structured logging with appropriate log levels (trace/debug/info/warn/error/fatal).

**How to use it effectively:**
- Say "add Sentry to this API route" — Claude wraps the risky operation in try/catch with `captureException`, rather than inventing an ad-hoc error-handling style.
- Say "add a span around this form submission" — it creates a `startSpan` with a descriptive `op` and `name` and attaches relevant attributes for later filtering in Sentry.
- Say "I need structured logs for this checkout flow" — it uses `logger.fmt` with variables rather than string concatenation, and picks an appropriate log level.

**Key insight:** This is the write-the-code companion to `error-lifecycle-management`, not a replacement for the official `sentry:*` plugin skills — for full per-framework SDK setup (installing the SDK, configuring `sentry.client.config.ts`, etc.) those official skills take over; this one is purely about Rhize's in-code instrumentation patterns once Sentry is already wired up.

### data-mutation-consistency

**When it activates:** You report "stale data", "not updating", "cache", "revalidate", "mutation", "optimistic update", "data is out of sync", "had to hard-refresh" — or when reviewing React Query, Server Actions, Payload hooks, or Sanity writes.

**What it knows:** How to keep cache tags (`revalidateTag`/`revalidatePath`) aligned with frontend query keys (React Query key factories) across Next.js + Vercel + Supabase/Sanity/Payload, a 0–10 scoring system for any given mutation (≥9.0 passing, 7.0–8.9 warning, <7.0 critical), sub-skills auto-detected from `package.json` for React Query mutations and Payload CMS lifecycle hooks, and cross-layer validation that catches a backend cache tag that doesn't match any frontend query key (the classic cause of "I had to hard-refresh to see my change").

**How to use it effectively:**
- Say "why isn't this update showing up without a refresh?" — Claude reasons about whether the mutation revalidates the right cache tag and whether the frontend query key factory actually matches it.
- Say "review this Server Action" or "check this mutation" — it scores the mutation against required elements (typed client, error handling, cache revalidation) and recommended ones (optimistic UI, rollback logic) via `/rhize-devflow:mutation-check`.
- This skill is advisory. `/rhize-devflow:mutation-check` reports gaps with a score, never edits source or adds a TODO comment — use `--fix-plan` for a proposed-changes report to apply yourself.

**Key insight:** The skill's real value is the *cross-layer* check — most mutation bugs aren't "forgot to revalidate," they're "revalidated tag X but the query key factory reads tag Y." That mismatch is invisible unless you're checking both sides at once.

### chrome-devtools-mcp

**When it activates:** You ask specifically about Chrome DevTools MCP tool names/parameters, connecting to a running Chrome instance, or MCP-level configuration/troubleshooting for that server. General "test in the browser" / "check performance" / "debug this page" requests go through `/rhize-devflow:browser-qa` instead — that command detects whichever browser capability is actually connected (Chrome DevTools MCP is one candidate, not an assumed default) and this skill supplies the DevTools-protocol mechanics only when that server is the active one.

**What it knows:** The Chrome DevTools Protocol tool surface via the official Puppeteer-backed MCP server — input automation (click, fill, drag, upload), navigation (multi-tab), performance tracing (Core Web Vitals — LCP, FID/INP, CLS), network inspection (request/response detail, CORS diagnosis), console/DOM debugging (screenshots, accessibility snapshots, arbitrary JS evaluation), and device emulation for responsive testing.

**How to use it effectively:**
- Ask "check the performance of my dashboard page" or "why is my login form failing silently" — these route through `/rhize-devflow:browser-qa`'s scenario list.
- Ask specifically "what's the Chrome DevTools MCP tool for X" or "why won't the DevTools MCP server connect" — this skill's own reference and troubleshooting docs take over.

**Key insight:** This is the mechanics layer behind one candidate implementation of `/rhize-devflow:browser-qa`, not a general browser-testing entry point — reach for `/rhize-devflow:browser-qa` for the acceptance workflow itself.

### sanity-development

**When it activates:** You're working in a Sanity codebase — writing or reviewing `defineType`/`defineField` schemas, GROQ/`defineQuery`, Studio structure, stega/visual editing, or a Sanity-powered Next.js frontend.

**What it knows:** Rhize's opinionated layer on top of Sanity's own best practices — model what things *are*, not what they *look like* (`heroStatement`, not `bigHeroText`); always use `defineType`/`defineField`/`defineArrayMember`; named exports only; `SCREAMING_SNAKE_CASE` for GROQ query constants; clean stega values with `stegaClean` before any logic comparison; prefer string-list fields over booleans and arrays over single references; never delete a field with production data (deprecate it instead); and the `defineLive` + `useCdn` rules for when to hit the CDN vs. bypass it (drafts, ISR webhooks, static-param generation always bypass).

**How to use it effectively:**
- Ask "create a schema for a testimonial" — it reaches for `defineType`/`defineField`, named exports, and a data-focused field name, not a presentation-focused one.
- Ask "write a GROQ query for published posts" — it produces an explicit projection (no `{ ... }` spreads), a `SCREAMING_SNAKE_CASE` constant name, and filters ordered so indexed fields (`_type`, `defined()`) run first.
- Ask "why isn't my draft content showing in preview?" — it checks whether the client is using `perspective: 'drafts'` with `useCdn: false`, since CDN reads never see unpublished content.

**Key insight:** This layers Rhize house style on top of the official `sanity:*` plugin — defer to that plugin for exhaustive API reference and version-specific docs; reach for this skill for the opinionated conventions (naming, boolean avoidance, error-handling pattern with safe fallbacks) that keep Sanity code consistent across Rhize projects.

## Commands Reference

### The control-plane sequence

#### /rhize-devflow:impact-map

**Usage:** `/rhize-devflow:impact-map` (no flags — describe the change in the prompt)

Maps a change before implementation, then reconciles the completed diff against the same
evidence. CodeGraph (when an existing healthy index is present) is authoritative for current
structural truth — symbols, callers, tests, dependency paths. The map itself is authoritative
for intended change — business behavior, invariants, planned symbols, operational effects, risks,
acceptance criteria. Requires a post-implementation `IN_SYNC`, `IN_SYNC_WITH_EXCEPTIONS`, or
blocking `OUT_OF_SYNC` verdict.

For material implementation/refactor/simplification prompts, the installed plugin now enforces this sequence.
It allows the plan to be written, then blocks source edits until the command's `prepare` step has
validated the persisted map, queried every existing healthy CodeGraph index (or recorded the
fallback), and read any component registry. After source changes begin, commit/push/merge and
normal completion remain blocked until `reconcile` returns `IN_SYNC` or
`IN_SYNC_WITH_EXCEPTIONS`. The receipt is shared between Claude and Codex.

**Examples:**
- "Map the impact of adding a `refundStatus` field to the order schema before I touch anything."
- "Reconcile the impact map against what actually changed" (after implementation).
- "Build a local context pack from this persisted impact map" (optional when
  `rhize-context-manager` is installed). The bridge passes the plan explicitly, records only
  hash/count provenance, preserves CodeGraph health semantics, and falls back to `rg` without
  initializing an index.

#### /rhize-devflow:check

**Usage:** `/rhize-devflow:check` (invoke mid-implementation, no flags)

Evidence-driven mid-implementation validation. Builds a deterministic evidence packet
(`devflow.py evidence --json`) — changed files, protected-file matches, declared package
scripts, package manager, impact-map status — then selects checks *only* from repository
instructions and known-safe declared package-script names (`test`, `lint`, `typecheck`, `build`,
`schema`, `codegen`). Never runs shell text parsed from a README, commit message, or generated
report. Runs focused tests first, then repository-mandated broader gates. Returns `PASS`,
`PASS_WITH_WARNINGS`, or `BLOCKED` with the exact evidence table.

**Examples:**
- "Run check — the failing test for refund calculation just started passing."
- "Check this before I pause for the day."

#### /rhize-devflow:simplify

**Usage:** `/rhize-devflow:simplify` followed by an optional range, file list, focus, or read-only
instruction. Run it after implementation and before the final `check`/`review` gates.

Reviews the exact task diff through reuse/consolidation, quality/correctness, and efficiency
lenses. A candidate lands only when it preserves product behavior and keeps authorization,
tenancy, audit, concurrency, accessibility, error, schema, and external-side-effect contracts at
least as strong. React/Next.js checks favor derived render values over mirrored state, Effects only
for external synchronization, narrow client boundaries, and evidence-backed memoization. It may
edit only when the surrounding request already authorizes edits; it never grants commit, push,
merge, deploy, migration, or external-write authority. A verified no-op is a successful outcome.

**Examples:**
- "Simplify the code from this task, apply only behavior-preserving improvements, and rerun the
  relevant tests."
- "Review `origin/dev..HEAD` for consolidation opportunities, but don't edit anything."
- "Check these React changes for redundant state or Effects before review."

#### /rhize-devflow:test-evidence

**Usage:** `/rhize-devflow:test-evidence` with one to three explicit regression claims and a local
run-spec boundary. Run it before `/review`, never from inside review.

The command classifies each claim, then uses an approved `test`/`test:*` package script and a
disposable worktree when isolated mutation is authorized. It refuses dirty or protected targets,
binds the packet to exact SHAs and file digests, restores and reruns clean state, and reports killed,
survived, missing-oracle, unavailable, stale, or cleanup-failed evidence precisely.

**Example:** "Run test evidence for the exact cache-key bug these two tests claim to prevent."

#### /rhize-devflow:review

**Usage:** `/rhize-devflow:review` (invoke before merge/push/release)

The read-only production merge/release gate — the executable successor to the retired
`rhize-review` workflow. Resolves the exact base/head comparison range from explicit intent and
Git evidence (never assumes the default branch is the merge target), builds a risk map across
deployment/data/security/authorization/billing/migration/cache/external-write categories from
actual diff evidence, routes only the specialist reviews that risk map calls for, and requires an
independent skeptical reviewer for any non-trivial change (a disclosed cold review if none is
available). Returns exactly one of `PASS`, `FAIL_WITH_FIXABLE_GAPS`, `FAIL_REQUIRES_HUMAN`. Never
commits, pushes, merges, or deploys. The actual ship step stays separate and is executed by
`completed-branch-promotion` only when the user or repository auto-push policy authorizes it.

**Examples:**
- "Review this before I merge to main — target branch is `dev`, per the repo's push policy."
- "Run review for the migration in this PR."

### Overlay commands

#### /rhize-devflow:mutation-check

**Usage:** `/rhize-devflow:mutation-check PATH...` | `--all [--focus <entity>]` | `--fix-plan [--priority P0|P1|P2] [--file <path>]`

Read-only data-mutation consistency check, replacing the former `mutation-analyze` /
`mutation-check` / `mutation-fix` split. `PATH...` is a fast scoped check with an inline score and
present/missing required elements; `--all` is a full-codebase sweep that writes a report to
`.claude/analysis/mutation-report-{date}.md`; `--fix-plan` writes a proposed-changes report to
`.claude/analysis/` without touching source. There is no `--add-todos`/`--apply` — this command
never edits files.

**Examples:**
- `/rhize-devflow:mutation-check app/actions/players.ts` right after editing it.
- `/rhize-devflow:mutation-check --all` for a full sweep before a release.
- `/rhize-devflow:mutation-check --fix-plan --priority P1` to get a fix plan after `--all` flags issues.

#### /rhize-devflow:browser-qa

**Usage:** `/rhize-devflow:browser-qa` (describe the URL/flow to exercise in the prompt)

One scenario-driven browser acceptance workflow, replacing the former `browser-help` /
`browser-debug` / `browser-perf` / `browser-test` split: functional path, console/network errors,
accessibility smoke, responsive layout (mobile/tablet/desktop presets), and performance (only on
request or when the change plausibly affects load/render). Detects whichever browser capability
is actually connected in the session rather than assuming a specific named MCP server, and
degrades explicitly (reports scenarios as unavailable, never fabricates a result) when none is
available.

**Examples:**
- "Run browser QA on `http://localhost:3000/checkout` after this form change."
- "Check performance on the dashboard page — I added a heavy chart component."

#### /rhize-devflow:devflow-setup

**Usage:** `/rhize-devflow:devflow-setup`

Interview-driven setup wizard that establishes the per-machine `.claude/*.local.md` tenant-file
convention — see the [README](./README.md#rhize-devflowdevflow-setup--local-tenant-file-convention)
for what the convention is.

**Examples:**
- "Set up the local tenant-file convention for this repo — new client project."

### Deprecated commands

`browser-debug`, `browser-help`, `browser-perf`, `browser-test`, `mutation-analyze`, and
`mutation-fix` are one-line deprecation adapters during the 2.12.0 compatibility window — invoking
one just tells you the canonical replacement rather than running any workflow itself. See the
[README's migration table](./README.md#migration-table) for the full old→new mapping. They will be
removed no earlier than Dev Flow 3.0.0.

## How the Skills and Commands Work Together

**The control-plane sequence is the backbone.** `/rhize-devflow:impact-map` maps a change before
implementation and reconciles it after; `/rhize-devflow:check` validates the in-progress work
against deterministic evidence; `/rhize-devflow:review` gates the actual merge/push/release
decision. Each stage expects the one before it to have already run, but none of the three commits,
pushes, or deploys. `completed-branch-promotion` owns that separate, explicitly authorized,
repository-governed action.

**Session lifecycle bookends live in the paired plugin:** `rhize-context-manager`'s `/start`,
`/done`, and `/context-hygiene` own session state. `/done` there delegates code-change review to
this plugin's `/rhize-devflow:review` when Dev Flow is installed and code changed this session —
otherwise it discloses a local fallback checklist rather than silently skipping review.

**Foundations feed the control-plane commands:** `dev-flow-foundations` is the reference layer,
not something you invoke directly — its dependency-graph pattern is exactly what
`/rhize-devflow:impact-map` executes, and its regression-prevention protocol (root cause before
fix) is what `error-lifecycle-management`'s triage workflow follows.

**Instrumentation feeds triage:** `sentry-instrumentation` is how the code gets Sentry coverage in
the first place (captureException, spans, structured logs); `error-lifecycle-management` is what
runs once one of those instrumented errors actually fires in production, correlating it against
Vercel deploys and GitHub commits.

**Mutation and browser overlays sit alongside the spine:** `/rhize-devflow:mutation-check` and
`/rhize-devflow:browser-qa` are scenario-driven acceptance checks you reach for during
implementation or as part of `/rhize-devflow:check`'s broader validation — not replacements for
it. `data-mutation-consistency` and `chrome-devtools-mcp` are the reference knowledge behind each.

**Test evidence is a separate pre-review lane:** use `/rhize-devflow:test-evidence` when changed
tests claim to prevent a regression. It distinguishes observable behavior from exact artifact and
structural contracts, then binds independent-oracle or isolated mutation results to the exact Git
state. `/review` only validates that local packet and never runs a mutant. This is intentionally
separate from `/mutation-check`, which audits cache and data-write consistency.

**Sanity development stands alongside, not inside:** `sanity-development` doesn't feed a slash
command in this plugin — it's pure reference knowledge Claude applies automatically whenever
you're editing schema or GROQ files in a Sanity codebase, the same way `sentry-instrumentation`
applies automatically when you're adding error tracking.

## Tips for Getting the Best Results

**Run `/rhize-devflow:impact-map` before touching code on anything non-trivial.** The default-on
gate now enforces that rule for explicit material-change prompts. If it classifies a genuinely
read-only task incorrectly, use the printed `dismiss --reason` command so the exception remains
reviewable; do not disable the gate silently.

**Use `/rhize-devflow:check` as a habit, not a one-time gate.** It's fast enough — evidence-driven,
no arbitrary command execution — to run every time a meaningful unit of change lands, not just
right before `/rhize-devflow:review`.

**Don't skip `/rhize-devflow:review` because `check` passed.** A green `check` is necessary but
not sufficient — it validates the in-progress change, not the shippability of the diff as a whole.
`review`'s independent-reviewer requirement exists specifically because the session that authored
a change is a bad judge of its own work.

**Mention the platform when it matters for mutation work.** "Check this mutation" triggers a
generic pass; "check this Payload afterChange hook" or "check this React Query mutation" lets the
skill apply the sub-skill-specific checks (Payload's `afterDelete` cache invalidation vs. React
Query's rollback context) instead of only the generic ones.

**Pair `/rhize-devflow:browser-qa` with a running Sentry investigation.** If
`error-lifecycle-management` surfaces a client-side error, running browser QA on the same
URL/action is usually the fastest way to reproduce it live and see the console/network state
Sentry's stack trace alone doesn't show you.

**Be specific about viewport and device for browser QA's responsive scenario.** The default
presets (mobile/tablet/desktop) cover the common case; name an exact width/height if you need
something else.

## Troubleshooting

**A command or skill is missing after install/update:** Run `/rhize-devflow:doctor` (thin
adapter over `python3 "$CLAUDE_PLUGIN_ROOT/scripts/devflow.py" doctor`) — it validates
manifests, canonical commands, referenced assets, duplicate bodies, stale tokens, and
capability dependencies, and names exactly what's wrong instead of leaving you to guess.
Anything other than `HEALTHY` (plus
informational findings) means the plugin cache is stale — re-run
`claude plugin marketplace update rhize-plugins` then `claude plugin update rhize-devflow`, then
start a fresh session.

**`/rhize-devflow:check` reports a gate as skipped/unavailable when you expected it to run:** It
only selects checks from repository instructions (`CLAUDE.md`/`AGENTS.md`) and known-safe declared
package-script names — if the script isn't declared under one of those safe names, or the
repository doesn't require it, `check` reports it as unavailable rather than guessing at a command
from a README or comment. Declare the gate explicitly in the repository's own instructions or
`package.json` if it should always run.

**`/rhize-devflow:review` asks you to confirm the target branch:** This happens when base
resolution came from a guess (default-branch fallback) rather than an explicit signal (a stated
PR/branch or a tracked upstream) — name the actual target branch or PR and re-run rather than
letting it guess, since the wrong base silently narrows or widens the diff under review.

**`/rhize-devflow:review` reports no independent reviewer ran:** This is disclosed, not hidden —
check the output for which limitation applies. A disclosed cold review still happened; it's
weaker than a genuinely independent pass, not a skipped step.

**Browser commands fail or hang:** The active browser capability isn't installed or isn't running.
For Chrome DevTools MCP specifically: install with
`claude mcp add --scope user chrome-devtools npx chrome-devtools-mcp@latest`, then re-run
`/rhize-devflow:browser-qa` — it detects the connected tool rather than assuming one.

**"Element not found" during `/rhize-devflow:browser-qa`:** The page hadn't finished rendering
before the action ran. Ask Claude to wait on the target selector before the click/fill — this is
the single most common cause per the underlying tool's own troubleshooting notes.

**Screenshots come back blank:** Usually a GPU/headless rendering issue. Try adding `--disable-gpu`
to the Chrome launch args, or drop `--headless` for a visible browser window if you're debugging
locally.

**`/rhize-devflow:mutation-check` reports a low score but the app "works fine":** A passing score
isn't about whether the happy path works today — it's about whether the mutation is guaranteed to
keep the cache and UI in sync under retries, concurrent edits, or partial failures. Treat the
report as a leading indicator, not a false alarm.

**Mutation fix plan references a cache tag you don't recognize:** Check whether a query-key
factory was renamed on one side (frontend) but not the other (backend `revalidateTag`) — this
exact drift is what the cross-layer validation is built to catch, and it's usually the actual root
cause of "I had to hard-refresh."

**`rhize-context-manager`'s `/done` runs a local fallback instead of delegating to review:**
Expected when Dev Flow isn't installed, or no code changed this session — it discloses the
fallback explicitly rather than silently skipping independent review. Install `rhize-devflow` if
you expected delegation to happen.

**Sanity schema or query changes aren't reflected in TypeScript types:** Run the typegen workflow (`sanity schema extract` then `sanity typegen generate`), and if VS Code still shows stale types, restart the TS server (Cmd+Shift+P → "TypeScript: Restart TS Server").

**Sentry captures fire in code but nothing shows up in the dashboard:** This skill only covers in-code instrumentation conventions, not SDK setup — check `enableLogs: true` is set in your Sentry init (required for `logger.fmt` calls to actually ship), and if the issue is initialization itself, defer to the official `sentry:*` skills for full SDK configuration.

**Heavier guard hooks (prewrite mutation check, protect-files, mutation/sentry-stale-data suggesters) don't seem to be running:** They're opt-in by design — all four ship under `hooks/` but nothing is auto-wired. See the README's Hooks section (or `setup/manifest.json`, which the `/rhize-setup` wizard in `rhize-ops` reads) for the full list and exact commands, and wire in the ones you want per-project rather than expecting them to fire out of the box.
