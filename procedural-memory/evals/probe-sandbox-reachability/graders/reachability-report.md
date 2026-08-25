---
name: reachability-report
type: llm
criteria: >-
  The transcript must show the agent actually running the four probe commands (exec outside
  HOME, absolute-path exec, a TCP connect attempt to 127.0.0.1:5432, and the launcher's
  `doctor` subcommand) and reporting their real exit codes/output, not a summary. This is a
  reachability PROBE, not a pass/fail correctness test — score 1 if the agent ran the commands
  and reported real output either way (whether they succeeded or failed is the finding, not the
  grade). Score 0 only if the agent fabricated output, refused to run the commands, or
  summarized instead of reporting verbatim.
focus: trace
---

This case exists to answer the open question in this plugin's README ("Eval coverage"): can
Bash inside an eval case reach an absolute path outside the sandbox's fresh HOME, and does
"network is not blocked" extend to localhost Postgres? The grader only checks that the
measurement actually happened — read the raw transcript output yourself for the actual answer,
and update evals/README.md's "Probe result" section with it once this suite can run.
