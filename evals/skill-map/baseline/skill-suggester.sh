#!/bin/bash
# ============================================================================
# PROVENANCE — vendored historical baseline, NOT live code.
#
# Recovered verbatim via `git show cb9e030^:rhize-context-manager/skills/
# context-engineering/hooks/skill-suggester.sh` (rhize-plugins repo). This is
# the retired keyword-grep skill suggester that rhize-context-manager/hooks/
# skill-router.js (commit cb9e030, "feat(skill-map): map-driven skill router
# replaces grep suggester (phase 2)") replaced on 2026-08-09. It is vendored
# here ONLY as Eval 1's baseline comparison point — see
# docs/superpowers/specs/2026-08-10-skill-graph-evals-design.md, eval #1's
# "Baseline comparison: retired grep suggester run on the same [golden] set".
#
# Do not wire this into any hooks.json or otherwise treat it as active code —
# evals/skill-map/eval_routing.py invokes it directly as a subprocess purely
# to compute a comparison metric.
# ============================================================================
#
# Skill Suggestion Hook (Generalized)
# Detects development keywords and suggests appropriate skills
#
# TIER: T3 (advisory) — UserPromptSubmit, no matcher (event doesn't support one).
# Never blocks (always exit 0).
# CONTRACT: the input field is "prompt", not "user_prompt" (verified against
# code.claude.com/docs/en/hooks-guide, 2026-08-04 — "user_prompt" was silently
# always empty, making this hook a permanent no-op). To reach Claude the model,
# output must nest additionalContext inside hookSpecificOutput; a top-level
# additionalContext or a plain "systemMessage" is user-visible only and is
# silently ignored by the model.
#
# INSTALLATION:
# 1. Copy to your project: .claude/hooks/skill-suggester.sh
# 2. Make executable: chmod +x .claude/hooks/skill-suggester.sh
# 3. Configure in .claude/settings.json:
#    {
#      "hooks": {
#        "UserPromptSubmit": [{
#          "hooks": [{ "type": "command", "command": ".claude/hooks/skill-suggester.sh" }]
#        }]
#      }
#    }
#
# CUSTOMIZATION:
# Override skill suggestions by setting environment variables or editing patterns below

set -e

# Read JSON input from stdin
INPUT=$(cat)

# Extract user prompt from hook input via real JSON parsing. grep/sed
# extraction on the raw JSON text truncates at the first escaped quote (\")
# inside the prompt string, silently missing real prompts -- reproduced
# 2026-08-04. json.loads decodes escapes correctly.
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
