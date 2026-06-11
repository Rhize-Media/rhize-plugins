# Regression Prevention Skill

> **Status:** Foundation Draft v1
> **Last Updated:** 2024-12-01
> **Dependencies:** Sentry MCP, Vercel MCP, Git MCP, Zen MCP

---

## Overview

This skill breaks the cycle of "fix one thing, break another" by enforcing systematic root cause analysis, test-first verification, and multi-model validation for complex fixes. The goal is to prevent the circular debugging sessions that consume context windows and developer time.

## The Problem This Solves

```
Typical Regression Cycle:
1. Bug reported
2. Quick fix applied (symptom addressed, not root cause)
3. Fix breaks something else
4. New fix applied
5. Original bug returns (or variant)
6. Context window exhausted
7. Session reset, context lost
8. Repeat from step 1
```

```
Target Flow:
1. Bug reported
2. Root cause analysis (mandatory)
3. Impact analysis (from Dependency Graph skill)
4. Test written to verify bug
5. Fix applied
6. Test passes + regression tests pass
7. Multi-model validation (complex cases)
8. Done - root cause documented for future reference
```

---

## Trigger Conditions

Activate this skill when:
- User mentions: "bug", "broken", "not working", "error", "regression", "fix"
- Sentry error is referenced
- User is attempting to modify code to fix an issue
- Second attempt at fixing the same issue

## Hard Stop Trigger

If Claude is about to write phrases like:
- "Let me try this quick fix..."
- "This should work..."
- "Let's just change this one line..."
- "Try this and see if it works..."

**STOP.** These indicate we're skipping root cause analysis.

---

## Phase 1: Root Cause Analysis (Mandatory)

### Before ANY Code Changes

```markdown
## Root Cause Analysis Template

### 1. Symptom Description
What is the observable problem?
- Error message (if any):
- Expected behavior:
- Actual behavior:
- Reproducibility: [always / sometimes / rare]

### 2. Timeline Investigation
When did this start?
- [ ] Check Sentry for first occurrence
- [ ] Check Vercel deployments for correlation
- [ ] Check git log for recent changes to affected files

### 3. Hypothesis Formation
What COULD be causing this? (List at least 3 possibilities)
1. [Hypothesis A]
2. [Hypothesis B]  
3. [Hypothesis C]

### 4. Evidence Gathering
For each hypothesis, what evidence supports or refutes it?

| Hypothesis | Supporting Evidence | Refuting Evidence | Confidence |
|------------|--------------------|--------------------|------------|
| A | | | low/medium/high |
| B | | | low/medium/high |
| C | | | low/medium/high |

### 5. Root Cause Identification
Based on evidence, the root cause is:
[Clear statement of WHY the bug exists, not just WHERE]

### 6. Why Did We Ship This?
Understanding how this got past review:
- [ ] Missing test coverage
- [ ] Edge case not considered
- [ ] Type system didn't catch it
- [ ] Integration issue (works in isolation)
- [ ] Environment difference (dev vs prod)
- [ ] Data-dependent (specific data triggers bug)
- [ ] Race condition / timing issue
- [ ] Third-party API change
- [ ] Other: _______________

### 7. Systemic Fix Needed?
Does this reveal a pattern that needs addressing?
- [ ] No - isolated incident
- [ ] Yes - add to anti-pattern list
- [ ] Yes - update skill with new guidance
- [ ] Yes - add linting rule / type constraint
```

### MCP Integration for RCA

```markdown
## Automated Investigation Steps

### Step 1: Sentry Context
Use: sentry:list_issues
Filter: filename contains [affected file]
Look for:
- Stack traces
- Breadcrumbs leading to error
- User context
- Release correlation

### Step 2: Deployment Correlation  
Use: vercel:deployments (last 10)
Look for:
- Deployment time vs error first seen
- Environment variables changed
- Build differences

### Step 3: Git History
Use: git:log --oneline -20 -- [affected files]
Look for:
- Recent changes to affected files
- Related changes in same commits
- Author (for additional context)

### Step 4: Zen Deep Think (Complex Cases)
Use: zen thinkdeep with max thinking mode
Prompt: "Analyze this bug with the following context: [symptoms], [hypotheses], [evidence]. What is the most likely root cause and why?"
```

---

## Phase 2: Impact Analysis

Before implementing the fix, run the Dependency Graph skill:

```markdown
## Pre-Fix Impact Check

Using Dependency Graph skill, identify:

### Files That Will Change
| File | Change Type | Risk Level |
|------|-------------|------------|
| [file] | [modify/add/delete] | [low/medium/high] |

### Cascade Effects
| Changed File | Affects | How |
|--------------|---------|-----|
| [file A] | [file B] | [import/type/prop] |

### Test Files Needed
| Test File | Status | Needs Update |
|-----------|--------|--------------|
| [test file] | [exists/missing] | [yes/no] |
```

---

## Phase 3: Test-First Verification

### The Rule
> Write a test that fails BEFORE writing the fix.
> The test proves the bug exists.
> The fix is complete when the test passes.

### Test Template for Bug Fixes

```typescript
// __tests__/regression/[bug-id]-[brief-description].test.ts

describe('Regression: [Brief description of bug]', () => {
  /**
   * Bug: [Link to issue or Sentry error]
   * Root Cause: [Brief explanation]
   * Fixed in: [commit hash or PR]
   */
  
  it('should [expected behavior that was broken]', async () => {
    // Arrange: Set up the conditions that trigger the bug
    const input = /* ... */;
    
    // Act: Perform the action that caused the bug
    const result = await functionUnderTest(input);
    
    // Assert: Verify correct behavior
    expect(result).toBe(/* expected */);
  });
  
  // Additional edge cases revealed during investigation
  it('should handle [edge case 1]', async () => { /* ... */ });
  it('should handle [edge case 2]', async () => { /* ... */ });
});
```

### Verification Checklist

```markdown
## Pre-Fix Verification
- [ ] Test written that reproduces the bug
- [ ] Test FAILS before fix is applied
- [ ] Test clearly documents the bug and root cause

## Post-Fix Verification
- [ ] Bug reproduction test now PASSES
- [ ] All existing tests still pass
- [ ] No new TypeScript errors introduced
- [ ] Linting passes
```

---

## Phase 4: Fix Implementation

### Implementation Guidelines

```markdown
## Fix Implementation Rules

### DO:
- Fix the root cause, not the symptom
- Make the smallest change that fixes the issue
- Add type constraints that prevent recurrence
- Add comments explaining WHY if not obvious
- Consider if this fix should apply elsewhere

### DON'T:
- Add defensive code without understanding why it's needed
- Suppress errors/warnings without fixing underlying issue
- Copy-paste fixes without understanding them
- Skip tests "because it's a simple fix"
- Fix multiple unrelated issues in one change
```

### Fix Documentation

```typescript
// In the code, document non-obvious fixes:

// FIX(2024-12-01): Handle null player when team is empty
// Root cause: getTeamPlayers returns [] not null, but downstream
// code assumed null check was sufficient. See: [issue link]
if (!players || players.length === 0) {
  return <EmptyState />;
}
```

---

## Phase 5: Regression Testing

### Comprehensive Test Run

```markdown
## Regression Test Checklist

### Automated Checks
- [ ] `pnpm typecheck` - No TypeScript errors
- [ ] `pnpm lint` - No linting errors  
- [ ] `pnpm test` - All unit tests pass
- [ ] `pnpm test:integration` - Integration tests pass (if applicable)

### Manual Verification (if needed)
- [ ] Reproduce original bug - now fixed
- [ ] Test related functionality
- [ ] Test on different screen sizes (if UI)
- [ ] Test with different data states (empty, full, error)

### Zen Precommit (Recommended)
Use: zen precommit
Validates changes against:
- Potential regressions
- Code quality issues
- Missing error handling
- Type safety concerns
```

---

## Phase 6: Multi-Model Validation (Complex Fixes)

For fixes that:
- Touch core business logic
- Affect multiple files
- Involve concurrency/timing
- Have unclear root cause

### Zen Consensus Validation

```markdown
## Multi-Model Validation

Use: zen consensus with pro and o3

Prompt template:
"Review this bug fix for potential issues:

BUG: [description]
ROOT CAUSE: [what we determined]
FIX: [what we changed]
FILES AFFECTED: [list]

Questions:
1. Does this fix address the root cause or just the symptom?
2. Could this fix introduce new bugs?
3. Are there edge cases we haven't considered?
4. Is there a simpler/safer approach?
5. What tests would give confidence this is complete?"
```

---

## Phase 7: Documentation & Learning

### Post-Fix Documentation

```markdown
## Bug Resolution Summary

### Issue
[Brief description]

### Root Cause
[What was actually wrong]

### Fix Applied
[What was changed]

### Files Modified
- [file 1]: [what changed]
- [file 2]: [what changed]

### Tests Added
- [test 1]: [what it verifies]

### Prevention Measures
[How to prevent similar bugs]

### Pattern Update Needed?
- [ ] No
- [ ] Yes - update PATTERNS.md with: [new guidance]
- [ ] Yes - add to DEPRECATED.md: [anti-pattern identified]
- [ ] Yes - update skill: [which skill, what content]
```

### Insight Capture

Link to Skill Refinement meta-skill:
- If a new pattern was discovered → Document in PATTERNS.md
- If an anti-pattern was identified → Add to DEPRECATED.md
- If a skill would have helped → Update appropriate skill

---

## Emergency Procedures

### When Stuck in Regression Loop

If we've attempted 3+ fixes without success:

```markdown
## Regression Loop Escape Protocol

1. STOP making changes
2. Revert to last known good state
3. Document everything tried so far
4. Use zen to save context: "regression-debug-[issue]"
5. Start fresh session
6. Restore context from zen
7. Request multi-model RCA:
   "Use zen thinkdeep with max thinking to analyze this 
    regression loop: [summary of attempts]"
```

### When Context Window Exhausted

```markdown
## Context Recovery for Bug Fixes

Before session ends, create:

### bug-context-[issue].md
```markdown
# Bug Fix Context: [Issue]

## Current Status
[Where we left off]

## Root Cause (if identified)
[Our current understanding]

## Attempts Made
1. [What we tried] - [Result]
2. [What we tried] - [Result]

## Files Investigated
- [file]: [relevant findings]

## Next Steps
1. [What to try next]

## Key Insights
- [Important discoveries]
```

Save to zen: "bug-fix-[issue]-context"
```

---

## Integration with Other Skills

### → Dependency Graph Skill
- Use impact map before implementing fix
- Identify all affected files

### → Component Registry Skill  
- Check if fix affects registered components
- Update registry if component behavior changes

### → Skill Refinement Skill
- Document patterns discovered during debugging
- Add anti-patterns to deprecated list

### → Error Triage Skill
- Pull Sentry context for investigation
- Correlate with deployment timeline

---

## Metrics for Success

1. **First-Fix Success Rate**
   - Target: 80% of bugs fixed on first attempt
   - Measure: Fixes that don't require follow-up commits

2. **Regression Introduction Rate**
   - Target: <5% of fixes introduce new bugs
   - Measure: Bugs reported within 1 week of fix deployment

3. **RCA Completion Rate**
   - Target: 100% of fixes have documented root cause
   - Measure: Bug resolution summaries created

4. **Time to Resolution**
   - Target: Complex bugs <2 hours average
   - Measure: Time from bug report to merged fix

---

## Quick Reference Card

```
┌─────────────────────────────────────────────────────────────┐
│                  REGRESSION PREVENTION                       │
├─────────────────────────────────────────────────────────────┤
│  1. OBSERVE: What's actually broken? (symptoms)              │
│  2. INVESTIGATE: Sentry → Vercel → Git history              │
│  3. HYPOTHESIZE: At least 3 possible causes                 │
│  4. VERIFY: Evidence for/against each hypothesis            │
│  5. IDENTIFY: Root cause (not symptom)                      │
│  6. MAP: Impact analysis (dependency graph)                 │
│  7. TEST FIRST: Write failing test                          │
│  8. FIX: Smallest change that addresses root cause          │
│  9. VERIFY: Test passes + no regressions                    │
│  10. DOCUMENT: Resolution summary + pattern updates          │
├─────────────────────────────────────────────────────────────┤
│  🚫 STOP PHRASES: "quick fix", "try this", "should work"    │
│  ✅ GOOD PHRASES: "root cause is", "evidence shows"         │
└─────────────────────────────────────────────────────────────┘
```

---

## Open Questions

1. How to handle time-sensitive production bugs that need quick fixes?
2. Should RCA be blocking for all bugs or just recurring ones?
3. Integration with GitHub Issues for bug tracking?
4. Automated test generation from bug reproduction steps?

---

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| v1 | 2024-12-01 | Initial foundation with RCA protocol |
