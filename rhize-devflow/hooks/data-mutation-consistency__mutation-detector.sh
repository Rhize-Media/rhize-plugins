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

# Read user prompt from stdin. The payload is JSON with a "prompt" field;
# extract it via real JSON parsing rather than keyword-matching the whole raw
# payload (the previous approach), which risked false positives against
# non-prompt fields (session_id, cwd, etc.) and -- had it ever needed to
# extract a delimited field with grep/sed -- would have silently mis-detected
# escaped-quote content the way the sibling prewrite-check.sh hook did
# (reproduced 2026-08-04).
RAW_INPUT=$(cat)
USER_PROMPT=$(printf '%s' "$RAW_INPUT" | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    print("")
else:
    print(data.get("prompt") or "")
')

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
  • `@analyze-mutations` - Full codebase mutation analysis
  • `@check-mutation [file]` - Check specific file

This will help identify missing cache revalidation, error handling, or optimistic update patterns.
</user-prompt-submit-hook>
EOF
    fi
fi

exit 0
