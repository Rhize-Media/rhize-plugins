# /apply-generalization Command

> Apply queued generalizations to user-scope skills

---

## Usage

```
/apply-generalization [PATTERN-ID]
/apply-generalization --list
/apply-generalization --all
```

---

## Description

When a refinement pattern reaches the threshold (≥2 occurrences across projects), it becomes eligible for generalization. This command applies those patterns to user-scope skills so they become the new defaults.

---

## Workflow

### Step 1: List Eligible Patterns

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 Generalization Queue
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Ready for Generalization:

1. PATTERN-001: Test Directory Exclusion
   Count: 3 projects
   Skills: context-engineering, error-lifecycle-management
   Priority: High

2. PATTERN-003: API Timeout Configuration
   Count: 2 projects
   Skills: error-lifecycle-management
   Priority: Medium

Select pattern to apply: [1/2/all/cancel]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

### Step 2: Review Pattern Details

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔍 Pattern Details: PATTERN-001
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Name: Test Directory Exclusion
Description: Exclude test directories from validation hooks

Occurrences:
  • 2024-12-01: example-web-app (REF-2024-1201-003)
  • 2024-12-03: example-frontend (REF-2024-1203-001)
  • 2024-12-04: client-project (REF-2024-1204-001)

Files to Update:
  1. ~/claude-skills/context-engineering/hooks/duplicate-check.sh
  2. ~/claude-skills/context-engineering/hooks/pre-commit-guard.sh
  3. ~/claude-skills/error-lifecycle-management/scripts/common/base_validator.py

Proposed Changes:

┌─ hooks/duplicate-check.sh ──────────────────────────
│ + # Configurable exclusion patterns
│ + EXCLUDE_PATTERNS="${EXCLUDE_PATTERNS:-__tests__|fixtures|__mocks__|\.test\.|\.spec\.}"
│ +
│ + # Skip excluded paths
│ + if echo "$FILE_PATH" | grep -qE "($EXCLUDE_PATTERNS)"; then
│ +   exit 0
│ + fi
└─────────────────────────────────────────────────────

┌─ base_validator.py ─────────────────────────────────
│ + DEFAULT_EXCLUDE_PATTERNS = [
│ +     r'__tests__',
│ +     r'fixtures',
│ +     r'__mocks__',
│ +     r'\.test\.',
│ +     r'\.spec\.',
│ + ]
└─────────────────────────────────────────────────────

Breaking Changes: None (additive only)

Apply this generalization? [yes/no]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

### Step 3: Apply Changes

**Actions performed:**

1. **Backup existing files**
   - Create `.backup` copies before modification

2. **Apply changes to user-scope skills**
   - Update files in `~/claude-skills/[skill]/`

3. **Update tracking files**
   - Mark pattern as "generalized" in `aggregated-patterns.md`
   - Archive related refinements in history
   - Update `.zen-sync` timestamp

4. **Sync to Zen MCP** (if available)
   - Update pattern status
   - Store generalization record

---

### Step 4: Confirmation

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Generalization Applied: PATTERN-001
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Updated Files:
  ✓ ~/claude-skills/context-engineering/hooks/duplicate-check.sh
  ✓ ~/claude-skills/context-engineering/hooks/pre-commit-guard.sh
  ✓ ~/claude-skills/error-lifecycle-management/scripts/common/base_validator.py

Backups Created:
  ~/claude-skills/.backups/2024-12-04/

Pattern Status: Archived
Related Refinements: 3 archived

💡 Next Steps:
  1. Test the updated skills in a new project
  2. Existing project overrides will continue to work
  3. Remove project-specific patches if no longer needed

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Options

| Option | Description |
|--------|-------------|
| `--list` | List all patterns ready for generalization |
| `--all` | Apply all ready patterns (with confirmation) |
| `--dry-run` | Preview changes without applying |
| `--no-backup` | Skip backup creation |
| `--force` | Apply without confirmation prompts |

---

## Safety Features

### Backup System
- Creates timestamped backups before any modification
- Stored in `~/claude-skills/.backups/YYYY-MM-DD/`
- Retained for 30 days

### Rollback
```
/apply-generalization --rollback PATTERN-001
```
Restores files from backup if generalization causes issues.

### Dry Run
```
/apply-generalization PATTERN-001 --dry-run
```
Shows exactly what would change without modifying files.

---

## Related Commands

- `/refine-skills` - Capture new refinements
- `/review-patterns` - View all tracked patterns
