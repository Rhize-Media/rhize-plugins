# Behavioral Test Evidence Gate

| Field | Value |
|---|---|
| Status | Proposed for review |
| Date | 2026-08-30 |
| Primary owner | `rhize-devflow` |
| Planning/review tier | Sol |
| Recommended implementation tier | Terra for gate integration; Luna for labeled fixtures and documentation |

## Decision

Make test validity a first-class Dev Flow evidence lane. A passing test suite is insufficient when
changed tests merely restate current implementation. The gate must distinguish legitimate
source/artifact contracts from behavior claims, and use an independent oracle or mutation evidence
for the latter.

Do not implement a blanket ban on source-content assertions and do not append an unscoped one-line
rule to every repository.

## Independent source review

Matt Pocock's [X post](https://x.com/mattpocockuk/status/2093068185830347088) proposes adding
“Tautological tests considered harmful” to repository standards so `/code-review` applies the rule.
The attached example reads a CSS file and checks for literal dark-mode strings; it verifies source
shape, not rendered behavior. The test is not literally tautological—it can fail when text changes—
and exact-text assertions are valid when text is the external contract. The useful insight is durable,
repository-scoped review guidance; the stronger enforcement is mutation or counterexample evidence.

## Verified current state

- `/rhize-devflow:check` selects and runs focused tests but does not assess whether their oracle is
  independent of implementation.
- `/rhize-devflow:review` builds a risk map and requires skeptical review, but has no explicit
  test-quality lane.
- The repo-root `skills/rhize-review/SKILL.md` already carries a stronger learned rule: reintroduce
  the exact bug a changed test claims to guard and report killed versus survived mutants.
- That mutation contract is not yet the canonical behavior of the installed `rhize-devflow` plugin.

## Test classification

Every changed or newly claimed regression test is classified as one of:

1. **Behavior contract** — asserts observable runtime/user/API behavior. Requires an independent
   oracle and should survive behavior-preserving refactors.
2. **Artifact contract** — asserts exact source, generated output, migration text, schema, or config
   because that artifact itself is the contract. Must state why the exact representation matters.
3. **Structural contract** — asserts architecture or dependency constraints. Must cite the governing
   invariant and use an AST/schema/graph signal where practical instead of brittle substring copies.

A finding is raised when the claimed contract and test mechanism disagree, not merely because a test
opens a source file.

## Intended semantic delta

- `check` reports which changed tests are candidates for test-quality review; it does not pretend a
  regex can prove intent.
- `review` remains strictly read-only and consumes a targeted test-evidence packet whenever tests
  changed or a change claims regression coverage.
- The lane cites the exact invariant, test, and independent oracle.
- For behavior claims, the preferred proof is a safely isolated mutation run by a separate,
  explicitly invoked pre-review command; `/review` never performs the mutation.
- The root `rhize-review` skill becomes an adapter to the plugin's canonical contract rather than a
  richer divergent implementation.
- Durable standards include scope, rationale, provenance, owner, review date, and supersession; the
  plugin consumes existing `AGENTS.md`, `CLAUDE.md`, or repository standards without requiring a new
  `CODING_STANDARDS.md` file.

## Planned files

| Action | Path | Purpose |
|---|---|---|
| Create | `rhize-devflow/schemas/test-evidence-v1.schema.json` | Contract, oracle, and mutation result shape |
| Create | `rhize-devflow/docs/test-evidence.md` | Classification and safe mutation procedure |
| Create | `rhize-devflow/commands/test-evidence.md` | Explicit one-writer mutation runner that emits evidence for read-only review |
| Modify | `rhize-devflow/scripts/devflow.py` | Emit deterministic candidates and evidence fields |
| Modify | `rhize-devflow/commands/check.md` | Surface candidate test-quality gaps without overclaiming |
| Modify | `rhize-devflow/commands/review.md` | Consume/verify test evidence without changing its hard read-only contract |
| Modify | `skills/rhize-review/SKILL.md` | Follow the canonical plugin gate and remove drift |
| Create/modify | `tests/rhize-devflow/fixtures/test-evidence/` | Labeled behavior/artifact/structural examples |
| Create | `tests/rhize-devflow/test_test_evidence.py` | Schema, classifier, mutation, and cleanup coverage |
| Modify | `rhize-devflow/README.md`, `rhize-devflow/GUIDE.md` | User-facing rule and limits |

## Phases

### Phase 0 — Labeled corpus before heuristics

Build real or minimal deterministic fixtures for:

- a CSS substring test that falsely claims rendered behavior;
- an exact migration/config string that is the contract;
- a behavior test with an independent oracle;
- a test that passes before and after the exact bug is reintroduced;
- a structural rule better expressed through schema or AST evidence.

Acceptance:

- human labels include the claimed contract and why the oracle is or is not independent;
- no production repository result is counted as benchmark evidence unless captured by the eval;
- a raw `readFile`/`toContain` pattern alone cannot produce a blocking verdict.

### Phase 1 — Evidence schema and advisory detection

Add evidence fields for changed test files, related production files, declared invariant, contract
class, oracle, and review status. Candidate detection may use syntax patterns, but it remains
advisory until a reviewer confirms the contract mismatch.

Acceptance:

- artifact-contract fixtures are not mislabeled as behavior failures;
- evidence packets contain no commands sourced from prose;
- unchanged tests are not swept into a repository-wide speculative audit.

### Phase 2 — Separate mutation evidence and read-only review

When mutation evidence is authorized, `/test-evidence` attacks 1–3 explicit claims under an exclusive
one-writer window and emits `supported`, `survived_mutation`, `oracle_missing`, `artifact_contract`,
or `not_applicable`. It restores the checkout and ends with clean-tree verification before `/review`
starts. `/review` validates and consumes that packet but remains read-only; no review or test lane runs
against the checkout during the mutation window.

Acceptance:

- a surviving mutant blocks a claimed regression fix;
- a killed mutant records the exact behavior protected;
- mutation residue is caught by final `git status`/diff checks;
- `/review` performs no mutation, edit, commit, push, merge, deploy, or external write;
- recursive `/code-review` dispatch is forbidden.

### Phase 3 — Standards lifecycle

Document how a repeated failure becomes a durable rule: observation/repro, scoped wording,
independent verification, owner, creation date, review date, and supersession. Add linting for exact
duplicate or contradictory built-in rules before adding more prose.

Acceptance:

- the Matt Pocock rule is expressed as a scoped decision test, not a universal slogan;
- repository instructions override generic guidance when they explicitly define an artifact contract;
- stale/superseded rules remain traceable rather than silently disappearing.

### Phase 4 — Eval and promotion

Promote from advisory to blocking only if the labeled corpus shows acceptable precision and every
blocking class has reproducible mutation/counterexample evidence. Report precision/recall and
unreviewed candidates separately; never invent a composite quality score.

## Completion criteria

- Dev Flow distinguishes tests that protect behavior from tests that mirror implementation.
- Exact-artifact tests retain a documented valid path.
- Regression claims require an independent oracle or mutation evidence.
- The installed plugin and repo-root review skill share one canonical contract.
- Every mutation run restores the checkout and passes the final clean-tree gate.
