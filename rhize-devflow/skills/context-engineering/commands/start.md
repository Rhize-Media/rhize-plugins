# Session Start

Initialize a new development session with full context loading.

## Triggers
**Keywords:** start, begin, new session, initialize, good morning, let's begin

## What This Does

1. **Load Project Context** via available MCP servers
2. **Show Sprint Status** from context file (if exists)
3. **Check for Stale Files** (>24h without updates)
4. **Display Active Work** item and pending tasks
5. **Suggest Next Action** based on context

## Automatic Actions

### Step 1: Check for Context Files
Look for and summarize:
- `CURRENT_SPRINT.md` or similar context file
- `COMPONENT_REGISTRY.md` for component inventory
- Recent git activity

### Step 2: Load Relevant Memories
If memory MCP available (Zen, Graphiti, etc.):
```
Query for relevant context about current project and recent work
```

### Step 3: Freshness Check
Check these files for staleness (>24h):
- Sprint/context files
- Component registry
- Any documentation that should stay current

### Step 4: Suggest Next Steps
Based on context, suggest one of:
- Continue active work item
- Run validation if changes from last session
- Address any pending blockers
- Start fresh if no context found

## Output Format

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🚀 Session Started: [Project Name]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 Active Work: [from context file]
📊 Status: [status]
⏰ Last Updated: [time ago]

📝 Pending:
  - [pending items if any]

💡 Suggested Action:
  [recommendation based on context]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

## When to Use
- At the beginning of every Claude Code session
- After a long break (>4 hours)
- When switching between major focus areas

## Related Commands
- `/done` - Run after completing work
- `/context-hygiene` - If session gets long
