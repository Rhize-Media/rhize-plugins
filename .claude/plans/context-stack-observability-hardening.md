# Context-stack observability hardening

**Status:** proposed, Jim-gated at the marked decision points
**Author:** Claude Opus 5 (1M), synthesized with an independent Codex (planning role) draft
**Date:** 2026-09-11
**Trigger:** `weekly-context-doctor` run 2026-09-10 (`~/.claude/context-manager/doctor/2026-09-10-1212.json`)

---

## The root defect

Not "Haiku ignored the routine's instructions." That framing is too narrow — a stronger
model fabricates continuity too, and this session proves it (see Exhibit A).

The real defect: **execution, evidence validation, and result reporting all depend on
model compliance, and nothing outside that chain notices when it breaks.** A routine can
report a confident headline while its probes never ran, ran against stale inputs, or were
summarized with invented arithmetic. There is no independent detector, because the only
thing that would have raised the alarm is the same component that failed.

Every finding below is a consequence of that one defect, except the claude-mem outage,
which is a genuine independent incident that the defect *hid for four days*.

### Exhibit A — why prose guardrails cannot be the control

The routine file already says, in plain language:

> "If `/context-doctor` itself errors, report the error plainly — don't fabricate a
> 'no drift' line."
> "Don't re-derive the delta from raw layer statuses — trust the command's own Step 3 diff."

With those instructions in context, the executor still: invented a `claude context-doctor`
CLI that does not exist; concluded from its failure that the routine was un-runnable; and
handed back the 7-day-old baseline formatted as this week's result.

Then, on the corrected retry, four integers from `observer-health.json` were summarized
three separate times by three different LLM passes:

| Pass | Claim | Reality |
|---|---|---|
| Executor (Haiku) | "DOWN for 43+ hours" | wrong |
| Me (Opus), correcting it | "~22 hours continuous failure" | also wrong — misread `lastErrorAt` by 20h |
| claude-mem's own session banner | "about 22 hours" | misleading — errors had stopped 2h in |
| `python3` over the raw epoch-ms | see Workstream A | correct |

The independent Codex reviewer caught it. No amount of additional prose would have.
**Arithmetic over evidence must not be performed by a language model.**

---

## Workstream A — claude-mem: active incident (P0)

### What the evidence actually says

Script-computed from `~/.claude-mem/observer-health.json`, verified 2026-09-11T14:11Z:

```
lastSuccessAt   2026-09-07T12:54:07Z
                  ↓ 49.5 h — neither success nor error recorded
failingSinceAt  2026-09-09T14:21:40Z
                  ↓ 2.05 h — 51 consecutive failures, all in this burst
lastErrorAt     2026-09-09T16:24:37Z
                  ↓ 45.8 h — TOTAL SILENCE, no errors and no successes
now             2026-09-11T14:11Z
```

Capture has produced nothing for **97.3 hours**. The health file has not been written in
45.8 h. Error: `NOT NULL constraint failed: session_summaries.memory_session_id`
(upstream #3609). Installed version is **13.24.20**; the 09-03 baseline ran 13.18.1 — so
the bug **recurred across an upgrade**, and the 08-27 "fixed by upgrading" resolution
did not hold.

**This is not a service that is retrying and failing. It stopped emitting.** The
distinction matters: "continuously failing" implies a live loop hitting a constraint,
which would suggest DB repair. Silence after a short burst suggests the writer died, or
a supervisor stopped restarting it. Those have different fixes.

### Decision rule — do NOT rebuild first

279 MB is not evidence of corruption, and the `-wal` being written today is not evidence
of successful capture. Gather evidence in this order, and stop as soon as it discriminates:

1. **Back up before touching anything** — a consistent SQLite backup including
   outstanding WAL (`.backup`, not `cp`; `cp` of a hot DB with a live WAL is not a backup).
2. **Separate the three hypotheses.** They look identical from the health file alone:
   - capture stopped (hook never fires) → check hook wiring + session-start invocation
   - worker stopped (process gone / not restarted) → check process table + supervisor
   - health reporting stopped (worker alive, telemetry broken) → check worker logs
3. **Running version vs installed version** — confirm what is actually executing, not
   what npm says is installed.
4. **Schema/migration state** + `PRAGMA integrity_check` against the *backup copy*.
5. **Upstream #3609 state** — check `stateReason` and release notes before treating any
   version as a remedy. A closed issue is not a fixed issue; that mistake is already on
   record here.
6. **End-to-end canary**: one controlled session whose expected observation is traced
   through persistence *and* retrieval. This is the only test that proves capture works.

**Then choose:** repair if a documented fix matches the reproduced failure (validate on
the backup, then canary). Pin/downgrade only with evidence of a working version **and**
schema compatibility — the recurrence across 13.18.1 → 13.24.20 means "upgrade again" is
not a plan. Rebuild only on demonstrated unrecoverable damage, retaining the original.

**Recommendation (Jim-gated):** treat claude-mem as **supplemental, not authoritative**,
independent of which repair lands. Four days of silent loss with no alert means explicit
project state (`STATE.md`, plans, commits) must remain the durable source of truth. That
is a posture change, not a repair, and it should hold even after capture is restored.

---

## Workstream B — routine output contract (P0, the structural fix)

This is the load-bearing workstream. It is what makes every future A/C/D finding
*discoverable* instead of silently absorbed.

### B1. Three outcomes per probe, enforced by a validator

| Outcome | Required evidence | Meaning |
|---|---|---|
| `OK` | current, completed, schema-valid measurement | check passed |
| `PROBLEM` | current, completed, schema-valid measurement | check found a defect |
| `NOT_RUN` | reason code + any partial evidence | **no valid determination was made** |

`NOT_RUN` reason codes cover: launch failure, missing executable, blocked credential,
timeout, malformed output, deliberate skip. Yesterday's run had *two* silent `NOT_RUN`s
(Keychain lookahead → "unknown"; `ecc:harness-audit` → skipped) sitting inside a report
with a confident headline. Under this contract they become visible coverage gaps.

**"Healthy" requires every mandatory probe to return `OK`.** Mandatory-vs-optional is
declared in config *before* execution, never inferred after. And the two findings do not
collapse into one severity — `"Problems detected; coverage incomplete"` is a legal and
more useful headline than either alone.

### B2. Provenance — a prior report can never satisfy a current probe

Every invocation gets a run ID. Every piece of evidence carries: run ID, probe ID,
config/schema version, observation time. This is the specific control that would have
stopped the executor handing back the 09-03 baseline as this week's answer — not because
it was told not to, but because the baseline's run ID would not match the current run.

A recent file on disk is not proof of execution.

### B3. Split the runner from the interpreter

Per the repo convention already in force — *"Executable logic lives in scripts. Never
embed multi-step bash/python pipelines as prose inside SKILL.md or scheduled-task
prompts — they rot silently."*

**Script owns** (versioned, tested, called by path): dependency resolution, probe
execution with deadlines, exit-code/timestamp/error capture, output schema validation,
coverage check, **all arithmetic and all baseline comparison**, atomic persistence,
authoritative report rendering.

**Model owns**: diagnosis, prioritization, suggested remediation, the judgment call on
what deserves a human's attention. Clearly labeled as commentary.

**The model has no authority** to set the health headline, suppress a mandatory failure,
or substitute narrative for the runner's result. The drift-only gate in Step 3 of the
current routine is precisely a status comparison — it belongs in the script.

This is an instance of an already-approved principle, not a new invention:
`~/.claude/skills/learned/control-runs-must-verify-their-own-mutation.md` ("make 'probe
broken' a third outcome") and `find-programmatic-path-before-manual.md`.

### B4. External watchdog — a dead process cannot report its own death

The runner cannot be the thing that detects the runner did not run. A separate check
alerts on **missed completion** and **overdue evidence** (no run artifact newer than
N days for a routine scheduled weekly). Must not share a failure domain with the runner.

Note what the current arrangement actually depended on: a human happening to read a
session-start banner. That is not monitoring.

### B5. Acceptance tests = deliberate failure injection

The contract is only real if these are tested. Inject, and assert the result is
`NOT_RUN`/incomplete-coverage/missed-run — never a clean headline:
auth failure · missing executable · malformed probe output · timeout · stale artifact
presented as current · runner killed mid-run.

Run them on a schedule, not once. An untested failure path is an assumption.

---

## Workstream C — PATH / bootstrap hardening (P1)

Third documented occurrence (09-07, 09-09, 09-10). Self-healed today via app restart, so
there is nothing to fix *right now* — which is exactly why it keeps coming back.

Two distinct problems, often conflated:

- **Scheduled routines must not depend on ambient PATH at all.** The wrapper already
  exists: `~/dev-local/claude-routines/scheduled/with-node.sh <cmd>` — prepends the shims
  in its own child and exits 3 rather than silently falling back to bunx/Homebrew node.
  Audit every scheduled entry point for use of it; the ones that skip it are the ones
  that will fail silently. This is a bounded, mechanical task.
- **The desktop app's launch environment is separate** and cannot be fixed from inside a
  running instance. A correct `~/.zshenv` does not repair a live process. The runner's
  bootstrap should therefore *detect and refuse* rather than degrade: explicit runtime
  resolution, prerequisite check, `NOT_RUN` with reason `missing_executable` on failure.

Under Workstream B this class stops being invisible: 8 ENOENT MCP servers plus a missing
`codegraph` CLI would have surfaced as failed mandatory probes, not as a footnote.

---

## Workstream D — scheduler registry consolidation (P2, deferred)

Three locations, none authoritative:

- `~/.claude/scheduled-tasks/` — 12 dirs
- `~/Documents/Claude/Scheduled/` — 12 dirs, **overlapping but not identical**
  (only-in-first: `codex-trial-decision-review`, `scheduler-registry-consolidation`,
  `seo-remediation-consumer`; only-in-second: `daily-completed-summary`,
  `monthly-seo-update`, `vault-inbox-processor`, `rhize-dashboard-snapshot-refresh`)
- `~/dev-local/claude-routines/scheduled/definitions/` — only 2

`weekly-context-doctor`'s `~/.claude` copy is a shim pointing at the `Documents` copy as
"the source of truth". A prior consolidation was recorded as complete; it is not.

Codex argued this is lower priority than I initially ranked it, and that is right — the
defect is *unclear ownership and unverifiable synchronization*, not directory count.
Multiple dirs are legitimate if one is generated from another and drift is detectable.
Target: one versioned registry, generated deployment copies, and a check that detects
missing / extra / mismatched registrations. A `scheduler-registry-consolidation` task
already exists — fold this into it rather than opening a second effort.

---

## Sequencing

1. **A1–A2 now** — back up claude-mem, discriminate the three hypotheses. Cheap, and it
   is an active four-day data-loss incident.
2. **B1–B3 next** — contract + runner script for `weekly-context-doctor` as the pilot.
   One routine, end to end, before generalizing.
3. **B4–B5** — watchdog and failure injection. Without these B is just a nicer report.
4. **C** — mechanical wrapper audit; can run in parallel, no dependency on B.
5. **D** — folded into the existing consolidation task.

Generalize the B contract to the other routines only after the pilot survives its own
injected failures.

## Jim-gated decisions

- **Workstream A repair path** — repair / pin / rebuild, decided by the A1–A6 evidence,
  not in advance. Recommendation above: demote claude-mem to supplemental regardless.
- **Alert channel and threshold for B4** — where a missed run pages, and how loudly.
  Getting this wrong produces alert fatigue, which is the failure mode that kills
  watchdogs.
- **Scope of B** — pilot on this one routine, or contract-first across all 12.
  Recommend the pilot.

## How this plan rots

Stated deliberately, because the thing it replaces rotted the same way — it was also
well-written and also unenforced.

- **Wrong probes.** A probe that measures the wrong thing passes confidently forever.
  Only the end-to-end canary (A6) defends against this; schema validation does not.
- **Shared failure domain.** If the watchdog runs on the same host, under the same
  scheduler, with the same PATH assumptions, it dies with the thing it watches.
- **Permanently-optional probes.** `harness-audit` marked optional "for now" becomes
  optional forever, and coverage silently shrinks back to today's state. Optional needs
  an owner and an expiry.
- **Alert fatigue.** A noisy watchdog gets muted, and muted is indistinguishable from
  the current state.
- **Ignored schema changes.** When the runner's output schema drifts and the validator is
  relaxed to make the red go away, the contract is gone.

Counters: named ownership per probe, periodic failure injection (B5) rather than one-time,
the capture canary, and alerts on missed runs and stale evidence — not just on bad results.
