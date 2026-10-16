# Typed decision research

This is the local adaptation of [autoresearch](https://github.com/karpathy/autoresearch)'s fixed evaluator, editable candidate and keep/discard ledger. Upstream autoresearch trains nanochat with CUDA on an NVIDIA GPU; it does not train Laya on this Apple Silicon host. This runner tests Laya checkpoints, question wording and abstention thresholds against human-adjudicated Rhize decisions. [Foreman](https://github.com/thruwire/foreman) informed the bounded, multi-check GSD supervision questions and deterministic candidate policy. No Foreman or autoresearch source code is copied here. Their published results do not establish a Rhize benefit.

The runner is a development tool. Keep real labeled cases, candidate files and ledgers in a private ignored directory outside tracked source. It sends only local loopback requests. It never launches a coding agent, modifies a worker, or enables advisory mode. The provider must return the checkpoint requested in each candidate.

## Case contract

One JSON object per line, with a stable `case_id`, `group_id` (task/source identity), `decision_type`, `stratum`, `label_source`, `adjudicated: true`, bounded `state`, named `questions`, and matching `labels`. Each question has `type: choice|noul` and nonempty `instructions`. Choice questions also have a `criteria` object and a label naming one option. Noul labels are booleans. `arm_a` is an optional map of the incumbent's recorded predictions with the same question IDs; missing Arm A data is reported as unavailable. Use `critical_...` strata for safety and authorization cases. Do not use Laya's own answers as ground truth.

For the generic non-pilot case contract, the seed assigns all cases from one group to train, validation, or locked holdout at 50/25/25. The exact corpus, seed and split hashes enter a manifest. A release candidate needs at least 200 adjudicated cases per decision type and at least 50 holdout cases comprising 25% of that type. Smaller runs are exploratory and the ledger says `release_eligible: false`. The operator prepares a new private split directory, then gives the candidate-generating agent only `train.jsonl`, `validation.jsonl`, and `manifest.json`; the reviewer retains `holdout.jsonl` separately.

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

The search phase evaluates train and validation only, ranks candidates first by fewer critical misses, then higher accuracy, then lower abstention, and appends every keep/discard result. Inspect all strata, Brier diagnostics where defined, latency and token usage; the provisional rank is not a release decision. Select and freeze exactly one kept candidate, put it alone in a candidate file, then run holdout once using the digest printed by search:

```sh
python3 evals/typed-decision/research.py --phase holdout \
  --manifest /private/path/new-split/manifest.json \
  --holdout /private/path/new-split/holdout.jsonl \
  --candidates /private/path/frozen.json --ledger /private/path/results.jsonl \
  --frozen-candidate-sha256 <printed-candidate-hash>
```

The ledger rejects a candidate never kept on development data and a second holdout run for the same corpus. Preserve the exact ledger and source hashes. The CLI does not provide a tamper-proof enclave; keep the holdout in the reviewer's separate workspace until the freeze. Real promotion needs the predeclared quality/safety bounds in the private decision-layer plan, an independent review and matched software-task outcomes. The 1,000,000-token cap applies to incremental coding-agent tokens for duplicate controlled tasks; local research calls do not consume that cap, but their inference time and compute are reported separately.

## Task outcome trials and control budget

Use `task_trials.py` with a private SQLite path. Hash the frozen task and fixture externally and use the same hashes for both arms. Before each duplicate control, write current host token-limit evidence to an owner-only file and call `reserve-control --task-hash <sha256> --fixture-hash <sha256> --limit-tokens <maximum> --host-limit-evidence <file>`. The reservation checks the global 1,000,000-token allowance under a SQLite write lock. The host must actually enforce that maximum during the run; the ledger cannot interrupt an agent. If the host lacks a per-run limit, do not launch that duplicate control.

Finalize the reserved ID with `finalize --run-id <id> --arm A_control --status completed|failed|incomplete --usage-file <file> --outcome accepted|rejected|undetermined --outcome-evidence <file> --wall-ms <milliseconds>`. The usage JSON records `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`, and `reasoning_tokens`; nullable ancillary counts stay null. Missing input/output usage requires `--usage-unavailable-reason` and charges the full reservation. Report any host limit overrun instead of masking it. Finalize B treatments and single-execution randomized A/B tasks with their own IDs and the same task/fixture hashes.

The private outcome evidence is a JSON object with exactly `schema: "rhize-typed-task-outcome-v1"`, `outcome` matching the CLI, `quality_score` from 0 to 100 or null, Boolean `required_checks_passed` and `independent_review_passed`, nonnegative integer `critical_failure_count` and `rework_count`, and the frozen `rubric_sha256`. An `accepted` outcome requires scored quality, passed checks and independent review, and zero critical failures. Freeze the rubric before running either arm and preserve the underlying review packet separately. `report` distinguishes assigned from evaluable pairs; only completed runs with reported input/output tokens, quality, wall time, a determinate outcome and the same rubric contribute to the paired B-minus-A mean deltas. The ledger stores hashes and compact scores, not prompts or source code. Its outcomes are operator-reported and need independent acceptance evidence.

Run a small replayable 4–6-pair pilot with identical rubric and frozen fixtures, then use randomized single-execution tasks on the real project. Predeclare quality, time and token analyses; count all fallbacks and missing data. Keep the duplicate-control total below the user's 1,000,000 incremental coding-agent token ceiling.

## Known limitations

- No real Rhize labels have been imported yet; fixtures only prove the evaluator contract.
- Laya 0.3.20's `typed-decisions` checkpoint emitted an invalid-temperature warning on first load, so its confidence needs task-specific calibration. Hold advisory mode until that is resolved or measured on the locked corpus.
- The candidate runner changes questions/checkpoints/thresholds, not Laya weights. Domain fine-tuning is a separate experiment after sufficient labels and a compatible training environment exist; compare it as another pinned candidate, then use the same holdout and project trial.
- Foreman-style thresholds are provisional and only produce `candidate_directive` in shadow. `FINISH` requires actual passed checks and independent review even as a candidate.

## Integrated workflow pilot v2

`pilot_cycle.py --research-root PRIVATE_DIRECTORY` is the daily workflow coordinator. Its automatic
CLI processes only `workflow-pilot-v2`; historical v1 exports and frozen experiments remain intact.
The older callable `legacy_cycle` is retained for explicit v1 fixture/exploratory compatibility,
not selected by this CLI. Automatic `--minimum-labels` defaults to **30** and is bounded to 20..10000 (the old 200-label floor is retired; see the advise-v1 gate below).

V2 export adds `cohort_version`, `normalization_version`, `collection_source_sha256`, opaque
`grouping_keys`, `task_family`, `host`, `candidate_ids`, human `routing_choice` and nullable
`arm_a_choice`. Export accepts only eligible decisions with bound human adjudication. It preserves
the original sealed model state/questions; Arm A is evaluation evidence, never a model feature.
A no-match catalog result is distinct from an actual general-family consultation.

Versioned taxonomy labels from `rhize-context-manager/scripts/pilot_labels.py` are a separate
answer key. When they exist, the cycle exports them instead of legacy human labels, using the
bases the private label policy accepts (human only unless the operator enables
`ai_model_reviewed`), and holds `mixed_label_schemas` if both kinds are present. Rows then also
carry `label_basis`, `family`, `phase`, `areas`, `risk_flags`, `choice_basis` and the richer
`stratum` (`routine`, `elevated`, `critical`; the evaluator still counts `critical*` misses).
Only explicitly judged routing choices are scored. Slice gates (each route >=15, >=4 families
>=15, >=20 elevated or critical) apply on top of the label minimum, and every output reports its label
bases. `research.py` accepts `label_basis` `human_adjudicated` (the default when missing) or
`ai_model_reviewed`.

Use the [collection and human review contract](../../rhize-context-manager/docs/decision-pilot.md)
for opt-in config, context-before-consult commands, inherited continuations, evidence bases,
normal-check measurement and focused daily review. Context is agent-asserted, consultation and
outcomes are operator-reported, measured checks are automatic artifacts, and human labels require
explicit adjudication. These evidence types cannot substitute for one another.

The workflow objective counts one consultation choice per case. The evaluator imports the same
`pilot_routing.decode_scores` used by live inference: finite bounded scores, deterministic argmax
and tie break, exclusion mask, then threshold abstention. It does not grade three binary Noul
answers as three independent routing decisions. V2 relevance values are uncalibrated and its
`brier_mean` stays null; generic non-pilot choice/Noul diagnostics retain their existing semantics.

In addition to the label minimum (default 30), provisional development gates apply to the **whole
corpus**, including the reserved holdout, and require the following. They do not guarantee these
counts in train or validation separately:

- At least 20 connected independent groups and at least two task domains.
- At least 20 labels per represented domain; no connected group over 20% of the corpus.
- Consistent collection-source and normalization versions, with no incompatible cohort mixture.

Diversity failures are reported holds, never silent filtering or release qualifications.
Mixed source/cohort/normalization metadata holds; malformed exported records produce a
preserved export-contract failure. Grouping joins session,
parent/task ancestry, normalized bounded input/template and separate exact prompt hashes. Repeated
input in different sessions cannot cross splits. Append-only split reservations are stored before
materializing new split files. Later bridges between assigned splits hold without reassigning the
old holdout. Legacy held-out identities are checked only through manifest membership metadata;
missing metadata or overlap holds the v2 cycle without opening old holdout cases. Cross-version
checks use only unchanged session/prompt identities, not differently normalized input/task keys.
Legacy membership-manifest digests enter attempt identity, so reviewed metadata correction can
create a new attempt while preserving the prior hold. Do not delete or rewrite split assignments
to clear holds. Newly observed groups receive an approximate 50/25/25 hash partition; frozen
assignments, not a changing group fingerprint, govern their subsequent split.

The coordinator creates five fixed wording/abstention candidates and makes at most 2,400 development
requests with a default 180-second deadline. It serializes with pending collection inference.
Corpus/cohort/config/source/scorer/evaluator identities bind each immutable attempt. Failed,
interrupted and malformed-corpus attempts remain visible and unchanged attempts are not replayed.
Preflight identity includes actual receipt/context/observation fingerprints and v2 helper sources,
so a genuine binding-input repair changes the identity. Invalid CLI bounds return structured
failure JSON; unavailable failure-receipt persistence is reported rather than hidden.
Insufficient labels creates a separate durable non-error hold, not a failed experiment.

Successful development search freezes one candidate for human review (`holdout: not_run`). The daily
job never runs a holdout, trains weights, fabricates labels or launches duplicate coding tasks.

### advise-v1 baseline gate (`workflow-fit`)

The 200-label floor is retired for the pilot: advise is earned by a reserved promotion cohort of at least `minCohort` = 30 cases, and the 200-case figure above remains only for the generic non-pilot research release gate (`research.py`). After the search, the cycle sends only the default wording (no instruction
overrides, no abstention threshold; the constants `ADVICE_QUESTION`/`ADVICE_CANDIDATES`/`ADVICE_POLICY` in
`decision_pilot_v2.py`) through one attempt of `typed_promotion.run_attempt`:

- Groups split by `sha256('split:'+group) % 3`: 2/3 tuning, 1/3 promotion. The baseline is the tuning
  majority class, frozen in the cohort's `reserve` event; it predicts the same promotion cases.
- The group is the statistical unit: one case per group (the smallest case id), never a group an earlier cohort
  of the decision used. The cohort (at least `minCohort` = 30 cases from 30 distinct groups) is written to
  `<root>/workflow-fit/advise-cohorts.jsonl` (case ids and group hashes) BEFORE Laya is called, and consumed by
  exactly one verdict. The availability probe is mandatory and must return exactly `True`; anything else holds
  without a ledger write. Attempt k tests at `alphaBase * 2^-(k-1)`; the budget is per decision, not per policy
  or Laya revision.
- Abstentions, timeouts and unavailable answers count as Laya wrong; coverage must be at least `minCoverage`.
- Pass needs the one-sided Clopper-Pearson lower bound of b/(b+c) above 0.5 (b: Laya right and baseline wrong,
  c: the reverse), a balanced accuracy above the baseline's, and for every class with at least 10% tuning
  share (zero-count classes included) at least 3 cases and recall at least 0.5. A critical decision also needs
  `minCriticalCases` trusted `critical_if_wrong` cases and zero critical misses; a critical miss is any such case
  Laya did not get right, an abstention or unavailable answer included.
- A pass calls `decision_registry.mutate('workflow-fit', 'advise', actor='cycle', reason='gate_pass')` with the
  binding `{policySha256, instrumentSha256, layaRevision, cohortId}`; a refused write (pin, stale revision,
  corrupt state) is recorded in the status receipt, never raised. `modes.json` no longer exists.
- With `advise` in force the cycle spends no attempt and probes Laya before re-querying it (an outage holds the
  check instead of scoring every answer wrong). It scores the latest `demote.window` cases once
  `demote.freshLabels` new cases accrue, and demotes to `shadow` (`gate_demote`) after `demote.consecutive`
  consecutive evaluations below the baseline (state in `<root>/workflow-fit/advise-demotion.json`); a critical
  miss demotes at once. A binding that went stale (new policy hash) is reset to `shadow` (`binding_stale`)
  so the gate can earn it again.
- Gate settings come from the registry entry's `advise` object (`rhize-context-manager/catalog/decision-registry.json`).

The generic holdout commands above describe a separately authorized review workflow;
they are not part of the automatic pilot. Existing Arm A continues executing throughout shadow
collection; Arm B recommendations cannot be credited with Arm A's task outcomes. `arm_a_coverage` records
known/total incumbent choices by split; comparison remains unavailable if even one required
incumbent choice is missing, rather than substituting a score for missing evidence.

## The advise learning loop (every advise decision, plan §8)

Surfaces record each advise-capable decision with `typed_advice.advise` (`<root>/<decision>/choice|snapshot|outcome/<id>.json`; `groupSha256` hashes the optional `group`, default the decision key). Three scripts close the loop; the daily autolabel job runs them in this order under its run lock.

1. **Labels** (`rhize-context-manager/scripts/typed_decisions/choice_labels.py run [--decision D] [--max-cases N] [--dry-run]`). For every advise decision except `skill-fit` and `workflow-fit` (which keep their own labelers), choice records with a snapshot and no label get a blinded packet: the snapshot request re-sanitized by `pilot_redaction` (its source hash is stored as `redactor`), the question, and candidate ids with criteria under neutral shuffled keys. Laya's recommendation, probabilities, mode, arm, outcome and earlier labels never enter a packet. Two no-tools annotators (Claude and Codex through `skillfit_labels`' backend) answer independently; identical answers are accepted, a split goes to a reviewer model that is neither annotator, an unresolved review is stored as ambiguous. Labels are write-once `<root>/<decision>/label/<id>.json` (`rhize-typed-choice-label-v1`, `basis: ai_model_reviewed`, `rubricVersion`, annotators, reviewer, `evidenceSha256`). The run spends at most `maxCases` (default 50) model-labelled cases in total, shared fairly across decisions, and shares `pilot_autolabel`'s `state/run.lock` (a held lock exits quietly with zero calls). Right after the import, a critical-tier decision with an imported label that contradicts a shown advice (record mode `advise`, arm `treatment`, `criticalIfWrong`, Laya status `ok`, label not ambiguous) is demoted to `shadow` (`critical_miss`) through `decision_registry.mutate`; `no_change` and pins are recorded in the run receipt `<root>/choice-labels/receipts/`.
2. **Cycle** (`decision_cycle.py run`). The skill-fit cosign cycle is unchanged. After it, `run_advise` handles every decision with an `advise` entry except `workflow-fit` (owned by `pilot_cycle.py`). The gate is **prospective**. Records are the ones on one binding: `policySha256` (the registry state's once advise is earned, else the most recent record's), the entry's advise instrument hash and the running Laya revision. Group is `groupSha256` (falling back to the decision id); skill-fit uses the session hash and the label's `bestSkill`, with the contract's `advise-v1` policy hash (the one the Node router writes and reads). With a tuning baseline available and no open cohort, the first pass probes Laya (must return exactly `True`) and appends an `open` event (`openedAt`, rule `earliest-record-per-promotion-group-after-open`) and holds as `cohort_opened`; nothing recorded before that moment is ever a case. Later passes collect, for the open cohort, the earliest record of each promotion-split group created after `openedAt` on that binding (skipping groups earlier cohorts used; the selection never looks at a label, outcome or Laya answer) and hold as `cohort_collecting` until at least `minCohort` such groups are labelled (and, for a critical decision, `minCriticalCases` critical cases); then the cohort is evaluated once and `consumed` with its case ids and group hashes. A binding change `abandon`s the open cohort (its attempt and alpha stay spent) and opens a new one. The baseline is the tuning-split majority; the required classes are the tuning classes with at least 10% share. Laya's answers are the ones recorded at decision time. A pass promotes to `advise` with `{policySha256, instrumentSha256, layaRevision, cohortId}`; with `advise` in force the rolling demotion rule runs on the latest advise-arm treatment cases (`gate_demote`), and a critical decision demotes at once (`critical_miss`) on any critical case Laya did not get right among all labelled cases with a `shown` marker since advise began, not only the window. Pins, `off`, `cosign` and registry refusals are recorded holds. `--no-advise` skips the pass.
3. **Scoreboard** (`typed_decisions/scoreboard.py render`). One advise row per decision: mode, labelled n, last verdict, accuracy vs baseline, CP lower bound, coverage, critical cases and misses, attempts used and the next alpha.
