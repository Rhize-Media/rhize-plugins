# Local typed checkpoint shadow signal

The related `scripts/typed_selection.py` accepts only source-bound, bounded candidate
metadata for `tool_trace_risk` or `browser_qa`. Each candidate must already be legal, and
browser QA requires an approved test surface. Pipe a JSON envelope containing `schema`,
`capability`, `sourceSha256`, `taskSignals`, `candidates`, `incumbentIds`, and `policy` to
`--mode shadow --evidence <current deterministic evidence file>`. The receipt ranks
candidates for review; it does not click, dispatch, grant approval or change this
checkpoint's verdict. See [the pilot matrix](../../docs/typed-decision-layer.md).

The optional adapter at `scripts/typed_checkpoint.py` asks local Laya a bounded set of Noul questions at an **existing** Dev Flow stage. It is observational. The deterministic impact map, check, test-evidence, review, and release contracts continue to decide the gate. No worker action, permission, test pass, review pass, approval, commit, merge, or deployment follows from its `candidateDirective`.

Enable only for a measured pilot with `RHIZE_LAYA_DEVFLOW_SHADOW=1`. The command still requires explicit `--mode shadow`; absence of this flag leaves the incumbent path. Pass the current deterministic stage evidence file; the adapter hashes its bytes without sending or storing them. Supply only the allowed bounded signal labels, without prompt text, code, paths, credentials, or logs:

```json
{"signals":["test_passed"],"required_checks_passed":true,"independent_review_passed":false,"approval_satisfied":false}
```

Allowed signals: `test_failed`, `test_passed`, `requirements_unmapped`, `diff_large`, `unresolved_dependency`, `review_pending`, `stuck_repeat`, `protected_file`, `source_stale`, `none`. The three hard-gate fields are facts from the incumbent workflow, not predictions. Set an unavailable or unverified gate to `false`, never to `true`. The state is hashed in the receipt and omitted from telemetry. A fresh private receipt path outside the repository is required for each study call; the adapter refuses to overwrite a prior receipt.

```sh
printf '%s\n' '{"signals":["test_passed"],"required_checks_passed":true,"independent_review_passed":false,"approval_satisfied":false}' |
  python3 "$CLAUDE_PLUGIN_ROOT/scripts/typed_checkpoint.py" \
    --stage check --evidence "/private/path/current-stage-evidence.json" \
    --model typed-decisions --mode shadow --receipt "/private/path/check-shadow.json"
```

The adapter uses loopback `http://127.0.0.1:8000` by default; `--base-url` is restricted to loopback HTTP. It requires the server to route the requested checkpoint. An invalid, unavailable, or mismatched response records `unavailable` and leaves Arm A in force. No call runs on every token or tool event; run once after each meaningful checkpoint evidence packet, then associate the receipt with the later accepted-task outcome. Do not count a shadow directive as an intervention. The Laya 0.3.20 `typed-decisions` pilot has uncalibrated confidence and no Rhize task-benefit evidence yet.
