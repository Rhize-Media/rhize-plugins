# Graph ontology contract evaluation

This suite exercises the offline release contract. The corpus uses synthetic labels and redacted
paths; it is not evidence of a live Neo4j deployment or a production canary.

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s evals/graph-ontology/tests -v
```

The tests cover deterministic ontology generation, extension isolation, Graphify translation,
tenant-safe identities, source provenance, parallel evidence, hyperedges, poisoned content,
CodeGraph reference drift, role separation, idempotent stage/publish, optimistic races, query
budgets, cross-tenant non-disclosure, purge, backup, restore, privacy-safe receipts, and host-neutral
CLI output. RT-159 separately owns driver integration, a real internal corpus, backup/RPO/RTO
evidence, live failure injection, and the promote/hold decision.
