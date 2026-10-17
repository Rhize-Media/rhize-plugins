# Local typed checkpoint signal (shadow and advise)

The related `scripts/typed_selection.py` accepts only source-bound, bounded candidate
metadata for `tool_trace_risk` or `browser_qa`. Each candidate must already be legal, and
browser QA requires an approved test surface. Pipe a JSON envelope containing `schema`,
`capability`, `sourceSha256`, `taskSignals`, `candidates`, `incumbentIds`, and `policy` to
`--mode shadow --evidence <current deterministic evidence file>`. The receipt ranks
candidates for review; it does not click, dispatch, grant approval or change this
checkpoint's verdict. `--mode advise` (`browser_qa` only; `tool_trace_risk` stays shadow-only)
asks the `browser-qa-selection` decision for one pick among the approved surfaces plus `none`;
see [Advise mode](#advise-mode). See [the pilot matrix](../../docs/typed-decision-layer.md).

The optional adapter at `scripts/typed_checkpoint.py` asks local Laya a bounded set of Noul questions at an **existing** Dev Flow stage. In `shadow` mode it is observational. The deterministic impact map, check, test-evidence, review, and release contracts continue to decide the gate. No worker action, permission, test pass, review pass, approval, commit, merge, or deployment follows from its `candidateDirective`.

Run with `--mode shadow` for a measured observation or `--mode advise` for the earned advisory line (below); `--mode disabled` (the default) leaves the incumbent path. Pass the current deterministic stage evidence file; the adapter hashes its bytes without sending or storing them. Supply only the allowed bounded signal labels, without prompt text, code, paths, credentials, or logs:

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

## Advise mode

`typed_checkpoint.py --mode advise` (decision `devflow-next-action`) and `typed_selection.py --mode advise` (decision `browser-qa-selection`) call the shared `typed_advice` client. The **registry decides whether anything is shown**: the decision stays in `shadow` (Laya is asked and recorded, nothing is shown) until the baseline gate earns `advise`, and a stale policy, instrument or Laya binding reads as `shadow` again. A deterministic holdback share (15% for the critical next-action decision, 10% for browser QA) is asked but never shown, so outcomes are collected in both arms.

Checkpoint inputs: the same bounded stdin state and `--evidence` file as shadow mode, plus optional `--summary-file` (a short text, scrubbed and capped at 1,500 characters together with the signals) and `--files-from` (repo-relative file hints, one per line; absolute, parent-relative and secret-shaped names are dropped). Candidates are `continue`, `investigate`, `verify` and `escalate`. `criticalIfWrong` is computed by code: true unless all three hard-gate fields in the state are true. The output is `{decisionId, mode, holdback, recommendation, advice}` plus the echoed hard gates and `gateChanged: false`; `advice` is empty unless a recommendation is earned and shown.

```sh
printf '%s\n' '{"signals":["test_passed"],"required_checks_passed":true,"independent_review_passed":false,"approval_satisfied":false}' |
  python3 "$CLAUDE_PLUGIN_ROOT/scripts/typed_checkpoint.py" --stage check \
    --evidence "/private/path/current-stage-evidence.json" --mode advise
python3 "$CLAUDE_PLUGIN_ROOT/scripts/typed_checkpoint.py" outcome --decision-id <decisionId> --chosen verify
```

Record the action you actually took with the `outcome` subcommand (also on `typed_selection.py`); the first write wins. An unavailable, timed-out or invalid Laya answer shows no advice and exits 0. The advisory line never changes obligations, approvals, required checks or any hard gate, and you may override it.
