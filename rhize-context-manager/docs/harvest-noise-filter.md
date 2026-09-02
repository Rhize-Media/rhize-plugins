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
existing queue patterns (**any** status) and the CLAUDE.md files passed via `--reference`.

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
