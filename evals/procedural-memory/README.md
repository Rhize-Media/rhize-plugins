# Procedural-memory deterministic evaluations

The existing `procedural-memory/evals/` suite remains the canonical agent-eval suite; native runs became available
in September 2026. See that directory's README for version-stamped results and sandbox limits. This directory adds a free local collision contract for both discovered skills:
`procedural-memory` and `functionize`.

```bash
python3 evals/procedural-memory/run_evals.py
python3 procedural-memory/evals/validate-suite.py --eval-dir procedural-memory/evals
```

Every skill has a positive and at least two meaningful negatives. Static quality checks cover the
registry digest/trust boundary and Functionize's compile-only proposal boundary. These checks do
not run an artifact, read real shell history, compile a proposal, or claim natural agent-trigger
accuracy.
