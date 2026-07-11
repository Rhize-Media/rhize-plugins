---
name: pr-review-on-create
enabled: true
event: bash
pattern: gh\s+pr\s+create
action: warn
---

🔍 **PR creation detected — kick off review flow**

A PR is being opened. After `gh pr create` returns the PR URL, **immediately** run the standard Rhize PR-review pipeline against it.

**Required next steps (in order):**

1. Capture the PR number/URL returned by `gh pr create`.
2. If the PR base is `main`, this is a release-candidate review — be strict.
3. Invoke the review skill on the new PR:
   - Primary: `/rhize-review` (prod merge-gate orchestrator — routes the diff to ecc specialist + security reviewers, returns one merge verdict)
   - Fallback (if `/rhize-review` is unavailable): `/pr-review-toolkit:review-pr`, `/code-review:code-review`, or `/review`
4. Cover at minimum:
   - Spec compliance vs. the PRD / linked plan
   - Type safety, lint, and build status (`pnpm typecheck && pnpm lint && pnpm build`)
   - Security: no leaked secrets, no `NEXT_PUBLIC_*` exposing server-only keys, no Supabase service-role usage in client code
   - Sanity schema changes have matching migration / type-gen
   - Tests: new logic has coverage, snapshots updated
5. Post review findings as a PR comment (`gh pr review --comment`).

**Do not skip this** — it's the gate between `dev` and `main`. If review surfaces blockers, switch the PR to draft (`gh pr ready --undo`) before merging.
