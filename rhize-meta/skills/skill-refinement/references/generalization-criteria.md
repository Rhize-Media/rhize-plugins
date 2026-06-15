# Generalization Criteria Reference

Guidelines for when and how to generalize project-specific refinements to user-scope skills.

---

## Overview

Generalization is the process of promoting a project-specific refinement to become a default behavior in user-scope skills. This ensures useful patterns are available across all projects.

---

## Automatic Generalization Triggers

The system automatically flags patterns for generalization when:

### Count Threshold (≥2)
```
Pattern seen in 2+ different projects
→ Added to generalization queue
→ Status: "ready-for-generalization"
```

### Consistency Check
Pattern must be consistent across occurrences:
- Same target section/file
- Similar patch content (>70% similarity)
- Same override type

---

## Generalization Potential Ratings

### High Potential

**Indicators:**
- Applies to common development patterns
- Addresses universal tooling issues
- Improves safety/validation without project-specific logic
- No project-specific paths or configurations

**Examples:**
- Test directory exclusions (`__tests__`, `fixtures`, `__mocks__`)
- Common file pattern exclusions (`.spec.`, `.test.`)
- Standard error message improvements
- Universal hook enhancements

**Recommendation:** Generalize after 2 occurrences

---

### Medium Potential

**Indicators:**
- Applies to common frameworks but not universal
- May need configuration options
- Useful for specific tech stacks

**Examples:**
- React-specific patterns
- Next.js API route handling
- Specific CMS integrations
- Framework-specific error patterns

**Recommendation:** Generalize after 3 occurrences, with configuration options

---

### Low Potential

**Indicators:**
- Project-specific business logic
- Custom naming conventions
- Organization-specific patterns
- One-off fixes

**Examples:**
- Company-specific file paths
- Custom API endpoint patterns
- Project-specific validation rules
- Temporary workarounds

**Recommendation:** Keep as project override, do not generalize

---

## Decision Matrix

| Factor | Generalize | Keep Project-Specific |
|--------|------------|----------------------|
| Occurrences | ≥2 projects | 1 project |
| Scope | Universal pattern | Project-specific logic |
| Configuration | None or simple | Complex/project-specific |
| Breaking risk | None/low | High |
| Maintenance | Low | High |

---

## Pre-Generalization Checklist

Before applying a generalization, verify:

### 1. Pattern Consistency
- [ ] Same issue addressed in all occurrences
- [ ] Similar solution applied each time
- [ ] No conflicting implementations

### 2. Breaking Change Assessment
- [ ] Existing projects won't break
- [ ] New behavior is backwards compatible
- [ ] Opt-out mechanism available if needed

### 3. Configuration Needs
- [ ] Determine if configuration options are needed
- [ ] Define sensible defaults
- [ ] Document configuration options

### 4. Testing Coverage
- [ ] Pattern tested in multiple contexts
- [ ] Edge cases considered
- [ ] Rollback procedure documented

### 5. Documentation
- [ ] Clear description of what changed
- [ ] Reason for generalization documented
- [ ] Usage examples provided

---

## Generalization Process

### Step 1: Review Pattern

```
/review-patterns PATTERN-001
```

Examine:
- All refinements that contributed to this pattern
- Differences between implementations
- Projects that will be affected

### Step 2: Verify Readiness

Check the generalization queue entry:
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔍 Pattern Detail: PATTERN-001
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Readiness Assessment:
  ✓ Count threshold met (3 occurrences)
  ✓ Consistent implementation
  ✓ No breaking changes
  ✓ Configuration defined
  ⚠️ Documentation needs update

Proceed with generalization? [yes/no/defer]
```

### Step 3: Apply Generalization

```
/apply-generalization PATTERN-001
```

This will:
1. Create backups of affected files
2. Apply changes to user-scope skills
3. Update pattern status to "generalized"
4. Archive related refinements

### Step 4: Verify and Clean Up

After generalization:
1. Test the updated skills in a new project
2. Remove project-specific overrides if no longer needed
3. Document the generalization in skill changelog

---

## When NOT to Generalize

### Project-Specific Logic
```
❌ Pattern: Custom API endpoint validation for /api/v2/lms/*
Reason: Path is specific to one project's API structure
Action: Keep as project override
```

### Conflicting Implementations
```
❌ Pattern: Error message formatting
Reason: Different projects use different formats
Action: Make configurable or keep separate
```

### Temporary Workarounds
```
❌ Pattern: Skip validation for legacy module
Reason: Workaround for specific legacy code
Action: Keep as project override until legacy is removed
```

### High-Risk Changes
```
❌ Pattern: Modified exit codes for hooks
Reason: May break CI/CD pipelines in other projects
Action: Needs extensive testing before generalizing
```

---

## Manual Promotion

For patterns with count = 1 that should still be generalized:

```
/review-patterns PATTERN-002 --promote
```

Reasons to manually promote:
- Known to be universally useful
- Requested by multiple team members
- Addresses common pain point
- Security or performance improvement

---

## Manual Dismissal

For patterns that should never be generalized:

```
/review-patterns PATTERN-003 --dismiss "Project-specific API structure"
```

Dismissed patterns:
- Move to "dismissed" status
- No longer trigger generalization alerts
- Can be undone if needed later

---

## Configuration Strategies

### Environment Variables
For values that vary by environment:
```bash
EXCLUDE_PATTERNS="${EXCLUDE_PATTERNS:-__tests__|fixtures}"
```

### JSON Configuration
For complex configuration:
```json
{
  "skill": "error-lifecycle-management",
  "config": {
    "exclude_patterns": ["__tests__", "fixtures"],
    "error_threshold": 10
  }
}
```

### Defaults with Override
For optional customization:
```python
DEFAULT_PATTERNS = ["__tests__", "fixtures"]

def get_patterns():
    return os.environ.get("PATTERNS", DEFAULT_PATTERNS)
```

---

## Rollback Procedure

If a generalization causes issues:

### Immediate Rollback
```
/apply-generalization --rollback PATTERN-001
```

### Manual Rollback
1. Navigate to `~/claude-skills/.backups/[date]/`
2. Restore affected files
3. Update pattern status to "tracking"

### Partial Rollback
Keep some changes, revert others:
1. Edit the generalized files manually
2. Document which parts were kept/reverted
3. Create new refinement for the reverted parts

---

## Metrics and Monitoring

Track generalization effectiveness:

| Metric | Target | Measurement |
|--------|--------|-------------|
| Successful generalizations | >90% | No rollbacks needed |
| Pattern detection accuracy | >80% | Correctly identified patterns |
| Time to generalization | <2 weeks | From first occurrence to generalized |
| Projects benefiting | >80% | Use generalized pattern without override |

---

## Best Practices

1. **Wait for natural consensus** - Let patterns emerge from real usage
2. **Prefer configuration** - Make patterns configurable rather than hard-coded
3. **Document extensively** - Future you will thank present you
4. **Test in isolation** - Verify pattern works standalone before generalizing
5. **Communicate changes** - Notify team of generalized patterns
6. **Monitor after generalization** - Watch for issues in first week
7. **Keep history** - Don't delete refinement records after generalization
