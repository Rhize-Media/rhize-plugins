#!/bin/sh
# session-start-env.sh — SessionStart hook: export this plugin's root to the Bash tool.
#
# WHY. Claude Code substitutes `${CLAUDE_PLUGIN_ROOT}` into plugin *config text* (commands,
# hooks, MCP definitions) when it loads a plugin. It does NOT export that variable into the
# Bash tool's shell environment — measured 2026-09-15 inside `claude plugin eval` and in an
# ordinary session: `echo "${CLAUDE_PLUGIN_ROOT:-unset}"` prints `unset`. So any shell command
# that names the launcher through the variable silently expands to `/scripts/...` and fails
# with 127. The slash commands are unaffected (their text is substituted at load time); prose
# guidance and eval prompts that reach the launcher from Bash are the ones that break.
#
# HOW. Hook processes DO receive CLAUDE_PLUGIN_ROOT, and SessionStart hooks also receive
# CLAUDE_ENV_FILE — a per-session script that Claude Code loads into the environment of every
# later Bash tool call. This hook appends one `export` line to that file. The name is
# plugin-specific on purpose (several plugins load at once; overwriting CLAUDE_PLUGIN_ROOT
# would be wrong for all of them).
#
#   "$PROCEDURAL_MEMORY_PLUGIN_ROOT/scripts/rhize-skill-launcher.sh" recall "<task>"
#
# CONTRACT. Advisory-only: exits 0 in every case, writes nothing but the one export line,
# never touches the registry or the CLI, no subprocess heavier than `pwd`. When
# CLAUDE_ENV_FILE is absent (any other hook event, or a host without the mechanism) it does
# nothing. POSIX sh — no bashisms; tests run it under /bin/sh and dash.

# Resolve the root: the runner's CLAUDE_PLUGIN_ROOT when present, else this script's parent
# directory (hooks/ sits directly under the plugin root), so the value is right even if the
# variable is ever withheld from hook processes.
if [ -n "${CLAUDE_PLUGIN_ROOT:-}" ]; then
    root="$CLAUDE_PLUGIN_ROOT"
else
    root=$(cd "$(dirname "$0")/.." 2>/dev/null && pwd -P) || exit 0
fi

[ -n "${CLAUDE_ENV_FILE:-}" ] || exit 0

# Single-quote for the shell that will source this file; the only character that needs care
# inside single quotes is the single quote itself: ' -> '\''
escaped=$(printf '%s' "$root" | sed "s/'/'\\\\''/g")
printf "export PROCEDURAL_MEMORY_PLUGIN_ROOT='%s'\n" "$escaped" >> "$CLAUDE_ENV_FILE" 2>/dev/null || exit 0
exit 0
