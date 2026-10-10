# Skill-map routing harness

A reproducible, offline way to measure what a change does to the skill router
(`rhize-context-manager/hooks/lib/route-core.js`, `routeFromIndex`). It is an
instrument, not a tuning target: it runs the repo's real `routeFromIndex` and
`tokenize` over a fixed set of prompts and counts where each prompt routes. No
model calls, no network.

## What it measures

Every prompt is routed against a resolved router index: this checkout's
`generated/skill-map.indexes.json` plus the third-party skills from
`third_party_snapshot.json`, with up to 3 inferred tag signals per third-party skill
computed by the checkout's own `build_local_skill_map.py` against its own
`catalog/tags.json`. Outcomes:

| Set | Rows | Outcomes |
| --- | --- | --- |
| eval positives | `evals/*/trigger_evals.json`, `rhize-context-manager/routing_cases.json`, `rhize-devflow/trigger_cases.json` and `skill-evals.json` cases with `expected` targets | `hit` (routed to the target), `wrong` (routed elsewhere), `silent` |
| eval negatives | the same files, "should NOT trigger skill X" | `false_trigger` (routed to X), `other_cross_plugin` (routed to a skill in a different plugin than X), `other_same_plugin` (a sibling in X's plugin, usually the intended route, so it is reported but never gated), `silent` |
| probes | `probes.json`: 17 author-written prompts using the vocabulary retired by the tag cleanup | `hit` / `wrong` / `silent` |
| long negatives | `long_negatives.json`: 80 long, realistic prompts that should route to nothing | `fire` (routed and not in the row's `acceptable` list) / `acceptable` / `silent`; the metric is the fire rate |

Target names are resolved to `skill:<plugin>/<name>` ids from
`generated/skill-map.static.json`; a name that does not resolve to exactly one skill is
skipped and listed under `skipped` in `corpus.json` (all current skips are `command:`
targets in `trigger_cases.json`). SKILL.md trigger phrases are deliberately not mined.

`results.json` holds the summary, a per-plugin breakdown, the long negatives that fire
and one compact record per row (`id`, `target`, `top`, `outcome`), so two runs can be
diffed route by route.

## Run it

```bash
# whole pipeline against this checkout; writes evals/skill-map-routing/out/ (git-ignored)
python3 evals/skill-map-routing/run.py

# another checkout (a lane worktree, a candidate branch): same prompts, that checkout's
# index, tag catalog, inference code and route-core
python3 evals/skill-map-routing/run.py --checkout ../wt-x --out /tmp/x

# route changes against the committed baseline, and the gates
python3 evals/skill-map-routing/run.py --checkout ../wt-x --out /tmp/x \
    --compare-to evals/skill-map-routing/baseline.json \
    --check evals/skill-map-routing/baseline.json
```

The corpus always comes from the repo that holds the harness, so every checkout is
measured on identical prompts. Individual steps, all usable on their own:

| Step | Command |
| --- | --- |
| corpus | `python3 build_corpus.py [--out corpus.json]` (deterministic; sorted keys, no timestamps) |
| resolved index | `python3 make_resolved.py --checkout PATH --out resolved_index.json --inferred-out inferred_signals.json` |
| route | `node run_router.js <route-core.js> <index.json> <rows.json> <out.json>` (works against any checkout's route-core) |
| score | `python3 score.py --rows rows.json --routes out.json --results results.json` |
| route changes | `python3 score.py --compare A/results.json B/results.json` |
| inferred-signal diff | `python3 score.py --compare-inferred A/inferred_signals.json B/inferred_signals.json` |
| gates | `python3 score.py --check baseline.json --thresholds thresholds.json --results results.json` (exit 1 on any failed gate) |

`thresholds.json` lists the gates. A gate's `value` is either a literal or `"baseline"`.
`--check` warns, or with `--strict-rows` fails, when the row set differs from the
baseline's (`rows_sha`): baseline-relative gates mean nothing across different corpora,
so regenerate the baseline whenever eval files, probes or long negatives change.

## Committed artifacts

- `baseline.json`, `inferred_baseline.json`: the harness run against unmodified `main` at
  the time of writing (commit `1ace47d`). Refresh with `run.py` and copy
  `out/results.json` and `out/inferred_signals.json`.
- `corpus.json`: the corpus as built from the repo, for review; `run.py` rebuilds it.
- `third_party_snapshot.json`: **a point-in-time snapshot of the third-party (marketplace)
  skill, command and plugin nodes from the maintainer's machine** (Oct 2026), reduced to
  `id`, `kind`, `name` and `description`. It is not regenerated and drifts from any real
  install; it only exists so third-party routing is measured against the same inventory
  everywhere.

## Known limits

1. **Description-mining changes are measured against their own training set.** Eval
   prompts in `evals/*/trigger_evals.json` were authored to contain SKILL.md vocabulary,
   because `run_evals.py`'s keyword-drift check requires it. Any change that mines
   description text into router signals (trigger phrases, description keywords) will look
   good here because the prompts were written from that same text. Only tag, name and
   stem changes (aliases, tie-breaks, stemming, tag removal) are measured fairly. Use the
   long negatives and probes, which were written independently of the descriptions, to
   catch over-firing, and do not read an eval-positive gain from a description-mining
   change as evidence.
2. **The sample is small and skewed toward Obsidian and SEO.** About 70 positives and 110
   negatives, with several plugins at one to three rows. Treat differences of +/-3 rows as
   noise, and read the per-plugin table before generalising.
3. **Third-party recall cannot be measured from phrases.** There is no independent set of
   prompts for third-party skills (their descriptions are truncated, and quoting them is
   circular). The harness can only diff the inferred signals (`inferred_signals.json`) between two
   runs and report which third-party skills gained or lost inferred tags; whether those
   tags would route a real prompt is not measured, apart from whatever the long negatives
   and eval rows happen to hit.
4. **Probes are author-written** and cover only the retired vocabulary. Passing them does
   not show general recall; failing them shows a specific regression.
5. **Long negatives measure over-firing only.** They are 80 prompts from one person's
   work mix (web, SEO, CRM, trading, fitness, ops). A zero fire rate is not a recall
   claim. Rows with `acceptable` ids are the few where a Rhize skill obviously applies;
   routing there is not counted as a fire.
6. **Not modelled:** the hook's workflow-selection bridge, the typed shadow decision, the
   map-scanning fallback (`route()`), and per-session suppression. Only `routeFromIndex`
   (including its explicit "use X" handling and extends tie-break) is exercised.

## Results history (2026-10-10)

Each row is measured on the same rows (`rows_sha` unchanged), with route-core and indexes taken
from the named checkout and the frozen third-party snapshot.

| Checkout | eval hit / wrong / silent (72) | eval negatives false / cross-plugin (110) | probes hit / wrong (17) | long-negative fires (80) |
|---|---|---|---|---|
| `0fd4619`, before the Oct 10 tag work (`baseline-pre-cleanup-0fd4619.json`) | 9 / 6 / 57 | 0 / 1 | 11 / 2 | 4 |
| `1ace47d`, after the tag cleanup (`baseline-main-1ace47d.json`) | 9 / 7 / 56 | 0 / 1 | 4 / 3 | 4 |
| routing-optimization branch (`baseline.json`) | 13 / 5 / 54 | 0 / 0 | 10 / 3 | 3 |

**Changes in the branch:**
- Removed `seo-audit` from the five non-audit SEO skills.
- Dropped `review` from rhize-visual-plan.
- Restored `security`, `prospecting`, `python` and `supabase`.
- Added per-skill router phrases.
- Plural folding.
- Guarded partial-name signal.
- Stack-only matches no longer qualify.

**Third-party inference:**
- Against `0fd4619`: 0 inferred slugs lost and 10 gained, all from plural folding (`score.py --compare-inferred`).
- The tag cleanup alone had removed 32 inferred signals from 31 skills.

**Rejected after measurement:** joining dotted names ("Next.js" → `nextjs`). Precision fell: long-negative fires went from 3 to 9 and cross-plugin eval routes from 0 to 3. Recall did not rise.

**Remaining probe misses:**
- "clip this web page…": the word is "clip", not "web clipping".
- "seo for our nextjs sanity cms development site": the label is arguable.
- "stale data in nextjs after supabase write": stack-only, by design.

Differences of ±3 are within noise on this sample.
