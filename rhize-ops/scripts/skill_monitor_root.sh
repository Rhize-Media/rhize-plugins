#!/bin/sh
# skill_monitor_root.sh — resolve the standalone rhize-skill-monitor tool's
# checkout root, for skills that used to find monitor.py bundled at
# ${CLAUDE_PLUGIN_ROOT}/skill-monitor/.
#
# The skill-usage monitor (monitor.py, dashboard.py, benchmark_status.py, ...)
# was extracted with its history to Rhize-Media/rhize-skill-monitor so it can
# be updated independently of this marketplace. This script is the one place
# that knows where a local checkout is expected to live, so no skill hardcodes
# that path.
#
# Usage:
#   MONITOR_ROOT="$("${CLAUDE_PLUGIN_ROOT}/scripts/skill_monitor_root.sh")" || exit $?
#   python3 "$MONITOR_ROOT/dashboard.py" ...
#
# RESOLUTION
#   1. $RHIZE_SKILL_MONITOR_ROOT, if set.
#   2. Otherwise $HOME/dev-local/RHIZE/rhize-skill-monitor.
#
# On success: prints the resolved root to stdout, exit 0.
# On failure (root/monitor.py does not exist): prints a fix-it message to
# stderr naming the clone command and the env var override, exit 78 (EX_CONFIG).
#
# POSIX sh on purpose: this runs on macOS and Linux with no bash dependency.

set -eu

SELF="skill_monitor_root.sh"

ROOT="${RHIZE_SKILL_MONITOR_ROOT:-${HOME}/dev-local/RHIZE/rhize-skill-monitor}"

if [ -f "$ROOT/monitor.py" ]; then
    printf '%s\n' "$ROOT"
    exit 0
fi

{
    echo "$SELF: rhize-skill-monitor not found at: $ROOT"
    echo
    echo "  This tool lives in a standalone repo, not bundled in rhize-ops. Fix it"
    echo "  with EITHER of these:"
    echo
    echo "  (a) Clone it to the default location:"
    echo "        git clone https://github.com/Rhize-Media/rhize-skill-monitor.git \"$ROOT\""
    echo
    echo "  (b) Point at an existing checkout:"
    echo "        export RHIZE_SKILL_MONITOR_ROOT=/path/to/rhize-skill-monitor"
} >&2

exit 78 # EX_CONFIG
