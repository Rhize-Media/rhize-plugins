# rhize-ops — User Guide

This guide explains what the rhize-ops plugin does and how to get the most out of it. It's Rhize Media's internal **operations** plugin — for running the team, not building software (that's `rhize-devflow`).

## What This Plugin Does

rhize-ops covers two everyday ops jobs:

- **Handing work off to a teammate** without losing context — turning a messy session into a clear, encouraging task package they can actually execute.
- **Watching skill health** — seeing which of your installed skills are earning their keep, so you know what to prune.

It's built for anyone running a Claude Code/Cowork setup who regularly delegates work and wants visibility into their own tool usage. `delegate-to-teammate` is config-driven — no recipient, workspace, or project data is hardcoded — so it works for any team once you run its setup wizard once.

## Setup

Before using `delegate-to-teammate` for the first time, run `/rhize-ops:delegate-setup` — see [Commands Reference](#commands-reference) below. `skill-dashboard` needs no setup.

## Skills Reference

### delegate-to-teammate

**When to use it:** Any time you want to hand work off to your configured teammate instead of doing it yourself — after a client call, when a task needs their specific expertise, or when something's become "their thing to own" going forward. Trigger it with "delegate this to [name]," "hand this off to [name]," "[name] should handle this," or just a bare "delegate"/"hand off" (your configured recipient is the default).

**What it produces:** A full delegation package, not just a note. The skill gathers context from your current session, the Obsidian vault, and (optionally) a relevant Fireflies meeting transcript; asks you a few quick questions (tracker project per task, due date, priority); then creates a tracker issue per task, shares any relevant vault documents as Slack Canvases, and posts to your configured channel with a scannable main message plus a threaded reply per task — tagging the recipient so they get notified. Each task package includes step-by-step instructions, gotchas, starter prompts they can paste straight into Claude, and validation criteria so they know when they're done.

**Example prompt:**
> "Delegate the sitemap cleanup to Alex — there's a client call transcript from Tuesday that has the details."

### skill-dashboard

**When to use it:** When you want a pulse check on which skills you're actually using — weekly, mid-week, or whenever the prune-candidates question comes up ("is this skill worth keeping installed?"). It reads accumulated audit snapshots, so it's instant — no transcript rescanning.

**What it shows:** A live dashboard with weekly usage trend, top skills with rank-of-the-week deltas, a direct-vs-indirect leverage view (are your subagents using a skill more than you do directly?), a prune-candidates table (skills that fired historically but not recently), a subagent-type breakdown, project/host-vs-Cowork rollups, and week-over-week movement. Renders as a Claude Artifact when the chat surface supports it (Desktop, claude.ai), or opens as HTML in your browser from Claude Code.

**Example prompt:**
> "Show me the skill dashboard" or "/skill-dashboard"

## Commands Reference

### /delegate-setup

**What it's for:** One-time (or occasional) setup for `delegate-to-teammate`. Interviews you for who you're delegating to and their technical context, then looks up Jira/Slack identifiers automatically wherever those MCP servers are connected — you shouldn't need to go dig up account IDs or channel IDs by hand. Writes everything to `~/.claude/rhize-ops/delegate.config.json`, outside this repo entirely, so it never leaves your machine.

**Example usage:**
> "/rhize-ops:delegate-setup" — answer the interview questions, confirm the auto-looked-up Jira/Slack IDs, and you're ready to delegate. Re-run it any time to add another recipient or fix a stale mapping.

### /bump-version

**What it's for:** Keeping every plugin's version, the marketplace manifest, and the CHANGELOG in sync across the whole `rhize-plugins` repo whenever you ship a change. It figures out what changed since the last release and infers major/minor/patch from your commit messages — you just confirm the plan. It never pushes on its own.

**Example usage:**
> "/rhize-ops:bump-version" — then confirm the proposed plan, and it applies the bump and shows you the diff to review before you commit.

## Tips & Troubleshooting

**"Who am I delegating to?" — run setup first.** If `delegate-to-teammate` triggers but there's no `~/.claude/rhize-ops/delegate.config.json` yet, it'll ask you to run `/rhize-ops:delegate-setup` instead of guessing. This is expected on a fresh install.

**Give delegate-to-teammate a transcript when you have one.** The skill will ask if there's a relevant Fireflies meeting — saying yes gets your teammate real client context (quotes, decisions, deadlines) instead of a bare task description.

**Multiple tasks, multiple projects.** If you're delegating several things at once, the skill asks about the Jira project for each task individually — don't assume they all land in the same place.

**Dashboard renders empty?** No snapshots exist yet. Run `python3 rhize-ops/skill-monitor/monitor.py --days 0` to seed one, then re-render.

**Want fresher dashboard data mid-week?** Ask to "refresh the dashboard" — this reruns the monitor before rendering. Normal renders just reuse whatever snapshots have already accumulated (fast, no rescan).

**Bump-version dry-runs by default.** Nothing gets written until you confirm the plan; run with `--check` any time to validate versions without making changes.
