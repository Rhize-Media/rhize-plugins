#!/bin/bash
#
# refinement-detector.sh - Detect skill refinement opportunities from user prompts
#
# This hook listens for keywords indicating the user wants to refine a skill.
# When detected, it suggests running /refine-skills.
#
# Installation:
#   Add to your .claude/settings.json hooks section:
#   {
#     "hooks": {
#       "user_prompt_submit": "skill-refinement/hooks/refinement-detector.sh"
#     }
#   }
#
# Usage:
#   This hook is triggered automatically on user prompt submission.
#   It reads the prompt from stdin.

set -e

# Read the prompt from stdin
PROMPT=""
while IFS= read -r line; do
    PROMPT="$PROMPT$line"
done

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

Run: /refine-skills

This will help:
  • Document the expected vs actual behavior
  • Create a project-specific override
  • Track the pattern for potential generalization

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EOF
fi

# Always exit success (don't block the prompt)
exit 0
