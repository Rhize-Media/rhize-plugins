# Local typed decision layer

This pilot uses a loopback Laya server with the `typed-decisions` checkpoint. Existing selectors, safety gates, approvals, and project execution remain authoritative. Arm A is the incumbent decision; Arm B is a scored candidate recorded in a private receipt. A score is neither permission nor proof of improved software outcomes.

The workflow measurement v2 cohort seals a bounded intent envelope before Arm A consultation,
keeps catalog consultation distinct from match/execution, and reports eligible, excluded, held,
unknown and missing-context events separately. Its scorer and development evaluator share one
routing decision function. Background callbacks and continuations are not independent routing
trials. Actual check exit/time artifacts can support task review; they cannot establish human
acceptance or attribute an Arm A outcome to an unexecuted Arm B recommendation. V1 evidence stays
separate and unchanged. See the [workflow contract](../rhize-context-manager/docs/decision-pilot.md).

| Candidate | Entry point | Activation | Existing authority |
|---|---|---|---|
| Skill fit | Context Manager `skill-router.js` | Decision registry `skill-fit` mode (`shadow` by default; `cosign` only after a passed gate) — see [skill fit](typed-decisions/skill-fit.md) | Deterministic skill suggestion and explicit user request |
| Workflow fit | Context Manager `workflow_selection.py` | `RHIZE_LAYA_WORKFLOW_SHADOW=1` | Opportunity decision and workflow execution evidence |
| Context Pack relevance | Context Manager `typed_relevance.py` | `RHIZE_LAYA_GRAPH_SHADOW=1` with native pack preview | Verified source inclusion and ACL |
| Governed graph relevance | Graph memory `query --typed-shadow` | Explicit CLI flag after governed query | ACL filtered query results |
| Context retention | Context Manager `typed_candidates.py` | Explicit `--mode shadow --evidence <current artifact>` | Protected anchors and incumbent retention |
| Dev Flow checkpoints | Dev Flow `typed_checkpoint.py` | `RHIZE_LAYA_DEVFLOW_SHADOW=1` | Impact map, checks, tests, review and approval |
| Tool trace risk and browser QA | Dev Flow `typed_selection.py` | Explicit `--mode shadow --evidence <current artifact>` | Legal candidates and approved test surface |
| Model and worker fit | Ops `typed_routing.py` | Explicit `--mode shadow` | User pin, host authorization and task graph |
| GSD planner, executor, verifier | Project Launcher installed project-local client | GSD handoff and per-agent hooks | GSD plan, test and verifier decisions |

Candidate CLIs read a bounded JSON envelope from stdin. Use `--help` and the local contract documentation in the owning plugin before calling them. Generate candidates from current deterministic evidence; do not send prompts, code, paths, logs, secrets, customer data, or graph properties to Laya. The one exception is an advisory-tier decision governed by the [earned-authority registry](#earned-authority-advisory-tier), which may send a bounded prompt head to the literal-loopback server after an identity probe and never persists it. A source hash records provenance, but it does not attest that caller-generated metadata is correct. The Context Manager retention and Dev Flow selection CLIs additionally rehash their evidence files. Score receipts are private, owner-readable, and must be joined to accepted-task outcomes before claiming benefit. A failed provider, invalid answer, or missing receipt leaves Arm A in force.

The Project Launcher handoff installs and probes the project-local client when the next project is scaffolded. Confirm the local server is running, inspect the probe receipt and each GSD agent's receipt, and keep `shadow` mode until adjudicated holdout and task trials satisfy the release gates. A source release alone does not activate a running host session or create the future project.

## Earned authority (advisory tier)

Jim approved this tier on 2026-10-11 so the decision layer can run now and prove itself as it goes. The full design and both reviews are in [the plan](superpowers/specs/2026-10-11-laya-earned-authority-plan.md); the operator guide is [skill fit](typed-decisions/skill-fit.md).

- **Registry.** `rhize-context-manager/catalog/decision-registry.json` lists each decision with a tier (`advisory`, `workflow`, `critical`) and its reachable modes (`off`, `shadow`, `cosign`). Critical decisions are shadow-only by schema. Machine-local state lives in `~/.local/share/rhize/typed-decisions/registry-state.json` and changes only through `scripts/typed_decisions/decision_registry.py` (locked, revisioned, audited, recoverable). A corrupt state reads as `shadow`; a manual pin suspends automation.
- **Prompt text (advisory only).** The first ≤1,200 code points of the prompt may go to the literal-loopback Laya server (`127.0.0.1`/`::1`, redirects refused, after a cached `/health` identity probe). It is never persisted; records hold hashes, ids and probabilities only. Cloud annotators still see only `pilot_redaction.sanitize` output.
- **Labels.** AI-reviewed labels (two annotators plus a reviewer) are sufficient for the advisory tier. Workflow and critical tiers keep the gates above; the workflow 200-label floor is unchanged.
- **Gate.** Only the deployable policy (`cosign-v1`) can be promoted automatically, through a frozen cohort of labeled disagreement cases tested once with an exact one-sided Clopper–Pearson bound and alpha spending across attempts. Demotion is automatic on quality or operational evidence. Every alternative policy is report-only.

The first and only advisory decision so far is skill fit.

## Measurement

Use [the fixed research evaluator](../evals/typed-decision/README.md) for decision accuracy and calibration. Build at least 200 human-adjudicated cases per decision type (advisory-tier decisions use the earned-authority gate below instead), with at least 50 in the locked 25% holdout; include safety and authorization strata. Keep candidate search separate from one-shot holdout. Evaluate each accepted task for correctness, required checks, review outcome, wall time, coding-agent input/output tokens, local Laya usage and latency, fallbacks, and abstentions. An unavailable usage field is missing evidence, not zero.

Run 4–6 replayable paired tasks as a pilot only after fixing the rubric and environment. Then favor single-execution randomized tasks in the upcoming project so normal delivery does not double its token cost. Reserve every duplicate Arm A control with `evals/typed-decision/task_trials.py`; its 1,000,000-token ceiling covers incremental coding-agent tokens for duplicate controls, and the host must enforce the per-run limit. Stop new paired controls when the ledger cannot reserve them. Local research inference is reported separately. A candidate needs the predeclared quality and safety bounds plus independent review before promotion; current synthetic checks do not satisfy that gate.

## Workflow measurement rollout

The [workflow pilot](../rhize-context-manager/docs/decision-pilot.md) is the first integrated collection
path. It records opportunity coverage, bound background scores, human review labels and task outcomes.
The recurring research coordinator is `evals/typed-decision/pilot_cycle.py`; no labels means a held
research cycle, and a kept development candidate still requires separate holdout and task trials.
