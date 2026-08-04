#!/bin/bash
#
# refinement-detector.sh - Detect skill refinement opportunities from user prompts
#
# This hook listens for keywords indicating the user wants to refine a skill.
# When detected, it suggests running `npx @rhize/skill-forge refine`.
#
# Installation:
#   Add to your .claude/settings.json hooks section:
#   {
#     "hooks": {
#       "user_prompt_submit": "<path-to-this-file>/refinement-detector.sh"
#     }
#   }
#
# Note: skill refinement now ships as `skill-forge refine` in the @rhize/skill-forge
# npm package — the rhize-meta plugin is retired.
#
# Usage:
#   This hook is triggered automatically on user prompt submission.
#   It reads the prompt from stdin.

set -e

# Read the prompt from stdin. The payload is JSON with a "prompt" field;
# extract it via real JSON parsing rather than treating the whole raw stdin
# as the prompt text (the previous line-concatenation loop) -- avoids
# matching keywords against non-prompt JSON fields and correctly decodes
# escaped quotes/newlines in the prompt content (reproduced 2026-08-04 on the
# sibling prewrite-check.sh hook, same underlying grep/sed-scraping class).
RAW_INPUT=$(cat)
PROMPT=$(printf '%s' "$RAW_INPUT" | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    print("")
else:
    print(data.get("prompt") or "")
')

# Convert to lowercase for matching
PROMPT_LOWER=$(echo "$PROMPT" | tr '[:upper:]' '[:lower:]')

# Keywords that indicate refinement opportunity
REFINEMENT_KEYWORDS=(
    "skill doesn't work"
    "skill doesnt work"
    "skill should have"
    "missing trigger"
    "should have caught"
    "why didn't skill"
    "why didnt skill"
    "skill broke"
    "skill broken"
    "improve skill"
    "extend skill"
    "add to skill"
    "skill missed"
    "false positive"
    "false negative"
    "hook doesn't"
    "hook doesnt"
    "hook should"
    "wrong behavior"
    "unexpected behavior"
)

# Check for keyword matches
MATCHED=""
for keyword in "${REFINEMENT_KEYWORDS[@]}"; do
    if echo "$PROMPT_LOWER" | grep -qF "$keyword"; then
        MATCHED="$keyword"
        break
    fi
done

# If a refinement keyword was found, output suggestion
if [ -n "$MATCHED" ]; then
    cat << 'EOF'
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💡 Skill Refinement Opportunity Detected
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

It looks like you've encountered an issue with a skill.
Would you like to capture this as a refinement?

Run: npx @rhize/skill-forge refine

This will help:
  • Document the expected vs actual behavior
  • Create a project-specific override
  • Track the pattern for potential generalization

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EOF
fi

# Always exit success (don't block the prompt)
exit 0
