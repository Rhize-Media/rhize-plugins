---
name: test-evidence
description: >-
  Classify changed regression tests as behavior, artifact, or structural contracts and produce or
  validate fail-closed, state-bound evidence metadata, with opt-in local Docker execution or an
  explicit unavailable status. Use before review
  when tests changed, a change claims regression coverage, or someone asks whether a test actually
  protects behavior. Do not route data/cache mutation consistency requests here.
metadata:
  rhize:
    tier: custom
    domain: dev-flow
    maturity: seedling
    topics: [review, evidence]
    stacks: [testing]
    extends: [dev-flow-foundations]
---

# Test Evidence

Classify each changed or claimed regression test as a behavior, artifact, or structural contract.
Read `../../docs/test-evidence.md` and use the host-neutral `../../scripts/test_evidence.py`; the
same files are canonical for Claude Code and Codex.

Start from `devflow.py evidence` and its advisory `test_evidence_candidates`. A candidate is not a
finding. Record the governing invariant and why the oracle is independent. Exact source assertions
remain valid artifact contracts when the representation itself is explicitly required.

For a behavior claim, prefer an independent oracle. Create a bounded run spec for one to three
explicit claims and invoke the runner to bind the claim to repository state. It refuses protected or
effectful canonical targets, every `.env*` form, symlink paths/parents, prose-derived commands, and
unapproved script names. It must never mutate or restore the user's live checkout.

Default execution remains unavailable. Explicit `--sandbox-image` with an existing full local
Docker image ID opts into the isolated adapter described in the contract; never pull an image or
install dependencies automatically. Use only trusted local Docker/image inputs. Python invocations
name an exact declared `.py` test file; no shell text is accepted. The adapter never runs host tests,
inherits candidate credentials, permits network, or mounts a writable host tree. Supported claims
require observed baseline/mutant/restored results and a private source-bound receipt. A declared
oracle alone is insufficient. Legacy execution claims remain unsupported; `cleanup_failed` returns `FAIL_REQUIRES_HUMAN`.
Review never executes, restores or retries. Keep packets and receipts local.

This skill is distinct from `data-mutation-consistency` and `/mutation-check`, which inspect cache,
CMS, and data-write consistency rather than mutation testing.

Optional [Skylos static evidence](../../docs/skylos-evidence.md) may flag assertion weakening or a
missing changed test. These are advisory candidates: an unrelated changed test can satisfy the
upstream heuristic. Record the governing invariant and independent oracle yourself. Scanner results
do not execute tests and cannot upgrade an unsupported execution status.
