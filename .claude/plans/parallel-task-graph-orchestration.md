# Parallel Task-Graph Orchestration

| Field | Value |
|---|---|
| Status | Proposed for review |
| Date | 2026-08-30 |
| Primary owner | `rhize-ops` |
| Planning/review tier | Sol |
| Recommended implementation tier | Terra for the contract and receipt migration; Luna for bounded fixtures and documentation |

## Decision

Extend `rhize-ops:parallel-agent-optimization` from prose-only lane planning to an inspectable,
ephemeral task-graph contract. Keep the host's agent tools as the executor. Do not build a second
scheduler, persist live task content in Neo4j, or treat agent count as evidence of parallelism.

The contract must model data dependencies and hidden shared-resource dependencies, bound fan-out,
verify every fan-in, and retain the skill's existing one-writer and privacy-safe receipt rules.

## Independent source review

The [0xWast3 graph-engineering article](https://x.com/0xWast3/status/2079899723947712845)
correctly emphasizes that many sequential steps have no data dependency and that shared files,
rate-limited APIs, context collapse, and missing node outputs are hidden edges. Its 40-call timing
example is arithmetic rather than a benchmark, its main Python snippet mixes the synchronous client
with `await`, and the title's 1,000-agent scale is not demonstrated. Adopt the dependency and fan-in
checks; reject the implied “scale is a config change” claim.

## Verified current state

- `parallel-agent-optimization` already separates `assess`, `apply`, `compare`, and `report`.
- `references/modes.md` already requires independent lanes, one writer per checkout, protected state,
  a join point, and coordinator-owned verification.
- `parallel_metrics.py` already derives interval overlap and keeps observational and controlled
  evidence separate.
- The eval harness already covers `parallel_read`, `disjoint_write`, `shared_state`,
  `dependency_chain`, `mixed_verification`, and `gated_live` shapes.
- Lane plans are still free-form prose. There is no machine-checkable DAG, shared-resource edge,
  fan-out budget, hierarchical fan-in rule, or expected-result completeness check.

## Intended semantic delta

Before dispatch, the skill renders a compact task graph whose nodes declare:

- an ephemeral node id and bounded deliverable;
- inputs and output contract;
- `dependsOn` node ids;
- read and write territories;
- shared resource pools, rate limits, approval gates, and external effects;
- timeout/concurrency budget and verification owner.

The graph validator derives five edge classes: `data`, `write_lock`, `resource_pool`, `approval`, and
`external_effect`. Only dependency-free ready nodes may overlap. A fan-in refuses to synthesize when
required results are missing, failed, or outside the declared output contract. Large result sets use
bounded, hierarchical fan-in rather than dumping every raw result into one context window.

The live graph may contain task descriptions and paths while executing, but it is never appended to
the receipt store. Receipts remain counts/timestamps/enums only.

## Scope and non-goals

In scope:

- pre-dispatch graph rendering and validation;
- bounded wave scheduling guidance for the host's real concurrency limit;
- completeness-aware and hierarchical fan-in;
- privacy-safe aggregate observations;
- fixtures that distinguish data independence from resource independence.

Out of scope:

- a durable distributed scheduler;
- provider-specific claims about hundreds or thousands of agents;
- automatic paid/API fan-out without effect-specific authorization;
- storing task prompts, paths, URLs, names, or node ids in telemetry;
- using CodeGraph, Graphify, or Neo4j to execute an ephemeral workflow DAG.

## Planned files

| Action | Path | Purpose |
|---|---|---|
| Create | `rhize-ops/skills/parallel-agent-optimization/references/task-graph-contract.md` | Human/runtime contract and examples |
| Create | `rhize-ops/skills/parallel-agent-optimization/references/task-graph-v1.schema.json` | Strict ephemeral graph shape |
| Create | `rhize-ops/skills/parallel-agent-optimization/scripts/validate_task_graph.py` | Dependency, resource, budget, and fan-in validation |
| Modify | `rhize-ops/skills/parallel-agent-optimization/SKILL.md` | Require graph validation before eligible dispatches |
| Modify | `rhize-ops/skills/parallel-agent-optimization/references/modes.md` | Wave, hidden-edge, and join semantics |
| Modify | `rhize-ops/skills/parallel-agent-optimization/references/receipt-contract.md` | Versioned aggregate completeness fields only |
| Modify | `rhize-ops/skills/parallel-agent-optimization/scripts/parallel_metrics.py` | Validate and report receipt v2 without task content |
| Modify | `tests/rhize-ops/test_parallel_agent_optimization.py` | Contract and migration coverage |
| Modify | `evals/parallel-agent-skills/` | Shared-resource, partial-fan-in, and layered-fan-in cases |
| Modify | `evals/parallel-agent-skills/manifest.json` | Remove the active `arm_ab` combined-arm definition |
| Modify | `evals/parallel-agent-skills/receipt.schema.json` | Reject new combined-arm receipts while preserving explicit legacy reads |
| Modify | `evals/parallel-agent-skills/scripts/aggregate_results.py` | Stop current comparisons from aggregating `arm_ab`; label historical rows legacy/non-comparable |
| Modify | `evals/parallel-agent-skills/README.md` | Document the one-resource-per-arm migration and archive boundary |
| Modify | `rhize-ops/README.md`, `rhize-ops/GUIDE.md` | Operator-facing behavior and limits |

## Phases

### Phase 0 — Freeze baselines and graph vocabulary

1. Record the current classifier/eval results and receipt schema version.
2. Define the five edge classes and prove each with one existing or new fixture.
3. Define the host concurrency budget as an input, never a hard-coded agent count.
4. Retire the active `arm_ab` manifest/schema/aggregator path. Preserve existing combined-arm result
   files as immutable legacy evidence, but never load them into a current comparison.

Acceptance:

- every edge class has a positive and negative fixture;
- a prose “and then” with no dependency produces no edge;
- two nodes writing the same territory or using a single-capacity resource do produce an edge.
- new evals expose only baseline, ECC, Superpowers, and Rhize as separate arms;
- historical `arm_ab` rows remain readable only as labeled legacy/non-comparable evidence.

### Phase 1 — Ephemeral validator

Implement strict JSON validation plus semantic checks for missing nodes, cycles, unresolved
dependencies, overlapping write territory, unowned verification, invalid approval placement, and
fan-out above the declared budget. Validation is read-only and writes no receipt.

Acceptance:

- invalid graphs fail before dispatch with a specific reason;
- valid parallel-read and mixed-verification fixtures produce deterministic ready waves;
- graph input containing paths/prompts is never copied into validation logs or receipts.

### Phase 2 — Completeness-aware execution guidance

Update `apply` so each wave declares expected node count and output shape. Require the coordinator to
check expected versus completed results before fan-in. Add layered fan-in when a declared context or
item budget would be exceeded. Partial synthesis is allowed only when the graph explicitly marks a
node optional and the output reports that omission.

Acceptance:

- one missing required node blocks synthesis;
- optional omissions remain visible;
- a large fixture compacts through at least two fan-in levels without exposing raw task content to
  telemetry;
- one-writer enforcement remains intact.

### Phase 3 — Receipt v2 and migration

Add only aggregate fields such as planned node count, required/completed count, failed count,
fan-in level count, declared concurrency cap, and observed maximum concurrency. Preserve v1 reads and
keep observational and controlled stores separate.

Acceptance:

- v1 receipts still validate and report;
- v2 rejects task ids, free text, paths, URLs, and unknown fields;
- interval overlap remains the only proof that work actually ran concurrently.

### Phase 4 — Bounded evaluation and release decision

Run replayable fixtures for linear dependency, true fan-out, hidden write contention, rate-pool
contention, missing result, and hierarchical fan-in. Do not duplicate a live task to manufacture a
comparison.

Promotion requires:

- zero missed hidden-resource collisions in the labeled fixtures;
- zero silent required-node omissions;
- full receipt privacy validation;
- measured elapsed-time improvement on at least one truly independent fixture without a correctness
  regression;
- no claim of 1,000-agent readiness without a separate host-supported load test.

## Completion criteria

- The task graph is inspectable, deterministic, and ephemeral.
- Every dispatch has a validated dependency/resource shape and one verification owner.
- Fan-in is bounded and completeness-aware.
- Receipts remain content-free and evidence classes remain separate.
- Documentation reports measured critical-path behavior, not headline agent counts.
