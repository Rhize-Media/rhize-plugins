# /rhize-devflow:mutation-analyze

Full codebase mutation pattern analysis.

## Aliases
- `@analyze-mutations`
- `/rhize-devflow:mutation-analyze`

## Usage
```
/rhize-devflow:mutation-analyze
/rhize-devflow:mutation-analyze --focus [table|entity]
```

## What This Command Does

1. **Discovery Phase**
   - Detect sub-skills from package.json (React Query, Payload CMS)
   - Scan for mutation patterns in TypeScript files
   - Identify server actions, API routes, client mutations

2. **Analysis Phase**
   - Extract mutations from code
   - Check for required elements (error handling, cache revalidation, types)
   - Apply sub-skill specific checks

3. **Scoring Phase**
   - Calculate weighted scores for each mutation
   - Aggregate overall project score
   - Identify critical and warning-level issues

4. **Cross-Layer Validation**
   - Verify backend cache tags align with frontend query keys
   - Flag misalignments that could cause stale data

5. **Output**
   - Write detailed report to `.claude/analysis/mutation-report-{date}.md`
   - Write pending fixes to `.claude/analysis/pending-fixes.md`
   - Return summary to chat (minimal context usage)

## Execution

```bash
# Claude should run:
python3 /path/to/skill/scripts/analyze_mutations.py \
    --root "$PROJECT_ROOT" \
    --dashboard
```

## Expected Output

```
## Mutation Analysis Complete

**Overall Score:** 8.2/10 ⚠️

**Sub-Skills Loaded:**
  - react-query-mutations: 7.8/10
  - payload-cms-hooks: 8.5/10

**Stats:** 12 passing, 5 warnings, 1 critical

**Top Issues:**
1. 🔴 Missing cache revalidation (updatePlayer.ts)
2. 🟡 No onSettled handler (useCreateGame.ts)
3. 🟡 afterDelete hook missing cache invalidation (Teams.ts)

📄 Full report: `.claude/analysis/mutation-report-20241205.md`
```

## Follow-up Actions

After analysis, user can:
- `@check-mutation [file]` - Deep dive into specific file
- `@fix-mutations P1` - Generate fix plan for warnings
- Review full report for detailed findings

## Scoring Thresholds

| Score | Status | Meaning |
|-------|--------|---------|
| ≥ 9.0 | ✅ Passing | Mutation follows all patterns |
| 7.0-8.9 | ⚠️ Warning | Missing recommended elements |
| < 7.0 | ❌ Critical | Missing required elements |
