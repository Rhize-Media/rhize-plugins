# Parallel Routing Evaluation

This neutral harness evaluates two instruction variants against six deterministic task classes:

- `baseline` — standing host and fixture instructions only;
- `rhize` — the self-contained `rhize-ops:parallel-agent-optimization` strategy.

Each task/variant cell runs three times. Baseline and Rhize for the same task/repetition share a
random local comparison ID and run sequentially in counterbalanced order, using fresh copies from
the same fixture seed. This is isolated controlled evidence, not a production benchmark.

## Lifecycle

`prepare_run.py` writes `RUN_RESERVATION.json` with status `pending`. The runner writes a
privacy-safe provisional `receipt.json`; `grade_run.py` executes observable checks and always
finalizes the accepted reservation as `completed`, `failed`, or `incomplete`. Missing or malformed
runner metadata becomes an honest incomplete receipt instead of disappearing.

Example pair:

```bash
comparison_id="$(python3 -c 'import uuid; print(uuid.uuid4())')"
python3 evals/parallel-agent-skills/scripts/prepare_run.py \
  --task parallel-read --variant baseline --repetition 1 \
  --comparison-id "$comparison_id" --output /private/tmp/parallel-eval/parallel-read-baseline-1
python3 evals/parallel-agent-skills/scripts/prepare_run.py \
  --task parallel-read --variant rhize --repetition 1 \
  --comparison-id "$comparison_id" --output /private/tmp/parallel-eval/parallel-read-rhize-1
```

Run and grade the baseline directory before starting the Rhize directory. Generate all 36 cells
from the manifest, then aggregate:

```bash
python3 evals/parallel-agent-skills/scripts/aggregate_results.py \
  /private/tmp/parallel-eval \
  --json-output /private/tmp/parallel-eval/repeated.json \
  --markdown-output /private/tmp/parallel-eval/repeated.md
```

Keep evaluation output outside Git unless a reviewed evidence decision explicitly accepts it. The
scripts never generate production benchmark rows.

## Readiness contract

Required metrics are predeclared in `manifest.json`: complete paired coverage, correctness,
verification, routing, elapsed improvement, actual overlap, collisions, rework, and agent count.
Token/tool counts are optional: unavailable host counters stay null with an allowed reason and are
visible in the readiness report, but they do not block every decision.

Receipt fields cannot contain prompts, code, commands, source/repository paths, names, URLs,
session IDs, or issue IDs. Parallelism is derived from intersecting nested-agent intervals.

## Legacy screening archive

`results/2026-08-27-smoke.{json,md}` is the immutable one-cell, four-arm v1 screening result. It
includes ECC, Superpowers, and combined candidate arms from the pre-consolidation investigation.
It remains readable historical evidence but is non-comparable with v2, is never pooled into the
current decision report, and is not a runtime dependency or a production benchmark.
