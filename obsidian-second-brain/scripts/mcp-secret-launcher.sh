#!/bin/sh
# mcp-secret-launcher.sh — portable shim for supplying secrets to this plugin's
# MCP server without ever writing a secret into a plugin file.
#
# Usage (from .mcp.json):
#   "command": "${CLAUDE_PLUGIN_ROOT}/scripts/mcp-secret-launcher.sh",
#   "args": ["VAR_NAME", "--", "npx", "some-mcp-server"]
#
# WHY THIS EXISTS
# ---------------
# An MCP config may write "env": { "API_KEY": "${API_KEY}" }. Claude Code
# substitutes ${VAR} from its OWN process environment when the config loads.
# That works only if the variable happens to be present in whatever environment
# Claude Code was started with. When it is absent, Claude Code passes the
# LITERAL string "${API_KEY}" through to the server, which then authenticates
# with that string and fails with a confusing 401/403 — while a perfectly valid
# credential may be sitting in the OS keychain.
#
# Because "is the variable present" depends on how Claude Code was launched,
# ${VAR} in an MCP config is not a reliable way to deliver a secret. This shim
# removes that dependence.
#
# RESOLUTION ORDER
#   1. `mcp-secret-launcher` on PATH, else ~/.local/bin/mcp-secret-launcher.
#      That tool reads each VAR from the login keychain (service
#      "claude-code:VAR") and exports it into this one child process only.
#   2. No launcher installed? Fall back to plain environment inheritance: if
#      every required variable is already exported, run the server with it.
#   3. Neither available? Exit with a message naming the missing variables and
#      how to supply them. We never launch a server we know is unauthenticated,
#      because that surfaces as a confusing runtime 401 instead of a setup error.
#
# POSIX sh on purpose: this runs on macOS, Linux, and inside Claude Cowork.
# It never reads, writes, logs, or echoes a secret value.

set -eu

SELF="mcp-secret-launcher.sh"

# --- split args at the `--` separator ---------------------------------------
VARS=""
while [ "$#" -gt 0 ]; do
    if [ "$1" = "--" ]; then
        shift
        break
    fi
    VARS="$VARS $1"
    shift
done

if [ "$#" -eq 0 ]; then
    echo "$SELF: no command given." >&2
    echo "  usage: $SELF VAR_NAME [VAR_NAME ...] -- command [args ...]" >&2
    exit 78 # EX_CONFIG
fi

# --- 1. prefer the real launcher --------------------------------------------
LAUNCHER=""
if command -v mcp-secret-launcher >/dev/null 2>&1; then
    LAUNCHER=$(command -v mcp-secret-launcher)
elif [ -x "${HOME:-}/.local/bin/mcp-secret-launcher" ]; then
    LAUNCHER="${HOME}/.local/bin/mcp-secret-launcher"
fi

if [ -n "$LAUNCHER" ]; then
    # Word-splitting $VARS is intentional; entries are shell identifiers.
    # shellcheck disable=SC2086
    exec "$LAUNCHER" $VARS -- "$@"
fi

# --- 2. fall back to plain environment inheritance --------------------------
MISSING=""
for _var in $VARS; do
    eval "_present=\${$_var:-}"
    if [ -z "${_present:-}" ]; then
        MISSING="$MISSING $_var"
    fi
done
unset _present

if [ -z "$MISSING" ]; then
    exec "$@"
fi

# --- 3. refuse to start unauthenticated -------------------------------------
{
    echo "$SELF: cannot start this MCP server - required credentials are unavailable."
    echo
    echo "  Missing variable(s):$MISSING"
    echo
    echo "  'mcp-secret-launcher' was not found on PATH or at ~/.local/bin, and the"
    echo "  variable(s) above are not present in the environment, so there is no way"
    echo "  to authenticate. Starting anyway would fail later as an opaque 401."
    echo
    echo "  Fix it with EITHER of these:"
    echo
    echo "  (a) Export the variable(s) in the environment Claude Code is launched from:"
    for _var in $MISSING; do
        echo "        export $_var=..."
    done
    echo
    echo "  (b) macOS - store them in the login keychain and install the launcher"
    echo "      (see docs/mcp-secret-launcher.md in the rhize-plugins repo):"
    for _var in $MISSING; do
        echo "        security add-generic-password -a \"\$USER\" -s \"claude-code:$_var\" -l \"$_var\" -U -w"
    done
    echo
    echo "  Never paste a secret into .mcp.json or any other file in this plugin."
} >&2

exit 78 # EX_CONFIG
