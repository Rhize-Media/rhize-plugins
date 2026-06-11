# Context Hygiene & Session Management Skill

> **Status:** Foundation Draft v1
> **Last Updated:** 2024-12-01
> **Dependencies:** Zen MCP, SuperClaude /sc:save & /sc:load, Git hooks

---

## Overview

This skill addresses the critical problem of context window exhaustion and documentation drift. It establishes systems for keeping contextual files lean and current, managing session boundaries, and preserving/restoring context across sessions.

## Problems This Solves

1. **CLAUDE.md becomes a monolith** - Too much info, outdated content, context overload
2. **Context window exhaustion** - Long debugging sessions eat all available context
3. **Documentation drift** - Docs don't reflect current codebase state
4. **Lost progress on session reset** - Work context evaporates when starting fresh
5. **Circular problem solving** - Same issues re-discussed without institutional memory

---

## Part 1: CLAUDE.md as Router Architecture

### The Problem with Monolithic CLAUDE.md

```markdown
❌ BAD: 2000-line CLAUDE.md that loads everything

# Project: VBA LMS App
[500 lines of architecture]
[300 lines of API docs]
[400 lines of component patterns]
[200 lines of setup instructions]
[300 lines of troubleshooting]
[300 lines of current work context]

→ Every session starts with massive context load
→ Most content irrelevant to current task
→ Updates require editing giant file
→ Easy to have conflicting/outdated sections
```

### The Router Pattern

```markdown
✅ GOOD: <200 line CLAUDE.md that routes to topic files

# VBA LMS App - Claude Context Router
> Keep this file under 200 lines. Details live in linked files.

## Quick Context
- Dual repo: rhize-lms (Next.js frontend) + vba-hoops (Payload CMS backend)
- Supabase for database, Payload for content management
- Deployed on Vercel

## Where to Find Information

| Topic | File | When to Read |
|-------|------|--------------|
| Architecture | ARCHITECTURE.md | System design questions |
| Current Work | CURRENT_SPRINT.md | Active feature context |
| Components | COMPONENT_REGISTRY.md | Before creating UI |
| Patterns | PATTERNS.md | Implementation guidance |
| Deprecated | DEPRECATED.md | What NOT to use |
| API | vba-hoops/docs/API.md | Backend integration |

## Critical Rules (Always Apply)
1. Check COMPONENT_REGISTRY.md before creating new components
2. Run `pnpm typecheck` before committing
3. All Supabase calls through lib/api/ - never direct
4. Use react-query for client data fetching

## Active Gotchas (Update Weekly)
- [ ] Player.teamId can be null during free agency periods
- [ ] Vercel preview deployments use different Supabase project

## Skills Available
See .claude/skills/ for specialized workflows:
- dependency-graph: Impact analysis before changes
- error-triage: Sentry + Vercel error investigation
- regression-prevention: Bug fix methodology
```

### File Hierarchy

```
project-root/
├── CLAUDE.md                    # Router (<200 lines)
├── ARCHITECTURE.md              # System design (load on demand)
├── PATTERNS.md                  # Coding patterns (load on demand)
├── DEPRECATED.md                # Anti-patterns (load on demand)
├── CURRENT_SPRINT.md            # Active work (load for relevant tasks)
├── COMPONENT_REGISTRY.md        # Auto-generated (load before UI work)
├── CHANGELOG.md                 # Version history
│
├── docs/
│   ├── setup/
│   │   ├── local-development.md
│   │   ├── environment-vars.md
│   │   └── database-setup.md
│   ├── guides/
│   │   ├── adding-new-feature.md
│   │   ├── deployment.md
│   │   └── testing.md
│   └── api/
│       ├── authentication.md
│       ├── players-api.md
│       └── teams-api.md
│
└── .claude/
    └── skills/
        └── [skill directories]
```

### Load-On-Demand Rules

```markdown
## When Claude Should Load Additional Files

### ARCHITECTURE.md
Load when:
- System design question
- "How does X connect to Y"
- Adding new integration
- Performance investigation

### CURRENT_SPRINT.md  
Load when:
- Resuming work from previous session
- Need context on active features
- Planning next steps

### PATTERNS.md
Load when:
- Implementing new feature
- "What's the pattern for X"
- Code review or refactoring

### COMPONENT_REGISTRY.md
Load when:
- About to create new component
- Looking for existing functionality
- Checking data fetching strategies

### DEPRECATED.md
Load when:
- Anti-pattern detection triggered
- Reviewing old code
- Migration planning
```

---

## Part 2: Session Management

### Session Types

```markdown
## Session Classification

### Type 1: Feature Implementation
Duration: 1-2 hours
Context needed: CURRENT_SPRINT.md, relevant patterns
Save threshold: After major milestone or 20 messages

### Type 2: Bug Fix / Debugging
Duration: 30 min - 2 hours
Context needed: Error context, relevant files
Save threshold: After each hypothesis tested

### Type 3: Exploration / Research
Duration: Variable
Context needed: Minimal, load as discovered
Save threshold: Before abandoning promising threads

### Type 4: Code Review / Refactor
Duration: 1-2 hours  
Context needed: Patterns, component registry
Save threshold: After review complete
```

### Session Boundaries

```markdown
## When to Start a New Session

### Mandatory New Session:
- Switching between frontend (rhize-lms) and backend (vba-hoops) work
- After 30+ messages in debugging session
- After completing a feature (before starting new one)
- When context feels "heavy" or responses slow

### Optional New Session:
- After 15+ messages on single topic
- When switching between unrelated files
- After successful deployment
- End of workday (preserve context for tomorrow)
```

### Context Preservation

#### Using Zen MCP

```markdown
## Zen Context Save/Restore

### Save Context (End of Session)
```
Use zen to save current context with key: 'feature-player-registration-v2'

Include in save:
- Current implementation status
- Files modified
- Tests written/needed
- Known issues
- Next steps
```

### Restore Context (New Session)
```
Use zen to restore context from key: 'feature-player-registration-v2'
```

### Key Naming Convention
Format: [type]-[feature]-[version]
Examples:
- feature-player-registration-v1
- bugfix-team-roster-null-v2
- refactor-api-layer-v1
- debug-auth-flow-session3
```

#### Using SuperClaude

```markdown
## SuperClaude Session Management

### Save Session
/sc:save "player-registration-complete"

### Load Session
/sc:load "player-registration-complete"

### Best Practices
- Save at natural break points
- Use descriptive names
- Include status in name: "auth-flow-wip" vs "auth-flow-done"
```

#### Manual Context File (Fallback)

```markdown
## SESSION_CONTEXT.md (When MCP unavailable)

Create before session ends:

# Session Context: [Date] [Topic]

## Status
[Current state of work]

## Files Modified
- [file]: [what changed]

## Decisions Made
- [Decision]: [Reasoning]

## Open Questions
- [Question 1]
- [Question 2]

## Next Steps
1. [Step 1]
2. [Step 2]

## Key Code Snippets
[Any important code that's hard to reconstruct]
```

---

## Part 3: Context Window Efficiency

### Context Budget Tracking

```markdown
## Approximate Context Costs

| Content Type | Est. Tokens | Load When |
|--------------|-------------|-----------|
| CLAUDE.md (router) | 500-800 | Always |
| ARCHITECTURE.md | 2000-4000 | Architecture questions |
| PATTERNS.md | 1500-3000 | Implementation |
| COMPONENT_REGISTRY.md | 1000-2000 | UI creation |
| Single source file | 200-1000 | Direct work |
| Stack trace | 500-2000 | Debugging |
| Conversation history | 100-300/msg | Accumulates |

## Budget Guidelines
- Fresh session: ~100k tokens available
- "Heavy" feeling: >60% used
- Danger zone: >80% used

## Signs of Context Exhaustion
- Responses becoming shorter
- Forgetting earlier context
- Repeating suggestions already tried
- Slower response times
```

### Aggressive Context Offloading

```markdown
## During Development

### Error/Debug Output
❌ Keep full stack traces in conversation
✅ Capture to file, keep summary in conversation

"Encountered TypeError in PlayerCard.tsx line 45.
Full stack trace saved to: logs/debug-2024-12-01-1430.md
Summary: Attempting to access 'name' on null player object."

### Large Code Blocks  
❌ Paste 200-line files into conversation
✅ Reference file path, load specific sections

"The relevant code is in lib/api/players.ts lines 45-60.
Let me check that section..."

### Investigation Results
❌ Keep all Sentry/Vercel output in conversation
✅ Summarize findings, save raw data to file

"Sentry shows 47 occurrences since deployment.
Details saved to: logs/sentry-report-2024-12-01.md
Key finding: All errors from Safari users on iOS 16."
```

### Memory Externalization

```markdown
## What to Keep in Working Memory vs External

### Working Memory (Conversation)
- Current task objective
- Active hypothesis (if debugging)
- Immediate next steps
- Blocking issues

### External Files
- Full error logs
- Investigation history
- Attempted solutions
- Code snippets for reference

### Zen/SuperClaude Context
- Session continuity info
- Cross-session patterns
- Feature progress state
```

---

## Part 4: Documentation Currency

### Automated Freshness Checks

```markdown
## Pre-Commit Documentation Check

### Git Hook: pre-commit
```bash
#!/bin/bash

# Check if code files changed but docs didn't
CODE_CHANGED=$(git diff --cached --name-only | grep -E '\.(ts|tsx)$' | wc -l)
DOCS_CHANGED=$(git diff --cached --name-only | grep -E '\.md$' | wc -l)

if [ "$CODE_CHANGED" -gt 5 ] && [ "$DOCS_CHANGED" -eq 0 ]; then
  echo "⚠️  Significant code changes without documentation updates."
  echo "Consider updating: PATTERNS.md, ARCHITECTURE.md, or COMPONENT_REGISTRY.md"
  # Warning only, don't block
fi

# Check COMPONENT_REGISTRY freshness
if [ -f "COMPONENT_REGISTRY.md" ]; then
  REGISTRY_AGE=$(( ($(date +%s) - $(stat -f %m COMPONENT_REGISTRY.md)) / 86400 ))
  if [ "$REGISTRY_AGE" -gt 7 ]; then
    echo "⚠️  COMPONENT_REGISTRY.md is $REGISTRY_AGE days old. Run: pnpm registry:generate"
  fi
fi
```

### Weekly Documentation Review

```markdown
## Weekly Documentation Audit

### Automated Checks
- [ ] COMPONENT_REGISTRY.md regenerated this week
- [ ] DEPRECATED.md reviewed for new items
- [ ] CURRENT_SPRINT.md reflects actual current work

### Manual Review
- [ ] CLAUDE.md still under 200 lines
- [ ] Active gotchas in CLAUDE.md still relevant
- [ ] PATTERNS.md matches actual implementation patterns
- [ ] No contradictions between doc files

### Update Triggers
If this week included:
- [ ] New component type → Update PATTERNS.md
- [ ] New API endpoint → Update API docs
- [ ] Deprecated old approach → Update DEPRECATED.md
- [ ] Architecture change → Update ARCHITECTURE.md
```

### CURRENT_SPRINT.md Template

```markdown
# Current Sprint Context
> Last updated: [date]
> Update this at start of each work session

## Active Features
### [Feature Name]
**Status:** [not started / in progress / blocked / review / done]
**Branch:** feature/[name]
**Files:**
- [ ] [file]: [status]
- [ ] [file]: [status]
**Blockers:** [none / description]
**Next:** [next action]

## In Progress Bugs
### [Bug Title]
**Sentry:** [link if applicable]
**Status:** [investigating / fix in progress / testing]
**Root Cause:** [if identified]
**Files:** [affected files]

## This Week's Decisions
- [Decision 1]: [Context and reasoning]
- [Decision 2]: [Context and reasoning]

## Parking Lot (Deferred Items)
- [Item 1]: [Why deferred, when to revisit]
```

---

## Part 5: Context Recovery Protocols

### After Context Reset

```markdown
## Context Recovery Workflow

### Step 1: Load Minimal Context
Read CLAUDE.md only (router pattern ensures this is light)

### Step 2: Check Session State
- Is there a zen context saved for current work?
- Is there a CURRENT_SPRINT.md with recent updates?
- Is there a SESSION_CONTEXT.md from last session?

### Step 3: Restore Relevant Context
Based on intended task:
- Feature work → Restore from zen + load CURRENT_SPRINT
- Bug fix → Restore from zen + load error context
- New task → Fresh start, just CLAUDE.md

### Step 4: Verify Understanding
Before proceeding: "Based on restored context, my understanding is [X]. 
Is this correct, or should I load additional context?"
```

### Cross-Session Continuity Prompt

```markdown
## Session Handoff Template

At end of session, create this summary:

"Session ending. Here's the context for continuation:

COMPLETED:
- [What was finished]

IN PROGRESS:
- [What's partially done]

BLOCKED BY:
- [Any blockers discovered]

NEXT STEPS:
1. [First thing to do next session]
2. [Second thing]

FILES TO REVIEW:
- [Key files for next session]

CONTEXT SAVED TO:
- Zen key: '[key name]'
- Files: [any context files created]"
```

---

## Integration with Other Skills

### → Dependency Graph Skill
After major changes, trigger registry regeneration

### → Regression Prevention Skill
Session management for debugging workflows

### → Skill Refinement Skill
Documentation updates feed into pattern detection

---

## Automation Scripts

### Registry Generation

```bash
# scripts/generate-docs.sh

#!/bin/bash

echo "Generating documentation..."

# Generate component registry
npx ts-node scripts/generate-registry.ts

# Check CLAUDE.md line count
CLAUDE_LINES=$(wc -l < CLAUDE.md)
if [ "$CLAUDE_LINES" -gt 200 ]; then
  echo "⚠️  CLAUDE.md is $CLAUDE_LINES lines (target: <200)"
  echo "   Consider moving content to topic-specific files"
fi

# Update timestamps
sed -i '' "s/Last updated:.*/Last updated: $(date +%Y-%m-%d)/" CURRENT_SPRINT.md

echo "Documentation generation complete"
```

### Freshness Report

```bash
# scripts/doc-freshness.sh

#!/bin/bash

echo "Documentation Freshness Report"
echo "=============================="

for file in CLAUDE.md ARCHITECTURE.md PATTERNS.md DEPRECATED.md CURRENT_SPRINT.md; do
  if [ -f "$file" ]; then
    DAYS_OLD=$(( ($(date +%s) - $(stat -f %m "$file")) / 86400 ))
    if [ "$DAYS_OLD" -gt 14 ]; then
      echo "⚠️  $file: $DAYS_OLD days old"
    else
      echo "✅ $file: $DAYS_OLD days old"
    fi
  else
    echo "❌ $file: NOT FOUND"
  fi
done
```

---

## Quick Reference

```
┌─────────────────────────────────────────────────────────────┐
│                   CONTEXT HYGIENE                           │
├─────────────────────────────────────────────────────────────┤
│  CLAUDE.md = ROUTER (< 200 lines)                          │
│  ├── Architecture questions → ARCHITECTURE.md               │
│  ├── Current work → CURRENT_SPRINT.md                       │
│  ├── Patterns → PATTERNS.md                                 │
│  ├── Anti-patterns → DEPRECATED.md                          │
│  └── Components → COMPONENT_REGISTRY.md                     │
├─────────────────────────────────────────────────────────────┤
│  SESSION MANAGEMENT                                         │
│  • Save context: zen save OR /sc:save                       │
│  • Load context: zen restore OR /sc:load                    │
│  • New session: Every 20-30 messages OR task switch        │
├─────────────────────────────────────────────────────────────┤
│  CONTEXT OFFLOADING                                         │
│  • Errors → Save to file, keep summary                      │
│  • Large code → Reference path, not paste                   │
│  • Investigation → Summarize, externalize details           │
└─────────────────────────────────────────────────────────────┘
```

---

## Metrics

1. **CLAUDE.md Size**
   - Target: <200 lines
   - Measure: Weekly line count

2. **Documentation Freshness**
   - Target: All docs <14 days old
   - Measure: File modification dates

3. **Session Length Before Degradation**
   - Target: 30+ messages without context issues
   - Measure: When responses start degrading

4. **Context Recovery Time**
   - Target: <2 minutes to resume work
   - Measure: Time from session start to productive work

---

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| v1 | 2024-12-01 | Initial foundation with router pattern |
