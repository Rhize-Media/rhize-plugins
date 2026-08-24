#!/bin/bash
# Hook: sentry-stale-data.sh
# Type: UserPromptSubmit (advisory)
# Purpose: Detect when user is investigating Sentry issues that may be stale data related
#
# Trigger: User mentions Sentry issue URL or discusses bug investigation with stale data keywords
#
# Usage in settings.json:
# {
#   "hooks": {
#     "UserPromptSubmit": [
#       {
#         "command": "/path/to/hooks/sentry-stale-data.sh \"$PROMPT\"",
#         "advisory": true
#       }
#     ]
#   }
# }

set -euo pipefail

PROMPT="${1:-}"

# Skip if no prompt
if [ -z "$PROMPT" ]; then
    exit 0
fi

# Convert to lowercase for matching
PROMPT_LOWER=$(echo "$PROMPT" | tr '[:upper:]' '[:lower:]')

# Check for Sentry URL patterns
SENTRY_URL_PATTERN="sentry\.io/issues|sentry\.io/organizations/.*/issues"

# Check for stale data keywords
STALE_DATA_KEYWORDS="stale data|cache miss|not updating|out of sync|outdated|showing old|changes not appearing|data not refreshing|mutation.*fail|update.*not reflect"

# Check for investigation keywords combined with data issues
INVESTIGATION_KEYWORDS="bug|error|issue|problem|investigate|debug|fix"

# Determine if this looks like a stale data investigation
is_stale_data_investigation=false
is_sentry_related=false

# Check for Sentry URL
if echo "$PROMPT" | grep -qE "$SENTRY_URL_PATTERN"; then
    is_sentry_related=true
fi

# Check for stale data keywords
if echo "$PROMPT_LOWER" | grep -qE "$STALE_DATA_KEYWORDS"; then
    is_stale_data_investigation=true
fi

# Check for investigation + data keywords
if echo "$PROMPT_LOWER" | grep -qE "$INVESTIGATION_KEYWORDS" && \
   echo "$PROMPT_LOWER" | grep -qE "data|cache|update|mutation|sync"; then
    is_stale_data_investigation=true
fi

# If this looks like a stale data investigation
if [ "$is_stale_data_investigation" = true ] || [ "$is_sentry_related" = true ]; then
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🔍 STALE DATA INVESTIGATION DETECTED"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    if [ "$is_sentry_related" = true ]; then
        echo "📊 Sentry issue detected. After reviewing the error details:"
        echo ""
    fi

    echo "This may be related to data mutation consistency issues."
    echo ""
    echo "Suggested investigation steps:"
    echo ""
    echo "1. Run mutation analysis:"
    echo "   /rhize-devflow:mutation-check --all"
    echo ""
    echo "2. If specific tables are affected:"
    echo "   /rhize-devflow:mutation-check --all --focus <table_name>"
    echo ""
    echo "3. Check specific mutation files:"
    echo "   /rhize-devflow:mutation-check <file_path>"
    echo ""
    echo "Common causes of stale data:"
    echo "  • Missing revalidateTag/revalidatePath after mutations"
    echo "  • Query key factories not matching cache tags"
    echo "  • Missing error handling causing silent failures"
    echo "  • Optimistic updates without proper rollback"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
fi

# Always exit 0 for advisory hooks
exit 0
