---
description: Session bookend — initialize a development session with full context loading (STATE.md, memory, session log)
---

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

### Step 0: Consult the Skill Map

Before anything else, check for the compiled skill-map artifact:
`~/.claude/context-manager/skill-map.resolved.json`, falling back to
`~/.claude/context-manager/skill-map.static.json`. If present, this repo's
stack-relevant skills are already surfaced automatically by
`rhize-context-manager/hooks/session-disclosure.js` (a SessionStart hook) —
no manual action needed here. If neither file exists, the map hasn't been
built/installed on this machine yet; degrade gracefully and proceed with the
rest of `/start` using the flat plugin/skill listing instead (see the
`context-stack` skill's "routing decisions consult the map; the flat listing
is fallback" note).

### Step 1: Check for Context Files
Look for and summarize:
- `STATE.md` — project memory (Verified facts · General rules · Open failures ·
  Lessons learned · Last session). READ THIS FIRST before changing any code;
  the "Last session" section tells you where to resume.
- `CURRENT_SPRINT.md` or similar context file
- `COMPONENT_REGISTRY.md` for component inventory
- Recent git activity

### Step 2: Load Relevant Memories
If an explicitly supported memory read API is available:
```
Query within the current tenant/project scope. Otherwise report unavailable; never scrape transcripts.
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
