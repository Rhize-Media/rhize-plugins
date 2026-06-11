# Skill Foundations Master Index

> **Status:** Foundation Drafts Ready for Iteration
> **Created:** 2024-12-01
> **Project:** vba-lms-app Development Workflow Optimization

---

## Overview

This document indexes the skill foundation documents created to optimize Claude Code development workflows. Each skill addresses specific pain points in large codebase development.

## Pain Points → Skills Mapping

| Pain Point | Primary Skill | Supporting Skills |
|------------|---------------|-------------------|
| Incomplete implementations across files | Dependency Graph | Component Registry |
| Code duplication | Component Registry | Anti-Pattern Agent |
| Outdated documentation | Context Hygiene | Skill Refinement |
| Context window exhaustion | Context Hygiene | Session Management |
| Circular debugging | Regression Prevention | Skill Refinement |
| Anti-patterns slipping through | Anti-Pattern Agent | Skill Refinement |

---

## Skill Documents

### 1. Dependency Graph & Impact Mapping
**File:** `SKILL-dependency-graph-v1.md`
**Purpose:** Enforces impact analysis before implementation

**Key Features:**
- Data type dependency extraction (not just file imports)
- Fetch optimization insights from dependency analysis
- Query optimization recommendations
- [TO-DO] Graphiti MCP integration for graph-based queries

**Status:** Foundation ready | Needs: AST script completion, Graphiti integration

---

### 2. Component & Function Registry
**File:** `SKILL-component-registry-v1.md`
**Purpose:** Living index with data fetching and state management tracking

**Key Features:**
- Data fetching strategy tracking (server vs client)
- State management strategy classification
- Return type → prop type matching for duplicate prevention
- Auto-generation scripts

**Status:** Foundation ready | Needs: Generation script testing, type diffing implementation

---

### 3. Context Hygiene & Session Management
**File:** `SKILL-context-hygiene-v1.md`
**Purpose:** Keep documentation lean and manage context efficiently

**Key Features:**
- CLAUDE.md as router pattern (<200 lines)
- Session boundary guidelines
- Context preservation with Zen MCP and SuperClaude
- Documentation freshness automation

**Status:** Foundation ready | Needs: Git hooks implementation, CLAUDE.md restructure

---

### 4. Regression Prevention
**File:** `SKILL-regression-prevention-v1.md`
**Purpose:** Break circular debugging cycles

**Key Features:**
- Mandatory root cause analysis protocol
- Test-first verification workflow
- Multi-model validation for complex fixes
- Context recovery for long debugging sessions

**Status:** Foundation ready | Needs: Sentry/Vercel MCP integration testing

---

### 5. Skill Refinement Meta-Skill
**File:** `SKILL-refinement-meta-v1.md`
**Purpose:** Create and improve skills from discovered patterns

**Key Features:**
- Insight → Skill capture workflow
- Pattern detection and recording
- Pattern categories (data fetching, state management, error handling)
- Documentation integration triggers

**Status:** Foundation ready | Needs: Pattern templates for vba-lms-app specifics

---

### 6. Anti-Pattern Detection Agent
**File:** `SKILL-anti-pattern-agent-v1.md`
**Purpose:** Actively prevent deprecated patterns at write-time

**Key Features:**
- Deprecated word/pattern trigger system
- Project-specific rule configuration
- Framework/package version awareness
- Severity-based intervention (error/warning/info)

**Status:** Foundation ready | Needs: deprecated-triggers.ts creation, vba-lms-app rules

---

## Iteration Roadmap

### Phase 1: Foundation Testing (Week 1)
- [ ] Restructure vba-lms-app CLAUDE.md to router pattern
- [ ] Create DEPRECATED.md with known anti-patterns
- [ ] Create PATTERNS.md with established patterns
- [ ] Test manual execution of each skill workflow

### Phase 2: Automation (Week 2)
- [ ] Implement component registry generation script
- [ ] Set up git hooks for documentation freshness
- [ ] Create deprecated-triggers.ts configuration
- [ ] Test Zen MCP context save/restore workflow

### Phase 3: MCP Integration (Week 3)
- [ ] Integrate Sentry queries into regression prevention
- [ ] Integrate Vercel deployment queries
- [ ] Test multi-model validation with Zen
- [ ] [TO-DO] Evaluate Graphiti MCP for dependency graphs

### Phase 4: Refinement (Week 4+)
- [ ] Review skill activation accuracy
- [ ] Adjust trigger conditions based on real usage
- [ ] Add vba-lms-app specific examples to each skill
- [ ] Document successful patterns discovered

---

## TO-DO Items Across All Skills

### Graphiti MCP Integration
- **Where:** Dependency Graph skill
- **What:** Graph-based storage and query for dependency relationships
- **Why:** O(1) traversal vs O(n) file scan, multi-hop analysis
- **When:** After validating markdown approach works

### Enhanced Registry Features
- **Where:** Component Registry skill
- **What:** 
  - Data fetching strategy classification
  - State management strategy tracking
  - Return type → prop type matching
- **Why:** Better duplicate prevention, pattern enforcement
- **When:** Phase 2, during registry script development

### Anti-Pattern Agent Automation
- **Where:** Anti-Pattern Agent skill
- **What:**
  - deprecated-triggers.ts file
  - IDE/ESLint integration investigation
  - Auto-update from package changelogs
- **Why:** Catch patterns at write-time, not review-time
- **When:** Phase 2-3

---

## Skill Interconnections

```
┌─────────────────────────────────────────────────────────────────┐
│                     SKILL ECOSYSTEM                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   ┌─────────────────┐                                          │
│   │  Context        │◄────────── Updates ──────────┐           │
│   │  Hygiene        │                              │           │
│   └────────┬────────┘                              │           │
│            │                                       │           │
│            │ Loads                                 │           │
│            ▼                                       │           │
│   ┌─────────────────┐      ┌─────────────────┐    │           │
│   │  Dependency     │◄────►│  Component      │    │           │
│   │  Graph          │      │  Registry       │    │           │
│   └────────┬────────┘      └────────┬────────┘    │           │
│            │                        │              │           │
│            │ Feeds into            │ Validates    │           │
│            ▼                        ▼              │           │
│   ┌─────────────────┐      ┌─────────────────┐    │           │
│   │  Regression     │      │  Anti-Pattern   │    │           │
│   │  Prevention     │      │  Agent          │    │           │
│   └────────┬────────┘      └────────┬────────┘    │           │
│            │                        │              │           │
│            │ Documents             │ Detects      │           │
│            └────────────┬──────────┘              │           │
│                         ▼                          │           │
│                ┌─────────────────┐                 │           │
│                │  Skill          │─────────────────┘           │
│                │  Refinement     │                             │
│                │  (Meta-Skill)   │                             │
│                └─────────────────┘                             │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Quick Start for Iteration

### To Review/Edit a Skill:
1. Download the skill file from outputs
2. Add to project knowledge or local development
3. Test workflow manually in Claude Code session
4. Note what works/doesn't work
5. Update the skill document
6. Re-upload to project knowledge

### To Test a Skill:
```
In Claude Code session:
"Let's test the [skill name] workflow. Here's the scenario: [describe task]
Follow the skill protocol and let me know where it helps or hinders."
```

### To Suggest Improvements:
Add comments directly in the skill markdown:

```markdown
<!-- FEEDBACK: This section was unclear when... -->
<!-- SUGGESTION: Add example for... -->
<!-- BUG: This trigger didn't activate when... -->
```

---

## Files Created

| File | Size | Purpose |
|------|------|---------|
| SKILL-dependency-graph-v1.md | ~15KB | Impact mapping before implementation |
| SKILL-component-registry-v1.md | ~18KB | Living component/function index |
| SKILL-context-hygiene-v1.md | ~14KB | Documentation and session management |
| SKILL-regression-prevention-v1.md | ~16KB | Root cause analysis and fix verification |
| SKILL-refinement-meta-v1.md | ~17KB | Pattern capture and skill improvement |
| SKILL-anti-pattern-agent-v1.md | ~15KB | Deprecated pattern detection |
| **SKILL-foundations-index.md** | ~8KB | This file - master index |

**Total:** ~100KB of skill foundations

---

## Next Steps

1. **Download all files** from `/mnt/user-data/outputs/`
2. **Add to project knowledge** for iteration
3. **Restructure vba-lms-app** with router-pattern CLAUDE.md
4. **Test each workflow** in real development sessions
5. **Iterate** based on what works

---

## Feedback Loop

As you use these skills, track:
- What triggers correctly?
- What's missing?
- What's too verbose/not verbose enough?
- What integrations would help most?

Update the relevant skill document and re-upload to iterate.
