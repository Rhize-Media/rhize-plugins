# Evaluation & Cold Start Reference

> Measuring memory quality and handling projects with no existing context

---

## Cold Start Patterns

### The Cold Start Problem

When starting with a new project or user, there's no memory to retrieve. The system must:
1. Provide value immediately without personalization
2. Rapidly learn preferences and patterns
3. Build useful memory from early interactions

---

### Strategy 1: Intelligent Defaults

Use sensible defaults until preferences learned:

```yaml
cold_start_defaults:

  code_style:
    - Follow language conventions (PEP8, ESLint)
    - Use common patterns for framework
    - Match existing codebase style if visible
    
  communication:
    - Moderate detail level
    - Include code examples
    - Ask clarifying questions when ambiguous
    
  workflow:
    - Standard development flow
    - Run obvious checks (lint, type, test)
    - Document significant decisions
```

---

### Strategy 2: Rapid Learning

Accelerate memory building in early sessions:

```yaml
rapid_learning_protocol:

  sessions_1_to_3:
    extraction_threshold: lower
    preference_discovery: active
    pattern_observation: aggressive
    
  discovery_prompts:
    - "I notice you're using X. Is that preferred?"
    - "Should I follow this pattern from your codebase?"
    - "What's your typical workflow for this?"
    
  after_session_3:
    extraction_threshold: normal
    preference_discovery: passive
    rely_on: built_memory
```

---

### Strategy 3: Project Onboarding

Systematic context gathering for new projects:

```markdown
PROJECT ONBOARDING CHECKLIST:

[ ] 1. SCAN PROJECT STRUCTURE
    - Identify framework/language
    - Find configuration files
    - Locate documentation

[ ] 2. READ KEY FILES
    - README.md
    - CLAUDE.md or similar
    - package.json / requirements.txt
    - Config files (tsconfig, eslint)

[ ] 3. IDENTIFY PATTERNS
    - Code organization style
    - Naming conventions
    - Testing approach
    - Error handling patterns

[ ] 4. NOTE CONSTRAINTS
    - Browser/runtime requirements
    - Performance targets
    - Security requirements

[ ] 5. CAPTURE AS MEMORIES
    - Create initial memory set
    - Mark confidence as "inferred"
    - Verify with user when relevant
```

---

### Onboarding Memory Template

```markdown
## Initial Project Memory

### Detected
- Framework: {detected}
- Language: {primary}
- Package Manager: {detected}
- Testing: {detected}

### Inferred Patterns
- Code Style: {observations}
- File Organization: {observations}
- State Management: {observations}

### To Verify
- [ ] Preferred patterns correct?
- [ ] Undocumented conventions?
- [ ] Workflow preferences?

### Confidence Levels
- Detected from files: medium
- Inferred from code: low
- Stated by user: high
```

---

## Evaluation Framework

### Why Evaluate?

Without measurement, memory systems can:
- Fill with noise (low signal)
- Miss important information (gaps)
- Return irrelevant results (poor retrieval)
- Slow down interactions (context bloat)

---

### Evaluation Dimensions

```
┌─────────────────────────────────────────────────────────────────┐
│                   MEMORY QUALITY DIMENSIONS                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  EXTRACTION         CONSOLIDATION        RETRIEVAL              │
│  ───────────        ─────────────        ─────────              │
│  • Precision        • Deduplication      • Recall@K             │
│  • Recall           • Conflict Rate      • Relevance            │
│  • Confidence       • Staleness          • Latency              │
│    Calibration                           • Ranking              │
│                                                                  │
│                     OVERALL                                      │
│                     ───────                                      │
│                     • Task Success                               │
│                     • Context Efficiency                         │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

### Extraction Metrics

**Precision**: Are extracted memories valuable?

```markdown
METHOD:
Sample 20 recent memories, rate each:
- Highly valuable: Clear, actionable, used
- Somewhat valuable: Correct but rarely needed
- Low value: Noise, too generic
- Wrong: Incorrect or outdated

CALCULATE: (Highly + Somewhat) / Total
TARGET: > 80%

IF LOW:
- Tighten extraction criteria
- Increase confidence threshold
- Review topic definitions
```

**Recall**: Are important things captured?

```markdown
METHOD:
Review last 5 sessions for missed opportunities:
- User repeated a preference
- Same question asked twice
- Pattern used multiple times

CALCULATE: Captured / (Captured + Missed)
TARGET: > 70%

IF LOW:
- Lower extraction threshold
- Add more topic definitions
- Increase extraction frequency
```

**Confidence Calibration**: Is confidence accurate?

```markdown
IDEAL:
- High confidence → 90%+ correct
- Medium confidence → 60-80% correct
- Low confidence → 40-60% correct

IF MISCALIBRATED:
- Adjust confidence criteria
- Review extraction prompts
```

---

### Consolidation Metrics

**Deduplication Rate**

```markdown
METHOD:
Analyze memory corpus for:
- Exact duplicates
- Near duplicates (>80% similar)

CALCULATE: (Exact + Near) / Total
TARGET: < 10%

IF HIGH:
- Run consolidation more frequently
- Improve similarity detection
```

**Conflict Rate**

```markdown
METHOD:
Find contradictory memories:
- "Prefers X" vs "Avoids X"

CALCULATE: Conflicting pairs / Total
TARGET: < 5%

IF HIGH:
- Improve supersession tracking
- Add timestamps
- Review conflict resolution
```

**Staleness**

```markdown
INDICATORS:
- Not accessed in 90+ days
- Created before major changes
- Low confidence + old

TARGET: < 20% stale

IF HIGH:
- Implement confidence decay
- Aggressive pruning
- Regular review cycles
```

---

### Retrieval Metrics

**Recall@K**: Is right memory in top K?

```markdown
TARGETS:
- Recall@3: > 60%
- Recall@5: > 75%
- Recall@10: > 85%

IF LOW:
- Improve embedding quality
- Tune similarity threshold
- Add keyword boosting
```

**Relevance**: Are retrieved memories helpful?

```markdown
RATE EACH RETRIEVAL:
- Highly relevant: Directly answered need
- Somewhat relevant: Useful context
- Tangentially relevant: Related but not helpful
- Irrelevant: Wasted context

TARGET: > 70% (Highly + Somewhat)

IF LOW:
- Adjust retrieval threshold
- Improve query understanding
- Filter by confidence
```

**Latency**

```markdown
TARGETS:
- Proactive retrieval: < 100ms
- Reactive retrieval: < 300ms
- Full context assembly: < 500ms

IF HIGH:
- Optimize vector search
- Add caching
- Reduce retrieval count
```

---

### End-to-End Metrics

**Task Success Rate**

```markdown
COMPARE WITH/WITHOUT MEMORY:
- Time to completion
- Errors made
- Rework required

SUCCESS INDICATORS:
- Fewer clarifying questions
- Less repetition of past decisions
- Faster context establishment
```

**Context Efficiency**

```markdown
ANALYZE COMPOSITION:
- Memory: < 20% of context
- Conversation: < 50% of context
- Wasted/irrelevant: < 10%

IF INEFFICIENT:
- Reduce proactive retrieval
- Improve precision
- Earlier compaction
```

---

## Evaluation Schedule

### Per-Session (Automatic)

```yaml
session_end_metrics:
  - memories_extracted: count
  - memories_retrieved: count
  - context_usage: percentage
  - session_duration: minutes
  - compactions: count
```

### Weekly (Review)

```markdown
[ ] Sample 20 memories for precision
[ ] Check for new duplicates
[ ] Review conflict rate
[ ] Assess staleness
[ ] Calculate retrieval relevance
```

### Monthly (Deep Analysis)

```markdown
[ ] Full deduplication pass
[ ] Recall evaluation
[ ] Confidence calibration check
[ ] Latency benchmarks
[ ] Task success comparison
[ ] Context efficiency audit
```

---

## Improvement Workflows

### Low Precision → Tighten Extraction

```markdown
1. Review topic definitions - too broad?
2. Increase confidence threshold
3. Add negative examples to prompt
4. Require explicit signals
```

### Low Recall → Expand Extraction

```markdown
1. Add more topic categories
2. Lower extraction threshold
3. Increase extraction frequency
4. Add "missed opportunity" detection
```

### High Duplication → Better Consolidation

```markdown
1. Lower similarity threshold for merging
2. Run consolidation more frequently
3. Pre-filter during extraction
4. Improve embedding quality
```

### Poor Retrieval → Optimize Search

```markdown
1. Tune similarity threshold
2. Add recency boosting
3. Add confidence weighting
4. Implement query expansion
5. Add keyword fallback
```

---

## Evaluation Dashboard

```markdown
# Memory System Health

## Last Updated: {timestamp}

### Extraction Health
| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Precision | X% | >80% | ✅/⚠️/❌ |
| Recall | X% | >70% | ✅/⚠️/❌ |

### Consolidation Health
| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Duplication | X% | <10% | ✅/⚠️/❌ |
| Conflicts | X% | <5% | ✅/⚠️/❌ |
| Staleness | X% | <20% | ✅/⚠️/❌ |

### Retrieval Health
| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Recall@5 | X% | >75% | ✅/⚠️/❌ |
| Relevance | X% | >70% | ✅/⚠️/❌ |
| Latency | Xms | <300ms | ✅/⚠️/❌ |

### Action Items
- [ ] {issue} → {action}
```
