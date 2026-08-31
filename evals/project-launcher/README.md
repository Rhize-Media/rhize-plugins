# Project Launcher evals

`trigger_evals.json` and `quality_evals.json` are future live-model cases for the shared
house harness. The immediate gate is deterministic, local, and free:

```bash
python3 evals/project-launcher/run_local_evals.py
```

It checks every discovered skill, keyword drift, one positive plus two collision/near-miss
negatives per skill, live-quality case presence, and static operational contracts. Its
lexical routing result is not a claim about real model routing.

`benchmark_spec.json` fixes Arm A as the exact pre-plugin/existing implementation and Arm B
as the plugin path. No arm ran and no results are recorded because paid/network calls were
prohibited.
