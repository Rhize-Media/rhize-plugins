# Advanced Scenarios Reference

> Multi-project, failure handling, edge cases, and production considerations

---

## Multi-Project Context Management

### The Challenge

Developers often work on multiple projects. Context engineering must:
- Isolate project memories (prevent cross-contamination)
- Enable project switching without confusion
- Support shared knowledge where appropriate

---

### Isolation Patterns

**Pattern 1: Strict Isolation**

```yaml
strict_isolation:
  scope: Each project has separate memory
  sharing: None
  key_format: "{project_id}-{type}-{feature}"
  
  use_when:
    - Client projects (confidentiality)
    - Unrelated technology stacks
    - Different teams/organizations
    
  implementation:
    - Include project_id in all operations
    - Filter retrieval by project_id
    - Separate storage namespaces
```

**Pattern 2: Layered Isolation**

```yaml
layered_isolation:
  layers:
    personal: # Shared across all
      - user_preferences
      - communication_style
    technology: # Shared within tech stack
      - react_patterns
      - typescript_conventions
    project: # Isolated
      - architecture
      - constraints
      
  use_when:
    - Multiple projects with similar tech
    - Personal vs client work
```

**Pattern 3: Organization-Scoped**

```yaml
organization_scope:
  levels:
    global: personal_preferences
    organization: company_patterns
    team: team_conventions
    project: project_specifics
    
  inheritance: project → team → org → global
  
  use_when:
    - Enterprise environments
    - Multiple teams, shared standards
```

---

### Project Switching Protocol

```markdown
PROJECT SWITCH WORKFLOW:

[ ] 1. COMPLETE CURRENT CONTEXT
    - Save session context
    - Extract pending memories
    - Update status files

[ ] 2. CLEAR WORKING MEMORY
    - Don't carry project A to project B
    - Explicit context boundary

[ ] 3. LOAD NEW PROJECT CONTEXT
    - Switch project identifier
    - Load project-specific memories
    - Restore saved context if exists

[ ] 4. VERIFY ISOLATION
    - Confirm correct project
    - Ensure no cross-contamination
```

---

## Failure Handling

### MCP Server Unavailability

**Zen MCP Fallback:**

```yaml
zen_fallback:
  detection:
    - Connection timeout
    - Error response
    
  fallback_chain:
    1: SESSION_CONTEXT.md
    2: CURRENT_SPRINT.md
    3: Manual summary in conversation
    
  recovery:
    - Note Zen unavailable
    - Offer to sync when available
    - Mark context as "local only"
```

**Graphiti MCP Fallback:**

```yaml
graphiti_fallback:
  detection:
    - Query failures
    
  fallback_chain:
    1: COMPONENT_REGISTRY.md
    2: File-based search (grep)
    
  recovery:
    - Queue writes for later
    - Note degraded search
    - Use keyword lookup
```

**Debug Stack Fallback:**

```yaml
debug_fallback:
  if_sentry_down:
    - Request error details from user
    - Use local logs
    - Manual reproduction
    
  if_vercel_down:
    - Check deployment manually
    - Use git for changes
    - Local build for testing
    
  if_git_down:
    - Work with current state
    - Note history unavailable
    - Document changes manually
```

---

### Memory Corruption/Inconsistency

**Detection:**

```markdown
SIGNS OF PROBLEMS:
- Contradictory retrievals
- Outdated information persisting
- Missing expected memories
- High duplication
```

**Recovery Procedures:**

```yaml
recovery_levels:

  minor: # < 10% affected
    - Manual correction
    - Re-run consolidation
    - Update confidence scores
    
  moderate: # 10-30% affected
    - Export good memories
    - Re-initialize store
    - Import verified memories
    - Re-extract from recent sessions
    
  severe: # > 30% affected
    - Full memory reset
    - Start fresh extraction
    - Use rapid learning
    - Investigate root cause
```

---

### Context Window Overflow

```yaml
overflow_handling:

  prevention:
    - Monitor continuously
    - Aggressive compaction at 70%
    - Hard warnings at 80%
    
  when_occurs:
    1: Drop low-priority context
    2: Summarize conversation
    3: Keep only essential memories
    4: Log what was dropped
    
  recovery:
    - Start new session
    - Restore essential only
    - Reference dropped by file
    
  post_mortem:
    - Why did it overflow?
    - What should have offloaded?
    - Update thresholds
```

---

## Privacy & Security

### PII Handling

```yaml
pii_protocol:

  sensitive_types:
    - Names (when not public)
    - Email addresses
    - Phone numbers
    - Physical addresses
    - Financial data
    - Health information
    - Credentials
    
  before_storage:
    1: Scan for patterns
    2: Redact or generalize
    3: Store safe version only
    
  redaction_examples:
    "john@company.com": "[user email]"
    "API_KEY=abc123": "[api key present]"
    "555-123-4567": "[phone number]"
    
  exceptions:
    - User explicitly requests storage
    - Data is already public
    - Required for function (with consent)
```

### Access Control

```yaml
access_control:

  isolation_requirements:
    - User A ≠ User B memories
    - Project X ≠ Project Y memories
    - Sessions scoped correctly
    
  implementation:
    - Include scope in all operations
    - Server-side enforcement
    - Audit log for access
    
  verification:
    - Regular access review
    - Test isolation with probes
    - Alert on anomalies
```

### Data Retention

```yaml
retention_policy:

  standard:
    active_memories: indefinite (with pruning)
    session_history: 90 days
    compacted_summaries: 1 year
    deleted_memories: 30 days (soft delete)
    
  user_rights:
    - View all memories
    - Delete specific memories
    - Export all data
    - Full deletion
```

---

## Edge Cases

### Contradictory User Statements

```yaml
contradiction_handling:

  scenario:
    session_1: "I prefer TypeScript"
    session_5: "Just use JavaScript here"
    
  resolution:
    1: Check if context-dependent
    2: If true contradiction:
       - Prefer newer
       - Track supersession
       - Optionally verify
    3: Store nuanced:
       - "Generally prefers TypeScript, flexible per-project"
```

### Rapidly Evolving Projects

```yaml
rapid_evolution:

  challenges:
    - Architecture changing frequently
    - Decisions being reversed
    - Patterns not yet stable
    
  adaptations:
    - Lower confidence for recent decisions
    - Shorter memory TTL
    - More frequent consolidation
    - "EXPERIMENTAL" marking
```

### Long-Running Sessions

```yaml
long_sessions:

  definition: "> 2 hours or > 50 messages"
  
  risks:
    - Context exhaustion
    - Lost focus
    - Fatigue errors
    
  mitigations:
    - Periodic checkpoints
    - Aggressive summarization
    - Topic filtering
    - Suggested breaks
    
  auto_interventions:
    30_messages: Suggest saving
    50_messages: Offer new session
    70_percent_context: Mandatory compaction
    80_percent_context: Strong recommendation
```

### Cross-Repository Work

```yaml
cross_repo:

  challenge: Frontend + backend repos
  
  solution:
    - Separate memory namespaces
    - Explicit cross-references
    - "Frontend X depends on Backend Y"
    
  session_management:
    - Save before switching
    - Load cross-repo context
    - Clear repo-specific memory
```

---

## Performance Optimization

### Context Budget

```yaml
budget_by_model:
  claude_3_5: 
    window: 200k
    aggressive_inclusion: true
  gpt_4:
    window: 128k
    moderate_inclusion: true
  smaller_models:
    window: varies
    minimal_high_precision: true

budget_by_task:
  simple_question: "< 20% for memory"
  complex_implementation: "< 30%"
  debugging: "up to 40%"
```

### Caching Strategies

```yaml
caching_layers:

  L1_user_profile:
    content: core_preferences
    ttl: session_duration
    
  L2_frequent:
    content: recently_accessed
    ttl: 1_hour
    
  L3_full:
    content: all_memories
    ttl: persistent
    
  invalidation:
    - On memory update
    - On consolidation
    - Periodic refresh
```

### Batch Operations

```yaml
batch_optimization:

  extraction:
    - Batch at session end
    - Single LLM call for multiple
    
  consolidation:
    - Batch related together
    - Single pass per category
    - Off-peak scheduling
    
  retrieval:
    - Batch proactive + reactive
    - Single embedding call
    - Parallel search
```

---

## Monitoring & Alerting

### Key Metrics

```yaml
health_metrics:
  - memory_count (growth rate)
  - retrieval_latency (p50, p95, p99)
  - context_usage_percent
  - extraction_success_rate
  - consolidation_error_rate

quality_metrics:
  - retrieval_relevance_score
  - memory_precision (sampled)
  - conflict_rate
  - staleness_percent

alerts:
  latency_warning: "> 500ms"
  latency_critical: "> 1s"
  conflict_warning: "> 10%"
  extraction_failures: "> 5%"
  memory_spike: investigate
```

### Debugging Memory Issues

```markdown
DEBUG WORKFLOW:

1. IDENTIFY SYMPTOM
   - Wrong memory retrieved?
   - Missing memory?
   - Slow retrieval?
   - Conflicting information?

2. CHECK LOGS
   - Last extraction
   - Last consolidation
   - Recent retrievals
   - Errors

3. INSPECT MEMORY
   - Retrieve specific memory
   - Check provenance
   - Verify accuracy
   - Check confidence

4. TEST FIX
   - Update/delete problematic
   - Verify improvement
   - Monitor recurrence
```
