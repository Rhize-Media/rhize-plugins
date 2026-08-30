---
name: completed-branch-promotion
consumes:
  - superpowers:finishing-a-development-branch
provenance: completed-branch-promotion
description: >-
  Promote a completed feature or task branch through Rhize's repository-governed protected-branch
  workflow. Use when implementation is complete and the user says "push to main" or "push to dev
  and main", or otherwise explicitly asks to ship or promote the completed branch. Treat those
  phrases as authorization for the appropriate PR-based promotion sequence, not a raw push to a
  protected branch; preserve narrower user overrides and repository-specific release policy.
metadata:
  rhize:
    tier: custom
    domain: dev-flow
    maturity: stable
    version: 1.0.0
    topics: [workflow-patterns]
    stacks: [testing, vercel]
    extends: [dev-flow-foundations]
---

# Completed Branch Promotion

Promote the exact completed task tree through the repository's real integration branches and
deployment gates. This skill owns Rhize's release choreography; it does not replace the read-only
`/rhize-devflow:review` verdict or grant authority beyond the user's request and repository policy.

Invoke `superpowers:finishing-a-development-branch` for its environment detection,
detached-worktree handling, rejected-push safeguards, and cleanup rules. This is a maintained
runtime dependency: if it is unavailable, stop before mutation and report the missing dependency
instead of copying or improvising its mechanics. The user has already chosen the integration
outcome when they say **"push to main"** or **"push to dev and main"**, so do not present its
integration-options menu again. Execute the applicable flow below.

## Authority and precedence

Apply these sources in order:

1. The user's explicit sequence or limitation for this run.
2. Repository-local `AGENTS.md`, `CLAUDE.md`, `STATE.md`, README/release docs, and protected-branch
   configuration.
3. Standing per-repository manual-push/auto-push policy.
4. This default flow.

The two trigger phrases authorize the ordinary Git/forge/deployment verification steps needed to
complete the named promotion. In a manual-push repository, that explicit phrase is the required
push/merge authorization. It does not independently authorize a production data migration,
credential change, billing action, force-push, branch-protection bypass, or any other materially
different external mutation when repository policy requires separate approval.

An explicit narrower instruction wins. For example, "push to main, but skip dev for this hotfix"
uses a PR to `main` if repository policy permits that route; "push the feature branch only" stops
after publishing that branch and does not open or merge promotion PRs. Never reinterpret a
restriction as permission to finish the default sequence.

## 1. Resolve exact release state

Before any commit, push, PR, merge, migration, or deployment action:

1. Read every applicable instruction and state file. Identify manual/auto-push classification,
   protected branches, required merge method, branch order, migration order, deployment provider,
   required checks, smoke tests, and commit-author constraints.
2. Fetch/prune the authoritative remote, then record the remote URL, current worktree path, detached
   or named-branch state, local `HEAD`, upstream, `origin/main`, `origin/dev` when present, merge
   bases, ahead/behind counts, and complete porcelain status including untracked files.
3. Prove the task boundary from the user request, plan, commits, and diff. Do not infer a completed
   feature solely from a branch name or clean working tree.
4. Determine whether the repository **uses** `dev` from its documented flow and remote evidence.
   The mere existence of an old `dev` ref is not sufficient. If the repository has no `dev` flow,
   the default is task branch -> PR -> `main`.
5. Resolve the exact source branch. In a detached managed worktree, choose a scoped task-branch name
   and publish `HEAD` to it; do not commit or push directly to a protected ref.

Stop and report the exact evidence when the target, remote, release policy, task boundary, or user
authority is genuinely ambiguous. Do not manufacture a default from Git's configured default branch.

### Dirty and diverged state

- Commit only files belonging to the completed task.
- Preserve unrelated staged, unstaged, and untracked work. If task and unrelated changes cannot be separated with confidence, use a clean
  isolated worktree/branch or stop; never stash, discard, overwrite, or sweep them into the release.
- If the task branch or an integration branch is non-fast-forward, diverged, or moved after the
  snapshot, stop the mutation sequence, fetch again, and reconcile through a normal merge/rebase or
  replacement PR consistent with repository policy. Never force-push unless the user explicitly
  requests that exact action and policy permits it.
- Re-check remote refs immediately before every PR merge. Evidence from the beginning of the run is
  stale once another writer moves a branch.

## 2. Converge the exact task commit through gates

Run all gates against the exact tree intended for the first PR:

1. Invoke `rhize-devflow:simplify` on the task diff. A verified no-op is valid. Any accepted edit
   stays inside the task boundary.
2. Run focused tests and every repository-required lint, typecheck, schema/codegen, build, migration
   dry-run, and browser check. Use `/rhize-devflow:check` where available.
3. Create a local commit only when scoped task changes remain. Stage exact paths; inspect the staged
   diff; do not create a gratuitous commit when the completed tree is already committed.
4. Run `/rhize-devflow:review` against the actual first PR base and the final task commit. Resolve
   fixable findings, recommit only scoped fixes, then rerun every invalidated gate and review.

Any simplify, test, review, build, migration-preflight, or required browser gate that fails blocks promotion.
Diagnose the actual failure; do not skip, weaken, or relabel it as a warning to ship.

## 3. Publish the task branch

Push the named task branch with ordinary upstream tracking only after Phase 2 passes. Verify that
the exact local task commit equals the intended remote task ref. A successful `git push` exit code
without remote-ref verification is insufficient.

If the push is rejected, treat it as evidence the remote changed. Do not retry with force. Return to
the divergence rules above.

## 4. Integrate through `dev` when the repository uses it

For a documented `dev` flow:

1. Open a PR from the task branch to `dev` using the repository's template and merge method.
2. Wait for all required checks/reviews. Re-fetch and prove the PR head and base still equal the
   commits reviewed in Phase 2 before merging.
3. Merge through the forge. Never create a direct local commit on `dev` or raw-push `dev` to bypass
   the protected-branch PR.
4. Fetch `origin/dev`; record its exact new SHA and correlate it to the forge's merged PR metadata.
   Verify the merged task tree/ancestry according to the repository's merge strategy.
5. Wait for the `dev` deployment when one exists. Verify the deployment is for that exact remote
   commit, inspect failed build/runtime logs rather than guessing, and run the repository's required
   preview/staging smoke checks.

Do not begin main promotion while the PR, remote-ref, deployment, migration, or smoke evidence for
`dev` is pending or failed.

## 5. Promote to `main` through a PR

Choose the main-promotion source from repository policy:

- A repository with a `dev` flow promotes the verified `origin/dev` tree, normally through a
  short-lived release branch/PR when the forge forbids same-branch PR choreography or a provider
  requires a safe release head commit.
- A repository without a `dev` flow promotes the verified task branch directly by PR to `main`.

Before opening the PR, fetch `origin/main` and prove the source is based on the expected current
integration state. Open the PR, wait for required checks/reviews, re-verify head/base SHAs, and merge
with the repository's required method. "Push to main" never means a raw `git push origin main` or a
direct protected-branch commit.

### Vercel commit-author-safe release head

When repository instructions or verified Vercel evidence show that production deployment accepts
only commits authored by an account with project access, create the release branch from the exact
verified promotion source and add a locally authored **empty release commit** before the PR to
`main`. Before using it:

- verify the configured local author identity is the authorized deployment identity;
- prove the release commit's tree is byte-for-byte identical to its parent; and
- keep the original task/dev history intact — never rewrite authors or fabricate identity.

Use this only when the constraint applies. An author-rejected deployment is a failed gate, not a
reason to bypass Vercel, rewrite someone else's commit, or claim the release succeeded.

## 6. Verify remote production, then report

After the main PR merge:

1. Fetch `origin/main` and record the exact remote SHA. Correlate it to the merged PR's forge
   metadata; account explicitly for merge, squash, or rebase strategy rather than assuming ancestry.
2. Prove the remote main tree contains exactly the reviewed promotion tree. When a release-only
   empty commit exists, prove its tree matches its parent and the verified source tree.
3. Verify the production deployment belongs to that exact main SHA and reaches the provider's
   successful terminal state. Inspect deployment-specific logs on failure.
4. Run repository-required production smoke checks, including migrations/data invariants in their
   documented order. A code push never retroactively proves a migration or deployment succeeded.
5. Report task/source/dev/main SHAs, PRs, checks, deployments, smoke evidence, migration status,
   and any skipped/unavailable verification. Never claim "regression-free" or equivalent certainty;
   state what was actually tested and observed.

## Stop conditions

Stop promotion and leave recoverable state in place when any of these occurs:

- authorization or branch/remote ownership is unresolved;
- `superpowers:finishing-a-development-branch` is unavailable;
- unrelated dirty work cannot be isolated;
- a source/integration branch diverges or moves unexpectedly;
- simplify, review, test, build, migration, required PR check, deployment, or smoke gate fails;
- a protected-branch rule would need bypassing;
- commit-author safety cannot be satisfied with a verified authorized local identity; or
- exact remote commit/deployment correlation cannot be established.

Report the blocking evidence and the last completed phase. Do not silently continue with a shorter
sequence, infer success from source code, or delete branches/worktrees that may be needed to recover.
