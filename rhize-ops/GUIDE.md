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

The same `parallel-agent-optimization` skill contract is discoverable in Claude Code and Codex.
Restart the host after installing or updating the plugin before running a discovery smoke; commands
are Claude adapters, while Codex routes through the canonical skill and its OpenAI metadata.

## Skills Reference

### delegate-to-teammate

**When to use it:** Any time you want to hand work off to your configured teammate instead of doing it yourself — after a client call, when a task needs their specific expertise, or when something's become "their thing to own" going forward. Trigger it with "delegate this to [name]," "hand this off to [name]," "[name] should handle this," or just a bare "delegate"/"hand off" (your configured recipient is the default).

**What it produces:** A full delegation package, split into three layers instead of one wall of text. The skill gathers context from your current session, the Obsidian vault, and (optionally) a relevant Fireflies meeting transcript, then asks you a few quick questions (tracker project per task, due date, priority). The recipient opens Jira and reads a concise, one-screen brief — what, why, done criteria, the one gotcha most likely to bite, and a starter prompt to paste into Claude. The full instructions — every step, every prompt, every gotcha, validation criteria — live one click away on a Confluence "handoff brief" page. Any vault notes the task depends on arrive as scrubbed markdown copies attached to the Jira issue, plus a Slack Canvas per document, never as local file paths the recipient can't open; anything that can't be attached shows up in a "Files to request from the delegator" list instead. The skill still posts to your configured Slack channel with a scannable main message plus a threaded reply per task, tagging the recipient so they get notified.

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

**What it produces:** An `apply` run does the real work once, using the built-in Rhize
coordination strategy, checks the result, and saves one record of how it went. A `compare` run is
a controlled experiment instead — it re-runs the same starting task twice, once with the strategy
and once without, in randomized order so neither run gets an unfair advantage, and only against a
safe, replayable fixture, never your live task.

Every run leaves behind a receipt — what kind of task it was, how long it took, whether agents
overlapped, and whether the result checked out — but never the actual prompts, code, files, names,
or IDs involved. A run that didn't finish cleanly shows up as `audit-pending` so you know to follow
up on it. Full schema: [README](./README.md#parallel-agent-optimization).

For execution, sketch nodes and dependencies before dispatch. The canonical skill validates that
file-disjoint work is also independent of checkout state, rate pools, approvals, and external
effects. Unknown host capacity becomes a sequential wave, and a missing required result blocks the
join. Claude Code and Codex share this host-neutral contract; neither host needs the other's hooks or
environment variables.

**Example prompt:**
> "/rhize-ops:parallel-optimize assess would parallel agents help with this repository audit?"

For real work:
> "/rhize-ops:parallel-optimize apply audit these three independent modules and verify the findings"

For a controlled fixture:
> "/rhize-ops:parallel-optimize compare evals/parallel-agent-skills/tasks/mixed-verification"

## Commands Reference

### /parallel-optimize

**What it's for:** The required entry point whenever parallel agents enter the conversation or
execution. `assess` makes a non-executing routing decision; `apply` runs the Rhize strategy once on
the actual task; `compare` runs baseline versus Rhize only when the task is isolated and replayable;
`report` separates observational, controlled, and legacy evidence; `audit-pending` finds accepted
runs that still need factual terminal finalization.

**Example usage:**
> "/rhize-ops:parallel-optimize report all" — inspect accumulated evidence without rerunning any task.

### /delegate-setup

**What it's for:** One-time (or occasional) setup for `delegate-to-teammate`. Interviews you for who you're delegating to and their technical context, then looks up Jira/Slack identifiers automatically wherever those MCP servers are connected — you shouldn't need to go dig up account IDs or channel IDs by hand. It also resolves the Confluence space and "Delegations" page where handoff briefs get filed, and checks Keychain for an Atlassian API token so it can report whether Jira attachments are enabled. Writes everything to `~/.claude/rhize-ops/delegate.config.json`, outside this repo entirely, so it never leaves your machine.

**Example usage:**
> "/rhize-ops:delegate-setup" — answer the interview questions, confirm the auto-looked-up Jira/Slack IDs, and you're ready to delegate. Re-run it any time to add another recipient or fix a stale mapping.

### /bump-version

**What it's for:** Keeping every plugin's version, the marketplace manifest, and the CHANGELOG in sync across the whole `rhize-plugins` repo whenever you ship a change. It figures out what changed since the last release and infers major/minor/patch from your commit messages — you just confirm the plan. It never pushes on its own.

**Example usage:**
> "/rhize-ops:bump-version" — then confirm the proposed plan, and it applies the bump and shows you the diff to review before you commit.

### /plugin-prune

**What it's for:** Deciding, with evidence, which enabled Claude Code plugins you can switch off. It runs a `@rhize/skill-forge` (0.17+) plugin audit over everything enabled, joins the latest skill-monitor usage snapshots, and prints one advisory row per plugin — recommendation, active HIGH/CRITICAL findings, and how many exhaustive snapshots never observed any of its skills. It never edits `~/.claude/settings.json`; if you name plugins to disable, it asks for a typed `yes` per plugin in your own terminal and then runs `claude plugin disable <id> --scope user`. Skill telemetry says nothing about a plugin's hooks, agents, commands, or MCP servers, so treat "unobserved" as a prompt to look, not a verdict.

**Example usage:**
> "/rhize-ops:plugin-prune" — read the table, then say which plugins (if any) to disable; nothing changes until you confirm each one.

### Setup moved to rhize-core

The fleet-level "pick your plugins, run their wizards, establish evaluation baselines, wire
opt-in hooks" workflow moved to the `rhize-core` plugin as `/rhize-core:setup` — see [its own
GUIDE](../rhize-core/GUIDE.md). `/rhize-ops:rhize-setup` still works for one release: it forwards
to `rhize-core:setup` when that plugin is installed, otherwise it runs the same wizard from a
fallback copy — install `rhize-core@rhize-plugins` to get the canonical copy.

## Cost & Savings Reports

Two scripts in the standalone [`rhize-skill-monitor`](https://github.com/Rhize-Media/rhize-skill-monitor) tool give you cost visibility on top of the skill-usage data — not a skill or command you invoke directly, but part of the weekly audit (and runnable on demand). Clone it once to `~/dev-local/RHIZE/rhize-skill-monitor` (or point `RHIZE_SKILL_MONITOR_ROOT` at your own checkout) and `skill-dashboard` finds it automatically.

**`savings_scorecard.py`** — answers "what am I actually spending, and what's actually being saved?" It keeps two tiers strictly separate: **Measured** (real per-session spend from `costs.jsonl`, plus rtk and Headroom's own tracked savings) and **Estimated** (claude-mem, OpenWolf, and headroom-learn's self-reported heuristics) — the estimated numbers are never added into the measured total, because they're not counting the same thing. New to rtk/Headroom/claude-mem/OpenWolf? See [START-HERE's glossary](../START-HERE.md#7-glossary).

**`skill_roi.py`** — answers "which skills are actually earning their session cost?" It joins skill invocations to the session cost they happened in and flags keep-listed skills sitting at zero invocations, plus skills that are expensive but rarely used.

**Example prompt:**
> "Run the savings scorecard for the last 28 days" or "what's the cost-per-skill ROI look like this week?" — both run as part of `weekly-skill-audit`, or on demand via `python3 savings_scorecard.py --days 28` / `python3 skill_roi.py` from your `rhize-skill-monitor` checkout.

## Tips & Troubleshooting

**"Who am I delegating to?" — run setup first.** If `delegate-to-teammate` triggers but there's no `~/.claude/rhize-ops/delegate.config.json` yet, it'll ask you to run `/rhize-ops:delegate-setup` instead of guessing. This is expected on a fresh install.

**Give delegate-to-teammate a transcript when you have one.** The skill will ask if there's a relevant Fireflies meeting — saying yes gets your teammate real client context (quotes, decisions, deadlines) instead of a bare task description.

**Multiple tasks, multiple projects.** If you're delegating several things at once, the skill asks about the Jira project for each task individually — don't assume they all land in the same place.

**The Jira description is still the full package.** Confluence is `incomplete` or missing from the config — re-run `/rhize-ops:delegate-setup` with the Atlassian MCP connected and confirm the "Delegations" page.

**The issue has no attachments and the Slack reply lists files to request.** No Atlassian token in Keychain (README: Atlassian API token) or the file exceeds the size cap (100 MB default).

**Transcript/vault content is quoted, not obeyed.** Meeting transcripts and vault notes are treated as context to summarize, never as instructions — project, due date, priority, and assignee always come from your own answers, not from anything a note or transcript says. If ingested content contains something that reads like an instruction, the skill will flag it to you instead of acting on it.

**Dashboard renders empty?** No snapshots exist yet. Run `python3 monitor.py --days 0` from your `rhize-skill-monitor` checkout to seed one, then re-render.

**Want fresher dashboard data mid-week?** Ask to "refresh the dashboard" — this reruns the monitor before rendering. Normal renders just reuse whatever snapshots have already accumulated (fast, no rescan).

**Bump-version dry-runs by default.** Nothing gets written until you confirm the plan; run with `--check` any time to validate versions without making changes.

**A comparison refused to run?** The command will not clone a live task into multiple arms. Supply
a deterministic fixture or disposable worktree seed with predeclared checks, then retry `compare`.
Use `apply` for the actual live task.

**Token/tool coverage says unavailable?** That is an honest host limitation, not zero usage. The
receipt keeps the field null with a reason and the report shows measured-run coverage instead of
estimating a value.

**Are ECC or Superpowers still invoked by this workflow?** No. They are provenance and
`ai-stack-version-drift` review references only. The existing skill monitor may still contain old
direct-launch counts, but those historical counts do not contain matched outcome evidence and are
not mixed into v2 reports.

**A receipt is evidence, not a decision.** Receipts tell you what happened; they don't adopt,
promote, or roll back a strategy on their own. Formally acting on a batch of receipts goes through
`rhize-context-manager`'s reviewed decision process, not this plugin — see the
[README](./README.md#decision-accountability-adapter) for exactly what that requires and what it
never does.


Snapshot history uses `--snapshot-count N` (`--weeks` remains a legacy alias). Output schema
`rhize-plugin-prune-v2` uses `snapshotsUnobserved`/`snapshotsTotal`, reports each selected window's
timestamp and duration, and includes telemetry scope in JSON. Overlapping or old samples are
not weeks of inactivity. Invalid, incomplete, bare-key or wholly unjoinable snapshots cannot
establish dormancy; same plugin names across marketplaces remain unknown. Failed disable
subprocesses return exit 2 while remaining requested IDs still get their own confirmation.

The audit command resolves the latest published Skill Forge package (audit JSON needs 0.17+;
routine JSON needs 0.18+). A newer source version alone does not imply npm publication.
