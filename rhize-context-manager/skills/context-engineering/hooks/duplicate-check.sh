#!/bin/bash
# Duplicate Component Detection Hook (Generalized)
# BLOCKS creation of new components/hooks/utilities if similar exists
#
# INSTALLATION:
# 1. Copy to your project: .claude/hooks/duplicate-check.sh
# 2. Make executable: chmod +x .claude/hooks/duplicate-check.sh
# 3. Configure in .claude/settings.json:
#    {
#      "hooks": {
#        "PreToolUse": [{
#          "type": "command",
#          "command": ".claude/hooks/duplicate-check.sh",
#          "toolNames": ["write_file", "create_file"]
#        }]
#      }
#    }
#
# REQUIRES: COMPONENT_REGISTRY.md in project root (or configured path)

set -e

# Read JSON input from stdin
INPUT=$(cat)

# Extract file_path from tool input
FILE_PATH=$(echo "$INPUT" | grep -o '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed 's/"file_path"[[:space:]]*:[[:space:]]*"\([^"]*\)"/\1/' || echo "")

# If no file path found, allow
if [ -z "$FILE_PATH" ]; then
  exit 0
fi

# Configurable patterns (override via environment)
CHECK_PATTERNS="${DUPLICATE_CHECK_PATTERNS:-components/|lib/hooks/|lib/utilities/|lib/actions/|src/components/|src/hooks/}"
REGISTRY_FILE="${COMPONENT_REGISTRY_FILE:-COMPONENT_REGISTRY.md}"

# Only check paths matching our patterns
if ! echo "$FILE_PATH" | grep -qE "($CHECK_PATTERNS)"; then
  exit 0
fi

# Skip if file already exists (this is an edit, not new file)
if [ -f "$FILE_PATH" ]; then
  exit 0
fi

# Get project directory
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
REGISTRY="$PROJECT_DIR/$REGISTRY_FILE"

# If no registry, allow (registry not set up yet)
if [ ! -f "$REGISTRY" ]; then
  exit 0
fi

# Extract component/hook name from path
FILENAME=$(basename "$FILE_PATH")
NAME_NO_EXT=$(echo "$FILENAME" | sed 's/\.[^.]*$//' | sed 's/\..*$//')

# Convert to searchable patterns (handle kebab-case, PascalCase, camelCase)
SEARCH_PATTERN=$(echo "$NAME_NO_EXT" | sed 's/[-_]/ /g' | sed 's/\([a-z]\)\([A-Z]\)/\1 \2/g' | tr '[:upper:]' '[:lower:]' | tr ' ' '.*')

# Search registry for similar names
MATCHES=$(grep -i "$SEARCH_PATTERN" "$REGISTRY" 2>/dev/null | grep -v "^#" | head -5 || echo "")

if [ -n "$MATCHES" ]; then
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" >&2
  echo "❌ BLOCKED: Potential duplicate component detected" >&2
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" >&2
  echo "" >&2
  echo "Creating: $FILENAME" >&2
  echo "Pattern:  $SEARCH_PATTERN" >&2
  echo "" >&2
  echo "Similar items in $REGISTRY_FILE:" >&2
  echo "$MATCHES" | while read -r line; do
    echo "  → $line" >&2
  done
  echo "" >&2
  echo "ACTION REQUIRED:" >&2
  echo "  1. Check if existing component can be reused" >&2
  echo "  2. If truly new, use a more distinct name" >&2
  echo "  3. Or explicitly confirm this is intentional" >&2
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" >&2
  exit 2  # BLOCKING ERROR
fi

exit 0
