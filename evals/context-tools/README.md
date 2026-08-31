# Context tools dogfood evals

These evals use the real pinned providers. Test-local doubles may exercise failure
branches, but they never generate benchmark rows and do not count toward adoption gates.

## Capture-health gate

Every live context experiment is evaluated separately from provider quality:

```bash
python3 rhize-context-manager/scripts/context_experiments/runner.py capture-health
```

The report validates the full receipt schema and model invariants, reconciles receipt history
with configured `completedRuns`, reports malformed receipt or pending files, separates
completed/incomplete Arm A and Arm B counts by capability, and flags failed, incomplete,
missing-arm, missing-metric, non-comparable, missing-history, and expired-pending captures.
A completed paired receipt needs at least one metric for each Arm and a shared metric
name/unit/evidence tuple. A healthy report exits `0`; actionable evidence loss exits `2`. Duplicate
failures can be grouped downstream for alerting, but the source report retains each affected
artifact. These tests verify the measurement pipeline only and never satisfy a provider
adoption gate.

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

Run the nine-case Phase 3 corpus against the checksum-verified upstream checkout:

```bash
python3 evals/context-tools/run_context_evals.py \
  --checkout /path/to/context-compiler \
  --output evals/results/context-tools/context-compiler-phase-3-real.json
```

The corpus uses the real provider over seven committed Python fixture repositories, the pinned
upstream repository, and this Rhize repository. It covers static aliases, duplicate-name
widening, dynamic dispatch, event decorators, callback registration, upstream self-analysis,
unsupported syntax, and real collision pressure. Each case runs twice in independent provider
processes and requires the same source-bound pack ID, stable manifest, and prompt content.

The `context-compiler-phase-3-v1` gate passed 9/9 cases on 2026-08-27. Both supported static
cases were accepted; the alias chain used 57 estimated Arm B tokens versus 87 for Arm A.
Duplicate names were accepted only after including both candidates and emitting a collision
warning. Dynamic, decorator, and callback fixtures omitted their hidden dependency but were
rejected to baseline with explicit reason codes; a repository containing invalid Python syntax
also failed closed. The real Rhize runner pack retained its required dependencies but was rejected after exceeding the
token, coverage, and collision budgets while detecting all three dynamic-edge classes.

Passing this gate permits Phase 4 provider-neutral design only. It proves adapter and guardrail
behavior, not improved coding outcomes.
Live-task receipts must separately measure correctness, follow-up reads, context tokens,
latency, and whether the compiled pack actually influenced the task.

## Native compiled context

Run the five language/risk cases plus three impact-assisted discovery cases:

```bash
python3 evals/context-tools/run_native_context_evals.py \
  --output /private/path/native-context-phase-4.json
```

The fixed cases cover TypeScript, JavaScript, Python, explicit mixed-language targets, and a
dynamic JavaScript import that must fall back. Three additional deterministic cases compare the
same baseline query with a repository-local impact-map hint, recording relevant-file recall,
critical misses, and measured build latency for both paths. The supported case must improve recall;
dynamic-import and unsupported-syntax cases must still reject use. Both arms run in every row: Arm A is the complete
supported-source baseline and Arm B is `rhize-native-context-pack-v2`. Every case compiles twice
and requires the same source-bound pack ID and prompt; no provider double produces benchmark data.

The original five cases passed `native-context-phase-4-v1`: four static packs were accepted,
the dynamic case was rejected with `dynamic_dependency_edge`, no critical entry was missing, and
the accepted cases had a 39.02% median estimated token reduction. Combined with the nine upstream
cases, the compiled-context decision corpus has 14 paired cases.

A real `rhize-plugins` explicit-target smoke accepted the provider implementation pack at 8,759
estimated Arm B tokens versus 680,703 for Arm A. A broad runner pack reduced tokens by more than
94% but rejected itself because of a dynamic edge. A query-discovered one-shot hook run then built
an accepted six-file pack before the next implementation slice. These results support only an
advanced opt-in pilot: task correctness and follow-up reads remain human-reviewed receipt fields,
and token reduction alone is not a default-enable signal.

`native-context-continuous-v2` keeps those five cases and adds the three baseline-versus-impact
cases. Its gate requires every assisted case to pass with zero assisted critical misses; measured
latency is reported but never converted into an outcome or correctness claim.

## mgrep

The first gate is the real CLI plus an independent local upload inventory:

```bash
python3 rhize-context-manager/scripts/context_experiments/runner.py \
  mgrep-preflight \
  --repo /absolute/path/to/rhize-plugins \
  --store rhize-dogfood-rhize-plugins
```

An unauthenticated CLI reports `completed: false` even though mgrep itself exits zero after
showing a login prompt. The 2026-08-27 economics/privacy gate stopped the managed pilot before
signup: Mixedbread's published free-tier data-use language is contradictory, and the local grepai
alternative then failed correctness non-inferiority. No account, token, store, or upload was
created. Managed mgrep remains rejected unless new terms or a paid approval materially change the
gate; the preflight code is retained only as auditable evaluation infrastructure.
