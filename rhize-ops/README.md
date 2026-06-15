# rhize-ops

Rhize Media's **operations** plugin — internal delegation, hand-offs, and team-workflow automation. Distinct from `rhize-devflow` (which is about *building* software); `rhize-ops` is about *running the team*.

## Skills

### `delegate-to-tom`

Turns the work from Jim's current session into a clearly structured hand-off package for [REDACTED_NAME]. Handles the full delegation pipeline: context gathering, Fireflies transcript analysis, task formatting, Jira issue creation, and Slack notification with an @mention.

**Invoked as:** `rhize-ops:delegate-to-tom`

**Triggers:** "delegate this to the recipient", "hand this off to the recipient", "assign this to the recipient", "the recipient should handle this", or a bare "delegate"/"hand off"/"assign" where the recipient is the default recipient.

## History

`delegate-to-tom` previously lived as a standalone user skill at `~/.claude/skills/delegate-to-tom/` with `name: rhize:delegate-to-tom`. The colon in a non-plugin skill name caused different runtimes to record it under three different names (`rhize:delegate-to-tom`, `rhizedelegate-to-tom`, `anthropic-skills:rhizedelegate-to-tom`), fragmenting usage analytics. Moving it into this plugin with a plain `delegate-to-tom` slug yields one stable, plugin-derived namespace: `rhize-ops:delegate-to-tom`.
