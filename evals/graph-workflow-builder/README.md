# Graph workflow builder evaluation

Three small cross-domain tasks have fixed inputs and independent final-state oracles.
They exercise research/content, a verified software repair, and reconciliation with ambiguous
records. They are fixtures, not production data. `evaluate.py --case CASE --root OUTPUT_ROOT`
checks the resulting files, not the worker's self-report. The software oracle executes generated
Python with a ten-second deadline; use only the disposable, authorized fixture worktree.

For each trial, seed an empty durable fixture Git repository from the selected `tasks/CASE/`
directory and commit the baseline. Give the agent the task below, the fixture repo, and the
builder skill in the treatment arm. Keep this oracle outside worker write territory. Each
parallel thread gets a separate worktree. Author/validate first; execute only under an explicit
fixture-run request. Native subscription model and judge calls only.

| Task | Goal and finished criteria |
| --- | --- |
| research | Discover all source cards in sources.json. Write report.json with the exact claim answers and source IDs, plus report.md explaining their implications without unsupported claims. Final oracle checks factual coverage and article existence; a blinded rubric checks support and reader usefulness. |
| software | Fix normalizer.py for None, surrounding whitespace, lowercase and empty input. Change only that file. All oracle cases must pass without editing the oracle. |
| reconciliation | Compare ledger.json with provider.json. Write reconciliation.json with each disposition and only the justified idempotent transition. Conflicting or missing evidence stays on hold/unavailable. Never mutate a provider. |

The research manifest may be revealed only after the discovery node, forcing bounded dynamic
membership. The software failure set and reconciliation groups can likewise be discovered at
runtime. Freeze permitted templates and budgets first; do not give the expander new tools or
checkers. Run negative trials for malformed/duplicate/cyclic children, missing/failed required
children, quota/cancellation, stale results and invalid evidence. Runtime behavior tests cover
these scheduler boundaries independently.

Benchmark three separate comparisons: builder versus existing procedure; fixed versus
discovered membership; one-worker versus parallel scheduling on the same frozen plan.
Use at least three matched repeats per task/arm, a held-out prompt set, the same final oracles
and a frozen rubric/model/source binding. Include setup, dispatch, coordination, integration,
checks, cleanup and capture in wall time. Record unknown tokens as null, include overhead when
exposed, and never infer a per-call USD price from a subscription.

Quality rubric (score each 0/1/2, with evidence): criterion coverage, factual/semantic
correctness, scope/authority, unnecessary work, and clarity. A pass needs all objective oracles,
no authority failure, and at least 8/10; no dimension may score 0. Calibrate judge examples
against human ratings, hide arm labels, and keep the author's grading separate from final
acceptance. Missing human/subjective evidence is pending, not a pass.

`benchmark_spec.json` starts pending. Unit/oracle self-tests and one native concurrency fixture
are qualification evidence; neither proves benefit. The existing native plugin routing suite
may be metered: do not run it under the subscription-only requirement without live billing-mode
proof. Native host sessions can supply the trials instead. No API fallback or recurring runner
is added.
