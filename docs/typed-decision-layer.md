# Local typed decision layer

This pilot uses a loopback Laya server with the `typed-decisions` checkpoint. Existing selectors, safety gates, approvals, and project execution remain authoritative. Arm A is the incumbent decision; Arm B is a scored candidate recorded in a private receipt. A score is neither permission nor proof of improved software outcomes.

The workflow measurement v2 cohort seals a bounded intent envelope before Arm A consultation,
keeps catalog consultation distinct from match/execution, and reports eligible, excluded, held,
unknown and missing-context events separately. Its scorer and development evaluator share one
routing decision function. Background callbacks and continuations are not independent routing
trials. Actual check exit/time artifacts can support task review; they cannot establish human
acceptance or attribute an Arm A outcome to an unexecuted Arm B recommendation. V1 evidence stays
separate and unchanged. See the [workflow contract](../rhize-context-manager/docs/decision-pilot.md).

Nine decisions live in the [earned-authority registry](#earned-authority-registry). Every one ships in `shadow`; the registry state, not an environment flag, decides what is shown. Reachable modes are `off` (no Laya call), `shadow` (asked and recorded, nothing shown), `advise` (one labelled, uncalibrated line; the incumbent path and every gate stay authoritative) and `cosign` (skill fit and the credential procedure only).

| Decision | Entry point | Tier | Reachable modes | Existing authority |
|---|---|---|---|---|
| `skill-fit` | Context Manager `skill-router.js` | advisory | off, shadow, advise, cosign | Deterministic skill suggestion and explicit user request — see [skill fit](typed-decisions/skill-fit.md) |
| `workflow-fit` | Context Manager `workflow_selection.py context` | workflow | shadow, advise | Opportunity decision and workflow execution evidence |
| `procedure-pick` | Context Manager `workflow_selection.py recommend-procedure` | advisory | off, shadow, advise | Stored-procedure recall and the agent's own `reuse`/`adapt` decision |
| `devflow-next-action` | Dev Flow `typed_checkpoint.py --mode advise` | critical | off, shadow, advise | Impact map, checks, tests, review and approval |
| `browser-qa-selection` | Dev Flow `typed_selection.py --mode advise` | advisory | off, shadow, advise | Legal candidates and approved test surface |
| `model-routing` | Ops `typed_routing.py --mode advise` | advisory | off, shadow, advise | User pin, host authorization and task graph |
| `gsd-directive` | Project Launcher `typed_decision.py supervise` (`install --local-laya`) | critical | off, shadow, advise | GSD plan, test and verifier decisions; `finish_candidate` needs checks and review |
| `check-relaxation` | Dev Flow `check_plan.py` ([S4](../rhize-devflow/docs/check-relaxation.md)) | critical | off, shadow, advise | Deterministic allowlist; Laya can only keep the full list |
| `credential-procedure` | Context Manager `credential-workflow.js` | workflow | off, shadow, cosign | Manual-only fixed CLI procedures; Dev Flow's Keychain GUI deny is independent |

Observational scorers outside the registry stay `shadow`-only and opt in per call:

| Candidate | Entry point | Activation | Existing authority |
|---|---|---|---|
| Context Pack relevance | Context Manager `typed_relevance.py` | `RHIZE_LAYA_GRAPH_SHADOW=1` with native pack preview | Verified source inclusion and ACL |
| Governed graph relevance | Graph memory `query --typed-shadow` | Explicit CLI flag after governed query | ACL filtered query results |
| Context retention | Context Manager `typed_candidates.py` | Explicit `--mode shadow --evidence <current artifact>` | Protected anchors and incumbent retention |
| Tool trace risk | Dev Flow `typed_selection.py` | Explicit `--mode shadow --evidence <current artifact>` | Legal candidates and approved test surface |
| Dev Flow checkpoint receipts | Dev Flow `typed_checkpoint.py` | Explicit `--mode shadow` | Impact map, checks, tests, review and approval |
| GSD planner, executor, verifier (hosted) | Project Launcher installed project-local client | GSD handoff and per-agent hooks | GSD plan, test and verifier decisions |

Candidate CLIs read a bounded JSON envelope from stdin. Use `--help` and the local contract documentation in the owning plugin before calling them. Generate candidates from current deterministic evidence; do not send prompts, code, paths, logs, secrets, customer data, or graph properties to Laya. The exception is a registry decision, which may send a bounded, redacted request (at most 1,500 characters) plus up to 20 repo-relative file-name hints to the literal-loopback server after an identity probe; the shared `typed_advice.py` client never raises and writes only hashes, candidate ids and probabilities in its records (see [earned authority](#earned-authority-registry)). A source hash records provenance, but it does not attest that caller-generated metadata is correct. The Context Manager retention and Dev Flow selection CLIs additionally rehash their evidence files. Score receipts are private, owner-readable, and must be joined to accepted-task outcomes before claiming benefit. A failed provider, invalid answer, or missing receipt leaves Arm A in force.

The Project Launcher handoff installs and probes the project-local client when the next project is scaffolded. Confirm the local server is running, inspect the probe receipt and each GSD agent's receipt, and keep `shadow` mode until adjudicated holdout and task trials satisfy the release gates. A source release alone does not activate a running host session or create the future project.

## Earned authority (registry)

Jim approved the advisory tier on 2026-10-11 and extended it on 2026-10-16 so the decision layer can run now and prove itself as it goes. The designs and reviews are in [the 2026-10-11 plan](superpowers/specs/2026-10-11-laya-earned-authority-plan.md) and [the 2026-10-16 advise-everywhere plan](superpowers/specs/2026-10-16-laya-advise-everywhere-plan.md), which overrides that plan's invariants I5, I6 and I8; the operator guide is [skill fit](typed-decisions/skill-fit.md).

- **Registry.** `rhize-context-manager/catalog/decision-registry.json` lists the nine decisions above with a tier (`advisory`, `workflow`, `critical`) and reachable modes. Machine-local state lives in `~/.local/share/rhize/typed-decisions/registry-state.json` and changes only through `scripts/typed_decisions/decision_registry.py` (locked, revisioned, audited, recoverable). A corrupt state reads as `shadow`; a manual pin (`set-mode --pin off|shadow`) suspends automation and is the kill switch. Every earned mode binds the policy hash, instrument hash and Laya revision; a mismatch reads as `shadow`.
- **Modes and gates.** Gates are per target mode, and passing one never authorizes another. `advise` uses the deployable policy `advise-v1` and the majority-baseline gate; `cosign` keeps `cosign-v1` and its disagreement gate. Critical decisions may reach `advise` but never `cosign`. `credential-procedure` is manual-only: no automated cycle moves it, and it never reaches `advise`.
- **Majority-baseline gate.** Labelled choice records are grouped by session and split 2/3 tuning, 1/3 promotion. The baseline is the tuning majority class, frozen into a promotion cohort at reserve time (at least 30 cases from distinct sessions) and scored as a constant predictor on the same cases. Abstentions, timeouts and invalid answers count as Laya wrong; answer coverage must be at least 90%. Promotion needs a paired exact one-sided Clopper-Pearson lower bound above 0.5 on the discordant cases at alpha_k = 0.10 * 2^-(k-1) (the budget is per decision), Laya's balanced accuracy above the baseline's, and recall of at least 0.5 on every class with at least 10% tuning share and at least 3 promotion cases. The 200-label floor no longer applies to workflow fit.
- **Critical decisions** also need at least 10 `critical_if_wrong` cases in the cohort (computed by trusted caller code from hard-gate state and frozen before any advice) and zero critical misses. One accepted critical miss demotes to `shadow` in the same locked job that imports the label. Otherwise each time 10 fresh advise-arm labels accrue, the latest 30 are scored and two consecutive evaluations below the baseline demote.
- **Holdback.** Each decision keeps a deterministic holdback (10%, 15% for critical) that is still asked and recorded but never shown advice, so outcomes are collected in both arms.
- **Prompt text.** Skill fit may send the first 1,200 code points of the prompt; the other decisions send the redacted request described above. Neither is persisted by hooks. Cloud annotators still see only `pilot_redaction.sanitize` output.
- **Labels.** AI-reviewed labels (two annotators plus a reviewer, `choice_labels.py run`) are sufficient for the registry decisions. Annotators see only the frozen pre-decision snapshot and the candidate set, never the recommendation, outcome or mode.
- **Cycle and scoreboard.** `evals/typed-decision/decision_cycle.py run` dispatches on `gateKind` (add `--no-advise` for the skill-fit cosign pass only); `scoreboard.py render` shows one row per decision (mode, labelled n, accuracy against baseline, bound, critical misses).

**Status:** the release ships the ability, not the authority. Every registry decision is in `shadow`; none is in `advise` or `cosign` unless the live cycle has earned it or an operator has pinned it, and the scoreboard is the place to check. Activation needs a plugin update, the daily job lines for `choice_labels.py`, `decision_cycle.py` and `pilot_cycle.py`, and fresh sessions.

## Measurement

Use [the fixed research evaluator](../evals/typed-decision/README.md) for decision accuracy and calibration. Build at least 200 human-adjudicated cases per decision type (registry decisions use the earned-authority gate above instead), with at least 50 in the locked 25% holdout; include safety and authorization strata. Keep candidate search separate from one-shot holdout. Evaluate each accepted task for correctness, required checks, review outcome, wall time, coding-agent input/output tokens, local Laya usage and latency, fallbacks, and abstentions. An unavailable usage field is missing evidence, not zero.

Run 4–6 replayable paired tasks as a pilot only after fixing the rubric and environment. Then favor single-execution randomized tasks in the upcoming project so normal delivery does not double its token cost. Reserve every duplicate Arm A control with `evals/typed-decision/task_trials.py`; its 1,000,000-token ceiling covers incremental coding-agent tokens for duplicate controls, and the host must enforce the per-run limit. Stop new paired controls when the ledger cannot reserve them. Local research inference is reported separately. A candidate needs the predeclared quality and safety bounds plus independent review before promotion; current synthetic checks do not satisfy that gate.

## Workflow measurement rollout

The [workflow pilot](../rhize-context-manager/docs/decision-pilot.md) is the first integrated collection
path. It records opportunity coverage, bound background scores, human review labels and task outcomes.
The recurring research coordinator is `evals/typed-decision/pilot_cycle.py`; no labels means a held
research cycle, and a kept development candidate still requires separate holdout and task trials.
