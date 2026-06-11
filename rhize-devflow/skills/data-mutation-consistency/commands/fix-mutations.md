# /rhize-devflow:mutation-fix

Generate fix plan for mutation issues.

## Aliases
- `@fix-mutations [priority]`
- `/rhize-devflow:mutation-fix [priority]`

## Usage
```
/rhize-devflow:mutation-fix P0         # Critical issues only
/rhize-devflow:mutation-fix P1         # Critical + warnings (default)
/rhize-devflow:mutation-fix P2         # All issues including info
/rhize-devflow:mutation-fix --file app/actions/players.ts  # Specific file
```

## Priority Levels

| Priority | Includes | Typical Count |
|----------|----------|---------------|
| P0 | Critical (score < 7.0) | Few, urgent |
| P1 | Critical + Warnings (< 9.0) | Most actionable |
| P2 | All issues | Comprehensive |

## What This Command Does

1. **Load Issues**
   - Read from `.claude/analysis/pending-fixes.md` if exists
   - Otherwise run fresh analysis

2. **Filter by Priority**
   - Apply priority filter
   - Optionally filter by specific file

3. **Generate Fix Plan**
   - Group issues by file
   - Generate code snippets for each fix
   - Write plan to `.claude/analysis/fix-plan-{timestamp}.md`

4. **Provide Summary**
   - Return overview to chat
   - Link to full fix plan

## Execution

```bash
# Claude should run:
python3 /path/to/skill/scripts/generate_fixes.py \
    --root "$PROJECT_ROOT" \
    --priority P1
```

## Expected Output

```
# Mutation Fix Plan

Generated: 2024-12-05 14:30:00
Priority: P1
Issues Found: 8
Files Affected: 4

---

## updatePlayer.ts

**Path:** `app/actions/updatePlayer.ts`

### Fix 1: cache_revalidation (Line 45)

**Issue:** No cache revalidation after mutation

**Solution:** Add revalidateTag() or revalidatePath() after mutation

**Code to add:**
```typescript
// After mutation, invalidate cache:
revalidateTag('players');
revalidatePath('/players');
```

---

...

Full plan: .claude/analysis/fix-plan-20241205-143000.md
```

## Options

### Add TODO Comments
Instead of generating a plan file, add TODO comments directly to source:

```
@fix-mutations --add-todos P1
```

This adds comments like:
```typescript
// TODO(mutation-consistency): Add revalidateTag('players') after mutation - cache_revalidation
export async function updatePlayer(id: string, data: PlayerUpdate) {
```

### Target Specific File
```
@fix-mutations --file app/actions/players.ts
```

## Workflow

1. **Run Analysis First**
   ```
   @analyze-mutations
   ```

2. **Review Issues**
   Check `.claude/analysis/mutation-report-{date}.md`

3. **Generate Fix Plan**
   ```
   @fix-mutations P1
   ```

4. **Apply Fixes**
   - Review fix plan
   - Apply changes manually or with Claude's help
   - Or use `@fix-mutations --add-todos` for incremental fixes

5. **Validate**
   ```
   @analyze-mutations
   ```
   Expected: Score should improve, issues should decrease

## Related Commands

- `/rhize-devflow:mutation-analyze` - Run analysis first
- `/rhize-devflow:mutation-check` - Check specific file after fixing
