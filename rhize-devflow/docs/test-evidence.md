# Behavioral test-evidence contract

`test-evidence` is an explicitly invoked pre-review writer. It classifies a claimed test contract,
binds evidence to an exact Git state, and—only when an approved package test script and safe fault
are supplied—runs the fault in a disposable worktree under an exclusive lease. `/review` validates
and consumes the packet but remains read-only.

## Classes and verdicts

- **Behavior**: requires an independent oracle or a killed mutant. `survived_mutation` and
  `oracle_missing` block a regression claim.
- **Artifact**: exact text/schema/config is the contract and must include its scoped rationale.
  It produces `artifact_contract`, not a behavior claim.
- **Structural**: cites an architecture invariant and should use AST/schema/graph evidence.

The complete verdict vocabulary is defined in `schemas/test-evidence-v1.schema.json`. A stale or
unknown packet is rejected. `cleanup_failed` always maps to `FAIL_REQUIRES_HUMAN`; review performs no
restoration.

## Safety and recovery

The runner refuses dirty targets, protected files, migrations, generated output, deployment files,
billing/payment code, `.env*`, and declared external effects. It accepts only a named `test` or
`test:*` package script from that repository's own `package.json`; command text in prose, test files,
or packets is never executable input. It starts a child process group, terminates the group on
timeout, restores and cleanly reruns the test, verifies the disposable tree, and removes the
worktree. If cleanup cannot be proven, the packet names human recovery rather than overwriting
concurrent state.

Packet output and lease files must live outside the target repository. Packets bind both the live
checkout's initial/final fingerprint and the disposable worktree's pre-mutation/post-restoration
fingerprints; a changed or incomplete binding is not accepted as regression evidence.

Packet paths and digests remain local. Jira receives only aggregate counts, version/SHA references,
and the promotion decision—never the packet, invariant prose, source content, credentials, or paths.

## Standards lifecycle

A durable rule records the observation/reproduction, narrow scope, rationale, provenance, owner,
creation date, review date, and supersession link. Existing repository instructions can explicitly
declare an artifact contract. Do not create a second standards file or append an unscoped slogan.
