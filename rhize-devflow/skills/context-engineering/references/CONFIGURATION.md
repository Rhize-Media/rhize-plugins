# Configuration Reference

> Project-type templates and customization for context engineering

---

## Overview

Context engineering configuration varies by:
- **Project type**: Web app, API, mobile, data/ML, CLI
- **Team size**: Solo, small team, large team
- **Technology stack**: Languages, frameworks, tools

This reference provides templates to customize memory extraction, session management, and retrieval strategies.

---

## Project Type Configurations

### Web Application (Full-Stack)

```yaml
context_engineering:
  project_type: web_fullstack
  
  memory:
    declarative_topics:
      - user_preferences
      - frontend_architecture
      - backend_architecture
      - api_patterns
      - data_model
      - integrations
      - constraints
      
    procedural_topics:
      - data_fetching
      - state_management
      - error_handling
      - testing
      - deployment
      
    extraction_triggers:
      - explicit_preference
      - architecture_decision
      - pattern_discovery
      - error_resolution
      
  sessions:
    mandatory_new:
      - repository_switch
      - feature_complete
      - context_exhaustion
    recommended_new:
      message_count: 25
      duration_minutes: 90
    compaction: recursive_summarization
    keep_recent: 10
      
  retrieval:
    proactive:
      - user_preferences
      - active_project_context
      - critical_constraints
    reactive:
      - historical_patterns
      - past_errors
      - archived_decisions
```

---

### API / Backend Service

```yaml
context_engineering:
  project_type: api_backend
  
  memory:
    declarative_topics:
      - api_design
      - data_model
      - auth_patterns
      - performance_constraints
      - integrations
      
    procedural_topics:
      - request_handling
      - error_responses
      - testing
      - debugging
      - deployment
      
    extraction_triggers:
      - schema_decision
      - endpoint_pattern
      - error_pattern
      
  sessions:
    mandatory_new:
      - schema_migration
      - api_version_change
      - feature_complete
    recommended_new:
      message_count: 30
      duration_minutes: 120
    compaction: topic_filter
    relevance_threshold: 0.7
      
  retrieval:
    proactive:
      - api_patterns
      - data_model
    reactive:
      - past_errors
      - performance_history
```

---

### Mobile Application

```yaml
context_engineering:
  project_type: mobile_app
  
  memory:
    declarative_topics:
      - platform_specifics
      - ui_patterns
      - offline_support
      - device_constraints
      - store_requirements
      
    procedural_topics:
      - state_persistence
      - api_integration
      - testing
      - release_process
      
    extraction_triggers:
      - platform_decision
      - ui_pattern
      - performance_requirement
      
  sessions:
    mandatory_new:
      - platform_switch
      - release_complete
    recommended_new:
      message_count: 25
      duration_minutes: 90
      
  retrieval:
    proactive:
      - platform_specifics
      - ui_patterns
    reactive:
      - past_issues
      - store_feedback
```

---

### Data Pipeline / ML

```yaml
context_engineering:
  project_type: data_ml
  
  memory:
    declarative_topics:
      - data_sources
      - transformations
      - model_architecture
      - evaluation_metrics
      - infrastructure
      
    procedural_topics:
      - data_validation
      - experiment_tracking
      - deployment
      - monitoring
      
    extraction_triggers:
      - experiment_result
      - model_decision
      - data_discovery
      
  sessions:
    mandatory_new:
      - experiment_complete
      - data_schema_change
      - model_version_change
    recommended_new:
      message_count: 40
      duration_minutes: 180
      
  retrieval:
    proactive:
      - current_experiment
      - model_config
    reactive:
      - past_experiments
      - failed_approaches
```

---

### CLI Tool / Library

```yaml
context_engineering:
  project_type: cli_library
  
  memory:
    declarative_topics:
      - api_surface
      - compatibility
      - conventions
      
    procedural_topics:
      - testing
      - documentation
      - release
      
    extraction_triggers:
      - api_decision
      - breaking_change
      - convention_established
      
  sessions:
    mandatory_new:
      - breaking_change
      - release_complete
    recommended_new:
      message_count: 20
      duration_minutes: 60
      
  retrieval:
    proactive:
      - api_surface
      - compatibility
    reactive:
      - past_releases
      - user_feedback
```

---

## Team Size Configurations

### Solo Developer

```yaml
team_config:
  size: solo
  
  memory:
    scope: personal
    isolation: project
    
  sessions:
    handoff: async
    key_pattern: "{project}-{feature}-{date}"
    
  documentation:
    audience: self
    verbosity: minimal
    
  recommendations:
    - Use memory aggressively (no team sync issues)
    - Session handoffs for multi-day work
    - Consolidate weekly
```

---

### Small Team (2-5)

```yaml
team_config:
  size: small_team
  
  memory:
    scope: 
      personal: user_preferences, working_style
      shared: architecture, patterns, decisions
    isolation: user + project
    
  sessions:
    handoff: structured
    key_pattern: "{project}-{feature}-{user}-v{n}"
    
  documentation:
    audience: team
    verbosity: moderate
    include_rationale: true
    
  recommendations:
    - Shared decision memory
    - Personal preference memory
    - Clear handoffs for pair programming
```

---

### Large Team (5+)

```yaml
team_config:
  size: large_team
  
  memory:
    scope:
      personal: preferences, working_style
      team: patterns, conventions
      project: architecture, decisions
    isolation: strict
    
  sessions:
    handoff: formal
    key_pattern: "{project}-{area}-{feature}-{user}"
    
  documentation:
    audience: external
    verbosity: high
    include_rationale: always
    link_decisions: true
    
  recommendations:
    - Formal decision records (ADRs)
    - Pattern library with memory integration
    - Regular consolidation reviews
    - Clear ownership boundaries
```

---

## Memory Topic Templates

### Standard Development Topics

```yaml
declarative_memory_topics:

  user_preferences:
    description: User's tool and workflow preferences
    examples:
      - "Prefers {language} over alternatives"
      - "Uses {tool} for {purpose}"
    confidence_boost: explicit_statement
    
  project_architecture:
    description: System design and structure
    examples:
      - "System uses {architecture_pattern}"
      - "Chose {technology} for {component}"
    confidence_boost: includes_rationale
    
  technical_constraints:
    description: Hard requirements and limitations
    examples:
      - "Must support {requirement}"
      - "Cannot exceed {limit}"
    confidence_boost: documented_requirement
    
  error_solutions:
    description: Problems solved and fixes
    examples:
      - "{Error} caused by {cause}, fixed by {solution}"
    confidence_boost: verified_working

procedural_memory_topics:

  debug_workflow:
    description: How to investigate issues
    examples:
      - "Start debugging by {first_step}"
      - "For {error_type}, check {resources} first"
    activation: error_investigation
    
  implementation_pattern:
    description: How to build features
    examples:
      - "For {feature_type}, use {pattern}"
    activation: feature_implementation
    
  review_process:
    description: How to validate work
    examples:
      - "Before committing, run {checks}"
    activation: pre_commit
```

---

## Extraction Prompt Templates

### General Extraction

```markdown
Analyze this conversation and extract memories.

EXTRACT ONLY:
- Explicit preferences ("I prefer X")
- Decisions with rationale ("We chose X because Y")
- Verified solutions ("The fix was X")
- Repeated patterns (same approach used multiple times)

FOR EACH MEMORY:
1. Type: declarative or procedural
2. Category: preference | fact | constraint | pattern | solution
3. Content: 1-2 sentence summary
4. Confidence: high | medium | low
5. Evidence: Quote from conversation

DO NOT EXTRACT:
- Conversational filler
- Failed attempts
- Common knowledge
- Speculative statements
```

### Domain-Specific Prompts

**Frontend:**
```markdown
Focus on: components, state, styling, accessibility, performance
```

**Backend:**
```markdown
Focus on: API design, data model, auth, error handling, caching
```

**DevOps:**
```markdown
Focus on: deployment, environments, scaling, monitoring, security
```

---

## Configuration Validation

```markdown
VALIDATION CHECKLIST:

[ ] Memory topics match project domain
[ ] Extraction triggers are specific
[ ] Session boundaries prevent exhaustion
[ ] Retrieval strategy matches use case
[ ] Team scope is appropriately isolated
[ ] Compaction preserves important context
[ ] Documentation verbosity matches audience
```

---

## Configuration Anti-Patterns

### Over-Extraction

```yaml
# ❌ BAD
extraction_triggers:
  - any_statement
  - all_code_blocks
```

### No Isolation

```yaml
# ❌ BAD
memory:
  scope: global  # All projects, all users
```

### Static Thresholds

```yaml
# ❌ BAD
sessions:
  message_count: 20  # Always same limit
```

### Better Approach

```yaml
# ✅ GOOD
sessions:
  simple_task:
    message_count: 15
  complex_feature:
    message_count: 30
  debugging:
    message_count: 50
```

---

## Model-Specific Limits

| Model | Context Window | Recommended Max Usage |
|-------|---------------|----------------------|
| Claude 3.5 | 200,000 | 70% (140k) |
| Claude 3 Opus | 200,000 | 70% (140k) |
| GPT-4 Turbo | 128,000 | 70% (90k) |
| GPT-4 | 8,192 | 70% (5.7k) |
| Gemini Pro | 32,000 | 70% (22k) |

Adjust session boundaries and compaction based on model limits.
