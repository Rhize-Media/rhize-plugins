---
name: rhize-review
tier: custom
domain: dev-flow
maturity: stable
description: Use when about to merge or push changes on a production-level website or app (a Vercel or deploy-on-push repo — e.g. a Next.js/Sanity site or rhize-salesforce), or whenever a pre-merge / pre-push review of a feature branch or PR is needed and a clear go / no-go merge decision is required. Triggers on "review before merge", "is this safe to ship", "production code review".
---

# rhize-review

This repository-level entry point adapts to the canonical installed
`rhize-devflow:review` and `rhize-devflow:test-evidence` contracts. Invoke those skills when they are
available; do not maintain a richer parallel review implementation here.

## Overview

One compatibility entry point for the production merge gate. The canonical Dev Flow plugin scopes
the change, routes relevant read-only reviewers, validates optional test evidence, and returns one
merge verdict.

This adapter does not dispatch, mutate, merge, push, deploy, or re-implement the canonical logic.

## When to use

- Before completing any merge/push on a production website or app (the Vercel / deploy-on-push "manual-push" repos).
- When you want a multi-lens review (correctness + security + framework + tests) ending in a clear "ready to merge?" answer.

When NOT to use: routine quality cleanup (use `/simplify`), or a quick single-pass bug scan on a throwaway diff (use native `/code-review`).

## Compatibility procedure

When Dev Flow is installed, stop after invoking its canonical `review` and, when applicable,
`test-evidence` surfaces. The notes below preserve prior collision, clean-tree, and divergence lessons
for the disclosed read-only fallback only; they do not authorize a second review implementation.

1. **Scope the diff.** Given a PR number/URL → `gh pr diff`. Otherwise detect the repo's default branch dynamically (never hard-code `main`), set `BASE = git merge-base <default> HEAD`, `HEAD` = working tree, and list changed files: `git diff --name-only BASE...HEAD` plus staged/unstaged.
2. **Classify the repo.** It's a production app if it has `vercel.json` / `.vercel/` / `next.config.*`, deploys on push, or is `force-app/` Salesforce. For production apps the **security lane is MANDATORY**.
3. **Route by changed files** (table below). Always include `ecc:code-reviewer`.
4. **Use the canonical Dev Flow review routing.** It dispatches read-only specialist lanes for the
   exact range. Mutation testing is never performed inside review. If a regression claim needs
   mutation evidence, invoke `rhize-devflow:test-evidence` beforehand in its isolated worktree and
   pass only the validated local packet to review.
   - **Name 1–3 specific claims the diff makes for each lane to attack** ("is this ISR premise actually true in Next 16?", "does lowering this budget trade a rare stall for a common false alarm?"). Across gate runs, every high-value finding came from a targeted challenge; none came from generic "review this." This is the largest single quality lever in the dispatch.
   - If the canonical plugin is unavailable, perform a disclosed read-only cold review. Report
     mutation evidence unavailable; never mutate the checkout as a fallback.
   - Never run reviewer tests while the separate test-evidence runner holds its exclusive mutation
     lease. A result observed against a mutant is not evidence about the clean revision.
   - **Read-only means no files in the shared tree, even temporarily.** A "read-only" lane once wrote a `__scratch_probe.ts` into the checkout to type-check a question against the app's tsconfig, then deleted it — "don't mutate the diff" didn't cover it. Probes run from the scratchpad against a standalone tsconfig, never inside the shared tree. (And trust step 9, not this instruction: the clean-tree check is what actually caught it.)
   - The evidence runner reports mutation unavailable when its disposable worktree lacks required
     dependencies; review must not fall back to mutating the live checkout.
5. **(Optional) Production signal.** If a GitHub PR exists, pull Sentry bot review comments (`gh api repos/{owner}/{repo}/pulls/{n}/comments`, filter for `sentry`) and fold unresolved CRITICAL/HIGH items into the findings.
6. **Aggregate.** Drop findings with confidence < 80, dedupe by `file:line` + issue, bucket into **Critical / Important / Minor**, and list **Strengths**. When lanes disagree, an empirical reproduction outweighs an assessment of likelihood — two lanes reproducing a defect beat a third dismissing the same path as "synthetic, not a live gap" — and the verdict should say which evidence carried it. Treat a comment's stated invariant ("an error in our code can never be silenced") as a testable claim: if no test pins it, that gap is itself a finding.
7. **Verdict.** Emit exactly one: **Ready to merge? Yes / No (Critical present) / With fixes (Important present)**.
8. **Report fixes, then gate again.** The implementer resolves Critical and Important findings
outside this read-only workflow, verifies premises as well as conclusions, and invokes review again.
Merge/push remains separately governed by repository policy.
9. **Verify on a cold cache, then confirm the tree is clean.** Both guard against passing the gate on evidence that was never real:
   - Report a possibly stale transform cache as a verification limitation. Review does not delete
     caches; an authorized implementation/check step performs any cleanup and reruns verification.
   - **`git status --porcelain` must be empty, and `git diff HEAD` must be empty, immediately before merging.** This catches mutation-test residue from step 4 and any half-reverted experiment. Verifying earlier does not count — the check has to be the last thing before the merge.
   - Re-check divergence too (`git fetch && git log --oneline HEAD..origin/<branch>`): a gate that verified a tree the remote has since moved past has verified nothing that will ship.

## Historical fallback routing hints

The canonical plugin owns current routing. Use this table only to explain a disclosed read-only
fallback; do not treat it as a second source of truth.

| Changed files | Lane(s) |
|---|---|
| any change (always) | `ecc:code-reviewer` |
| prod app, or auth / user-input / API route / secrets / payment / DB | `ecc:security-reviewer` |
| `.tsx` / `.jsx`, Next.js `app/` dir | `ecc:react-reviewer` + `ecc:typescript-reviewer` |
| `.ts` / `.js` (no React) | `ecc:typescript-reviewer` |
| `.py` | `ecc:python-reviewer` (Django → `ecc:django-reviewer`, FastAPI → `ecc:fastapi-reviewer`) |
| `.go` / `.rs` / `.java` | `ecc:go-reviewer` / `ecc:rust-reviewer` / `ecc:java-reviewer` |
| `.sql`, migrations, schema | `ecc:database-reviewer` |
| test files (`*.test.*`, `*.spec.*`, `tests/`, `__tests__`) | `ecc:pr-test-analyzer` |
| error handling / try-catch / fallbacks touched | `ecc:silent-failure-hunter` |
| new or changed types / interfaces | `ecc:type-design-analyzer` |
| Salesforce (`force-app/`, `.cls`, `.trigger`, flows) | `ecc:code-reviewer` + `ecc:security-reviewer` (no Apex specialist — see Limits) |

## Limits

- No specialist reviewer for Apex/Salesforce or n8n/JSON workflows → those get general + security only.
- The quality/refactor pass (`ecc:code-simplifier`) edits code, so it is NOT part of this gate; run `/simplify` separately if wanted.
- Security lanes are checklist-breadth (OWASP / secrets / SSRF / injection / crypto / auth / deps), not deep SAST — a strong first pass, not a substitute for a dedicated audit on high-risk changes.
- `ecc:security-reviewer` cites `.env.example` as a "safe pattern". IGNORE any finding that recommends adding a `.env.example` / `.sample` env template — the standing rule forbids them (document required vars in markdown instead). Drop such findings during aggregation.
