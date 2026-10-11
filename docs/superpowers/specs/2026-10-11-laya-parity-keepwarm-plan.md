# Laya keep-warm, learning feeds and Claude/Codex parity: plan and impact map (2026-10-11)

Status: planned. Builds on `2026-10-11-laya-earned-authority-plan.md`. On the maintainer's Mac, skill-fit is
live in `cosign`, at registry revision 1, bound to policy `cosign-v1`, instrument `laya-choice-v1` and Laya
55cf4c4e.

## 1. Evidence

**E1. Cold start (measured 2026-10-11 on the Mac, raw `/v1/systemone` from a loopback client).** These are
single measurements per idle gap:

| idle before the call | time to answer | warm follow-up |
|---|---|---|
| 30 s | 201 ms | 47 ms |
| 60 s | 163 ms | 32 ms |
| 120 s | 177 ms | 36 ms |
| 300 s | 1,297 ms | 34 ms |
| ~22 min | 1,213 ms | 48 ms |

Compressed memory for the Laya process stayed flat at 605 MB, so the slowdown is not caused by memory
compression. The hook spends a further 60–150 ms on node start-up and the `/health` probe, whose cache lasts
60 s. Two live cosign smokes timed out at 800 ms after idle periods.

**E2. Gaps between Laya-eligible router events.** Across 265 events on 2026-09-27..10-11, the share of
events preceded by more than a given idle time was:

| idle longer than | share of events |
|---|---|
| 2 min | 76% |
| 5 min | 54% |
| 10 min | 40% |

The median gap was 387 s. Under the 800 ms budget, roughly half of live calls would therefore time out and
show the incumbent.

**E3. Parity audit (Mac, 2026-10-11).**

| Feature | Claude | Codex |
|---|---|---|
| Workflow-fit: workflow-selection checkpoint and Laya shadow | runs (plugin `hooks.json` UserPromptSubmit #2, plus the router bridge) | runs: hooks are trusted in `config.toml`, and the checkpoint was seen as a developer message in a 2026-10-11 rollout |
| Skill-fit: router suggestion, Laya co-sign and decision records | runs (the `~/.claude/settings.json` hook only) | **missing**: the router is not in the plugin's `hooks.json` |
| Record `host` | `claude` | `RHIZE_HOST` env var only; would record `claude` |
| Outcome join | Claude transcripts | turns are searchable, but there is **no skill-invocation parser**, so the join reports unavailable |
| Backfill | 15 days | none; there is no router history to replay |
| Daily loop, labels, gate, scoreboard | host-neutral; the labelers use both CLIs | (same) |
| Scoreboard per-host split | n/a | **missing** |

Codex loads skills by reading `…/skills/<name>/SKILL.md`. 34 such reads were found in the 16 most recent
2026-10-11 rollouts. Hook `additionalContext` arrives in Codex as a `developer` message.

## 2. Semantic delta

### K. Keep-warm (approved: keep-warm, budget stays 800 ms)

- **New `rhize-context-manager/scripts/typed_decisions/laya_keepwarm.py`.** Standard library plus
  `typed_decisions.instrument` only.
  - `once` sends one ping.
  - `run --interval 90 --active-window-hours 2` loops.
  - Each ping is one fixed, synthetic `choice` request built with `instrument.build_choice_request`. It
    carries no user data and uses the same shape and endpoint as the hook (literal loopback,
    `ProxyHandler({})`, redirects refused, 10 s timeout).
- **Activity gate.** It pings only while the newest of these is younger than the active window:
  - the suggestion log, `$RHIZE_SUGGESTION_LOG` or `~/.claude/context-manager/suggestion-log.jsonl`;
  - the newest skill-fit records file.

  Otherwise it sleeps and counts `skippedIdle`.
- **Failure backoff.** 90 s → 180 s → 360 s → 600 s cap. It resets on the first success.
- **State.** `<root>/laya-keepwarm.json` (0600, atomic, no symlinks) holds:
  - `lastPingAt`, `lastStatus`, `lastLatencyMs` and `consecutiveFailures`;
  - the counters `pings`, `ok` and `skippedIdle`;
  - `startedAt`, `intervalSeconds` and `activeWindowHours`.

  It never writes decision records, labels or outcomes. `LAYA_KEEPWARM=0` disables it.
- **The scoreboard** adds a keep-warm line built from that file: last ping, status, failures and age.
- **Ops (Mac, gitignored).** `managed-serve.py` starts the keep-warm loop in a daemon thread, by importing it
  from the native marketplace clone, before it either waits on an existing listener or serves. An import or
  runtime error is caught and logged once, and the server is unaffected. The launchd job is restarted once at
  activation, which verifies the pins against a fresh process.

### H. Learning-harvest feed (item 1, daily, deterministic, queue-only)

- **New `scripts/typed_decisions/harvest_signals.py`.**
  - `emit --queue PRIVATE_JSONL --proof PRIVATE_JSON [--root R] [--now T]` reads skill-fit records and
    their outcomes after the watermark, together with any record more than 24 h old that has an outcome.
    It writes refinement-queue candidates in the learn-harvest schema to the private file only, never to the
    live queue. The proof records the candidate watermark, its source hashes and the counts.
  - `commit --proof PRIVATE_JSON` advances `<root>/skill-fit/harvest/watermark.json` atomically under a
    lock. It refuses if the watermark moved since the proof was written.
- **Signals.** These are grouped per skill per window and carry ids and counts only, never prompt text.
  `source` is `skill-fit-decisions` and `id` is sha1-12(source+pattern).
  1. `signal_type: "routing-miss"`, `subtype: "not-shortlisted"`: skill S was invoked
     (`invoked_unlisted`) after the router emitted another skill or nothing. `target_skill` is S.
  2. `signal_type: "routing-miss"`, `subtype: "suggested-but-ignored"`: the router emitted X, and the user
     invoked another shortlisted skill Y (`invoked_other_shortlisted`). `target_skill` is X.
  3. `signal_type: "decision-layer"`, `subtype: "cosign-suppressed-then-invoked"`: cosign withheld X and the
     user invoked X anyway. `target_skill` is X. This is the direct cost of Laya's authority.
  4. `signal_type: "decision-layer"`, `subtype: "laya-timeouts"`: the window's live timeout share is above
     5%.

  Signals are split by host when both hosts contribute.
- **`commands/learn-harvest.md`.** The "suggested-but-ignored is not computed" paragraph is replaced. It now
  says the signal comes from decision records, and it documents the two new signal types.
- **Runbook (claude-routines, `scheduled/codex/daily-learn-harvest/RUNBOOK.md`).** In the monitor phase,
  `harvest_signals.py emit` runs as a captured phase command. Its candidates enter the existing filter
  and verify steps. `commit` runs after verify, next to `sources.py consume`.

### W. Weekly improvement loop (item 2, autoresearch-style, never auto-merges)

- **New `evals/skill-map-routing/real_traffic.py`.** It is the fixed evaluator for router candidates on real
  traffic.
  - **Cases.**
    - Labeled skill-fit cases: the acceptable set, constrained to the original shortlist.
    - Harvested weak positives: an invoked skill S, where `invoked_unlisted` or `invoked_other_shortlisted`
      came within 3 user turns.
  - **Replay.** Prompt text is recovered from local transcripts in memory only, never persisted. The same
    `route_replay.js` is replayed against the baseline checkout and against a candidate checkout.
  - **Split.** By `sha256('rt-split:' + sessionHash)`: 75% dev, 25% locked holdout. The split is
    deterministic and recorded in the manifest.
  - **Metrics.** Acceptable-hit, false-fire (fired when the label says no shortlisted skill fits),
    weak-positive recall, and unscorable (the route fell outside the labeled shortlist).
  - **Keep rule.** A candidate is kept only if all three of these hold:
    - the routing harness `run.py --checkout CANDIDATE --check baseline.json` passes;
    - the dev net gain (hits + recalls − false fires) is ≥ 1;
    - the holdout net is ≥ 0 and holdout false fires do not rise.
  - **Ledger.** `<root>/skill-fit/improvement/ledger.jsonl` (append-only, hashes and counts) and a report
    per run.
- **New weekly Codex automation `skill-fit-weekly-improvement`** (Sundays 18:30, local).
  1. Read the week's `skill-fit-decisions` queue entries and the scoreboard.
  2. In an isolated git worktree on a local branch, propose at most 3 candidate edits. Allowed edits are
     `catalog/tags.json` entries, or tags and trigger phrases in owned SKILL.md files.
  3. Run the evaluator.
  4. Write the patch, the evaluation and the ledger entry to a private folder.
  5. Notify Jim.

  It never pushes, merges or opens a PR. It never edits the instrument, policy, registry or gate code, and
  it never runs the gate.

### C. Codex parity (item 3)

- **`hooks/hooks.json`.** The skill router is appended as UserPromptSubmit entry index **3** (timeout 10 s,
  since the router needs ≥ 8 s). Existing entry indices are unchanged, so existing Codex trust keys stay
  valid. Codex asks Jim to trust the new entry through its native UI.
- **`hooks/skill-router.js`.**
  - Host detection mirrors `workflow_selection.detect_host`. `thread_id` or a non-empty `PLUGIN_ROOT` means
    codex. `CLAUDE_CODE_ENTRYPOINT` means claude. A contradiction or no evidence means `unknown`. An explicit
    `RHIZE_HOST` still wins.
  - The session id is `session_id || thread_id`.
  - **Per-prompt dedupe receipt.** The key is sha256(host:session:contextHash:minute), created with O_EXCL
    under `os.tmpdir()/rhize-skill-router-<uid>/`. Receipts older than 10 minutes are pruned
    opportunistically. A second registration of the router for the same prompt exits with no output, no Laya
    call and no record. This makes the transition window safe, while Claude still has both the
    `settings.json` entry and the `hooks.json` entry.
- **`scripts/typed_decisions/transcripts.py`: Codex skill-invocation parser.**
  - **`skill_file_read`.** A `function_call` or `custom_tool_call` whose arguments or input name a path
    `…/<plugin>/[<version>/]skills/<skill>/SKILL.md` under a plugin root
    (`~/.codex/plugins/cache/<mkt>/<plugin>/<ver>/`, `~/.claude/plugins/marketplaces/<mkt>/<plugin>/`, or a
    `rhize-plugins` checkout) gives the ref `plugin:skill`.
  - **`explicit_mention`.** A user turn that names `$skill` or `$plugin:skill` gives the same kind of ref.
  - Codex turns stay searchable as today.
  - `outcomes.py` no longer treats Codex transcripts as unavailable.
- **`scoreboard.py`.** A per-host breakdown covering records, live arms, statuses, disagreement prevalence
  and outcomes.
- **Activation (Claude).** Right after the Claude plugin update, the `settings.json` router entry is removed,
  with a backup. The plugin's `hooks.json` entry is then the only registration in both hosts.

### R. 08:00 report (item 4)

- **Prompt.** The Codex automation `laya-workflow-measurement-and-research` gets one read-only paragraph. It
  reads `skill-fit/daily/latest-summary.json`, `latest-scoreboard.md` and `laya-keepwarm.json`, and reports
  mode, last cycle actions, cohort status, per-host counts, timeout share and keep-warm status.
- **It notifies on:**
  - a mode change;
  - a failed or timed-out loop step;
  - a summary more than 26 h old with no active run;
  - keep-warm `consecutiveFailures` ≥ 3, or no ping for 2 h while activity is recent;
  - a live timeout share above 5%.
- **Guardrails.** It never runs the loop, the cycle or the labelers. The previous toml is archived under the
  automation's `history/`.

## 3. Invariants

- **I1.** Keep-warm sends only its fixed synthetic request to a literal loopback endpoint. It never writes
  decision evidence, and it can neither stop nor slow the server by failing.
- **I2.** `harvest_signals emit` never writes the live queue or prompt text. The watermark moves only through
  `commit` with a matching proof.
- **I3.** The weekly loop never pushes or merges, and never edits instrument, policy, registry or gate files.
  Prompt text stays in memory. The holdout split is fixed and recorded, and the ledger is append-only.
- **I4.** At most one router run produces output, Laya calls or records per prompt per host, even when the
  router is registered twice.
- **I5.** Existing `hooks.json` entry indices and commands are unchanged. Only one entry is appended.
- **I6.** Records carry the detected host. Contradictory evidence records `unknown`.
- **I7.** Both hosts read the same registry state, binding and Laya pin. A stale binding reads as shadow in
  both.
- **I8.** The instrument and policy hashes are unchanged: `instrument.py` and the `contract.py` policy table
  are untouched. The live cosign binding therefore survives this release. A test pins the instrument hash.
- **I9.** The 08:00 automation stays read-only with respect to skill-fit.

## 4. Acceptance tests

- **A1 (keep-warm).**
  - `once` against a stub server sends exactly the fixed request, and the state file has 0600 permissions.
  - With an idle activity gate it does not ping.
  - Failures back off up to the cap and reset on success.
  - The pinned endpoint rejects anything but loopback and refuses redirects.
  - `LAYA_KEEPWARM=0` makes it exit without pinging.
- **A2 (harvest).** Fixture records and outcomes produce the four signal kinds with exact counts and ids.
  - No prompt text.
  - A second emit after commit yields nothing new.
  - Commit refuses a stale proof.
  - The live queue path is never opened.
- **A3 (weekly evaluator).** On synthetic cases with injected prompt text:
  - The baseline-versus-candidate metrics are exact.
  - The split is deterministic.
  - The keep rule is enforced, including a harness failure.
  - The ledger is append-only.
  - No prompt text reaches the outputs.
- **A4 (router).**
  - Host detection works for the claude, codex, contradictory and explicit cases.
  - `thread_id` is accepted as the session.
  - A second invocation for the same prompt is silent: no stdout, no Laya request, no record.
  - Distinct prompts both run.
  - `hooks.json` keeps entries 0–2 byte-identical and appends the router at index 3.
- **A5 (Codex outcomes).** Fixture rollouts with SKILL.md reads and `$skill` mentions produce the expected
  invocations. Paths outside a plugin root and Claude-only `Skill` tool events are not misread. Codex
  outcomes are joined.
- **A6 (scoreboard).** The per-host split and the keep-warm line render. An empty root still renders.
- **A7 (no regression).**
  - The full pytest and Node suites pass.
  - The routing harness gates pass.
  - The instrument hash pin passes.
  - `validate_skill_map --check-stale` and the version check pass.
- **A8 (Mac activation).** All of these must be observed:
  - Both hosts are on the new version.
  - Codex shows the trust prompt, and Jim approves it.
  - One fresh Codex prompt and one fresh Claude prompt each produce exactly one decision record, with the
    correct `host`.
  - The Codex record's `sessionHash` maps to its rollout file.
  - Keep-warm pings and `laya-keepwarm.json` updates.
  - The p50 cold-gap latency after a 5-minute idle with keep-warm active is below 400 ms.
  - The daily loop and the 08:00 report read the new files.

## 5. Implementation lanes

Implementation runs as parallel Sonnet lanes in isolated worktrees, from a contract commit.

| Lane | Scope (exclusive files) |
|---|---|
| L1 router (JS) | `hooks/skill-router.js`, `hooks/hooks.json`, `tests/skill-map/test_router_parity.js` (new) |
| L2 Codex outcomes and scoreboard (Py) | `typed_decisions/transcripts.py`, `outcomes.py`, `scoreboard.py`, tests and fixtures under `tests/rhize-context-manager/` (new files) |
| L3 keep-warm and harvest (Py) | `typed_decisions/laya_keepwarm.py`, `harvest_signals.py`, `commands/learn-harvest.md`, new tests |
| L4 weekly evaluator (Py) | `evals/skill-map-routing/real_traffic.py`, new tests, `docs/typed-decisions/weekly-improvement.md` (automation prompt) |

**Coordinator.**
- Plan and contract: the scoreboard keep-warm reader interface.
- Docs: the operator guide, the README, GUIDE and CHANGELOG, and the version bump through `bump_version.py`.
- Integration.
- Mac ops: `managed-serve.py`, the runbook commit in claude-routines, the automation tomls, `settings.json`
  router removal, native updates and verification.

Executors never push.

## 6. Rollback

- **Keep-warm.** `LAYA_KEEPWARM=0` in the launchd environment, or revert `managed-serve.py`.
- **Router in Codex.** Decline or untrust the entry in the Codex trust UI. In Claude, restore the
  `settings.json` backup.
- **Harvest and weekly loop.** Revert the runbook commit or pause the automation. Both are queue- and
  report-only.
- **Skill-fit authority.** `decision_registry.py set-mode skill-fit shadow --reason manual_rollback --pin`.

## 7. Plan-review reconciliation (supersedes §2 to §5 where they conflict)

Fable verdict: proceed-with-changes (0.75). Codex `dcbc1824` verdict: proceed-with-changes. Claims were
checked against the Mac:

- **Hook transcript path.** Codex hook payloads carry `transcript_path`. Of the last 600 workflow request
  snapshots, 105 point at a Codex rollout.
- **Thread source.** Rollout `session_meta` has `thread_source`. In October there were 917 rollouts: 752
  `guardian_review`, 152 `subagent`, 11 `user`, 1 `automation` and 1 `agent_created_thread`.
- **Session ids.** `session_meta.session_id == id ==` the filename UUID for user threads. For subagents,
  `session_id` is the root thread's id.
- **Router opt-in.** The router is an opt-in T3 hook: setup manifest `skill-router`, `"default": false`.

| # | Finding | Resolution |
|---|---|---|
| F1 / Fable 1 | Codex machine traffic would pollute evidence: guardian reviews, subagents, automations | For host codex, the router reads the first line of `transcript_path` (bounded to 512 KiB) and runs only when `session_meta.thread_source == "user"`. Otherwise there is no suggestion, no Laya call and no record. Harvest and the evaluator also drop non-user Codex sessions. A8 adds: an automation run produces zero records. |
| F2 / Codex | Unverified Codex session identity | The Codex session identity is `session_meta.id` (which equals the rollout UUID that `session_paths` indexes), falling back to `session_id ‖ thread_id`. A8 verifies the mapping. The outcome summary keeps counting unmatched sessions. |
| F3 / both | SKILL.md reads and `$` mentions over-count invocations | Count only read-shaped shell `function_call` commands (`cat`, `sed -n`, `head`, `tail`, `nl`, `bat`, `less`) on a `…/skills/<s>/SKILL.md` under plugin cache or marketplace roots (`~/.codex/plugins/cache`, `~/.claude/plugins/{cache,marketplaces}`). Never count the dev checkout, `custom_tool_call` (e.g. `apply_patch`), or mentions. `via = "skill_file_read"` is a separate evidence type; the outcome schema `via` enum gains it. Precision is checked by hand on real rollouts before activation. The evaluator excludes `skill_file_read` weak positives. |
| F4 / Codex | Host-detection precedence | Order: a valid `RHIZE_HOST` override, then the `transcript_path` location (`~/.codex/{sessions,archived_sessions}/…/rollout-*.jsonl` means codex, `~/.claude/projects/` means claude), then payload `thread_id` (codex) or the `CLAUDE_CODE_ENTRYPOINT` env var (claude). Conflicting inferred signals give `unknown`. An invalid override is ignored. Each case gets a fixture. |
| F5 / both | Minute-bucket dedupe receipt is unsound | Dropped. There is a single registration instead. The `hooks.json` entry runs `skill-router.js --packaged`. A packaged run requires the opt-in config `~/.local/share/rhize/skill-router/config.json` = `{"schemaVersion":1,"enabled":true}` (default off, so other plugin users are unaffected). In Claude, a packaged run also defers silently while `~/.claude/settings.json` still has a manual `skill-router.js` hook. Manual runs behave exactly as today. Migration: enable the config, then remove the manual entry. |
| F6 / both | Codex would go straight to cosign with zero Codex evidence and be pooled into the gate and demotion | Router: `COSIGN_HOSTS = ['claude']`, so any other host's effective mode is capped at `shadow`. `cohorts.py`: `GATE_HOSTS = ('claude',)` filters the reserve pool, live unavailability and the demotion windows. Codex shadow evidence accumulates for a later Codex-stratified gate. The scoreboard shows every metric per host. The binding is unaffected: no policy or instrument change. |
| F7 / both | Weekly keep rule is weak; the holdout is adaptive; shortlist-constrained labels; weak-positive confounding | `real_traffic.py` uses a **prospective** design. A candidate is frozen with hashes, then confirmed only on cases first recorded **after** its freeze time, so it never sees them. Weak positives require `latencyTurns == 0`, the nearest record, `via ∈ {skill_tool, slash_command}`, and must not be a mandated-skill-only signal. Labeled metrics cover comparable cases only; a route outside the labeled shortlist is unscorable and reported separately. Silence samples (the 1/20 non-fires) act as negatives, and the fire rate must not rise. **Keep** requires: the harness `--check` passes, ≥ 10 discordant confirmatory cases, a one-sided sign test at p ≤ 0.05 favoring the candidate, no rise in fire rate, and an unscorable share ≤ 20%. The weekly automation confirms the last frozen candidates on fresh data, then proposes ≤ 3 new ones using dev data only. It never pushes, merges or opens a PR. |
| F8 / Codex | Prompt-text boundary in replay | Replay prompts reach node via stdin only (never argv), in a child environment with a temporary `RHIZE_TYPED_DECISIONS_ROOT` and `XDG_DATA_HOME`, so no Laya call, no workflow bridge and no decision writes happen. Outputs are an allowlist of aggregates and opaque occurrence keys. Errors pass through `safe_reason`. |
| F9 / both | Keep-warm thread inside the live server; backoff cap above the cold threshold; gated on router activity | It runs as a **separate** launchd agent, `media.rhize.laya-keepwarm` (KeepAlive, `/usr/bin/python3`, marketplace clone), with no server restart. Interval 90 s, backoff capped at 120 s, and the first ping waits for `/health`. It skips a ping when any activity signal is under 60 s old, since live traffic is already keeping Laya warm. The activity gate is the newest of: the workflow-selection `receipts/` directory (both hosts write a receipt per prompt), the suggestion log and the newest skill-fit records file, inside 2 h. Its health is reported separately from server health. |
| F10 / both | Harvest watermark semantics; daily duplicate ids | No watermark. Each run is idempotent over a trailing 14-day window of finalized records (outcome present). A candidate is emitted when (signal, subtype, skill, host) has ≥ 3 events. The pattern is stable (no counts or dates), so `id = sha1-12(source+pattern)` dedupes against every queue status. Signals are framed as **review candidates**, not ground truth. Suggested-but-ignored needs the suggestion to have been shown. Suppressed-then-invoked needs the treatment arm, `emitted` null and `latencyTurns ≤ 1`. |
| F11 / Codex | Ordered rollout | See §8. |
| Note | Shipping in `hooks.json` reaches all plugin users | Default-off config plus fail-silent behavior, documented in the README, GUIDE and setup manifest. |
| Ops | Tonight's smoke tests reached the workflow pilot through the router's workflow bridge | 17 synthetic opportunities (2026-10-11 21:18–21:32Z, `transcriptPath` null) are recorded in ACTIVATION.md and in the 08:00 prompt as operator probes, not user tasks. Captures are not edited. From now on, smokes set a temporary `XDG_DATA_HOME`. |

## 8. Lane contract and ordered rollout

**Contract (coordinator; lanes implement against it).**

- **`<root>/laya-keepwarm.json`** (written by L3, read by L2's scoreboard). Fields:
  - `schema: "rhize-laya-keepwarm-v1"`, `startedAt`, `lastPingAt`
  - `lastStatus` ∈ {ok, timeout, unavailable, invalid, redirect_refused}
  - `lastLatencyMs`, `consecutiveFailures`, `pings`, `ok`, `skippedIdle`, `skippedWarm`
  - `intervalSeconds`, `activeWindowHours`, `lastActivityAt`
- **Skill-router opt-in.** `$XDG_DATA_HOME|~/.local/share/rhize/skill-router/config.json` holds
  `{"schemaVersion":1,"enabled":true}`. Any other content means disabled.
- **Host and session.**
  - Record `host` ∈ {claude, codex, unknown}.
  - Codex session identity is `session_meta.id`.
  - The `typed_*` legacy row fields are unchanged.
  - The legacy row gains `host`, and the suggestion-log readers tolerate the extra key.
- **Outcome `via` enum.** {skill_tool, slash_command, skill_file_read}.
- **Gate scope.** `cohorts.GATE_HOSTS = ('claude',)` and router `COSIGN_HOSTS = ['claude']`.

**Ordered rollout (A8).**
1. Merge and release, then confirm CI.
2. Update the Claude plugin and the Codex marketplace and plugin through the native lifecycle. Confirm both
   hosts report the new version.
3. Load and start the keep-warm agent. Verify its pings and state file, then re-measure latency after a
   5-minute idle.
4. Write the skill-router opt-in config. Claude defers to its manual entry, so there is still exactly one run.
5. Ask Jim to approve the appended Codex hook in the native trust UI. Verify the existing trust entries are
   unchanged.
6. Remove the Claude manual `settings.json` router entry, keeping a backup. Verify that a fresh Claude prompt
   produces one record with `host=claude`.
7. Verify that a fresh Codex user prompt produces one record with `host=codex`, in shadow, whose
   `sessionHash` maps to its rollout. Verify that an automation or subagent prompt produces none.
8. Run outcomes, then harvest emit, then the scoreboard, and confirm the per-host rows.
9. Update the 08:00 prompt, commit the runbook change, and create the weekly automation.

## 9. Implementation reconciliation

Four parallel Sonnet lanes worked in isolated worktrees: task-graph v2 was validated, 2 waves, 4 isolated roots. Each lane was squash-merged with the correct attribution.

**Deviations accepted:**
- **L1:**
  - `transcript_path` outranks the `thread_id`/`CLAUDE_CODE_ENTRYPOINT` pair. A Codex process started from Claude therefore stays `codex` and is gated.
  - Non-user Codex threads write no legacy row, so they are not counted as silence samples.
  - A packaged run on an `unknown` host does not look for a manual registration.
  - Codex roots are `~/.codex` only; `CODEX_HOME` is not honored.
- **L2:**
  - `current_key` and its reserve feed are also scoped to `GATE_HOSTS`. This stops a newer Codex record from moving the gate key.
  - One existing test, the old "Codex has no parser" assertion, was updated.
  - `decision_cycle.alternatives_report` still pools hosts. It is report-only.
- **L3:**
  - `once --force` (for diagnosis) and a single-writer lock.
  - The first ping waits for `/health`.
  - Harvest patterns carry no numerals.
  - `laya-timeouts` uses all live records in the window.
  - The plist must use `KeepAlive` with `SuccessfulExit=false`.
- **L4:**
  - `freeze` refuses a dirty checkout, a candidate that changes router code, and a manifest overwrite.
  - Arm index and map copies are frozen next to the manifest.
  - The weekly prompt retires an `insufficient` candidate after 4 weeks. The prompt enforces this, not the code.

**Integration fixes:**
- The scoreboard's keep-warm reader accepts every `laya_choice.STATUSES` value, including `identity_failed`, which the writer can record. A seam test covers this.
- Harvest gives Codex `skill_file_read` outcomes their own candidates ("host codex, SKILL.md-read evidence"), and a seam test covers this too.
- A test pins the bound instrument (8df42f4f…) and policy (19509e93…) hashes (I8).

**Release:** Context Manager 0.47.0, marketplace 2.104.0.
