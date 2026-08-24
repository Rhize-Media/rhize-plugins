# Skill-graph evals: measuring what the map actually buys us

**Status:** approved direction 2026-08-10 (Jim: "draft the eval spec and proceed") · extends the
existing `evals/` harness, does not replace it.

## Why

The skill map makes six measurable claims: better routing, cheaper disclosure, useful
remediation/succession suggestions, duplicate-blocking curation, and low-noise drift detection.
Every one of those has so far been argued from anecdote (the incidents in the article). This spec
defines the instruments and metrics that turn each claim into a number — and, where possible, a
number *compared against the pre-map baseline*.

Two ground rules, inherited from the substrate itself:

1. **Instrument-first.** Online metrics (acceptance, ignore-rate) are only computable from a
   suggestion log that did not exist before this round. The log ships before any dashboard.
2. **Privacy precedent.** skill-monitor stores counts and ids, never prompt text or project
   paths. Every eval artifact follows suit: mined datasets containing user text stay
   machine-local and gitignored; only miners, runners, and aggregate metrics are committed.

## Instruments

### Suggestion log (new, machine-local)

`~/.claude/context-manager/suggestion-log.jsonl`, append-only, written fail-silent by all four
map hooks after a suggestion fires. Pinned schema per line:

```json
{"ts": "<ISO8601>", "session_id": "<from hook stdin>", "hook": "router|disclosure|remediation|next-step",
 "suggested": "<id or array>", "context_hash": "<sha256[:16] of matched input>"}
```

No raw prompt text, tool output, or paths — hash only. The router additionally logs a
deterministic 1-in-20 sample of *no-suggestion* prompts (`"suggested": null`) so silence
precision has a denominator. Env override `RHIZE_SUGGESTION_LOG` for tests.

### Golden routing set (mined, machine-local)

`evals/skill-map/mine_golden_set.py` walks local session transcripts
(`~/.claude/projects/*/*.jsonl`) and emits prompt→invoked-skill pairs: a user prompt followed
within the same session by a Skill invocation is a positive example; sampled prompts with no
subsequent skill use are negatives.

Constraints (both load-bearing):

- **Output is gitignored** (`evals/skill-map/data/`). Prompts are user text. The miner and the
  metrics code are committed; the dataset never is.
- **Contamination guard:** the map router went live 2026-08-09. Mining is restricted to sessions
  *before* that date, else the router is graded on ground truth it helped create. Once the
  suggestion log accrues, a second mode can use post-log sessions with suggestion-triggered
  invocations filtered out (join on `session_id` + suggested id).

## The six evals

| # | Eval | Type | Metric(s) | Baseline comparison |
|---|---|---|---|---|
| 1 | Routing accuracy | offline, golden set | top-1 hit rate; **silence precision** (no false suggestion on negatives) | retired grep suggester run on the same set |
| 2 | Suggestion acceptance | online, longitudinal | per-hook acceptance rate (suggested id invoked in-session), ignore rate | none (new capability) |
| 3 | Disclosure cost/benefit | offline + online | bytes/tokens injected at SessionStart per repo vs the 4 retired banners (fixed cost); fraction of disclosed skills invoked that session | the 4 banners' summed byte count |
| 4 | Remediation precision | offline corpus | condition-pattern precision/recall on labeled failing tool outputs; false-positive rate per 100 failed commands | none |
| 5 | Curation gate regression | offline fixtures | block rate on 5 real historical duplicates (4 retired ECC forks + graphify); pass rate on novel controls; extends-exemption honored | the old process (which missed all 5) |
| 6 | Drift signal quality | longitudinal | verdict counts per weekly run; false-alarm count (target 0) | 7 false alarms pre-three-way |

Details worth pinning:

- **1 — silence precision outranks hit rate.** ~90% of prompts warrant no suggestion; a router
  that is right on positives but chatty on negatives is a net regression. Report both, gate on
  silence precision.
- **2 — the join.** `session_id` links log lines to skill-monitor invocations. If monitor data
  proves aggregate-only at some granularity, the report documents the proxy used — no silent
  approximation.
- **4 — corpus curation is manual once.** Failing Bash outputs are harvested from local
  transcripts (machine-local dataset, same privacy rule), labeled with correct-fixer/no-fixer.
  The regexes live in `catalog/tags.json`; the eval is the regression net that lets anyone edit
  a pattern safely.
- **5 — the strongest eval is not synthetic.** The five duplicates are documented incidents the
  old process missed; the gate must catch all five, forever. Lives in skill-forge's own test
  suite (the gate's home), with a vendored map snapshot for hermeticity.
- **6 — nearly free.** The weekly audit already computes verdicts; it appends one metrics line
  per run to a local report file. The eval is the trend.

## Harness integration

`evals/` already has `run_evals.py` (trigger + quality evals per plugin). Skill-map evals live in
`evals/skill-map/` following the same result-file conventions (`evals/results/` is gitignored).
`run_evals.py --plugin skill-map` should pick them up if the harness's plugin discovery allows;
otherwise a thin `evals/skill-map/run.py` entry point with the same result schema — do not fork
the assertion engine.

The weekly audit gains one step: run the offline evals that need no fresh labeling (1 vs current
golden set, 5, 6) and append their metrics to the report line, so regressions in routing or the
gate surface weekly, not when someone remembers.

## Explicitly out of scope

Embedding/LLM-judged routing quality; cross-machine log aggregation; auto-tuning tag vocab from
eval results (a human reads the metrics and edits the catalog); publishing any mined dataset.
