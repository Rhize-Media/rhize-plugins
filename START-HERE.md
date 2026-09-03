# Start Here

New to this repository? Read this page first — it explains what's here in plain language, which
plugins to install for your situation, and how all the different files you'll run into fit
together. Everything here links out to more detail; nothing here is the deep reference.

## 1. What this is

This is a marketplace of Claude Code and Codex plugins built by Rhize Media. A plugin is a
packaged set of instructions and small tools that teach Claude how to do something specific well
— write SEO-optimized content, plan a software feature safely, manage an Obsidian vault, hand off
work to a teammate, and more. You install the plugins you need, and from then on Claude reaches
for the right one automatically when your request matches it, or you run it explicitly with a
slash command.

## 2. The plugins, in plain words

<!--
  The paragraphs below are hand-written for a first-time reader. They are a different artifact
  from the one-line `description` field each plugin carries in its plugin.json/marketplace.json
  (those exist for Claude's own plugin listing and this repo's generated tables) — if the two
  ever say something different, trust neither over the plugin's own GUIDE.
-->

### Knowledge & Context

**obsidian-second-brain** — for anyone who keeps their notes, research, and knowledge base in
[Obsidian](https://obsidian.md). Teaches Claude to read, write, organize, and search your vault:
proper note formatting, database-style views, visual canvases, web clipping, and vault health
checks. Reach for it whenever you want Claude to touch your notes instead of just talking about
them. Start with → [GUIDE](./obsidian-second-brain/GUIDE.md).

**rhize-context-manager** — for anyone running long or complex Claude sessions where context fills
up, the same fact gets repeated, or you're not sure which memory tool is actually helping. Gives
Claude one legible view across every context/memory layer running on your machine, health-checks
it, and routes new knowledge to the right place. Reach for it when a session feels sluggish or
confused. Start with → [GUIDE](./rhize-context-manager/GUIDE.md).

**procedural-memory** — for developers who keep re-solving the same small problem (a deploy guard,
a data conversion script, a tagging routine). Lets Claude find and re-run a previously verified
script instead of writing it from scratch again, with safety checks on what it's allowed to touch.
Reach for it before asking Claude to build a one-off script for something you suspect has already
been solved. Start with → [GUIDE](./procedural-memory/GUIDE.md).

### Operations

**rhize-core** ⭐ — the **hub plugin everyone should install first** (see
[§3](#3-which-should-i-install)). It is the setup wizard (`/rhize-core:setup`) that finds the Rhize
plugins you have installed, runs each one's own setup, and wires the optional hooks you choose — and
nothing else: no skills of its own, run once per project and again after upgrades. Start with →
[GUIDE](./rhize-core/GUIDE.md).

**rhize-ops** — Rhize Media's internal operations toolkit. For anyone who delegates work,
wants visibility into which skills are actually earning their keep, or runs several Claude agents
in parallel and wants that done safely. Reach for it when handing a task to a teammate, checking
skill usage, or coordinating parallel agent work. Start with → [GUIDE](./rhize-ops/GUIDE.md).

**rhize-tasks** — for anyone juggling approved Jira tickets against their own calendar, on a Mac.
Turns your Jira work into a realistic daily plan: it blocks focus time on one dedicated Google
Calendar and creates matching entries in Apple Reminders, without ever treating your personal
calendar as Rhize's to schedule. Reach for it when you want one honest answer to "what should I
work on now?" Start with → [GUIDE](./rhize-tasks/GUIDE.md).

### Engineering & Delivery

**rhize-devflow** — Rhize's engineering workflow for shipping to production: plan a change, build
it, test it, and get it independently reviewed before it ships. For developers (and Claude, acting
as one) working on real Next.js/Sanity/Vercel applications with real stakes, not a prototype.
Reach for it any time you're touching code that's going to production. Start with →
[GUIDE](./rhize-devflow/GUIDE.md).

**project-launcher** — for anyone starting a new project — an automation, a web app, an
integration — who wants the research, requirements, and planning done properly instead of
reinvented each time. Takes an idea through research, a requirements interview, a written plan you
review and approve, and a scaffolded project folder ready for autonomous development. Reach for it
the moment an idea is more than a one-off script. Start with → [GUIDE](./project-launcher/GUIDE.md).

**rhize-cowork** — for anyone kicking off a new Cowork project, internal or client. Stands up four
starter files (business info, voice and tone, key facts, operating rules) in one session so
Claude's very first draft for that project is already on-brand instead of generic. Reach for it
before any other work starts on a new client or project. Start with →
[GUIDE](./rhize-cowork/GUIDE.md).

### Content Intelligence

**seo-aeo-geo** — for SEO practitioners, content teams, marketers, and developers who need to
know how a site is actually performing in search and in AI answers. Audits site health, researches
keywords, analyzes backlinks, tracks rankings, optimizes content, and checks whether AI systems
like ChatGPT and Google AI Overviews are citing you — all backed by live data, not guesswork.
Reach for it for any SEO, AEO, or GEO question about a real site. Start with →
[GUIDE](./seo-aeo-geo/GUIDE.md).

### Toolchain

**@rhize/skill-forge** — not a plugin in this marketplace; a separate npm command-line tool
(`Rhize-Media/skill-forge`) that several plugins here depend on for curating and refining skills
(checking a skill against upstream for drift, scanning a candidate skill for safety issues before
it's added). You don't install it as a plugin — some plugins' commands will tell you to run
`npx @rhize/skill-forge <command>` when they need it. Start with →
`npx @rhize/skill-forge --help`.

## 3. Which should I install?

**rhize-core is the hub:** it's the only plugin that ships the setup wizard
(`/rhize-core:setup`) able to wire every other plugin's *optional* hooks and dependencies
into your project — without it, those hooks stay documentation-only and you'd have to hand-edit
`.claude/settings.json` yourself. Every plugin still installs and works without it; you'd just be
doing setup by hand. Install it first, regardless of which profile below fits you. (Already have
rhize-ops? `/rhize-ops:rhize-setup` keeps working for one release and simply forwards to it.)

| Profile | Recommended set |
| --- | --- |
| **Solo developer** — building your own projects | rhize-core, rhize-ops, rhize-devflow, rhize-context-manager. Add obsidian-second-brain if you keep notes in Obsidian, and project-launcher when an idea is ready to become a real project. |
| **Client engineering team** — shipping software for clients | rhize-core, rhize-ops, rhize-devflow, rhize-context-manager, project-launcher, rhize-cowork (client kickoff), and rhize-tasks if the team plans work off Jira. |
| **Content / SEO team** — auditing and optimizing sites, no code shipping | rhize-core, seo-aeo-geo, and obsidian-second-brain if research and reports live in a vault. |

procedural-memory and `@rhize/skill-forge` are power-user tools — add them once you notice the
specific need (repeated one-off scripts, or wanting to check a skill for upstream drift) rather
than as part of a starting set.

## 4. How the pieces fit — the context-file architecture

Every plugin in this repo follows the same file layout, so once you understand the layers below
you understand all of them. Two terms used throughout: a **skill** is reference knowledge Claude
loads on its own when what you ask matches it — you never type its name; a **command** is an
action you run explicitly by typing `/plugin-name:command-name`.

| Layer | What it is | Who edits it | Where it lives | Tracked in Git? | Read more |
| --- | --- | --- | --- | --- | --- |
| Your global instructions | Standing instructions that apply to every project you work in, on this machine | You | `~/.claude/CLAUDE.md` | Only if you put `~/.claude` under its own Git repo | — |
| Project instructions | Standing instructions specific to one project/repo | You | `CLAUDE.md` at the project root | Yes, with the project | — |
| Plugin docs for you | Human-readable documentation — the README is setup and technical reference, the GUIDE is the day-to-day walkthrough | The plugin's maintainer | `<plugin>/README.md`, `<plugin>/GUIDE.md` | Yes | [Documentation Hierarchy](./README.md#documentation-hierarchy) |
| Plugin instructions for Claude | The actual instructions a skill or command executes | The plugin's maintainer | Skills: `<plugin>/skills/*/SKILL.md` (triggered automatically by what you ask). Commands: `<plugin>/commands/*.md` (run by typing `/plugin:command`) | Yes | [Documentation Hierarchy](./README.md#documentation-hierarchy) |
| Hooks | Small scripts the harness runs automatically before or after a tool call — e.g. to block a risky edit or log an event | The plugin's maintainer (auto-wired hooks); you, via the setup wizard (optional/opt-in hooks) | Declared in `<plugin>/hooks/hooks.json` (auto-wired) or `<plugin>/setup/manifest.json` (opt-in); optional guardrail hooks get wired into your project's `.claude/settings.json` by `/rhize-ops:rhize-setup` | The declarations are yes; what gets wired into *your* project's `.claude/settings.json` is your project's own file | [rhize-ops README § Setup manifest schema](./rhize-core/README.md#setup-manifest-schema) |
| Private/local files | Content specific to one installer or tenant that should never be hardcoded into a shared skill | You, usually via a setup wizard | Durable personal config: `~/.claude/<plugin>/...`. Disposable repo-local reference material: `.claude/*.local.md` inside a project | No — both paths are gitignored | [README § Progressive disclosure](./README.md#progressive-disclosure) |
| Derived state | Generated artifacts a plugin reads or writes at runtime — caches, receipts, indexes | The plugin itself, automatically | `~/.rhize/`, `~/.claude/context-manager/`, `~/.skill-forge/`, `~/Library/Application Support/Rhize Tasks/` | No | — |

## 5. Setting up

1. Install `rhize-core` from this marketplace (see the root [README's Quick Start](./README.md#quick-start) for the exact install command for your host).
2. Run `/rhize-core:setup`. It asks which of your installed plugins to set up (all of them by
   default), checks their dependencies once, checks whether the files it is about to change are
   under version control and offers to track them, hands off to each selected plugin's own setup
   wizard, then wires the optional guardrail hooks you pick into your project — and ends with a
   report of what was written where and how to look at it. Each plugin's wizard also runs on its
   own if you only want that one.
3. Follow each plugin's own README Setup/Install section for anything the wizard doesn't cover
   (API credentials, external CLIs): [rhize-core](./rhize-core/README.md#setup) ·
   [seo-aeo-geo](./seo-aeo-geo/README.md#setup) ·
   [obsidian-second-brain](./obsidian-second-brain/README.md#setup) ·
   [project-launcher](./project-launcher/README.md#setup) ·
   [rhize-devflow](./rhize-devflow/README.md#install) ·
   [rhize-context-manager](./rhize-context-manager/README.md#install) ·
   [rhize-ops](./rhize-ops/README.md#setup) ·
   [rhize-tasks](./rhize-tasks/README.md#install) ·
   [rhize-cowork](./rhize-cowork/README.md#setup) ·
   [procedural-memory](./procedural-memory/README.md#setup).

**What setup writes, and where to look:** every plugin declares the files it creates in its setup
manifest, and [`rhize-core/docs/setup-artifacts.md`](./rhize-core/docs/setup-artifacts.md) is the
rendered list — path, purpose, how to view it, how long it lives, how sensitive it is, and whether
it is tracked in Git.

## 6. Rolling back

Git is the rollback for almost everything a plugin writes into your project or your home config —
commit before you run a setup wizard, and `git diff`/`git checkout` gets you back. The one
exception is a skill refinement applied by skill-forge, which has its own undo:
`skill-forge refine rollback <backup-id>`. See
[rhize-core README § Rollback](./rhize-core/README.md#rollback) for the full recipe, including how
to check what's tracked before you commit.

## 7. Glossary

| Term | Meaning |
| --- | --- |
| AEO | Answer Engine Optimization — making content easy for AI answer engines (ChatGPT, Perplexity) to cite. |
| GEO | Generative Engine Optimization — making content show up in AI-generated search summaries (Google AI Overviews and similar). |
| MCP | Model Context Protocol — the standard way Claude connects to an external tool or data source, called an "MCP server" (e.g. DataForSEO, Obsidian). |
| skill | Reference knowledge Claude loads automatically when your request matches it — you never invoke it by name. |
| command | An action you run explicitly by typing `/plugin:command-name`. |
| hook | A small script the harness runs automatically around a tool call — to block a risky action, log an event, or nudge Claude. |
| PRD | Product Requirements Document — the written spec a project is built from. |
| GSD | "Get Shit Done" (GSD v2, the `get-shit-done-cc` npm package) — the framework Rhize uses to hand an approved PRD to an autonomous coding agent. |
| receipt | A small saved record that a step (a review, a setup run, a delegation) actually happened, so later steps can check it instead of redoing the work. |
| evidence packet | The concrete build/test/lint output a review or check step collects, so its result is backed by real command output rather than a claim. |
| verdict | The pass/fail-style outcome a gate or review returns (e.g. `PASS`, `BLOCKED`). |
| impact map | A written record of which files a change will touch and why, prepared before editing starts. |
| control plane | The top-level plan → build → test → review → release workflow the other pieces plug into. |
| skill map | The generated graph of every skill, plugin, and how they relate — powers routing and the doc tables in this repo. |
| CodeGraph | A local, indexed map of a codebase's symbols and call paths, used instead of grep for faster, more accurate navigation. |
| RTK | A local proxy that shortens some command output to save tokens — verify a correctness-critical result yourself rather than trusting its summary. |
| Headroom | A local proxy that compresses API traffic between Claude and the model to reduce token cost. |
| claude-mem | A plugin that remembers facts across sessions, so Claude doesn't start from zero each time. |
| OpenWolf | A per-repo file index that gives Claude cheaper, faster context about one specific codebase. |
| Serena | A tool for precise, symbol-level code navigation. |
| Arm A / Arm B | The two sides of a controlled comparison (e.g. "with the skill" vs. "without it") used to measure whether a skill actually helps. |
| ACL | Access Control List — the rule set deciding who or what may read or write a given piece of data. |
| PKM | Personal Knowledge Management — methods (Zettelkasten, PARA) for organizing notes so they compound over time. |
| GROQ | The query language Sanity CMS uses to fetch content. |
| ICP | Ideal Customer Profile — a description of exactly who a product or offer is for. |
| RT-### | Rhize's internal Jira ticket numbering, referenced in commit messages and changelogs. |

## 8. Where next

- [`docs/README.md`](./docs/README.md) — cross-plugin reference material for maintainers.
- [`CHANGELOG.client.md`](./CHANGELOG.client.md) — plain-language highlights of what shipped.
- [`ROADMAP.md`](./ROADMAP.md) — active and planned future work.
- [`evals/README.md`](./evals/README.md) — what each evaluation suite grades and how to run it.
- [`docs/release/CHANGELOG-history.md`](./docs/release/CHANGELOG-history.md) — the full engineering record before 2026-09-03; each plugin now keeps its own `CHANGELOG.md`.
- [`docs/session-guardrails.md`](./docs/session-guardrails.md) — the session-level guardrails agents read when a session starts looping.
