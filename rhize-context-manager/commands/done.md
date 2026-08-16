---
description: Session bookend — post-implementation validation, verifier pass, and STATE.md update before commit
---

# Post-Implementation Validation

Complete validation after finishing a feature or bug fix.

## Triggers
**Keywords:** done, finished, complete, ready to commit, ship it, wrap up

## What This Does

1. **Full Impact Analysis** - All files changed this session
2. **Verify Related Files** - Ensure no incomplete changes
3. **Build Validation** - Full type check and build
4. **Generate Commit Message** - Based on changes
5. **Delegate Code Review** - `/rhize-devflow:review` when available, disclosed fallback otherwise
6. **Update Context** - Mark progress in sprint file + STATE.md

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

### Step 4: Generate Commit Message
Based on changes, suggest commit message:
```
type(scope): description

- Detail 1
- Detail 2
```

Types: feat, fix, refactor, docs, style, test, chore

### Step 5: Delegate Code-Change Review (Dev Flow when available)
The maker never grades its own work. This plugin does not bundle its own verifier — the
independent verifier subagent lives only at `rhize-devflow/agents/verifier.md`.

- If this session changed code **and** the `rhize-devflow` plugin is installed with its
  `/review` command available: delegate to the fully qualified `/rhize-devflow:review`
  command — Dev Flow's production merge/release gate, which routes to that verifier for
  non-trivial changes.
  ```
  Run /rhize-devflow:review to independently verify this session's changes: diff,
  tests/build, and STATE.md updates.
  ```
  - Verdicts: `PASS` / `FAIL_WITH_FIXABLE_GAPS` / `FAIL_REQUIRES_HUMAN`
  - `FAIL_WITH_FIXABLE_GAPS` → fix the listed gaps, re-verify
  - `FAIL_REQUIRES_HUMAN` → stop and escalate; do NOT commit
- Otherwise — no code changed this session, or Dev Flow/`/review` is unavailable — run the
  minimal fallback self-review checklist below yourself and **disclose** that the fallback
  ran instead of an independent review. Never block session closure on Dev Flow's absence.

**Minimal fallback self-review checklist** (used only when Dev Flow is unavailable or no
code changed):
- [ ] Diff matches the stated task; no unrelated files touched
- [ ] Tests/build were run and their result reported (or explicitly "no code change to test")
- [ ] STATE.md (if the project has one) was updated

### Step 6: Update Context File + STATE.md (compounding contract)
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
- [ ] `/rhize-devflow:review` returned PASS, or the disclosed local fallback checklist ran
- [ ] Context file + STATE.md updated (something persisted for the next run)
- [ ] Commit message accurate

## Related Commands
- `/start` - Begin new session
- `/context-hygiene` - If session was long
