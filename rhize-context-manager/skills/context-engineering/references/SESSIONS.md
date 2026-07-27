# Sessions Reference

> Detailed session management patterns for context engineering

---

## Session Architecture

A session consists of two components:

```
┌─────────────────────────────────────────────────────────────────┐
│                         SESSION                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────┐  ┌─────────────────────────────┐  │
│  │        EVENTS           │  │          STATE              │  │
│  │  (Conversation History) │  │    (Working Memory)         │  │
│  ├─────────────────────────┤  ├─────────────────────────────┤  │
│  │ • User messages         │  │ • Active files              │  │
│  │ • Assistant responses   │  │ • Current task context      │  │
│  │ • Tool calls/results    │  │ • Accumulated knowledge     │  │
│  │ • Errors encountered    │  │ • Decisions made            │  │
│  └─────────────────────────┘  └─────────────────────────────┘  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Session Lifecycle

```
CREATE ──► ACTIVE ──► COMPACT ──► CLOSE
  │           │          │          │
  │           │          │          ▼
  │           │          │     PERSIST
  │           │          │    (if needed)
  │           │          │
  │           ▼          │
  │      [Working]       │
  │           │          │
  │           └──────────┘
  │           (if context heavy)
  │
  ▼
INITIALIZE
• Load preferences
• Load project context
• Restore saved state
```

---

## Session Types

### Feature Implementation

```yaml
type: feature_implementation
characteristics:
  typical_duration: 1-2 hours
  message_count: 15-30
  context_weight: medium-high
  
context_loading:
  always:
    - Project architecture overview
    - Relevant patterns and conventions
    - Related component context
  on_demand:
    - Specific file contents
    - API documentation
    - Test examples
    
save_triggers:
  - Feature complete and working
  - Major milestone reached
  - Before switching to different feature
  - Context approaching limit
  
handoff_template: |
  ## Feature: {feature_name}
  
  ### Status: {in_progress|blocked|complete}
  
  ### Completed
  - {list of completed items}
  
  ### Remaining
  - {list of remaining items}
  
  ### Key Decisions
  - {decisions made and rationale}
  
  ### Files Modified
  - {list of files}
  
  ### To Continue
  1. {next steps}
```

### Bug Fix / Debugging

```yaml
type: debugging
characteristics:
  typical_duration: 30 min - 2 hours
  message_count: 10-50 (high variance)
  context_weight: high (lots of error context)
  
context_loading:
  always:
    - Error details (Sentry, logs)
    - Recent changes (git log)
    - Related file context
  on_demand:
    - Deployment history
    - Similar past errors
    - Dependency information
    
save_triggers:
  - Bug resolved and verified
  - Root cause identified (even if not fixed)
  - Blocked on external dependency
  - Need to context switch
  
handoff_template: |
  ## Bug: {bug_description}
  
  ### Status: {investigating|identified|fixed|blocked}
  
  ### Error Details
  - Type: {error_type}
  - Location: {file:line}
  - First seen: {timestamp}
  
  ### Investigation
  - {steps taken}
  - {findings}
  
  ### Root Cause
  {description or "Still investigating"}
  
  ### Fix Applied
  {description or "Not yet"}
  
  ### Verification
  - [ ] Local testing
  - [ ] Staging deployment
  - [ ] Monitoring confirmed
```

### Exploration / Research

```yaml
type: exploration
characteristics:
  typical_duration: variable
  message_count: 5-20
  context_weight: grows over time
  
context_loading:
  always:
    - Minimal - let it grow organically
  on_demand:
    - Documentation as discovered
    - Examples as needed
    - Related prior research
    
save_triggers:
  - Findings ready to document
  - Decision point reached
  - Moving to implementation
  
handoff_template: |
  ## Research: {topic}
  
  ### Question
  {what we were trying to learn}
  
  ### Findings
  - {key discoveries}
  
  ### Options Considered
  | Option | Pros | Cons |
  |--------|------|------|
  | {opt1} | {pros} | {cons} |
  
  ### Recommendation
  {recommended path and why}
  
  ### Resources
  - {useful links and docs}
```

### Code Review / Refactor

```yaml
type: code_review
characteristics:
  typical_duration: 1-2 hours
  message_count: 10-25
  context_weight: medium
  
context_loading:
  always:
    - Style guides and conventions
    - Patterns for this codebase
    - Files under review
  on_demand:
    - Related component context
    - Test coverage info
    - Historical context
    
save_triggers:
  - Review complete
  - Refactor complete
  - Significant feedback documented
  
handoff_template: |
  ## Review: {pr_or_scope}
  
  ### Scope
  - Files: {list}
  - Type: {review|refactor|both}
  
  ### Feedback Given
  - {categorized feedback}
  
  ### Changes Made
  - {list of changes}
  
  ### Follow-ups
  - {items for future}
```

---

## Session Compaction Strategies

### Truncation

Simply drop old messages, keeping recent ones.

```
BEFORE: [M1, M2, M3, M4, M5, M6, M7, M8, M9, M10]
AFTER:  [M7, M8, M9, M10]  (kept last 4)
```

**Pros:** Fast, simple, predictable
**Cons:** Loses context, decisions forgotten
**Use when:** Old messages truly irrelevant, quick cleanup needed

### Recursive Summarization

Summarize older content, keep recent detail.

```
BEFORE: [M1, M2, M3, M4, M5, M6, M7, M8, M9, M10]
AFTER:  [Summary(M1-M6), M7, M8, M9, M10]
```

**Pros:** Preserves key decisions, maintains narrative
**Cons:** Slower, may lose nuance
**Use when:** Important decisions in early messages, need continuity

### Topic Filtering

Keep only messages relevant to current topic.

```
BEFORE: [auth_M1, ui_M2, auth_M3, db_M4, auth_M5, ui_M6]
AFTER:  [auth_M1, auth_M3, auth_M5]  (filtered for auth topic)
```

**Pros:** Focused context, relevant information only
**Cons:** May lose cross-cutting insights
**Use when:** Clear topic focus, other topics truly unneeded

### Hybrid Approach

Combine strategies for best results.

```
1. Filter by relevance (topic filtering)
2. Summarize old relevant messages
3. Keep recent messages in full
4. Preserve all decisions regardless of age

RESULT: [Summary(relevant_old), Decisions[], Recent_full[]]
```

**Pros:** Best of all approaches
**Cons:** Most complex, slowest
**Use when:** High-value sessions, complex multi-topic work

---

## Session Boundaries

### When to Start New Session

```
MANDATORY (always new session):
├── Repository switch
│   └── Context from repo A not useful for repo B
├── Feature/task complete  
│   └── Clean slate for next work
├── Context exhaustion (>80%)
│   └── Quality degradation imminent
└── Major topic change
    └── Accumulated context now irrelevant

RECOMMENDED (usually new session):
├── Message count > 25-30
│   └── Conversation getting long
├── Duration > 90 minutes
│   └── Natural break point
├── After debugging session
│   └── Debug context clutters next task
└── Before unrelated work
    └── Prevent context pollution
```

### Session Continuation Signals

When to continue existing session:
- Work is incomplete and in progress
- Context still relevant and useful
- Under 50% context usage
- Same repository and feature

---

## Session Security

### Isolation Requirements

```
STRICT ISOLATION:
├── User A sessions ≠ User B sessions
├── Project X context ≠ Project Y context
├── Historical sessions scoped correctly
└── No cross-tenant data leakage
```

### PII in Sessions

```
BEFORE PERSISTENCE:
├── Scan for PII patterns
│   ├── Email addresses
│   ├── Phone numbers
│   ├── API keys / secrets
│   ├── Personal identifiers
│   └── Financial data
├── Redact or generalize
│   ├── "john@example.com" → "[email]"
│   ├── "API_KEY=abc123" → "[api_key]"
│   └── "SSN: 123-45-6789" → "[redacted]"
└── Store only safe version
```

---

## Session Metrics

### Health Indicators

| Metric | Healthy | Warning | Critical |
|--------|---------|---------|----------|
| Message count | < 20 | 20-30 | > 30 |
| Duration | < 60 min | 60-90 min | > 90 min |
| Context usage | < 50% | 50-70% | > 70% |
| Compaction count | 0 | 1 | > 1 |
| Topic switches | < 2 | 2-3 | > 3 |

### When Metrics Indicate Action

```
IF message_count > 25:
  → Consider new session or summarization

IF context_usage > 60%:
  → Apply compaction strategy

IF compaction_count > 1:
  → Strongly consider new session

IF topic_switches > 2:
  → Evaluate if context still coherent
```

---

## Integration with Memory

### Session → Memory Flow

```
During Session:
├── Accumulate events (conversation)
├── Build state (working memory)
└── Note potential memories (tagged)

At Session End:
├── Review tagged items
├── Extract as memories
│   ├── Preferences discovered
│   ├── Decisions made
│   ├── Patterns learned
│   └── Solutions found
├── Assign confidence
├── Check for conflicts
└── Store with provenance
```

### Memory → Session Flow

```
At Session Start:
├── Retrieve proactive memories
│   ├── User preferences
│   ├── Active project context
│   └── Critical constraints
├── Prepare reactive queries
│   ├── Error patterns for debugging
│   ├── Past decisions for features
│   └── Patterns for implementation
└── Load into session state
```
