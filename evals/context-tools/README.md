# Context tools dogfood evals

These evals use the real pinned providers. Test-local doubles may exercise failure
branches, but they never generate benchmark rows and do not count toward adoption gates.

## Local semantic retrieval

The paired retrieval runner executes real scoped ripgrep searches as Arm A and real local
grepai searches as Arm B-local:

```bash
python3 evals/context-tools/run_retrieval_evals.py \
  --output evals/results/context-tools/retrieval-phase-1.5-real.json
```

grepai is pinned to `0.35.0`; its Ollama model is `nomic-embed-text:v1.5` with manifest
digest `0a109f422b47e3a30ba2b10eca18548e944e8a23073ee3f3e947efcf3c45e59f`.
The runner requires a current `.grepai/rhize-snapshot.json` marker and the adapter doctor;
an installed binary or non-empty GOB file is not enough.

Do not run `grepai watch` in a real main worktree. Version 0.35.0 automatically initializes
and indexes every registered linked worktree and exposes no supported opt-out. With the current
adapter, build the index only in a detached single-worktree disposable clone, verify the source
manifest/snapshot, wait for the foreground scan to complete, and then stop it. A non-Git mirror
would be safer still but is not supported by this adapter yet.

The first real six-case run on snapshot
`d95c8a8d5a234696cbb0df1f64a8ca06a0c3dede` failed the continue gate:

| Provider | Mean recall@5 | Mean precision@5 | Critical misses | Median query time |
|---|---:|---:|---:|---:|
| Arm A — ripgrep | 1.0 | 0.466667 | 0 | 41.444 ms |
| Arm B-local — guarded grepai adapter | 0.166667 | 0.1 | 5 | 534.875 ms |

The grepai timing is end to end and includes the adapter's pinned-provider, local-model,
inventory, and snapshot checks because that guarded path—not a direct CLI shortcut—is what a
live experiment would execute.

The corpus is a smoke set, not the final adoption corpus, but a critical miss is already a
stop condition. The report records the versioned gate result as `pause`, with
`candidate_has_critical_misses` and `candidate_recall_below_baseline`. `localRetrieval`
therefore remains disabled and unarmed; these rows must not be reframed as a successful live
experiment.

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
