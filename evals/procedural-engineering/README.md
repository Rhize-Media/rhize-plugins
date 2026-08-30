# Procedural engineering evidence baseline

`baseline-2026-08-30.json` freezes the pre-implementation state used by the
procedural-engineering evidence-gates plan. It contains identifiers, schedules, hashes,
evidence locations, and cohort classifications only. It intentionally excludes source
bodies, prompts, credentials, DSNs, and customer content.

Validate it with:

```bash
python3 evals/procedural-engineering/validate_baseline.py \
  evals/procedural-engineering/baseline-2026-08-30.json
```

Historical rows are never upgraded in place. The `strictComparable` count is derived from
the receipt contract active at capture time; legacy activity remains visible under
`observedRows` and its exclusion reason.
