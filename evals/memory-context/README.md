# Memory-context deterministic evaluation

The paired fixture is fed to the same host-neutral runner for Claude Code and Codex. Tests freeze
the timestamp and assert byte-equivalent manifests, conflict preservation, inert untrusted content,
scope denial, unavailable adapters, TTL, source revision invalidation, and exact-source purge.

The graph fixture drives the same adapter and assembler path for Claude Code and Codex against the
governed in-memory Neo4j contract. It adds tenant/ACL denial, compilation and provenance drift,
bounded results, contradiction grouping, inert poison content, unavailable-store, and purge cases.
No evaluation opens a database connection, accepts Cypher, or mutates graph state through the memory
adapter.

This corpus is deterministic contract evidence only. It is not operational retrieval evidence and
must not be pooled with later host/model task outcomes.

```bash
python3 -m pytest -q evals/memory-context/tests
```

The opt-in awareness tests add catalog-before-detail disclosure, exact duplicate/present-source
bindings, digest and authority binding, combined presentation budgets, denial, stale/revoked packs,
conflict preservation, and real CLI round trips. A component comparison executes both arms:

```bash
python3 evals/memory-context/run_awareness_benchmark.py --seed 130 --repeats 20 \
  --output /absolute/private/awareness-component.json
```

Arm A is pinned to the unchanged legacy assembler at `e184246a5d325320126b18f6d3906b1d921fc025`;
the harness refuses drift. Arm B runs catalog, private persistence, verification and expansion with
explicitly **oracle-selected** source IDs. Both arms actually execute, in seeded randomized order,
over long, short, no-memory-needed, sparse, contradictory and scoped/poisoned corpora. An additional
empty-memory control actually runs. Reports include source hashes, input bytes, local latency,
source coverage and rendered byte/4 token estimates. This is not proof of agent selection quality,
instruction-injection resistance in a model, billable cost savings, or host integration.

Use the [implementation plan and live protocol](../../docs/research/memory-awareness-benchmark.md)
for exact baseline confirmation, held-out task rubrics, measured maintenance cost and advancement
gates. Synthetic reports must not enter real reserve/finalize receipts.

## Personal-work paired gauntlet

`run_gauntlet.py` runs all ten cases from `gauntlet.json`; no single-arm mode exists. Supply
`--host host-neutral --output /private/path/retrieval.json` for a local mechanism check. For actual
answers, supply `--host claude --model <exact-model> --answers` or `--host codex --model <exact-model>
--answers`, with a unique `--output`. `--case <id>` restricts cases but never arms. Existing
subscription login is required; API-key fallback is disabled. These calls consume subscription quota.

The corpus is curated from recurring personal-work categories. Heading extraction and keyword
selection never see required answers or source IDs. Rubrics combine answer terms and required
source citations; they measure bounded answer behavior, not complete production tasks. Captured
JSON includes every attempted arm, actual native usage, source coverage, hashes and per-host/model
aggregates. Auxiliary Claude model usage is included; Codex usage comes from its terminal turn.
Cached token accounting differs by host and is normalized in `totalInputTokens`.

Natural opportunities use the same engine through native hooks. Follow the
[configuration and interpretation contract](../../rhize-context-manager/skills/memory-context/references/paired-evaluation.md).

## Controlled quality pilot

`pilot-2026-09.json` is a three-case calibration corpus (release evidence, superseded policy,
absent information). It is newly curated, not historical production evidence or a held-out main
study. Keep it separate from natural receipts and the older ten-case gauntlet.

Real answers now require `--baseline-commit <confirmed-incumbent-sha>`. The runner checks that the
incumbent assembler matches those exact Git bytes before spending any calls. `--repetitions 3`
alternates A/B answer order. `--max-answer-calls 27` caps the declared calls before execution;
`--empty-control` adds an after-pair empty-evidence probe graded for abstention, not an additional
incumbent. Do not use its always-after position for a latency comparison. No automatic retry
changes a failed trial into a pass. All reservations exist before execution; each trial updates
the report so interruptions remain visible.

Use `--retain-review` only for an explicitly selected, shareable corpus. It saves 0600 full-answer
packets in a sibling 0700 directory, labels responses opaquely for blinded review, and keeps the
arm mapping in the run report. Delete that explicitly selected review directory after its agreed
review period; passive natural capture continues to retain answer hashes only. Term/source grades
are versioned, record rubric hashes and each check, and leave independent semantic review pending.
An empty rubric is invalid. Negative grader fixtures prove wrong answers, missing citations and
unsupported answers do not silently pass.

Example (each host gets its own report, model pin and subscription quota):

```bash
python3 evals/memory-context/run_gauntlet.py --host claude --model <exact-model> --answers \
  --corpus evals/memory-context/pilot-2026-09.json --repetitions 3 \
  --baseline-commit <user-confirmed-sha> --retain-review --empty-control \
  --max-answer-calls 27 --output /absolute/private/claude-pilot.json
```

Use the same corpus, baseline, repetitions and limits with `--host codex` and its explicit model.
Judge quality within each host. Different native host overhead and unrelated task samples cannot
support a model ranking. Pilot results establish measurement feasibility and reveal failure cases;
choose a separate main-study corpus and sample size from the desired precision before running it.
