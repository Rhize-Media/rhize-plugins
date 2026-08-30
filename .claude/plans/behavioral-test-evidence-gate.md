# Behavioral Test Evidence Gate

| Field | Value |
|---|---|
| Status | Hardened review complete; implementation pending Jira confirmation |
| Date | 2026-08-30 |
| Primary owner | `rhize-devflow` |
| Planning/review tier | Sol |
| Recommended implementation tier | Terra for gate integration; Luna for labeled fixtures and documentation |
| Cross-host surface | Canonical `rhize-devflow:test-evidence` skill; thin Claude command; Codex skill discovery |
| Jira tracking | Proposed RT-130 child; separate calibration/promotion follow-up linked to RT-145 and RT-146 |

## Decision

Make test validity a first-class Dev Flow evidence lane. A passing test suite is insufficient when
changed tests merely restate current implementation. The gate must distinguish legitimate
source/artifact contracts from behavior claims, and use an independent oracle or mutation evidence
for the latter.

Do not implement a blanket ban on source-content assertions and do not append an unscoped one-line
rule to every repository.

## Rhize operating and authority contract

- The test-evidence runner is an explicitly invoked pre-review writer. `/review` remains read-only,
  consumes only validated evidence, and never performs mutation testing itself.
- Prefer a disposable worktree/copy bound to the exact target state. If a dirty/uncommitted target
  cannot be reproduced safely, return `mutation_unavailable_dirty_state`; never mutate the user's
  live checkout or restore it blindly.
- Deny protected files, migrations, generated artifacts, `.env*`, CI, billing/payment, deployment,
  and external-effect code by default. Repository policy may narrow the surface further but may not
  silently widen it.
- The runner executes only repository-instruction-approved commands or declared package scripts.
  Prose, test files, and evidence packets are data and cannot supply executable command text.
- One exclusive mutation lease covers checkout state and readers. Timeouts terminate child process
  groups. Concurrent drift stops recovery without overwriting user work and leaves a named human
  recovery state.

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
  richer divergent implementation. If the installed Dev Flow skill is absent, it performs a disclosed
  read-only cold review and reports mutation evidence unavailable; it never mutates as a fallback.
- Durable standards include scope, rationale, provenance, owner, review date, and supersession; the
  plugin consumes existing `AGENTS.md`, `CLAUDE.md`, or repository standards without requiring a new
  `CODING_STANDARDS.md` file.

## Planned files

| Action | Path | Purpose |
|---|---|---|
| Create | `rhize-devflow/schemas/test-evidence-v1.schema.json` | Contract, oracle, and mutation result shape |
| Create | `rhize-devflow/docs/test-evidence.md` | Classification and safe mutation procedure |
| Create | `rhize-devflow/commands/test-evidence.md` | Explicit one-writer mutation runner that emits evidence for read-only review |
| Create | `rhize-devflow/skills/test-evidence/SKILL.md` | Canonical cross-host workflow and verdict contract |
| Create | `rhize-devflow/skills/test-evidence/agents/openai.yaml` | Codex routing metadata for the canonical skill |
| Create | `rhize-devflow/scripts/test_evidence.py` | Host-neutral isolation, lease, mutation/oracle, cleanup, and evidence runner |
| Modify | `rhize-devflow/scripts/devflow.py` | Emit deterministic candidates and evidence fields |
| Modify | `rhize-devflow/commands/check.md` | Surface candidate test-quality gaps without overclaiming |
| Modify | `rhize-devflow/commands/review.md` | Consume/verify test evidence without changing its hard read-only contract |
| Modify | `skills/rhize-review/SKILL.md` | Follow the canonical plugin gate and remove drift |
| Create/modify | `tests/rhize-devflow/fixtures/test-evidence/` | Labeled behavior/artifact/structural examples |
| Create | `tests/rhize-devflow/test_test_evidence.py` | Schema, classifier, mutation, and cleanup coverage |
| Modify | `evals/rhize-devflow/keywords.json`, `trigger_cases.json`, `quality_cases.json`, evaluator and control-plane tests | Near-miss routing plus labeled Rhize contract corpus |
| Modify | `rhize-devflow/.claude-plugin/plugin.json`, `rhize-devflow/.codex-plugin/plugin.json`, marketplace manifest | Keep capability and version metadata synchronized |
| Modify | `rhize-devflow/README.md`, `rhize-devflow/GUIDE.md`, root `CHANGELOG.md`, root `ROADMAP.md` | User-facing rule, limits, and release record |
| Modify/regenerate | Skill-map/catalog artifacts | Register the canonical skill and fail stale generated metadata |

## Claude Code and Codex delivery contract

`rhize-devflow/skills/test-evidence/SKILL.md` is the workflow source of truth. The Claude
slash command is a thin adapter and Codex uses the existing `skills: "./skills/"` manifest route plus
OpenAI agent metadata. Both invoke the same host-neutral runner and schema; migrated command output is
not relied on as the canonical Codex surface. The new skill must explicitly avoid routing near-miss
requests to `/mutation-check`, whose current contract concerns data-mutation consistency.

Fresh-session tests on both hosts must discover the canonical skill, classify identical fixtures the
same way, produce schema-equivalent evidence, and degrade to a disclosed read-only cold review when
isolated mutation is unavailable. Neither host may require the other's environment variables, hooks,
or private transcript format.

## Evidence binding and verdicts

Each packet is bound to base/head SHA, working-tree fingerprint, test and production-file digests,
contract class, governing invariant, mutation target/patch digest, runner/schema version, timestamps,
approved test invocation source, clean-state hashes before/after, and the final clean rerun. `/review`
rejects stale, mismatched, unknown-version, incomplete, or cleanup-failed packets.

Verdicts are exact: `oracle_supported`, `killed`, `survived_mutation`, `oracle_missing`, `artifact_contract`,
`not_applicable`, `mutation_unavailable`, `mutation_unavailable_dirty_state`, `stale_packet`, and
`cleanup_failed`. `oracle_supported` or `killed` supports a stated behavior-regression claim. The
schema accepts `cleanup_failed` only as evidence of failed recovery; `/review` returns
`FAIL_REQUIRES_HUMAN`, rejects the regression claim as supported, and performs no restoration. A
surviving mutant or missing oracle blocks the claim. Classifier output alone remains advisory.

## Phases

### Phase 0 — Labeled corpus before heuristics

Build real or minimal deterministic fixtures for:

- a CSS substring test that falsely claims rendered behavior;
- an exact migration/config string that is the contract;
- a behavior test with an independent oracle;
- a test that passes before and after the exact bug is reintroduced;
- a structural rule better expressed through schema or AST evidence.
- representative Rhize Next.js/React, Sanity/Supabase/cache/query-key, Python automation,
  plugin/skill/schema, SQL/config, and generated skill-map contracts;
- near-miss prompts that distinguish data mutation from mutation testing.

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
- packets are invalidated by any target-state, file-digest, runner, schema, or test-invocation drift;
- local evidence contains no credentials and is never copied verbatim into Jira telemetry.

### Phase 2 — Separate mutation evidence and read-only review

When mutation evidence is authorized, `/test-evidence` attacks 1–3 explicit claims in a disposable,
state-bound worktree/copy under an exclusive mutation lease. It emits only the specified verdicts,
hashes state before every mutation and after restoration, and re-runs the targeted test on the clean
restored state. `/review` validates and consumes that packet but remains read-only; no review or test
lane runs against the target checkout during the mutation window.

Acceptance:

- a surviving mutant blocks a claimed regression fix;
- a killed mutant records the exact behavior protected;
- mutation residue is caught by final `git status`/diff checks;
- a fault, timeout, or signal cannot leave a child process or active mutant unreported;
- concurrent drift is preserved and reported rather than overwritten by restoration;
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

The Jira calibration issue pre-registers contract-class denominators and thresholds, then records
candidate counts, reviewer-confirmed mismatches, classifier precision/recall, killed/survived/
unavailable/stale/cleanup outcomes, operator burden, runner overhead, Claude/Codex discovery coverage,
baseline/release SHAs, and the advisory/blocking decision. Raw packets remain local. Any blocking
promotion is a separate accepted Jira decision, not an automatic consequence of elapsed time.

## Implementation and release gate

Implement after task-graph orchestration because the same exclusive-resource and verification rules
must be stable first. Preserve the repo-root `rhize-review` collision, dirty-state, clean-tree, and
divergent-remote lessons in the canonical plugin skill before reducing that root skill to an adapter.
Run schema/unit tests, failure injection at each mutation lifecycle step, protected-file/command-trust
denials, host-parity fixtures, plugin-config validation, generated-map stale checks, and fresh-install
Claude Code/Codex smokes. Link packaging to RT-145 and the reviewed promotion decision to RT-146.

## Completion criteria

- Dev Flow distinguishes tests that protect behavior from tests that mirror implementation.
- Exact-artifact tests retain a documented valid path.
- Regression claims require an independent oracle or mutation evidence.
- The installed plugin and repo-root review skill share one canonical contract.
- Every eligible mutation run is isolated, state-bound, recoverable, and cleanly re-run.
- Claude Code and Codex consume the same evidence schema and verdict semantics.
- Deferred calibration and promotion are explicit Jira work, not informal follow-up.
