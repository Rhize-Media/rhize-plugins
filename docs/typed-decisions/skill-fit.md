# Skill fit: Laya co-signs router suggestions

Skill fit is the first decision governed by the earned-authority registry. The skill router (`rhize-context-manager/hooks/skill-router.js`) proposes at most one skill per prompt. The local Laya server can co-sign that proposal. A suggestion is then shown only when Laya independently picks the same skill.

Laya starts in `shadow`. It earns `cosign` only by passing a frozen statistical gate, and it loses it again automatically.

- Design and reviews: [the plan](../superpowers/specs/2026-10-11-laya-earned-authority-plan.md).
- Tier policy: [typed decision layer](../typed-decision-layer.md#earned-authority-advisory-tier).

## What happens on each prompt

1. The router computes its incumbent suggestion exactly as before. It also precomputes today's exact hook output.
2. Sessions run by ECC's homunculus background observer (cwd under `~/.local/share/ecc-homunculus`, or the ECC launcher environment) get no router suggestion, no Laya call and no record. On 2026-10-11 that machine traffic was 83% of all replayed router fires.
3. The hook skips the Laya call (records nothing, and emits the incumbent output) when any of these is true:
   - `skill-fit` mode is `off`;
   - the router did not fire;
   - the prompt is an explicit skill request.
4. Otherwise the hook builds the `laya-choice-v1` request:
   - the first ≤1,200 code points of the prompt;
   - up to 5 shortlisted skills, each with a 120-character description;
   - a `none` option.

   It sends the request to the literal-loopback Laya server. A refused redirect, a failed `/health` identity probe, or the 800 ms deadline (shared by probe and request) all count as failures.
5. The output settles exactly once:

   | Situation | Hook output |
   |---|---|
   | Mode `cosign`, treatment arm (90%), Laya status `ok`, Laya's choice differs from the incumbent | The output without the router suggestion. A workflow message, if any, is still shown. |
   | Mode `advise`, treatment arm (90%), Laya status `ok`, Laya picks a shortlisted skill other than the incumbent | The incumbent output unchanged, plus one appended line: `Laya suggests the <plugin:skill> skill (advisory).` The incumbent is still the suggestion shown; the agent may ignore the line. |
   | Everything else (`shadow`, the 10% holdback arm, Laya agrees or picks `none` in `advise`, any Laya failure, deadline expiry, any error) | The incumbent output, byte for byte. |

6. After stdout has flushed, the hook appends one private decision record. The record holds hashes, ids, probabilities and latency, but never prompt text. The legacy suggestion-log row is written as before. Its `suggested` field now records what was actually shown, plus `typed_mode`, `typed_arm`, `typed_status` and `typed_agrees`.

**Hook timeout.** The hook needs a host timeout of at least 8 s. That covers the 4.5 s workflow bridge, the 0.8 s Laya deadline and Node startup. The default Claude Code command-hook timeout already exceeds this.

**Latency.** On Jim's Mac the Laya call measured 117 ms median and 142 ms at p90 on long prompts (2026-10-11).

## Where things live

Everything below lives under `~/.local/share/rhize/typed-decisions/`. Directories are 0700, files 0600, and symlinks below the root are refused.

| Path | What | Written by |
|---|---|---|
| `registry-state.json`, `registry-audit.jsonl`, `registry-state.lock` | Current mode per decision, and its audit trail | `decision_registry.py` (and the cycle through it) |
| `laya-runtime.json` | `{"revision": "<checkpoint revision>"}`, written at activation from the Laya runtime pins | operator |
| `laya-health.json` | 60 s identity-probe cache | hook |
| `skill-fit/records/YYYY-MM-DD.jsonl` | Decision records, live and backfill | hook, `backfill.py` |
| `skill-fit/labels/…`, `skill-fit/outcomes/…`, `skill-fit/cohorts/…` | Labels, transcript-joined outcomes, cohort ledger | `skillfit_labels.py`, `outcomes.py`, `cohorts.py` |
| `skill-fit/backfill/` | Frozen index, map and manifest for resumable backfill | `backfill.py` |
| `skill-fit/cohort-meta/`, `skill-fit/receipts/`, `skill-fit/cycles/` | Cohort inclusion probabilities, gate receipts, cycle receipts | `cohorts.py`, `decision_cycle.py` |

The shipped defaults (mode, holdback, budget, λ, gates) live in `rhize-context-manager/catalog/decision-registry.json`.

## Commands

All scripts are under `rhize-context-manager/scripts/typed_decisions/`, except the cycle. Each one accepts `--root DIR`; the default is the path above.

```bash
# Inspect, pin or roll back (manual pins suspend automation until --unpin)
python3 decision_registry.py show
python3 decision_registry.py set-mode skill-fit shadow --reason manual_rollback --pin
python3 decision_registry.py set-mode skill-fit shadow --reason manual_unpin --unpin
python3 decision_registry.py recover            # finish an interrupted mode change
# If recovery is blocked (diverged state, revision gap), cosign and automated changes are refused until it is
# fixed, but set-mode off/shadow from the CLI still works: the kill switch never waits on recovery.
python3 decision_registry.py set-mode skill-fit cosign --reason manual_override \
    --laya-revision <rev> --manual-override       # ungated, audited override (prefer --cohort-id)

# Evidence
python3 backfill.py run --since 2026-09-27 --cutover <activation ISO> --budget 1200
python3 outcomes.py join
python3 skillfit_labels.py label-cohort --cohort-id <id> [--prepare-only]
python3 skillfit_labels.py label-pool --n 12 [--prepare-only]

# The recursive loop and the daily report
python3 ../../../evals/typed-decision/decision_cycle.py run [--dry-run]
python3 scoreboard.py render --format md
```

## How authority is earned and lost

**Estimand.** Co-sign and the incumbent differ only when Laya disagrees with the router. Co-sign is better exactly when the router's suggestion is wrong in more than 1/(1+λ) of those disagreements. With λ = 1 that is more than half.

**Promotion.** The cycle reserves a frozen cohort of 60 disagreement cases from distinct sessions; reserving does not label anything. Once the labeler has labeled the cohort, the cycle tests it once. Promotion requires all of these:
- the one-sided exact Clopper–Pearson lower bound on "router wrong" exceeds 0.5 at α_k = 0.05·2^−(k−1), where k is the attempt number;
- at most 20% of labels are ambiguous;
- Laya's unavailable rate is at most 5%. For backfilled cases that rate comes from the backfill run logs (`skill-fit/backfill/runs.jsonl`). Each backfill record's `decisionId` starts with the 16-hex id of the run that answered it. A record whose run never logged, or logged fewer answered calls than it has records, is left out of the cohort pool.

Holds that need no labels are settled when the cohort is reserved, so they never spend α. This covers unavailability above the limit and backfill records the logs don't account for. Evaluation re-checks both, in case the evidence changed after reservation (`laya_unavailable`, `backfill_runs_missing`).

At n = 60 the first attempt needs at least 37 "router wrong". Ambiguous labels stay in the denominator and never count as "router wrong", so they can only make promotion harder. Every tested cohort spends its α, including one held at evaluation, and each new attempt needs a new cohort with a stricter α. Only evidence from the Laya checkpoint that is running now (`laya-runtime.json`) can reserve or promote a cohort. Only the plain co-sign policy (`cosign-v1`) can ever be deployed.

**Demotion.**
- **Quality:** demote when there are at least 30 labeled live co-sign disagreements in 14 days and the upper bound falls below 0.5.
- **Operational:** demote when Laya is unavailable or invalid on more than 10% of calls over 3 days.
- **Latency:** report-only for the first 14 days after a promotion, then enforced.
- **Pin:** a manual pin overrides all of these.

**Binding.** A cosign state is bound to the policy hash, the instrument hash and the Laya revision it was tested with. When a plugin update changes the policy or instrument, or when `laya-runtime.json` names a different checkpoint, the hook reads the state as `shadow` immediately. The next cycle records the demotion (`binding_stale` or `laya_revision_changed`) and starts a new cohort, so authority is re-earned on the new version. Rewrite `laya-runtime.json` whenever the Laya checkpoint changes. No cohort is reserved while the revision is `unknown`.

**Manual override.** `set-mode skill-fit cosign` needs `--laya-revision`. It also needs either `--cohort-id <passed cohort>` or an explicit `--manual-override`; leaving the cohort out never grants authority on its own. Overrides are audited as actor `cli`. Pin them (`--pin`) if automation must not demote them.

**Alternatives** (stricter router floors, thresholded co-sign, veto, swap, router-else-Laya) are scored on the daily label pool and reported only. A stricter floor that wins becomes a code-review recommendation.

## Daily rhythm

The existing 07:30 autolabel job, `laya-autolabel.sh`, runs the workflow labeler first. It then runs `skillfit-daily.py` in the same job. That script has its own lock, a 10-minute budget, and per-call deadlines for the labelers. It runs these steps:
1. `outcomes.py join`
2. `skillfit_labels.py label-cohort` for any open cohort, at most 30 cases a day
3. `skillfit_labels.py label-pool --n 12`
4. `decision_cycle.py run`
5. `scoreboard.py render`, which writes `skill-fit/daily/latest-scoreboard.md`. A counts-only run summary goes to `skill-fit/daily/latest-summary.json`.

The steps run from the native marketplace clone, the same tree the live hook runs from, so the cycle's policy and instrument hashes match the records the hook writes. A step that fails or times out is recorded, and the rest still run. If the job receives SIGTERM, the signal is forwarded to the running step, and any steps not yet started are skipped. `SKIP_SKILLFIT=1` skips the loop.

## Advise mode

`advise` is a second earned mode for skill fit, gated separately from `cosign` (advise policy `advise-v1`,
majority-baseline gate). It never suppresses the router suggestion; it only appends the line above when
Laya disagrees. Skill fit therefore ships in `shadow`, and nothing is in `advise` until the live cycle earns
it or an operator pins it.

- **Records.** A record written in `advise` has `mode: advise`. `emitted` stays the incumbent (or `null`),
  because the incumbent output is what is shown; whether the line was added follows from the record: mode
  `advise`, arm `treatment`, Laya `ok` and a choice that is neither the incumbent nor `none`. The cosign
  gate and demotion windows read only `cosign` records.
- **Binding.** The hook's reader (`decision-registry.js`) demotes an `advise` state to `shadow` when its
  `instrumentSha256` is not the `laya-choice-v1` hash, its `layaRevision` differs from `laya-runtime.json`,
  or an overriding `RHIZE_LAYA_ENDPOINT` is used without `RHIZE_LAYA_ENDPOINT_AUTHORITY=1`. It cannot
  recompute the `advise-v1` policy hash, so the appended line is gated by the instrument and revision
  binding (plus the Python cycle that sets the state), not by a policy-hash check in the hook.
- **Hosts.** Claude and Codex both honour `advise`. Codex records still stay out of the gate's reserve pool
  (`GATE_HOSTS`).

## Claude and Codex

Both hosts run the same router from the plugin's `hooks/hooks.json` (`skill-router.js --packaged`, appended as UserPromptSubmit entry 3) and share one registry state, binding and evidence store.

- **Opt-in.** The packaged router runs only when `~/.local/share/rhize/skill-router/config.json` is exactly `{"schemaVersion":1,"enabled":true}`. In Claude it also stays silent while `~/.claude/settings.json` (or `settings.local.json`, or the project's `.claude/` copies) still lists a manual `skill-router.js` hook. Remove that entry once the config is written; until then the router still runs exactly once. The check also looks in the `.claude/` folder of every parent of the session's directory. If your Claude version reads project settings from the session directory only, a manual entry in a parent project silences the packaged hook in subdirectory sessions until you remove it. Codex asks you to approve the appended hook in its native trust prompt.
- **Host.** Each record carries `host`. The order is: a valid `RHIZE_HOST`, then the `transcript_path` location (`~/.codex/sessions` or `archived_sessions` rollouts mean codex; `~/.claude/projects` means claude), then payload `thread_id` (codex) or `CLAUDE_CODE_ENTRYPOINT` (claude). Conflicting signals record `unknown`. No signal at all records `claude`, the legacy default.
- **Codex machine threads.** The router reads the first line of the rollout and runs only when `thread_source` is `user`. Guardian reviews, subagents, automations and agent-created threads produce no suggestion, no Laya call and no record. The Codex session identity is the rollout's `session_meta.id`, which is the same UUID the transcript index uses.
- **Authority.** Codex stays in `shadow` for `cosign` (`COSIGN_HOSTS = ['claude']`); `advise` is allowed on both hosts. The gate's reserve pool, live unavailability and demotion windows count only `GATE_HOSTS = ('claude',)`. Codex shadow evidence accumulates for a later Codex-stratified gate.
- **Outcomes.** Codex invocations come from read-shaped shell commands (`cat`, `sed -n`, `head`, `tail`, `nl`, `bat`, `less`) on a `SKILL.md` under a plugin cache or marketplace root, or under the user skill folders (`~/.agents/skills`, `~/.codex/skills`, `~/.claude/skills`). Current Codex rollouts are read through Codex's own parsed command (`item_completed` CommandExecution entries of type `read`), and only a command that exited 0 counts; in those rollouts the coexisting `function_call` lines are ignored. Older rollouts that record only the shell `function_call` carry no exit code, so there a read-shaped command counts on its shape alone. They are recorded as `via: skill_file_read`, a weaker evidence type than Claude's `Skill` tool call. Edits, `apply_patch`, grep, failed reads and `$skill` mentions never count.
- **Scoreboard.** Every count, arm, status, prevalence figure and outcome is reported per host.

## Keep-warm

After about 5 minutes idle, Laya's first answer took about 1.3 s, past the 800 ms hook budget; warm calls take 30–220 ms. `laya_keepwarm.py run` sends one fixed synthetic choice request, with no user data, every 90 s. It does this only while the hosts are active: the newest workflow-selection receipt, suggestion-log write or skill-fit record must be under 2 h old. It skips the ping while live traffic is already keeping Laya warm, which means a live skill-fit record whose Laya call answered `ok` in the last 60 s; backfill replays and skipped or failed calls never count as warm. After a failure it backs off to at most 120 s, and `run` exits 1 when its final state write fails, so launchd's `SuccessfulExit=false` restarts it. It never writes decision evidence. State lives in `<root>/laya-keepwarm.json`, which the scoreboard reports. `LAYA_KEEPWARM=0` disables it. Run it as its own launchd agent so the Laya server never needs restarting:

```xml
<key>Label</key><string>media.rhize.laya-keepwarm</string>
<key>ProgramArguments</key><array><string>/usr/bin/python3</string>
  <string>$HOME/.claude/plugins/marketplaces/rhize-plugins/rhize-context-manager/scripts/typed_decisions/laya_keepwarm.py</string><string>run</string></array>
<key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>
<key>ThrottleInterval</key><integer>60</integer>
```

(Use the absolute home path in a real plist. `SuccessfulExit=false` stops launchd from respawning the agent after `LAYA_KEEPWARM=0` makes it exit cleanly.)

## Learning feed and weekly improvement

- `harvest_signals.py emit --queue NEW_PRIVATE_FILE` writes `skill-fit-decisions` review candidates for `/learn-harvest`. It covers four kinds: not-shortlisted, suggested-but-ignored, cosign-suppressed-then-invoked and laya-timeouts, per skill and host, with at least 3 events in 14 days. Codex SKILL.md-read evidence gets its own candidates. It never writes the live queue, and its patterns are stable so the queue dedupes by id. See [learn-harvest](../../rhize-context-manager/commands/learn-harvest.md).
- `evals/skill-map-routing/real_traffic.py` (`freeze`, `evaluate`, `dev-report`) proves a router candidate on cases recorded after it was frozen. See [weekly improvement](weekly-improvement.md) for the keep rule and the weekly automation. Nothing in this loop pushes, merges or touches the gate.

## Testing without touching live evidence

A smoke test of the hook must set `RHIZE_TYPED_DECISIONS_ROOT`, `RHIZE_SUGGESTION_LOG` and `XDG_DATA_HOME` to temp paths. Otherwise the router's workflow bridge writes real workflow-pilot opportunities.

## Limits

- Labels are constrained to the shortlist. They support no claim about catalog-wide recall or about Laya recovering skills the router missed.
- The acceptance outcome (was the suggested skill invoked?) is confounded by the suggestion itself. It is reported as a secondary signal only.
- Codex transcripts are not yet joined for outcomes.

Failed native model calls expose bounded error-tag counts in the labeler summary. Only redacted failure receipts are archived under `skill-fit/labeling/failed/`; transient CLI homes and other temporary files are removed. Failed or unavailable annotations remain unlabelled.

The default loopback skill-fit client uses Node's direct HTTP transport, avoiding cold global-fetch initialization inside the 800 ms deadline. It retains identity-before-prompt, redirect refusal, capped responses, abort cleanup and proxy checks, and rechecks the monotonic deadline after decoding.
