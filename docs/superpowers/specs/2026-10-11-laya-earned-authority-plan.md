# Laya decision layer: earned authority (plan + impact map)

**Status:** v2. This version reconciles the Fable advisory review (§10); Codex review is pending. Nothing here is implemented yet.

**Branch:** `claude/laya-earned-authority`

**Authority:** Jim, 2026-10-11:

> implement our decision layer strategy fully now and try to recursively implement and prove it as we go using tools like the autoresearch library … optimally integrating Laya's decision-making capabilities into our daily operations.

He also asked for:
- a Fable + Codex review before implementation;
- Sonnet 5.5 parallel lanes, but only if they are recommended;
- a final Fable + Codex review before `main`.

## 1. What we measured (2026-10-11, all read-only)

All figures below were measured on Jim's Mac today. The replays are exploratory and use small samples. None of them is a release-gate result.

| # | Finding | Evidence |
|---|---|---|
| E1 | **Laya is already in daily use.** The v2 workflow pilot has 349 observations since 2026-09-28: 179 scored in shadow, 163 excluded (operational, prebound or continuation) and 4 unavailable. | `~/.local/share/rhize/workflow-selection/pilot/v2/*` |
| E2 | **The workflow labels are few and lopsided.** There are 75 AI-reviewed taxonomy labels; 73 have an explicit choice (58 general, 13 none, 2 content). Research is held at the 200-label floor. | `taxonomy-labels/`, 07:30 `media.rhize.laya-autolabel` |
| E3 | **The workflow instrument is broken, and data volume is not the cause.** `request_for()` asks three *independent* `noul` questions using only `{eventKind, action, domain, exclusions}`, then takes the argmax. Laya picks `content` 70 of 73 times, so it agrees with the labels **2/73 = 2.7%** of the time. | replay via `127.0.0.1:8000/v1/systemone` |
| E4 | **A better question helps, but still loses to trivial baselines.** <br>• Laya's native **`choice`** question type on the same fields agrees **47/73 = 64.4%**. <br>• Adding the redacted task text gives **21/35 = 60%** (only 35 cases have a request snapshot). <br>• Both lose to always-`general` (**79.5%**). <br>• A 3-line rule scores ~91%, but that is in-sample: I fit it after seeing the labels. | same replay |
| E5 | **Skill fit is where Laya helps.** Measured on the 279 routing-harness rows (frozen third-party snapshot), in the table below. | `evals/skill-map-routing`, Laya replay |
| E6 | **Laya itself is fast.** A direct HTTP call takes **59 ms p50 / 92 ms p90** for the short harness prompts. The pilot's 1.57 s p50 is mostly the cost of launching Python for every call. Long-prompt latency has not been measured yet (see §4.2). | replay timings |
| E7 | **What the checkpoint is.** The typed-decisions checkpoint is a ModernBERT-large model with an RL head. <br>• `build_sequence` puts the instructions and options in a **192-token head**. Each option is capped at 48 tokens and shrunk to about 29 tokens when there are 6 options. <br>• The state gets the remaining room up to **512 tokens** (about 317), keeping the start of the text. <br>• It supports `choice`, `score` and `noul` questions; `choice` returns per-option `probabilities`. <br>• It makes no network calls and does not log requests (`managed-service.log` is 397 bytes). `/health` returns `{"loaded":["typed-decisions"]}`. <br>• There is no fine-tune API. | `laya` 0.3.20, checkpoint `55cf4c4` |
| E8 | **The skill-fit shadow never runs.** <br>• It needs `RHIZE_LAYA_SKILL_SHADOW=1`, which is unset. <br>• It is skipped whenever workflow selection is attempted. <br>• Laya only ever sees hashed ids and router-matched tokens, which is circular. <br>• Its shortlist uses the *floored* `scoreCandidates()`. | `skill-router.js:84-127` |
| E9 | **None of the routing fixes are live.** <br>• The `settings.json` skill-router hook runs `node <repo checkout>/…/skill-router.js`. <br>• That checkout is on `codex/laya-transcript-size-limit` (99083e5), 24 commits behind `main`. <br>• It suggested `completed-branch-promotion` from stack-only matches at 17:51 today. <br>• The setup orchestrator already supports a portable path, `$HOME/.claude/plugins/marketplaces/<clone>/<plugin>`, that follows `claude plugin marketplace update`. | Mac settings; `rhize-core/scripts/setup_orchestrator.py:253-272` |
| E10 | **There is a large backlog of real prompts to learn from.** <br>• Since 2026-09-27 the router has fired **2,235** times, about **150 per day**, plus 110 sampled silences (a 1-in-20 sample). <br>• Each row carries the raw `session_id` and `context_hash = sha256(prompt)[:16]`. <br>• Workflow outcomes are 183/183 `undetermined`. | `~/.claude/context-manager/suggestion-log.jsonl` |

**E5 in detail.** The baseline is the current router. The other policies are:
- *Stricter floor*: the router with a higher minimum score.
- *Co-sign*: a suggestion is shown only when Laya's `choice` independently names the same skill. Laya chooses from the top 5 unfloored lexical candidates plus `none`, given the prompt text.

| Policy | Fires | Precision | Hits | Wrong | False fires |
|---|---|---|---|---|---|
| Router (incumbent) | 33 | 0.67 | 22 | 8 | 3 |
| Router, score ≥ 3 | 29 | 0.76 | 22 | 6 | 1 |
| Router, score ≥ 3.5 | 9 | 0.89 | 8 | 1 | 0 |
| Co-sign | 21 | 0.86 | 18 | 3 | 0 |
| Co-sign + score ≥ 3 | 21 | 0.86 | 18 | 3 | 0 |
| Laya replaces the router (p ≥ 0.4) | 65 | 0.45 | — | — | — |

Notes on E5:
- **Agreement carries the signal.** There are 12 disagreements. The router was right in 4 of them and Laya's alternative in 5. Agreement vs hit gives Fisher p ≈ 0.0055.
- **Caveats.** The prompts are authored trigger cases that share vocabulary with skill descriptions, and they are short (p90 148 characters). The router's thresholds were also tuned on this same corpus. Treat E5 as a hypothesis; backfill on real prompts is the real test.
- **Descriptions** came from `generated/skill-map.static.json` plus the `description` fields in `third_party_snapshot.json`.

## 2. Thesis

Laya's problem has been **how it is asked**, not how much data it gets:
- It is a text classifier, but it has been given category labels and hashed ids.
- Its independent yes/no scores are not comparable across options.

The real question is "**for which decision does Laya beat the incumbent and the trivial baselines?**" That has to be answered continuously from live evidence, so authority is earned and lost automatically.

This plan does five things:
1. **Fixes the instrument:** native `choice`, a bounded prompt head, candidate descriptions and a direct HTTP call.
2. **Gives Laya one real job:** co-signing skill suggestions. It is high-volume, low-risk and advisory, and Laya has measured value there.
3. **Bootstraps evidence from real traffic on day one:** backfill plus a disagreement-focused labeling batch, so the first promotion decision does not wait weeks.
4. **Builds a small generic registry plus research loop,** so later decisions plug in.
5. **Keeps workflow fit with Arm A,** and critical decisions in schema-enforced shadow.

## 3. Policy changes Jim must accept

**P-A — task text goes to the loopback Laya server.** This applies to the advisory tier only. `docs/typed-decision-layer.md` currently says "do not send prompts … to Laya." The change:
- **What is sent:** the first ≤1,200 characters of the prompt, which matches Laya's ~317-token state budget.
- **Where it goes:** the **loopback, offline** Laya server, and only after a cached identity probe passes (`/health` lists `typed-decisions`).
- **What is kept:** the text is never persisted. Records keep hashes, ids and probabilities only.
- **No hook-side redaction.** The text never leaves the machine, and transcripts already hold it on the same disk. Cloud annotators still only see `pilot_redaction.sanitize` output.

**P-B — AI-reviewed labels are enough for the advisory tier.** These are two annotators plus a Fable reviewer, as for workflow. The tier uses the disagreement-based gates in §4.6. The workflow and critical tiers keep their current gates. The workflow 200-label floor is **unchanged**. Separately, a small optional weekly human-adjudicated stratum (`basis:"human_adjudicated"`) calibrates the AI labeler against Jim's intent.

**P-C — mode changes are automatic for the advisory tier only.** Each change is audited, reversible with a single CLI command, and allowed only through the gate.

## 4. Design

### 4.1 Registry and modes (kept small)

| Piece | Location | Notes |
|---|---|---|
| Shipped default | `rhize-context-manager/config/decision-registry.json` | Validated by `schemas/decision-registry.schema.json` |
| Machine-local state | `~/.local/share/rhize/typed-decisions/registry-state.json` | Validated by `schemas/decision-registry-state.schema.json` |
| Audit trail | `registry-audit.jsonl` | Every mode change appends one line |

Only `decision_cycle.py` and `decision_registry.py set-mode` may write the state. If the state file is missing, the shipped default applies. **If it is corrupt or unreadable, the mode is `shadow`.**

The modes are `off`, `shadow` and `cosign`. Under `cosign`, the incumbent's output is shown only when the challenger agrees. A permanent randomized **holdback** (default 10%, propensity logged) uses the incumbent alone; it exists to measure acceptance effects.

The tier enum is `advisory`, `workflow` and `critical`. The schema rejects any mode other than `shadow`/`off` for `critical`.

Only two decisions are registered:

| Decision | Tier | Default mode | Reachable modes |
|---|---|---|---|
| `skill-fit` | advisory | **`shadow`** | off, shadow, cosign |
| `workflow-fit` | workflow | `shadow` | shadow |

`workflow-fit` is a reference entry only: the v2 pilot keeps its own machinery. Other decisions are added when they are actually wired.

`skill-fit` starts in **shadow**, and automatic promotion is expected on day zero or one (§4.6). The reason: labels judge a prompt and its candidates regardless of arm, so shadow yields the same promotion evidence as cosign. Starting in cosign would only add the confounded acceptance signal early. If the first gate passes, cosign switches on automatically, so "prove as we go" happens on real traffic within the first cycle.

### 4.2 Laya client v2 and instrument `laya-choice-v1`

**`hooks/lib/laya-client.js`** (Node ≥ 18, using global `fetch` with `AbortController`):
- Allows loopback URLs only.
- **Identity probe:** `GET /health` must list `typed-decisions`. The result is cached for 60 s in `~/.local/share/rhize/typed-decisions/laya-health.json` (mode 0600). Prompt text is **never** sent unless the probe has passed.
- Makes one `POST /v1/systemone` with a **hard abort at `latencyBudgetMs`** (default 800 ms).
- Validates the response: `routing.model` matches, and the `choice` answer has per-option `probabilities`.
- Never throws. It returns `{status: ok|timeout|unavailable|invalid|identity_failed, …}`.

**`scripts/typed_decisions/laya_choice.py`** is the Python mirror used for replay and research.

**Request builder.** There is one reference implementation, plus a shared fixture `tests/rhize-context-manager/fixtures/typed-decisions/laya-choice-requests.json`. The fixture pins byte-identical requests from Node and Python. It covers fewer than 5 candidates, unicode, long descriptions and empty descriptions, and includes a response fixture.

The instrument:
- **State:** `{request: <prompt head, ≤1,200 chars, cut at a whitespace boundary>}`.
- **Question:** a single `choice` question, `skill`, asking "Which skill, if any, should be loaded to handle `request`?"
- **Criteria:** `s0..s{k-1}` = `"<skill-name>: <description[:120]>"`, plus `none` = "none of these skills is needed; answer directly".
- **Truncation flag:** the record notes `truncated:true` whenever the prompt head was cut.
- **`instrumentSha256`** covers the template.

**Acceptance:**
- The longest fixture request stays inside Laya's budget. The test checks this with the vendored tokenizer when it is available, otherwise with a conservative character proxy.
- A8 reports agreement and latency **by prompt-length bucket**: <200, 200–600, 600–1,200 and >1,200 characters.

### 4.3 Skill-fit in `skill-router.js`

1. `main` becomes **async**. Incumbent `routeFromIndex()` runs unchanged.
2. If the incumbent fired, the prompt is not an explicit skill request, and the mode is not `off`, the hook builds the shortlist with the new exported **`lexicalShortlist(index, promptTokens, incumbentId, k=5)`** in `route-core.js`.
   - It is unfloored: ranking is by matched non-partial weight, and the incumbent is forced in.
   - It is pinned by a fixture.
   - The replay runner uses it too.
3. Descriptions come from the existing `readMap()` (resolved, falling back to static), parsed once per hook run.
4. The arm is `sha256(sessionHash‖promptHash) mod 10000 < holdback·10000`. That band is holdback; everything else is treatment.
5. What gets shown:

| Situation | Shown |
|---|---|
| Treatment arm, mode `cosign`, Laya agrees with the incumbent | the incumbent |
| Treatment arm, mode `cosign`, Laya disagrees or picks `none` | nothing |
| `shadow` mode, or holdback arm | the incumbent |
| Any Laya status other than `ok` | the incumbent (fail-open) |
| A timer at the budget expires before Laya returns, or anything unexpected happens | the incumbent |

The timer guarantees an emission. Records are written **after** the output has been written.

6. `process.exit` happens only after stdout has flushed. The required host hook timeout is ≥ 8 s, which covers the 4.5 s workflow bridge, the 0.8 s Laya call and startup. That is documented in GUIDE and checked in A1.
7. The workflow bridge logic is untouched.
   - The old `workflowAttempted` gate on the Laya call is removed. It no longer competes with the bridge, because it is a capped HTTP call, not a Python spawn.
   - The content-engine overlap suppression stays.
8. The **legacy `suggestion-log.jsonl` row logs what was *emitted*** (null when suppressed). It adds `typed_mode`, `typed_arm`, `typed_status` and `typed_agrees`. GUIDE documents the expected drop in legacy fire rate under cosign.
9. Every eligible prompt appends one decision record (§4.4). Records stay under 2 KB so that `appendFileSync` stays atomic.

Router-silent prompts are not sent to Laya live. "Laya adds missed skills" is evaluated only from backfill, with silence weights (§4.6).

### 4.4 Contract (committed by the coordinator before any lane starts)

All data is machine-local under `~/.local/share/rhize/typed-decisions/<decision>/`:
- 0700 directories and 0600 JSONL files, partitioned by UTC day;
- schemas in `rhize-context-manager/schemas/`;
- fixtures in `tests/rhize-context-manager/fixtures/typed-decisions/`.

**`rhize-typed-decision-record-v1`**:
- Identity: `decision`, `decisionId` (uuid4 hex), `ts`, `promptTs`, `host`, `basis` (`live` | `backfill`).
- Hashes: `sessionHash` = sha256(session_id) and `promptHash` = sha256(prompt), the same functions as workflow receipts. Backfill rows whose full hash cannot be recovered use `promptHashPrefix`.
- Provenance: `registrySha256`, `instrument`, `instrumentSha256`, `routerSourceSha256`.
- Assignment: `mode`, `arm`, `propensity`, `stratumWeight` (1 for fired prompts, 20 for sampled silences).
- Decision: `incumbent {skillId, score}` or null, `shortlist` (≤5 ids), `laya {status, choice, probabilities, latencyMs, truncated, reason}`, `emitted`.
- **No text, paths or tokens. `additionalProperties: false`.**

**`rhize-typed-decision-outcome-v1`**:
- Fields: `decisionId`, `outcome`, `skillInvoked`, `via` (`skill_tool` | `slash_command`), `latencyTurns`, `joinedAt`, `transcriptSha256`.
- `outcome` is one of: `invoked_emitted`, `invoked_other_shortlisted`, `invoked_unlisted`, `none_invoked`, `transcript_unavailable`.
- This is a **secondary signal only**, because it is confounded by the suggestion effect.

**`rhize-typed-decision-label-v1`**:
- Fields: `decisionId`, `basis` (`ai_model_reviewed` | `human_adjudicated` | `harness`), `bestSkill` (an id or `none`), `acceptable`, `annotators`, `reviewer`, `evidenceSha256`, `labeledAt`.
- Labels are arm-independent, so every policy is scored offline on the same cases.

The contract commit also includes:
- the **registry-state and audit schemas**;
- `lexicalShortlist()` with its fixture;
- the request-builder reference implementation and fixture;
- the prefix-transcript-scanner interface (§4.5).

### 4.5 Evidence pipeline (L2)

**`scripts/typed_decisions/transcripts.py`** is a new module owned by L2. `pilot_autolabel.py` is **not** edited.
- It provides a prefix-capable scanner (`sha256(text)[:16]` within one session).
- It imports and reuses `transcript_message` and `choose_match` (timestamp tolerance resolves repeated prompts such as "continue") from `pilot_autolabel`, and `sanitize` from `pilot_redaction`.
- Real 64-bit collisions are negligible. Identical repeated prompts are disambiguated by timestamp, not refused.

**`backfill.py`** — for router rows since 2026-09-27 (about 2,235 fires and 110 silences):
1. Recover each turn from its transcript.
2. Replay the **current** incumbent and `laya-choice-v1` through `route_replay.js`, which uses `lexicalShortlist`.
3. Write records with `basis:"backfill"`, `mode:"shadow"`, `emitted:null`.
- Backfill records count for label-based ΔU, because they are deterministic replays of real prompts. They **never** count for acceptance or causal claims.
- The run is bounded and resumable, with a call budget per run.

**`outcomes.py`** — joins records to `Skill` tool_use events **and** to skill slash-command invocations in the same session after `promptTs`, within the next 3 user turns or 30 minutes. It is idempotent. Codex transcripts are marked `transcript_unavailable` in v1.

**`skillfit_labels.py`** — folded into L2. It reuses the `pilot_autolabel` primitives (`model_command`, `child_env`, auth handling and the `run_process` guards) by import.

| Run | Budget | What it labels |
|---|---|---|
| Daily | ≤ 12 cases | Stratified: **disagreements oversampled to ≥ 50%**, then agreements, then a Laya-only pick on a silence (weighted) |
| One-time day-0 bootstrap | ≤ 40 cases | Backfill disagreements |

Each case gives the annotators the redacted prompt, the preceding context and the candidate set with descriptions. Two annotators answer under a schema; a Fable reviewer resolves splits.

**Harness labels.** The 279 harness rows become `basis:"harness"` labels. They are a fixed regression gate and are never part of a holdout.

### 4.6 Recursive research loop (`evals/typed-decision/decision_cycle.py`, L3)

This is an autoresearch-style keep/discard loop and a sibling of `pilot_cycle.py`, which it does not modify. v1 handles `skill-fit` only.

**Candidates.** All are decoding policies computed from **logged** probabilities, so no new Laya calls are needed:
- the incumbent;
- never-fire;
- **the incumbent at stricter floors** (score ≥ 3, ≥ 3.5);
- co-sign;
- co-sign at p ≥ τ, for τ ∈ {0.3, 0.4, 0.5};
- veto-only;
- co-sign-or-swap (show Laya's pick on disagreement);
- router-else-Laya at τ, evaluated with silence weights.

Instrument-variant search (wording, description length, k) is deferred.

**Metric.** Utility per eligible prompt: U = hits − λ·(wrong + false fires), with λ = 1 set in the registry. Precision and recall are also reported, with Wilson intervals. The paired bootstrap uses 2,000 resamples and a fixed seed. Stratum weights apply.

**Splits** follow the `research.py` contract:
- Order is by `promptTs`. The newest 25% of labeled cases (live and backfill) form the holdout.
- The dev split picks **one** candidate per cycle, recorded as a dev keep.
- The holdout is locked **per dataset hash** (`check_holdout_authority` semantics): **one holdout test per cycle per decision**.
- Between holdout tests there must be at least 7 days or at least 20 new labeled disagreements.
- Harness labels form a regression gate only.

**Gates for the advisory tier.** Defaults live in the registry and are tunable:

| Action | Conditions (all must hold unless marked "or") |
|---|---|
| **Promote** shadow → cosign | ≥ 20 labeled **disagreement** cases in the holdout; **and** the 80% paired-bootstrap lower bound on ΔU vs the incumbent is > 0; **and** harness precision ≥ the incumbent's; **and** unavailable ≤ 5% |
| **Demote** cosign → shadow | Over a rolling 14 days with ≥ 15 labeled disagreements, the 80% upper bound on ΔU is < 0; **or** unavailable > 10% |

Timeouts are counted separately. Demotion on latency (p90 over budget for 3 days) is **report-only for the first 14 days**, to avoid demoting on MPS contention or cold starts.

**Floor baselines.** If a stricter-floor baseline beats both co-sign and the incumbent, the cycle **recommends** a router floor change in the scoreboard. That change ships through normal code review and the harness. It is never auto-applied.

**Outputs:**
- a cycle receipt;
- a mode change for the advisory tier only, applied through `decision_registry.py`;
- a minimal **scoreboard** (`scripts/typed_decisions/scoreboard.py`) appended to the autolabel summary that the 08:00 Codex automation already reads. It shows:
  - mode and arm counts;
  - labeled precision and recall with CIs, and the disagreement count;
  - acceptance (secondary);
  - Laya p50/p90 and its timeout/unavailable rates by length bucket;
  - the last verdict, and any change applied.

### 4.7 Activation on the Mac (ops, after merge)

1. **Repoint the router.** Change Jim's `settings.json` skill-router entry from the dev checkout to the portable marketplace-clone path. Do this either by re-running the setup orchestrator against the marketplace source or by editing that one entry (with a backup). This needs no change to `hooks.json` and no new trust prompt for other users.
2. **Update both hosts.** Update the Claude and Codex plugins through the native lifecycle, run `claude plugin marketplace update`, rebuild the local skill map, and verify in a fresh session.
3. **Day-0 bootstrap.** Run backfill, then the outcomes join, then the bootstrap labels (≤ 40), then the first cycle.
4. **Daily steps.** Append labels → cycle → scoreboard to `laya-autolabel.sh`. They run **after** the existing workflow steps, under the same lock, with their own sub-deadline of 10 minutes and a Laya-call budget.
5. Send Jim the first scoreboard.

## 5. Invariants

- **I1:** The only user-visible change is `skill-fit` cosign suppression in the treatment arm, after promotion. Workflow Arm A, the v2 pilot and critical decisions are unchanged.
- **I2:** Any Laya failure, a timer expiry or any hook error emits the incumbent byte-for-byte, and the failure is recorded.
- **I3:**
  - Hooks persist no prompt text, paths or tokens.
  - Text reaches only loopback Laya, and only after the identity probe passes.
  - Cloud annotators receive text only through the shared redactor.
- **I4:** Laya adds at most `latencyBudgetMs` (800 ms) to the hook, enforced by a hard cap. The target is p50 ≤ 150 ms.
- **I5:** The v2 pilot is unmodified: collection, the files behind `source_digest()`, labels, `pilot_cycle.py` and the 200 floor.
- **I6:**
  - Only advisory-tier decisions change mode automatically.
  - Every change is audited and reversible.
  - Corrupt state means `shadow`.
  - The schema rejects any non-shadow mode on the critical tier.
- **I7:** The holdout is locked per dataset, with one test per cycle. Harness rows never enter it.
- **I8:** The routing harness's incumbent gates pass unchanged.
- **I9:** Plugins stay islands. `pilot_autolabel.py` and `decision_pilot_v2.py` are not edited.

## 6. Acceptance tests

- **A1 — router** (`tests/skill-map/test_router_skill_fit.js`):
  - cosign suppresses on disagreement and emits on agreement;
  - timeout, unavailable, invalid and identity-failure all emit the incumbent;
  - when the timer fires before the HTTP call returns, the incumbent is emitted;
  - shadow and holdback never change output;
  - arm assignment is deterministic;
  - explicit skill requests skip Laya;
  - the legacy row logs `emitted`;
  - records are under 2 KB;
  - a corrupt registry state means shadow.
- **A2 — client:**
  - identical request bytes from Node and Python on the shared fixture;
  - loopback-only;
  - abort at budget;
  - probe caching;
  - `choice` and `probabilities` validation;
  - the longest request stays within budget.
- **A3 — schemas:** record, outcome, label, registry and registry-state schemas validate their fixtures in Node and Python. A record with a text field fails. The critical tier set to cosign fails.
- **A4 — backfill and outcomes** on fixture transcripts and log rows:
  - repeated prompts are resolved by timestamp;
  - slash-command and `Skill` invocations are both joined;
  - the join is idempotent;
  - the run is budgeted and resumable.
- **A5 — labeler:**
  - deterministic stratified sample with disagreement oversampling;
  - redaction happens before any model call;
  - guards are reused;
  - labels validate;
  - the bootstrap budget is respected.
- **A6 — `decision_cycle`:**
  - holds below the gate;
  - one holdout test per cycle, with the dataset lock and the spacing rule;
  - promotes and demotes through the gate only;
  - refuses the critical tier;
  - stricter-floor wins become recommendations only;
  - silence weights are applied;
  - the ledger is append-only;
  - nothing is written to workflow-v2 paths.
- **A7 — full suite:** full `pytest -q`, all `tests/**/*.js`, `validate_skill_map.py --check-stale`, the harness `--check`, `bump_version.py --check` and the parity tests.
- **A8 — live smoke on the Mac after merge:**
  - backfill on ≥ 50 real prompts, with p50/p90 and agreement by length bucket;
  - one cold-start call and one concurrent call (two sessions);
  - a canary: send a unique token, then confirm it is absent from Laya's log and cache directories;
  - the scoreboard renders.

## 7. Implementation plan and parallelization

**Recommendation: three parallel Sonnet 5.5 lanes,** with disjoint file ownership. Before dispatch, the coordinator (Opus) commits the contract:
- schemas and fixtures;
- the registry files;
- `lexicalShortlist()`;
- the request-builder reference implementation;
- the scanner interface stub.

Each lane gets its own worktree and branch, task-graph v2 validation, and begin/finalize receipts, per `rhize-ops:parallel-agent-optimization`.

| Lane | Owns | Depends on |
|---|---|---|
| L1 Router/runtime (JS) | `hooks/lib/laya-client.js`, `hooks/lib/decision-registry.js`, async `skill-router.js`, `tests/skill-map/test_router_skill_fit.js`, `tests/rhize-context-manager/test_laya_client*.js` | contract |
| L2 Evidence + labels (Py) | `scripts/typed_decisions/{records,laya_choice,transcripts,backfill,outcomes,skillfit_labels}.py`, `scripts/typed_decisions/route_replay.js`, tests | contract |
| L3 Research/report (Py) | `evals/typed-decision/decision_cycle.py`, `scripts/typed_decisions/{decision_registry,scoreboard}.py`, tests; imports L2's `records.py` (stubbed by fixtures until merge) | contract |

The coordinator owns:
- integration, as fast-forward merges in the order L2 → L1 → L3;
- docs: the `docs/typed-decision-layer.md` policy update (P-A/B/C), `docs/typed-decisions/skill-fit.md`, and the GUIDE/README hook-timeout notes;
- the full suite;
- `bump_version.py --plugin rhize-context-manager --level minor` with a CHANGELOG entry;
- impact-map reconciliation;
- the final Fable + Codex review;
- the push to `main`;
- the Mac activation.

Executors never push.

## 8. Out of scope (next steps)

- Instrument-variant search, which needs a text replay.
- `agent-brief-skill` co-sign.
- Codex-host outcomes.
- A workflow v3 cohort with the `choice` instrument. This is a separate spike, recommended to the v2 owners because of E3/E4.
- A learned calibrator.
- Context-retention and graph wiring.
- Registering further decisions.

## 9. Questions for Codex

1. Is shadow-first with day-0 bootstrap promotion sound? Can the disagreement-based gate be gamed, or is it too weak at 20 cases?
2. Is the holdout contract (per-dataset lock, one test per cycle, spacing) equivalent to or stronger than `research.py`'s? Is mixing backfill and live cases in a time-ordered holdout acceptable for label-based ΔU?
3. P-A: are the identity probe and the no-redaction rationale adequate?
4. The async hook: is there any path where the incumbent fails to emit (host kill, stdout flush, unhandled rejection)?
5. Are there hidden couplings left in the three-lane split, or a better cut?

## 10. Fable advisory review — reconciliation (2026-10-11)

**Verdict: approve-with-changes.** Each finding was checked against code or data before it was accepted.

| Finding | Disposition |
|---|---|
| B1 instrument overflows 512 | **Accepted, re-scoped to major.** `build_sequence` budgets the head and options (192 tokens) separately and keeps the start of the state, so criteria are never cut. The prompt cap is set to 1,200 characters and descriptions to 120, with a truncation flag and length-bucket reporting. |
| M1 gates in the wrong unit | **Accepted.** Gates now count disagreement cases, labeling oversamples disagreements, and silence weights apply. Fisher p = 0.0055 was verified. |
| M2 stricter-floor baseline | **Accepted and measured.** Score ≥ 3 gives 0.76 precision with 0 hits lost. It is now a candidate, and a win produces a recommendation only. |
| M3 E5 optimistic | **Accepted.** Caveats were added, and the description source is pinned. |
| M4 shortlist and descriptions contract | **Accepted.** `lexicalShortlist()` is in the contract; descriptions come from `readMap()`. |
| M5 port-8000 identity | **Accepted.** A `/health` probe, cached 60 s, is required before any text is sent; there is also a canary. |
| M6 `hooks.json` move | **Accepted.** The work is dropped; the `settings.json` entry is repointed to the portable path instead. |
| M7 holdout weaker than `research.py` | **Accepted.** Per-dataset lock, one test per cycle, and spacing. |
| M8 `TranscriptIndex` coupling | **Accepted.** A new L2 module does prefix matching with `choose_match`, and slash commands are counted. |
| M9 async hook fail-open | **Accepted.** A timer-guaranteed emission, write after emit, and a ≥ 8 s host timeout. |
| m1 shadow-first | **Accepted.** Shadow plus day-0 bootstrap promotion. |
| m2–m8 | **Accepted:** legacy log semantics, volume (about 150 fires per day), corrupt state means shadow, latency demotion report-only, sub-deadline, probabilities fixture, 3 lanes. |
| Scope cuts | **Accepted:** no `hooks.json`, no instrument search, no workflow challengers in the cycle, 2 registered decisions, minimal scoreboard. |
