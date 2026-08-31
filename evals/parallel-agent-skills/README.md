# Parallel Routing Evaluation

This neutral harness evaluates two instruction variants against six deterministic task classes:

- `baseline` — standing host and fixture instructions only;
- `rhize` — the self-contained `rhize-ops:parallel-agent-optimization` strategy.

The Rhize strategy validates its ephemeral dependency/resource graph before dispatch. Deterministic
graph fixtures under `fixtures/task-graphs/` cover parallel reads, shared resources, hidden writes,
partial fan-in, and layered fan-in. Runtime receipt v2 is owned under `rhize-ops`; this harness's
receipt schema is limited to isolated fixture lifecycle and grading fields.

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

## Isolated Superpowers guide comparison

`guide-comparison.manifest.json` defines a separate three-variant experiment over the same six
bounded task classes. Arm A is the standing host plus `TASK.md`; Arm B-superpowers is an exact
snapshot named `dispatching-parallel-agents`; Arm B-rhize is an exact snapshot named
`parallel-agent-optimization`. The preparation script requires explicit guide paths, validates
those identities, records their SHA-256 digests, and copies each into a fresh run directory. It
never hard-codes an installed path.

Each class runs three repetitions with a Latin rotation, so every variant appears once in each
order position. Complete each group sequentially in its recorded order. The validator compares
Superpowers and Rhize separately against the same baseline; it does not pool the two guide arms or
feed this evidence into canonical Rhize v2 readiness.

```bash
python3 evals/parallel-agent-skills/scripts/prepare_guide_comparison.py \
  --task parallel-read --repetition 1 --comparison-id "$(uuidgen | tr '[:upper:]' '[:lower:]')" \
  --superpowers-guide /explicit/path/to/dispatching-parallel-agents/SKILL.md \
  --rhize-guide rhize-ops/skills/parallel-agent-optimization/SKILL.md \
  --output /private/tmp/parallel-guide-comparison/parallel-read-1

python3 evals/parallel-agent-skills/scripts/validate_guide_receipts.py \
  /private/tmp/parallel-guide-comparison --require-complete-cohort
```

Receipts record the variant actually assigned plus correctness/accuracy, routing
precision/recall, exposed token categories, latency, tool calls, follow-up reads, corrections,
rework, failures, refusals, collisions, and factual agent intervals. Unknown counters stay null
with a declared reason. No receipts are shipped, and this live implementation lane is
observational context only—not causal comparison evidence.

The group reservation is authoritative: validation rejects context drift in task identity/class,
repetition, order, guide digest, isolation, mutation, or readiness boundaries, plus duplicate
task/repetition groups. Actual overlap, concurrent-agent milliseconds, maximum concurrency, agent
count, and collision totals are derived per variant from receipt intervals and counters; runners do
not submit those summary claims directly.

## Package skill coverage

`scripts/evaluate_ops_skills.py` runs the local/free routing and static quality contract for all
three rhize-ops skills. It gives each trigger-capable skill one positive plus at least two
near-miss/collision negatives. This deterministic gate is not presented as natural LLM trigger
evidence.
