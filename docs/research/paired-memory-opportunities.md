# Paired memory opportunities: implementation and evidence

2026-09-06 (environment date). Release: context-manager 0.30.0 / marketplace 2.69.0.
Scope: native Claude/Codex opportunity measurement and a repeatable personal-work gauntlet.

## Decision

Require **both arms for every measurement-enabled task**. Collect opportunistic real-work
measurements alongside a small repeatable gauntlet to accumulate evidence faster. Retain direct
retrieval as the normal path: the measured catalog selector misses relevant sources on this corpus.
Do not promote catalog injection, procedural integration, or a replacement memory store yet.

The [earlier review and architecture plan](memory-awareness-benchmark.md) remains the source for
Hipocampus, the article, Skill Forge study `STUDY-0876539964f6cece`, and ownership boundaries.
This phase supersedes its no-measurement-hooks restriction under the user's subsequent explicit
authorization. The Skill Forge study is review-ready; this release does not impersonate human
approval or install upstream Hipocampus code, hooks or transcript capture.

## Delivered implementation

| Component | Behavior | Verification |
|---|---|---|
| Shared opportunity engine | Executes A/direct and B/catalog-selected expansion on the same canonical-document snapshot; no expected-answer selector oracle | Paired execution, failed-first, scope, duplicate/concurrent delivery and no-memory contracts |
| Native host entry points | SessionStart records model; prompt triggers a pair; tool/stop events update observations; event-specific thin launchers share one implementation | Real shell entry points for both host environments; native installation/trust verified separately |
| Answer worker | Same question/model, two fresh directories, subscription authentication, restricted tools/read-only execution, no production action replay | Actual Claude and Codex cohorts; failure/timeout, source drift, auth, lock and interrupted-claim contracts |
| Queue and health | One worker, 12 whole pairs per host/UTC day, 100-packet cap, lazy one-hour private-packet expiry, private modes, disable command | Budget boundary, interrupted recovery, expiry at zero budget and private-packet removal tests |
| Reports | Actual execution/variant, source coverage, catalog maintenance, estimated presentation size, native token usage, latency and explicit rubric outcomes | Complete-pair checks; missing usage stays null; host/model/corpus/implementation strata |
| Existing context experiments | Legacy shadow=false can no longer request a single arm | Assignment regression and existing evidence/finalization suite |

Native hooks remain observational. Neither successful Stop nor a retrieved pack is a correctness
measurement. Natural answer questions have no automatic correctness grade. Public curated cases
have explicit answer-term and source-citation rubrics. All required model calls use existing
subscriptions; CLI price estimates are not billed-cost measurements.

## Frozen final cohort

Ten curated cases were executed on each host: **20 complete pairs / 40 completed model answers**.
Every case ran A and B. Required-source IDs were available to the grader only, never the B selector.
The corpus represents recurring work categories; it is not a sample of historical completed tasks
and is not the held-out promotion corpus.

| Host / explicit model | A rubric passes | B rubric passes | Mean A total native input tokens | Mean B total native input tokens | Mean A answer ms | Mean B answer ms |
|---|---:|---:|---:|---:|---:|---:|
| Claude / claude-opus-4-8 | 10/10 | 8/10 | 2,895.4 | 2,292.6 | 4,337.4 | 4,157.7 |
| Codex / gpt-6-astra | 10/10 | 8/10 | 20,607.9 | 20,387.5 | 7,144.7 | 6,890.0 |

B missed the resume-state and unhelpful-heading sources on both hosts. Mean catalog-plus-detail
byte/4 estimate was **405.6 B vs 232.1 A**, including the local catalog overhead. The model receives
selected details; catalog selection is deterministic local keyword matching, not a second LLM
call. Thus lower model input does not imply lower all-in context cost or better answers.

Claude native input totals include auxiliary-model usage as well as the requested answer model.
Codex native input includes cached tokens already; Claude cache counters are added to uncached
input. Keep host strata separate. These short, sequential local runs do not establish population
latency, whole-task quality, production savings or non-inferiority. Descriptive bootstrap intervals
are emitted with a fixed seed; they are not a promotion certificate.

Exact evidence:

- [Claude final cohort](paired-memory-evidence/claude-final.json)
- [Codex final cohort](paired-memory-evidence/codex-final.json)
- [Development attempts, including incomplete captures](paired-memory-evidence/development-attempts.json)

Both final cohorts bind driver SHA-256
`e4adcaecacb95540ad8b7092917127986cebcb861676a0424c3e6a5da6331d9d`.
Corpus and retrieval implementation hashes are included in every result. Runtime hashes are
captured at module load so a long-running process cannot relabel its executing code after an edit.
Earlier development batches exposed an auxiliary-model attribution issue and a Codex advisory
event misclassified as a tool attempt; they remain separate from the final cohort and are not
silently rewritten as successful production evidence.

## Operation and activation

Follow the [paired-evaluation contract](../../rhize-context-manager/skills/memory-context/references/paired-evaluation.md)
for configuration, opt-out, health and explicit drain commands. Configuration is shared by both
hosts, but native hook trust and observed events are host-specific. The workspace allowlist reads
only bounded canonical files at the active task directory, without crawling descendants.

Current Codex supports native plugin hooks, contrary to older Rhize documentation. The official
[Codex hook documentation](https://learn.chatgpt.com/docs/hooks) describes plugin discovery and
host-controlled trust. Installing a package does not establish trust. Do not manufacture trust
hashes or use a trust-bypass flag. Explicit event/worker commands remain available for older hosts.

## Remaining advancement plan

1. Accumulate naturally triggered pairs and review answer correctness where an objective rubric
   exists. Track eligible-to-paired capture rate, unknown-model queues, source misses, incomplete
   pairs and per-host quota use. Natural observations and curated outcomes stay separate.
2. Develop a fallback or better catalog selector against development tasks; freeze its version
   before evaluation. The current keyword selector demonstrably misses relevant headings. Compare
   any replacement as a new B against the unchanged explicit A; never tune on held-out answers.
3. Run at least 30 disjoint held-out paired tasks per host before considering default use. Apply
   the earlier plan's privacy, stale-revision, correctness non-inferiority, total-cost and latency
   gates. An all-zero bootstrap alone cannot prove non-inferiority.
4. Only after those gates, implement the procedural runtime's metadata-only, scoped recall contract
   in its own repository. Reuse registry/digest/health; do not execute artifacts, refresh embeddings
   or parse procedural prose to imitate a supported adapter. Compare exact incumbent recall with
   candidate recall on both hosts before adoption.
5. Preserve existing ownership: claude-mem owns episodic capture, OpenWolf owns file indexes,
   CodeGraph owns code relations, and canonical documents/Obsidian own semantic facts. Hold RTK
   and Headroom settings fixed within a pair. No additional database, Graphiti substitution,
   transcript archive or upstream memory plugin is needed for these measurements.

Recommended execution tier: Terra for cross-cutting integration; the most capable available model
for design and skeptical review. This implementation used the current coordinator, with no source
delegation. Release checks and exact native activation status are recorded in the release task;
repository history is authoritative for publication.

## Verified lessons

- Requesting both arms must be a runner invariant, not an optional shadow setting or prose promise.
- A host can emit multiple model-usage entries without changing its primary answer model.
- A Codex `item.completed` advisory of type `error` is not a failed turn; require terminal turn and
  structured-answer evidence while rejecting actual tool attempts.
- Freeze implementation fingerprints at load time for long-running cohorts.
- Simple heading matching saved model input while reducing source coverage; retain A and keep B
  experimental until a measured correction passes the independent adoption gate.
