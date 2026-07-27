# Patterns Reference

> Common patterns and anti-patterns for context engineering

---

## Context Assembly Patterns

### Router Documentation Pattern

Keep main documentation file lean, routing to topic-specific files.

```
✅ GOOD: Router architecture

CLAUDE.md (< 200 lines)
├── Quick reference / decision tree
├── Links to: ARCHITECTURE.md
├── Links to: PATTERNS.md
├── Links to: TROUBLESHOOTING.md
└── Links to: WORKFLOWS.md

Each linked file: focused, detailed, standalone
```

```
❌ BAD: Monolithic documentation

CLAUDE.md (2000+ lines)
├── Everything in one file
├── Hard to navigate
├── Always loads full content
└── Context budget consumed
```

**Implementation:**
```markdown
# CLAUDE.md (Router)

## Quick Reference
{Essential commands and conventions}

## Topics
- [Architecture](docs/ARCHITECTURE.md) - System design
- [Patterns](docs/PATTERNS.md) - Coding conventions
- [Troubleshooting](docs/TROUBLESHOOTING.md) - Common issues
- [Workflows](docs/WORKFLOWS.md) - Step-by-step guides

## Decision Tree
IF error → See Troubleshooting
IF new feature → See Architecture + Patterns
IF process question → See Workflows
```

---

### Progressive Context Loading

Load context in layers based on need.

```
LAYER 1 - Always Load (Essential):
├── User preferences
├── Project type and tech stack
├── Active constraints
└── Communication style

LAYER 2 - Task-Identified (Relevant):
├── Patterns for current task type
├── Related component context
├── Recent decisions in area
└── Known issues in area

LAYER 3 - On-Demand (As Needed):
├── Historical decisions
├── Archived patterns
├── Detailed specifications
└── Extended documentation
```

**Implementation:**
```typescript
async function loadContext(task: Task) {
  // Layer 1: Always
  const essential = await loadEssentialContext();
  
  // Layer 2: Based on task type
  const relevant = await loadTaskContext(task.type);
  
  // Layer 3: On explicit request or tool call
  // Loaded reactively when needed
  
  return { essential, relevant };
}
```

---

### Context Offloading Pattern

Move heavy content to files, keep references in conversation.

```
BEFORE (heavy context):
├── Full file contents in conversation
├── Complete logs inline
├── All data visible
└── Context: 80%+ used

AFTER (offloaded):
├── File summaries in conversation
├── Log highlights + file reference
├── Data summary + file reference
└── Context: 40% used

References allow retrieval when needed.
```

**Implementation:**
```markdown
Instead of pasting 500 lines of logs:

"I've saved the full logs to `/tmp/debug-logs.txt`.
Key findings:
- Error at line 234: Connection timeout
- Warning cluster at lines 100-150: Memory pressure
- Request pattern shows spike at 14:32

Should I analyze a specific section?"
```

---

### Memory-as-Tool Pattern

Let agent decide when to create/query memories.

```
Traditional: Extract memories automatically every turn
Memory-as-Tool: Agent has tools, calls them when appropriate

TOOLS:
- create_memory(content, type, confidence)
- query_memories(query, filters)
- update_memory(id, changes)

AGENT DECIDES:
- "This seems like an important preference" → create_memory
- "I need past solutions for this error" → query_memories
- "User corrected my understanding" → update_memory
```

**Benefits:**
- Fewer low-value memories
- More intentional extraction
- Agent understands memory value
- Reduced noise in memory store

---

## Session Management Patterns

### Session Boundaries Pattern

Clear rules for when to start new sessions.

```
MANDATORY NEW SESSION:
┌─────────────────────────────────────────┐
│ • Repository/project switch             │
│ • Feature/task complete                 │
│ • Context exhaustion (>80%)             │
│ • Major topic change                    │
└─────────────────────────────────────────┘

RECOMMENDED NEW SESSION:
┌─────────────────────────────────────────┐
│ • Message count > 25-30                 │
│ • Duration > 90 minutes                 │
│ • After long debugging session          │
│ • Before unrelated work                 │
└─────────────────────────────────────────┘
```

---

### Session Preservation Pattern

Save session state for continuation.

```
SAVE TRIGGERS:
├── Work incomplete at session end
├── Switching to different task temporarily
├── Context getting heavy (preemptive save)
└── Before significant risky operation

SAVE CONTENT:
├── Summary of current state
├── Files modified
├── Decisions made with rationale
├── Blockers and dependencies
├── Next steps
└── Any context needed to resume

SAVE METHODS:
├── Zen MCP: save_context({ key, content })
├── File: SESSION_CONTEXT.md
└── Structured: Handoff document
```

---

### Session Compaction Pattern

Reduce context while preserving value.

```
STRATEGY 1: Truncation
├── Keep: Last N messages
├── Drop: Everything older
└── Use when: Old context irrelevant

STRATEGY 2: Summarization
├── Keep: Recent messages full
├── Summarize: Older messages
└── Use when: Need continuity

STRATEGY 3: Topic Filtering
├── Keep: Messages matching current topic
├── Drop: Unrelated messages
└── Use when: Clear single focus

STRATEGY 4: Hybrid
├── Summarize relevant old
├── Drop irrelevant old
├── Keep recent full
├── Preserve all decisions
└── Use when: Complex, high-value session
```

---

## Memory Patterns

### Declarative Memory Storage

Store facts with proper categorization.

```yaml
categories:
  preferences:
    content_type: User preference statement
    example: "Prefers TypeScript with strict mode"
    confidence_source: Explicit user statement
    
  facts:
    content_type: Known true information
    example: "Project uses PostgreSQL 15"
    confidence_source: Observed or stated
    
  constraints:
    content_type: Requirements/limitations
    example: "Must support Safari 14+"
    confidence_source: Documented requirement
    
  history:
    content_type: Past events/decisions
    example: "Chose Zustand over Redux, Sprint 3"
    confidence_source: Recorded during event
```

---

### Procedural Memory Storage

Store how-to knowledge.

```yaml
categories:
  debug_workflow:
    content_type: How to investigate
    example: "For auth errors, check cookies first"
    activation: error_type matches
    
  implementation_pattern:
    content_type: How to build
    example: "Use server actions for mutations"
    activation: feature_type matches
    
  review_process:
    content_type: How to validate
    example: "Run typecheck before commit"
    activation: pre_commit event
```

---

### Memory Consolidation Pattern

Regular cleanup and optimization.

```
DETECT DUPLICATES:
├── Semantic similarity > 0.9
├── Same subject/topic
└── Merge into single memory

RESOLVE CONFLICTS:
├── Find contradictions
├── Apply resolution rules
│   ├── Recency wins
│   ├── Explicit > inferred
│   └── Specific > general
└── Update or supersede

PRUNE STALE:
├── Not accessed 90+ days
├── Low confidence + old
├── Superseded
└── Archive or delete

SCHEDULE:
├── Weekly: Duplicate check
├── Monthly: Full consolidation
└── Quarterly: Deep cleanup
```

---

## Anti-Patterns

### Context Hoarding

```
❌ ANTI-PATTERN: Loading everything

Load ALL documentation
Load ALL memories
Load FULL file contents
Keep ENTIRE conversation history
Result: Context exhaustion, slow responses

✅ PATTERN: Context discipline

Load ESSENTIAL only initially
Load RELEVANT based on task
Load DETAILED on demand
Compact HISTORY progressively
Result: Efficient context, fast responses
```

---

### Memory Pollution

```
❌ ANTI-PATTERN: Extracting everything

"User said hello" → Memory
"Tried X but failed" → Memory
"JavaScript has functions" → Memory
Every code block → Memory
Result: Noisy retrieval, wasted storage

✅ PATTERN: Memory hygiene

Explicit preferences → Memory
Verified solutions → Memory
Repeated patterns → Memory
Significant decisions → Memory
Result: High-signal retrieval
```

---

### Session Sprawl

```
❌ ANTI-PATTERN: Unbounded sessions

Never start new session
Let context grow unlimited
Mix unrelated topics
No handoff documentation
Result: Context exhaustion, lost coherence

✅ PATTERN: Session discipline

Clear boundaries for new sessions
Proactive context management
Topic focus per session
Handoff before switching
Result: Coherent, efficient sessions
```

---

### Documentation Monolith

```
❌ ANTI-PATTERN: Giant single file

CLAUDE.md: 2000 lines
Everything in one place
Full detail always loaded
No progressive disclosure
Result: Context waste, hard to navigate

✅ PATTERN: Router architecture

CLAUDE.md: < 200 lines (router)
Topic files: Focused, detailed
Load on demand
Progressive disclosure
Result: Efficient, navigable
```

---

### Blind Retrieval

```
❌ ANTI-PATTERN: Always load all

Load all memories every query
No relevance filtering
No confidence weighting
No recency consideration
Result: Context bloat, irrelevant noise

✅ PATTERN: Smart retrieval

Proactive: Essential only
Reactive: Query-dependent
Filtered: By relevance, confidence
Ranked: By recency, usage
Result: Focused, relevant context
```

---

## Integration Patterns

### MCP Orchestration

Coordinate multiple MCP servers for enhanced capability.

```
ERROR INVESTIGATION ORCHESTRATION:

1. Sentry MCP: Get error details
2. Vercel MCP: Get deployment context
3. Git: Get recent changes
4. Graphiti: Query similar errors
5. Zen: Check for saved debug context

Combine results for comprehensive picture.
```

---

### Fallback Chains

Handle MCP server unavailability gracefully.

```
ZEN FALLBACK:
├── Primary: zen.save_context()
├── Fallback 1: SESSION_CONTEXT.md
├── Fallback 2: Conversation summary
└── Recovery: Sync to Zen when available

GRAPHITI FALLBACK:
├── Primary: graphiti.query()
├── Fallback 1: COMPONENT_REGISTRY.md
├── Fallback 2: File-based search
└── Recovery: Queue for later sync
```

---

## Pattern Selection Guide

| Situation | Recommended Pattern |
|-----------|---------------------|
| Documentation > 500 lines | Router Documentation |
| Context > 50% used | Progressive Loading |
| Large files/logs | Context Offloading |
| Memory noise | Memory-as-Tool |
| Long session | Session Compaction |
| Topic switch | Session Boundaries |
| Work incomplete | Session Preservation |
| Duplicate memories | Memory Consolidation |
| MCP unreliable | Fallback Chains |
| Multi-source debug | MCP Orchestration |
