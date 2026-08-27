# Parallel-Agent Skill Evaluation

This harness compares four instruction variants against six deterministic task classes:

- `baseline` — neither candidate loaded;
- `arm_a` — ECC `parallel-execution-optimizer`;
- `arm_b` — Superpowers `dispatching-parallel-agents`;
- `arm_ab` — both candidates, with load order recorded per run.

The evaluator copies one task fixture into an isolated temporary directory, then an independent
agent completes `TASK.md` and writes `receipt.json`. `grade_run.py` checks observable outcomes and
keeps routing quality separate from task correctness.

## Prepare and grade

```bash
python3 evals/parallel-agent-skills/scripts/prepare_run.py \
  --task parallel-read --variant baseline --output /private/tmp/parallel-eval/parallel-read-baseline

python3 evals/parallel-agent-skills/scripts/grade_run.py \
  /private/tmp/parallel-eval/parallel-read-baseline
```

After all 24 cells are graded, create the privacy-safe aggregate:

```bash
python3 evals/parallel-agent-skills/scripts/aggregate_results.py \
  /private/tmp/parallel-eval \
  --json-output evals/parallel-agent-skills/results/smoke.json \
  --markdown-output evals/parallel-agent-skills/results/smoke.md
```

The aggregate derives actual parallelism from overlapping nested-agent timestamps. A parallel
decision or an agent count greater than one is not treated as proof of concurrency.

The harness never stores prompt text, source-repository paths, user content, secrets, or raw agent
messages in aggregate receipts. Token and tool-call fields must be `null` with an availability
reason when the host cannot expose authoritative counters.

## Boundaries

- All agent writes stay inside the prepared run directory.
- Candidate skills are read from their installed plugin paths; they are not copied or edited.
- The production-gate fixture is simulated and has a protected hash checked by the grader.
- This harness does not create a scheduler, wrapper skill, or production integration.
