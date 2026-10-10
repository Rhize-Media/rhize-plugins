# Codex review packet: skill-router optimization (branch `claude/routing-optimization`)

**Authority:** Jim asked for the routing effects of the Oct 10 tag cleanup to be analyzed and optimized, with Fable and Codex consulted. He chose "Fable now, Codex before `main`." This packet asks Codex for an independent `review` before the branch is merged into `main`. The packet authorizes no edits, pushes or merges.

**Target model:** use the most capable Codex model available, at high effort.

## Objective

Restore what the tag cleanup broke, and raise legitimate router recall without losing precision. Every change must be backed by measurement from the checked-in harness.

## How to verify (from the repo root on the branch)

```bash
python3 scripts/validate_skill_map.py --check-stale
python3 evals/skill-map-routing/run.py --check evals/skill-map-routing/baseline.json
python3 evals/skill-map-routing/run.py --checkout <worktree at 0fd4619> --out /tmp/orig
python3 evals/skill-map-routing/score.py --compare /tmp/orig/results.json evals/skill-map-routing/baseline.json
python3 evals/skill-map-routing/score.py --compare-inferred /tmp/orig/inferred_signals.json evals/skill-map-routing/inferred_baseline.json
for f in tests/skill-map/*.js; do node "$f"; done
python3 -m pytest -q
```

The full pytest suite passes, apart from `test_stale_temp_dirs_are_swept_and_unwritable_cache_is_explained`, which fails only because the sandbox runs as root.

## Changes

1. **Data (`catalog/tags.json`, SKILL.md frontmatter):**
   - `seo-audit` now marks only seo-site-audit. It had been on 6 of the 7 SEO skills, so "SEO audit" prompts tied, and the tie-break on id picked aeo-geo-optimization.
   - `review` is dropped from rhize-visual-plan; it caused 3 wrong routes on real eval prompts.
   - Topics `security` and `prospecting` and stacks `python` and `supabase` are restored on their original carriers. The cleanup had removed 32 inferred signals from 31 installed third-party skills.
   - The retirement rule in `docs/skill-map.md` now requires a `--report-inferred` before/after diff.
2. **Router phrases (`scripts/build_skill_map.py`):**
   - Optional `metadata.rhize.router.phrases`: 2+ words, at most 3 per skill, validated with a BuildError.
   - These emit `{kind: "phrase", weight: 2}` signals, used only for the five skills whose retired slug echoed their name.
   - There is no indexes `schemaVersion` bump; the reasoning is in `query-layer.md`.
3. **Matching (`rhize-context-manager/hooks/lib/route-core.js`, `skill-router.js`, `scripts/build_local_skill_map.py`):**
   - Plural folding via `normalizeWord`. It is mirrored in Python, and `tests/skill-map/fixtures/stem-parity.json` is checked from both node and pytest.
   - One shared matcher (`matchSignals` / `scoreCandidates` / `pickBest`), used by `routeFromIndex`, `route()` and the shadow shortlist.
   - A guarded `name-partial` signal at weight 0.5. It is suppressed whenever any skill's full name matched the prompt.
   - Stack-only matches no longer qualify. Declared tag signals carry `facet`; signals without a facet behave as before.
4. **Harness (`evals/skill-map-routing/`):**
   - A deterministic corpus: 72 eval positives, 110 negatives and 17 probes. Negatives are scored as "other" only when the route lands outside the target's plugin.
   - 80 long realistic negatives, written without reading the skill descriptions.
   - A frozen third-party snapshot, an inferred-signal diff, `--check` gates, and history files for `0fd4619` and `1ace47d`.

## Measured results (same rows, frozen third-party snapshot)

| Checkout | eval hit/wrong/silent | negatives false/cross-plugin | probes hit/wrong | long-negative fires |
|---|---|---|---|---|
| `0fd4619`, before Oct 10 | 9/6/57 | 0/1 | 11/2 | 4/80 |
| `1ace47d`, after the cleanup | 9/7/56 | 0/1 | 4/3 | 4/80 |
| this branch | 13/5/54 | 0/0 | 10/3 | 3/80 |

- **Third-party inference** vs `0fd4619`: 0 slugs lost, 10 gained (all from plural folding).
- **Rejected after measurement:**
  - Description-mined trigger phrases. They are circular: 36–41 of the 83 prototype eval prompts contain their target's own phrase. With phrase-alone qualification, 3 false triggers also appeared.
  - Specificity tie-break: no effect.
  - `-ing` stemming: an extra misfire, and it folds `testing` into `test`.
  - Dotted-name joining ("Next.js" → `nextjs`): fires went from 3 to 9 and cross-plugin routes from 0 to 3.
- **Advisory review (Fable):** reached the same verdicts. It also flagged the third-party loss, the SEO tie, the circularity and the weak negatives; those findings drove this branch.

## Questions for Codex

1. **Correctness of the shared matcher refactor.** Are there behavior changes beyond plural folding, partials and the stack floor, especially in `route()`'s new signal construction and `shadowShortlist`'s `taskSignals`?
2. **The partial-name guard.** Is "any full-name match suppresses all partials" the right scope, or should it be per-sibling, i.e. names that share 2 or more words?
3. **The stack floor.** Is "at least one non-stack signal" sound? It costs one eval hit: "review my Next.js + Sanity site for SEO" now goes to a third-party sanity skill instead of nextjs-sanity-seo. Would a narrower rule do better, such as stacks counting only when the skill carries 3 or fewer stacks?
4. **Python/JS parity.** Are `normalizeWord` and `_normalize_word` truly identical for all inputs, including non-ASCII, digits and empty strings? Does the fixture cover enough?
5. **Harness validity.** Look for remaining leakage or scoring bias, and say whether the thresholds are too tight or too loose given n=72.
6. **Compatibility.** Machines with older installed indexes have no `facet` field and no phrase signals. Confirm they degrade safely, and that `agent-brief-router`'s metric shift is acceptable.

Return findings as suggestions with file and line references. The coordinator will verify each one against the code and the harness before changing anything.

## Review outcome (2026-10-10)

All three rounds went through the `rhize-bridge` `request_review` tool to Codex (`gpt-6.1-sol`, high effort), from the maintainer's Mac. The coordinator checked every finding against the code and the harness before changing anything.

### Round 1 — job `ccd97785-86ad-44bc-aaee-877aa4a62167`
Result: `needs_context`; 2 major and 4 minor findings, all fixed in `7f84656`:
- **Stack-floor bypass (major):** a partial name counted as task evidence.
- **Fallback phrases (major):** the `route()` fallback ignored router phrases.
- **Shadow hints:** they included partial-name labels.
- **Phrase validation:** it compared literal text instead of plural-folded word sets.
- **Unicode:** the ASCII-token contract was undocumented.
- **Guard scope:** measured but not adopted, because the narrower guard added a long-prompt misfire.

### Round 2 — job `ffeaf4a4-1a0c-436c-9231-972a9819bd7d`
- Result: router fixes confirmed, verdict **hold**, with 1 major and 4 minor harness defects plus 1 nit.
- The defects were multi-target scoring, negative-probe handling, optional corpus identity, a missing probe-recall gate, and inferred-diff counting.
- All were fixed in `22e03bd`, with regression tests.

### Round 3 — job `aa90eb04-cc13-4d67-92d3-5252c6aeb6ca`
- Result: all round-2 findings resolved, no new defects, verdict **merge**.
