#!/bin/sh
# fake_claude.sh — stub for the real `claude` binary, used by
# tests/rhize-ops/test_plugin_prune.py via PLUGIN_PRUNE_CLAUDE_BIN so no test
# ever invokes the real CLI. Records its argv (one space-joined line) to the
# file named by $FAKE_CLAUDE_LOG, then exits with $FAKE_CLAUDE_EXIT (default 0).
set -eu
: "${FAKE_CLAUDE_LOG:?FAKE_CLAUDE_LOG must be set}"
echo "$*" >> "$FAKE_CLAUDE_LOG"
exit "${FAKE_CLAUDE_EXIT:-0}"
