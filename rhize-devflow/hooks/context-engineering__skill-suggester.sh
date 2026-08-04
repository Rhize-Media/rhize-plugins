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

# Extract user prompt from hook input. Claude Code's UserPromptSubmit payload
# field is "prompt" (verified against the harness contract) -- a prior version
# of this script looked for "user_prompt", which never appears, so PROMPT was
# always empty and the hook was a silent no-op on every call. Real JSON
# parsing (not grep/sed) also fixes escaped-quote/newline prompts, which the
# old "[^"]*" pattern truncated at the first \" -- reproduced 2026-08-04.
PROMPT=$(printf '%s' "$INPUT" | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    print("")
else:
    print(data.get("prompt") or "")
')

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

# additionalContext (nested in hookSpecificOutput) reaches Claude; systemMessage
# is a user-visible-only banner. Emit both via jq so quoting is always valid JSON.
CONTEXT_MSG="Detected: ${REASON}. Suggested: ${SKILL}. Before proceeding, consider asking the user: \"Would you like me to run ${SKILL} first?\""
BANNER="━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💡 SKILL SUGGESTION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Detected: ${REASON}
Suggested: ${SKILL}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

jq -n --arg ctx "$CONTEXT_MSG" --arg banner "$BANNER" \
  '{systemMessage: $banner, hookSpecificOutput: {hookEventName: "UserPromptSubmit", additionalContext: $ctx}}'
