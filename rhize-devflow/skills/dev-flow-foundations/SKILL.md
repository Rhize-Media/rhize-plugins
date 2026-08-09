---
name: dev-flow-foundations
tier: custom
domain: dev-flow
maturity: stable
version: 1.0.0
description: >-
  Foundational workflow patterns for large-codebase development — dependency-graph impact mapping,
  component/function registry to prevent duplication, context hygiene, regression prevention,
  anti-pattern detection at write-time, and skill-refinement meta-patterns. Use when the user asks
  about "design patterns", "workflow optimization", "prevent regression", "anti-patterns",
  "dependency mapping", "component registry", "why did this break again", or wants to set up
  durable development guardrails. Reference layer that informs context-engineering and
  error-lifecycle-management; also encodes Boris Cherny's verify-first and worktree practices.
metadata:
  rhize:
    topics: [workflow-patterns, project-planning]
    stacks: []

---

# Dev Flow Foundations

> Foundational patterns and protocols for optimized Claude Code development workflows.

---

## Overview

These foundation documents address six core development workflow challenges:

| Challenge | Foundation | Key Concept |
|-----------|------------|-------------|
| Incomplete implementations | [Dependency Graph](SKILL-dependency-graph-v1.md) | Map impact before changing |
| Code duplication | [Component Registry](SKILL-component-registry-v1.md) | Track what exists, reuse first |
| Outdated context | [Context Hygiene](SKILL-context-hygiene-v1.md) | Keep docs lean, sessions bounded |
| Circular debugging | [Regression Prevention](SKILL-regression-prevention-v1.md) | Root cause first, test before deploy |
| Anti-patterns slipping | [Anti-Pattern Agent](SKILL-anti-pattern-agent-v1.md) | Catch at write-time, not review |
| Lost patterns | [Skill Refinement](SKILL-refinement-meta-v1.md) | Capture and formalize what works |

---

## Documents

### [Dependency Graph & Impact Mapping](SKILL-dependency-graph-v1.md)

**Problem:** Changes to one file break unexpected others.

**Solution:** 
- Map data type dependencies (not just imports)
- Analyze impact before implementation
- Track fetch optimization opportunities

**Key Pattern:** "What uses this?" before "How do I change this?"

---

### [Component & Function Registry](SKILL-component-registry-v1.md)

**Problem:** Duplicate components created instead of reusing existing.

**Solution:**
- Living index of components, hooks, utilities
- Data fetching strategy tracking
- Return type → prop type matching

**Key Pattern:** Search registry before creating new.

---

### [Context Hygiene & Session Management](SKILL-context-hygiene-v1.md)

**Problem:** Context window exhaustion, stale documentation.

**Solution:**
- CLAUDE.md as router (<200 lines)
- Clear session boundaries
- Freshness automation

**Key Pattern:** Reference, don't embed. New session when focus changes.

---

### [Regression Prevention](SKILL-regression-prevention-v1.md)

**Problem:** Fixes create new bugs, circular debugging cycles.

**Solution:**
- Mandatory root cause analysis
- Test-first verification
- Multi-model validation for complex fixes

**Key Pattern:** Understand why before fixing how.

---

### [Anti-Pattern Agent](SKILL-anti-pattern-agent-v1.md)

**Problem:** Deprecated patterns slip into codebase.

**Solution:**
- Trigger-based pattern detection
- Severity levels (error/warning/info)
- Framework version awareness

**Key Pattern:** Block bad patterns at write-time.

---

### [Skill Refinement Meta-Skill](SKILL-refinement-meta-v1.md)

**Problem:** Good patterns discovered but not captured.

**Solution:**
- Insight → Skill workflow
- Pattern categorization
- Documentation integration

**Key Pattern:** When something works twice, make it a skill.

---

## Interconnections

```
┌─────────────────────────────────────────────────────────────────┐
│                     FOUNDATION ECOSYSTEM                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   ┌─────────────────┐                                          │
│   │  Context        │◄────────── Updates ──────────┐           │
│   │  Hygiene        │                              │           │
│   └────────┬────────┘                              │           │
│            │ Informs                               │           │
│            ▼                                       │           │
│   ┌─────────────────┐      ┌─────────────────┐    │           │
│   │  Dependency     │◄────►│  Component      │    │           │
│   │  Graph          │      │  Registry       │    │           │
│   └────────┬────────┘      └────────┬────────┘    │           │
│            │ Feeds into            │ Validates    │           │
│            ▼                        ▼              │           │
│   ┌─────────────────┐      ┌─────────────────┐    │           │
│   │  Regression     │      │  Anti-Pattern   │    │           │
│   │  Prevention     │      │  Agent          │    │           │
│   └────────┬────────┘      └────────┬────────┘    │           │
│            │ Documents             │ Detects      │           │
│            └────────────┬──────────┘              │           │
│                         ▼                          │           │
│                ┌─────────────────┐                 │           │
│                │  Skill          │─────────────────┘           │
│                │  Refinement     │                             │
│                └─────────────────┘                             │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Relationship to Other Skills

These foundations inform practical implementations:

| Foundation | Implemented In |
|------------|----------------|
| Context Hygiene | context-engineering (hooks, commands) |
| Dependency Graph | context-engineering (/impact-map command) |
| Component Registry | context-engineering (duplicate-check hook) |
| Regression Prevention | error-lifecycle-management (triage workflow) |
| Anti-Pattern Agent | error-lifecycle-management (validation scripts) |

---

## Using These Documents

**For Learning:** Read to understand the "why" behind workflow patterns.

**For Implementation:** Extract specific protocols into project-specific skills.

**For Reference:** Link from CLAUDE.md when relevant patterns apply.

**For Iteration:** Add `<!-- FEEDBACK -->` comments when patterns don't work.

---

## Files

| Document | Focus |
|----------|-------|
| [SKILL-dependency-graph-v1.md](SKILL-dependency-graph-v1.md) | Impact analysis |
| [SKILL-component-registry-v1.md](SKILL-component-registry-v1.md) | Reuse tracking |
| [SKILL-context-hygiene-v1.md](SKILL-context-hygiene-v1.md) | Context management |
| [SKILL-regression-prevention-v1.md](SKILL-regression-prevention-v1.md) | Debug cycles |
| [SKILL-anti-pattern-agent-v1.md](SKILL-anti-pattern-agent-v1.md) | Pattern enforcement |
| [SKILL-refinement-meta-v1.md](SKILL-refinement-meta-v1.md) | Skill improvement |
| [SKILL-foundations-index.md](SKILL-foundations-index.md) | Original index |
| [Claude-dev-flow-optimization.md](Claude-dev-flow-optimization.md) | Overview document |
