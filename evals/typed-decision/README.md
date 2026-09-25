# Typed decision research

This is the local adaptation of [autoresearch](https://github.com/karpathy/autoresearch)'s fixed evaluator, editable candidate and keep/discard ledger. Upstream autoresearch trains nanochat with CUDA on an NVIDIA GPU; it does not train Laya on this Apple Silicon host. This runner tests Laya checkpoints, question wording and abstention thresholds against human-adjudicated Rhize decisions. [Foreman](https://github.com/thruwire/foreman) informed the bounded, multi-check GSD supervision questions and deterministic candidate policy. No Foreman or autoresearch source code is copied here. Their published results do not establish a Rhize benefit.

The runner is a development tool. Keep real labeled cases, candidate files and ledgers in a private ignored directory outside tracked source. It sends only local loopback requests. It never launches a coding agent, modifies a worker, or enables advisory mode. The provider must return the checkpoint requested in each candidate.

## Case contract

One JSON object per line, with a stable `case_id`, `group_id` (task/source identity), `decision_type`, `stratum`, `label_source`, `adjudicated: true`, bounded `state`, named `questions`, and matching `labels`. Each question has `type: choice|noul` and nonempty `instructions`. Choice questions also have a `criteria` object and a label naming one option. Noul labels are booleans. `arm_a` is an optional map of the incumbent's recorded predictions with the same question IDs; missing Arm A data is reported as unavailable. Use `critical_...` strata for safety and authorization cases. Do not use Laya's own answers as ground truth.

The seed assigns all cases from one group to train, validation, or locked holdout at 50/25/25. The exact corpus, seed and split hashes enter a manifest. A release candidate needs at least 200 adjudicated cases per decision type and at least 50 holdout cases comprising 25% of that type. Smaller runs are exploratory and the ledger says `release_eligible: false`. The operator prepares a new private split directory, then gives the candidate-generating agent only `train.jsonl`, `validation.jsonl`, and `manifest.json`; the reviewer retains `holdout.jsonl` separately.

## Candidate contract and commands

`candidates.json` is an array of `{ "id": "baseline", "model": "typed-decisions", "instructions": {}, "abstain_below": 0.0 }`. The optional `instructions` map replaces only question wording. The evaluator, labels, split seed and scoring code remain fixed. The candidate list must start with the pinned base checkpoint, then may try other Laya checkpoints and bounded wording/threshold variations. A runner call caps candidates at 12 and requests at 2,400 by default. Log search experiments separately from controlled software-task A/B runs.

```sh
python3 evals/typed-decision/research.py --phase prepare \
  --cases /private/path/labeled.jsonl --out-dir /private/path/new-split \
  --seed frozen-study-seed

python3 evals/typed-decision/research.py --phase search \
  --manifest /private/path/new-split/manifest.json \
  --train /private/path/new-split/train.jsonl \
  --validation /private/path/new-split/validation.jsonl \
  --candidates /private/path/candidates.json --ledger /private/path/results.jsonl
```

The search phase evaluates train and validation only, ranks candidates first by fewer critical misses, then higher accuracy, then lower abstention, and appends every keep/discard result. Inspect all strata, calibration/Brier sums, latency and token usage; the provisional rank is not a release decision. Select and freeze exactly one kept candidate, put it alone in a candidate file, then run holdout once using the digest printed by search:

```sh
python3 evals/typed-decision/research.py --phase holdout \
  --manifest /private/path/new-split/manifest.json \
  --holdout /private/path/new-split/holdout.jsonl \
  --candidates /private/path/frozen.json --ledger /private/path/results.jsonl \
  --frozen-candidate-sha256 <printed-candidate-hash>
```

The ledger rejects a candidate never kept on development data and a second holdout run for the same corpus. Preserve the exact ledger and source hashes. The CLI does not provide a tamper-proof enclave; keep the holdout in the reviewer's separate workspace until the freeze. Real promotion needs the predeclared quality/safety bounds in the private decision-layer plan, an independent review and matched software-task outcomes. The 1,000,000-token cap applies to incremental coding-agent tokens for duplicate controlled tasks; local research calls do not consume that cap, but their inference time and compute are reported separately.

## Known limitations

- No real Rhize labels have been imported yet; fixtures only prove the evaluator contract.
- Laya 0.3.20's `typed-decisions` checkpoint emitted an invalid-temperature warning on first load, so its confidence needs task-specific calibration. Hold advisory mode until that is resolved or measured on the locked corpus.
- The candidate runner changes questions/checkpoints/thresholds, not Laya weights. Domain fine-tuning is a separate experiment after sufficient labels and a compatible training environment exist; compare it as another pinned candidate, then use the same holdout and project trial.
- Foreman-style thresholds are provisional and only produce `candidate_directive` in shadow. `FINISH` requires actual passed checks and independent review even as a candidate.
