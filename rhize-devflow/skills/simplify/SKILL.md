---
name: simplify
description: >-
  Safely simplify recent or explicitly scoped code changes by consolidating duplicated policy,
  removing accidental complexity, and eliminating unnecessary work without changing behavior.
  Use after implementation or before delivery when the user asks to simplify, consolidate,
  deduplicate, reduce complexity, apply React best practices, remove redundant state/effects, or
  review recent code for a cleaner solution. A verified no-op is valid; never expand into broad
  redesign or unrelated cleanup.
metadata:
  rhize:
    tier: custom
    domain: dev-flow
    maturity: stable
    version: 1.0.0
    topics: [workflow-patterns]
    stacks: [nextjs, testing]
    extends: [dev-flow-foundations]
---

# Simplify

Make the scoped change easier to understand and harder to misuse without changing product
behavior, public contracts, security boundaries, or operational semantics. The objective is less
code and fewer sources of truth, not stylistic churn. A well-supported no-op is a valid result.

## Core contract

- **Resolve the exact boundary first.** Honor user-specified files/ranges. Otherwise inspect the
  current task's changes, including committed work when the tree is clean. Never silently treat the
  whole repository as "recent work."
- **Preserve behavior and authority.** Product intent, APIs, schemas, authorization, tenancy,
  auditability, concurrency, accessibility, error vocabulary, and external side effects are
  constraints, not cleanup opportunities.
- **Minimum useful change.** Apply only candidates that remove a source of truth, branch,
  duplication, or unnecessary operation. Moving a one-off block behind a new abstraction is not
  simplification.
- **No manufactured findings.** If the code is already the simplest reliable form, report a
  verified no-op.
- **No extra release authority.** This workflow may edit only when the user's request already
  authorizes edits. It never grants permission to commit, push, merge, deploy, migrate data, or
  perform another external mutation.

## Phase 1: establish the review boundary

1. Read repository instructions and inspect Git status before judging the code. Preserve unrelated
   work; use an isolated worktree when the active checkout is dirty or shared.
2. Resolve the comparison range in this order:
   - explicit user-specified range, files, or focus;
   - files changed by the current task, whether staged, unstaged, or committed;
   - branch merge-base/upstream evidence when the task boundary is otherwise unclear.
3. Include equivalent callers and source contracts only when needed to prove that a proposed
   consolidation preserves behavior. Do not turn that dependency check into repository-wide
   cleanup.
4. Record the range and run the smallest relevant baseline check before editing. Distinguish a
   pre-existing failure from a regression introduced by simplification.

## Phase 2: review through three lenses

Run three distinct passes, then deduplicate the candidates. Parallel reviewers are optional only
when delegation is explicitly authorized and available; the lenses do not require subagents.

### Reuse and consolidation

- Find repeated policy, role checks, validation, error mapping, transformations, or test setup in
  the changed code and its equivalent callers.
- Prefer an existing helper or contract over creating another abstraction.
- Centralize a business rule when caller drift could allow different behavior.
- Reject abstractions that obscure domain language, add indirection without reducing the future
  change surface, or exist for one use only.

### Quality and correctness

- Remove redundant or prop-mirrored state, unreachable branches, unused return values, misleading
  names, and comments that only narrate syntax.
- Preserve comments that explain decisions, security invariants, concurrency, migrations, or
  non-obvious product rules.
- Check types, failure/loading lifecycle, permissions, accessibility, retries, optimistic
  concurrency, and equivalent mutation paths before consolidating.
- Treat database and external API contracts as behavior. Never rewrite an applied migration to
  make it cleaner; use a forward-only change only when a real defect warrants one.

### Efficiency

- Remove duplicate reads, repeated calculations, needless serialization, unnecessary effects, and
  work performed at a broader scope than its consumer needs.
- Prefer deletion and direct derivation over new layers.
- Do not add caching, memoization, batching, or concurrency without evidence that it helps.
  Performance machinery is not simplification by itself.

## React and Next.js gold-standard checks

When React or Next.js is in scope:

- Derive render values directly from props and state. Use Effects to synchronize with external systems,
  not to mirror props or calculate render state.
- Keep transient state local and model only information that cannot be derived. Preserve explicit
  pending state when it enforces mutation, stale-response, or refresh correctness.
- Keep Server Components as the App Router default and place `"use client"` at the narrowest
  practical interactive boundary. Never move server data or secrets into client props for
  convenience.
- Use `useMemo`, `useCallback`, and `memo` only for measured performance needs or when referential
  stability is required by an API—never for correctness or by habit.
- Prefer semantic HTML, accessible names, native disabled states, stable keys, deterministic
  rendering, and event handlers over effect-driven user actions.
- Extract a component or custom hook only when it has a coherent responsibility, is reused, or
  materially clarifies its caller—not solely because a file is long.
- For server mutations, keep client state aligned with authoritative refreshed data and preserve
  duplicate-submit, stale-response, loading, and error safeguards.

## Phase 3: candidate gate

Apply a candidate only when every condition holds:

1. Observable behavior and accepted product intent remain unchanged.
2. Authorization, tenancy, audit, concurrency, accessibility, and error contracts remain at least
   as strong.
3. The result has fewer sources of truth, fewer branches, less duplication, or clearer ownership.
4. Relevant tests can demonstrate preserved behavior, or the change is mechanically verifiable.
5. Every touched line belongs to the scoped change; there is no drive-by cleanup.

Reject a candidate when it crosses a product decision, changes an API/schema, weakens a defensive
layer, relies on speculative performance work, or produces only subjective stylistic churn.
Record important rejections so a future session does not repeat the same unsafe proposal.

## Phase 4: execute and verify

For an edit-authorized request:

1. Apply the smallest independent candidate first.
2. Add or adjust regression coverage when a shared rule or removed state transition is not already
   pinned by tests.
3. Run focused tests after each meaningful candidate.
4. Re-read the final diff cold and confirm the net result is simpler, not merely different.
5. Run repository-required lint, type, build, database, and broader test gates in proportion to
   risk. Use `/rhize-devflow:check` for the deterministic implementation gate and
   `/rhize-devflow:review` before production release.
6. Follow repository commit, push, and release policy; do not infer authority from this skill.

For a read-only request, report candidates and evidence without editing.

## Report

State:

- the exact range or files reviewed;
- simplifications applied and why they reduce complexity;
- tempting changes rejected because they add risk or abstraction;
- validation performed and any pre-existing failures;
- remaining recommendations, separated from completed work.

## Provenance and Rhize extensions

This workflow is an additive adaptation of Claude Code's built-in `simplify` command. It preserves
the upstream reuse/quality/efficiency lenses and adds the controls required for reliable Rhize and
Codex work: exact diff resolution, dirty-worktree protection, an explicit behavior-preservation
gate, verified no-op outcomes, React/Next.js conventions, migration and external-contract safety,
authorization/concurrency checks, and separation between code-edit and release authority. Recheck
the current upstream command when its three-lens contract changes; retain Rhize additions only
while they continue to close those gaps.
