# Memory Lifecycle Reference

> Extraction, consolidation, and retrieval patterns for persistent memory

---

## Memory vs RAG

Understanding the difference:

| Aspect | Memory | RAG |
|--------|--------|-----|
| Goal | Personalization, learning | Information retrieval |
| Data Source | Conversation history | External documents |
| Isolation | Per-user, per-project | Often shared corpus |
| Write Pattern | Extract from sessions | Ingest documents |
| Read Pattern | Proactive + reactive | Query-driven |
| Content | Preferences, decisions, patterns | Facts, documentation |

Memory complements RAG - they serve different purposes.

---

## Memory Types

### Declarative Memory (Facts)

What the system knows about user/project.

```yaml
categories:
  
  preferences:
    description: User's stated preferences
    examples:
      - "Prefers TypeScript over JavaScript"
      - "Uses functional components, not class"
      - "Likes detailed explanations"
    confidence_source: explicit_statement
    
  facts:
    description: Known information about project/context
    examples:
      - "Project uses Next.js App Router"
      - "Database is PostgreSQL via Supabase"
      - "Deploys to Vercel"
    confidence_source: stated_or_observed
    
  constraints:
    description: Requirements and limitations
    examples:
      - "Must support IE11"
      - "Bundle size limit 200KB"
      - "No external API calls from client"
    confidence_source: documented_requirement
    
  history:
    description: Past events and decisions
    examples:
      - "Chose Zustand over Redux in Sprint 3"
      - "Migrated from Pages to App Router"
      - "Previous error with auth was cookie issue"
    confidence_source: recorded_event
```

### Procedural Memory (How-To)

How to do things in this context.

```yaml
categories:

  debug_workflow:
    description: How to investigate issues
    examples:
      - "Check Sentry first, then Vercel logs"
      - "For auth issues, verify cookie settings"
      - "Database errors - check connection pool"
    activation: error_investigation
    
  implementation_pattern:
    description: How to build features
    examples:
      - "Server actions for mutations"
      - "React Query for client data fetching"
      - "Zod for validation schemas"
    activation: feature_implementation
    
  review_process:
    description: How to validate work
    examples:
      - "Run typecheck before commit"
      - "Test on mobile viewport"
      - "Check accessibility with axe"
    activation: pre_commit, code_review
    
  communication_style:
    description: How to interact with user
    examples:
      - "Prefers code examples over explanations"
      - "Wants brief answers unless asked for detail"
      - "Uses technical terminology freely"
    activation: always
```

---

## Extraction

### What to Extract

```
EXTRACT:
├── Explicit preferences
│   └── "I prefer X" → High confidence
├── Architecture decisions  
│   └── "We chose X because Y" → High confidence
├── Discovered patterns
│   └── "This approach works well" → Medium confidence
├── Error solutions
│   └── "The fix was X" → High confidence (if verified)
└── Workflow preferences
    └── Repeated behaviors → Medium confidence

DO NOT EXTRACT:
├── Conversational filler
│   └── "Thanks", "Got it", "Okay"
├── Failed attempts
│   └── Debug tries that didn't work
├── Common knowledge
│   └── "JavaScript has functions"
├── Superseded info
│   └── Old decisions since changed
└── Uncertain statements
    └── "Maybe we could try..."
```

### Extraction Methods

**Schema-Based Extraction:**

```typescript
interface ExtractedMemory {
  type: 'declarative' | 'procedural';
  category: string;
  content: string;
  confidence: 'high' | 'medium' | 'low';
  source: {
    sessionId: string;
    messageIndex: number;
    quote: string;  // Supporting evidence
  };
}
```

**LLM Extraction Prompt:**

```markdown
Analyze this conversation segment and extract memories.

EXTRACT ONLY:
- Explicit preferences ("I prefer X", "I always use Y")
- Decisions with rationale ("We chose X because Y")  
- Verified solutions ("The fix was X and it worked")
- Repeated patterns (same approach used multiple times)

FOR EACH MEMORY:
1. Type: declarative (fact) or procedural (how-to)
2. Category: preference | fact | constraint | pattern | solution
3. Content: 1-2 sentence summary
4. Confidence: high (explicit), medium (inferred), low (uncertain)
5. Evidence: Quote from conversation

DO NOT EXTRACT:
- Greetings, thanks, acknowledgments
- Failed attempts or dead ends
- Common programming knowledge
- Speculative statements
```

### Extraction Timing

| Trigger | When | Blocking? |
|---------|------|-----------|
| Session end | Always | No (background) |
| Explicit request | User says "remember this" | Yes |
| Significant event | Decision made, error fixed | No |
| Periodic | Every N messages | No |
| Memory-as-Tool | Agent decides | Yes |

---

## Consolidation

### Why Consolidate?

Over time, memory accumulates issues:
- **Duplicates**: Same fact extracted multiple times
- **Conflicts**: Old and new versions of same info
- **Staleness**: Outdated information persists
- **Fragmentation**: Related info scattered

### Consolidation Operations

```yaml
operations:

  UPDATE:
    trigger: New info supersedes old
    action: Update existing memory, track history
    example:
      before: "Uses React 17"
      after: "Uses React 18 (upgraded from 17)"
      
  CREATE:
    trigger: Genuinely new information
    action: Add new memory with provenance
    check: Verify not duplicate of existing
    
  DELETE:
    trigger: Info no longer valid
    action: Soft delete, keep for audit
    examples:
      - Temporary workaround removed
      - Project constraint lifted
      
  MERGE:
    trigger: Multiple memories about same topic
    action: Combine into single comprehensive memory
    example:
      before: 
        - "Prefers TypeScript"
        - "Uses strict TypeScript config"
        - "Enables all TypeScript checks"
      after:
        - "Prefers TypeScript with strict configuration and all checks enabled"
```

### Consolidation Prompt

```markdown
Given these existing memories and new candidates, determine consolidation actions.

EXISTING MEMORIES:
{list of current memories with IDs}

NEW CANDIDATES:
{list of extracted memories}

FOR EACH CANDIDATE, determine:
1. ACTION: create | update | merge | skip
2. TARGET: If update/merge, which existing memory ID
3. RESULT: Final memory content
4. REASON: Why this action

RULES:
- UPDATE if new info supersedes existing
- MERGE if multiple memories cover same topic
- CREATE only if genuinely new
- SKIP if duplicate or low value
```

### Conflict Resolution

When memories conflict:

```
RESOLUTION STRATEGIES:

1. Recency wins (default)
   - Newer information replaces older
   - Track supersession chain
   
2. Explicit wins over inferred
   - User statement beats observed behavior
   - High confidence beats low
   
3. Specific wins over general
   - "For this project, use X" beats "Generally use Y"
   - Context-dependent memories preserved
   
4. Ask user (when critical)
   - Flag for verification
   - Don't auto-resolve important conflicts
```

---

## Retrieval

### Proactive Retrieval

Always loaded at session start:

```yaml
proactive_memories:
  - user_preferences
  - active_project_context
  - critical_constraints
  - communication_style

loading_strategy:
  - Load immediately on session create
  - Include in initial context
  - Refresh if session long-running
```

### Reactive Retrieval

Query-dependent, loaded as needed:

```yaml
reactive_triggers:
  
  error_investigation:
    query: Similar past errors and solutions
    filter: type=solution, project=current
    
  feature_implementation:
    query: Relevant patterns and decisions
    filter: type=pattern|decision, area=relevant
    
  code_review:
    query: Style guides and conventions
    filter: type=convention, project=current
```

### Retrieval Methods

**Semantic Similarity:**
```
Query embedding → Compare to memory embeddings → Rank by similarity
```

**Structured Query:**
```
Filter by: type, category, confidence, recency, project
```

**Hybrid:**
```
1. Semantic search for candidates
2. Filter by structured criteria
3. Boost by confidence and recency
4. Return top K
```

### Ranking Factors

```
RELEVANCE_SCORE = 
  semantic_similarity * 0.4 +
  confidence_score * 0.25 +
  recency_score * 0.2 +
  access_frequency * 0.15
```

---

## Memory Provenance

### Why Track Provenance?

- **Debugging**: Why does system think X?
- **Trust**: How confident should we be?
- **Maintenance**: When was this established?
- **Conflicts**: Which source to prefer?

### Provenance Schema

```typescript
interface MemoryProvenance {
  id: string;
  content: string;
  type: 'declarative' | 'procedural';
  category: string;
  
  // Origin
  createdFrom: {
    sessionId: string;
    messageIndex: number;
    timestamp: Date;
    extractionMethod: 'explicit' | 'inferred' | 'observed';
  };
  
  // Trust
  confidence: 'high' | 'medium' | 'low';
  verifiedBy?: 'user' | 'system' | 'repeated_use';
  verifiedAt?: Date;
  
  // History
  supersedes?: string[];  // IDs of replaced memories
  supersededBy?: string;  // ID if this was replaced
  
  // Usage
  lastAccessed: Date;
  accessCount: number;
  
  // Metadata
  project?: string;
  tags?: string[];
}
```

---

## Memory Anti-Patterns

### Over-Extraction

```
❌ BAD: Extract everything
   - "User said hello" → Memory
   - "Discussed options" → Memory
   - Every code block → Memory

✅ GOOD: Extract selectively
   - Explicit preferences
   - Verified solutions
   - Repeated patterns
```

### No Consolidation

```
❌ BAD: Never clean up
   - Duplicates accumulate
   - Conflicts unresolved
   - Stale data persists

✅ GOOD: Regular consolidation
   - Weekly cleanup
   - Conflict resolution
   - Staleness pruning
```

### Blind Retrieval

```
❌ BAD: Load all memories
   - Context bloat
   - Irrelevant noise
   - Slow responses

✅ GOOD: Smart retrieval
   - Proactive minimum
   - Reactive as needed
   - Relevance filtering
```

---

## Memory Hygiene

### Regular Maintenance

```yaml
daily:
  - None (too frequent)
  
weekly:
  - Check for duplicates
  - Resolve new conflicts
  - Update access stats
  
monthly:
  - Full staleness review
  - Confidence recalibration
  - Category cleanup
  
quarterly:
  - Archive unused memories
  - Schema updates
  - Quality audit
```

### Confidence Decay

Memories should lose confidence over time if unused:

```
NEW_CONFIDENCE = ORIGINAL_CONFIDENCE * (1 - DECAY_RATE * DAYS_SINCE_ACCESS / 90)

Example:
- High confidence (1.0)
- Not accessed for 90 days
- Decay rate 0.3
- New confidence: 1.0 * (1 - 0.3) = 0.7 (medium)
```

### Pruning Rules

```yaml
prune_candidates:
  - confidence: low
    last_accessed: > 90 days
    action: archive
    
  - confidence: any
    superseded_by: exists
    action: archive
    
  - confidence: any
    last_accessed: > 180 days
    access_count: < 3
    action: review_for_deletion
```
