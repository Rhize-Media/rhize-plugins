# Workflow decision measurement pilot

This opt-in pilot measures one decision: should a task consult the content workflow,
a general executable workflow, or neither? The existing agent decides from the full task.
Laya sees only a fixed allowlist of task signals and three static candidate descriptions.
This deliberately limited input can miss negation and conversation context. Empty signals
abstain without inference. Shadow recommendations never change selection or approvals.

## Activate and verify

Merge `"decisionPilot":{"enabled":true,"mode":"shadow"}` into the existing private
workflow-selection config alongside `"schemaVersion":1,"enabled":true`. Keep the configured
procedural launcher and other settings. Set `enabled` false to stop new pilot capture.
Existing pending observations remain available for an explicit drain. Do not set the older
`RHIZE_LAYA_WORKFLOW_SHADOW` flag as well; the pilot takes precedence when configured.

The existing UserPromptSubmit workflow hook writes its opportunity first, then enqueues a
redacted observation and starts a detached worker. Duplicate delivery cannot replace the first
observation or result. Workers serialize on a nonblocking lock, process at most 20 pending
observations within a 45-second batch (plus at most one 5-second request), and disconnect all
host pipes. Failed inference is retained, not retried into a success. Source changes invalidate
pending observations instead of scoring them with a different question implementation.

Run a pinned Laya `typed-decisions` checkpoint at `http://127.0.0.1:8000`. Manage startup using
the host's existing service mechanism; verify package version, checkpoint files and a real
synthetic request, not merely a listening port. Keep downloads offline after provisioning.
The worker validates the returned checkpoint and usage. Source digests identify client code;
server checkpoint-file identity must also be retained in the local deployment evidence.

Install/update the plugin through each host's normal lifecycle. Review changed hooks through
its native trust UI; never hand-edit approval hashes. Start a fresh task after cache updates.
A source release does not prove an already-running task loaded it. Verify both hosts using
actual native tasks and private receipts. Synthetic hook payloads establish contract behavior
only. The optional Stop hook records exact native host/session/turn matches; hosts without
that identity record an unavailable diagnostic rather than attaching to the latest task.
Stop never means passed checks or accepted work.

## Operator commands

Run `python3 scripts/decision_pilot.py` from the Context Manager plugin:

- `report`: coverage, missing observations/results/outcomes, host attribution, disagreements,
  human-labeled accuracy, local latency/usage and separately reported task outcomes.
- `queue`: all failed/missing scores and disagreements, pending baselines, plus a deterministic
  20% sample of agreements. Review the original task, not just the bounded signals.
- `drain`: process pending work, including work left by an unavailable worker.
- `adjudicate --id ID --evidence PRIVATE_JSON`: import an actual human-reviewed label.
- `outcome --id ID --evidence PRIVATE_JSON`: attach measured task results, including failures.
- `export --out NEW_PRIVATE_JSONL`: export human-labeled cases for research; never overwrite.

The default storage is `$XDG_DATA_HOME/rhize/workflow-selection/pilot`, or
`~/.local/share/rhize/workflow-selection/pilot`. `--root` and `--receipts` support isolated
fixtures and explicit storage. Reports fail explicitly on malformed records or inventories
over 10,000 files. Historical workflow receipts without the pilot marker are excluded. Missing
observation files still count against the opportunity denominator. Raw prompts, code, paths,
customer text and transcripts are not captured. Host/session/task identities are hashes.

Each evidence document includes the exact `opportunityId` and collection `sourceSha256` from
`pilot/observations/ID.json`. All remaining keys are required; unknown values are JSON null.

Human label fields:

```json
{"opportunityId":"<64 hex>","sourceSha256":"<64 hex>","choice":"general","reviewer":"human-reviewer-id","basis":"human_adjudicated","stratum":"ordinary","reviewEvidenceSha256":"<64 hex>"}
```

`choice` is `content`, `general` or `none`. `stratum` is `ordinary`, `critical_safety` or
`critical_authorization`. A model may propose a label in a separate review artifact but cannot
mark it human-adjudicated. Preserve the original human review evidence privately. Record hashes
bind evidence; they do not attest its truth. Labels are immutable; corrections require a reviewed
new cohort rather than silently changing the answer key.

Task outcome fields:

```json
{"opportunityId":"<64 hex>","sourceSha256":"<64 hex>","outcome":"undetermined","qualityScore":null,"checksPassed":null,"reviewPassed":null,"criticalFailureCount":null,"reworkCount":null,"wallMs":null,"usage":{"input_tokens":null,"output_tokens":null},"rubricSha256":null}
```

`outcome` is `accepted`, `rejected` or `undetermined`. Accepted requires a quality score 0–100,
passed required checks, passed independent review, zero critical failures and the frozen rubric
digest. A cold self-review alone is not independent review. Usage and wall time must come from
actual host measurements; do not infer them from local Laya tokens, receipt counts or task text.
The task agent records the outcome at completion. This operator-reported evidence is separate
from workflow-selection execution/validation/capture stages; do not invent a workflow run to
complete an outcome. Unfinished tasks and missing host usage remain visible.

## Recurring research

Use the repository's `evals/typed-decision/pilot_cycle.py --research-root PRIVATE_DIRECTORY`.
It waits for 200 adjudicated labels by default (20 minimum for an explicitly exploratory run),
then exports cases, prepares stable session-group splits and evaluates a fixed bounded set of
wording/abstention candidates. It makes at most 2,400 requests with a 180-second wall deadline
by default. Local inference serializes with the live worker. The development search never
receives a holdout argument; the split manager retains it for separate reviewer use. Candidate
construction uses fixed templates, not an autonomous agent or model-weight training.

Every cohort/candidate/evaluator combination gets one attempt, including failed or interrupted
attempts. Unchanged inputs do not repeat a failed experiment. Inspect and resolve the recorded
failure before preparing an explicitly reviewed new experiment. Successful searches freeze one
candidate and request review. No holdout test, live promotion or duplicate coding task is launched.
A passing development score is not release authorization. The unchanged fixed evaluator and
`task_trials.py` contracts still govern holdout and later controlled outcome trials.

Schedule the operator cycle to drain pending work, refresh report/queue, and invoke research only
when reviewed cases exist. Keep reports and actual run receipts private; notify only for a new
failure, meaningful change or required human review. A daily check is sufficient during this pilot.
Reports must keep this study's Arm A (existing workflow decision) and Arm B (local shadow score)
separate from older workflow-discovery or memory-treatment experiments.
