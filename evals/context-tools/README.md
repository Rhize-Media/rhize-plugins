# Context tools dogfood evals

These evals use the real pinned providers. Test-local doubles may exercise failure
branches, but they never generate benchmark rows and do not count toward adoption gates.

## Context Compiler

Run both current cases against the checksum-verified upstream checkout:

```bash
python3 evals/context-tools/run_context_evals.py \
  --checkout /path/to/context-compiler \
  --output evals/results/context-tools/context-compiler.json
```

The upstream self-case is the supported static-import control. The Rhize runner case is a
real collision-pressure case from this repository; it must retain its required local
dependencies while the injection policy rejects an over-broad or over-budget pack.

Passing these cases proves adapter and guardrail behavior, not improved coding outcomes.
Live-task receipts must separately measure correctness, follow-up reads, context tokens,
latency, and whether the compiled pack actually influenced the task.

## mgrep

The first gate is the real CLI plus an independent local upload inventory:

```bash
python3 rhize-context-manager/scripts/context_experiments/runner.py \
  mgrep-preflight \
  --repo /absolute/path/to/rhize-plugins \
  --store rhize-dogfood-rhize-plugins
```

An unauthenticated CLI reports `completed: false` even though mgrep itself exits zero after
showing a login prompt. Once authenticated, the vendor dry-run may create or retrieve the
named remote store, but it does not upload file content. Repository upload remains a later,
explicitly confirmed action based on the reviewed manifest.
