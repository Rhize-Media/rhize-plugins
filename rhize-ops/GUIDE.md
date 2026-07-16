# rhize-ops — User Guide

This guide explains what the rhize-ops plugin does and how to get the most out of it. It's Rhize Media's internal **operations** plugin — for running the team, not building software (that's `rhize-devflow`).

## What This Plugin Does

rhize-ops covers two everyday ops jobs:

- **Handing work off to [REDACTED_NAME]** without losing context — turning a messy session into a clear, encouraging task package he can actually execute.
- **Watching skill health** — seeing which of your installed skills are earning their keep, so you know what to prune.

It's built for Jim (and anyone else running the Rhize Media Claude setup) who regularly delegates work and wants visibility into their own tool usage.

## Skills Reference

### delegate-to-tom

**When to use it:** Any time you want to hand work off to the recipient instead of doing it yourself — after a client call, when a task needs his marketing/ads/sales expertise, or when something's become "his thing to own" going forward. Trigger it with "delegate this to the recipient," "hand this off to the recipient," "the recipient should handle this," or just a bare "delegate"/"hand off" (the recipient is the default recipient).

**What it produces:** A full delegation package, not just a note. The skill gathers context from your current session, the Obsidian vault, and (optionally) a relevant Fireflies meeting transcript; asks you a few quick questions (Jira project per task, due date, priority); then creates a Jira issue per task, shares any relevant vault documents as Slack Canvases, and posts to `#[REDACTED_CHANNEL]` with a scannable main message plus a threaded reply per task — tagging the recipient so he gets notified. Each task package includes step-by-step instructions, gotchas, starter prompts he can paste straight into Claude, and validation criteria so he knows when he's done.

**Example prompt:**
> "Delegate the Acme Co. sitemap cleanup to the recipient — there's a client call transcript from Tuesday that has the details."

### skill-dashboard

**When to use it:** When you want a pulse check on which skills you're actually using — weekly, mid-week, or whenever the prune-candidates question comes up ("is this skill worth keeping installed?"). It reads accumulated audit snapshots, so it's instant — no transcript rescanning.

**What it shows:** A live dashboard with weekly usage trend, top skills with rank-of-the-week deltas, a direct-vs-indirect leverage view (are your subagents using a skill more than you do directly?), a prune-candidates table (skills that fired historically but not recently), a subagent-type breakdown, project/host-vs-Cowork rollups, and week-over-week movement. Renders as a Claude Artifact when the chat surface supports it (Desktop, claude.ai), or opens as HTML in your browser from Claude Code.

**Example prompt:**
> "Show me the skill dashboard" or "/skill-dashboard"

## Commands Reference

### /bump-version

**What it's for:** Keeping every plugin's version, the marketplace manifest, and the CHANGELOG in sync across the whole `rhize-plugins` repo whenever you ship a change. It figures out what changed since the last release and infers major/minor/patch from your commit messages — you just confirm the plan. It never pushes on its own.

**Example usage:**
> "/rhize-ops:bump-version" — then confirm the proposed plan, and it applies the bump and shows you the diff to review before you commit.

## Tips & Troubleshooting

**Give delegate-to-teammate a transcript when you have one.** The skill will ask if there's a relevant Fireflies meeting — saying yes gets the recipient real client context (quotes, decisions, deadlines) instead of a bare task description.

**Multiple tasks, multiple projects.** If you're delegating several things at once, the skill asks about the Jira project for each task individually — don't assume they all land in the same place.

**Dashboard renders empty?** No snapshots exist yet. Run `python3 rhize-ops/skill-monitor/monitor.py --days 0` to seed one, then re-render.

**Want fresher dashboard data mid-week?** Ask to "refresh the dashboard" — this reruns the monitor before rendering. Normal renders just reuse whatever snapshots have already accumulated (fast, no rescan).

**Bump-version dry-runs by default.** Nothing gets written until you confirm the plan; run with `--check` any time to validate versions without making changes.
