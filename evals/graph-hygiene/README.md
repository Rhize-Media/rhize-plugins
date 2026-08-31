# Graph hygiene evaluation

This suite verifies Rhize's candidate-only identity workflow independently of a live Neo4j database. It covers deterministic normalization, tenant/namespace/ACL/type/trust gates, poisoned and flooded inputs, compare-and-swap review leases, authorization, failure atomicity, logical projection and dependency-aware reversal, proposal-only watermarks, and privacy-safe quality reporting.

Run from the repository root:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s evals/graph-hygiene/tests -p 'test_*.py'
```

The labeled fixture is a deterministic contract corpus, not a calibrated Rhize production threshold. Tuning/held-out measurements, the internal proposal-only canary, and any automatic identity authority remain separate Jira gates.
