---
name: block-direct-push-to-main
enabled: true
event: bash
action: block
conditions:
  - field: command
    operator: regex_match
    pattern: git\s+(-C\s+\S+\s+)?push\b.*\b(main|master)\b
  - field: command
    operator: not_contains
    pattern: --dry-run
---

🚨 **Direct push to `main`/`master` blocked**

Rhize workflow requires all changes flow through a PR from `dev` → `main` with a review pass.

**What to do instead:**

1. Make sure you're on a feature/`dev` branch: `git branch --show-current`
2. Push to that branch: `git push -u origin <branch-name>`
3. Open a PR with `gh pr create --base main --head <branch-name>` (or `--base dev` for feature work)
4. The `pr-review-on-create` rule will then trigger the review flow.

If you truly need to push to `main` (e.g., a hotfix the user explicitly authorized), pass `--dry-run` first to confirm intent, then ask the user for explicit confirmation before retrying — never bypass silently.
