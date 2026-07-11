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

### Step 6: Independent Verification (verifier subagent)
The maker never grades its own work. Delegate to the `verifier` subagent (global
`~/.claude/agents/verifier.md`, or the copy bundled in this plugin's `agents/`):
```
Use the verifier subagent to check this session's changes: it must inspect the diff,
run the relevant tests/build, and confirm STATE.md was updated.
```
- Verdicts: PASS / FAIL_WITH_FIXABLE_GAPS / FAIL_REQUIRES_HUMAN
- FAIL_WITH_FIXABLE_GAPS → fix the listed gaps, re-verify
- FAIL_REQUIRES_HUMAN → stop and escalate; do NOT commit
- If no verifier subagent is available, perform the same checks explicitly and say so

### Step 7: Update Context File + STATE.md (compounding contract)
- Mark completed items; update "Completed This Session" section; clear done pending items
- If the project has a `STATE.md` (Verified facts · General rules · Open failures ·
  Lessons learned · Last session): record at least one verified fact, open failure
  with repro, or lesson learned. **No run is complete until the next run is better
  prepared.** If a multi-session project lacks STATE.md, offer to create it.

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
- [ ] Verifier subagent returned PASS
- [ ] Context file + STATE.md updated (something persisted for the next run)
- [ ] Commit message accurate

## Related Commands
- `/start` - Begin new session
- `/context-hygiene` - If session was long
