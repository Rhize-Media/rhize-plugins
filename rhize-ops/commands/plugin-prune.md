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
2. Generate a fresh skill-forge plugin audit into that temp file (needs `@rhize/skill-forge`
   0.17 or newer for `audit`, or 0.18+ for `routine` JSON. Version 0.17 first added `--claude-plugins` and the `plugins[]` report
   section; an older audit has no `plugins` array and step 3 refuses it with a message naming
   the required version):
   ```bash
   npx -y @rhize/skill-forge@latest audit --yes --claude-plugins \
     --usage-snapshot "$MONITOR_ROOT/data/snapshots" --json > "$TMP_AUDIT"
   ```
3. Run the advisor against that report and the latest 4 snapshots (historical samples, not four elapsed weeks):
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/plugin_prune.py" \
     --audit "$TMP_AUDIT" --snapshots "$MONITOR_ROOT/data/snapshots" --snapshot-count 4
   ```
4. Present the table to the user as-is. Ask which plugins, if any, they want disabled — do not
   pick for them.
5. Only for plugins the user explicitly names, run the same command again with
   `--apply --disable <id>` (repeatable) **in the user's own terminal**, so the script's own
   `type yes to confirm` prompt is answered by the user, not simulated. `--apply` refuses without
   a real TTY.

## What this does and does not do

- **Advisory only.** `recommendation`/`reasons` come straight from the skill-forge audit; this
  command never computes a verdict of its own beyond the snapshot-unobserved counts.
- **Dormancy is only ever reported from *exhaustive* snapshots** — one whose `skill_totals` field
  (or an uncapped `top_skills`) covers every skill that fired, not just the top 50. A plugin
  missing from a capped snapshot is not proof it went unused; the table says how many of the
  selected snapshots were skipped as non-exhaustive.
- **Skill telemetry says nothing about a plugin's hooks, agents, commands, or MCP servers.** A plugin
  can be doing real work (a hook, a background MCP server) with zero Skill-tool invocations —
  "unobserved" describes skill usage only, not the plugin as a whole.
- **Nothing is disabled without you.** Without `--apply` the script only reports. With
  `--apply --disable <id>`, each id still needs a typed `yes` per plugin before
  `claude plugin disable <id> --scope user` runs.

## Input shape (the contract `plugin_prune.py` validates)

A skill-forge `audit --json`/`routine --json` document with `"schemaVersion": 1` and a
`plugins` array; each entry is
`{ pluginId: "<plugin>@<marketplace>", version, installPath, skillCount,
findingCounts: { LOW, MEDIUM, HIGH, CRITICAL }, observedSkillCount?,
recommendation: "keep" | "review" | "unobserved" | "unknown", reasons: string[] }`.
The fixture at `tests/rhize-ops/fixtures/plugin_prune/audit.json` is the reference example.
Every string is control-character-stripped on load, and `pluginId`s are cross-referenced against
the user-scope `~/.claude/settings.json` `enabledPlugins` (`--settings` overrides the path).


Snapshot history uses `--snapshot-count N` (`--weeks` remains a legacy alias). Output schema
`rhize-plugin-prune-v2` uses `snapshotsUnobserved`/`snapshotsTotal`, reports each selected window's
timestamp and duration, and includes telemetry scope in JSON. Overlapping or old samples are
not weeks of inactivity. Invalid, incomplete, bare-key or wholly unjoinable snapshots cannot
establish dormancy; same plugin names across marketplaces remain unknown. Failed disable
subprocesses return exit 2 while remaining requested IDs still get their own confirmation.
