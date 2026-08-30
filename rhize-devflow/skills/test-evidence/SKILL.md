---
name: test-evidence
description: >-
  Classify changed regression tests as behavior, artifact, or structural contracts and produce or
  validate fail-closed, state-bound evidence metadata, including where safely isolated mutation evidence
  would be required. Use before review
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

The current runner has no trusted sandbox adapter and therefore never executes a package script or
calls its ambient process-runner boundary. It emits `execution_unavailable` for a clean checkout (or
`mutation_unavailable_dirty_state` for a dirty one), and `/review` must treat the packet as
unsupported. A declared oracle or artifact rationale cannot be promoted into `oracle_supported` or
`artifact_contract` without real sandbox execution. A future adapter must explicitly isolate
filesystem, network, secrets, processes, timeouts, and cleanup before execution-backed verdicts can
return. A stored legacy `cleanup_failed` returns `FAIL_REQUIRES_HUMAN`; review still performs no
restoration. Packets stay local and are never copied verbatim into Jira.

This skill is distinct from `data-mutation-consistency` and `/mutation-check`, which inspect cache,
CMS, and data-write consistency rather than mutation testing.
