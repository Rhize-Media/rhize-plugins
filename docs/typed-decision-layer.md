# Local typed decision layer

This pilot uses a loopback Laya server with the `typed-decisions` checkpoint. Existing selectors, safety gates, approvals, and project execution remain authoritative. Arm A is the incumbent decision; Arm B is a scored candidate recorded in a private receipt. A score is neither permission nor proof of improved software outcomes.

| Candidate | Entry point | Activation | Existing authority |
|---|---|---|---|
| Skill fit | Context Manager `skill-router.js` | `RHIZE_LAYA_SKILL_SHADOW=1` | Deterministic skill suggestion and explicit user request |
| Workflow fit | Context Manager `workflow_selection.py` | `RHIZE_LAYA_WORKFLOW_SHADOW=1` | Opportunity decision and workflow execution evidence |
| Context Pack relevance | Context Manager `typed_relevance.py` | `RHIZE_LAYA_GRAPH_SHADOW=1` with native pack preview | Verified source inclusion and ACL |
| Governed graph relevance | Graph memory `query --typed-shadow` | Explicit CLI flag after governed query | ACL filtered query results |
| Context retention | Context Manager `typed_candidates.py` | Explicit `--mode shadow --evidence <current artifact>` | Protected anchors and incumbent retention |
| Dev Flow checkpoints | Dev Flow `typed_checkpoint.py` | `RHIZE_LAYA_DEVFLOW_SHADOW=1` | Impact map, checks, tests, review and approval |
| Tool trace risk and browser QA | Dev Flow `typed_selection.py` | Explicit `--mode shadow --evidence <current artifact>` | Legal candidates and approved test surface |
| Model and worker fit | Ops `typed_routing.py` | Explicit `--mode shadow` | User pin, host authorization and task graph |
| GSD planner, executor, verifier | Project Launcher installed project-local client | GSD handoff and per-agent hooks | GSD plan, test and verifier decisions |

Candidate CLIs read a bounded JSON envelope from stdin. Use `--help` and the local contract documentation in the owning plugin before calling them. Generate candidates from current deterministic evidence; do not send prompts, code, paths, logs, secrets, customer data, or graph properties to Laya. A source hash records provenance, but it does not attest that caller-generated metadata is correct. The Context Manager retention and Dev Flow selection CLIs additionally rehash their evidence files. Score receipts are private, owner-readable, and must be joined to accepted-task outcomes before claiming benefit. A failed provider, invalid answer, or missing receipt leaves Arm A in force.

The Project Launcher handoff installs and probes the project-local client when the next project is scaffolded. Confirm the local server is running, inspect the probe receipt and each GSD agent's receipt, and keep `shadow` mode until adjudicated holdout and task trials satisfy the release gates. A source release alone does not activate a running host session or create the future project.

## Measurement

Use [the fixed research evaluator](../evals/typed-decision/README.md) for decision accuracy and calibration. Build at least 200 human-adjudicated cases per decision type, with at least 50 in the locked 25% holdout; include safety and authorization strata. Keep candidate search separate from one-shot holdout. Evaluate each accepted task for correctness, required checks, review outcome, wall time, coding-agent input/output tokens, local Laya usage and latency, fallbacks, and abstentions. An unavailable usage field is missing evidence, not zero.

Run 4–6 replayable paired tasks as a pilot only after fixing the rubric and environment. Then favor single-execution randomized tasks in the upcoming project so normal delivery does not double its token cost. Reserve every duplicate Arm A control with `evals/typed-decision/task_trials.py`; its 1,000,000-token ceiling covers incremental coding-agent tokens for duplicate controls, and the host must enforce the per-run limit. Stop new paired controls when the ledger cannot reserve them. Local research inference is reported separately. A candidate needs the predeclared quality and safety bounds plus independent review before promotion; current synthetic checks do not satisfy that gate.
