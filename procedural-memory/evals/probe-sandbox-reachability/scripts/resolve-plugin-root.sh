#!/bin/sh
# resolve-plugin-root.sh — scaffold_script for the probe-sandbox-reachability case.
#
# `${CLAUDE_PLUGIN_ROOT}` is substituted into plugin *config text* (commands, hooks, MCP) when
# Claude Code loads a plugin; it is NOT exported into the Bash tool's environment. The first real
# run of this suite (2026-09-15) proved that: the launcher probe expanded to
# `/scripts/rhize-skill-launcher.sh` and exited 127 without measuring anything.
#
# This scaffold runs before the agent starts and records the plugin root — resolved from this
# script's own location (case/scripts/ -> case -> evals/ -> plugin) — into the sandbox HOME, so
# the prompt can reach the real launcher by an absolute path without hardcoding this machine's
# checkout. If the harness copies the case directory elsewhere, the recorded path will not hold
# a plugin manifest and the probe reports that instead of silently probing the wrong file.

set -eu

ROOT=$(cd "$(dirname "$0")/../../.." && pwd -P)
printf '%s\n' "$ROOT" > "$HOME/.probe-plugin-root"

if [ -f "$ROOT/.claude-plugin/plugin.json" ]; then
    echo "plugin root recorded: $ROOT (manifest present)"
else
    echo "plugin root recorded: $ROOT (WARNING: no .claude-plugin/plugin.json there)"
fi
