---
name: test-evidence
description: >-
  Classify changed regression tests as behavior, artifact, or structural contracts and produce or
  validate state-bound independent-oracle or safely isolated mutation evidence. Use before review
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

For a behavior claim, prefer an independent oracle. When the user has authorized isolated mutation
evidence, create a bounded run spec for one to three explicit claims and invoke the runner. It refuses
dirty state, protected/effectful targets, prose-derived commands, and unapproved scripts. It uses a
disposable worktree and exclusive lease; never mutate or restore the user's live checkout.

Only `oracle_supported` or `killed` supports a behavior-regression claim. `artifact_contract` supports
only the declared artifact invariant. `survived_mutation`, `oracle_missing`, unavailable, or stale
evidence blocks the claim. `cleanup_failed` returns `FAIL_REQUIRES_HUMAN`; do not attempt restoration
from `/review`. Packets stay local and are never copied verbatim into Jira.

This skill is distinct from `data-mutation-consistency` and `/mutation-check`, which inspect cache,
CMS, and data-write consistency rather than mutation testing.
