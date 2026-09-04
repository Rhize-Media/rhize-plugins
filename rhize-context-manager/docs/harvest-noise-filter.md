# Harvest noise filter

Deep reference for `scripts/harvest_noise_filter.py` (repo root), the content-dedupe step
`/learn-harvest` runs before it appends anything to the refinement queue. See the README's
Commands section for the one-line summary and when you'd reach for this.

## Why it exists

Queue entry ids are `sha1-12(source + pattern)`, so **a rephrasing of an already-known
fact produces a new id and walks past id-dedupe**. Measured on 2026-08-14: 3 of 5
headroom entries restated facts folded into CLAUDE.md on 2026-08-12, and the two largest
`est_savings` claims (235k, 45k) were the two most duplicative — roughly 30% of a day's
yield spent re-litigating settled facts.

## How it scores a candidate

Step 7 of `/learn-harvest` runs this filter, which matches on content instead of hash.
Each candidate is scored by greedy set-cover: what fraction of its normalized content
tokens are covered by up to `--max-blocks` (default 3) reference blocks, drawn from
existing queue patterns (**any** status) and the files passed via `--reference`. As of
2026-09-04 the reference set is `CLAUDE.md`, `~/.claude/CLAUDE.md`,
`docs/session-guardrails.md`, and the invoking project's auto-memory `MEMORY.md`
(`~/.claude/projects/<cwd-slashes-as-dashes>/memory/MEMORY.md`) — MEMORY.md was the
dominant missing reference: measured against the reference docs alone (queue
excluded), adding it moved 21 of 41 candidates in a 2026-09-03 batch from "kept" to
correctly `suppressed` (headroom's dry-run output echoes existing MEMORY.md sections
back as if they were new findings). With the live queue's own reference chunks
included — the actual production configuration — the incremental delta on that same
batch was 1 of 41, since the queue already caught most of the same overlap; the
fix's value scales with how sparse a given project's queue history is. A missing
reference file warns and is skipped, never errors — safe to always pass all four.

| Outcome | Coverage | Action |
|---|---|---|
| `suppressed` | ≥ `--threshold` (0.75) | dropped — a restatement |
| `flagged` | ≥ `--flag-threshold` (0.45) | **kept**, tagged with `filter_note` for triage |
| `thin` | < 6 content tokens | dropped — a bare heading is not a signal |
| `kept` | otherwise | appended normally |

Thresholds are calibrated against the 44 human-labeled dispositions of 2026-08-14, where
the populations separated as: real signals ≤ 0.70, fully-covered restatements ≥ 0.80.
Reproduce with `--self-audit`. Composite entries (`Topic — Fact1. Fact2. Fact3.`) sit in
the 0.46–0.56 band — each fact known, the bundle still part-novel — which is why that band
flags for a human rather than auto-suppressing; no threshold separates them from genuine
signals, so the filter declines to guess.

Stdlib only (system `python3` has no `jsonschema`), deterministic, no network. The report
is teed to `~/.claude/context-manager/harvest-logs/<date>-filter.txt`: suppression must
leave a disk artifact, or "few new entries" becomes indistinguishable from a collector
that never ran.

## Test coverage

`tests/rhize-context-manager/test_harvest_noise_filter.py` (added 2026-09-04) covers the
tokenizer, reference-building, all four classification outcomes at their boundary values,
the `--max-blocks` union behavior, and pins the default thresholds/`MIN_CONTENT_TOKENS`
as an explicit regression guard — a silent threshold change now fails a test instead of
just shifting queue volume unnoticed.
