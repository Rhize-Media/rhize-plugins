#!/bin/bash
#
# session-end.sh - Prompt for refinements after significant sessions
#
# This hook runs at the end of a session and prompts the user
# to capture any skill refinements if the session was substantial.
#
# Thresholds for prompting:
#   - > 20 tool calls
#   - > 0 errors encountered
#   - > 1 hour duration
#
# Installation:
#   Add to your .claude/settings.json hooks section:
#   {
#     "hooks": {
#       "session_end": "<path-to-this-file>/session-end.sh"
#     }
#   }
#
# Note: skill refinement now ships as `skill-forge refine` in the @rhize/skill-forge
# npm package (npx @rhize/skill-forge refine) — the rhize-meta plugin is retired.
#
# Environment variables (set by Claude Code):
#   SESSION_TOOL_CALLS - Number of tool calls in session
#   SESSION_ERRORS - Number of errors encountered
#   SESSION_DURATION - Duration in seconds
#   SESSION_FILES_TOUCHED - Number of files modified

set -e

# Get session stats from environment (with defaults)
TOOL_CALLS="${SESSION_TOOL_CALLS:-0}"
ERRORS="${SESSION_ERRORS:-0}"
DURATION="${SESSION_DURATION:-0}"
FILES_TOUCHED="${SESSION_FILES_TOUCHED:-0}"

# Thresholds for prompting
TOOL_THRESHOLD=20
ERROR_THRESHOLD=1
DURATION_THRESHOLD=3600  # 1 hour in seconds
FILES_THRESHOLD=10

# Check if session was significant
SHOULD_PROMPT=false
REASONS=""

if [ "$TOOL_CALLS" -gt "$TOOL_THRESHOLD" ]; then
    SHOULD_PROMPT=true
    REASONS="${REASONS}\n  • $TOOL_CALLS tool calls (threshold: $TOOL_THRESHOLD)"
fi

if [ "$ERRORS" -gt 0 ]; then
    SHOULD_PROMPT=true
    REASONS="${REASONS}\n  • $ERRORS errors encountered"
fi

if [ "$DURATION" -gt "$DURATION_THRESHOLD" ]; then
    SHOULD_PROMPT=true
    DURATION_MINS=$((DURATION / 60))
    REASONS="${REASONS}\n  • ${DURATION_MINS} minute session (threshold: 60)"
fi

if [ "$FILES_TOUCHED" -gt "$FILES_THRESHOLD" ]; then
    SHOULD_PROMPT=true
    REASONS="${REASONS}\n  • $FILES_TOUCHED files modified (threshold: $FILES_THRESHOLD)"
fi

# Output prompt if session was significant
if [ "$SHOULD_PROMPT" = true ]; then
    cat << EOF
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📝 Session Complete
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

This was a substantial session:
$(echo -e "$REASONS")

📊 Session Stats:
  • Tool calls: $TOOL_CALLS
  • Errors: $ERRORS
  • Files touched: $FILES_TOUCHED
  • Duration: $((DURATION / 60)) minutes

Any skill refinements to capture from this session?
  → Run: npx @rhize/skill-forge refine
  → Or say "no refinements" to skip

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EOF
fi

# Always exit success
exit 0
