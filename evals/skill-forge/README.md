# Skill Forge integration evaluations

This Rhize-side harness never edits Skill Forge. It accepts an explicit checkout and/or executable;
no private checkout path is embedded in code.

```bash
python3 evals/skill-forge/integration_eval.py inspect \
  --checkout /explicit/path/to/skill-forge --binary /explicit/path/to/skill-forge

python3 evals/skill-forge/integration_eval.py safety \
  --checkout /explicit/path/to/skill-forge --repetitions 3 --output /private/tmp/skill-forge-safety.json
```

`inspect` detects package/binary drift before any benchmark. `safety` runs a hand-labeled six-case
precision/recall corpus with three safe near-miss/basic cases and three unsafe cases. It also records
local scan latency across explicit repetitions. Results stay outside Git; imperfect precision or
recall is a measured finding, not silently converted into a failed harness run.

`evolve-benchmark.json` and `evolve_contract.py` define a separate pre/post non-inferiority path.
Arm A is the digest-pinned pre-evolve skill. Arm B is the digest-pinned staged proposal before
adoption. Each arm records the common metrics, the actual arm run, and three counterbalanced
repetitions. Validation gates correctness, routing precision/recall, latency, rework, and failures.
The protocol is isolated, offline, and never adopts a proposal. No receipts or claimed results are
included because the agent-mediated evaluation has not been run.
