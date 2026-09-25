# Project Launcher Plugin — User Guide

This guide explains what the Project Launcher plugin does, how its two skills work together, and how to get the most out of it when you're taking a project from a rough idea to something ready for autonomous development.

## What This Plugin Does

Project Launcher takes you from "I have an idea" to "there's a scaffolded project directory, ready to hand to GSD v2 for autonomous execution." It's built for anyone who regularly starts new projects — automations, web apps, content systems, integrations — and wants the boring-but-critical setup work (research, requirements, a PRD that holds up under scrutiny, a real project skeleton) done consistently instead of reinvented each time.

Without this plugin, "starting a project" usually means a scattered mix of a half-written doc, some Slack messages, and a folder you `mkdir`'d and forgot to configure. With it, Claude runs a proven pipeline: research the problem space first, ask you only the questions research couldn't answer, write a PRD that's specific enough for an autonomous agent to build from, stress-test that PRD before anyone writes code, turn it into a reviewable visual plan you actually sign off on, then scaffold a real directory with `CLAUDE.md`, `.planning/` docs, and the GSD v2 framework installed.

The plugin contains two skills and five commands (each command runs a specific slice of the
pipeline) — see [START-HERE.md's glossary](../START-HERE.md#7-glossary) if "skill" and "command"
are new terms to you.

## Setup

Install via the marketplace — there's no account to create and no credential this plugin itself
requires. The MCP servers and skills it can call on along the way (DataForSEO, Sentry, Obsidian,
and so on) are all optional: connect the ones relevant to your project and skip the rest. See the
[README](./README.md#setup) for the full list and what happens when one isn't connected.

## The Pipeline, In Plain Language

The full pipeline has six phases. Each phase produces something the next phase needs:

1. **Research** — Before asking you anything, Claude checks your Obsidian vault, scans related codebases, pulls external docs, and queries whatever MCP servers are relevant (Jira, Slack, DataForSEO, Google Drive, etc.) so it shows up to the interview already informed.
2. **Requirements Interview** — Claude asks the questions research couldn't answer, in batches of 5-10, grouped by theme (architecture, constraints, integrations, scope, quality bar).
3. **PRD + Visual Plan** — Claude writes a full Product Requirements Document (the machine-readable spec GSD will build from), then renders it into a `plan.mdx` visual plan — the human-friendly review surface with diagrams, file maps, and data contracts. **You review and approve the visual plan, not the raw PRD.**
4. **Critical Gap Analysis** — Before anyone scaffolds anything, the PRD gets stress-tested: failure modes, missing error handling, scalability assumptions, security gaps, cost estimates. This produces PRD v2.
5. **Project Scaffolding** — Claude creates the actual project directory: `CLAUDE.md`, `.planning/` (PROJECT.md, REQUIREMENTS.md, ROADMAP.md, STATE.md), the GSD v2 framework, and deliverable directories.
6. **GSD Handoff** — A final checklist verifies the plan, GSD 1.42.3 installation, and a live synthetic Jev/Laya decision probe before Claude briefs you on `/gsd-autonomous`.

**Where you can jump in:** you don't have to run the whole thing at once.

- Want the entire pipeline end to end? Use `/launch-project`.
- Just want a solid PRD without scaffolding anything yet? Use `/write-prd` (phases 1-4).
- Already have a PRD from somewhere else and just want it stress-tested? Use `/grill-prd` (phase 4 alone).
- Have an approved PRD and just need the project directory built? Use `/scaffold-gsd` (phases 5-6).
- Have any plan — not necessarily a project-launcher PRD — that needs a reviewable visual treatment? Use `/visual-plan` on its own.

## Skills Reference

### project-launcher

**When it activates:** You say something like "start a new project," "create a PRD," "plan an automation," "scaffold for GSD," "prepare for autonomous development," "I want to build...," or "new project idea." It also activates on requests to research a topic before building, interview about requirements, analyze a PRD for gaps, or prepare a `CLAUDE.md`/`.planning/` setup for a new codebase.

**What it knows:** The full 6-phase methodology — research sourcing (vault, codebase, docs, MCP servers), the interview question bank across 11 domains, the 14-section PRD template, the gap-analysis question categories, the `CLAUDE.md`/`.planning/` scaffolding structure, GSD v2 installation, and the handoff checklist. It also knows which MCP servers and skills to reach for at each phase, and can suggest and safety-gate additional skills for the project's stack once scaffolding starts.

**How to use it effectively:**
- Say "I want to build a tool that syncs our Slack standup notes into Notion" — Claude will start Phase 1 research on both platforms' APIs before asking you anything.
- Say "let's plan a new n8n workflow project for lead enrichment" — it recognizes the automation project type and pulls the automation-specific interview questions.
- Say "prepare a handoff for GSD" when you already have a PRD — it jumps straight to scaffolding.
- If you already know exactly what phase you want, just say so — "skip the interview, I already answered all this in the PRD I'm pasting."

### rhize-visual-plan

**When it activates:** You say "visual plan," "make this plan reviewable," "turn this plan into mdx," "wireframe this," "rich plan document," "review surface for this plan," "canvas plan," or "plan as an approval gate." It also activates automatically inside Phase 3 of the project-launcher pipeline, right after the PRD draft exists.

**What it knows:** The Rhize `plan.mdx` component vocabulary (`<Diagram>`, `<FileMap>`, `<DataModel>`, `<ApiEndpoint>`, `<Wireframe>`, `<Canvas>`, `<Decision>`, `<OpenQuestions>`), how to choose the right visual surface for the work (none / canvas-only / canvas + behavior notes), the `rhize-plan` CLI for live preview and self-contained HTML export, and how the plan degrades gracefully to plain Markdown + Mermaid in Obsidian.

**How to use it effectively:**
- Say "turn this PRD into a visual plan" and point at a PRD path — it produces `plan.mdx` with diagrams and file maps, not just prose.
- Say "wireframe the empty and error states for this screen" — it builds a `<Canvas>` with one artboard per state.
- Ask it to render what it just built — "show me the plan" — and it'll give you the actual path/URL from `rhize-plan serve`, not a description.
- This skill is deliberately usable outside project-launcher too — if you have any risky, multi-file, or ambiguous plan (not necessarily a project-launcher PRD) that deserves a real review artifact instead of a chat wall of text, invoke it directly.

## Commands Reference

### /launch-project

**Usage:** `/launch-project <project idea>`

Runs the complete 6-phase pipeline: research → interview → PRD + visual plan → gap analysis → scaffold → GSD handoff. If you don't pass an idea, Claude asks what you want to build and starts Phase 1 from there.

**Examples:**
- `/launch-project a Slack bot that posts weekly PostHog metrics to #product`
- `/launch-project` (then answer the follow-up question)

### /write-prd

**Usage:** `/write-prd <project idea>`

Runs phases 1-4 only — research, interview, PRD + visual plan, gap analysis — and stops before scaffolding. Good when you want a solid, stress-tested PRD but aren't ready to commit to a project directory yet.

**Examples:**
- `/write-prd a customer-facing status page for our services`
- `/write-prd redesign our lead scoring pipeline` (then continue the interview)

### /grill-prd

**Usage:** `/grill-prd <path to PRD>`

Runs Phase 4 (critical gap analysis) standalone, against a PRD you already have — whether it came from `/write-prd` or from somewhere else entirely. Produces a `-v2` version with all resolved gaps incorporated. If you don't have a PRD yet, it'll redirect you to `/write-prd` or `/launch-project`.

**Examples:**
- `/grill-prd prd/lead-scoring-prd.md`
- `/grill-prd` (then paste the PRD content directly)

### /scaffold-gsd

**Usage:** `/scaffold-gsd <path to PRD or project dir>`

Runs phases 5-6 — creates the project directory, `CLAUDE.md`, `.planning/` docs, installs GSD v2, and runs the handoff checklist. Assumes an approved PRD already exists; if none is found, it tells you to run `/write-prd` or `/launch-project` first.

**Examples:**
- `/scaffold-gsd prd/lead-scoring-prd-v2.md`
- `/scaffold-gsd ~/dev-local/lead-scoring` (if the PRD already lives inside the project dir)

### /visual-plan

**Usage:** `/visual-plan <PRD path, existing plan, or task description>`

Invokes `rhize-visual-plan` directly to turn any plan (not just a project-launcher PRD) into a reviewable `plan.mdx` with diagrams, wireframes, file maps, and data contracts. Useful standalone for any risky or multi-file change that deserves a real review artifact.

**Examples:**
- `/visual-plan prd/lead-scoring-prd-v2.md`
- `/visual-plan turn my pasted migration plan into something reviewable`

## How It All Fits Together

Research feeds the interview so you're only asked what research couldn't answer. The interview's answers get compiled straight into the PRD — you never have to repeat yourself. The PRD then gets distilled into the visual plan (`plan.mdx`): the PRD is the exhaustive, numbered machine spec that GSD reads; the visual plan is the reviewable version with diagrams and file maps that a human actually looks at and approves. Gap analysis stress-tests the PRD before that approval sticks, producing PRD v2 — and the visual plan gets refreshed to match, so what you approved and what GSD receives never drift apart. Only after the visual plan is approved does scaffolding happen: the PRD becomes the source for `CLAUDE.md` and every `.planning/` doc, and the visual plan travels with the project into `plans/<slug>/plan.mdx`. The handoff checklist confirms the PRD, approved plan, GSD skill injection, and a live decision probe before you're told it's safe to run `/gsd-autonomous`.

## Typed decision layer at project launch

Project Launcher copies a Python client into the new project and configures GSD
`agent_skills` for its planner, executor, and verifier. Each agent asks fixed,
bounded supervision questions at a meaningful checkpoint. Claude Code hooks check that the specific agent
made a client call before its work ends; a provider failure creates an unavailable
receipt and the agent uses the existing GSD judgment path. The decision answer is
observational in shadow mode: PRD requirements, code checks, and approval gates still decide what ships.

For hosted Jev, make `TYPESAFE_API_KEY` available only to the project session. For a
local Laya-compatible server, set `TYPESAFE_BASE_URL` to its loopback base URL and
optionally `LAYA_API_KEY`. On Apple Silicon, start the Python reference
server bound to `127.0.0.1` and evaluate `TYPESAFE_DEFAULT_MODEL=typed-decisions`
as one pinned pilot candidate. Laya's default English and multilingual checkpoints
must be scored separately; the synthetic probe checks connectivity, not accuracy.
The client starts in `shadow` mode, and `RHIZE_DECISION_MODE=advisory` requires an
explicit choice after task-relevant evaluation. Phase 6 runs a synthetic probe, then
`python3 .claude/rhize-decision/typed_decision.py status`. If either fails, the
handoff is blocked until the provider is available. No real project text is used
by this probe. During GSD execution, inspect
`.planning/decision-layer/receipts.jsonl` for per-agent calls and token usage.
The ready status checks the most recent probe against the current provider and
model environment, so rerun it after changing either setting.

For a local pilot, install the pinned Python server in a separate local directory
with Python 3.12, then run it in one terminal:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install 'laya[serve]==0.3.20'
LAYA_HOST=127.0.0.1 LAYA_DEVICE=mps LAYA_MODELS=typed-decisions .venv/bin/laya-serve
```

The first launch downloads the selected checkpoint. In the Project Launcher/GSD
session, set `TYPESAFE_BASE_URL=http://127.0.0.1:8000`,
`TYPESAFE_DEFAULT_MODEL=typed-decisions`, and `RHIZE_DECISION_MODE=shadow` before
the synthetic probe. Record the package version, model returned in receipts,
device, cold/warm latency, and memory use; compare the checkpoint with the
incumbent path on the frozen task-specific corpus before enabling advisory mode.
The local probe also checks that the server actually routed `typed-decisions`;
its generic response `model` field alone is insufficient. The reference checkpoint
has emitted a calibration-temperature warning during local startup, so its
confidence is uncalibrated until the Rhize holdout says otherwise. The
[typed-decision research runner](../evals/typed-decision/README.md) provides a
bounded autoresearch-style search and locked holdout using benchmark labels.
Foreman-style multi-check results and a deterministic candidate directive are
recorded in shadow for planner, executor, and verifier; no automatic steering,
stopping, completion or release is enabled by this pilot.

## Tips

- **Let Phase 1 run before you answer anything.** If Claude jumps straight to asking questions without mentioning what it found in your vault or codebase, it skipped research — ask it to check prior art first.
- **Use `/grill-prd` before scaffolding, every time — even on a PRD you're confident in.** The value isn't catching obvious mistakes; it's forcing answers on failure modes, cost, and multi-tenancy questions you'd otherwise only discover mid-build. Skipping it just moves the same questions to a more expensive point in the process.
- **Review the visual plan, not the raw PRD.** The `plan.mdx` is deliberately the approval surface — diagrams and file maps surface problems prose buries. If you find yourself scrolling through the raw PRD to decide whether to approve, ask for the visual plan instead.
- **You can invoke `/visual-plan` on anything, not just project-launcher PRDs.** Any risky, multi-file, or ambiguous plan benefits from becoming a real review artifact instead of a chat wall of text.
- **Don't skip straight to `/scaffold-gsd` on a PRD that hasn't been through gap analysis.** The scaffolding command assumes the PRD it's reading is the stress-tested version — feeding it a v1 PRD means the gaps get discovered during autonomous execution instead of before it.
- **If the project uses the Rhize Next.js stack** (Next.js + Supabase + Sanity), scaffolding offers to install hookify guardrails — a starter rule set that blocks direct pushes to main and leaked secrets before they ship. Worth accepting.

## Troubleshooting

**Claude asks generic questions instead of informed ones:** Phase 1 research either didn't run or came back empty. Point it explicitly at your vault or a related codebase and ask it to redo research before continuing the interview.

**`/grill-prd` says it can't find a PRD:** You need to either pass a path as an argument or paste the PRD content directly in the conversation. If you don't have a PRD yet, run `/write-prd` or `/launch-project` first.

**`/scaffold-gsd` won't proceed:** It requires an existing PRD, either at the path you gave it or inside a `prd/` or `.claude/plans/` directory. If none is found, run `/write-prd` first to generate one.

**The visual plan looks thin or skips diagrams entirely:** That's often correct, not a bug — `rhize-visual-plan` deliberately skips visual surfaces for architecture-only or copy-only plans rather than forcing chrome onto something that doesn't need it. If you do want diagrams and the plan is genuinely multi-file or data-heavy, say so explicitly.

**GSD handoff checklist fails on `.claude/settings.json`:** Verify the pinned GSD install completed and that typed decision `SubagentStart` and `SubagentStop` hooks are present. The older `superpowers@claude-plugins-official` setting is a separate project preference, not proof of GSD or decision-layer readiness.

**Decision layer status is blocked:** Set the provider environment variable and run the synthetic `probe` command from the scaffolded project. Check `gsd-sdk query agent-skills` for planner, executor, and verifier. The project should not be described as ready until these checks pass.

**A skill it suggests during scaffolding gets blocked:** Project-launcher gates any skill it suggests through a safety check before adding it, and refuses anything rated HIGH/CRITICAL risk. This is intentional — it won't silently add an unvetted skill just because it looked relevant to your stack.
