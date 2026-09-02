# Review gate lessons

Operating reference for `/rhize-devflow:review`'s Phase 4 (routing) and Phase 6
(aggregation), distilled from prior gate runs against the retired `rhize-review`
repo-root adapter. This is lessons and defaults, not a second workflow — it never
overrides `commands/review.md`'s contract, and it is never itself invoked.

## Specialist routing by changed files

`review.md`'s Phase 4 routes by matched **risk category** (security, data, deployment,
...). The table below is the finer-grained, stack-based routing that produced the best
results in practice — use it to pick the actual specialist once a risk category is
matched, and as a fallback discovery table when `review.md`'s generic category names
don't map cleanly onto what changed.

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

### The largest single quality lever: name the claims each lane must attack

Dispatching a lane with "review this" produces generic, low-value output. Across gate
runs, every high-value finding traced back to naming **1–3 specific claims the diff
makes, for each lane, and asking the lane to attack them** — for example: "is this ISR
premise actually true in Next 16?" or "does lowering this budget trade a rare stall for
a common false alarm?" None of the high-value findings came from an unscoped "review
this" prompt. When routing a specialist, spend the effort here first, before worrying
about which specialist to pick.

### Production signal: folding in Sentry-bot PR comments

When a GitHub PR exists, pull its Sentry bot review comments and fold unresolved
CRITICAL/HIGH items into the findings before aggregating:

```bash
gh api repos/{owner}/{repo}/pulls/{n}/comments
```

Filter the results for comments from a `sentry` bot account; treat only the unresolved
CRITICAL/HIGH items as findings. This is optional evidence, not a replacement for the
lane-based routing above.

## Aggregating findings (Phase 6)

- **Drop low-confidence noise.** Discard any finding with confidence below 80 before
  it reaches the verdict.
- **Dedupe by `file:line` + issue.** The same defect flagged by two lanes is one
  finding, not two.
- **Bucket into Critical / Important / Minor**, and separately list **Strengths** —
  a review that only lists problems under-reports what the change got right.
- **Empirical reproduction outweighs a likelihood assessment.** When lanes disagree,
  two lanes that reproduced a defect beat a third lane that dismissed the same path as
  "synthetic, not a live gap." Say which evidence carried the verdict.
- **A comment's stated invariant is a testable claim, not a settled fact.** Treat
  wording like "an error in our code can never be silenced" as something to verify: if
  no test pins that invariant, the missing test is itself a finding.

### False positive to drop on sight: `.env.example`

`ecc:security-reviewer` cites a `.env.example` file as a "safe pattern" for documenting
required environment variables. This repository's standing rule forbids `.env.example`
/ `.sample` env templates outright (document required variable names in Markdown
instead — see root `CLAUDE.md`). Any finding recommending one is a false positive:
drop it during aggregation, don't report it as a fix.

## Limits

- **No specialist reviewer for Apex/Salesforce or n8n/JSON workflows.** Those changes
  get the general + security lanes only, never a dedicated specialist pass.
- **`ecc:code-simplifier` is never part of this gate.** It edits code, and review is
  read-only; run `/rhize-devflow:simplify` separately for the quality/refactor pass.
- **Security lanes are checklist-breadth, not deep SAST.** They cover OWASP / secrets /
  SSRF / injection / crypto / auth / dependency classes as a strong first pass — treat
  that as a floor, not a substitute for a dedicated audit on genuinely high-risk changes.

## Before you ship: pre-merge checklist

Run these last, in order, immediately before merging — verifying earlier in the gate
does not count, because any of the three can change between an earlier check and the
actual merge:

1. **Cold-cache verification is a reported limitation, not something review fixes.**
   A possibly stale transform/build cache is reported as a verification limitation.
   Review never deletes caches itself; an authorized implementation/check step performs
   any cleanup and reruns verification.
2. **The tree must be clean, checked last.** `git status --porcelain` and `git diff
   HEAD` must both be empty immediately before merging. This is what catches
   mutation-test residue or a half-reverted experiment that an earlier check would have
   missed.
3. **Re-check divergence against the remote.** `git fetch && git log --oneline
   HEAD..origin/<branch>` — a gate that verified a tree the remote has since moved past
   has verified nothing that will actually ship.

## Read-only discipline: no scratch files in the shared tree

"Read-only" means no files land in the shared working tree, even temporarily and even
if deleted afterward. A prior gate run wrote a throwaway `__scratch_probe.ts` into the
checkout to type-check a question against the app's `tsconfig`, then deleted it — "don't
mutate the diff" didn't cover that case, but the clean-tree check above did catch it.
Run any such probe from the scratchpad against a standalone `tsconfig`, never inside the
shared tree — and treat the pre-merge clean-tree check, not this rule, as the actual
backstop.
