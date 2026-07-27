# Post-Implementation Validation

Complete validation after finishing a feature or bug fix.

## Triggers
**Keywords:** done, finished, complete, ready to commit, ship it, wrap up

## What This Does

1. **Full Impact Analysis** - All files changed this session
2. **Verify Related Files** - Ensure no incomplete changes
3. **Build Validation** - Full type check and build
4. **Code Review** - Multi-perspective review via MCP
5. **Generate Commit Message** - Based on changes
6. **Update Context** - Mark progress in sprint file

## Automatic Actions

### Step 1: Gather All Changes
```bash
git status
git diff --name-only HEAD
```

### Step 2: Full Impact Analysis
For each changed file:
- List all files that import it
- Check if those files need updates
- Verify type files if schema changed

### Step 3: Build Validation
```bash
# Run appropriate build command for project
npm run build  # or yarn build, pnpm build
npm run typecheck  # if separate
```

### Step 4: Code Review (if Zen MCP available)
```
Use zen precommit to validate changes:
- Focus: quality, correctness
- Files: [list of changed files]
```

### Step 5: Generate Commit Message
Based on changes, suggest commit message:
```
type(scope): description

- Detail 1
- Detail 2
```

Types: feat, fix, refactor, docs, style, test, chore

### Step 6: Update Context File
- Mark completed items
- Update "Completed This Session" section
- Clear pending items that are done

## Output Format

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Post-Implementation Validation
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📁 Files Changed: [count]
  [file list]

🔨 Build Status: ✅/❌

🔍 Code Review:
  [summary of findings]

📝 Suggested Commit:
━━━━━━━━━━━━━━━━━
[commit message]
━━━━━━━━━━━━━━━━━

🚀 Ready to Commit: [Yes/No - with reasons]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

## Checklist Before Commit

- [ ] All related files updated
- [ ] No type errors
- [ ] Build passes
- [ ] Code reviewed
- [ ] Context file updated
- [ ] Commit message accurate

## Related Commands
- `/start` - Begin new session
- `/context-hygiene` - If session was long
