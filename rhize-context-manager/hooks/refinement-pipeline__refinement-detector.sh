#!/bin/bash
#
# refinement-detector.sh - Detect skill refinement opportunities from user prompts
#
# This hook listens for keywords indicating the user wants to refine a skill.
# When detected, it suggests running `/rhize-context-manager:learn-harvest` to
# queue the signal for triage.
#
# Installation:
#   Add to your .claude/settings.json hooks section:
#   {
#     "hooks": {
#       "user_prompt_submit": "<path-to-this-file>/refinement-pipeline__refinement-detector.sh"
#     }
#   }
#
# Note (updated 2026-08-09): skill refinement is now the gated pipeline in the
# `refinement-pipeline` skill (this plugin) — signals go through
# `/rhize-context-manager:learn-harvest` (collect) and `/skill-refine`
# (triage/run), which drives `@rhize/skill-forge evolve` under a safety re-gate.
# A bare `npx @rhize/skill-forge refine` skips that queue and re-gate.
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

Run: /rhize-context-manager:learn-harvest
Then triage it: /skill-refine review

This will help:
  • Queue the signal for human triage before any skill is touched
  • Document the expected vs actual behavior
  • Track the pattern toward a gated skill-forge evolve pass

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EOF
fi

# Always exit success (don't block the prompt)
exit 0
