---
name: rhize-review
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
5. **(Optional) Production signal.** If a GitHub PR exists, pull Sentry bot review comments (`gh api repos/{owner}/{repo}/pulls/{n}/comments`, filter for `sentry`) and fold unresolved CRITICAL/HIGH items into the findings.
6. **Aggregate.** Drop findings with confidence < 80, dedupe by `file:line` + issue, bucket into **Critical / Important / Minor**, and list **Strengths**.
7. **Verdict.** Emit exactly one: **Ready to merge? Yes / No (Critical present) / With fixes (Important present)**.
8. **Resolve, then gate.** Fix Critical (mandatory) and Important (before merge) using verify-before-fix discipline — verify each finding against the code, push back on wrong findings, no reflexive agreement. **REQUIRED background:** superpowers:receiving-code-review. Re-run affected lanes if fixes were substantial. The merge/push itself still follows the Git Push Policy (production repos = only on the user's explicit go-ahead).

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
