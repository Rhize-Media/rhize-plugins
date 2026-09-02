---
description: Read-only production merge/release gate. Use for a review before merge, to answer "is this safe to ship", or for a production code review before a push, deploy, or release — resolves the exact comparison range, builds a risk map from actual diff evidence, routes only relevant specialist reviews, and returns one merge verdict backed by an independent skeptical reviewer
---
<!-- canonical: rhize-devflow:review -->

# Review

Gate a merge, push to a manual-push/production repository, or release. This command
analyzes; it never ships.

## Core Contract

- **Read-only.** This command never commits, pushes, merges, deploys, edits files, or
  resolves external issues (tickets, PR comments) from within the review. If the verdict
  permits shipping, the actual merge/push/deploy remains a separate, explicit action
  governed by the repository's own push policy — never performed by this command.
- **Resolve the exact range first.** Establish base and head from explicit user intent and
  Git evidence before any analysis. Never assume the default branch is the merge target —
  when resolution is a guess rather than a stated intent, report the ambiguity and ask
  rather than proceed on the guess.
- **Evidence, not impression.** `devflow.py evidence` reports the changed-file, protected,
  and base-resolution facts this workflow builds its risk map from. Deployment, data,
  security, authorization, billing, migration, cache, and external-write risk come from
  actual changed files and repository policy — never from a general impression of the
  change.
- **No fixed panel.** Route only the specialist reviews the risk map actually calls for; a
  trivial documentation diff gets no specialist panel.
- **Independent reviewer required for non-trivial work.** A separate agent/model that did
  not write the change reviews it. If none is available, this command performs a disclosed
  cold review and marks the limitation in its output — it does not silently skip the check.
- **Preserve accepted product decisions as constraints — reviewers do not relitigate scope.**
  A decision the team already accepted (documented in repository instructions or the
  session) is a constraint the review works within, not a finding to reopen.
- **Distinguish introduced failures from pre-existing failures; report both, dismiss
  neither.** A failure this change did not cause is still reported — it is never silently
  attributed away, and it is never used to inflate this change's own verdict either.
- **Review never runs mutations.** When tests changed or a regression claim is material, validate
  the explicitly supplied local packet with `scripts/test_evidence.py validate`. Reject stale,
  unknown, incomplete, unsupported, or cleanup-failed evidence. Never restore or edit from review.

## Triggers

Use before merging, pushing to a manual-push/production repository, or cutting a release —
typically after `/rhize-devflow:check` has already passed, with or without warnings. This is
the last gate before a merge/push decision.

## Phase 1: Resolve the Exact Comparison Range

1. Resolve base and head from **explicit user intent first**: a stated PR/MR number or URL,
   a named target branch, or the repository's own documented release flow
   (`CLAUDE.md`/`AGENTS.md`/README). Never assume the default branch is the merge target —
   the real target may be a `dev` branch, a release branch, or whatever the user or
   repository policy names, not whatever Git happens to resolve to when nothing is stated.
2. Cross-check that intent against Git evidence with the evidence CLI's `--base` argument
   (Phase 2). Its `git.base.resolved_via` field reports how the base was actually found:
   - `explicit` or `upstream` — a real signal (the caller supplied `--base`, or the branch
     has a tracked upstream). Treat as settled.
   - `default-branch`, `local-fallback`, or `unresolved` — a guess, not a confirmed
     target. Do not silently treat a guess as the merge target: report the ambiguity and
     ask the user to confirm the actual target branch before proceeding with analysis,
     unless the user already named one in Step 1.
3. Identify the exact comparison range (the resolved base SHA against head) before any risk
   analysis begins. Every downstream phase operates on this range, not on "whatever changed
   recently."

## Phase 2: Build the Evidence Packet

For each affected repository root — treat each independently in multi-repository work;
never merge two roots' evidence or verdict into one:

```bash
python3 "$CLAUDE_PLUGIN_ROOT/scripts/devflow.py" evidence --json --repo <root> --base <ref-from-phase-1>
```

Treat the output as facts, not permission — the same discipline `/rhize-devflow:check`
uses. From the evidence packet:

- `git.base` — the resolved base and how it was resolved (Phase 1).
- `git.changed_files` — the actual diff surface for this root, scoped to the resolved range
  plus working-tree state.
- `protected_matches` / `findings` — any protected-file touch, always reported, never
  cleared.
- `instruction_files` — whether `CLAUDE.md`/`AGENTS.md` exist; read them for
  repository-declared release/branch policy and any accepted product decisions before
  finalizing Phase 1's resolution and Phase 3's risk map.
- `codegraph` — whether a healthy index exists, for cross-referencing structural evidence
  against the semantic impact map (when one exists for this change) in Phase 3.
- `test_evidence_candidates` — advisory changed-test candidates. Classify the declared contract;
  do not convert a raw `readFile`/`toContain` pattern into a blocking verdict without evidence.

Never initialize `.codegraph/` — use it only when it already exists and is healthy.

## Phase 3: Build the Risk Map

Using `git.changed_files`, repository policy from `instruction_files`, deployment behavior,
and any semantic impact map already produced for this change, classify the diff against
every risk category below. Name each category the diff plausibly touches, even when the
resulting risk is low; a category with no signal is stated as unaffected, not omitted.

| Risk category | Signals to check in the diff and repository policy |
|---|---|
| Deployment | Build/deploy config, `vercel.json`, Dockerfiles, `.github/workflows/*`, infra-as-code |
| Data | Schema/model changes, backfills, data-shape changes, PII fields |
| Security | Auth, input validation, secrets handling, tracing/PII scrubbing (e.g. Sentry instrumentation config) |
| Authorization | Role/permission checks, access-control logic, tenant isolation |
| Billing | Payment, invoicing, subscription, or `billing`/`payment` paths |
| Migration | `migrations/`, `alembic/`, `.sql` files, schema-generation output |
| Cache | Cache keys, invalidation, CDN/edge cache config, query-key changes |
| External-write | Any call that writes to a system outside this repository (webhook, third-party API, ticket system) |

A change is **trivial** only when no risk category above is matched — for example a
documentation-, comment-, or formatting-only diff. Any matched category makes the change
non-trivial and requires Phase 5's independent reviewer.

## Phase 4: Route Specialist Reviews

Route only the specialist review(s) the matched risk categories call for — no fixed panel
for a trivial change. Name available specialist agents/skills generically; when this
plugin's usual specialist isn't installed, note the absence in the output and continue —
an unavailable specialist alone does not force `FAIL_REQUIRES_HUMAN` unless the underlying
risk itself demands human judgment regardless of tooling (security, billing, an unsanctioned
protected-file touch).

| Matched risk category | Specialist to route (if installed) |
|---|---|
| Security, authorization, billing | Security reviewer (e.g. `ecc:security-reviewer`) |
| Data, migration | Database/migration reviewer (e.g. `ecc:database-reviewer`) |
| UI/browser-facing changes | Accessibility/browser reviewer (e.g. `ecc:a11y-architect`, `/rhize-devflow:browser-qa`) |
| Deployment | Delivery/CI reviewer, informed by repository push/deploy policy |
| Security (tracing/PII scrubbing) | Security reviewer, informed by this plugin's `sentry-instrumentation` conventions |

For the finer-grained, stack-based routing table (React/TypeScript/Python/Go/Rust/Java/
database/test/error-handling/type-design specialists) and the technique that produces
the highest-value findings, see [`docs/review-lessons.md`](docs/review-lessons.md).

## Phase 5: Independent Skeptical Review

For any non-trivial change (Phase 3), route to a separate agent/model that did not write the change
under review — a fresh subagent invocation of this plugin's independent verifier, or another
available cold second-opinion reviewer. Never let the same context/session that authored the
diff grade its own work.

If no independent reviewer is available, perform a **disclosed cold review**: re-read the
diff adversarially yourself, and explicitly mark in the final output that no independent
reviewer ran and why — never silently skip this step and present the verdict as if an
independent pass occurred.

## Phase 6: Report One Merge Verdict

Return exactly one of:

- **`PASS`** — every matched risk category is addressed, no unresolved protected-file touch
  remains, and (for non-trivial work) the independent reviewer — or the disclosed cold
  review — raised no unresolved finding.
- **`FAIL_WITH_FIXABLE_GAPS`** — a concrete, fixable gap remains (a missing test, an
  unaddressed specialist finding, an unhandled edge case) that does not itself require
  human judgment to resolve.
- **`FAIL_REQUIRES_HUMAN`** — security, billing, an unsanctioned `.github/workflows/*`
  touch, or genuinely ambiguous merge intent (Phase 1 could not confirm the target) remains
  unresolved.

Present findings as a table:

| Finding | File | Severity | Suggested fix owner |
|---|---|---|---|

"Suggested fix owner" names who resolves it — the implementer, a named specialist, or "the
user (human judgment required)" for anything landing in `FAIL_REQUIRES_HUMAN`.

## Safety

- Read-only: this command never commits, pushes, merges, deploys, edits files, or resolves
  external issues — no external mutation of any kind happens from within review.
- A protected-file touch is always surfaced. An unsanctioned touch to
  `.github/workflows/*` always returns `FAIL_REQUIRES_HUMAN`. Workflow changes are never auto-approved
  by this command, regardless of the rest of the diff's risk.
- Never initialize `.codegraph/` — use it only when it already exists and is healthy.
- An unavailable independent reviewer never becomes an unreported gap — the disclosed cold
review and its limitation must appear in the output.

When a behavior-regression claim is part of the change, report the packet verdict separately:
`oracle_supported` or `killed` supports it; `survived_mutation`, `oracle_missing`, unavailable, or
stale evidence is a fixable gap. `cleanup_failed` is `FAIL_REQUIRES_HUMAN`. An explicitly justified
`artifact_contract` is valid only for the representation it names.

## Related Workflows

- `/rhize-devflow:check` — run first; this command expects `check` to have already passed
  or reported its warnings.
- `/rhize-devflow:impact-map` — supplies the semantic invariants and intended delta used in
  Phase 3's risk map, when one exists for this change.
- `agents/verifier.md` — the independent verifier this command routes to for non-trivial
  work (same plugin).
- `dev-flow-foundations` — rationale and reusable impact-analysis principles (same plugin).
- [`docs/review-lessons.md`](docs/review-lessons.md) — stack-based specialist routing,
  the Sentry-bot PR-comment fold-in, aggregation rules, the `.env.example` false-positive
  rule, and the pre-merge checklist distilled from prior gate runs.
