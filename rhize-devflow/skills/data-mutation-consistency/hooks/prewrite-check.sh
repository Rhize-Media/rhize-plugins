#!/bin/bash
# Pre-Write Mutation Check Hook
# Trigger: PreToolUse (Write, Edit)
# Purpose: Check mutations in files being written/edited for consistency
#
# 🪝 AUTO-TRIGGERED by Claude Code hooks system
# Configure in .claude/settings.json:
# {
#   "hooks": {
#     "PreToolUse": [{
#       "type": "command",
#       "command": ".claude/hooks/prewrite-check.sh",
#       "toolNames": ["Write", "Edit"]
#     }]
#   }
# }

# Read tool call info from stdin (JSON format)
TOOL_INPUT=$(cat)

# Extract file path from the tool input
FILE_PATH=$(echo "$TOOL_INPUT" | grep -oP '"file_path"\s*:\s*"\K[^"]+' 2>/dev/null || echo "")

# If no file path found, try alternate formats
if [ -z "$FILE_PATH" ]; then
    FILE_PATH=$(echo "$TOOL_INPUT" | grep -oP '"path"\s*:\s*"\K[^"]+' 2>/dev/null || echo "")
fi

# Exit if no file path
if [ -z "$FILE_PATH" ]; then
    exit 0
fi

# Only check TypeScript files
if [[ ! "$FILE_PATH" =~ \.(ts|tsx)$ ]]; then
    exit 0
fi

# Check if file is in relevant directories
RELEVANT_DIRS=(
    "actions"
    "api"
    "hooks"
    "mutations"
    "collections"
    "payload"
)

IS_RELEVANT=false
for dir in "${RELEVANT_DIRS[@]}"; do
    if echo "$FILE_PATH" | grep -qi "/$dir/\|/$dir$"; then
        IS_RELEVANT=true
        break
    fi
done

# Also check for mutation-related file names
if echo "$FILE_PATH" | grep -qiE "(mutation|action|update|create|delete|upsert)"; then
    IS_RELEVANT=true
fi

if [ "$IS_RELEVANT" = false ]; then
    exit 0
fi

# Extract content being written (if available)
CONTENT=$(echo "$TOOL_INPUT" | grep -oP '"content"\s*:\s*"\K[^"]+' 2>/dev/null || echo "")
if [ -z "$CONTENT" ]; then
    CONTENT=$(echo "$TOOL_INPUT" | grep -oP '"new_string"\s*:\s*"\K[^"]+' 2>/dev/null || echo "")
fi

# Check for Supabase mutations
if echo "$CONTENT" | grep -qE "supabase.*\.(insert|update|delete|upsert)"; then

    # Check for error handling
    HAS_ERROR_HANDLING=false
    if echo "$CONTENT" | grep -qE "(error|Error|try\s*\{|catch)"; then
        HAS_ERROR_HANDLING=true
    fi

    # Check for cache revalidation
    HAS_REVALIDATION=false
    if echo "$CONTENT" | grep -qE "revalidate(Tag|Path)"; then
        HAS_REVALIDATION=true
    fi

    # Warn if missing elements
    WARNINGS=""

    if [ "$HAS_ERROR_HANDLING" = false ]; then
        WARNINGS="$WARNINGS\n  ⚠️ Missing error handling for Supabase mutation"
    fi

    if [ "$HAS_REVALIDATION" = false ]; then
        # Only warn for server actions
        if echo "$CONTENT" | grep -q "'use server'\|\"use server\""; then
            WARNINGS="$WARNINGS\n  ⚠️ Server action missing cache revalidation (revalidateTag/revalidatePath)"
        fi
    fi

    if [ -n "$WARNINGS" ]; then
        cat << EOF
<pre-tool-use-hook>
🔍 Mutation pattern check for: $(basename "$FILE_PATH")
$WARNINGS

Consider running \`@check-mutation $FILE_PATH\` after editing.
</pre-tool-use-hook>
EOF
    fi
fi

# Check for React Query mutations
if echo "$CONTENT" | grep -qE "useMutation\s*\("; then

    WARNINGS=""

    # Check for query key factory
    if ! echo "$CONTENT" | grep -qE "\w+Keys\."; then
        WARNINGS="$WARNINGS\n  ⚠️ Consider using query key factory instead of inline keys"
    fi

    # Check for onError
    if ! echo "$CONTENT" | grep -q "onError"; then
        WARNINGS="$WARNINGS\n  ⚠️ Missing onError handler"
    fi

    # Check for onSettled
    if ! echo "$CONTENT" | grep -q "onSettled"; then
        WARNINGS="$WARNINGS\n  ⚠️ Missing onSettled for cache invalidation"
    fi

    if [ -n "$WARNINGS" ]; then
        cat << EOF
<pre-tool-use-hook>
🔍 React Query mutation check for: $(basename "$FILE_PATH")
$WARNINGS

Run \`@check-mutation $FILE_PATH\` for detailed analysis.
</pre-tool-use-hook>
EOF
    fi
fi

# Check for Payload collections
if echo "$CONTENT" | grep -qE "CollectionConfig\s*="; then

    WARNINGS=""

    # Check for hooks
    if echo "$CONTENT" | grep -qE "hooks\s*:\s*\{\s*\}"; then
        WARNINGS="$WARNINGS\n  ⚠️ Empty hooks object - add afterChange and afterDelete for cache invalidation"
    fi

    # Check for afterChange
    if ! echo "$CONTENT" | grep -q "afterChange"; then
        WARNINGS="$WARNINGS\n  ⚠️ Missing afterChange hook for cache invalidation"
    fi

    # Check for afterDelete
    if ! echo "$CONTENT" | grep -q "afterDelete"; then
        WARNINGS="$WARNINGS\n  ⚠️ Missing afterDelete hook - deleted records may leave stale cache"
    fi

    if [ -n "$WARNINGS" ]; then
        cat << EOF
<pre-tool-use-hook>
🔍 Payload collection check for: $(basename "$FILE_PATH")
$WARNINGS

Run \`@check-mutation $FILE_PATH\` for detailed analysis.
</pre-tool-use-hook>
EOF
    fi
fi

exit 0
