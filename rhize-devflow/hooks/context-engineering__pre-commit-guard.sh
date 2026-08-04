#!/bin/bash
# Pre-Commit Impact Analysis Guard (Generalized)
# Warns if related files aren't staged with changes
#
# INSTALLATION:
# 1. Copy to your project: .claude/hooks/pre-commit-guard.sh
# 2. Make executable: chmod +x .claude/hooks/pre-commit-guard.sh
# 3. Configure in .claude/settings.json:
#    {
#      "hooks": {
#        "PreToolUse": [{
#          "type": "command",
#          "command": ".claude/hooks/pre-commit-guard.sh",
#          "toolNames": ["bash"]
#        }]
#      }
#    }

set -e

# Read JSON input from stdin
INPUT=$(cat)

# Extract the bash command from tool input
COMMAND=$(echo "$INPUT" | grep -o '"command"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed 's/"command"[[:space:]]*:[[:space:]]*"\([^"]*\)"/\1/' || echo "")

# Only check git commit commands
if [[ ! "$COMMAND" =~ "git commit" ]]; then
  exit 0
fi

# Get project directory
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
cd "$PROJECT_DIR"

# Get staged files
STAGED_FILES=$(git diff --cached --name-only 2>/dev/null || echo "")

if [ -z "$STAGED_FILES" ]; then
  echo "⚠️ No files staged for commit" >&2
  exit 0
fi

# Track related files that should be checked
MISSING_RELATED=""

# Configurable patterns (override via environment)
COMPONENTS_DIR="${COMPONENTS_DIR_PATTERN:-components/}"
HOOKS_DIR="${HOOKS_DIR_PATTERN:-hooks/}"
TYPES_FILE="${TYPES_FILE_PATTERN:-types.ts|payload-types.ts|schema.ts}"

# For each staged TypeScript/TSX file, check for related files
while IFS= read -r file; do
  if [[ "$file" =~ \.(ts|tsx)$ ]]; then
    BASENAME=$(basename "$file" | sed 's/\.[^.]*$//')
    DIR=$(dirname "$file")

    # If editing a component, check for its hook
    if [[ "$file" =~ $COMPONENTS_DIR ]]; then
      # Look for hooks that might use this component
      HOOK_PATTERN=$(echo "$file" | sed "s|$COMPONENTS_DIR|$HOOKS_DIR|" | sed 's/\.tsx$/.ts/')
      if [ -f "$HOOK_PATTERN" ]; then
        if ! echo "$STAGED_FILES" | grep -q "$HOOK_PATTERN"; then
          if grep -q "$BASENAME" "$HOOK_PATTERN" 2>/dev/null; then
            MISSING_RELATED="$MISSING_RELATED\n  - $HOOK_PATTERN (may reference $BASENAME)"
          fi
        fi
      fi
    fi

    # If editing types/schema files, warn about regeneration
    if echo "$file" | grep -qE "collections/|models/|schemas/"; then
      if ! echo "$STAGED_FILES" | grep -qE "$TYPES_FILE"; then
        MISSING_RELATED="$MISSING_RELATED\n  - Check if types need regeneration"
      fi
    fi
  fi
done <<< "$STAGED_FILES"

# If missing related files found, show warning
if [ -n "$MISSING_RELATED" ]; then
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" >&2
  echo "⚠️  IMPACT ANALYSIS: Related files not staged" >&2
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" >&2
  echo -e "$MISSING_RELATED" >&2
  echo "" >&2
  echo "Review these to ensure changes are complete." >&2
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" >&2
  # Warning only - don't block
  exit 0
fi

exit 0
