# Rhize Context Manager skill evals

This directory adds deterministic, offline coverage for all shipped
`rhize-context-manager` skills. It complements `evals/context-tools/`: that directory
owns provider, context-pack, retrieval, receipt-health, and natural Arm A/B evidence;
this directory owns full skill routing/contract coverage and paired benchmark
specifications.

Run it with:

```bash
python3 evals/rhize-context-manager/run_evals.py
python3 evals/rhize-context-manager/run_evals.py --json
```

The runner makes no model, network, provider, paid, or live-mutation calls and writes no
receipt or result file. It validates four contracts:

1. Every curated routing keyword is still present in its live `SKILL.md`.
2. Every discovered skill has at least one positive case and two meaningful adjacent-
   skill or scope-collision negatives. The fixed substring classifier is only a
   deterministic frontmatter-distinctiveness check, not a claim about live model routing.
3. Every discovered skill has a static quality/ownership contract evaluated against the
   shipped skill text.
4. Every discovered skill has an explicit paired outcome benchmark specification. Arm A
   names the exact existing non-plugin path; Arm B names the plugin path. The common
   record/metric schema identifies the arm that actually ran and covers correctness,
   routing precision/recall, tokens by exposed category, latency, tool calls, follow-up
   reads, correction/rework, and failures/refusals.

## Natural evidence boundary

`benchmark_contracts.json` preserves the existing Context Manager evidence rules. Only
real, redacted receipts can become natural benchmark evidence. Fabricated receipts are
forbidden. A date-only row cannot establish strict ordering; incomplete or non-comparable
cohorts remain explicitly `indeterminate`; and missing measurements remain missing.
Specs in this directory authorize no capture, provider, network, or mutation run.

The `context-pack` spec binds to its existing deterministic `evals/context-tools` runner.
The binding is a contract reference, not a replacement runner: receipt validation,
assignment, privacy, capture health, and real-provider safeguards remain owned and tested
there.
