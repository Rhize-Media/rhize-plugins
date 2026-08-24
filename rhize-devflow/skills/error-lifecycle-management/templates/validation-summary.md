# Validation Summary Template

Use this template to document validation runs for STATE.md persistence via
`/rhize-context-manager`.

---

## Validation Run: [DATE]

**Mode**: [warning | strict]
**Validators Run**: [list or "all"]

### Results Overview

| Validator | Files | Errors | Warnings | Status |
|-----------|-------|--------|----------|--------|
| api-patterns | [n] | [n] | [n] | [pass/fail] |
| error-coverage | [n] | [n] | [n] | [pass/fail] |
| type-safety | [n] | [n] | [n] | [pass/fail] |
| performance | [n] | [n] | [n] | [pass/fail] |
| payload-hooks | [n] | [n] | [n] | [pass/fail] |
| react-query | [n] | [n] | [n] | [pass/fail] |
| server-actions | [n] | [n] | [n] | [pass/fail] |
| payments | [n] | [n] | [n] | [pass/fail] |
| **TOTAL** | **[n]** | **[n]** | **[n]** | **[status]** |

### Critical Findings (Must Fix)

1. **[rule-name]** in `[file:line]`
   - Issue: [description]
   - Impact: [why this matters]
   - Fix: [recommended action]

### High Priority Findings (Should Fix)

1. **[rule-name]** in `[file:line]`
   - Issue: [description]
   - Fix: [recommended action]

### Sentry Correlations

| Validation Finding | Sentry Query | Matches Found |
|--------------------|--------------|---------------|
| [rule] | [query] | [count or "pending"] |

### Actions Taken

- [ ] [Fix applied for critical finding 1]
- [ ] [Fix applied for critical finding 2]
- [ ] [Created Sentry query for correlation]

### Comparison to Previous Run

| Metric | Previous | Current | Change |
|--------|----------|---------|--------|
| Total Errors | [n] | [n] | [+/-n] |
| Total Warnings | [n] | [n] | [+/-n] |
| Coverage % | [n]% | [n]% | [+/-n]% |

### Recommendations

1. [Process improvement]
2. [New validation rule to add]
3. [Code pattern to enforce]

---

## STATE.md Persistence

Save this summary via `/rhize-context-manager:done`, under an entry named
`validation-[YYYY-MM-DD]` in STATE.md's Verified facts or Open failures section, as
appropriate.

## Quick Reference

Run validation:
```bash
yarn validate           # All validators (warning mode)
yarn validate:strict    # All validators (CI mode)
yarn correlate          # Generate Sentry correlations
```
