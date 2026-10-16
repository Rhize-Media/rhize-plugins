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
  - `majority-baseline` (policy `advise-v1`) — salvaged from the 2026-10-06 S1 gate:
    1. labels split by stable hash into tuning and promotion; each attempt needs ≥10 promotion cases the
       previous attempt did not see;
    2. promote when the one-sided 90% Wilson lower bound of promotion accuracy exceeds the majority
       baseline (27/30, 44/50, 86/100 at an 80% baseline) **and** balanced accuracy beats the baseline's;
    3. every class with ≥10% prior share has ≥3 promotion cases and recall ≥0.5;
    4. zero critical misses (a wrong, non-abstaining answer on a `critical_if_wrong` case);
    5. minimum 30 labelled cases (the retired 200 floor is not reinstated);
    6. demote immediately on any critical miss, otherwise after two consecutive cycles below baseline;
    7. state binds `policySha256` (instructions, criteria, candidate set, abstain threshold) and
       `instrumentSha256`; any change returns the decision to `shadow`.
  - Skill fit may reach `advise` by the same gate (its advice is an added line, not suppression).

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
- Gate fixtures: 27/30 at 80% passes, 26/30 holds; class coverage; hysteresis; ≥10 new cases.
- Full suite, Node router tests, Python 3.9, manifests/config-lint/skill-map freshness all pass.
- No decision is in `advise` at release unless the live cycle earned it; the release ships the ability.
