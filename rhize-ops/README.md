# rhize-ops

Rhize Media's **operations** plugin — internal delegation, hand-offs, and team-workflow automation. Distinct from `rhize-devflow` (which is about *building* software); `rhize-ops` is about *running the team*.

## Skills

### `delegate-to-tom`

Turns the work from Jim's current session into a clearly structured hand-off package for [REDACTED_NAME]. Handles the full delegation pipeline: context gathering, Fireflies transcript analysis, task formatting, Jira issue creation, and Slack notification with an @mention.

**Invoked as:** `rhize-ops:delegate-to-tom`

**Triggers:** "delegate this to the recipient", "hand this off to the recipient", "assign this to the recipient", "the recipient should handle this", or a bare "delegate"/"hand off"/"assign" where the recipient is the default recipient.

### `skill-dashboard`

Renders the live skill-monitor audit dashboard — aggregates every per-run snapshot into one interactive view (weekly trend, top skills with rank deltas, direct/indirect leverage, prune candidates, subagent-type breakdown, project rollup, host/Cowork split, week-over-week delta). Renders as a Claude Artifact when the surface supports it, or as external HTML otherwise.

**Invoked as:** `rhize-ops:skill-dashboard`

**Triggers:** "show the skill dashboard", "render the audit dashboard", "skill usage dashboard", "/skill-dashboard", or a request to visualize skill-monitor data.

## Commands

### `/bump-version`

Coordinated semver bump for the `rhize-plugins` marketplace. Wraps `scripts/bump_version.py`, which auto-discovers plugins and keeps each plugin's version, the marketplace manifest, and the CHANGELOG in sync. Never pushes.

**Invoked as:** `/rhize-ops:bump-version`

## Data Subsystem

`skill-monitor/` is not a skill — it's the audit tool `skill-dashboard` reads from. `monitor.py` walks Claude Code/Cowork transcripts to produce JSON snapshots (`data/snapshots/`), and `dashboard.py` aggregates those snapshots into the rendered dashboard. See `skill-monitor/README.md` for details.

## History

`delegate-to-tom` previously lived as a standalone user skill at `~/.claude/skills/delegate-to-tom/` with `name: rhize:delegate-to-tom`. The colon in a non-plugin skill name caused different runtimes to record it under three different names (`rhize:delegate-to-tom`, `rhizedelegate-to-tom`, `anthropic-skills:rhizedelegate-to-tom`), fragmenting usage analytics. Moving it into this plugin with a plain `delegate-to-tom` slug yields one stable, plugin-derived namespace: `rhize-ops:delegate-to-tom`.
