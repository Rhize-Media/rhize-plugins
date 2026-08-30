# Procedural Engineering Evidence-Gates Execution Plan

| Field | Value |
|---|---|
| Status | Proposed for execution review |
| Created | 2026-08-30 |
| Program owner | Rhize Tools |
| Jira umbrella | RT-130 |
| Context/search tracker | RT-128 |
| Planning and final review tier | Sol |
| Recommended implementation tier | Terra for cross-cutting work; Luna for bounded fixtures and documentation |

## 1. Objective

Turn the existing procedural-memory, execution-graph, Functionize, mgrep, and compiled-context work into decision-grade evidence. The program succeeds when Rhize can decide, without overstating incomplete data, which capabilities to keep, revise, package, or retire.

This is a focused execution companion to:

- `.claude/plans/procedural-engineering-verified-memory-graphs.md`;
- `.claude/plans/mgrep-context-compiler-dogfood.md`;
- `.claude/plans/benchmark-status-module.md`.

Those documents remain the design history. This plan governs the order of the remaining work and resolves the current mismatch between shipped capability and comparable live evidence.

## 2. Current evidence baseline

Freeze this snapshot before implementation. Re-verify every mutable fact at the start of its phase rather than copying it forward as current truth.

| Lane | Current state | Decision status |
|---|---|---|
| Daily Completed Summary / RT-134 | Four Arm-A rows exist; three are natural. Natural rows use post-hoc phase estimates and omit the input fingerprint and baseline SHA required by the experiment contract. | Natural activity is verified; strict comparable cohort is 0/3. |
| AI Stack Version Drift / RT-136 | One Arm-A row exists. Step boundaries are estimated and date-only liveness is `indeterminate_same_day`. Canonical cadence and observed Desktop cadence disagree. | Strict comparable cohort is 0/3. |
| Weekly Skill Audit / RT-137 | Desktop/Registry A duplicate is paused; Registry B is canonical. No post-reenable natural cohort exists. The routine currently risks resolving a stale checkout copy of `benchmark_status.py`. | Strict comparable cohort is 0/3. |
| Functionize / RT-138 and RT-140 | Mining, redaction, ranking, safe export, and review ledger are shipped. Two real candidates were rejected. Generation and promotion remain dormant. | Correctly waiting for an accepted candidate contract. |
| Graph G1 / RT-143 | The historical runner-1.3 set has four eligible attempts, two clean results, one quality rejection, and one infrastructure failure. It lacks a matched Arm-B cohort, full cost coverage, the 95% named-wall floor, and blinded review. | Hold; not a promotion cohort. |
| Matched B/G1 runner 1.5 / RT-143 | The self-cleaning protocol is released in the isolated cohort checkout. The planned five pairs have no completed rows. | Awaiting new digest-bound paid/effect authorization. |
| Compiled context / RT-128 | Native context packs passed the offline gate and are packaged as advanced opt-in. One automatic shadow run is armed for the next eligible `rhize-plugins` task; the current receipt corpus for this follow-on live gate is empty. | Await one real receipt, then stop for review. |
| mgrep / RT-128 | Installed but disabled, unauthenticated, unindexed, and not network-approved. Managed-provider terms remain unacceptable without clarification and explicit approval. | Do not run or upload source. |
| Scheduler definitions | Read-only sync check reports one drifted definition: `claude-code-desktop/daily-learn-harvest`. | Reconcile before trusting pointer/runtime smoke. |

Historical receipts remain evidence, but rows that fail the current contract must be labeled `non_comparable`; they must never be silently upgraded, averaged into the strict cohort, or deleted.

## 3. Binding evidence and safety rules

1. **Real evidence only.** Never fabricate or backfill a row, receipt, prompt, cost, source body, credential, effect, or run result.
2. **Separate evidence lanes.** Report performance, output parity, correctness, and operability independently. Do not collapse them into one score.
3. **Separate variants.** A, B, G, G1, G2, and G3 remain distinct. Graph receipts are operational evidence and never count toward routine A/B performance or liveness.
4. **Comparable means contract-complete.** A row is comparable only when its run-bound receipt contains exact timestamps, scope, input fingerprint, baseline SHA, expected/completed steps, outputs/effects, retries, and append assertion.
5. **Natural means natural.** RT-134, RT-136, and RT-137 require scheduler-originated runs. Manual acceleration may test code but cannot satisfy their cohort gates.
6. **One row per run.** Every representative natural run produces exactly one canonical row or a loud correctness incident. Duplicate, missing, or amended rows retain an audit trail.
7. **No same-day inference.** Date-only evidence cannot prove ordering. Until timestamped binding exists, use `indeterminate_same_day`, not `ok` or `row_missing`.
8. **Privacy first.** No managed search upload, account creation, store creation, authentication, or background indexing without a reviewed exact manifest and literal network/data authorization.
9. **Effects are temporary in experiments.** G1 experimental Sanity and HighLevel drafts must be removed after each workflow and their absence verified. Cleanup failure locks the cohort before another workflow begins.
10. **Authorization is digest-bound.** Paid calls and external mutations require a fresh literal authorization naming the runner digest, graph digest, input fingerprint, call cap, effect classes, cleanup actions, and retained benchmark mutations.
11. **Change one variable.** G2 starts only after a stable G1 baseline; G3 starts only after G2; Functionize generation starts only after an accepted candidate contract.
12. **Jira follows evidence.** Update an issue only when new evidence, an incident, a gate decision, or a verified implementation change lands.

## 4. Dependency order

```text
P0 freeze truth
  -> P1 repair instrumentation
  -> P2 reconcile scheduler/runtime
  -> P3 observe natural cohorts
       -> P7 evidence review and packaging decisions

P0 -> P4 one-shot compiled-context receipt -> P7
P4 review -> P5 managed-mgrep decision gate -> P7
P0 -> P6 authorize and run matched B/G1 cohort -> P7

Accepted Functionize candidate -> generation -> promotion -> P7
Stable G1 -> optional G2 -> optional G3 -> P7
```

P1 and the read-only parts of P2 may be developed concurrently in isolated files or worktrees. P4 may land automatically while P1-P3 are underway. P5 privacy research and P6 authorization-manifest preparation are also read-only and independent. Mutations remain sequential at each effect boundary.

## 5. Phase P0 — Freeze authoritative truth

### Goal

Prevent another evidence cycle from running against an unpinned implementation, ambiguous scheduler, or stale baseline.

### Tasks

1. Re-read the authoritative Desktop and Registry B scheduler records for RT-134, RT-136, and RT-137. Capture identifiers, enabled state, runtime, cadence, last run, and next run.
2. Record the active Git SHA and version for every routine definition, `benchmark_status.py`, graph runner, graph artifact, model map, and context-experiment runner.
3. Re-run the released watchdog and read-only scheduler sync check. Preserve `indeterminate_same_day` and the exact drift report.
4. Reconcile Jira statuses with evidence counts without moving any issue to Done.
5. Create a small machine-readable baseline manifest for the implementation phase. It stores identifiers, hashes, schema versions, and evidence locations—not source text, prompts, credentials, or DSNs.

### Verification and exit gate

- Every mutable component has an exact SHA/digest and evidence location.
- Scheduler state is read from the authoritative registries, not inferred from note dates.
- Old rows are classified as comparable or non-comparable under one explicit schema version.
- The baseline manifest validates and contains no sensitive content.

### Jira

Add one RT-130 checkpoint comment only if the verified snapshot differs materially from the current issue state. Do not duplicate the full plan in Jira.

## 6. Phase P1 — Repair Daily and AI measurement at the source

### Goal

Make the next natural RT-134 and RT-136 executions self-measuring, run-bound, and capable of proving both work and measurement completeness.

### P1.1 Shared receipt contract

Implement or extend a structured receipt with these required fields:

- `schemaVersion`, `runId`, `routineId`, `variant`, and scheduler execution identifier;
- UTC `startedAt`, `endedAt`, and monotonic duration for the whole run;
- exact start/end timestamps and duration for every expected step;
- `baselineSha`, routine-definition digest, artifact/function digest, and environment/surface;
- normalized `inputFingerprint` plus a non-sensitive description of the input scope;
- ordered `expectedSteps` and `completedSteps` with per-step status;
- output artifact identifiers, effect identifiers, failure classes, retry counts, and approval cycles;
- correctness/operability flags, including partial source failure and human correction;
- canonical benchmark-row identifier and the routine's own post-append read assertion.

The structured receipt is authoritative. The Markdown row is a human-readable projection. If projection or append assertion fails, the run is an incident—not a successful run with missing metrics.

Input fingerprints must hash a canonical, redacted manifest of sources and parameters. They must not copy source bodies or secrets into the receipt.

### P1.2 Daily Completed Summary / RT-134

1. Instrument every expected deterministic and model-assisted step at its real boundary; remove post-hoc timing estimates from new rows.
2. Capture completeness for Git/GitHub, Jira, Slack, session logs, and produced summary artifacts separately. Pagination or truncation is explicit.
3. Bind the benchmark append to the same run ID and assert a one-row delta plus identifier match before success.
4. Add deterministic fixtures for complete, partial-source, retry, duplicate-append, append-failure, and interrupted-run cases.
5. Retain the three existing natural rows as `non_comparable_legacy`; start a new 0/3 strict cohort after release.

### P1.3 AI Stack Version Drift / RT-136

1. Instrument inventory, provider fetch, normalization, semver classification, report write, and benchmark append independently.
2. Preserve provider/source failures per step. Never emit a fabricated-clean report when one provider failed.
3. Record requested and actually observed provider scope so unequal fetch sets cannot compare.
4. Bind report and row mutation to the run ID, then assert both mutations.
5. Add deterministic fixtures for partial provider failure, timeout/retry, no-version-change, true drift, append failure, and interrupted run.
6. Retain the existing row as `non_comparable_legacy`; start a new 0/3 strict cohort after release.

### Verification and exit gate

- Schema and projection validators reject every missing required field.
- Fixed-clock tests verify exact phase boundaries and duration reconciliation.
- The sum of named step time is reported against wall time; unexplained time remains visible.
- Duplicate or missing rows fail loudly and do not create a second canonical record.
- Both routines pass local deterministic tests and a non-effectful receipt smoke before their definitions are released.
- Released definitions and receipts are pinned to exact SHAs.

### Rollback

If instrumentation breaks the routine, restore the last verified definition and record the attempted run as an instrumentation incident. Do not hand-edit a passing row.

## 7. Phase P2 — Reconcile scheduler drift and Weekly Audit runtime

### Goal

Enter the next natural observation window with one scheduler per routine and a released watchdog resolved by construction.

### P2.1 `daily-learn-harvest` drift

1. Run `sync-check.sh` without `--pull` and inspect the exact canonical/live diff.
2. Determine whether the definition or the live pointer is newer and intentional using Git history, scheduler metadata, and the last successful run.
3. Select the source explicitly. Stage one reversible pointer repair; do not perform a blind pull or bulk sync.
4. Re-run the read-only sync check. Only after zero drift, run deterministic pointer-resolution smoke checks.

This drift is not itself a benchmark result, but unresolved scheduler drift invalidates claims that the installed runtime matches the tested source.

### P2.2 Weekly Skill Audit / RT-137

1. Keep the Desktop/Registry A duplicate paused and Registry B canonical.
2. Eliminate checkout-dependent watchdog resolution. Pin the scheduled routine to the released plugin/artifact path or an immutable released SHA, not whichever development checkout happens to be active.
3. Verify that the resolved watchdog preserves the trust taxonomy and `indeterminate_same_day` behavior.
4. Confirm the audit's expected evidence mutations: usage report, refinement-queue handling, dashboard refresh, watchdog snapshot, and benchmark row/assertion.
5. Read back the canonical schedule and calendar-check the next natural execution. As of this plan, the expected first observation is Monday, 2026-08-31 at 6:30 p.m. ET; the registry read is authoritative.

### P2.3 AI cadence ambiguity

1. Compare the canonical definition, live scheduler record, and Jira description.
2. Choose one cadence for the benchmark window based on the intended routine—not on which copy happened to run.
3. Update only the incorrect surface and read back next-run state.
4. Record the cadence decision in RT-136 so missing Thursday or duplicate Monday executions are interpreted correctly.

### Verification and exit gate

- Read-only sync check is clean.
- Pointer runtime smoke resolves the released content without transmitting routine bodies externally.
- Exactly one enabled scheduler exists per routine.
- Weekly Audit resolves the corrected watchdog before its natural run.
- AI Stack has one explicit cadence and one computed next run.

### Rollback

Every scheduler mutation must preserve the prior record and support immediate restoration. If read-back differs, restore and stop rather than widening the rollout.

## 8. Phase P3 — Observe strict natural Arm-A cohorts

### Goal

Collect three representative, contract-complete natural runs for each of RT-134, RT-136, and RT-137 without manual acceleration.

### Per-run procedure

For each natural execution:

1. Read scheduler telemetry and bind it to exactly one receipt and benchmark row.
2. Verify expected/completed steps, exact timing, outputs, correctness, operability, input fingerprint, baseline SHA, retries, effects, and append assertion.
3. Reconcile report/note mutations with run timestamps; never use same-day file dates as ordering proof.
4. Run the corrected watchdog and preserve its trust classification.
5. Diagnose any row-missing, duplicate-row, silent no-op, or fabricated-clean signal before classifying it.
6. Update the matching Jira issue only when the new evidence lands.

### Cohort rules

- Daily, AI, and Weekly each need three new strict rows after the relevant instrumentation/runtime repair.
- Legacy rows remain visible but do not reduce the 3-row requirement.
- A partial provider/source failure can be representative if it is honestly recorded and the scope remains useful; it is not comparable to a full-scope row without explicit stratification.
- An implementation comparison or closure waits until the lane has three comparable natural rows.

### Automation behavior

Keep `verify-daily-summary-arm-a` active while any of the three cohorts is below its gate. It should remain identifier-only, avoid manual acceleration, and update Jira only on new evidence. Delete it only after all three issues meet the evidence gate and their Jira state is reconciled.

### Exit gate

Each lane is either:

- `3/3 comparable` with reconciled raw receipts and no unresolved incident; or
- stopped with a documented correctness/operability reason that makes further collection wasteful or unsafe.

## 9. Phase P4 — Review the one-shot compiled-context live receipt

### Goal

Let the already-armed native compiled-context experiment claim the next eligible `rhize-plugins` task automatically, then review it before any rearm.

### Tasks

1. Before claim, verify provider health, armed-run count, repository allowlist, snapshot, shadow mode, runner SHA, and receipt schema.
2. Do not manufacture an eligible task. The normal next task must satisfy the selector.
3. Permit exactly one claim. Arm B is the compiled pack; Arm A is read-only shadow or has an explicit skip reason.
4. After finalization, verify snapshot validity, pack warnings, selected files, critical dependencies, follow-up reads, task outcome, context tokens, latency, tool calls, and any fallback.
5. Reconcile the raw receipt to the aggregate report and update RT-128 only at this first-receipt milestone.
6. Leave the experiment disarmed after its run until a Sol-level review chooses `rearm`, `narrow`, `retain advanced opt-in`, or `stop`.

If the automatic claim occurs before P1-P3 finish, complete this receipt review immediately; do not delay or reclassify it to preserve the document order.

### Exit gate

- One real, contract-valid receipt exists and names both executed and skipped arms honestly.
- No stale pack, hidden critical miss, or correctness regression occurred.
- A first-run decision is recorded in RT-128.

## 10. Phase P5 — Keep mgrep behind a managed-provider gate

### Goal

Decide whether new vendor facts justify a bounded managed mgrep pilot. This phase is a gate, not an instruction to upload source.

### Read-only gate work

1. Obtain current written clarification of free/paid data retention, training use, deletion, and purge guarantees.
2. Recompute cost against the exact approved repository manifest and current pricing.
3. Review the exact allowlist/denylist, hidden-file omissions, symlink handling, size limits, proposed store name, one-shot snapshot, and purge operation.
4. Define a one-run comparison against the current CodeGraph/`rg` route with relevant-file correctness as the non-inferiority gate.
5. Prepare a literal authorization manifest covering authentication, store creation, exact file upload, query cap, cost cap, store deletion, credential removal, and retained redacted receipts.

### Go/no-go gate

Proceed only if:

- data-use terms are unambiguous and acceptable;
- the exact repository manifest is approved;
- cost and query caps are approved;
- store purge is documented and testable;
- a new literal network/data authorization is granted.

If approved, use one fixed snapshot, no watcher, one Arm-B-live/Arm-A-shadow task, deterministic verification of every semantic candidate, first-run review, then purge unless continuation is explicitly approved.

If any gate fails, leave mgrep disabled and record `reject` or `revisit_on_changed_terms`. A simulated upload is not evidence.

## 11. Phase P6 — Authorize and execute the matched B/G1 cohort

### Goal

Produce five matched B/G1 pairs under one immutable runner/protocol, with complete quality, cost, timing, effect, and cleanup evidence.

### P6.1 Pre-authorization manifest

Re-derive and present, immediately before authorization:

- runner digest (currently `cceb53086c40264a8a5b55a770e337034352a883c25af0804871d7ecf1d66621` in the isolated runner-1.5 release);
- graph digest `ec7f403c737f4d42202a1f60c2ee3cb4db7549ef2796516e49b57c89ed1f9a65`;
- input fingerprint `8c5163...`, expanded to its full current value from the runner manifest;
- exact B/G1 order and five-pair plan;
- provider/model/judge pins and freshness timestamps;
- maximum paid calls (currently planned as 60 across 10 workflows);
- transient effects (currently one Sanity draft and three HighLevel drafts per workflow);
- delete and absence-verification operations after every workflow;
- retained mutations (currently 10 cohort-local benchmark rows plus failure/incidence evidence);
- total cost cap and stop conditions.

Any changed digest, model pin, input fingerprint, call cap, effect class, or retention rule invalidates the manifest and requires new literal authorization. Prior runner-1.3 authorizations do not cover runner 1.5.

### P6.2 Execution protocol

1. Refresh provider/model availability if the snapshot is older than 24 hours. If pins change, recompute fingerprints and return to authorization.
2. Execute the predeclared B/G1 sequence; do not reorder based on interim quality.
3. After each workflow, append its immutable row, delete every experimental Sanity/HighLevel output, and verify absence by exact identifier.
4. If any cleanup or absence check fails, lock the cohort and diagnose before another paid call.
5. Preserve transport, quality, and infrastructure failures as non-comparable attempts. Do not silently replay them or average them into clean results.
6. Do not add replacement runs beyond the authorized cap. A replacement needs a new manifest and authorization.
7. Run blinded output adjudication after identifiers are masked; preserve judge disagreement.

### P6.3 Cohort acceptance

The cohort is decision-grade only when:

- five planned B/G1 pairs reconcile to raw receipts or an explicitly authorized stopping boundary;
- at least 95% of wall time is attributed to named phases in every comparable row;
- token and monetary cost are complete on the same basis;
- correctness, schema validity, gate/revise behavior, and human correction are reported separately;
- all temporary Sanity and HighLevel resources have delete receipts and absence verification;
- zero unauthorized or persistent production/customer effects exist;
- blinded review and aggregate calculations are reproducible.

Update RT-143 after authorization, on any incident/lock, and at the completed decision gate—not after every uneventful workflow.

## 12. Phase P7 — Evidence review, deferred experiments, and packaging

### Goal

Convert valid cohorts into explicit continue/change/promote/stop decisions without allowing later ideas to contaminate the baseline.

### Review order

1. Review RT-134, RT-136, and RT-137 independently after each reaches its natural cohort gate.
2. Review the one-shot compiled-context receipt independently from any retrieval experiment.
3. Review matched B/G1 results independently across performance, output, correctness, and operability.
4. Hold the RT-130 evidence-review story only after the source cohorts reconcile.
5. Update the package/release story only for capabilities that cleared their own gate.

### Deferred work gates

- **G2 model routing:** start only if the matched G1 cohort is stable and the review identifies a model-routing question worth testing. Change only the model map.
- **G3 structural trim:** start only after G2 concludes. Change only graph structure.
- **Functionize generation / RT-138:** keep dormant until a candidate has a reviewed, accepted contract with measurable non-obvious value. Generate only into an isolated, unregistered proposal directory.
- **Functionize promotion / RT-140:** start only after generated code passes behavior-difference tests, secret/path checks, human diff review, and the existing promoter. Registry write and Secure-Enclave approval remain separate.
- **Plugin packaging / RT-145:** package only the smallest independently proven surfaces. Do not package mgrep merely because the adapter exists, and do not package Functionize generation before one real accepted proposal is promoted and observed.

### Decision record

For every capability, record exactly one disposition:

- `bundle`;
- `retain_advanced_opt_in`;
- `revise_and_rerun` with one changed variable;
- `reject_or_retire` with rollback/purge status.

Negative or null results are successful program outcomes when the evidence is valid.

## 13. Jira execution map

| Work | Jira surface | Status rule |
|---|---|---|
| Daily instrumentation and natural cohort | RT-134 | In Progress until 3/3 strict rows or documented stop. |
| AI instrumentation, cadence, and natural cohort | RT-136 | In Progress until 3/3 strict rows or documented stop. |
| Weekly runtime pin and natural cohort | RT-137 | In Progress until 3/3 strict rows or documented stop. |
| Functionize generation | RT-138 | Backlog while no candidate contract is accepted. |
| Functionize promotion | RT-140 | Backlog until generation gate passes. |
| Matched B/G1 cohort | RT-143 | In Progress; blocked only at a real authorization, cleanup, or correctness gate. |
| Packaging | RT-145 | Backlog until an evidence review approves a capability. |
| Context and mgrep | RT-128 | In Progress through the armed compiled-context receipt review; mgrep remains separately gated. |
| Program evidence review | RT-130 child story for evidence review | Start only after source cohorts are decision-grade. Verify the exact child key before mutation. |

Every Jira evidence comment should contain only:

- run/cohort identifiers and variant;
- schema and implementation digests;
- comparable/non-comparable counts;
- correctness/operability incidents;
- evidence artifact links or paths;
- the explicit decision and next gate.

Do not paste prompts, source bodies, credentials, DSNs, or customer content into Jira.

## 14. Immediate execution sequence

1. **Before the next natural windows:** complete P0, repair RT-134/RT-136 instrumentation, reconcile `daily-learn-harvest`, pin Weekly Audit to the released watchdog, and resolve AI cadence.
2. **At the Monday, 2026-08-31 Weekly window:** observe Registry B naturally, verify exact mutations and one run-bound row, diagnose incidents, and update RT-137 only if evidence lands.
3. **On subsequent natural runs:** collect new strict Daily and AI rows until each reaches 3/3; continue Weekly until it reaches 3/3.
4. **Whenever the next eligible context task appears:** allow the single armed compiled-context claim, review its receipt, and keep it disarmed afterward.
5. **In parallel, read-only:** prepare the mgrep legal/privacy/cost gate and the runner-1.5 authorization manifest. Neither preparation authorizes execution.
6. **After literal G1 authorization:** execute the matched cohort sequentially with cleanup and absence verification after each workflow.
7. **After cohorts reconcile:** conduct the evidence review; only then unlock G2, G3, Functionize generation/promotion, or packaging as justified.

## 15. Program completion criteria

This execution plan is complete when:

- RT-134, RT-136, and RT-137 each have three strict natural rows or an evidence-backed stop decision;
- the compiled-context one-shot has a reconciled first-run decision;
- mgrep has either passed every managed-provider gate and completed its bounded real pilot, or has a documented rejection/revisit condition with no uploaded data left behind;
- the matched B/G1 cohort has a reproducible decision and zero surviving experimental Sanity/HighLevel outputs;
- G2, G3, and Functionize work remain gated rather than being started for data volume alone;
- Jira statuses and comments reconcile to the raw evidence;
- only capabilities supported by independent decision-grade evidence enter the Rhize plugin suite;
- every rejected hypothesis and failed attempt remains classified and auditable.
