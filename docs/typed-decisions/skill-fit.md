# Skill fit: Laya co-signs router suggestions

Skill fit is the first decision governed by the earned-authority registry. The skill router (`rhize-context-manager/hooks/skill-router.js`) proposes at most one skill per prompt. The local Laya server can co-sign that proposal. A suggestion is then shown only when Laya independently picks the same skill.

Laya starts in `shadow`. It earns `cosign` only by passing a frozen statistical gate, and it loses it again automatically.

- Design and reviews: [the plan](../superpowers/specs/2026-10-11-laya-earned-authority-plan.md).
- Tier policy: [typed decision layer](../typed-decision-layer.md#earned-authority-advisory-tier).

## What happens on each prompt

1. The router computes its incumbent suggestion exactly as before. It also precomputes today's exact hook output.
2. The hook skips the Laya call (records nothing, and emits the incumbent output) when any of these is true:
   - `skill-fit` mode is `off`;
   - the router did not fire;
   - the prompt is an explicit skill request.
3. Otherwise the hook builds the `laya-choice-v1` request:
   - the first ≤1,200 code points of the prompt;
   - up to 5 shortlisted skills, each with a 120-character description;
   - a `none` option.

   It sends the request to the literal-loopback Laya server. A refused redirect, a failed `/health` identity probe, or the 800 ms deadline (shared by probe and request) all count as failures.
4. The output settles exactly once:

   | Situation | Hook output |
   |---|---|
   | Mode `cosign`, treatment arm (90%), Laya status `ok`, Laya's choice differs from the incumbent | The output without the router suggestion. A workflow message, if any, is still shown. |
   | Everything else (`shadow`, the 10% holdback arm, any Laya failure, deadline expiry, any error) | The incumbent output, byte for byte. |

5. After stdout has flushed, the hook appends one private decision record. The record holds hashes, ids, probabilities and latency, but never prompt text. The legacy suggestion-log row is written as before. Its `suggested` field now records what was actually shown, plus `typed_mode`, `typed_arm`, `typed_status` and `typed_agrees`.

**Hook timeout.** The hook needs a host timeout of at least 8 s. That covers the 4.5 s workflow bridge, the 0.8 s Laya deadline and Node startup. The default Claude Code command-hook timeout already exceeds this.

**Latency.** On Jim's Mac the Laya call measured 117 ms median and 142 ms at p90 on long prompts (2026-10-11).

## Where things live

Everything below lives under `~/.local/share/rhize/typed-decisions/`. Directories are 0700, files 0600, and symlinks below the root are refused.

| Path | What | Written by |
|---|---|---|
| `registry-state.json`, `registry-audit.jsonl`, `registry-state.lock` | Current mode per decision, and its audit trail | `decision_registry.py` (and the cycle through it) |
| `laya-runtime.json` | `{"revision": "<checkpoint revision>"}`, written at activation from the Laya runtime pins | operator |
| `laya-health.json` | 60 s identity-probe cache | hook |
| `skill-fit/records/YYYY-MM-DD.jsonl` | Decision records, live and backfill | hook, `backfill.py` |
| `skill-fit/labels/…`, `skill-fit/outcomes/…`, `skill-fit/cohorts/…` | Labels, transcript-joined outcomes, cohort ledger | `skillfit_labels.py`, `outcomes.py`, `cohorts.py` |
| `skill-fit/backfill/` | Frozen index, map and manifest for resumable backfill | `backfill.py` |
| `skill-fit/cohort-meta/`, `skill-fit/receipts/`, `skill-fit/cycles/` | Cohort inclusion probabilities, gate receipts, cycle receipts | `cohorts.py`, `decision_cycle.py` |

The shipped defaults (mode, holdback, budget, λ, gates) live in `rhize-context-manager/catalog/decision-registry.json`.

## Commands

All scripts are under `rhize-context-manager/scripts/typed_decisions/`, except the cycle. Each one accepts `--root DIR`; the default is the path above.

```bash
# Inspect, pin or roll back (manual pins suspend automation until --unpin)
python3 decision_registry.py show
python3 decision_registry.py set-mode skill-fit shadow --reason manual_rollback --pin
python3 decision_registry.py set-mode skill-fit shadow --reason manual_unpin --unpin
python3 decision_registry.py recover            # finish an interrupted mode change

# Evidence
python3 backfill.py run --since 2026-09-27 --cutover <activation ISO> --budget 1200
python3 outcomes.py join
python3 skillfit_labels.py label-cohort --cohort-id <id> [--prepare-only]
python3 skillfit_labels.py label-pool --n 12 [--prepare-only]

# The recursive loop and the daily report
python3 ../../../evals/typed-decision/decision_cycle.py run [--dry-run]
python3 scoreboard.py render --format md
```

## How authority is earned and lost

**Estimand.** Co-sign and the incumbent differ only when Laya disagrees with the router. Co-sign is better exactly when the router's suggestion is wrong in more than 1/(1+λ) of those disagreements. With λ = 1 that is more than half.

**Promotion.** The cycle reserves a frozen cohort of 60 disagreement cases from distinct sessions; reserving does not label anything. Once the labeler has labeled the cohort, the cycle tests it once. Promotion requires all of these:
- the one-sided exact Clopper–Pearson lower bound on "router wrong" exceeds 0.5 at α_k = 0.05·2^−(k−1), where k is the attempt number;
- at most 20% of labels are ambiguous;
- Laya's unavailable rate is at most 5%.

At n = 60 the first attempt needs at least 37 "router wrong". Each new attempt needs a new cohort and a stricter α. Only the plain co-sign policy (`cosign-v1`) can ever be deployed.

**Demotion.**
- **Quality:** demote when there are at least 30 labeled live co-sign disagreements in 14 days and the upper bound falls below 0.5.
- **Operational:** demote when Laya is unavailable or invalid on more than 10% of calls over 3 days.
- **Latency:** report-only for the first 14 days after a promotion, then enforced.
- **Pin:** a manual pin overrides all of these.

**Alternatives** (stricter router floors, thresholded co-sign, veto, swap, router-else-Laya) are scored on the daily label pool and reported only. A stricter floor that wins becomes a code-review recommendation.

## Daily rhythm

The existing 07:30 autolabel job, `laya-autolabel.sh`, runs these steps after its workflow steps, under the same lock and with a 10-minute sub-deadline:
1. `outcomes.py join`
2. `skillfit_labels.py label-cohort` for any open cohort
3. `skillfit_labels.py label-pool`
4. `decision_cycle.py run`
5. `scoreboard.py render`, appended to the summary the 08:00 Codex automation already reads

## Limits

- Labels are constrained to the shortlist. They support no claim about catalog-wide recall or about Laya recovering skills the router missed.
- The acceptance outcome (was the suggested skill invoked?) is confounded by the suggestion itself. It is reported as a secondary signal only.
- Codex transcripts are not yet joined for outcomes.
