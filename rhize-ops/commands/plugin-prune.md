---
description: Report-first plugin-prune advisor — cross-references a skill-forge plugin audit with skill-monitor usage snapshots, then optionally disables what you pick
---

# /rhize-ops:plugin-prune

Advisory table of every enabled Claude Code plugin — recommendation, active HIGH/CRITICAL
findings, and how many recent skill-monitor snapshots never observed the plugin's skills fire —
built from a `@rhize/skill-forge` plugin audit plus optional usage history. Wraps
`scripts/plugin_prune.py`. It never writes `~/.claude/settings.json`; the only mutating step is
an explicit, per-plugin confirmed `claude plugin disable <id> --scope user`.

## Steps

1. Resolve the standalone `rhize-skill-monitor` checkout and a scratch file for the audit:
   ```bash
   MONITOR_ROOT="$("${CLAUDE_PLUGIN_ROOT}/scripts/skill_monitor_root.sh")" || exit $?
   TMP_AUDIT="$(mktemp -t plugin-prune-audit)"
   ```
2. Generate a fresh skill-forge plugin audit into that temp file:
   ```bash
   npx -y @rhize/skill-forge@0.17 audit --yes --claude-plugins \
     --usage-snapshot "$MONITOR_ROOT/data/snapshots" --json > "$TMP_AUDIT"
   ```
3. Run the advisor against that report and the last 4 weeks of snapshots:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/plugin_prune.py" \
     --audit "$TMP_AUDIT" --snapshots "$MONITOR_ROOT/data/snapshots" --weeks 4
   ```
4. Present the table to the user as-is. Ask which plugins, if any, they want disabled — do not
   pick for them.
5. Only for plugins the user explicitly names, run the same command again with
   `--apply --disable <id>` (repeatable) **in the user's own terminal**, so the script's own
   `type yes to confirm` prompt is answered by the user, not simulated. `--apply` refuses without
   a real TTY.

## What this does and does not do

- **Advisory only.** `recommendation`/`reasons` come straight from the skill-forge audit; this
  command never computes a verdict of its own beyond the weeks-unobserved counts.
- **Dormancy is only ever reported from *exhaustive* snapshots** — one whose `skill_totals` field
  (or an uncapped `top_skills`) covers every skill that fired, not just the top 50. A plugin
  missing from a capped snapshot is not proof it went unused; the table says how many of the
  selected snapshots were skipped as non-exhaustive.
- **Skill telemetry says nothing about a plugin's hooks, commands, or MCP servers.** A plugin
  can be doing real work (a hook, a background MCP server) with zero Skill-tool invocations —
  "unobserved" describes skill usage only, not the plugin as a whole.
- **Nothing is disabled without you.** Without `--apply` the script only reports. With
  `--apply --disable <id>`, each id still needs a typed `yes` per plugin before
  `claude plugin disable <id> --scope user` runs.
