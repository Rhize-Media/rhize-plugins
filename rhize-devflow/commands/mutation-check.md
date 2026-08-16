---
description: Read-only data-mutation consistency check — scoped file(s), whole codebase, or a proposed fix plan — never edits source or adds TODOs
---
<!-- canonical: rhize-devflow:mutation-check -->

# Mutation Check

Detect missing error handling, cache revalidation, type safety, optimistic-UI, and hook
coverage in Supabase, React Query, and Payload CMS mutations. Replaces the former
`mutation-analyze` / `mutation-check` / `mutation-fix` split with one command and three
modes.

## Core Contract

- **Read-only.** This command never edits source files and never adds TODO comments to
  them. `--fix-plan` emits a proposed-changes report to `.claude/analysis/` — it does not
  touch the files it analyzes.
- **Fails closed.** A file that cannot be read, a malformed `.claude/mutation-patterns.yaml`,
  or a file set larger than the configured limit stops the run with a non-zero exit and an
  explicit error — never a partial score presented as a complete one.
- **Installed-root-safe.** Every invocation resolves scripts through
  `${CLAUDE_PLUGIN_ROOT}/skills/data-mutation-consistency/scripts/`, which works identically
  from a source checkout and an installed plugin cache. No command below contains a
  placeholder path.

## Modes

### `PATH...` — scoped check (one or more files)

```
/rhize-devflow:mutation-check app/actions/players.ts
/rhize-devflow:mutation-check app/actions/players.ts hooks/useUpdatePlayer.ts
```

```bash
python3 "$CLAUDE_PLUGIN_ROOT/skills/data-mutation-consistency/scripts/check_single_file.py" \
    --file "$TARGET_FILE"
```

Run once per path. Immediate inline result, no file output.

### `--all` — whole-codebase analysis

```
/rhize-devflow:mutation-check --all
/rhize-devflow:mutation-check --all --focus players
```

```bash
python3 "$CLAUDE_PLUGIN_ROOT/skills/data-mutation-consistency/scripts/analyze_mutations.py" \
    --root "$PROJECT_ROOT" \
    --dashboard
```

Writes a full report to `.claude/analysis/mutation-report-{date}.md` and returns a summary
to chat. Also validates cache-tag/query-key alignment across layers.

### `--fix-plan` — proposed changes only

```
/rhize-devflow:mutation-check --fix-plan
/rhize-devflow:mutation-check --fix-plan --priority P1
/rhize-devflow:mutation-check --fix-plan --file app/actions/players.ts
```

```bash
python3 "$CLAUDE_PLUGIN_ROOT/skills/data-mutation-consistency/scripts/generate_fixes.py" \
    --root "$PROJECT_ROOT" \
    --priority P1
```

Writes a fix plan to `.claude/analysis/fix-plan-{timestamp}.md` describing what to change
and why. **`--add-todos` and `--apply` do not exist** — both wrote to source files, which
was out of contract for this command, so they were removed from `generate_fixes.py`
outright rather than merely discouraged. Applying a proposed fix is a separate, explicit
edit the user or Claude performs after reviewing the plan.

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All checked mutations pass (≥ 9.0) |
| 1 | Warnings present (7.0–8.9) |
| 2 | Critical issues (< 7.0) |
| 3 | Failed closed — unreadable file(s), malformed config, or file set exceeded the limit |

Exit 3 is never downgraded to a passing or partial summary. Report it as a blocked
analysis, not as a score.

## Expected Output

### Scoped check
```
**useUpdatePlayer.ts** - Score: 10.0/10 ✅

  Line 12: players (update) - 10.0/10
    ✅ error_handling, cache_revalidation, type_safety, optimistic_ui, rollback_logic
```

### Whole-codebase
```
## Mutation Analysis Complete

**Overall Score:** 8.2/10 ⚠️

**Sub-Skills Loaded:**
  - react-query-mutations: 7.8/10
  - payload-cms-hooks: 8.5/10

**Stats:** 12 passing, 5 warnings, 1 critical
```

### Fix plan
```
# Mutation Fix Plan

Priority: P1
Issues Found: 8
Files Affected: 4

## updatePlayer.ts
### Fix 1: cache_revalidation (Line 45)
**Solution:** Add revalidateTag('players') after mutation
```

## Related Workflows

- `/rhize-devflow:check` — repository-wide test/lint/typecheck gate; run after applying any
  fix from a `--fix-plan` report.
- `/rhize-devflow:review` — production merge/release gate.
