# Laya decision layer: earned authority (plan + impact map)

**Status:** v3, implemented on this branch (§12 reconciles the actual changes). The Fable advisory review (approve-with-changes, §10) and the Codex review (implement-with-changes, §11) were reconciled before implementation.
**Branch:** `claude/laya-earned-authority`
**Authority:** Jim, 2026-10-11:

> implement our decision layer strategy fully now and try to recursively implement and prove it as we go using tools like the autoresearch library … optimally integrating Laya's decision-making capabilities into our daily operations.

He also asked for:
- a Fable + Codex review before implementation;
- Sonnet 5.5 parallel lanes, used only if recommended;
- a final Fable + Codex review before `main`.

## 1. What we measured (2026-10-11, all read-only)

All figures come from Jim's Mac today. These are exploratory replays with small samples, not release-gate results.

| # | Finding | Evidence |
|---|---|---|
| E1 | **Laya is already in daily use.** The v2 workflow pilot has 349 observations since 2026-09-28: 179 scored in shadow, 163 excluded and 4 unavailable. | `~/.local/share/rhize/workflow-selection/pilot/v2/*` |
| E2 | **There are 73 explicit AI-reviewed labels.** They split 58 general, 13 none and 2 content. Research is held at the 200-label floor. | `taxonomy-labels/`, 07:30 autolabel |
| E3 | **The workflow instrument is broken.** It asks three independent `noul` questions using only four enum fields, then takes the argmax. Agreement is **2/73 = 2.7%**, because Laya picks `content` 70 of 73 times. | replay via `/v1/systemone` |
| E4 | **Fixing the question type helps but does not beat the baseline.** A native `choice` question on the same fields agrees **47/73 = 64.4%**. Adding the redacted task text gives **21/35 = 60%**. Both lose to always-`general` (**79.5%**). | same replay |
| E5 | **Skill fit looks promising.** On the 279-row routing harness, co-signing raises precision from 0.67 to 0.86 (table below). | `evals/skill-map-routing` + Laya replay |
| E6 | **Direct HTTP is fast.** Laya answers in 59 ms p50 / 92 ms p90 on short prompts. Most of the pilot's 1.57 s p50 is the cost of spawning Python. Long-prompt latency has not been measured. | replay timings |
| E7 | **Model limits.** The checkpoint is ModernBERT-large with an RL head. Instructions and options get a 192-token head (each option is capped at 48 tokens, and shrinks to about 29 when there are 6). The state gets the remaining room up to 512 tokens (about 317, head-kept). `choice` returns per-option `probabilities`. The server makes no network calls and logs no requests. `/health` lists the loaded models. There is no fine-tune API. | `laya` 0.3.20, checkpoint `55cf4c4` |
| E8 | **The skill-fit shadow never runs.** It needs an environment flag that is unset. It is skipped whenever workflow selection is attempted. Even when it runs, Laya sees only hashed ids and the tokens the router already matched. | `skill-router.js:84-127` |
| E9 | **The routing fixes are not live.** The `settings.json` hook runs the repo checkout, which is on a Codex branch 24 commits behind `main`. The setup orchestrator already supports a portable path that follows marketplace updates. | Mac settings; `setup_orchestrator.py:253-272` |
| E10 | **There is plenty of real traffic.** Since 2026-09-27 the router has fired **2,235** times (about 150 a day), plus 110 silences sampled at 1 in 20. Each log row carries `session_id` and `sha256(prompt)[:16]`. | `suggestion-log.jsonl` |

**E5 in detail.** Co-sign means a suggestion is shown only when Laya's `choice` independently names the same skill. Laya chooses among the top-5 unfloored lexical shortlist plus `none`, given the prompt text.

| Policy | Fires | Precision | Hits | Wrong | False fires |
|---|---|---|---|---|---|
| Router (incumbent) | 33 | 0.67 | 22 | 8 | 3 |
| Router, score ≥ 3 | 29 | 0.76 | 22 | 6 | 1 |
| Router, score ≥ 3.5 | 9 | 0.89 | 8 | 1 | 0 |
| **Co-sign** | 21 | **0.86** | 18 | 3 | 0 |
| Laya replaces router (p ≥ 0.4) | 65 | 0.45 | — | — | — |

- **Disagreements:** there were 12. The router was right in 4 and Laya's alternative in 5. Fisher's exact test gives p ≈ 0.0055.
- **Caveats:** these are authored trigger prompts that share vocabulary with skill descriptions. They are short (p90 148 characters), and the router's thresholds were tuned on this same corpus.
- **Status:** E5 justifies *testing* the instrument. It does not establish that the 1,200/120-character instrument beats the incumbent on real prompts.

## 2. Thesis

Laya has been held back by **how it is asked**, not by data volume. The question is: "**for which decision does Laya beat the incumbent and the trivial baselines?**" The answer has to come continuously from live evidence, so that authority is earned and lost automatically.

This plan:
1. **Fixes the instrument:** a native `choice` question, a bounded prompt head, candidate descriptions and a direct HTTP call.
2. **Gives Laya one real job:** co-signing skill suggestions. This decision is high-volume, low-risk and advisory.
3. **Validates the instrument and collects evidence from real traffic on day 0.** A reserved bootstrap cohort decides the first promotion test.
4. **Builds a small generic registry and research loop** that later decisions can join.
5. **Keeps workflow fit with Arm A** and keeps critical decisions in schema-enforced shadow.

## 3. Policy changes Jim must accept

**P-A: task text goes to loopback Laya (advisory tier only).**
- **What is sent:** the first ≤1,200 Unicode code points of the prompt.
- **Where it can go:** only literal loopback addresses (`127.0.0.1`, `::1`). HTTP redirects are refused, and nothing is sent until a cached `/health` probe for that exact endpoint and model has passed.
- **What is kept:** nothing. The text is never persisted, and cloud annotators still see only redactor output.
- **No hook-side redaction.** The text never leaves the machine, and transcripts already hold it on the same disk.
- **Trust assumption, stated explicitly:** any process listening on the loopback port already runs as Jim's user and could read his transcripts anyway.

**P-B: AI-reviewed labels are sufficient for the advisory tier.** These are two annotators plus a Fable reviewer, using the exact binomial gate in §4.6. The workflow and critical tiers are unchanged, and the workflow 200-label floor is **unchanged**. An optional weekly human-adjudicated stratum calibrates the labeler.

**P-C: mode changes are automatic for the advisory tier only.** Every change is audited and reversible. A manual pin suspends automation.

## 4. Design

### 4.1 Registry, modes and the mutation contract

The registry has three parts:
- **Shipped default:** `rhize-context-manager/catalog/decision-registry.json`, validated by `schemas/decision-registry-v1.schema.json`.
- **Machine-local state:** `~/.local/share/rhize/typed-decisions/registry-state.json`, validated by `schemas/decision-registry-state-v1.schema.json`.
- **Audit log:** `registry-audit.jsonl`.

**Single mutation path.** All state writes go through `scripts/typed_decisions/decision_registry.py`, both the CLI and the library calls `decision_cycle.py` makes.
1. Take an exclusive `fcntl` lock on `registry-state.lock`.
2. Read the state and check `revision`. A stale `expectedRevision` is rejected.
3. Validate the new state.
4. Append an audit `intent` line containing the old and new revision and the full new state.
5. Write to a temp file, `fsync`, then `os.replace`.
6. Append an audit `commit` line.

**Recovery.** If the audit log shows an intent with no commit and the state revision is older, recovery re-applies the audited new state. If the state already matches, recovery adds the missing commit line.

**Readers.** The Node hook reads the state only and never writes it. A missing state file means the shipped default applies. A corrupt, unreadable or schema-invalid state means `shadow`.

**Manual pin.** `set-mode --pin` writes `pinned:true` and suspends automatic changes until `unpin`.

**Modes:** `off`, `shadow` and `cosign`.
- **Holdback:** a permanent randomized holdback (default 10%, propensity logged) stays on the incumbent alone. It measures acceptance effects only.
- **Tiers:** `advisory`, `workflow` and `critical`. The schema rejects any mode other than `shadow` or `off` for `critical`.

**Deployable policy.** In v1 the **only** policy that can be deployed automatically is `cosign-v1`, plain co-sign. Every other candidate produces a recommendation only. Each mode transition and gate receipt is bound to `policySha256`, `instrumentSha256`, `layaRevision` and the registry revision.

Registered decisions:

| Decision | Tier | Default | Reachable modes |
|---|---|---|---|
| `skill-fit` | advisory | **`shadow`** | off, shadow, cosign |
| `workflow-fit` | workflow | `shadow` | shadow (reference only) |

### 4.2 Laya client v2 and instrument `laya-choice-v1`

**Request builder (coordinator-owned contract code).** There is one reference builder in each language:
- `hooks/lib/laya-instrument.js` (Node);
- `scripts/typed_decisions/instrument.py` (Python).

A shared fixture pins byte-identical canonical requests. The cases cover fewer than 5 candidates, astral and combining Unicode, long and empty descriptions, and long skill names.

Counting and serialization rules (both languages):
- **Counting:** Unicode code points, in both languages.
- **Whitespace:** ASCII whitespace only.
- **Prompt head:** at most 1,200 code points, cut back to the last ASCII whitespace if one falls in the final 200 code points.
- **Descriptions:** ASCII whitespace runs collapse to one space, then the text is truncated to 120 code points.
- **Serialization:** canonical JSON (sorted keys, compact separators, UTF-8, no ASCII escaping) is used only for hashing.

`promptLengthBucket` (`lt200`, `200-600`, `600-1200`, `gt1200`) is computed from the **original** prompt.

The request:
- **State:** `{request: head}`.
- **Question:** one `choice` question named `skill`: "Which skill, if any, should be loaded to handle `request`?"
- **Criteria:** `s0..s{k-1}` = `"<skill-name>: <description>"`, plus `none` = "none of these skills is needed; answer directly".

The builder also returns:
- `keyMap`, which maps each `s*` key to its skill id;
- `truncated`;
- `promptLengthBucket`;
- `criteriaSha256`, the hash of the canonical criteria, which pins the description content per record;
- `instrumentSha256`, the hash of the template constants.

**Clients:**
- **Node:** `hooks/lib/laya-client.js` (Node ≥ 18, `fetch` with `redirect:'error'`).
- **Python:** `scripts/typed_decisions/laya_choice.py` (`urllib` with no redirect handler).

Both clients:
- accept only literal `127.0.0.1` or `::1` endpoints, with no hostnames;
- keep **one monotonic deadline (`latencyBudgetMs`, default 800 ms) covering the probe and the POST together**;
- read at most 64 KiB of response;
- validate that `routing.model` matches, that `choice` is a criteria key, and that `probabilities` covers every key with values in [0, 1];
- never throw;
- return `{status: ok|timeout|unavailable|invalid|identity_failed|redirect_refused, choice, probabilities, latencyMs}`.

The probe result is cached for 60 s in `laya-health.json` (mode 0600), keyed by `{endpoint, model}`.

**Laya revision.** `layaRevision` is read from an optional `~/.local/share/rhize/typed-decisions/laya-runtime.json`, which activation writes from the runtime pins. If that file is missing, the value is `"unknown"`. Evidence cohorts are keyed by it.

### 4.3 Skill-fit in `skill-router.js` (async, settle-once)

1. Compute the incumbent and the **complete incumbent hook payload first**: the exact bytes today's code would emit, including any workflow message.
2. If the incumbent fired, the prompt is not an explicit skill request, and the mode is not `off`, build the shortlist. It comes from **`lexicalShortlist(index, promptTokens, incumbentId, k=5)`**, a new export of `route-core.js` that is unfloored, forces the incumbent in, breaks ties by code-unit order, and is pinned by a fixture. Descriptions come from `readMap()`, parsed once.
3. Assign the arm: `sha256(sessionHash‖promptHash) mod 10000 < holdback·10000` puts the prompt in holdback.
4. Call Laya under the single deadline. The routing decision **settles exactly once**:
   - In the treatment arm with mode `cosign`, if Laya returns `ok`: emit the incumbent only when `choice === incumbent`; otherwise emit the payload without the router suggestion. A workflow message, if present, is still emitted.
   - In every other case (shadow, holdback, any non-`ok` status, deadline expiry, or an exception) emit the precomputed incumbent payload.
   - A late HTTP completion after settlement is ignored.
5. **Await the `stdout.write` callback** before any persistence or exit. Persistence happens afterwards inside its own try/catch, so it can never erase output. `process.exit(0)` runs only after the write callback (or an error) and the persistence attempt.
6. The workflow bridge is untouched. The old `workflowAttempted` gate on the Laya call is removed. The content-engine overlap suppression stays. The host hook timeout is documented as ≥ 8 s.
7. The legacy log row records what was **emitted**, plus `typed_mode`, `typed_arm`, `typed_status` and `typed_agrees`.
8. A decision record (§4.4) is appended for every eligible prompt. It must be under 2 KB.

Router-silent prompts are not sent to Laya live.

### 4.4 Contract (committed before any lane starts)

Data is machine-local under `~/.local/share/rhize/typed-decisions/<decision>/`. Directories are 0700 and files 0600, in JSONL partitioned by UTC day. Schemas live in `rhize-context-manager/schemas/` and fixtures in `tests/rhize-context-manager/fixtures/typed-decisions/`.

**`rhize-typed-decision-record-v1`.** It contains no text, paths or tokens, and sets `additionalProperties:false`.

| Group | Fields |
|---|---|
| Identity | `decision`, `decisionId` (uuid4 hex), `occurrenceKey`, `ts`, `host`, `basis` (`live` \| `backfill`), `sourceStratum` (`fired` \| `silent_sample`) |
| Hashes | `sessionHash`, `promptHash` (full sha256, recovered from the transcript for backfill), `promptLengthBucket` |
| Versions | `routerSourceSha256` (route-core + skill-router + laya-instrument), `indexSha256`, `registryRevision`, `policy`, `policySha256`, `instrument`, `instrumentSha256`, `criteriaSha256`, `layaRevision` |
| Assignment | `mode`, `arm`, `propensity` |
| Decision | `incumbent {skillId, score}\|null`, `shortlist` (at most 5 ids), `laya {status, choice, probabilities, latencyMs, truncated}`, `emitted` |

Field rules:
- **`occurrenceKey`** = `sha256(sessionHash + ":" + promptHash + ":" + ts truncated to the minute)`. The `ts` is the router hook's own clock in both cases: the live record time, or the legacy log row's `ts`. Repeated identical prompts within one minute count as one occurrence.
- **`sourceStratum`** is the *original* router outcome from the log, kept independent of the replayed decision.

**`rhize-typed-decision-label-v1`.** Fields: `decisionId`, `occurrenceKey`, `basis` (`ai_model_reviewed` \| `human_adjudicated` \| `harness`), `cohortId`, `stratum`, `inclusionProbability`, `candidates`, `acceptable` (a subset of `candidates`), `bestSkill` (an id or `none`), `unlistedBetter`, `ambiguous`, `annotators`, `reviewer`, `evidenceSha256`, `labeledAt`.

**Scoring rules, frozen in the contract.** For a shown suggestion `s`:

| Case | Score |
|---|---|
| `s ∈ acceptable` | **hit** |
| `acceptable = ∅` | **false fire** |
| otherwise | **wrong** |

- `ambiguous` labels are excluded from gates and counted.
- Labels are **shortlist-constrained**. No claim about catalog-wide recall or silence recovery is made from them.

**`rhize-typed-decision-outcome-v1`.** Fields: `decisionId`, `occurrenceKey`, `outcome` (`invoked_emitted` \| `invoked_other_shortlisted` \| `invoked_unlisted` \| `none_invoked` \| `transcript_unavailable`), `skillInvoked`, `via` (`skill_tool` \| `slash_command`), `latencyTurns`, `joinedAt`, `transcriptSha256`. Outcomes are a secondary signal only.

**`rhize-typed-decision-cohort-v1`.** This is a ledger with one line per cohort event:

| Event | Fields |
|---|---|
| `reserve` | `cohortId`, `decision`, `policySha256`, `instrumentSha256`, `layaRevision`, `lambda`, `alpha`, `attempt`, `target`, `occurrenceKeys` |
| `labeled` | `cohortId`, the counts |
| `consumed` | `cohortId`, `verdict`, the statistic, `receiptSha256` |

A cohort is frozen at `reserve`. Its policy is fixed before any of its labels exist, and it is tested exactly once.

The contract commit also includes:
- the registry and registry-state schemas plus the mutation contract docstring;
- `lexicalShortlist()` and its fixture;
- both instrument builders and their fixture;
- the `transcripts.py` interface stub.

### 4.5 Evidence pipeline (L2)

**`scripts/typed_decisions/transcripts.py`** is new; `pilot_autolabel.py` is not edited.
- It provides a prefix-capable scanner.
- It reuses `transcript_message` and `choose_match`, which resolves repeated prompts by timestamp, and `sanitize`.
- It recovers the full `promptHash` and the turn text in memory only.

**`backfill.py`** covers only router log rows **before the live-collection cutover** recorded at activation, so live and backfill can never overlap.
- **Inputs:** each run freezes a manifest of the index, map, route-core, instrument and Laya revision hashes. A resumed run must reuse that manifest.
- **Replay:** current incumbent plus `laya-choice-v1`, run through `route_replay.js`.
- **Output:** records with `basis:"backfill"`, `mode:"shadow"`, `emitted:null`, deduplicated by `occurrenceKey`.
- **Limits:** bounded, resumable, with a per-run call budget.

**`outcomes.py`** joins records to `Skill` tool_use events and skill slash commands in the same session, after `ts`, within the next 3 user turns or 30 minutes. It is idempotent.

**`skillfit_labels.py`** reuses the `pilot_autolabel` primitives by import.
- **Sampling:** for a cohort it picks a uniform random sample **within its stratum**, with at most **1 case per session**, and records `inclusionProbability`.
- **Cohort inputs:** the cohort stratum for the gate is *disagreements* (incumbent fired, Laya status `ok`, Laya choice ≠ incumbent).
- **Annotation:** two annotators see the redacted prompt, the preceding context and the candidates with descriptions. Each answers `acceptable`, `bestSkill`, `unlistedBetter` and `ambiguous` under a schema. A Fable reviewer resolves splits.
- **Daily scoreboard sample:** a separate pool of ≤12 cases (agreements and disagreements, with inclusion probabilities). It is never used for gates.

**Harness rows** (279) become `basis:"harness"` labels. They are a regression gate only.

### 4.6 Research loop (`evals/typed-decision/decision_cycle.py`, L3)

This is an autoresearch-style loop and a sibling of `pilot_cycle.py`, which it does not modify.

**Estimand.** Co-sign and the incumbent differ **only** on disagreement cases. With λ the registry's wrong-suggestion cost (λ = 1, frozen per cohort):
- the change in utility per router-fired prompt is P(disagree) × (λ·p − (1 − p));
- p is the share of disagreements in which the incumbent's suggestion is **not** a hit;
- so co-sign improves utility exactly when **p > 1/(1+λ)**, which is 0.5 at λ = 1.

**Promotion test (only `cosign-v1`).**
1. Reserve a fresh cohort of ≥ 60 disagreement cases from distinct sessions, under a frozen policy.
2. Label the cohort.
3. Exclude ambiguous labels. If more than 20% are ambiguous, the result is held.
4. Promote if the **one-sided exact Clopper–Pearson lower bound on p is above 1/(1+λ)** at α_k, and Laya's unavailable rate is ≤ 5%.

**Alpha spending.**
- Attempt k uses α_k = 0.05·2^−(k−1), so the total false-promotion risk stays ≤ 0.10 per (policy, instrument, Laya revision).
- Each attempt needs a **new cohort reserved after the previous one was consumed**.
- At n = 60 and α₁ = 0.05, the test needs ≥ 37/60. If the E5 point estimate p ≈ 0.67 holds, power is about 0.85.

**Demotion test (in `cosign`).**
- **Statistical:** a rolling cohort of ≥ 30 labeled live disagreements; demote if the one-sided upper bound at 0.10 falls below 1/(1+λ).
- **Operational:** demote if unavailable plus invalid exceeds 10% over 3 days.
- **Latency:** report-only for the first 14 days; timeouts are counted separately.
- **Pins:** a manual pin wins over both.

**Alternatives are report-only.** These include stricter floors, thresholded co-sign, veto, swap and router-else-Laya. They are scored on scoreboard pools with Horvitz–Thompson weights (inclusion probability × `sourceStratum` weight). Intervals come from a **session-cluster bootstrap**, and results carry a shortlist-constraint caveat. A stricter-floor win becomes a code-review recommendation.

**Outputs:**
- a cycle receipt bound to all version hashes;
- a mode change made through the registry mutation contract;
- a minimal **scoreboard** appended to the autolabel summary that the 08:00 automation reads.

The scoreboard shows:
- mode and arm counts;
- cohort status and test statistic;
- disagreement prevalence;
- the report-only alternatives;
- acceptance (secondary);
- Laya p50/p90 and timeout/unavailable rates by length bucket;
- the last verdict and any change.

### 4.7 Activation on the Mac (ops, after merge)

1. **Repoint the router.** Change the `settings.json` skill-router entry to the portable marketplace-clone path (re-run setup, or edit the one entry with a backup). Do not change `hooks.json`.
2. **Update both hosts.** Update the Claude and Codex plugins through the native lifecycle, run the marketplace update, rebuild the local skill map, and write `laya-runtime.json` from the runtime pins. Record the **live-collection cutover** timestamp, then verify in a fresh session.
3. **Day 0 is for instrument validation and evidence collection.**
   - Run the A8 smoke.
   - Run the backfill.
   - Run the outcomes join.
   - Reserve and label **bootstrap cohort 1**: 60 backfill disagreements from distinct sessions, roughly 60 case-labelings in a one-time batch.
   - Run the first test. If it passes, `skill-fit` is promoted to `cosign` that day. If it fails, it stays in shadow and live evidence keeps accruing.
4. **Daily.** Append labels, then the cycle, then the scoreboard, to `laya-autolabel.sh`. These run after the existing workflow steps, under the same lock, with a 10-minute sub-deadline and a call budget.
5. **Report.** Send Jim the first scoreboard.

## 5. Invariants

- **I1** The only user-visible change is cosign suppression in the treatment arm, and only after a passed gate. Workflow Arm A, the v2 pilot and critical decisions are unchanged.
- **I2** Any Laya failure, deadline expiry, exception or persistence failure emits the precomputed incumbent payload byte-for-byte, and output is flushed before anything else.
- **I3** Hooks persist no prompt text, paths or tokens. Text reaches only literal-loopback Laya, with redirects refused and only after the identity probe. Cloud annotators see only redactor output.
- **I4** Probe plus POST fits within one 800 ms deadline. The target is p50 ≤ 150 ms.
- **I5** The v2 pilot is unmodified: collection, the `source_digest()` files, labels, `pilot_cycle.py` and the 200 floor.
- **I6** Only the advisory tier changes mode automatically, through the single locked, revisioned and audited mutation path. A corrupt state means `shadow`. A pin suspends automation. Critical decisions are shadow-only by schema.
- **I7** Each cohort is frozen before labeling and tested once. Attempts follow alpha spending. Harness rows never enter a cohort.
- **I8** Only `cosign-v1` is auto-deployable. Receipts and transitions are bound to the policy, instrument and Laya revision hashes.
- **I9** The routing harness's incumbent gates pass unchanged.
- **I10** Plugins stay islands. `pilot_autolabel.py` and `decision_pilot_v2.py` are not edited.

## 6. Acceptance tests

- **A1 — router** (`tests/skill-map/test_router_skill_fit.js`, run in CI through a pytest wrapper):
  - cosign agree/disagree;
  - shadow and holdback;
  - every non-`ok` status;
  - a **hanging probe**;
  - **late HTTP after fallback**;
  - a **persistence failure** that leaves output intact;
  - an explicit request skips Laya;
  - a workflow message is preserved under suppression;
  - legacy row semantics;
  - records under 2 KB;
  - a corrupt state yields shadow;
  - a pinned state is respected;
  - deterministic arm assignment.
- **A2 — clients:**
  - byte-identical builder output on the shared fixture;
  - code-point and whitespace rules;
  - length buckets;
  - loopback literal-only (`localhost` is refused);
  - **external redirect refused**;
  - **endpoint change invalidates the probe cache**;
  - the shared deadline;
  - the 64 KiB response cap;
  - `choice` and probabilities validation.
- **A3 — schemas:**
  - fixtures validate in Node and Python;
  - text fields fail;
  - the critical tier set to `cosign` fails;
  - the label scoring-rule table is applied as specified.
- **A4 — backfill and outcomes:**
  - occurrence-key dedup;
  - the pre-cutover-only rule;
  - frozen-manifest reuse on resume;
  - repeated prompts resolved by timestamp;
  - slash commands and `Skill` invocations;
  - idempotency.
- **A5 — labeler:**
  - uniform within-stratum sampling with at most 1 case per session;
  - inclusion probabilities;
  - redaction before any model call;
  - guards reused;
  - cohort/scoreboard pool separation.
- **A6 — cycle and registry:**
  - the Clopper–Pearson gate;
  - alpha spending across attempts;
  - one test per cohort;
  - a fresh cohort is required;
  - only `cosign-v1` can deploy;
  - the ambiguity hold;
  - **concurrent CLI and cycle writes**;
  - an **interrupted update is recovered** from the audit;
  - stale-revision rejection;
  - HT and cluster-bootstrap report math;
  - no writes to workflow-v2 paths.
- **A7 — full suite:** `pytest -q`, all `tests/**/*.js`, `validate_skill_map.py --check-stale`, the harness `--check`, `bump_version.py --check` and the parity tests.
- **A8 — Mac smoke:**
  - backfill on ≥ 50 real prompts, with p50/p90 and agreement **by length bucket**;
  - **actual tokenizer** measurement of client versus server truncation on those requests (character caps are heuristics);
  - a cold start and a concurrent pair;
  - the canary token is absent from Laya's log and cache;
  - the scoreboard renders.

## 7. Implementation and parallelization

**Three parallel Sonnet 5.5 lanes**, each with disjoint ownership.

The coordinator (Opus) first commits the contract:
- schemas and fixtures;
- the registry files;
- `lexicalShortlist()`;
- both instrument builders;
- the stubs.

Each lane then works in its own worktree and branch, with task-graph v2 validation and begin/finalize receipts.

| Lane | Owns |
|---|---|
| L1 Router/runtime (JS) | `hooks/lib/laya-client.js`, `hooks/lib/decision-registry.js` (read-only state reader), async `skill-router.js`, `tests/skill-map/test_router_skill_fit.js`, `tests/rhize-context-manager/test_laya_client.js`, and the pytest wrapper `tests/skill-map/test_node_suites.py` |
| L2 Evidence + labels (Py) | `scripts/typed_decisions/{records,laya_choice,transcripts,backfill,outcomes,skillfit_labels}.py`, `scripts/typed_decisions/route_replay.js`, tests |
| L3 Research/registry/report (Py) | `scripts/typed_decisions/{decision_registry,cohorts,scoreboard}.py`, `evals/typed-decision/decision_cycle.py`, tests; it imports L2's `records.py` (fixtures until merge) |

The coordinator also owns:
- integration (L2 → L1 → L3);
- docs: the `typed-decision-layer.md` policy, `docs/typed-decisions/skill-fit.md`, and GUIDE/README;
- the full suite;
- the minor version bump of `rhize-context-manager` with its CHANGELOG entry;
- impact-map reconciliation;
- the final reviews;
- the push;
- Mac activation.

## 8. Out of scope

- instrument-variant search;
- `agent-brief-skill` co-sign;
- Codex-host outcomes;
- the workflow v3 cohort with `choice` (a separate spike, recommended to the v2 owners);
- a learned calibrator;
- context-retention and graph wiring;
- more decisions.

## 10. Fable advisory review: reconciliation

**Verdict: approve-with-changes.** Every finding was verified against code or data before being accepted.

| Finding | Disposition |
|---|---|
| B1: window overflow | Re-scoped to major. `build_sequence` budgets the head and options separately and keeps the start of the state. The plan sets explicit caps, a truncation flag, length buckets and a tokenizer measurement. |
| M1: gate units | Accepted. The gate is now the exact binomial test on disagreements in §4.6. |
| M2: stricter-floor baseline | Measured (score ≥ 3: 0.76, no hits lost). Kept as a report-only recommendation. |
| M3 | Caveats added. |
| M4 | `lexicalShortlist()` and `readMap()` descriptions are in the contract. |
| M5 | Identity probe and canary added. |
| M6 | `hooks.json` change dropped; repoint `settings.json` instead. |
| M7 | Superseded by Codex B1: cohorts. |
| M8 | Prefix scanner added, using `choose_match`; slash commands are counted. |
| M9 | Settle-once with an awaited flush. |
| m1–m8 and scope cuts | Accepted. |

## 11. Codex review: reconciliation (job `fe1383b9`, gpt-6.1-sol, high)

**Verdict: implement-with-changes.** Every finding was accepted.

| Finding | Disposition |
|---|---|
| BLOCKER: holdout reuse | Persistent frozen cohorts, each tested once, with alpha spending across attempts (§4.4 cohort ledger, §4.6). |
| Sampling and bootstrap | The estimand is restricted to disagreements (exact binomial). Sampling is uniform within stratum with at most 1 case per session, and inclusion probabilities are recorded. `sourceStratum` is preserved. Report-only alternatives use HT weights and a session-cluster bootstrap. |
| Evaluated vs deployed policy | Only `cosign-v1` is auto-deployable. Transitions and receipts are bound to policy, instrument and Laya hashes. |
| Async failure boundaries | One shared deadline covering probe and POST, a precomputed payload, settle-once, an awaited write before persistence, and bounded parsing. Tests cover a hanging probe, late completion and logging failure. |
| Loopback and redirects | Redirects refused in both clients, literal loopback only, probe cache keyed by endpoint and model, and the trust assumption stated. |
| Day-0 promotion claim | Reworded. Day 0 is validation plus a reserved 60-case bootstrap cohort, and promotion happens only if that cohort passes. |
| Registry transaction | One locked, revisioned, atomic, audited mutation path with recovery. A pin suspends automation. |
| Evidence identity and replay | `occurrenceKey` dedup, a pre-cutover backfill boundary, a frozen manifest on resume, and full version hashes on every record. |
| Label semantics | Scoring-rule table frozen. Labels are shortlist-constrained, with no recall claims. |
| Length telemetry (minor) | `promptLengthBucket` added, with code-point parity rules. |
| Token budget (minor) | Tokenizer measurement added to A8; character caps are heuristics. |

## 12. Implementation reconciliation (2026-10-11)

Implemented as planned: a coordinator contract commit, then three parallel Sonnet lanes in isolated worktrees (task graph v2 validated: one wave, three isolated writers; observational receipt reserved), then coordinator integration.

**Changed paths:**
- Contract (coordinator):
  - `hooks/lib/{laya-instrument,typed-decisions}.js` and route-core `lexicalShortlist()`;
  - `scripts/typed_decisions/{__init__,contract,instrument,records}.py`;
  - seven schemas in `rhize-context-manager/schemas/`;
  - `catalog/decision-registry.json`;
  - fixtures and `make_fixtures.py`;
  - `tests/skill-map/test_node_suites.py` (every Node suite now runs in CI).
- L1:
  - `hooks/lib/{laya-client,decision-registry}.js`;
  - the async, settle-once `hooks/skill-router.js`;
  - `tests/skill-map/test_{router_skill_fit,laya_client,decision_registry}.js`;
  - the retired-flag case in `test_router.js`.
- L2:
  - `scripts/typed_decisions/{laya_choice,transcripts,backfill,outcomes,skillfit_labels,evidence_fs}.py` and `route_replay.js`;
  - two test files.
- L3:
  - `scripts/typed_decisions/{decision_registry,cohorts,scoreboard,locked_io}.py`;
  - `evals/typed-decision/decision_cycle.py`;
  - three test files.
- Integration (coordinator):
  - one store symlink policy, anchored at the store root (macOS `/tmp` is a symlink, and the first real backfill failed on it);
  - private intermediate directories;
  - the labeler reads the cohort-meta inclusion probability;
  - safe failure reasons;
  - the background-observer skip (router and backfill);
  - docs (`typed-decision-layer.md` policy, `docs/typed-decisions/skill-fit.md`, GUIDE, README, CHANGELOG);
  - `rhize-context-manager` 0.46.0.

**Deviations from the plan, all accepted:**
- **L1:**
  - the cosign state must carry this code's policy and instrument hashes, or it reads as shadow (enforces I8);
  - an env-proxy guard;
  - a module-load fallback to the legacy router;
  - the cosign suppression that leaves no message goes through the 1-in-20 silence sample.
- **L2:** backfill does not persist failed Laya calls (they are retried next run), and a resume is refused unless every frozen hash matches.
- **L3:**
  - operational and latency demotion need at least 20 live records in the window;
  - demotion windows start at the last promotion;
  - a manual CLI cosign is allowed with a null `cohortId`, still bound to the policy and instrument hashes.
- **New finding, the background-observer skip:** this was not in the plan. Real traffic showed 83% of router fires were ECC homunculus machine sessions. Skipping them withholds advice only from a background observer.

**Real-data smoke** (Mac, 2026-10-11, temporary store, nothing activated):
- **Backfill coverage:** of 2,364 log rows in the window, 1,425 were recovered from transcripts. The 939 not recovered break down as 492 legacy rows without `session_id`, 442 prompts not found and 5 missing transcripts.
- **Background observer:** 1,134 of the 1,366 replayed fires were background-observer sessions.
- **Interactive traffic:** 232 fires (about 15 a day). Laya disagreed on 199 of them (86%), spread across 192 distinct sessions. That is enough for the 60-case bootstrap cohort.
- **Laya latency:** p50 89–117 ms and p90 117–137 ms across length buckets. 210 of 262 prompts exceeded 1,200 characters and were truncated by design.
- **Live hook:** the run through the real Laya took 184–373 ms end to end (cold to warm), against about 80 ms for a non-eligible prompt.

## 13. Final reviews (2026-10-11)

**Fable** (merge-after-fixes): three majors, four minors and parity nits. All were fixed in `9f84919`:
- cosign is bound to policy, instrument and Laya revision in both readers, and the cycle demotes honestly;
- the observer skip is cwd-only;
- an explicit `--manual-override` is required;
- backfill failure counts are kept;
- a failed promotion is retried;
- the probe cache is written after the flush;
- reader parity is fixed.

**Codex**, two parallel jobs:
- **Part A, runtime** (`1b8c5dae`, merge-after-fixes):
  - the env-proxy exemption must match the exact endpoint host;
  - an overriding `RHIZE_LAYA_ENDPOINT` drops cosign to shadow unless `RHIZE_LAYA_ENDPOINT_AUTHORITY=1` (test harnesses);
  - the Laya budget now starts before the optional preparation.
- **Part B, authority** (`bbdd816e`, hold):
  - **blocker:** ambiguous labels now stay in n, never in x. Every consumed cohort spends α, held ones included; this reverses the Fable m3 "held spends no α" change, because a hold is decided after labeling.
  - live and backfill attempts are each counted once in the unavailability hold;
  - reserving and promoting require the cohort's revision to equal the running checkpoint, and mutation refuses a binding to any other revision;
  - a blocked recovery stops every mutation;
  - evaluation holds when the frozen gate shares are missing.

  All were fixed and tested, then sent back to Codex for verification.
