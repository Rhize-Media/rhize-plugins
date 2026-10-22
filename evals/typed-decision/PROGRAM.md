# Research program for a bounded agent run

Read [README.md](README.md) and the private study plan before proposing candidates. Use only the training cases to inspect errors and generate up to 12 candidate configs. Do not read locked holdout data, alter the evaluator, labels, split seed or ledger, or infer missing Arm A results. Propose one change per candidate: checkpoint, question instructions, or abstention threshold. Run `research.py --phase search` once for the batch. Review validation accuracy, critical misses, abstention, Brier sums, latency and local token use by stratum. Inspect case-level critical errors privately before selecting a candidate; an equal aggregate count may hide a different miss. Record failed attempts. Freeze one candidate hash and hand the holdout command to an independent reviewer. Stop after the bounded batch; do not run indefinitely. Never promote a model based on fixture or development results alone.

Use current metric semantics: wrong/unresolved critical decisions include abstentions; actual
unsafe actions are unmeasured by inference. Inspect class support, independent groups, label bases,
the frozen tuning-majority comparator and recorded Arm A separately. Calibration diagnostics are
uncalibrated estimates, with question type/candidate count disclosed. Operational deadline replay
and grouped menu-order panels use development cases only; preserve all failure denominators and
never count rotated menus as independent tasks. A new scorer comparison requires a frozen local
corpus and approved runtime, not a banking leaderboard result or zero generated answer tokens.
