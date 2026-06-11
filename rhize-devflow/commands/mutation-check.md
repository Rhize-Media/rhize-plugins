# /rhize-devflow:mutation-check

Quick pattern check for a single file.

## Aliases
- `@check-mutation [file]`
- `/rhize-devflow:mutation-check [file]`

## Usage
```
/rhize-devflow:mutation-check app/actions/players.ts
/rhize-devflow:mutation-check hooks/useUpdatePlayer.ts
/rhize-devflow:mutation-check app/payload/collections/Players.ts
```

## What This Command Does

1. **Read Target File**
   - Parse TypeScript/TSX content
   - Detect mutation type (Supabase, React Query, Payload)

2. **Pattern Detection**
   - Find all mutations in the file
   - Check each for required elements
   - Apply category-specific checks

3. **Immediate Feedback**
   - Return inline result (no file output)
   - Show present/missing elements
   - Provide fix suggestions

## Execution

```bash
# Claude should run:
python3 /path/to/skill/scripts/check_single_file.py \
    --file "$TARGET_FILE"
```

## Expected Output

### Passing File
```
**useUpdatePlayer.ts** - Score: 10.0/10 ✅

  Line 12: players (update) - 10.0/10
    ✅ error_handling, cache_revalidation, type_safety, optimistic_ui, rollback_logic
```

### File with Issues
```
**updatePlayer.ts** - Score: 7.5/10 ⚠️

  Line 15: players (update) - 7.5/10
    ✅ error_handling, type_safety
    ❌ cache_revalidation, input_validation

**Fixes needed:**
  🔴 Add revalidateTag('players') after mutation
  🟡 Add zod schema validation before mutation
```

### Payload Collection
```
**Teams.ts** - Score: 6.0/10 ❌

  Line 1: teams (payload_collection) - 6.0/10
    ✅ after_change_hook
    ❌ after_delete_hook, after_delete_cache, before_change_validation

**Fixes needed:**
  🔴 Add afterDelete hook with cache invalidation
  🟡 Add beforeChange validation hook
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All mutations pass (≥ 9.0) |
| 1 | Warnings present (7.0-8.9) |
| 2 | Critical issues (< 7.0) |

## Use Cases

1. **Before Committing**
   ```
   @check-mutation app/actions/players.ts
   ```

2. **After Editing Mutation**
   ```
   @check-mutation hooks/useCreateGame.ts
   ```

3. **Debugging Stale Data**
   ```
   @check-mutation app/payload/collections/Games.ts
   ```

## Related Commands

- `/rhize-devflow:mutation-analyze` - Full codebase analysis
- `/rhize-devflow:mutation-fix` - Generate fixes for this file
