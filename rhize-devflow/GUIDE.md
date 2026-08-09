# rhize-devflow Plugin — User Guide

This guide explains what the rhize-devflow plugin does, how its pieces fit together, and how to get the most out of it while building on Next.js/Sanity/Payload/Supabase stacks deployed on Vercel.

## What This Plugin Does

rhize-devflow teaches Claude the production-grade development discipline Rhize expects on real client projects: how to run a session without losing context, how to triage and root-cause a production error, how to keep cache tags and query keys from drifting apart, how to instrument code with Sentry the Rhize way, how to drive a real browser for debugging and performance work, and how to write Sanity schemas and GROQ queries in house style.

It's for developers (and Claude, acting as one) who are shipping to production — not prototyping in a vacuum. The plugin assumes real stakes: a stale cache means a client sees wrong data, an uninstrumented error means nobody finds out until a user complains, and a context-exhausted session means work gets redone. Every skill here exists to prevent one of those failure modes.

The plugin has two kinds of components:

**Skills** are reference knowledge Claude loads automatically when your request matches certain trigger phrases. You don't invoke them directly — Claude reads them behind the scenes to produce better output.

**Commands** are actions you invoke explicitly with a slash prefix (e.g., `/rhize-devflow:mutation-check`). They drive a specific workflow, usually combining several skills and real tool calls (git, build commands, browser automation, subagents).

## Quick Mental Model

Seven skills, but they cluster into four jobs:

| Cluster | Skills | Question it answers |
|---------|--------|----------------------|
| **Session & context hygiene** | `dev-flow-foundations` (session/context engineering itself now lives in the `rhize-context-manager` plugin) | "Where were we, what already exists, and is this session getting too heavy?" |
| **Production errors** | `error-lifecycle-management`, `sentry-instrumentation` | "How do I instrument this so I find out when it breaks, and how do I triage it once it does?" |
| **Data-mutation consistency** | `data-mutation-consistency` | "Will this mutation leave the cache and the UI in sync, or will someone have to hard-refresh?" |
| **Browser debugging** | `chrome-devtools-mcp` | "What does this actually look like/do in a real browser — network, console, performance, visuals?" |
| **CMS house style** | `sanity-development` | "What's the Rhize-opinionated way to model this in Sanity?" |

Commands are the hands-on-keyboard layer built on top of these skills — `/start` and `/done` bookend a session, `/impact-map` and `/context-hygiene` keep it clean mid-session, `/mutation-*` commands drive the data-mutation skill, and `/browser-*` commands drive the Chrome DevTools skill.

## Skills Reference

### dev-flow-foundations

**When it activates:** You mention "design patterns", "workflow optimization", "prevent regression", "anti-patterns", "dependency mapping", "component registry", "why did this break again", or want to set up durable development guardrails.

**What it knows:** Six foundational workflow problems and their fixes — dependency-graph impact mapping ("what uses this?" before "how do I change this?"), a component/function registry to stop duplicate components from being built, context hygiene principles (CLAUDE.md as a <200-line router, not an essay), regression prevention (root-cause first, never patch blind), anti-pattern detection at write-time rather than at review, and a skill-refinement pattern for turning a repeated fix into a formal skill.

**How to use it effectively:**
- Ask "before I build this, what already touches this area?" — it reasons from the dependency-graph pattern rather than jumping straight to code.
- Ask "why does this keep breaking every time we touch it?" — it applies the regression-prevention protocol: root cause before fix, test before deploy.
- This is the reference layer, not a command surface — its patterns show up concretely inside the `rhize-context-manager` plugin's `context-engineering` skill (which implements the registry and dependency-graph ideas as `/rhize-context-manager:impact-map` and the duplicate-check hook) and inside `error-lifecycle-management` (which implements regression prevention as the triage workflow).

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
- Say "review this Server Action" or "check this mutation" — it scores the mutation against required elements (typed client, error handling, cache revalidation) and recommended ones (optimistic UI, rollback logic).
- This skill is advisory, not blocking — it will flag gaps with a score and a TODO comment and let you keep moving, rather than stopping implementation cold.

**Key insight:** The skill's real value is the *cross-layer* check — most mutation bugs aren't "forgot to revalidate," they're "revalidated tag X but the query key factory reads tag Y." That mismatch is invisible unless you're checking both sides at once.

### chrome-devtools-mcp

**When it activates:** You want to "test in browser", "check performance", "debug network", "take a screenshot", "fill a form", inspect "console errors", "inspect the page", "automate the browser", diagnose "CORS issues", or run a "lighthouse audit" — including on Next.js/Sanity/Payload preview URLs.

**What it knows:** The full Chrome DevTools Protocol tool surface via the official Puppeteer-backed MCP server — input automation (click, fill, drag, upload), navigation (multi-tab), performance tracing (Core Web Vitals — LCP, FID/INP, CLS), network inspection (request/response detail, CORS diagnosis), console/DOM debugging (screenshots, accessibility snapshots, arbitrary JS evaluation), and device emulation for responsive testing.

**How to use it effectively:**
- Ask "check the performance of my dashboard page" — it navigates, starts a trace, and comes back with Core Web Vitals plus specific render-blocking resources, not just a pass/fail.
- Ask "why is my login form failing silently?" — it navigates, fills and submits the form, then inspects both network requests (auth headers, response bodies) and console errors together.
- Ask "show me this page at mobile, tablet, and desktop" — it emulates each viewport and screenshots all three so you can compare layouts in one pass.

**Key insight:** This pairs with `gsd-browser-harness` — prefer this skill specifically when you need DevTools-protocol-level performance and network introspection (traces, waterfalls, CORS headers), not just generic browser automation.

### sanity-development

**When it activates:** You're working in a Sanity codebase — writing or reviewing `defineType`/`defineField` schemas, GROQ/`defineQuery`, Studio structure, stega/visual editing, or a Sanity-powered Next.js frontend.

**What it knows:** Rhize's opinionated layer on top of Sanity's own best practices — model what things *are*, not what they *look like* (`heroStatement`, not `bigHeroText`); always use `defineType`/`defineField`/`defineArrayMember`; named exports only; `SCREAMING_SNAKE_CASE` for GROQ query constants; clean stega values with `stegaClean` before any logic comparison; prefer string-list fields over booleans and arrays over single references; never delete a field with production data (deprecate it instead); and the `defineLive` + `useCdn` rules for when to hit the CDN vs. bypass it (drafts, ISR webhooks, static-param generation always bypass).

**How to use it effectively:**
- Ask "create a schema for a testimonial" — it reaches for `defineType`/`defineField`, named exports, and a data-focused field name, not a presentation-focused one.
- Ask "write a GROQ query for published posts" — it produces an explicit projection (no `{ ... }` spreads), a `SCREAMING_SNAKE_CASE` constant name, and filters ordered so indexed fields (`_type`, `defined()`) run first.
- Ask "why isn't my draft content showing in preview?" — it checks whether the client is using `perspective: 'drafts'` with `useCdn: false`, since CDN reads never see unpublished content.

**Key insight:** This layers Rhize house style on top of the official `sanity:*` plugin — defer to that plugin for exhaustive API reference and version-specific docs; reach for this skill for the opinionated conventions (naming, boolean avoidance, error-handling pattern with safe fallbacks) that keep Sanity code consistent across Rhize projects.

## Commands Reference

> **Moved:** the session & context commands (`/rhize-devflow:start`, `/rhize-devflow:done`,
> `/rhize-devflow:context-hygiene`, `/rhize-devflow:impact-map`) now live in the
> `rhize-context-manager` plugin as `/rhize-context-manager:start`, `/rhize-context-manager:done`,
> `/rhize-context-manager:context-hygiene`, and `/rhize-context-manager:impact-map`.

### Data-mutation commands

#### /rhize-devflow:mutation-analyze

**Usage:** `/rhize-devflow:mutation-analyze [--focus table|entity]`

Full codebase scan for mutation patterns. Detects which sub-skill applies (React Query, Payload CMS) from `package.json`, scores every mutation found, cross-checks that backend cache tags match frontend query keys, and writes a detailed report to `.claude/analysis/mutation-report-{date}.md` while keeping the chat summary to a few lines.

**Examples:**
- `/rhize-devflow:mutation-analyze` for a full sweep before a release
- `/rhize-devflow:mutation-analyze --focus players` when you suspect one entity/table specifically

#### /rhize-devflow:mutation-check

**Usage:** `/rhize-devflow:mutation-check <file>`

Quick single-file check — no report file, just an inline score and a list of present/missing required elements (error handling, cache revalidation, type safety, and category-specific checks for React Query or Payload).

**Examples:**
- `/rhize-devflow:mutation-check app/actions/players.ts` right before committing a mutation
- `/rhize-devflow:mutation-check hooks/useUpdatePlayer.ts` right after editing it

#### /rhize-devflow:mutation-fix

**Usage:** `/rhize-devflow:mutation-fix [P0|P1|P2] [--file <path>] [--add-todos]`

Generates a concrete fix plan from a prior analysis (or runs a fresh one), filtered by priority — P0 is critical-only, P1 (the default) is critical + warnings, P2 is everything. Can write a fix-plan file or add inline `TODO(mutation-consistency)` comments directly to the source for incremental fixing.

**Examples:**
- `/rhize-devflow:mutation-fix P1` after `/rhize-devflow:mutation-analyze` flags issues
- `/rhize-devflow:mutation-fix --file app/actions/players.ts` to scope the fix plan to one file
- `/rhize-devflow:mutation-fix --add-todos P1` to mark issues in place rather than generate a separate plan doc

### Browser commands

#### /rhize-devflow:browser-perf

**Usage:** `/rhize-devflow:browser-perf [url] [--mobile]`

Records a Chrome DevTools performance trace against a URL and reports Core Web Vitals (LCP, FID/INP, CLS) against target thresholds, plus specific render-blocking resources and unused-JS findings.

**Examples:**
- `/rhize-devflow:browser-perf http://localhost:3000/dashboard`
- `/rhize-devflow:browser-perf --mobile http://localhost:3000` to check mobile performance specifically

#### /rhize-devflow:browser-debug

**Usage:** `/rhize-devflow:browser-debug [url] [--action "click submit"]`

Navigates to a URL (optionally performing an action first), then lists network requests with failures called out, console errors/warnings, and CORS issues — with full request/response detail on anything that failed.

**Examples:**
- `/rhize-devflow:browser-debug http://localhost:3000/checkout`
- `/rhize-devflow:browser-debug --action "click submit" http://localhost:3000/form`

#### /rhize-devflow:browser-test

**Usage:** `/rhize-devflow:browser-test [url] [--responsive] [--form "field=value,..."]`

Visual and functional testing. Default mode screenshots the page and checks for console errors; `--responsive` screenshots mobile/tablet/desktop and flags layout issues; `--form` fills and submits a form and verifies the result (redirect, success message, no console errors).

**Examples:**
- `/rhize-devflow:browser-test http://localhost:3000/pricing`
- `/rhize-devflow:browser-test --responsive http://localhost:3000`
- `/rhize-devflow:browser-test --form "email=test@test.com,password=Test123" http://localhost:3000/login`

#### /rhize-devflow:browser-help

**Usage:** `/rhize-devflow:browser-help`

Quick reference card for the other three browser commands, the full MCP tool list, installation/configuration snippets, and a troubleshooting table. Reach for this when you've forgotten the exact flag or tool name rather than re-deriving it.

## How the Skills and Commands Work Together

**Session lifecycle bookends now live elsewhere:** the `context-engineering` skill and its `/start`/`/done`/`/context-hygiene`/`/impact-map` bookend commands moved to the `rhize-context-manager` plugin (`/rhize-context-manager:start`, `/rhize-context-manager:done`, etc.). `dev-flow-foundations` remains here in rhize-devflow.

**Foundations feed the commands:** `dev-flow-foundations` is the reference layer, not something you invoke directly — its dependency-graph and component-registry patterns are what `rhize-context-manager`'s `/rhize-context-manager:impact-map` command actually executes, and its regression-prevention protocol (root cause before fix) is what `error-lifecycle-management`'s triage workflow follows.

**Instrumentation feeds triage:** `sentry-instrumentation` is how the code gets Sentry coverage in the first place (captureException, spans, structured logs); `error-lifecycle-management` is what runs once one of those instrumented errors actually fires in production, correlating it against Vercel deploys and GitHub commits.

**Mutation analyze → check → fix is a pipeline:** `/rhize-devflow:mutation-analyze` finds the issues across the codebase, `/rhize-devflow:mutation-check` lets you spot-check a single file (before committing, or after editing), and `/rhize-devflow:mutation-fix` turns flagged issues into an actual fix plan or inline TODOs. Re-run `/rhize-devflow:mutation-analyze` after applying fixes to confirm the score improved.

**Chrome DevTools feeds all three browser commands:** `chrome-devtools-mcp` is the underlying tool knowledge; `/rhize-devflow:browser-perf`, `/rhize-devflow:browser-debug`, and `/rhize-devflow:browser-test` are three different lenses on the same MCP server — performance tracing, network/console debugging, and visual/form testing, respectively. `/rhize-devflow:browser-help` is the cheat sheet that ties them together when you need a reminder of which one does what.

**Sanity development stands alongside, not inside:** `sanity-development` doesn't feed a slash command in this plugin — it's pure reference knowledge Claude applies automatically whenever you're editing schema or GROQ files in a Sanity codebase, the same way `sentry-instrumentation` applies automatically when you're adding error tracking.

## Tips for Getting the Best Results

**Run `/rhize-context-manager:start` even for a "quick fix."** The whole point of `STATE.md` is that a five-minute fix six months from now shouldn't require re-discovering context that was already captured. Skipping `/start` on "small" sessions is how that discipline erodes. (This command now lives in the `rhize-context-manager` plugin.)

**Don't skip `/rhize-context-manager:done` because the build passed.** A green build is necessary but not sufficient — the verifier subagent exists specifically because the maker (Claude, in this session) is a bad judge of its own work. A FAIL_REQUIRES_HUMAN verdict is meant to stop a commit, not get worked around. (This command now lives in the `rhize-context-manager` plugin; the bundled `agents/verifier.md` it delegates to still lives here in rhize-devflow.)

**Mention the platform when it matters for mutation work.** "Check this mutation" triggers a generic pass; "check this Payload afterChange hook" or "check this React Query mutation" lets the skill apply the sub-skill-specific checks (Payload's `afterDelete` cache invalidation vs. React Query's rollback context) instead of only the generic ones.

**Use `/rhize-devflow:mutation-check` right after editing, not just before committing.** It's fast enough (no file output, no full-codebase scan) to run as a habit every time you touch a Server Action or mutation hook.

**Pair browser commands with a running Sentry investigation.** If `error-lifecycle-management` surfaces a client-side error, `/rhize-devflow:browser-debug` on the same URL/action is usually the fastest way to reproduce it live and see the console/network state Sentry's stack trace alone doesn't show you.

**Be specific about viewport and device for browser-test.** "`--responsive`" gives you the three standard breakpoints; if you need something else, name the exact width/height and it'll emulate that instead of guessing.

## Troubleshooting

**Browser commands fail or hang:** The Chrome DevTools MCP server isn't installed or isn't running. Install with `claude mcp add --scope user chrome-devtools npx chrome-devtools-mcp@latest`, then verify with `/rhize-devflow:browser-help` which lists the install/verify steps.

**"Element not found" during `/rhize-devflow:browser-test` or `/rhize-devflow:browser-debug`:** The page hadn't finished rendering before the action ran. Ask Claude to add a `wait_for` on the target selector before the click/fill — this is the single most common cause per the skill's own troubleshooting table.

**Screenshots come back blank:** Usually a GPU/headless rendering issue. Try adding `--disable-gpu` to the Chrome launch args, or drop `--headless` for a visible browser window if you're debugging locally.

**`/rhize-devflow:mutation-analyze` reports a low score but the app "works fine":** A passing score isn't about whether the happy path works today — it's about whether the mutation is guaranteed to keep the cache and UI in sync under retries, concurrent edits, or partial failures. Treat the report as a leading indicator, not a false alarm.

**Mutation fix plan references a cache tag you don't recognize:** Check whether a query-key factory was renamed on one side (frontend) but not the other (backend `revalidateTag`) — this exact drift is what the cross-layer validation is built to catch, and it's usually the actual root cause of "I had to hard-refresh."

**`/rhize-context-manager:done` can't find a verifier subagent:** Confirm `agents/verifier.md` exists (either the global `~/.claude/agents/verifier.md` or the copy bundled in this plugin). If genuinely unavailable, the command falls back to performing the same checks (diff review, build, STATE.md update) explicitly and should say so rather than silently skipping verification.

**Sanity schema or query changes aren't reflected in TypeScript types:** Run the typegen workflow (`sanity schema extract` then `sanity typegen generate`), and if VS Code still shows stale types, restart the TS server (Cmd+Shift+P → "TypeScript: Restart TS Server").

**Sentry captures fire in code but nothing shows up in the dashboard:** This skill only covers in-code instrumentation conventions, not SDK setup — check `enableLogs: true` is set in your Sentry init (required for `logger.fmt` calls to actually ship), and if the issue is initialization itself, defer to the official `sentry:*` skills for full SDK configuration.

**Heavier guard hooks (prewrite mutation check, protect-files, mutation/sentry-stale-data suggesters) don't seem to be running:** They're opt-in by design — all four ship under `hooks/` but only the lightweight SessionStart banner in `hooks/hooks.json` is auto-wired. See the README's Hooks section (or `setup/manifest.json`, which the `/rhize-setup` wizard in `rhize-ops` reads) for the full list and exact commands, and wire in the ones you want per-project rather than expecting them to fire out of the box. (The context-engineering guard hooks — duplicate-check, pre-commit-guard, session-init, skill-suggester — and the skill/session refinement suggesters now live in the `rhize-context-manager` plugin, not here.)
