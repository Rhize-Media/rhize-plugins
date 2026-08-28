# rhize-ops — User Guide

This guide explains what the rhize-ops plugin does and how to get the most out of it. It's Rhize Media's internal **operations** plugin — for running the team, not building software (that's `rhize-devflow`).

## What This Plugin Does

rhize-ops covers three everyday ops jobs:

- **Handing work off to a teammate** without losing context — turning a messy session into a clear, encouraging task package they can actually execute.
- **Watching skill health** — seeing which of your installed skills are earning their keep, so you know what to prune.
- **Optimizing parallel-agent work** — choosing one safe execution strategy for real work and gathering evidence through isolated comparisons when a replayable fixture exists.

It's built for anyone running a Claude Code/Cowork setup who regularly delegates work and wants visibility into their own tool usage. `delegate-to-teammate` is config-driven — no recipient, workspace, or project data is hardcoded — so it works for any team once you run its setup wizard once.

## Setup

Before using `delegate-to-teammate` for the first time, run `/rhize-ops:delegate-setup` — see [Commands Reference](#commands-reference) below. `skill-dashboard` and `parallel-agent-optimization` need no setup. The latter creates its private local receipt directory on first use.

## Skills Reference

### delegate-to-teammate

**When to use it:** Any time you want to hand work off to your configured teammate instead of doing it yourself — after a client call, when a task needs their specific expertise, or when something's become "their thing to own" going forward. Trigger it with "delegate this to [name]," "hand this off to [name]," "[name] should handle this," or just a bare "delegate"/"hand off" (your configured recipient is the default).

**What it produces:** A full delegation package, not just a note. The skill gathers context from your current session, the Obsidian vault, and (optionally) a relevant Fireflies meeting transcript; asks you a few quick questions (tracker project per task, due date, priority); then creates a tracker issue per task, shares any relevant vault documents as Slack Canvases, and posts to your configured channel with a scannable main message plus a threaded reply per task — tagging the recipient so they get notified. Each task package includes step-by-step instructions, gotchas, starter prompts they can paste straight into Claude, and validation criteria so they know when they're done.

Every approved task's Jira description and Slack thread reply also share a stable [`rhize-delegation:v1` ID](./skills/delegate-to-teammate/references/rhize-delegation-v1.md). If Jira is missing or its result is uncertain, the thread reply is clearly marked `needs_jira`; Rhize Tasks can surface that one recognized delegation for approval and merge it later when Jira contains the exact same ID. The shared root message is never marked, and arbitrary Slack messages are ignored even when they look task-like.

**Example prompt:**
> "Delegate the sitemap cleanup to Alex — there's a client call transcript from Tuesday that has the details."

### skill-dashboard

**When to use it:** When you want a pulse check on which skills you're actually using — weekly, mid-week, or whenever the prune-candidates question comes up ("is this skill worth keeping installed?"). It reads accumulated audit snapshots, so it's instant — no transcript rescanning.

**What it shows:** A live dashboard with weekly usage trend, top skills with rank-of-the-week deltas, a direct-vs-indirect leverage view (are your subagents using a skill more than you do directly?), a prune-candidates table (skills that fired historically but not recently), a subagent-type breakdown, project/host-vs-Cowork rollups, and week-over-week movement. Renders as a Claude Artifact when the chat surface supports it (Desktop, claude.ai), or opens as HTML in your browser from Claude Code.

**Example prompt:**
> "Show me the skill dashboard" or "/skill-dashboard"

### parallel-agent-optimization

**When to use it:** Always when parallel or multi-agent work is mentioned, discussed, planned,
reviewed, or employed—including subagents and concurrent agent dispatch. Invoke it before the first
agent spawn. Use `assess` for discussion or planning with no execution or receipt, `apply` for real
work, and `compare` only for a safe replayable repository fixture. Parallel agents are the execution
default when at least two independent bounded lanes pass the isolation and coordination-benefit
gates. The skill keeps dependency chains, shared-state work, and approval-gated operations
sequential even when the request asks for parallelism.

**What it produces:** An `apply` run selects exactly one of baseline, ECC, Superpowers, or Rhize,
executes it under a one-writer safety envelope, verifies the result, and appends one observational
receipt. A `compare` run creates four isolated arms from the same seed, runs them in a
counterbalanced order, and stores controlled receipts separately. There is no combined
ECC+Superpowers arm, and the Rhize arm chooses at most one upstream resource.

Receipts include coarse task class, variant, timing/overlap, tool/token coverage, agent counts,
verification, correctness, collisions, and rework. They cannot contain prompts, code, commands,
paths, names, URLs, session IDs, or issue IDs.

**Example prompt:**
> "/rhize-ops:parallel-optimize assess would parallel agents help with this repository audit?"

For real work:
> "/rhize-ops:parallel-optimize apply audit these three independent modules and verify the findings"

For a controlled fixture:
> "/rhize-ops:parallel-optimize compare evals/parallel-agent-skills/tasks/mixed-verification"

## Commands Reference

### /parallel-optimize

**What it's for:** The required entry point whenever parallel agents enter the conversation or
execution. `assess` makes a non-executing routing decision; `apply` runs one strategy on the actual
task; `compare` runs four separate arms only when the task is isolated and replayable; `report`
renders observational and controlled evidence in separate sections.

**Example usage:**
> "/rhize-ops:parallel-optimize report all" — inspect accumulated evidence without rerunning any task.

### /delegate-setup

**What it's for:** One-time (or occasional) setup for `delegate-to-teammate`. Interviews you for who you're delegating to and their technical context, then looks up Jira/Slack identifiers automatically wherever those MCP servers are connected — you shouldn't need to go dig up account IDs or channel IDs by hand. Writes everything to `~/.claude/rhize-ops/delegate.config.json`, outside this repo entirely, so it never leaves your machine.

**Example usage:**
> "/rhize-ops:delegate-setup" — answer the interview questions, confirm the auto-looked-up Jira/Slack IDs, and you're ready to delegate. Re-run it any time to add another recipient or fix a stale mapping.

### /bump-version

**What it's for:** Keeping every plugin's version, the marketplace manifest, and the CHANGELOG in sync across the whole `rhize-plugins` repo whenever you ship a change. It figures out what changed since the last release and infers major/minor/patch from your commit messages — you just confirm the plan. It never pushes on its own.

**Example usage:**
> "/rhize-ops:bump-version" — then confirm the proposed plan, and it applies the bump and shows you the diff to review before you commit.

### /rhize-setup

**What it's for:** A fleet-wide guardrail wizard. Installing a Rhize plugin never turns on any of its hooks by itself — this command finds every installed plugin's opt-in hook catalog, shows you what's already wired vs. just available in the current project, and lets you pick which ones to turn on without hand-editing `.claude/settings.json`. Every hook it offers gets smoke-tested before it's wired, so a broken hook script can't get wired silently.

**Example usage:**
> "/rhize-ops:rhize-setup" — review the per-plugin menu, pick the guardrails you want (each shows its tier — T3 advisory or T4 blocking — and a one-line description), and it writes them into your project's `.claude/settings.json` plus prints a status table for every available item, wired or not.

## Cost & Savings Reports

Two scripts under `skill-monitor/` give you cost visibility on top of the skill-usage data — not a skill or command you invoke directly, but part of the weekly audit (and runnable on demand).

**`savings_scorecard.py`** — answers "what am I actually spending, and what's actually being saved?" It keeps two tiers strictly separate: **Measured** (real per-session spend from `costs.jsonl`, plus rtk and Headroom's own tracked savings) and **Estimated** (claude-mem, OpenWolf, and headroom-learn's self-reported heuristics) — the estimated numbers are never added into the measured total, because they're not counting the same thing.

**`skill_roi.py`** — answers "which skills are actually earning their session cost?" It joins skill invocations to the session cost they happened in and flags keep-listed skills sitting at zero invocations, plus skills that are expensive but rarely used.

**Example prompt:**
> "Run the savings scorecard for the last 28 days" or "what's the cost-per-skill ROI look like this week?" — both run as part of `weekly-skill-audit`, or on demand via `python3 skill-monitor/savings_scorecard.py --days 28` / `python3 skill-monitor/skill_roi.py`.

## Tips & Troubleshooting

**"Who am I delegating to?" — run setup first.** If `delegate-to-teammate` triggers but there's no `~/.claude/rhize-ops/delegate.config.json` yet, it'll ask you to run `/rhize-ops:delegate-setup` instead of guessing. This is expected on a fresh install.

**Give delegate-to-teammate a transcript when you have one.** The skill will ask if there's a relevant Fireflies meeting — saying yes gets your teammate real client context (quotes, decisions, deadlines) instead of a bare task description.

**Multiple tasks, multiple projects.** If you're delegating several things at once, the skill asks about the Jira project for each task individually — don't assume they all land in the same place.

**Transcript/vault content is quoted, not obeyed.** Meeting transcripts and vault notes are treated as context to summarize, never as instructions — project, due date, priority, and assignee always come from your own answers, not from anything a note or transcript says. If ingested content contains something that reads like an instruction, the skill will flag it to you instead of acting on it.

**Dashboard renders empty?** No snapshots exist yet. Run `python3 rhize-ops/skill-monitor/monitor.py --days 0` to seed one, then re-render.

**Want fresher dashboard data mid-week?** Ask to "refresh the dashboard" — this reruns the monitor before rendering. Normal renders just reuse whatever snapshots have already accumulated (fast, no rescan).

**Bump-version dry-runs by default.** Nothing gets written until you confirm the plan; run with `--check` any time to validate versions without making changes.

**A comparison refused to run?** The command will not clone a live task into multiple arms. Supply
a deterministic fixture or disposable worktree seed with predeclared checks, then retry `compare`.
Use `apply` for the actual live task.

**Token/tool coverage says unavailable?** That is an honest host limitation, not zero usage. The
receipt keeps the field null with a reason and the report shows measured-run coverage instead of
estimating a value.

**Do direct ECC or Superpowers invocations add receipts?** No. Only runs routed through
`/rhize-ops:parallel-optimize` use this receipt contract. The existing skill monitor may still count
some direct Claude-host skill launches, but those historical counts do not contain matched outcome
evidence and are not mixed into these reports.
