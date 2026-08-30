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
