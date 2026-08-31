# Obsidian evals

This directory keeps two complementary eval surfaces:

- `trigger_evals.json` and `quality_evals.json` are live-model cases consumed by the
  repository's shared `evals/run_evals.py` harness.
- `run_local_evals.py` is the immediate deterministic, offline gate. It makes no model,
  network, qmd, vault, or paid calls.

Run the local gate with:

```bash
python3 evals/obsidian/run_local_evals.py
```

The local routing score checks curated substrings from each live `SKILL.md`, keyword
drift, one positive and two near-miss/collision negatives per skill, complete
live-quality coverage, and static operational contracts. It does **not** claim to
measure a model's real Skill invocation decision.

`benchmark_spec.json` defines the future paired benchmark. Arm A is the exact
pre-plugin/existing implementation; Arm B is the plugin path. No arm ran in this change,
and `results` stays empty because paid/network calls were prohibited.
