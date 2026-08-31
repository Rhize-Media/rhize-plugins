# Rhize Tasks evaluations

`run_evals.py` is the free, local deterministic gate for all six skills. It measures an explicit
phrase-routing contract across the package, so collision cases are evaluated together rather than
as six isolated keyword checks. Every skill owns at least one positive and two near-miss/collision
negatives. It also checks safety-critical workflow anchors in each canonical `SKILL.md`.

```bash
python3 evals/rhize-tasks/run_evals.py
```

This gate reports routing precision/recall and quality-contract coverage. It does not claim to
measure an LLM's natural trigger behavior, macOS integration, dashboard behavior, connector I/O, or
the user benefit of the skills. Those paths require isolated agent-mediated evaluation; the
controlled benefit protocol in this directory reserves and validates those runs without making a
live mutation or fabricating receipts.

`benefit-benchmark.json` defines exact Arm A and Arm B implementations, six bounded fixture task
contracts, three repetitions, counterbalanced order, and the common metric set. Use
`benchmark_contract.py reserve` before each pair and `benchmark_contract.py validate` afterward.
The validator can require the complete 18-pair cohort. No receipts or results are included here.
