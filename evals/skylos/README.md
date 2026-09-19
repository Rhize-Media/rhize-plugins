# Skylos static-evidence comparison

Arm A runs the existing deterministic Devflow evidence CLI. Arm B runs that inventory plus the
optional isolated Skylos adapter, then consumes its report through the public CLI. Each of the 13
fixtures uses a fresh disposable Git repository. Fixture source is never executed. This is a
single-host static signal evaluation, not a comparison against full human/agent review.

Run from a host with an explicitly provisioned Skylos 4.38.0 virtual environment:

```bash
python3 evals/skylos/run.py --python /absolute/dedicated-venv/bin/python > /private/tmp/skylos-eval.json
```

`fixtures.json` declares before/after source and expected rule/location signals in advance. Expected
signals are hypothesis targets, including a deliberately difficult unrelated-test case; they are
not promises that upstream implements each pattern. `detected` requires the expected rule and
location; `missed` means a usable scanner result omitted it, even when coverage was incomplete.
`unavailable` is counted separately. Clean cases have no seeded defect; classify any additional
findings manually before labeling them false positives. Never equate zero findings with safety.

Rows record arm, variant, fixture hash, actual execution availability, runtime, completeness,
findings/misses, packet acceptance and unchanged source. Arm B time is baseline inventory plus scan;
it excludes report-consumption overhead. No token, productivity, ROI or statistical claim is made.
Re-run after changing adapter policy or upstream version. Normal unit tests do not install Skylos or
require the platform sandbox; the real execution results are a separate acceptance gate.

Run `python3 evals/skylos/isolation.py --python /absolute/dedicated-venv/bin/python` first to
verify filesystem and network isolation using temporary inert sentinel files. No fixture source is
executed. See [recorded results and limitations](RESULTS.md) for the completed local run.
