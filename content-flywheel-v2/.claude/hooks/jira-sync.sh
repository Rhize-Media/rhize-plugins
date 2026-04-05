#!/bin/bash
# PostToolUse hook for Bash: detects git commit and extracts RT-XX Jira keys.
# Outputs a reminder for Claude to transition Jira issues via Atlassian MCP.
#
# Tool input is JSON on stdin: {"tool_name":"Bash","tool_input":{"command":"git commit ..."}}

INPUT=$(cat)

# Check if this is a git commit command
if ! echo "$INPUT" | grep -q "git commit"; then
  exit 0
fi

# Extract RT-XX keys from anywhere in the input (commit message, etc.)
KEYS=$(echo "$INPUT" | grep -oE 'RT-[0-9]+' | sort -u | tr '\n' ' ')

if [ -z "$KEYS" ]; then
  exit 0
fi

echo "JIRA_SYNC: Commit references Jira issues: ${KEYS}"
echo "ACTION REQUIRED: Use mcp__claude_ai_Atlassian__transitionJiraIssue to transition each to Done (id: 31)."
echo "Then use mcp__claude_ai_Atlassian__addIssueComment to add commit SHA + summary."
echo "Cloud ID: ac62d3a2-66bb-4513-a8e8-b634d3465466"
