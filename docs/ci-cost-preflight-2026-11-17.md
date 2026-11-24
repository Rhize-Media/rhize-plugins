# CI preflight cost review — November 17, 2026

Local candidate on `codex/ci-cost-preflight`, based on main
`5b3118ad8c13580023ff7ea47633721f5f359fb7`. No publication or realized savings.
Dates below come from GitHub Actions API timestamps; local verification occurred
November 17 (America/New_York). This review owns rhize-plugins only.

## Decision

Run 16 existing release-input tests after Python dependencies and Node setup,
before installing the static Claude validator and running the full suite. Use
`--exitfirst` only for this preflight. Reuse existing routing, rendering and catalog
assertions instead of creating a second implementation of their contracts.

Every old validation step remains byte-for-byte equivalent after YAML parsing and
in its original order. Successful inputs still run full pytest, strict manifest
checks, config lint, doctor, generated-artifact checks, render idempotence and the
PR version/release contract. No result cache, historical success reuse, new
dependency, provider call, publisher edit or plugin version bump was introduced.
Canonical package versions remain owned by their existing release tasks.

PRs to main now always emit `validate`, including narrative-only changes. Main-push
exclusions remain unchanged. GitHub documents that path-skipped required workflows
can remain pending ([required-check troubleshooting](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks)).
This intentionally adds full validation cost for narrative-only PRs. At inspection,
main branch protection returned `Branch not protected` and the repository ruleset
list was empty; neither setting was changed. No required-check promotion is implied.

## Arm A: observed baseline

The latest 50 runs were inspected as a bounded sample, not a monthly census.
Existing safeguards already included a 15-minute validation timeout, pinned
Actions and dependencies, pip/npm download caches, superseded-run cancellation,
main-only pushes and a serialized non-cancelling publisher. The prior September
CI-hardening branch is already incorporated; the October 22 implementation report
covered other repositories and did not supply a missing rhize-plugins patch.

Three runs reported failure at the end of the full pytest step:

| Run | Candidate source head | Observed pytest seconds | Failure caught by preflight |
| --- | --- | ---: | --- |
| [44001296384](https://github.com/Rhize-Media/rhize-plugins/actions/runs/44001296384) | `3e956084747989ac3bcedfb25ed450d5e116191c` | 296.68 | Routing corpus drift; this run also failed catalog checks |
| [43917455707](https://github.com/Rhize-Media/rhize-plugins/actions/runs/43917455707) | `b1a82c5cfb99373bff0d07fd6d828a3bc96de07c` | 324.05 | Routing corpus drift |
| [42713762763](https://github.com/Rhize-Media/rhize-plugins/actions/runs/42713762763) | `36dc101169bee889058640c5bb7dad4833c539ed` | 328.78 | Stale generated README section |

These are logged pytest elapsed times from the latest attempt, not billed minutes,
whole-job savings, or a count of every rerun. Their sum is 949.51 seconds; do not
credit it as recovered usage. Run 44001296384 took 314 seconds from job start to
completion; run 43917455707 took 341 seconds. Setup/teardown and billing differ.

## Arm B: local evidence, not hosted savings

The exact preflight command was run against disposable Git archives of the three
candidate source heads above. These were source-head replays on local macOS/Python
3.14/Node 24, not reproductions of GitHub's PR merge tree, runner, or Python 3.12/
Node 22 toolchain. No prior result qualifies the candidate for skipped validation.

| Historical source tree | Local process seconds | Result |
| --- | ---: | --- |
| `6824e12a5d8b0086195ba9e6d817341305280842` | 2.75 | Expected failure: routing corpus; 1 failed, 3 passed |
| `3ea7aae4b79eca78fd8ba952a74867ade17824a5` | 3.57 | Expected failure: routing corpus; 1 failed, 3 passed |
| `68e40cdf872286ee08735cba7faeda251af785f1` | 3.39 | Expected failure: generated README; 1 failed, 12 passed |

The current base's preflight passed 16 tests in 2.70 seconds. Candidate preflight
plus workflow contracts passed 21 tests in 10.38 seconds while other work was
active. These are separate observations, not a controlled speed comparison.

Expected gross benefit is avoiding roughly a five-minute full test step on a
matching bad-input run, less preflight/setup cost. Green runs repeat the small
preflight subset. Additional narrative PR runs can outweigh those savings. Net
savings are **unmeasured**, and realized savings are **zero** until publication and
observation. The handoff's November org figures (rhize-plugins 360 Linux minutes;
procedural-memory 95; infra 68; routines 41) were not re-audited as billing here.
Organization usage is billed from a separate pool and cannot replenish a personal account's allowance.

For future comparison, label before/after runs Arm A/Arm B; retain candidate and
tree SHA, base, workflow/dependency hashes, toolchain, event, every attempt, job and
step durations, failure class and docs-only status. Reconcile to account billing;
include green-run preflight overhead and newly admitted docs PRs. Do not trigger
paid runs merely to measure this patch.

## Alternatives and boundaries

- Moving `Validate version bumps` earlier is not a cheap preflight: its command
  reruns the Dev Flow suite and repository contracts. Keep it intact.
- No duplicate PR/main suppression: equivalent candidate tree, base, workflow,
  configuration/toolchain and immutable dependencies were not established.
- No full-suite fail-fast flag: passing-run coverage and normal failure diagnostics
  remain unchanged. Early input rejection deliberately reports the first defect.
- No broad new path exclusions, dynamic affected-test router, cache of test results,
  package changes, Laya authority change, scheduled release, or client rollout.
- Related read-only review confirmed procedural-memory already has a ten-minute
  timeout, pip cache, concurrency cancellation and narrative exclusions.
- claude-routines `workflow-source-bindings.yml` currently runs on every push/PR,
  without concurrency or a timeout, using version-tag Actions. Its owner should
  consider a bounded timeout, PR/ref concurrency for pure validation, immutable
  action pins and elimination of duplicate feature push/PR work. Any path routing
  must include all source-binding inputs and preserve a stable PR result. No edits
  were made there; source-binding validation remains mandatory.

## Changed files

- `.github/workflows/validate.yml`: preflight and PR trigger.
- `tests/config-lint/test_ci_contract.py`: coverage, ordering and check-presence guards.
- `README.md`: current CI behavior and added docs-PR cost.
- `STATE.md`: verified facts, interruption and limits.
- `docs/ci-cost-preflight-2026-11-17.md`: this evidence and handoff record.

## Local verification and publication

- Passed: final focused workflow, routing, rendering and complete catalog/setup test
  selection: **35 tests in 5.85 seconds**, with the verified Python 3.14 and real Node
  binary first on PATH. The initial broader 30-test selection had one nested-Python
  smoke failure; the unchanged test passes with this explicit environment.
- Passed: actionlint 1.7.12 for `validate.yml` (official release checksum verified);
  both new workflow contracts reject the old workflow; structural YAML comparison
  preserves every existing validation step and order, permissions, concurrency,
  main-push trigger and the unchanged tag publisher.
- Passed: all 14 strict marketplace/plugin manifest validations with the lockfile's
  Claude 2.1.278; configuration lint; map and setup-artifact freshness; two render
  runs reported no changes. Doctor exited zero, with existing Vercel deployment
  correlation reported degraded, not a fully healthy integration claim.
- Passed: three historical preflight replays produced the expected failures.
- Independent code/report review: no blocking issue after placing the preflight
  after Node setup. The render fixture is hermetic; savings remain unproven.
- Historical incomplete run: the initial full suite was interrupted near 75% after
  at least three failure markers. Its terminal summary and failure identities were
  lost; the earlier cause remains unknown. This history is not a passing result.
- Passed on the user's follow-up request: the complete suite at
  `d21dd61248731a91d3564835081d3fe53553e388` finished with **4,930 passed,
  9 skipped and 130 subtests passed in 1,006.14 seconds**, exit zero. JUnit reports
  5,069 total tests including skips/subtests, zero failures and zero errors. The earlier
  markers did not reproduce; no change-caused failure or code fix was identified.
  Durable stdout, JUnit, process/result records and input hashes are saved in the
  local analysis directory. Only this verification report and STATE change afterward.
- The nine skips are unchanged conditional coverage: two absent Codex manifests,
  three optional jsonschema checks (canonical stdlib validators still run), one
  opt-in Docker isolation canary, one pinned Muse-binary canary, and two real-provider
  compiler cases. No test or assertion was disabled for this change.
- This is native macOS evidence, with Python 3.14, Node 24.22.3, pytest 9.1.1,
  PyYAML 6.0.3 and installed cryptography 46.0.6. CI uses Linux, Python 3.12,
  Node 22 and cryptography 50.0.2. Dependencies were not changed; exact hosted
  validation remains separate and will run after a later authorized push.
- Passed: `python3 scripts/bump_version.py --check --since
  5b3118ad8c13580023ff7ea47633721f5f359fb7` with native process access: **938 Dev
  Flow tests in 382.68 seconds**, seven impact-map contracts, map/setup freshness
  and configuration lint. Exit zero, no plugin changes requiring a version bump.
  This separate successful gate does not convert the interrupted whole-repository
  run into a pass. No hosted workflow was triggered.

The user authorized local main integration after full-suite validation and explicitly
reserved pushing for the next deployment. Work is committed on the feature branch,
then local main is fast-forwarded after ancestry and unrelated-file checks. This
includes the already-published base commits that the primary checkout was behind.
No push, PR, remote merge, tag, hosted run, repository-setting change, deployment,
installed plugin update, budget change, external message or schedule activation
is part of this work. Unrelated untracked files are preserved.

Before a future push, reconcile with then-current remote main and check exact-ref
private context freshness; hosted validation remains required. Roll back the CI
behavior by reverting `d21dd61248731a91d3564835081d3fe53553e388`; the follow-up
verification commit changes documentation only. No plugin version or runtime data
migration is involved.
