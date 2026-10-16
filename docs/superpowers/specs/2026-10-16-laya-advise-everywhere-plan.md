# Laya decision layer: advise everywhere (plan rev 3, 2026-10-16)

**Branch:** `claude/laya-advise-v2` (worktree `~/dev-local/RHIZE/.worktrees/laya-advise-v2`).
**Builds on:** [the 2026-10-11 earned-authority plan](2026-10-11-laya-earned-authority-plan.md), which is
implemented on `main`. This plan extends its registry; it does not replace it.
**Recovers:** the 2026-10-06 advise rollout (`.claude/plans/laya-advise-mode-rollout.md`, local). Its S1/S2
commits are on the local branch `claude/laya-advise`; its uncommitted S3 was lost when macOS purged the
`/private/tmp` worktree (rule added to global CLAUDE.md and Codex AGENTS.md on 2026-10-16).

## 1. Authority (Jim, 2026-10-16)

> We should retire the 200-label floor and advise once it beats the baseline. Advice surfaces should be:
> workflow, procedure, skill, dev flow, routing, GSD … S4 is fine. For critical decisions, Laya should
> advise with a baseline gate. Go with your recommendations to make sure that all of our intended
> optimizations land on main for a successful new release.

Earlier standing decisions (2026-10-06): authority is *advise + baseline gate*; Laya input is redacted
request text plus file names, loopback only; routine checks may be relaxed from a deterministic allowlist.
Deploy, publish, credentials, approvals, security review, required CI and the production-merge review are
never relaxable.

## 2. Overrides of the 2026-10-11 invariants

| 2026-10-11 rule | Now |
|---|---|
| I5: the v2 workflow pilot and its 200-label floor are unchanged | Floor retired. Workflow fit moves to the v3 envelope (one `choice` question over redacted text) and earns `advise` through the baseline gate. Research floor default 30 (bounds 20..10000). |
| I6: critical decisions are shadow-only by schema | Critical decisions may reach `advise` (never `cosign`) through the baseline gate with **zero critical misses**. |
| I8: only `cosign-v1` is auto-deployable | A second deployable policy, `advise-v1`, may be set automatically by the baseline gate. |
| §4.4: decision records are skill-shaped only | A second, generic record schema `rhize-typed-choice-record-v1` serves every non-skill decision. |

Unchanged: I2 (failure emits the incumbent byte-for-byte), I3 (no prompt text persisted by hooks; text
reaches only literal-loopback Laya after the identity probe), the single locked registry mutation path, a
manual pin suspends automation, corrupt state reads as `shadow`, plugins stay islands, skill fit keeps its
cosign estimand and gate.

## 3. Modes and gates

- **Modes:** `off`, `shadow`, `advise`, `cosign`.
  - `advise`: Laya's pick is shown to the agent as a labelled, uncalibrated recommendation. The incumbent
    path and every gate stay authoritative; the agent may override.
  - `cosign`: unchanged (skill fit only, suppresses a router suggestion Laya disagrees with).
- **Holdback:** each decision keeps a deterministic holdback (`sha256('holdback:'+decision+':'+key)`, 10%
  default, 15% for critical) that never sees advice; assigned and recorded before any advice is emitted.
- **`gateKind` per decision:**
  - `cosign-disagreement` — skill fit's existing Clopper–Pearson estimand (unchanged).
  - `majority-baseline` (policy `advise-v1`) — final rule after the Codex review (§11):
    1. **Population.** Labelled choice records of the decision, grouped by session before a stable
       `sha256('split:'+group)` split: tuning 2/3, promotion 1/3. Candidate search sees tuning only. The
       **group is the statistical unit**: a cohort holds at most one case per group, and the ledger refuses a
       cohort whose groups (stored as sha256) intersect any earlier cohort of the decision.
    2. **Baseline.** The majority class of the tuning split, frozen into the cohort at reserve time and
       evaluated as a constant predictor on the same promotion cases.
    3. **Outcomes.** `none` is an ordinary candidate. An abstention, timeout, unavailable or invalid answer
       counts as **Laya wrong**. Answer coverage must be ≥ 90%.
    4. **Test.** Paired exact sign test on discordant cases (Laya right/baseline wrong = b, Laya
       wrong/baseline right = c): promote when the one-sided Clopper–Pearson lower bound of b/(b+c) > 0.5
       at α_k, **and** Laya's balanced accuracy beats the baseline's, **and** every class with ≥ 10% tuning
       share (zero-count classes included) has ≥ 3 cohort cases with recall ≥ 0.5.
    5. **Cohorts and retries.** A promotion cohort (≥ 30 cases from distinct groups) is consumed by exactly
       one attempt. *Live decisions are prospective:* with a tuning baseline and a passing availability probe,
       the cycle appends an `open` event (policy, instrument, Laya revision, `openedAt`, rule
       `earliest-record-per-promotion-group-after-open`) to the cohort ledger before any eligible record
       exists and holds as `cohort_opened`. The cases are the earliest record of each promotion-split group
       created after `openedAt` on that binding (outcome-independent; groups of earlier cohorts skipped),
       evaluated once when ≥ `minCohort` such groups are labelled (and, for critical, ≥ `minCriticalCases`
       critical cases), then `consumed` with the case ids and group hashes. A binding change `abandon`s the
       open cohort without refunding its attempt. *Replay* (`workflow-fit` corpus) keeps reserve-before-replay,
       one case per group. Attempt k uses α_k = 0.10·2^−(k−1) (open and reserve both count); the budget is
       per decision (a new policy or Laya revision does not reset it). The probe is mandatory: it must return
       exactly `True`; a raise or any other value is "unavailable" and holds with no ledger write.
    6. **Critical.** A critical decision also needs ≥ 10 `critical_if_wrong` cases in the cohort and zero
       critical misses. A critical miss is any `critical_if_wrong` case Laya did not get right, an
       abstention or unavailable answer included. `critical_if_wrong` is computed by trusted caller code from
       hard-gate state and frozen in the record before any advice.
    7. **Demotion.** Any critical miss among *all* labelled cases that were shown (a `shown` marker exists)
       since the last demotion, not only the latest window, demotes to `shadow` (in the label-import job, and
       again in the cycle). Otherwise, each time ≥ 10 fresh advise-arm labels accrue, the latest 30 are
       scored; two consecutive evaluations where Laya's accuracy is below the baseline's on the same cases
       demote. The pilot's demotion check probes Laya before re-querying it.
    8. **Bindings.** Every earned mode (`advise`, `cosign`) binds `policySha256`, `instrumentSha256` and
       `layaRevision`; any mismatch reads as `shadow`. Pins and bindings are revalidated inside the lock. An
       earned advise is judged on the registry state's own `policySha256`, so a stray record of another policy
       cannot flap it.
  - **Gates are per target mode.** An entry lists `modes: {advise: {policy: advise-v1, gate: majority-baseline},
    cosign: {policy: cosign-v1, gate: cosign-disagreement}}`. Passing one gate never authorizes the other mode;
    skill fit can hold `advise` (an added line) and later earn `cosign` (suppression) separately.

## 4. Registry entries

| Decision | Owner | Tier | Reachable | Gate | Candidates |
|---|---|---|---|---|---|
| `skill-fit` | Context Manager `skill-router.js` | advisory | off, shadow, advise, cosign | both | top-5 shortlist + none |
| `workflow-fit` | Context Manager `workflow_selection.py` | workflow | shadow, advise | majority-baseline | content, general, none |
| `procedure-pick` | Context Manager `workflow_selection.py recommend-procedure` | advisory | off, shadow, advise | majority-baseline | top-5 recall hits + none |
| `devflow-next-action` | Dev Flow `typed_checkpoint.py` | critical | off, shadow, advise | majority-baseline | continue, investigate, verify, escalate |
| `browser-qa-selection` | Dev Flow `typed_selection.py` | advisory | off, shadow, advise | majority-baseline | approved surfaces |
| `model-routing` | Ops `typed_routing.py` | advisory | off, shadow, advise | majority-baseline | authorized models/workers |
| `gsd-directive` | Project Launcher `typed_decision.py supervise` | critical | off, shadow, advise | majority-baseline | continue, investigate, verify, escalate, finish_candidate |
| `check-relaxation` | Dev Flow `check` | critical | off, shadow, advise | majority-baseline | full, relaxed |

Every new entry ships `defaultMode: shadow`; only the gate (or an operator pin) moves it.

## 5. Shared island module `typed_advice.py`

One stdlib-only file (Python 3.9), copied byte-identical into `rhize-context-manager/scripts`,
`rhize-devflow/scripts`, `rhize-ops/scripts` and `project-launcher/scripts`, drift-tested in
`tests/config-lint/test_shared_shims.py`. Context Manager's `laya_choice.py` (skill-fit instrument) is not
modified.

- **Transport:** literal loopback only (`127.0.0.1`, `[::1]`), no redirects, no proxies, `/health` identity
  probe cached 60 s, 64 KiB cap, one monotonic deadline, never raises. Same semantics as `laya_choice.py`.
- **Request:** state `{request: ≤1,500 redacted chars, files: ≤20 repo-relative hints}` plus one `choice`
  question with per-candidate criteria; absolute paths, `..` and secret-shaped names are dropped.
- **Mode:** reads `~/.local/share/rhize/typed-decisions/registry-state.json` (read-only), default `shadow`,
  corrupt → `shadow`, binding mismatch → `shadow`. Kill switch: `set-mode --pin off|shadow`.
- **Records:** `<root>/<decision>/choice/<id>.json` write-once (`os.link`), dirs 0700, files 0600, symlinks
  refused. A record holds hashes, candidate ids, recommendation, probabilities, mode, arm and
  `critical_if_wrong`; the redacted request snapshot is stored separately (owner-only) for blinded labelling
  and never contains raw prompt text beyond the redactor output.
- **API:** `advise(decision, request, files, candidates, key, *, critical_if_wrong, criteria)` →
  `{decisionId, mode, holdback, recommendation: {id, confidence} | None}`; `record_outcome(decision, id,
  chosen)`.

## 6. Surfaces

- **Workflow fit:** S1 v3 envelope (salvaged), advice line in `workflow_selection.py context` when the
  registry says `advise`; hook text becomes mode-aware (no longer "Laya is shadow-only").
- **Procedure pick:** `workflow_selection.py recommend-procedure --id` reads recall hits on stdin; `decide
  reuse|adapt` records the outcome.
- **Skill fit:** `skill-router.js` adds an `advise` branch ("Laya suggests the <skill> skill (advisory).")
  next to the existing cosign branch; settle-once and byte-identical fallback unchanged.
- **Dev Flow:** `typed_checkpoint.py --mode advise` (`devflow-next-action`, critical when hard gates are not
  all true), `typed_selection.py` browser-QA advise; `outcome` subcommand.
- **Routing:** `typed_routing.py --mode advise`; a user pin skips Laya (`mode: pinned`).
- **GSD:** fix the `supervise` choice/noul bug; local advisory mode asks `gsd-directive`; `finish_candidate`
  suppressed unless checks and review passed; `install --local-laya`; hosted Jev path unchanged.

## 7. Check relaxation (S4)

`rhize-devflow` `check` gains `check_relaxation.py`:
- **Eligibility is deterministic** and never from Laya: routine stratum, non-release stage, every changed
  path in an allowlisted class. Unknown or mixed → not eligible.
- **Allowlist:** docs-only → affected tests instead of the full suite; no component/style/template/route
  files → skip browser QA; no logic files → skip mutation analysis; lint narrowed to changed files.
- **Protected paths never qualify:** build/CI/deploy config, auth, env files, dependency manifests and
  lockfiles, migrations, infra.
- **Never relaxable:** deploy, publish, credentials, approvals, security review, required CI, the
  production-merge review — enforced in the execution path regardless of Laya output.
- **Binding:** a relaxation is bound to the diff hash and expires on any change or a move to a release stage.
- Laya advises `full|relaxed` only on eligible diffs; in `shadow` the full checks always run.

## 8. Learning loop

- **Labels:** a generic choice labeler beside `skillfit_labels.py`, reusing its two-annotator + reviewer
  backend and the redactor; annotators see only the frozen pre-decision snapshot and the candidate set.
- **Cycle:** `decision_cycle.py` dispatches on `gateKind`; `majority-baseline` reads choice records and labels,
  runs the gate, and mutates the registry through `decision_registry.mutate` (the single locked path).
- **Scoreboard:** one row per decision (mode, labelled n, accuracy vs baseline, Wilson bound, critical misses).
- **Daily:** append to the existing autolabel launchd job (twice daily, shared lock).

## 9. Waves (worktree-durable; `wip:` commit after every handback; simplify after every phase)

1. **Contract (coordinator):** registry/state schemas + `contract.py` + tests for `advise`, `gateKind`,
   critical-advise; `rhize-typed-choice-record-v1`; `typed_advice.py` + drift test; S1 salvage
   (`f5038b7` code, minus `typed_transport.py`); majority-baseline gate module.
2. **Surfaces (parallel, by plugin territory):** Context Manager, Dev Flow, Ops, Project Launcher.
3. **Learning loop:** labeler adapter, cycle dispatch, scoreboard.
4. **S4:** check relaxation.
5. **Release:** docs, minor bumps (4 plugins + marketplace), skill map, vault review, Codex + Dev Flow final
   review, PR, merge.

## 10. Acceptance

- Mode matrix per surface: off/shadow/advise/holdback, timeout, invalid id, stale binding, corrupt state.
- Transport: hostname refused, redirect refused, proxy ignored, identity failure, oversize body.
- Critical: a critical miss demotes; critical never reaches `cosign`.
- S4: protected paths and never-relaxable set enforced with Laya forced to `relaxed`.
- Gate fixtures (paired Clopper–Pearson, α=0.10, 80% baseline): 28/30 passes, 27/30 holds; class coverage; alpha spending; disjoint cohorts.
- Full suite, Node router tests, Python 3.9, manifests/config-lint/skill-map freshness all pass.
- No decision is in `advise` at release unless the live cycle earned it; the release ships the ability.

## 11. Codex review (gpt-6.1-sol, job bc36574c, 2026-10-16) — adopted

| Finding | Resolution |
|---|---|
| Wilson bound has no control over repeated attempts | Disjoint, ledger-reserved cohorts; per-decision alpha spending (§3.5) |
| Baseline estimand underspecified | Majority from tuning, frozen; paired sign test on the same promotion cases (§3.2, §3.4) |
| Abstention/unavailable denominators | Count as wrong; `none` is a candidate; coverage ≥ 90% (§3.3) |
| Zero critical misses with zero critical cases | ≥ 10 critical cases; trusted, frozen `critical_if_wrong`; demotion inside the label-import job (§3.6–3.7) |
| Skill fit needs two gates | Per-mode gate and policy map; no substitution; regression tests (§3) |
| Bindings must cover advise | Every earned mode binds policy, instrument and Laya revision; revalidated under lock (§3.8) |
| S4 needs an executable contract | Trusted `check_plan.py`: complete diff (status incl. renames/deletes) + stage + config → mandatory set; advice can only remove items from the relaxable set; missing input → full. Next-action and GSD advice are text only and never change a gate result (tested) |
| Independent labels | Session grouping before split; annotators see only the frozen snapshot and candidates (no recommendation, outcome or mode); labels carry `rubricVersion`; labels in a consumed cohort are frozen by hash |
| Demotion hysteresis vague | Fresh-label rolling rule (§3.7) |
| Persistence vs "hooks persist no text" | Hooks persist nothing new (skill fit keeps its transcript-backfill path). Only CLI surfaces store snapshots, from caller text passed through the versioned redactor (`pilot_redaction` in Context Manager, `typed_advice.scrub` in islands, version recorded); 0600, 90-day retention |
| Drift from `laya_choice.py` | Shared behavioural conformance suite runs both transports through the same cases |
| Record/outcome contract | Outcomes are separate write-once files referencing `decisionId`; `chosen` must be a candidate; first write wins, a conflicting duplicate returns False; path components validated; no durable record → no advice shown |
| Holdback unit | Unit = decision key; domain `holdback:` separate from `split:`; holdback still calls Laya (shadow evidence) but never shows advice; outcomes collected in both arms |
| Test ordering | Contract + safety tests land in wave 1, before surfaces; release requires an integrated label → cycle → registry → reader test |

## 12. Final review fixes (2026-10-16) - F2b gate

| Finding (Codex final) | Resolution |
|---|---|
| Repeated cases of one session inflate the sign test | Group is the unit: one case per group in `evaluate`, ledger refuses intersecting groups across attempts (§3.1, §3.5) |
| A policy picked after seeing outcomes can reuse earlier-recorded cases | Prospective cohort: `open` event first, cases are the earliest record per promotion group created after `openedAt` on that binding (§3.5) |
| Class coverage skipped tuning classes missing from the cohort | Required classes = tuning prior share ≥ 10%, zero-count included (§3.4) |
| Unanswered critical cases were not critical misses (10 unanswered + 90 correct passed) | Critical miss = `critical_if_wrong` case not right, abstain/unavailable included, in the gate and in demotion (§3.6, §3.7) |
| Outage handling ambiguous | Probe mandatory before `open`/`reserve`; must return `True`, else held with no ledger write; pilot demotion probes first (§3.5, §3.7) |
| Demotion only looked at the window | Critical-tier demotion scans every shown critical case since the last demotion (§3.7) |
| Binding flapped on stray records | An earned advise uses the registry state's `policySha256`; skill-fit binds the `advise-v1` contract hash on both the Python and Node readers (§3.8) |
