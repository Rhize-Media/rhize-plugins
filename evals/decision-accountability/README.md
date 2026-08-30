# Decision accountability deterministic evaluation

This corpus verifies the offline decision-accountability contract before any Neo4j publication or
natural decision capture. It contains only synthetic hashes and opaque Rhize-internal references.

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s evals/decision-accountability/tests -p 'test_*.py'
```

The fixed fixtures exercise deterministic policy reproduction, strict source/evidence/policy/
approval/effect/outcome/correction separation, preview expiry and replay denial, CAS/idempotency,
failure atomicity, ACL/tenant denials, conservative causality, bounded queries, purge behavior, and
the optional PROV-O interoperability view. They do not capture client data, natural decisions, live
Neo4j results, or promotion evidence.
