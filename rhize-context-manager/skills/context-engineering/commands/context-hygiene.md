# Context Hygiene

Manage context window and session health during long development sessions.

## Triggers
**Keywords:** context, cleanup, long session, slow, confused, lost, where were we, compress

## What This Does

1. **Assess Context Health** - Check token usage indicators
2. **Identify Stale Context** - Find outdated information
3. **Compress or Archive** - Reduce unnecessary context
4. **Refresh Critical Info** - Reload what matters
5. **Create Checkpoint** - Save progress for continuity

## When to Use

- Session has been running >2 hours
- Responses are getting slower
- Claude seems to "forget" recent context
- Working across many files
- Switching focus areas within session

## Automatic Actions

### Step 1: Context Assessment
Evaluate current session:
- How many files have been discussed?
- How many tool calls made?
- Any repeated questions or circular discussions?

### Step 2: Identify What to Keep
Critical context to preserve:
- Current task/goal
- Files actively being edited
- Recent decisions and their rationale
- Blockers or pending items

### Step 3: Identify What to Drop
Stale context to release:
- Completed tasks (already committed)
- Files no longer relevant
- Debug output from resolved issues
- Exploratory code paths not taken

### Step 4: Create Summary Checkpoint
Generate a concise summary:
```markdown
## Session Checkpoint - [timestamp]

### Active Work
- [current task]

### Key Decisions
- [decision 1]: [rationale]

### Modified Files
- [file]: [what changed]

### Next Steps
- [immediate next action]
```

### Step 5: Refresh Strategy
Options:
1. **Soft Reset**: Summarize and continue
2. **Hard Reset**: Save checkpoint, start new conversation
3. **Selective Reload**: Re-read only critical files

## Output Format

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🧹 Context Hygiene Report
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 Session Stats:
  Duration: [time]
  Files Touched: [count]
  Tool Calls: [count]

🎯 Active Context:
  [list of relevant items]

🗑️ Stale Context:
  [list of items to drop]

💾 Checkpoint Created: [yes/no]

💡 Recommendation:
  [soft reset / hard reset / continue]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

## Signs You Need This

- Claude asks about something already discussed
- Responses reference outdated file states
- Circular debugging (same fix attempted twice)
- Responses getting noticeably slower
- Context feels "muddy" or unfocused

## Related Commands
- `/start` - Fresh session initialization
- `/done` - Complete current work first
