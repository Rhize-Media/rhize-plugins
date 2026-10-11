# Laya decision layer: earned authority (plan + impact map)

**Status:** draft for Fable + Codex plan review. Nothing here is implemented yet.
**Branch:** `claude/laya-earned-authority`
**Authority:** Jim (2026-10-11): "implement our decision layer strategy fully now and try to recursively implement and prove it as we go using tools like the autoresearch library … optimally integrating Laya's decision-making capabilities into our daily operations." He asked for a Fable + Codex review before implementation, Sonnet 5.5 parallel lanes only if they are recommended, and a final Fable + Codex review before `main`.

## 1. What we measured (2026-10-11, all read-only)

Every figure below comes from Jim's Mac today. The replays are exploratory and use small samples. None of them is a release-gate result.

| # | Finding | Evidence |
|---|---|---|
| E1 | Laya is already in daily use. The v2 workflow pilot has 349 observations since 2026-09-28. 179 were scored in shadow; 163 were excluded as operational, prebound or continuation events; 4 were unavailable. | `~/.local/share/rhize/workflow-selection/pilot/v2/*` |
| E2 | There are 73 explicit labels: 75 AI-reviewed taxonomy labels in total, of which 73 are explicit. They split 58 general, 13 none, 2 content. Research is held at the 200-label floor. | `taxonomy-labels/`, 07:30 `media.rhize.laya-autolabel` |
| E3 | **The workflow instrument is broken, and data volume is not the cause.** `request_for()` asks three *independent* `noul` questions. It sends only `{eventKind, action, domain, exclusions}` and decodes by argmax. Laya picks `content` 70 of 73 times, giving **2/73 = 2.7%** agreement. | replay through `127.0.0.1:8000/v1/systemone` |
| E4 | With Laya's native **`choice`** question type on the same fields, agreement is **47/73 = 64.4%**. The same question with the redacted task text added scores **21/35 = 60%**; only 35 cases have a request snapshot. Both lose to always-`general` (**79.5%**). A 3-line rule (explain or handoff → none; content domain → content; else general) scores **~91% in-sample**. I fit that rule after seeing these labels, so it is optimistic. | same replay |
| E5 | **Skill fit is where Laya helps.** On the 279 labeled rows of the routing harness, using the frozen third-party snapshot: the incumbent router fires 33 times with precision 0.67 (22 hit, 8 wrong, 3 false fires). In the **co-sign** policy, a suggestion is shown only when Laya's `choice`, over the top-5 lexical shortlist plus `none` and given the prompt text, independently picks the same skill. Co-sign fires 21 times with precision **0.86** (18 hit, 3 wrong, 0 false fires). Letting Laya alone decide (≥0.4) has precision 0.45; letting Laya add skills the router missed costs precision. Wilson 95% intervals overlap (≈0.65–0.95 vs ≈0.50–0.80), so this is suggestive only. | `evals/skill-map-routing` corpus, Laya replay |
| E6 | Called directly over HTTP, Laya takes **59 ms p50 / 92 ms p90** for skill prompts and ~110 ms p50 / ~650 ms p90 for workflow requests. The pilot's 1.57 s p50 is mostly the cost of launching Python for each call. | replay timings |
| E7 | The typed-decisions checkpoint is ModernBERT-large plus an RL head. Its input window is 512 tokens. It supports `choice`, `score` and `noul` question types. It does no network I/O and does not log request bodies (`managed-service.log` is 397 bytes). There is no fine-tune API, so improvement has to come from the instrument and from calibration. | `laya` 0.3.20 pinned checkpoint `55cf4c4` |
| E8 | **The skill-fit shadow never runs.** It needs `RHIZE_LAYA_SKILL_SHADOW=1`, which is unset. It is skipped whenever workflow selection is attempted. It sends Laya hashed candidate ids and router-matched tokens only, so it is circular and cannot see anything the router missed. | `skill-router.js:114` |
| E9 | **None of the routing fixes are live.** The skill router hook in `~/.claude/settings.json` runs `node <repo checkout>/rhize-context-manager/hooks/skill-router.js`. That checkout is on `codex/laya-transcript-size-limit` (99083e5), 24 commits behind `main`. It still suggested `completed-branch-promotion` from stack-only matches at 17:51 today. The installed plugin cache is at 0.43.3. | Mac settings, suggestion log |
| E10 | The router fires about 130–200 times per active day. Each log row carries the raw `session_id` and `context_hash = sha256(prompt)[:16]`, so historical turns can be re-identified in transcripts. Workflow outcomes are 183/183 `undetermined`. | `~/.claude/context-manager/suggestion-log.jsonl` |

## 2. Thesis

Laya has been held back by **how it is asked**, not by how much data it gets. It is a text classifier, but it has been fed category labels and hashed ids. Its three separate yes/no scores are not comparable to each other. The useful question is not "is Laya good?" It is "**for which decision does Laya beat the incumbent and the trivial baselines?**" The system needs to keep answering that from live evidence: each decision earns authority, and loses it automatically.

So this plan:
1. Fixes the instrument: a native `choice` question, redacted task text, and candidate descriptions instead of hashed ids, called directly over HTTP.
2. Gives Laya **one** real job now: **co-signing skill suggestions**. This decision is high-volume, low-risk and advisory, and Laya has measured value there.
3. Builds the generic registry and the evidence and research loop, so that more decisions can join with the same machinery.
4. Keeps workflow fit with Arm A. Laya is a challenger there but loses to the trivial baselines.
5. Keeps critical decisions in shadow, enforced by schema.

## 3. Policy changes Jim must accept (called out explicitly)

- **P-A, task text to loopback Laya.** `docs/typed-decision-layer.md` currently says "do not send prompts … to Laya." This plan sends the head of the prompt (≤2,000 chars, ≤512 tokens) to the **loopback, offline** Laya server, for **advisory-tier** decisions only.
  - The text is never persisted. Records keep hashes, ids and probabilities only.
  - Cloud annotators still see only shared-redactor output (`pilot_redaction.sanitize`).
  - Rationale: E5/E7. Without text, Laya can only re-rank the router's own evidence.
- **P-B, AI-reviewed labels for the advisory tier.** The advisory tier earns authority on AI-reviewed labels (two annotators plus a Fable reviewer, as for workflow) with tiered floors (§4.6). The workflow tier and critical tier keep their current gates. The workflow 200-label floor is **unchanged**.
- **P-C, automatic mode changes.** Promotion and demotion happen automatically for the advisory tier only. Every change writes an audit receipt and can be undone with one CLI command.

## 4. Design

### 4.1 Decision registry and modes

There are two pieces:
- **Shipped default:** `rhize-context-manager/config/decision-registry.json`, validated by `rhize-context-manager/schemas/decision-registry.schema.json`.
- **Machine-local state:** `~/.local/share/rhize/typed-decisions/registry-state.json`, written only by `decision_cycle.py` or the `decision_registry.py set-mode` CLI. Each write is appended to `registry-audit.jsonl`.

Modes, in order: `off` < `shadow` < `cosign` < `advisory` < `authoritative`. In this plan only `shadow` and `cosign` are reachable.
- `cosign` means the incumbent's output is shown only when the challenger agrees with it. Otherwise nothing is shown.
- There is a permanent randomized **holdback** (default 10%). Holdback prompts use incumbent-only behavior and log their propensity, so causal comparison never stops.

| Decision id | Tier | Default mode | Reachable modes | Notes |
|---|---|---|---|---|
| `skill-fit` | advisory | `cosign` (holdback 0.10) | off, shadow, cosign | First earned-authority decision |
| `workflow-fit` | workflow | `shadow` | shadow | v2 pilot untouched; report-only challengers |
| `context-pack`, `graph-relevance`, `context-retention`, `tool-trace`, `agent-brief-skill` | advisory/workflow | `off` | off, shadow | Registered for the generic loop; not wired in this plan |
| `devflow-gates`, `approvals`, `gsd-finish`, `model-worker` | critical | `shadow` | **shadow only (schema-enforced)** | No automation may change them |

Starting `skill-fit` directly in `cosign` follows Jim's "implement now, prove as we go." The risk is low: in the worst case a hint is suppressed. The E5 harness result and the auto-demotion guard (§4.6) back this choice. If a reviewer recommends it, the start can be `shadow` with auto-promotion instead.

### 4.2 Laya client v2

`rhize-context-manager/hooks/lib/laya-client.js` (Node, used by hooks):
- Loopback-only URL validation, mirroring `typed_relevance.local_call`.
- One `POST /v1/systemone`.
- **Hard abort at the registry `latencyBudgetMs`**, default 800 ms; on abort, `status:"timeout"`.
- Response validation for the `choice` answer type.
- It never throws to the caller.

`rhize-context-manager/scripts/typed_decisions/laya_choice.py` is the Python mirror, used for replay, backfill and research. A shared fixture `tests/rhize-context-manager/fixtures/laya-choice-requests.json` pins byte-identical request construction for Node and Python.

The instrument is `laya-choice-v1`:
- State: `{request: <prompt head ≤2000 chars>}`.
- Question: one `choice` question, `skill`, with these criteria:
  - `s0`…`s4`, each `"<skill-name>: <description[:240]>"`;
  - `none`: "none of these skills is needed; answer directly".
- The instrument's sha256 covers the template, not the prompt.

The skill-fit path no longer launches a Python process per call; `typed_candidates.py` stays for graph and retention.

### 4.3 Skill-fit co-sign in `skill-router.js`

1. The incumbent `routeFromIndex()` runs unchanged.
2. If the incumbent fired, and the request is not an explicit skill request, and the mode is not `off`, the hook builds the **unfloored lexical shortlist**: the top 5 by matched non-partial weight, with the incumbent forced in. This is the shortlist measured in E5.
3. The hook then calls `laya-choice-v1`.
4. The arm is assigned deterministically per prompt: `sha256(sessionHash‖promptHash) mod 10000 < holdback·10000` puts the prompt in the holdback arm.
5. What is emitted:

   | Arm and mode | Emitted |
   |---|---|
   | treatment + `cosign` | the incumbent only when `laya.choice === incumbent`; otherwise nothing |
   | holdback, or `shadow` | the incumbent |
   | Laya unavailable, timeout or invalid | the incumbent (fail-open) |
6. The workflow message logic is untouched. The `workflowAttempted` suppression of the Laya call is removed: the call no longer competes with the workflow budget, because it is a direct HTTP call capped at 800 ms. The suppression of the content-engine overlap message stays as is.
7. Every eligible prompt appends one **decision record** (§4.4). The legacy `suggestion-log.jsonl` row continues unchanged, so existing reports keep working.

Router-silent prompts are not sent to Laya live. "Laya adds skills the router missed" stays a research-only challenger, scored from backfill (E5 shows it costs precision).

### 4.4 Contract: records, outcomes, labels (written before any lane starts)

All are machine-local under `~/.local/share/rhize/typed-decisions/<decision>/`, mode 0600 files in 0700 directories, as JSONL partitioned by UTC day. JSON Schemas live in `rhize-context-manager/schemas/`, with fixtures under `tests/rhize-context-manager/fixtures/typed-decisions/`.

- **`rhize-typed-decision-record-v1`** fields:
  - identity: `decision`, `decisionId` (uuid4 hex), `ts`, `host`, `basis` (`live` | `backfill`);
  - binding: `sessionHash` = sha256(session_id), `promptHash` = sha256(prompt) (the same functions as the workflow receipts, so `TranscriptIndex` can find the turn), `registrySha256`, `instrument`, `instrumentSha256`, `routerSourceSha256`;
  - assignment: `mode`, `arm` (`treatment` | `holdback`), `propensity`;
  - decision: `incumbent` (`{skillId, score}` | null), `shortlist` (≤5 skill ids), `laya` (`{status, choice, probabilities, latencyMs, reason}`), `emitted` (skill id | null).
  - **No prompt text, paths or tokens. Schema `additionalProperties: false`.**
- **`rhize-typed-decision-outcome-v1`**, produced by a join that reads Claude transcripts with bounded reads:
  - Fields: `decisionId`, `outcome`, `skillInvoked`, `latencyTurns`, `joinedAt`, `transcriptSha256`.
  - `outcome` values: `invoked_emitted` | `invoked_other_shortlisted` | `invoked_unlisted` | `none_invoked` | `transcript_unavailable`.
  - Codex transcripts: `transcript_unavailable` in v1 unless the existing `transcript_message` parser handles them cheaply.
  - Acceptance is confounded by suggestion effects, so it is a secondary signal and never the promotion metric.
- **`rhize-typed-decision-label-v1`**:
  - Fields: `decisionId`, `basis` (`ai_model_reviewed` | `human_adjudicated` | `harness`), `bestSkill` (skill id | `none`), `acceptable` (list), `annotators`, `reviewer`, `evidenceSha256`, `labeledAt`.
  - Labels judge the prompt plus the candidate set, independent of arm, so both policies are scored offline on the same cases.

### 4.5 Evidence pipeline: backfill, outcomes, labels

- **Backfill** (`scripts/typed_decisions/backfill.py`):
  1. For each historical router row (fired, or a sampled silence) in `suggestion-log.jsonl`, find the turn by `session_id` and `sha256(prompt)[:16]` prefix, using `pilot_autolabel.TranscriptIndex` within the plugin, read-only.
  2. Replay the **current** incumbent (node `route-core`, through a small runner) and `laya-choice-v1`.
  3. Write records with `basis:"backfill"`, `arm:"holdback"`, `mode:"shadow"`, `emitted:null`.

  This turns roughly two weeks of real traffic (about 400 router fires plus sampled silences) into research cases on day one. **Backfill records are never counted as live causal evidence.**
- **Outcomes** (`scripts/typed_decisions/outcomes.py`): joins records to `Skill` tool_use events after the decision timestamp, in the same session, within the next 3 user turns or 30 minutes. It is idempotent.
- **Labels** (`scripts/typed_decisions/skillfit_labels.py`):
  - Picks a stratified daily sample of ≤12 records across these strata: agree; router-only; Laya-only above τ; silence with a Laya pick. Holdback and treatment are both included.
  - Rebuilds the redacted prompt and preceding context through the existing sanitizer and transcript index.
  - Asks the same two no-tools annotators with a schema-bound answer; a Fable reviewer resolves disagreements.
  - It reuses `pilot_autolabel` primitives (`model_command`, `child_env`, auth handling, run_process guards). It does not fork them.
  - Runs inside the **existing 07:30 job**, under the same lock and deadline. No new scheduler.
- **Harness labels:** the 279 routing-harness rows also become `basis:"harness"` labels. They form a fixed regression set and are never part of a holdout.

### 4.6 Recursive research loop (`evals/typed-decision/decision_cycle.py`)

The loop is generic over registered decisions and is autoresearch-style (keep/discard). It is a sibling of `pilot_cycle.py` and does not modify it.

**Candidates** are policies:
- the incumbent;
- trivial baselines (never fire; always fire the incumbent);
- decoding variants computed from **logged** probabilities, with no new Laya calls: co-sign, co-sign at p ≥ τ (τ ∈ {0.3, 0.4, 0.5}), veto-only, replace at τ, and router-else-Laya at τ;
- instrument variants, which need a Laya replay on the Mac from redacted transcript text: criteria wording, description length, and k ∈ {3, 5}.

The candidate budget is capped at 1,200 Laya calls per cycle and 180 s.

**Metric:** utility U = hits − λ·(wrong + false fires) per eligible prompt, with λ = 1 configurable in the registry. Precision and recall are also reported. Uncertainty comes from Wilson intervals and paired bootstrap (2,000 resamples, fixed seed).

**Splits:** time-ordered. The holdout is the newest 25% of labeled live cases at cycle time, is **single-use per candidate hash** (ledger, as `research.py check_holdout_authority`), and contains no backfill cases. Harness labels are a regression gate only.

**Advisory-tier gates** (defaults in the registry, tunable by Jim):
- **Promote** a challenger: ≥60 labeled live cases with ≥15 incumbent fires in the holdout, **and** the paired-bootstrap 80% lower bound on ΔU > 0, **and** harness precision is not worse than the incumbent's, **and** Laya unavailable ≤ 5%, **and** p90 latency ≤ the budget.
- **Demote** to shadow: over a rolling 14 days with ≥40 labeled live cases, the 80% upper bound on ΔU < 0, **or** unavailable/timeout > 10%, **or** p90 > budget for 3 consecutive days.

**Workflow and critical tiers:** report-only. `workflow-fit` adds `choice`-form and rule-baseline challengers to an **exploratory** replay report over v2 labels. It changes nothing in v2 collection, `pilot_cycle.py`, its source digest or its 200-label floor.

**Outputs:**
- a cycle receipt;
- an applied mode change (advisory tier only) through the registry CLI;
- a daily **scoreboard** (`scripts/typed_decisions/scoreboard.py`) with, per decision:
  - mode and arm counts;
  - labeled precision and recall with CIs;
  - acceptance;
  - Laya p50/p90 and unavailable rate;
  - the last cycle verdict;
  - any promotion or demotion.

The scoreboard is appended to the existing autolabel summary that the 08:00 Codex automation already reads.

### 4.7 Activation on the Mac (ops, after merge)

1. **Make the router follow released code** rather than whichever branch a Codex session has checked out (E9).
   - **Recommended:** register `skill-router.js` in the plugin's own `hooks/hooks.json` (so it uses `${CLAUDE_PLUGIN_ROOT}` and moves with the native update lifecycle). It is gated by an opt-in flag in `~/.claude/context-manager/router.json`, so it stays opt-in for everyone else. The now-duplicate `settings.json` entry is removed, with a backup, and only that entry.
   - **Alternative:** keep `settings.json` and point it at a pinned runtime export, following the `pilot-runtime/<commit>` pattern.
   - Jim approves any hook-trust prompt in the native UI. Approval files are never edited.
2. Update the Claude and Codex plugins through `claude plugin marketplace update` / `plugin update` and the Codex equivalent. Rebuild the local skill map. Open a fresh session to verify.
3. Run the backfill once, then the outcomes join and the first cycle. Append the three steps (labels → cycle → scoreboard) to `laya-autolabel.sh`, within its existing lock and deadline.
4. Send Jim the first scoreboard.

## 5. Invariants

- **I1** The only user-visible behavior change is `skill-fit` co-sign suppression in the treatment arm. Workflow Arm A, the v2 pilot and all critical decisions behave exactly as before.
- **I2** Any Laya failure, whether down, timed out or invalid, produces the incumbent's output byte-for-byte, and the failure is recorded.
- **I3** Hooks persist no prompt text, paths or tokens. Prompt text reaches only loopback Laya (never logged) and, through the shared redactor, the existing cloud annotators.
- **I4** Added hook latency is hard-capped at the budget (800 ms). The target is p50 ≤ 150 ms.
- **I5** The v2 pilot's collection files, source digest inputs, labels, cycle and 200 floor are unmodified (`decision_pilot_v2.source_digest()` paths untouched).
- **I6** Only advisory-tier decisions change mode automatically. Every change is audited and reversible. The schema rejects non-shadow modes for the critical tier.
- **I7** Holdout cases are single-use per candidate hash. Backfill and harness rows never enter the holdout.
- **I8** The routing harness's incumbent gates still pass unchanged (`run.py --check baseline.json`).
- **I9** Plugins are islands: no cross-plugin imports, and the `rhize-context-manager` scripts stay self-contained.

## 6. Acceptance tests

- **A1** Router:
  - cosign suppresses on disagreement and emits on agreement;
  - timeout, unavailable and invalid responses emit the incumbent;
  - shadow and holdback never change output;
  - arm assignment is deterministic and propensity is logged;
  - an explicit skill request skips Laya;
  - the legacy log row is unchanged.
- **A2** `laya-client.js` and `laya_choice.py`: identical request bytes on the shared fixture; loopback-only validation; abort at the budget; `choice` answer validation.
- **A3** Record, outcome, label and registry schemas validate their fixtures in Node and Python. A record carrying any text field fails. The critical tier set to `cosign` fails.
- **A4** Backfill and outcomes run on fixture transcripts and suggestion-log rows and produce the expected records and outcomes. Prefix collisions are refused. The join is idempotent.
- **A5** The labeler: the sample is deterministic and budget-capped; it redacts before any model call; it reuses the existing guards; the labels validate.
- **A6** `decision_cycle.py`:
  - holds below the floor;
  - consumes each holdout case once;
  - promotes and demotes an advisory decision only through the gate;
  - refuses the critical tier;
  - keeps the ledger append-only;
  - writes no workflow-v2 files.
- **A7** The full `pytest -q`, all `tests/**/*.js`, `validate_skill_map.py --check-stale`, routing harness `--check`, `bump_version.py --check` and the description-parity tests pass.
- **A8** Post-merge live smoke on the Mac: backfill replay over ≥20 real prompts reports Laya p50/p90, and the scoreboard renders.

## 7. Implementation plan and parallelization

**Recommendation: parallel Sonnet 5.5 lanes are justified.** There are four lanes with disjoint file ownership. The shared contract (§4.4 schemas, fixtures, and the registry file) is written and committed by the coordinator **before** dispatch. Each lane gets its own worktree and branch, task-graph v2 validation, and begin/finalize receipts, following `rhize-ops:parallel-agent-optimization`.

| Lane | Owns | Depends on |
|---|---|---|
| L1 Router/runtime (JS) | `hooks/lib/laya-client.js`, `hooks/lib/decision-registry.js`, `hooks/skill-router.js` changes, plugin `hooks.json` registration + opt-in flag, `tests/rhize-context-manager/test_skill_fit_*.js` | contract |
| L2 Evidence (Py) | `scripts/typed_decisions/{__init__,records,laya_choice,backfill,outcomes}.py` + `route_replay.js` runner + tests | contract |
| L3 Labels (Py) | `scripts/typed_decisions/skillfit_labels.py` + tests (mocked model runner) | contract, L2 `records` API (stubbed by fixtures) |
| L4 Research/report (Py) | `evals/typed-decision/decision_cycle.py`, `scripts/typed_decisions/{decision_registry,scoreboard}.py`, docs (`docs/typed-decision-layer.md` policy update, `docs/typed-decisions/skill-fit.md`) + tests | contract |

The coordinator (Opus) owns:
- the contract;
- integration (fast-forward merges in the order L2 → L1 → L3 → L4);
- the full-suite run;
- the `bump_version.py --plugin rhize-context-manager --level minor` bump with CHANGELOG, README and GUIDE;
- impact-map reconciliation;
- the final Fable and Codex reviews;
- the push to `main`;
- the Mac activation.

Executors never push.

## 8. Out of scope (next decisions to join)

- `agent-brief-skill` co-sign (agent-dispatch briefs);
- Codex-host outcomes;
- a workflow v3 cohort with the `choice` instrument (only if the exploratory replay ever beats the majority baseline);
- a learned calibrator on top of Laya probabilities;
- context-retention and graph-relevance wiring.

## 9. Questions for reviewers

1. Is starting `skill-fit` in `cosign` with 10% holdback right, or should it start in `shadow` and auto-promote?
2. Are the advisory gates (≥60 labeled live cases, 80% paired-bootstrap bound, λ = 1) sound for a low-risk hint? Is anything about the time-ordered holdout exploitable?
3. P-A: is the loopback-only, non-persisted prompt head an acceptable change to "do not send prompts to Laya"? Should the hook redact secrets first, which would mean a JS port of the redactor and a parity burden?
4. Is the transcript-based backfill and outcome join sound, given 16-hex prefix matching and the risk of prefix collisions?
5. Router registration: is moving the router into plugin `hooks.json` with an opt-in flag better than a pinned runtime path?
6. Is the lane split and the contract-first order right? Are there hidden couplings, for example `route_replay.js` versus L1's route-core use?
