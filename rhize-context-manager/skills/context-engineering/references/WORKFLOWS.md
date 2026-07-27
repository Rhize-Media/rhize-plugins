# Workflows Reference

> Step-by-step procedures for context engineering operations

---

## Session Workflows

### New Session Initialization

```markdown
## Workflow: Initialize New Session

[ ] 1. IDENTIFY SESSION TYPE
    - Feature implementation?
    - Bug fix / debugging?
    - Exploration / research?
    - Code review / refactor?

[ ] 2. LOAD PROACTIVE CONTEXT
    - User preferences (from memory)
    - Project context (CLAUDE.md, config files)
    - Active sprint/status (CURRENT_SPRINT.md)

[ ] 3. CHECK FOR SAVED STATE
    - Query Zen MCP for relevant saved contexts
    - If continuing work: restore saved state
    - If new work: skip

[ ] 4. LOAD TASK-SPECIFIC CONTEXT
    - Debugging: error details, recent changes
    - Feature: related patterns, architecture
    - Review: style guides, affected files

[ ] 5. VERIFY CONTEXT CURRENCY
    - Check documentation freshness
    - Verify assumptions still valid
    - Note any outdated information
```

### Session Handoff

```markdown
## Workflow: Session Handoff

[ ] 1. SUMMARIZE CURRENT STATE
    - What was accomplished?
    - What is in progress?
    - What is blocked?

[ ] 2. DOCUMENT PENDING WORK
    - List incomplete items
    - Note dependencies
    - Identify blockers

[ ] 3. RECORD DECISIONS
    - What was decided?
    - Why? (rationale)
    - Any alternatives considered?

[ ] 4. SAVE CONTEXT
    - Use Zen MCP: save_context({ key, content })
    - Or: Update SESSION_CONTEXT.md
    - Include: summary, files, decisions, next_steps

[ ] 5. EXTRACT MEMORIES
    - Review session for extractable insights
    - Preferences discovered
    - Patterns learned
    - Solutions found

[ ] 6. UPDATE STATUS FILES
    - CURRENT_SPRINT.md (if applicable)
    - COMPONENT_REGISTRY.md (if new components)
    - DEPENDENCY_GRAPH.md (if new dependencies)

---

### Handoff Document Template

# Session Handoff: {feature_or_task}

## Status: {in_progress | blocked | complete}

## Summary
{Brief description of work done}

## Completed
- {item 1}
- {item 2}

## In Progress
- {item 1}: {current state}
- {item 2}: {current state}

## Blockers
- {blocker 1}: {details}

## Next Steps
1. {step 1}
2. {step 2}

## Key Decisions
| Decision | Rationale |
|----------|-----------|
| {decision} | {why} |

## Files Modified
- `{path/to/file1}`: {what changed}
- `{path/to/file2}`: {what changed}

## Context Recovery
To continue this work:
1. Load this handoff document
2. Restore context: `zen.get_context({ key: "{key}" })`
3. Review files listed above
4. Continue from "Next Steps"
```

---

## Memory Workflows

### Memory Extraction

```markdown
## Workflow: Extract Memories from Session

[ ] 1. REVIEW SESSION
    - Scan conversation for extractable insights
    - Look for: preferences, decisions, patterns, solutions

[ ] 2. CATEGORIZE EACH CANDIDATE
    - Type: declarative (fact) or procedural (how-to)
    - Category: preference | fact | constraint | pattern | solution
    - Scope: user-level | project-level | task-level

[ ] 3. ASSESS CONFIDENCE
    - High: Explicit statement, verified solution
    - Medium: Inferred from behavior, unverified
    - Low: Uncertain, speculative

[ ] 4. CHECK FOR CONFLICTS
    - Query existing memories for conflicts
    - If conflict: determine resolution
    - Update/supersede as needed

[ ] 5. STORE WITH PROVENANCE
    - Include: session ID, timestamp, confidence
    - Tag: project, category, type
    - Link: related memories

[ ] 6. UPDATE RELATED MEMORIES
    - Mark superseded memories
    - Link related memories
    - Update indexes
```

### Memory Consolidation

```markdown
## Workflow: Consolidate Memories

[ ] 1. RETRIEVE CANDIDATES
    - Get memories for consolidation
    - Filter by: project, category, or full corpus
    - Include: confidence scores, last accessed, creation date

[ ] 2. IDENTIFY DUPLICATES
    - Find semantically similar memories
    - Group by topic/subject
    - Note exact vs near duplicates

[ ] 3. RESOLVE CONFLICTS
    - Find contradictory memories
    - Apply resolution strategy:
      - Recency wins
      - Explicit beats inferred
      - Specific beats general
    - Or flag for user verification

[ ] 4. MERGE REDUNDANT
    - Combine related memories
    - Preserve most specific details
    - Update provenance to track merge

[ ] 5. PRUNE LOW-VALUE
    - Identify stale memories (unused, old, low confidence)
    - Archive or delete
    - Keep audit trail

[ ] 6. UPDATE INDEXES
    - Refresh search indexes
    - Update category mappings
    - Verify retrieval quality
```

### Memory Retrieval

```markdown
## Workflow: Retrieve Memories for Task

[ ] 1. DETERMINE RETRIEVAL TYPE
    - Proactive: always needed (preferences, project context)
    - Reactive: query-dependent (errors, patterns)

[ ] 2. PROACTIVE RETRIEVAL
    - Load: user preferences
    - Load: active project context
    - Load: critical constraints
    - Load: communication style

[ ] 3. REACTIVE RETRIEVAL
    - Analyze task/query
    - Construct search query
    - Include filters: type, category, confidence
    - Execute search

[ ] 4. RANK RESULTS
    - Score by: relevance, confidence, recency
    - Apply boost for recently accessed
    - Filter by minimum relevance threshold

[ ] 5. APPLY TO CONTEXT
    - Include top N memories in context
    - Format appropriately
    - Note confidence levels where relevant
```

---

## Debugging Workflows

### Error Investigation

```markdown
## Workflow: Investigate Error

[ ] 1. GATHER ERROR CONTEXT
    - Sentry: get_error_details({ issue_id })
    - Extract: error type, stack trace, breadcrumbs
    - Note: affected users, frequency, first/last seen

[ ] 2. GET DEPLOYMENT CONTEXT
    - Vercel: get_deployment({ near error time })
    - Check: deployment status, build logs
    - Identify: last successful deployment

[ ] 3. GET CODE CHANGES
    - Git: log since last working deployment
    - Focus: files in stack trace
    - Identify: potential causes

[ ] 4. SEARCH MEMORY FOR SIMILAR
    - Query: similar errors seen before
    - Check: known solutions
    - Review: related patterns

[ ] 5. FORM HYPOTHESIS
    - Based on: error, changes, patterns
    - Prioritize: most likely causes
    - Plan: investigation steps

[ ] 6. TEST HYPOTHESIS
    - Reproduce error
    - Apply fix
    - Verify resolution

[ ] 7. DOCUMENT RESOLUTION
    - What was the root cause?
    - What was the fix?
    - How was it verified?

[ ] 8. EXTRACT TO MEMORY
    - Store: error pattern
    - Store: solution
    - Link: error → solution

---

### Investigation Log Template

# Error Investigation: {error_type}

## Error Details
- **Type**: {error_type}
- **Message**: {error_message}
- **Location**: {file:line}
- **First Seen**: {timestamp}
- **Frequency**: {count} occurrences

## Stack Trace
{stack_trace}

## Recent Changes
| Commit | Author | Files | Message |
|--------|--------|-------|---------|
| {hash} | {name} | {files} | {msg} |

## Hypothesis
1. {hypothesis_1}: {evidence}
2. {hypothesis_2}: {evidence}

## Investigation Steps
- [ ] {step_1}
- [ ] {step_2}

## Root Cause
{description of actual cause}

## Resolution
{description of fix applied}

## Verification
- [ ] Local testing passed
- [ ] Staging deployment successful
- [ ] Monitoring confirmed resolution

## Learnings
- {what to remember for future}
```

### Regression Prevention

```markdown
## Workflow: Prevent Regression

[ ] 1. DOCUMENT ROOT CAUSE
    - Clear description of what went wrong
    - Why it wasn't caught earlier
    - Contributing factors

[ ] 2. IDENTIFY RISK AREAS
    - What other code might have same issue?
    - What changes could reintroduce?
    - Dependencies that might be affected

[ ] 3. VERIFY FIX SCOPE
    - Does fix address root cause?
    - Does fix cover all affected areas?
    - Any edge cases?

[ ] 4. CREATE/UPDATE TESTS
    - Unit test for specific fix
    - Integration test for flow
    - Consider property-based testing

[ ] 5. RUN VERIFICATION
    - All existing tests pass
    - New tests pass
    - Manual verification complete

[ ] 6. MULTI-MODEL VALIDATION (optional)
    - Save context for validation
    - Have different model review
    - Address any concerns

[ ] 7. UPDATE DOCUMENTATION
    - Document pattern/anti-pattern
    - Update relevant registries
    - Add to troubleshooting guides

[ ] 8. EXTRACT MEMORIES
    - Error pattern
    - Solution
    - Prevention strategy
```

---

## Context Management Workflows

### Context Pressure Response

```markdown
## Workflow: Handle Context Pressure

TRIGGER: Context usage > 60%

[ ] 1. ASSESS SITUATION
    - What's consuming context?
    - Is all loaded content necessary?
    - Can conversation be summarized?

[ ] 2. OFFLOAD TO FILES
    - Move large code blocks to files
    - Move logs and data to files
    - Keep references in conversation

[ ] 3. SUMMARIZE CONVERSATION
    - Compact old messages
    - Preserve key decisions
    - Keep recent detail

[ ] 4. FILTER MEMORIES
    - Remove low-relevance memories
    - Keep only task-critical
    - Re-retrieve if needed later

[ ] 5. CONSIDER NEW SESSION
    - If > 70%: strongly consider
    - If > 80%: highly recommend
    - Create handoff if switching
```

### Documentation Currency

```markdown
## Workflow: Keep Documentation Current

[ ] 1. CHECK FRESHNESS
    - CLAUDE.md: < 14 days?
    - CURRENT_SPRINT.md: < 3 days?
    - COMPONENT_REGISTRY.md: < 7 days?

[ ] 2. IDENTIFY DRIFT
    - Compare docs to actual code
    - Check for undocumented changes
    - Note any conflicts

[ ] 3. UPDATE DOCUMENTS
    - Refresh stale sections
    - Add new components/patterns
    - Remove deprecated info

[ ] 4. REGENERATE IF NEEDED
    - DEPENDENCY_GRAPH.md from imports
    - COMPONENT_REGISTRY.md from files

[ ] 5. VERIFY ROUTER PATTERN
    - Main doc (CLAUDE.md) routes correctly?
    - Links to details valid?
    - Progressive disclosure working?
```

---

## Quick Reference Checklists

### Session Start Checklist
```
[ ] Load user preferences
[ ] Load project context
[ ] Check for saved session state
[ ] Load task-specific context
[ ] Verify documentation currency
```

### Session End Checklist
```
[ ] Summarize progress
[ ] Document blockers
[ ] Save context (if incomplete)
[ ] Extract memories
[ ] Update status files
```

### Debug Start Checklist
```
[ ] Get error details from Sentry
[ ] Get deployment context from Vercel
[ ] Get recent changes from Git
[ ] Query memory for similar errors
[ ] Form initial hypothesis
```

### Debug End Checklist
```
[ ] Document root cause
[ ] Document solution
[ ] Verify fix
[ ] Add/update tests
[ ] Extract to memory
```

### Weekly Maintenance Checklist
```
[ ] Check documentation freshness
[ ] Run memory consolidation
[ ] Review stale memories
[ ] Check for duplicate memories
[ ] Verify MCP server connections
```
