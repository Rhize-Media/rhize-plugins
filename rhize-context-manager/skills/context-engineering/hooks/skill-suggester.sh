#!/bin/bash
# Skill Suggestion Hook (Generalized)
# Detects development keywords and suggests appropriate skills
#
# INSTALLATION:
# 1. Copy to your project: .claude/hooks/skill-suggester.sh
# 2. Make executable: chmod +x .claude/hooks/skill-suggester.sh
# 3. Configure in .claude/settings.json:
#    {
#      "hooks": {
#        "UserPromptSubmit": [{
#          "type": "command",
#          "command": ".claude/hooks/skill-suggester.sh"
#        }]
#      }
#    }
#
# CUSTOMIZATION:
# Override skill suggestions by setting environment variables or editing patterns below

set -e

# Read JSON input from stdin
INPUT=$(cat)

# Extract user prompt from hook input
PROMPT=$(echo "$INPUT" | grep -o '"user_prompt"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/"user_prompt"[[:space:]]*:[[:space:]]*"\([^"]*\)"/\1/' || echo "")

# If no prompt found, continue normally
if [ -z "$PROMPT" ]; then
  exit 0
fi

# Convert to lowercase for matching
PROMPT_LOWER=$(echo "$PROMPT" | tr '[:upper:]' '[:lower:]')

# Skill detection - customize these for your project
SKILL=""
REASON=""

# Implementation keywords → impact mapping
if echo "$PROMPT_LOWER" | grep -qE "(implement|create new|add feature|build|new component|new hook|new page)"; then
  SKILL="${SKILL_IMPLEMENTATION:-/skill:impact-map}"
  REASON="New implementation detected - map dependencies first"
fi

# Bug fix keywords → systematic debugging
if echo "$PROMPT_LOWER" | grep -qE "(bug|fix|error|broken|not working|issue|crash|fail|exception)"; then
  SKILL="${SKILL_BUGFIX:-/skill:debug}"
  REASON="Bug fix detected - use systematic debugging"
fi

# Refactoring keywords → design validation
if echo "$PROMPT_LOWER" | grep -qE "(refactor|architecture|redesign|major change|restructure|reorganize)"; then
  SKILL="${SKILL_REFACTOR:-/skill:validate-design}"
  REASON="Major change detected - validate design first"
fi

# Completion keywords → post-implementation validation
if echo "$PROMPT_LOWER" | grep -qE "(commit|push|done|finished|ready|complete|ship it)"; then
  SKILL="${SKILL_COMPLETION:-/skill:done}"
  REASON="Completion detected - run validation"
fi

# Context fatigue keywords → session management
if echo "$PROMPT_LOWER" | grep -qE "(confused|lost|context|slow|long session|forgot|where were we|start over)"; then
  SKILL="${SKILL_CONTEXT:-/skill:context-hygiene}"
  REASON="Context fatigue detected - manage session"
fi

# Performance keywords → performance analysis
if echo "$PROMPT_LOWER" | grep -qE "(slow|performance|optimize|speed|memory|bundle size|lighthouse)"; then
  SKILL="${SKILL_PERFORMANCE:-/skill:performance}"
  REASON="Performance concern detected - analyze first"
fi

# If no skill detected, continue normally
if [ -z "$SKILL" ]; then
  exit 0
fi

# Return JSON with system message for Claude
cat << EOF
{
  "continue": true,
  "systemMessage": "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n💡 SKILL SUGGESTION\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\nDetected: ${REASON}\nSuggested: ${SKILL}\n\nBefore proceeding, consider asking the user:\n\"Would you like me to run ${SKILL} first?\"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}
EOF
