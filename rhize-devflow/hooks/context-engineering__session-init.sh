#!/bin/bash
# Session Initialization Hook (Generalized)
# Runs at session start to load context and check freshness
#
# INSTALLATION:
# 1. Copy to your project: .claude/hooks/session-init.sh
# 2. Make executable: chmod +x .claude/hooks/session-init.sh
# 3. Configure in .claude/settings.json:
#    {
#      "hooks": {
#        "SessionStart": [{
#          "type": "command",
#          "command": ".claude/hooks/session-init.sh"
#        }]
#      }
#    }

set -e

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
PROJECT_NAME=$(basename "$PROJECT_DIR")

# Configurable file names (override via environment)
SPRINT_FILE="${CONTEXT_SPRINT_FILE:-CURRENT_SPRINT.md}"
REGISTRY_FILE="${CONTEXT_REGISTRY_FILE:-COMPONENT_REGISTRY.md}"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🚀 Session Initialized: $PROJECT_NAME"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Check sprint/context file freshness
check_freshness() {
  local file="$1"
  local name="$2"
  
  if [ -f "$PROJECT_DIR/$file" ]; then
    if [[ "$OSTYPE" == "darwin"* ]]; then
      FILE_MOD=$(stat -f %m "$PROJECT_DIR/$file" 2>/dev/null)
    else
      FILE_MOD=$(stat -c %Y "$PROJECT_DIR/$file" 2>/dev/null)
    fi

    NOW=$(date +%s)
    HOURS_AGO=$(( (NOW - FILE_MOD) / 3600 ))

    if [ "$HOURS_AGO" -gt 24 ]; then
      echo "⚠️  $name not updated in ${HOURS_AGO} hours"
    else
      echo "✅ $name is current (${HOURS_AGO}h ago)"
    fi
  fi
}

check_freshness "$SPRINT_FILE" "$SPRINT_FILE"
check_freshness "$REGISTRY_FILE" "$REGISTRY_FILE"

# Show active work item if sprint file exists
if [ -f "$PROJECT_DIR/$SPRINT_FILE" ]; then
  ACTIVE_ITEM=$(grep -A1 "Primary Work Item\|Active Work\|Current Task" "$PROJECT_DIR/$SPRINT_FILE" 2>/dev/null | tail -1 | sed 's/^[- ]*//' || echo "")
  if [ -n "$ACTIVE_ITEM" ] && [ "$ACTIVE_ITEM" != "--" ]; then
    echo "📋 Active: $ACTIVE_ITEM"
  fi
fi

# Check for uncommitted changes
UNCOMMITTED=$(git -C "$PROJECT_DIR" status --porcelain 2>/dev/null | wc -l | tr -d ' ')
if [ "$UNCOMMITTED" -gt 0 ]; then
  echo "📝 Uncommitted changes: $UNCOMMITTED files"
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

exit 0
