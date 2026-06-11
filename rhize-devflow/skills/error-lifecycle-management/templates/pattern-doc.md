# Pattern Documentation Template

Use this template when extracting error patterns from resolved Sentry issues.

---

## Pattern: [RULE_NAME]

**Sentry Issue**: `[ISSUE-ID]`
**Date Learned**: [YYYY-MM-DD]
**Severity**: [critical | high | medium | low]
**Type**: [type-safety | async | payment | api | hooks | react-query | server-actions | general]

### Description

[One paragraph describing what this error is and when it occurs]

### Root Cause

[Explanation of WHY this error happens - the underlying cause]

### Affected Code Locations

- `[file-path:line]` - [brief description]
- `[file-path:line]` - [brief description]

### Detection Pattern

```regex
[Regex pattern that can detect this anti-pattern in code]
```

### Anti-Pattern (Don't Do This)

```typescript
// BAD: [explanation]
[code example showing the problematic pattern]
```

### Correct Pattern (Do This Instead)

```typescript
// GOOD: [explanation]
[code example showing the correct implementation]
```

### Prevention

- [ ] Added to validation rules
- [ ] Updated error-patterns.md
- [ ] Created Serena memory
- [ ] Tested detection with `yarn validate`

### Related

- Similar patterns: [list related rule names]
- Documentation: [link to relevant docs]
- Sentry Query: `[query to find similar issues]`

---

## Usage

1. Copy this template
2. Fill in all sections
3. Save to `reference/error-patterns.md` under "Learned Patterns"
4. Run `python extract_pattern.py` for automated extraction
