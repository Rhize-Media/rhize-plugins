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

### Versioned decision diagnostics and operational deadlines

New research results declare `metrics_schema: rhize-typed-research-metrics-v2`. A critical
miss means a wrong or unresolved critical decision, including an abstention, for choice and
Noul alike. `critical_abstentions`, `critical_wrong_answers` and Noul
`critical_false_negatives` remain separate; `unsafe_actions` is null because inference does
not establish an executed action. Historical receipts retain their original definitions.
Search ranks only keeps with current metric semantics; a current holdout needs a matching
current keep, and any historical holdout use still blocks another use of that corpus.

Reports include per-decision/question/candidate-count confusion, class support, recall,
macro-F1, balanced accuracy, label bases and independent group counts. Reliability bins,
ECE and fixed coverage/error slices are descriptive uncalibrated diagnostics, not a fitted
threshold or an automation gate. Choice Brier is averaged across candidates; Noul is a
scalar squared error. Compare like candidate counts and question types. V2 relevance keeps
its Brier/calibration diagnostics unavailable. The majority comparator is frozen from the
training split and reused from the matching keep on holdout. Recorded Arm A remains a
separate comparator; missing incumbent predictions remain unavailable.

`operational.py` is a separate development replay using the same literal-loopback transport,
identity check and decoder. Supply the real caller budget: for example 800 ms for skill fit;
do not replace a surface's actual budget with the research runner's 20-second allowance.

```sh
python3 evals/typed-decision/operational.py run --cases PRIVATE_DEVELOPMENT.jsonl \
  --candidate PRIVATE_CANDIDATE.json --deadline-ms 800 --condition warm \
  --runtime-evidence PRIVATE_RUNTIME.json --output PRIVATE_NEW_REPORT.json
python3 evals/typed-decision/operational.py menu-panel --cases PRIVATE_CHOICE_CASES.jsonl \
  --output PRIVATE_NEW_ORDER_PANEL.jsonl
```

The candidate file is one JSON object using the existing candidate contract. Runtime evidence
is a bounded JSON object recording checkpoint/source hashes, hardware, dtype, thread/queue
settings and collection conditions; the report binds its bytes, not the truth of the operator's
assertions. No missing or different checkpoint is silently substituted. Runs are sequential,
at most 2,400 requests, with no retries. New output files are private and never overwrite a
prior result. Do not give this CLI locked holdout or promotion cases; it has no gate authority.

Every attempted case stays in the denominator. Reports distinguish `ok`, `late`, `timeout`,
`invalid`, `busy` and `unavailable`; deadline yield requires all of a case's questions to be
correct before the deadline. Critical unresolved/late cases remain missed decisions, not
observed unsafe actions. Latency percentiles use valid in-budget client calls, including
abstained calls, with n disclosed; timeout elapsed time is censored and remains separate.
Timing includes the shared client's health probe and response handling, but excludes native
host scheduling and evaluator grading. A replay is not a native-host latency measurement.
Separate cold/warm and concurrent field observations rather than pooling their populations.

The order panel rotates the *same* request/menu without changing gold labels or original
group IDs. Explicit `candidate_orders` survive canonical JSON and enter request identity.
Keep all related variants in one split and count their group once for inference. Order
disagreement compares successfully answered variants with the same state/questions/labels.
Curate additional candidate-count, distractor, missing-correct-choice/none and exclusion cases
with reviewed labels; the tool does not invent labels when menu semantics change. Use the
existing review queue for underrepresented independent groups, not repeated model calls as n.

### Complete-task uncertainty and optional cost evidence

Use `task_trials.py` with a private SQLite path. Hash the frozen task and fixture externally and use the same hashes for both arms. Before each duplicate control, write current host token-limit evidence to an owner-only file and call `reserve-control --task-hash <sha256> --fixture-hash <sha256> --limit-tokens <maximum> --host-limit-evidence <file>`. The reservation checks the global 1,000,000-token allowance under a SQLite write lock. The host must actually enforce that maximum during the run; the ledger cannot interrupt an agent. If the host lacks a per-run limit, do not launch that duplicate control.

Finalize the reserved ID with `finalize --run-id <id> --arm A_control --status completed|failed|incomplete --usage-file <file> --outcome accepted|rejected|undetermined --outcome-evidence <file> --wall-ms <milliseconds>`. The usage JSON records `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`, and `reasoning_tokens`; nullable ancillary counts stay null. Missing input/output usage requires `--usage-unavailable-reason` and charges the full reservation. Report any host limit overrun instead of masking it. Finalize B treatments and single-execution randomized A/B tasks with their own IDs and the same task/fixture hashes.

The private outcome evidence is a JSON object with exactly `schema: "rhize-typed-task-outcome-v1"`, `outcome` matching the CLI, `quality_score` from 0 to 100 or null, Boolean `required_checks_passed` and `independent_review_passed`, nonnegative integer `critical_failure_count` and `rework_count`, and the frozen `rubric_sha256`. An `accepted` outcome requires scored quality, passed checks and independent review, and zero critical failures. Freeze the rubric before running either arm and preserve the underlying review packet separately. `report` distinguishes assigned from evaluable pairs; only completed runs with reported input/output tokens, quality, wall time, a determinate outcome and the same rubric contribute to the paired B-minus-A mean deltas. The ledger stores hashes and compact scores, not prompts or source code. Its outcomes are operator-reported and need independent acceptance evidence.

The additive `pairedUncertainty` report clusters by task hash, averages fixture variants within
each task, then uses 1,000 fixed-seed task-bootstrap resamples for descriptive 95% intervals.
Fewer than two independent tasks leaves intervals null. The existing fixture-pair means are
preserved and explicitly differ from the new equal-task weighting. Small samples remain a pilot,
not a powered benefit result. Per-arm summaries retain failed/pending/unknown outcomes and rework.

`finalize --telemetry-file PRIVATE_TELEMETRY.json` optionally records a separate digest-bound
`rhize-task-telemetry-v1` packet in the same transaction. It has exactly `schema`,
`advice_exposure` (`shown|holdback|not_shown|unknown`), `advice_following`
(`followed|overrode|unknown`), and `local_inference_ms`, `local_forward_passes`,
`provider_cost_usd`, `review_cost_usd`, `local_cost_usd`. Numeric values are nonnegative finite
numbers or explicit null; forward passes are integers. Following/override requires shown advice.
Dollar fields must describe disjoint provider, review/label and local marginal costs; preserve
their underlying measured/estimated basis privately. Missing telemetry/cost/cache usage stays
null, not free. Recorded cost per accepted task includes costs of all arm attempts and requires
complete cost fields plus at least one independently accepted outcome. No new experiment,
human acceptance, or decision-mode change follows from a report.

Run a small replayable 4–6-pair pilot with identical rubric and frozen fixtures, then use randomized single-execution tasks on the real project. Predeclare quality, time and token analyses; count all fallbacks and missing data. Keep the duplicate-control total below the user's 1,000,000 incremental coding-agent token ceiling.

### Prospective task benefit lab

`benefit_lab.py` audits a **private development bundle** without executing tasks, calling a
provider, importing labels or changing decision authority. It complements `task_trials.py`
(token reservations, real task outcomes and task-cluster uncertainty), `operational.py`
(deadline replay and menu rotations), and the existing isolated Docker evidence harness.
It does not introduce another runtime controller or scheduled loop.

Freeze a reviewed protocol **before** collecting new trials, preserve that file separately,
then audit the completed or interrupted bundle:

```sh
python3 evals/typed-decision/benefit_lab.py freeze \
  --bundle /private/trial/protocol.json --output /private/trial/frozen.json
python3 evals/typed-decision/benefit_lab.py audit \
  --bundle /private/trial/bundle.json --frozen /private/trial/frozen.json \
  --output /private/trial/report.json
```

Inputs and referenced evidence files are bounded to 4 MiB each. References are relative
`{"path": "...", "sha256": "..."}` objects confined to the bundle directory; missing files,
symlinks, traversal and changed bytes fail closed. Outputs are new owner-only files; existing
reports are never replaced. Exit 0 means a valid report was written, **not** that the experiment
improved outcomes. Exit 2 returns a structured unavailable result without private error text.

The exact executable schema and a complete synthetic read-only diagnostic example are in
[`test_benefit_lab.py`](../../tests/typed-decision/test_benefit_lab.py). The fixture distinguishes
reading interpreter/dependency metadata for an import failure from reading the named failing
test and traceback for an assertion failure. It executes neither diagnostic nor task. Its
utility values and evidence are synthetic contract anchors, never real labels or acceptance.

The `rhize-benefit-protocol-v1` object freezes:

- UTC `created_at`, opaque `decision`, source and mandatory-control SHA-256 values with
  matching `source_evidence` and `required_controls_evidence` byte references.
- Two to twelve named `arms`, exactly one `baseline`; other development modes are `rules`,
  `shadow`, `advice` or `holdback`. Each pins `policy_sha256`, `question_sha256`, the same
  `required_controls_sha256`, `context_mode` (`original|brief`), `question_kind`
  (`broad|concrete`), matching `policy_evidence`/`question_evidence` byte references, and
  optional-observer condition `observer` (`on|off`). An off observer
  never disables required capture, approvals, safety controls or native guards.
- Up to 2,400 cases with opaque `id`, immutable `group_sha256`, and task, fixture, context,
  prompt, session and rubric hashes. The six `inputs` references must match those bytes.
  Related task/session/prompt identities cannot span independent groups.
- A bounded prospective `brief` (`intent`, `artifact`, `stage`, `constraints`, `missing_fact`),
  frozen `actions` with descriptions and reviewed utility in [-1, 1], and explicit
  `action_order`. More than one action may have positive utility. These are a separate
  experimental answer key; existing taxonomy labels and gate scoring remain unchanged.
- `pool` (`representative|challenge`), `variant` (`original|order|distractor|paraphrase|urgency|
  no_correct_action`) and original `parent`. Variants retain task/fixture/session/group
  identity. Order-only variants preserve menu, brief, context, prompt and rubric semantics. A named review binds
  the SHA-256 of the exact case excluding its `review` field, with underlying review evidence.
  Semantic edits require a newly reviewed case; there is no automatic label propagation.

`freeze` writes a `rhize-frozen-benefit-protocol-v1` envelope containing the protocol, its
canonical digest and automatically recorded UTC `frozen_at`. `audit` requires equality with
that separately preserved snapshot and rejects trials dated before the freeze or in the future. Digests
use UTF-8 JSON with sorted keys, compact separators and finite numbers. This proves byte and
declared chronology consistency, **not** an independently witnessed preregistration or native
prompt/session binding. Independently verify original authorized context before admitting a
real case. Missing historical context stays deferred; never reconstruct earlier capture.

The `rhize-benefit-bundle-v1` has exactly `schema`, `protocol`, `runs`, `judge_anchors` and
`cache_bindings`. Each run has an opaque `id`, `case`, `arm`, matching `protocol_sha256`, UTC
`observed_at` after protocol creation, `status` (`completed|failed|incomplete`), nullable
`selected` and `proposed` actions, nullable `confidence`, `exposure` and `following` as in
the existing telemetry contract. Following/override must agree with the two actual actions;
baseline, shadow and holdback cannot show advice. Preserve every attempt under a distinct ID.

Run `artifact`, `checks`, `correction`, `outcome`, `policy_evidence`, `reward_evidence` are
nullable byte references. `acceptance` contains `value` (`accepted|rejected|undetermined`),
`reviewer` and `evidence`. Undetermined uses null reviewer/evidence. An accepted task needs
explicit acceptance evidence, a completed artifact and checks, plus the existing
`rhize-typed-task-outcome-v1` contract with scored quality, passed checks and independent
review, no critical failures, the frozen rubric and matching `rework`. Invocation, successful
checks and exit 0 never establish acceptance. The lab checks supplied evidence consistency;
it does not authenticate a reviewer or independently grade their work.

Explicit accepted/rejected evidence is a `rhize-benefit-acceptance-v1` JSON object with exactly
`schema`, `case`, `arm`, `protocol_sha256`, `artifact_sha256` (null if no artifact), `outcome`,
`reviewer`, UTC `recorded_at`, and declared `basis` (`human|independent_model|fixture`). These
must match the exact run and artifact; the answer cannot predate the run or lie in the future.
Reports separate those bases. This is consistency checking of an explicit supplied answer,
not authentication of a human reviewer; fixture acceptance never establishes real benefit.

Run `wall_ms` and each `tax_ms` component (`prepare`, `schedule`, `queue`, `health`, `forward`,
`decode`, `record`, `task`) are finite nonnegative measurements or null. Components must be
disjoint and their known sum cannot exceed wall time. Do not double count a request envelope
and its health/forward children. Missing native scheduling, orchestration or recording stays
null and makes the full-tax comparison incomplete. Known stages that do not account for the
whole wall envelope leave explicit `unattributed_ms` and an incomplete flag. Keep cold/warm and epoch cohorts in separate
protocols. Reuse `task_trials.py` for token/cost accounting and the host-enforced duplicate cap.

Optional `reward` in [0, 1] requires `reward_evidence`; exact-menu `logging_probabilities` and
`target_probabilities` require `policy_evidence`. Otherwise leave all null. The per-arm,
per-pool self-normalized importance estimate holds on missing data, absent target support or
unstable weights. Effective sample size describes rows, not independent tasks. Logged
probabilities must come from the actual assignment policy, never model confidence or invented
propensities. This is an offline descriptive diagnostic with no causal or deployment claim.

`judge_anchors` bind an artifact, independent expected and observed Boolean judgments,
reviewer evidence and preserved blinding evidence. Reports count false accepts and all
disagreements but do not claim verified blindness. `cache_bindings` check exact source,
policy, question, context, fixture and menu hashes with evidence. The menu hash covers
`{"actions": ..., "action_order": ...}` so order changes invalidate a cache binding. A valid binding proves
invalidation behavior only; it never authorizes reuse, supplies permission or establishes a win.

Reports retain every status, missing expected case, unknown outcome and incomplete timing.
Proposed-action diagnostics are separate; shadow advice never inherits the incumbent's acceptance.
Action utilities are equal-weighted within case, then within independent group. A group
requires an observed action for every expected case/attempt before it is scored or paired;
missing variants cannot silently improve a mean. Representative and challenge pools remain
separate. Use the existing task ledger for accepted-task quality/time/token uncertainty;
action utility alone is not that outcome. Review candidates are at most one representative
per pool/group, ranked by judged regret times uncertainty, with correction/override/rework
signals preserved. Every case with a context gap occupies a separate diagnostic list, including
missing-context siblings of eligible cases in the same group, and never receives a review
priority. This deterministic selection is not a random population accuracy sample.

Implementation coverage of the development plan:

| Direction | Working support and remaining evidence |
| --- | --- |
| Outcome chain | Verified input/action/exposure/artifact/check/acceptance links; missing stages visible. Prospective real capture still required. |
| Full decision tax | Disjoint timing stages and incomplete flags by arm; real native measurements required. |
| Narrow benefit pilot | Frozen read-only diagnostic fixture and protocol; use the existing ledger, identical rubrics and independent task groups for real trials. |
| Context repair | Versioned prospective brief and separate missing-fact diagnostics; no historical backfill. |
| Selective intervention | Baseline/shadow/holdback/advice contrasts and unresolved-action accounting; no live routing change. |
| Counterfactual lab | Group-bound frozen variants and per-action utility; execute artifacts only through the existing isolated harness with real oracles. |
| Review allocation | Group-deduplicated regret/uncertainty and correction queues; no label import. |
| Judge audit | Digest-bound anchors, false accepts and disagreement counts; independent anchor collection and exposure verification still required. |
| Rules and exact caches | Exact invalidation audit plus rules arm; review accepted-task wins in the existing ledger before distillation or reuse. |
| Adversarial menus | Reviewed challenge variants and explicit order; use operational replay for model comparisons. |
| Acceptable action sets | Separately versioned reviewed utility maps; no change to existing single-label gates. |
| Procedure quality | Duplicate-description and acceptable-action diagnostics against frozen menus; procedure correctness needs an oracle/review. |
| Concrete questions | Pinned broad/concrete question hashes and conditions; real comparative trials required. |
| Corrections and rework | Evidence-bound correction, override and rework candidates; explicit human decisions remain separate. |
| Observer effect | Pinned optional observer conditions with identical mandatory-control hashes; no disabling safety controls. |
| Offline policy evaluation | Support/reward/propensity validation and bounded descriptive estimate; no online learning or promotion. |

No daily loop is run to validate this tooling. Real prospective trials require actual source
binding, reviewed fixtures/rubrics, independently graded outcomes and enforced host budgets;
development readiness does not establish native activation or recovered live performance.

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
  without a ledger write. The receipt is published exclusively per cohort, and a reserved cohort left without a
  verdict (crash, or a probe failure right before evaluation) is resumed, its stored receipt adopted unchanged,
  instead of reserving another. Attempt k tests at `alphaBase * 2^-(k-1)`; the budget is per decision, not per policy
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
2. **Cycle** (`decision_cycle.py run`). The skill-fit cosign cycle is unchanged. After it, `run_advise` handles every decision with an `advise` entry except `workflow-fit` (owned by `pilot_cycle.py`). The gate is **prospective**. Records are the ones on one binding: `policySha256` (the registry state's once advise is earned, else the most recent record's), the entry's advise instrument hash and the running Laya revision. Group is `groupSha256` (falling back to the decision id); skill-fit uses the session hash and the label's `bestSkill`, with the contract's `advise-v1` policy hash (the one the Node router writes and reads). With a tuning baseline available and no open cohort, the first pass probes Laya (must return exactly `True`) and appends an `open` event (`openedAt`, rule `earliest-record-per-promotion-group-after-open`, and the **baseline frozen at that moment**: the tuning-split majority) and holds as `cohort_opened`; nothing recorded before that moment is ever a case. Later passes **enroll** without reading a label, outcome or Laya answer: the earliest record of each promotion-split group created after `openedAt` on that binding (skipping groups earlier cohorts used), in record-time order, until there are `ceil(minCohort / 0.8)` of them (the headroom covers up to 20% ambiguous labels) and, for a critical decision, `ceil(minCriticalCases / 0.8)` critical cases (the critical flag is pre-decision state). Until then the pass holds as `cohort_collecting`. The immutable `enrolled` event (case ids and group hashes) is then appended; there is no replacement afterwards. The cohort waits (`cohort_labelling`) until every enrolled case has a final label; ambiguous labels are excluded, and more than 20% of them consume the cohort as a hold (`ambiguous_share`). Immediately before the final evaluation the pass probes Laya again (a failure holds as `laya_unavailable` and consumes nothing), then evaluates the enrolled set with the open-frozen baseline exactly once. The receipt is published exclusively per cohort id and `consumed` is appended after it; a retry after a crash in between adopts the stored receipt unchanged (no re-evaluation, whatever labels arrived since) and appends the missing `consumed`. A binding change `abandon`s the open or enrolled cohort (its attempt and alpha stay spent) and opens a new one. The required classes are the tuning classes with at least 10% share. Laya's answers are the ones recorded at decision time. A pass promotes to `advise` with `{policySha256, instrumentSha256, layaRevision, cohortId}`; with `advise` in force the rolling demotion rule runs on the latest advise-arm treatment cases (`gate_demote`), and a critical decision demotes at once (`critical_miss`) on any critical case Laya did not get right among all labelled cases with a `shown` marker since advise began, not only the window. Pins, `off`, `cosign` and registry refusals are recorded holds. `--no-advise` skips the pass.
3. **Scoreboard** (`typed_decisions/scoreboard.py render`). One advise row per decision: mode, labelled n, last verdict, accuracy vs baseline, CP lower bound, coverage, critical cases and misses, attempts used and the next alpha.
