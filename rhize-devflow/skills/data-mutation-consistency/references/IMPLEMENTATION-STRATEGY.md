# Data Mutation Consistency - Implementation Strategy

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│         DATA MUTATION CONSISTENCY SKILL (Primary)               │
│         Platform: Vercel + Next.js + Supabase                   │
│         Framework-agnostic for state/CMS libs                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────┐  ┌──────────────────┐  ┌────────────────┐ │
│  │  react-query-    │  │  payload-cms-    │  │  (planned)     │ │
│  │  mutations       │  │  hooks           │  │  rtk-query     │ │
│  │  Sub-Skill       │  │  Sub-Skill       │  │  sanity-cms    │ │
│  └──────────────────┘  └──────────────────┘  └────────────────┘ │
│         │                      │                                 │
│         └──────────┬───────────┘                                 │
│                    │                                             │
│         ┌──────────▼───────────┐                                │
│         │  Cross-Layer         │                                │
│         │  Validation          │                                │
│         │  (cache tags ↔ keys) │                                │
│         └──────────────────────┘                                │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Platform-specific primary** | Vercel/Next.js/Supabase is your core stack |
| **Sub-skills for libraries** | React Query, Payload are interchangeable |
| **9.0 threshold** | High bar prevents drift accumulation |
| **Advisory mode** | Warn + TODO, don't block development |
| **File-first output** | Minimize context consumption |
| **Auto-detect sub-skills** | Load based on package.json |

---

## File Structure

```
/dev-local/claude-skills/
├── data-mutation-consistency/
│   ├── SKILL.md                          # Primary skill (router)
│   ├── sub-skills/
│   │   ├── react-query-mutations.md      # React Query patterns
│   │   ├── payload-cms-hooks.md          # Payload CMS patterns
│   │   ├── rtk-query-mutations.md        # (planned)
│   │   └── sanity-cms-hooks.md           # (planned)
│   ├── config/
│   │   ├── scoring-weights.yaml          # Scoring configuration
│   │   └── detection-patterns.yaml       # Regex patterns
│   ├── templates/
│   │   ├── mutation-report.md            # Report template
│   │   ├── fix-plan.md                   # Fix plan template
│   │   └── pending-fixes.md              # Tracked issues
│   └── agents/
│       ├── analyze-mutations.yaml        # Full analysis agent
│       ├── check-mutation.yaml           # Single file agent
│       └── fix-mutations.yaml            # Fix generation agent
```

---

## Agent Specifications

### Primary Analysis Agent

```yaml
name: analyze-mutations
description: Full codebase mutation pattern analysis
trigger: "@analyze-mutations"
enforcement: advisory
output: file-first

workflow:
  # Phase 1: Discovery
  - step: detect_sub_skills
    tool: Desktop Commander:read_file
    params:
      path: "{project}/package.json"
    extract:
      - "@tanstack/react-query" → load react-query-mutations
      - "payload" → load payload-cms-hooks
    
  # Phase 2: Platform Analysis (always runs)
  - step: find_server_actions
    tool: Desktop Commander:start_search
    params:
      path: "{project}/app"
      searchType: content
      pattern: "'use server'"
      filePattern: "*.ts"
    output_to: ".claude/temp/server-actions.json"
    
  - step: find_supabase_mutations
    tool: Desktop Commander:start_search
    params:
      path: "{project}"
      searchType: content
      pattern: "supabase.*\\.(insert|update|delete|upsert)"
      filePattern: "*.ts"
    output_to: ".claude/temp/supabase-mutations.json"
    
  - step: find_revalidation
    tool: Desktop Commander:start_search
    params:
      path: "{project}"
      searchType: content
      pattern: "revalidate(Tag|Path)"
      filePattern: "*.ts"
    output_to: ".claude/temp/revalidation.json"
    
  # Phase 3: Sub-Skill Analysis (conditional)
  - step: react_query_analysis
    condition: "react-query-mutations loaded"
    delegate: sub-skill
    output_to: ".claude/temp/rq-analysis.json"
    
  - step: payload_analysis
    condition: "payload-cms-hooks loaded"
    delegate: sub-skill
    output_to: ".claude/temp/payload-analysis.json"
    
  # Phase 4: Cross-Reference
  - step: cross_validate
    action: compare
    inputs:
      - payload cache tags
      - react query key factories
    find: misalignments
    output_to: ".claude/temp/cross-validation.json"
    
  # Phase 5: Scoring
  - step: calculate_scores
    action: score
    config: "config/scoring-weights.yaml"
    inputs:
      - server-actions.json
      - supabase-mutations.json
      - revalidation.json
      - rq-analysis.json (if present)
      - payload-analysis.json (if present)
    output_to: ".claude/temp/scores.json"
    
  # Phase 6: Report Generation
  - step: generate_report
    tool: Desktop Commander:write_file
    params:
      path: ".claude/analysis/mutation-report-{timestamp}.md"
    template: "templates/mutation-report.md"
    
  - step: update_pending
    tool: Desktop Commander:write_file
    params:
      path: ".claude/analysis/pending-fixes.md"
      mode: append
    content: issues_below_threshold
    
  # Phase 7: Return Summary Only
  - step: return_summary
    action: summarize
    max_tokens: 200
    include:
      - overall_score
      - sub_skill_scores (if applicable)
      - top_3_issues
      - report_path
      
output_format: |
  ## Mutation Analysis Complete
  
  **Overall Score:** {score}/10 {status_emoji}
  
  Sub-Skills Loaded:
  {sub_skill_list}
  
  Top Issues:
  1. {issue_1}
  2. {issue_2}
  3. {issue_3}
  
  📄 Full report: `.claude/analysis/mutation-report-{timestamp}.md`
```

### Single File Check Agent

```yaml
name: check-mutation
description: Quick pattern check for single file
trigger: "@check-mutation [file]"
enforcement: advisory
output: inline (brief)

workflow:
  - step: read_file
    tool: Desktop Commander:read_file
    params:
      path: "{file}"
      
  - step: detect_type
    action: classify
    categories:
      - server_action (contains 'use server')
      - react_query_hook (contains useMutation)
      - payload_collection (contains CollectionConfig)
      - api_route (in app/api/)
      
  - step: analyze
    action: check_patterns
    against: appropriate_standard
    
  - step: score
    action: calculate_score
    
  - step: return_result
    format: inline
    template: |
      **{file}** - Score: {score}/10
      
      ✅ Present: {present_elements}
      ❌ Missing: {missing_elements}
      
      {warnings_if_below_9}
```

### Fix Generation Agent

```yaml
name: fix-mutations
description: Generate fixes for identified issues
trigger: "@fix-mutations [priority]"
enforcement: advisory
output: file

workflow:
  - step: load_pending
    tool: Desktop Commander:read_file
    params:
      path: ".claude/analysis/pending-fixes.md"
      
  - step: filter_by_priority
    action: filter
    params:
      priority: "{priority_param}"  # P0, P1, P2
      
  - step: generate_fixes
    iterate: filtered_issues
    action: generate_fix_code
    using: appropriate_template
    
  - step: write_fix_plan
    tool: Desktop Commander:write_file
    params:
      path: ".claude/analysis/fix-plan-{timestamp}.md"
    template: "templates/fix-plan.md"
    
  - step: return_summary
    template: |
      Generated fix plan for {count} {priority} issues.
      
      📄 Review: `.claude/analysis/fix-plan-{timestamp}.md`
      
      Apply with: `@apply-fixes`
```

---

## Context Window Optimization

### File-First Strategy

```yaml
principle: "Write details to files, return summaries to chat"

analysis_output:
  # Written to file (not in context)
  - Full mutation list with scores
  - Detailed element breakdown
  - Code snippets
  - Fix suggestions
  
  # Returned to chat (in context)
  - Overall score (1 line)
  - Top 3 issues (3 lines)
  - File path (1 line)

max_chat_response: 10 lines

temp_files:
  location: ".claude/temp/"
  cleanup: after_report_generated
  
report_files:
  location: ".claude/analysis/"
  naming: "{type}-{timestamp}.md"
  retention: manual (user deletes)
```

### Incremental Analysis

```yaml
# For large codebases, analyze incrementally

incremental_mode:
  trigger: "> 50 files detected"
  
  approach:
    - Analyze by domain/directory
    - Write partial results to temp files
    - Aggregate at end
    - Single report output
    
  benefit: "Never exceeds context with intermediate results"
```

---

## Integration with Existing Skills

### Anti-Pattern Agent Updates

Add to your existing `deprecated-triggers.ts`:

```typescript
// Platform (Vercel/Next.js/Supabase)
'server-action-no-revalidate': {
  regex: /'use server'[\s\S]*?supabase[\s\S]*?(?:insert|update|delete)(?![\s\S]*?revalidate)/s,
  replacement: 'Add revalidateTag or revalidatePath after mutation',
  reason: 'Server actions must revalidate cache',
  severity: 'error',
},

'supabase-no-error-check': {
  regex: /const\s*\{\s*data\s*\}\s*=\s*await\s+supabase/,
  replacement: 'Destructure error: const { data, error } = await supabase...',
  reason: 'Supabase operations can fail silently',
  severity: 'warning',
},

// React Query (from sub-skill)
'rq-inline-query-key': { /* ... */ },
'rq-optimistic-no-rollback': { /* ... */ },
'rq-convenience-no-spread': { /* ... */ },

// Payload CMS (from sub-skill)
'payload-empty-hooks': { /* ... */ },
'payload-no-after-delete': { /* ... */ },
```

### Regression Prevention Integration

Add to your RCA protocol:

```markdown
## Data Sync Issue Investigation

When debugging stale/inconsistent data:

1. **Quick Check**
   ```
   @check-mutation [affected file]
   ```

2. **If score < 9.0, run full analysis**
   ```
   @analyze-mutations
   ```

3. **Check cross-layer alignment**
   - Backend cache tags match frontend keys?
   - Admin panel operations invalidate cache?
   
4. **Document in RCA**
   - Root cause: Missing [element] in [file]
   - Add to pending-fixes.md
```

### Dependency Graph Extension

```yaml
# Add mutation mapping to dependency graph

mutation_dependencies:
  useUpdatePlayer:
    supabase_table: players
    cache_tags: ['players']
    query_keys: ['playerKeys.detail', 'playerKeys.lists']
    payload_collection: Players (if applicable)
    affected_components: [PlayerCard, PlayerList, TeamRoster]
```

---

## Implementation Phases

### Phase 1: Foundation (Days 1-2)

```markdown
## Tasks

- [ ] Create skill directory structure in /dev-local/claude-skills
- [ ] Copy SKILL.md (primary)
- [ ] Copy sub-skills/ (react-query, payload)
- [ ] Create config/scoring-weights.yaml
- [ ] Create templates/mutation-report.md

## Validation
- [ ] Manual test: @analyze-mutations on rhize-lms
- [ ] Verify file output works
- [ ] Check score calculation
```

### Phase 2: Agent Automation (Days 3-4)

```markdown
## Tasks

- [ ] Implement analyze-mutations agent workflow
- [ ] Implement check-mutation agent
- [ ] Test Desktop Commander integration
- [ ] Tune detection patterns

## Validation
- [ ] Agent produces correct report
- [ ] Summary is concise (< 10 lines)
- [ ] Full details in file
```

### Phase 3: Integration (Days 5-6)

```markdown
## Tasks

- [ ] Add triggers to anti-pattern-agent
- [ ] Update regression-prevention RCA
- [ ] Add mutation mapping to dependency-graph
- [ ] Create fix-mutations agent

## Validation
- [ ] Anti-patterns detected at write-time
- [ ] Fix generation works
- [ ] Cross-skill references function
```

### Phase 4: Refinement (Ongoing)

```markdown
## Tasks

- [ ] Tune 9.0 threshold based on real usage
- [ ] Add project-specific overrides
- [ ] Document edge cases
- [ ] Create additional sub-skills as needed

## Metrics to Track
- False positive rate (< 10% target)
- Issues caught before commit
- Time saved in debugging
```

---

## Configuration Templates

### Project Configuration

```yaml
# .claude/mutation-patterns.yaml (per-project)

platform:
  deployment: vercel
  framework: nextjs
  database: supabase
  
analysis:
  output_dir: ".claude/analysis"
  
enforcement:
  mode: advisory
  warning_threshold: 9.0
  critical_threshold: 7.0
  add_todos: true
  
sub_skills:
  auto_detect: true
  # Or manual:
  # enabled:
  #   - react-query-mutations
  #   - payload-cms-hooks
  
ignore:
  paths:
    - "**/test/**"
    - "**/__mocks__/**"
    - "**/migrations/**"
  files:
    - "*.test.ts"
    - "*.spec.ts"
    - "*.d.ts"
```

### Scoring Weights

```yaml
# config/scoring-weights.yaml

platform:
  error_handling: 1.5
  cache_revalidation: 1.5
  type_safety: 1.3
  input_validation: 1.0
  
react_query:
  query_key_factory: 1.5
  optimistic_update: 1.2
  rollback_context: 1.4
  cache_invalidation: 1.4
  user_feedback: 0.8
  
payload:
  after_change_hook: 1.5
  after_change_cache: 1.5
  after_delete_hook: 1.3
  after_delete_cache: 1.3
  before_change_validation: 1.0
  
thresholds:
  warning: 9.0
  critical: 7.0
```

---

## Success Criteria

| Metric | Target | Measurement |
|--------|--------|-------------|
| Analysis Speed | < 30s | Time for @analyze-mutations |
| Report Completeness | 100% | All mutations analyzed |
| Context Usage | < 500 tokens | Chat response size |
| False Positives | < 10% | User overrides with valid reason |
| Pattern Coverage | 95%+ | Mutations following standards |
| New Mutation Compliance | 100% | Pre-write checks pass |

---

## Quick Start

1. **Copy skills to your directory:**
   ```bash
   cp -r /path/to/skills/data-mutation-consistency /dev-local/claude-skills/
   ```

2. **Create project config:**
   ```bash
   mkdir -p .claude/analysis
   # Copy mutation-patterns.yaml template
   ```

3. **Run initial analysis:**
   ```
   @analyze-mutations
   ```

4. **Review report:**
   ```bash
   cat .claude/analysis/mutation-report-*.md
   ```

5. **Generate fixes:**
   ```
   @fix-mutations P1
   ```

---

## Files Delivered

| File | Description |
|------|-------------|
| SKILL-data-mutation-consistency-v1.md | Primary skill (platform-focused) |
| sub-skills/react-query-mutations.md | React Query sub-skill |
| sub-skills/payload-cms-hooks.md | Payload CMS sub-skill |
| IMPLEMENTATION-STRATEGY.md | This document |
