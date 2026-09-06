# Memory-context deterministic evaluation

The paired fixture is fed to the same host-neutral runner for Claude Code and Codex. Tests freeze
the timestamp and assert byte-equivalent manifests, conflict preservation, inert untrusted content,
scope denial, unavailable adapters, TTL, source revision invalidation, and exact-source purge.

The graph fixture drives the same adapter and assembler path for Claude Code and Codex against the
governed in-memory Neo4j contract. It adds tenant/ACL denial, compilation and provenance drift,
bounded results, contradiction grouping, inert poison content, unavailable-store, and purge cases.
No evaluation opens a database connection, accepts Cypher, or mutates graph state through the memory
adapter.

This corpus is deterministic contract evidence only. It is not operational retrieval evidence and
must not be pooled with later host/model task outcomes.

```bash
python3 -m pytest -q evals/memory-context/tests
```

The opt-in awareness tests add catalog-before-detail disclosure, exact duplicate/present-source
bindings, digest and authority binding, combined presentation budgets, denial, stale/revoked packs,
conflict preservation, and real CLI round trips. A component comparison executes both arms:

```bash
python3 evals/memory-context/run_awareness_benchmark.py --seed 130 --repeats 20 \
  --output /absolute/private/awareness-component.json
```

Arm A is pinned to the unchanged legacy assembler at `e184246a5d325320126b18f6d3906b1d921fc025`;
the harness refuses drift. Arm B runs catalog, private persistence, verification and expansion with
explicitly **oracle-selected** source IDs. Both arms actually execute, in seeded randomized order,
over long, short, no-memory-needed, sparse, contradictory and scoped/poisoned corpora. An additional
empty-memory control actually runs. Reports include source hashes, input bytes, local latency,
source coverage and rendered byte/4 token estimates. This is not proof of agent selection quality,
instruction-injection resistance in a model, billable cost savings, or host integration.

Use the [implementation plan and live protocol](../../docs/research/memory-awareness-benchmark.md)
for exact baseline confirmation, held-out task rubrics, measured maintenance cost and advancement
gates. Synthetic reports must not enter real reserve/finalize receipts.
