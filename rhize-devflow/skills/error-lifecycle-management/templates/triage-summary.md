# Triage Summary Template

Use this template to document error triage sessions for STATE.md persistence via
`/rhize-context-manager`.

---

## Triage Session: [DATE]

**Duration**: [time spent]
**Issues Triaged**: [count]

### Issues Resolved

#### 1. [ISSUE-ID]: [Title]

**Status**: Resolved / In Progress / Blocked
**Severity**: [critical | high | medium | low]
**Affected Users**: [count]
**Frequency**: [events/day or week]

**Root Cause**:
> [Brief explanation of why this happened]

**Fix Applied**:
> [What code changes were made]

**Files Modified**:
- `[file-path]` - [change description]

**Pattern Extracted**: [yes/no]
- Rule Name: `[rule-name]`
- Added to: `error-patterns.md`

**Verification**:
- [ ] Fix deployed to staging
- [ ] Error rate decreased
- [ ] Issue marked resolved in Sentry

---

### Patterns Learned

| Rule Name | Issue ID | Type | Severity |
|-----------|----------|------|----------|
| [name] | [ID] | [type] | [sev] |

### Correlations Found

| Validation Rule | Sentry Issue | Action Taken |
|-----------------|--------------|--------------|
| [rule] | [issue-id] | [action] |

### Recommendations

1. [Recommendation for preventing similar issues]
2. [Process improvement suggestion]
3. [Validation rule to add]

### Follow-up Actions

- [ ] [Action item 1]
- [ ] [Action item 2]

---

## STATE.md Persistence

Save this summary via `/rhize-context-manager:done`, under an entry named
`triage-[YYYY-MM-DD]` in the appropriate STATE.md section (Open failures for
in-progress/blocked issues, Lessons learned for resolved ones with an extracted pattern).
