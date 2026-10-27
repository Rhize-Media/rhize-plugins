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

## Private real-task inputs and independent review

Reuse the controlled gauntlet with `--corpus /private/tasks.json --rubrics /private/grading.json`.
The separate task file contains only `schemaVersion: 1`, `name`, `provenance` and `cases`. Each case
contains `id`, `question`, and `sources`; each source contains only `id`, `heading`, and `body`.
Grader/answer fields in task inputs are rejected before provider execution. Use approved source
excerpts from actual work, keep their provenance privately, and never commit private corpus files.

The grading file contains `schemaVersion: 1`, `corpusHash` (SHA-256 of the exact task-file bytes), a
nonempty, predeclared `decisionRule`, and `cases` matching task IDs exactly. Each grading case has
`id`, `rubric` and `reviewCriteria` (a nonempty list of semantic review checks). The rubric accepts
`requiredTerms`, `forbiddenTerms`, `requiredSourceIds` and `expectedAbstention`; required sources
must belong to that case. Grade inputs never enter the native question/evidence prompt. Hashes
retain the task/grading binding and decision rule in the run report. This is operator-declared
chronology, not authenticated proof that the rule was chosen prospectively.

With `--retain-review`, private packets include the original shared source evidence and semantic
review checks. Opaque response labels conceal the arm mapping; the run report retains that mapping
separately. Give reviewers only the review packets. Do not give them the run report. This is
concealment by export, not independently verified blindness. Reported end-to-end elapsed time
includes retrieval, native answers and local report work; refresh cost stays null unless measured
separately. Native usage stays null when unavailable rather than becoming zero.

Retain human or model review separately with:

```bash
python3 evals/memory-context/review_pilot.py --run /private/run.json \
  --review-dir /private/run-review --reviews /private/reviewer-one.json \
  --reviews /private/reviewer-two.json --output /private/imported-reviews.json
```

Each review file has `schemaVersion: "memory-pilot-review-v1"`, `runSha256` (exact run-file bytes),
`reviewerId` (safe ID), `basis` (`human` or `model`), and `reviews`. Each review item contains:

```json
{"packetSha256":"<exact packet hash>","responseId":"response-1","correctness":null,
 "materialOmissions":[],"unsupportedClaims":[],"correction":null,
 "abstentionAppropriate":null,"notes":"Review pending"}
```

`correctness` and `abstentionAppropriate` are boolean or null. Omissions and unsupported claims are
lists of nonempty strings; correction is text or null. Import validates exact run/packet/answer
bindings and opaque response labels, refuses duplicate reviewer/response records and retains
disagreements. Reviewer identity and basis are declarations, not authentication. No import grants
human acceptance, changes routing, promotes a skill or overwrites the original run.

The optional preview `--requirements` source checklist is documented in the memory-context skill's
[evidence completeness reference](../../rhize-context-manager/skills/memory-context/references/evidence-completeness.md).
Its report changes neither core assembler bytes nor ranking, and has separate contract tests.

For a distinct full-source comparison, `export_raw_control.py --corpus /private/tasks.json
--rubrics /private/grading.json --output /private/raw-control.json` prepares all admissible source
records without selection budgets. This is a separate offline control; Arm A remains the bounded
legacy assembler and Arm B remains awareness selection. The export retains exact corpus/snapshot
bindings, source hashes, source/input bytes, measured construction time, and a byte/4 token estimate.
It refuses inputs exceeding the existing native driver's 64,000-byte prompt ceiling rather than
silently truncating evidence. It preserves scope/sensitivity admission. Model calls, quality and
refresh cost remain unobserved, and the export cannot establish a raw-source answer-quality result.
