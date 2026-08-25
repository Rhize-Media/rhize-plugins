---
name: rhize-review
tier: custom
domain: dev-flow
maturity: stable
description: Use when about to merge or push changes on a production-level website or app (a Vercel or deploy-on-push repo — e.g. a Next.js/Sanity site or rhize-salesforce), or whenever a pre-merge / pre-push review of a feature branch or PR is needed and a clear go / no-go merge decision is required. Triggers on "review before merge", "is this safe to ship", "production code review".
---

# rhize-review

## Overview

One entry point for a production merge-gate review. It scopes the change set, routes it to the right specialist reviewers, runs them as isolated subagents, then returns **one merge verdict**.

Composition only: it dispatches existing `ecc:*` review agents and uses the superpowers review glue. It does **not** re-implement review logic, and it does **not** merge, push, or auto-edit code — it gates.

## When to use

- Before completing any merge/push on a production website or app (the Vercel / deploy-on-push "manual-push" repos).
- When you want a multi-lens review (correctness + security + framework + tests) ending in a clear "ready to merge?" answer.

When NOT to use: routine quality cleanup (use `/simplify`), or a quick single-pass bug scan on a throwaway diff (use native `/code-review`).

## Procedure

1. **Scope the diff.** Given a PR number/URL → `gh pr diff`. Otherwise detect the repo's default branch dynamically (never hard-code `main`), set `BASE = git merge-base <default> HEAD`, `HEAD` = working tree, and list changed files: `git diff --name-only BASE...HEAD` plus staged/unstaged.
2. **Classify the repo.** It's a production app if it has `vercel.json` / `.vercel/` / `next.config.*`, deploys on push, or is `force-app/` Salesforce. For production apps the **security lane is MANDATORY**.
3. **Route by changed files** (table below). Always include `ecc:code-reviewer`.
4. **Dispatch concurrently** via the Agent tool — one message, multiple calls, one per lane. Give each agent ONLY: the `BASE...HEAD` range, its lane's file list, and a 2–3 sentence change summary. Never pass conversation history. **REQUIRED background:** superpowers:requesting-code-review. Tell each agent "zero findings is a valid result."
   - **Name 1–3 specific claims the diff makes for each lane to attack** ("is this ISR premise actually true in Next 16?", "does lowering this budget trade a rare stall for a common false alarm?"). Across gate runs, every high-value finding came from a targeted challenge; none came from generic "review this." This is the largest single quality lever in the dispatch.
   - **At most ONE lane may mutate the working tree.** Mutation testing is the single most valuable thing this gate does, so make it an explicit expectation of `ecc:pr-test-analyzer`, not a footnote: *reintroduce the exact bug each new/changed test claims to guard; if the test still passes, the test is theatre.* This framing has caught a brand-new test that could never fail (a mock discarded the very prop the assertion read) and a surviving mutant that became the run's blocking finding. Have the lane report each mutant as killed/survived. Every other lane is read-only. All lanes share one checkout, so two writers corrupt each other's reads; a stray `console.log` from one lane once turned up mid-review in a file another lane was assessing. Instruct the mutating lane to back up before and restore after, and to report what it mutated.
   - **A read-only lane's test RUN during the mutation window produces phantom "flaky test" findings.** (2026-08-25, glenwood, twice in one gate.) Two lanes each reported a new test failing "once in N runs" with a credible-sounding race theory; both failure signatures were byte-for-byte the kill signature of a mutant the mutation lane held applied to the shared checkout at that moment, and neither reproduced across 8+ clean full-suite runs afterward. The one-writer rule protects the DIFF, but a reader executing `vitest` mid-mutation reads mutated source. Two mitigations, in preference order: (1) tell read-only lanes to run suites at the START of their pass, before the mutation lane is likely mid-mutant, or accept the aggregator re-running them; (2) during aggregation, treat every "intermittent" failure observed by a concurrent lane as suspect-collision FIRST — diff its failure signature against the mutation lane's mutant list before accepting a race-condition theory, then re-run clean N times to confirm. An empirical repro normally outranks likelihood arguments (step 6), but a repro taken from a tree another lane was mutating is not an observation of the committed code.
   - **Read-only means no files in the shared tree, even temporarily.** A "read-only" lane once wrote a `__scratch_probe.ts` into the checkout to type-check a question against the app's tsconfig, then deleted it — "don't mutate the diff" didn't cover it. Probes run from the scratchpad against a standalone tsconfig, never inside the shared tree. (And trust step 9, not this instruction: the clean-tree check is what actually caught it.)
   - Do **not** reach for `isolation: "worktree"` to solve this in a pnpm monorepo: a fresh worktree has no `node_modules`, so no lane could run the suite without a full install. The one-writer rule is the cheap fix.
5. **(Optional) Production signal.** If a GitHub PR exists, pull Sentry bot review comments (`gh api repos/{owner}/{repo}/pulls/{n}/comments`, filter for `sentry`) and fold unresolved CRITICAL/HIGH items into the findings.
6. **Aggregate.** Drop findings with confidence < 80, dedupe by `file:line` + issue, bucket into **Critical / Important / Minor**, and list **Strengths**. When lanes disagree, an empirical reproduction outweighs an assessment of likelihood — two lanes reproducing a defect beat a third dismissing the same path as "synthetic, not a live gap" — and the verdict should say which evidence carried it. Treat a comment's stated invariant ("an error in our code can never be silenced") as a testable claim: if no test pins it, that gap is itself a finding.
7. **Verdict.** Emit exactly one: **Ready to merge? Yes / No (Critical present) / With fixes (Important present)**.
8. **Resolve, then gate.** Fix Critical (mandatory) and Important (before merge) using verify-before-fix discipline — verify each finding against the code **and verify its premises, not just its conclusion** (a lane once cited a lint rule the repo doesn't have; a dispatch prompt once asserted a test file was new when it already existed), push back on wrong findings, no reflexive agreement. **REQUIRED background:** superpowers:receiving-code-review. Re-run affected lanes if fixes were substantial. The merge/push itself still follows the Git Push Policy (production repos = only on the user's explicit go-ahead).
9. **Verify on a cold cache, then confirm the tree is clean.** Both guard against passing the gate on evidence that was never real:
   - **Clear stale transform caches before the verification run** (`rm -rf {apps,packages}/*/node_modules/.vite`, or the equivalent for the bundler in use). A stale vite cache has served transforms from *before* the diff — producing failures that matched historical file states, and, more dangerously, capable of producing a PASS against code that was never compiled. Costs seconds; a false PASS on a production gate costs a deploy.
   - **`git status --porcelain` must be empty, and `git diff HEAD` must be empty, immediately before merging.** This catches mutation-test residue from step 4 and any half-reverted experiment. Verifying earlier does not count — the check has to be the last thing before the merge.
   - Re-check divergence too (`git fetch && git log --oneline HEAD..origin/<branch>`): a gate that verified a tree the remote has since moved past has verified nothing that will ship.

## Routing table

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
