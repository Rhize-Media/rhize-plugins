# /review-patterns Command

> Review tracked refinement patterns and generalization queue

---

## Usage

```
/review-patterns
/review-patterns --status [tracking|ready|generalized]
/review-patterns --skill [skill-name]
/review-patterns [PATTERN-ID]
```

---

## Description

Displays tracked refinement patterns across all projects, showing:
- Patterns being tracked (count = 1)
- Patterns ready for generalization (count ≥ 2)
- Previously generalized patterns (archived)

---

## Default Output

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 Refinement Patterns Overview
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Ready for Generalization (2)
────────────────────────────

🟡 PATTERN-001: Test Directory Exclusion
   Count: 3 | Skills: context-engineering, error-lifecycle
   Projects: example-web-app, frontend-repo, client-project
   → Run: /apply-generalization PATTERN-001

🟡 PATTERN-003: API Timeout Configuration
   Count: 2 | Skills: error-lifecycle-management
   Projects: example-web-app, analytics-dashboard
   → Run: /apply-generalization PATTERN-003

Currently Tracking (3)
──────────────────────

⚪ PATTERN-002: CMS-Specific Validators
   Count: 1 | Skills: error-lifecycle-management
   First seen: example-web-app (Payload CMS)
   Note: Will auto-generalize at 2 occurrences

⚪ PATTERN-004: Custom Hook Timeout
   Count: 1 | Skills: context-engineering
   First seen: frontend-repo

⚪ PATTERN-005: Sentry Environment Tags
   Count: 1 | Skills: error-lifecycle-management
   First seen: client-project

Recently Generalized (1)
────────────────────────

✅ PATTERN-000: API Pattern Configuration
   Generalized: 2024-11-28
   Applied to: error-lifecycle-management v2.0.0

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Pattern Detail View

```
/review-patterns PATTERN-001
```

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔍 Pattern Detail: PATTERN-001
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Name: Test Directory Exclusion
Status: 🟡 Ready for Generalization
Count: 3 occurrences

Description:
  Hooks and validators need standard exclusion patterns
  for test directories (__tests__, fixtures, __mocks__).

Affected Skills:
  • context-engineering
    - hooks/duplicate-check.sh
    - hooks/pre-commit-guard.sh
  • error-lifecycle-management
    - scripts/common/base_validator.py

Refinement History:
  ┌────────────┬─────────────────┬──────────────────────┐
  │ Date       │ Project         │ Refinement ID        │
  ├────────────┼─────────────────┼──────────────────────┤
  │ 2024-12-01 │ example-web-app     │ REF-2024-1201-003    │
  │ 2024-12-03 │ frontend-repo       │ REF-2024-1203-001    │
  │ 2024-12-04 │ client-project  │ REF-2024-1204-001    │
  └────────────┴─────────────────┴──────────────────────┘

Proposed Generalization:
  Add EXCLUDE_PATTERNS environment variable with defaults:
  __tests__|fixtures|__mocks__|\.test\.|\.spec\.

Actions:
  → /apply-generalization PATTERN-001
  → /review-patterns PATTERN-001 --refinements (view all refinements)
  → /review-patterns PATTERN-001 --diff (view proposed changes)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Filter Options

### By Status
```
/review-patterns --status tracking    # Count = 1
/review-patterns --status ready       # Count ≥ 2
/review-patterns --status generalized # Already applied
```

### By Skill
```
/review-patterns --skill context-engineering
```

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 Patterns for: context-engineering
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🟡 PATTERN-001: Test Directory Exclusion (3)
⚪ PATTERN-004: Custom Hook Timeout (1)
✅ PATTERN-000: API Pattern Configuration (generalized)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### By Project
```
/review-patterns --project example-web-app
```

---

## Statistics View

```
/review-patterns --stats
```

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📈 Refinement Statistics
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Total Refinements: 23
Total Patterns: 6

By Status:
  🟡 Ready: 2 patterns
  ⚪ Tracking: 3 patterns
  ✅ Generalized: 1 pattern

By Skill:
  context-engineering: 12 refinements
  error-lifecycle-management: 8 refinements
  dev-flow-foundations: 3 refinements

By Category:
  hook: 9 refinements
  trigger: 6 refinements
  pattern: 5 refinements
  config: 3 refinements

Top Projects:
  example-web-app: 10 refinements
  frontend-repo: 7 refinements
  client-project: 6 refinements

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Actions

### Manually Trigger Generalization
For patterns that shouldn't wait for threshold:
```
/review-patterns PATTERN-002 --promote
```

### Dismiss Pattern
For patterns that won't be generalized:
```
/review-patterns PATTERN-002 --dismiss "Project-specific, won't generalize"
```

### Merge Patterns
Combine similar patterns:
```
/review-patterns --merge PATTERN-002 PATTERN-004
```

---

## Related Commands

- `/refine-skills` - Capture new refinements
- `/apply-generalization` - Apply ready patterns
