# Provenance — parallel-agent-optimization

The machine-readable ledger entry is `../../SOURCES.md#parallel-agent-optimization--2026-08-30`.
The user authorized consolidation on 2026-08-30. The sources are attribution and update-review
inputs, not runtime dependencies.

| Source | Installed version | Skill SHA-256 | License |
| --- | --- | --- | --- |
| ECC `parallel-execution-optimizer` | 2.2.0 | `b44def0f7c24ab2505bd2eee10ceb777d591724dbe32dfdf5220354385e1e3ab` | MIT, Copyright 2026 Affaan Mustafa |
| Superpowers `dispatching-parallel-agents` | 6.3.0 | `1968923066f3b707eb01d1992cdf4c42284c3855f70253b9cd5000ff45fca13c` | MIT, Copyright 2025 Jesse Vincent |

Source URLs:

- https://github.com/affaan-m/ECC/tree/main/skills/parallel-execution-optimizer
- https://github.com/obra/superpowers/tree/main/skills/dispatching-parallel-agents

## Consolidated practices

- From ECC: explicit dependency graphs/lane matrices, batching independent checks, deliberate
  polling, blocker propagation, isolated write surfaces, and verification-first reporting.
- From Superpowers: one independent domain per agent, focused self-contained briefs with scope,
  constraints and required output, plus coordinator review/conflict checking/full-suite integration.
- Rhize retains its existing eligibility gate, protected-state and one-writer rules, true interval
  overlap, lifecycle receipts, observational/controlled separation, and privacy boundary.

The Rhize prose is a concise implementation of these high-level practices; it does not vendor the
upstream skills or their examples. Historical candidate and combined-arm v1 smoke remains archived
as non-comparable screening evidence. New runtime and controlled execution never load either
source and never create an ECC+Superpowers arm.

## Drift boundary

The existing `ai-stack-version-drift` scheduled review is the sole version sensor. It may compare
installed versions and skill digests above and open a human review when a source changes. A source
update does not change runtime behavior automatically and does not require reintroducing a
dependency or candidate arm. Do not add another scheduler.
