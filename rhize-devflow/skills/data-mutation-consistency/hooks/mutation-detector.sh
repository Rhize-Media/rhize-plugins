#!/bin/bash
# Mutation Detector Hook
# Trigger: UserPromptSubmit
# Purpose: Detect mutation-related keywords and suggest analysis
#
# 🪝 AUTO-TRIGGERED by Claude Code hooks system
# Configure in .claude/settings.json:
# {
#   "hooks": {
#     "UserPromptSubmit": [{
#       "type": "command",
#       "command": ".claude/hooks/mutation-detector.sh"
#     }]
#   }
# }

# Read user prompt from stdin
USER_PROMPT=$(cat)

# Mutation-related keywords
MUTATION_KEYWORDS=(
    "mutation"
    "cache"
    "revalidate"
    "stale data"
    "stale cache"
    "out of sync"
    "data mismatch"
    "invalidate"
    "optimistic"
    "rollback"
    "useMutation"
    "afterChange"
    "afterDelete"
    "server action"
)

# Analysis trigger keywords
ANALYSIS_TRIGGERS=(
    "@analyze-mutations"
    "@check-mutation"
    "@mutation-report"
    "@fix-mutations"
    "/rhize-devflow:mutation"
)

# Check for explicit analysis triggers (let them through)
for trigger in "${ANALYSIS_TRIGGERS[@]}"; do
    if echo "$USER_PROMPT" | grep -qi "$trigger"; then
        exit 0
    fi
done

# Check for mutation keywords
DETECTED_KEYWORDS=""
for keyword in "${MUTATION_KEYWORDS[@]}"; do
    if echo "$USER_PROMPT" | grep -qi "$keyword"; then
        DETECTED_KEYWORDS="$DETECTED_KEYWORDS $keyword"
    fi
done

# If mutation keywords detected, suggest analysis
if [ -n "$DETECTED_KEYWORDS" ]; then
    # Check if discussing an error/bug
    if echo "$USER_PROMPT" | grep -qiE "bug|error|issue|problem|broken|not working|doesn't work"; then
        cat << 'EOF'
<user-prompt-submit-hook>
🔍 Mutation-related issue detected. Consider running:
  • `/rhize-devflow:mutation-check --all` - Full codebase mutation analysis (formerly @analyze-mutations)
  • `/rhize-devflow:mutation-check [file]` - Check specific file (formerly @check-mutation)

This will help identify missing cache revalidation, error handling, or optimistic update patterns.
</user-prompt-submit-hook>
EOF
    fi
fi

exit 0
