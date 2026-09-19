# Paired opportunity and answer measurements

Every measurement-enabled task requests **A and B together**. A is `legacy-direct-v1`; B is
`awareness-selected-v1`, using `catalog-keyword-overlap-v1`. B ranks labels/keywords without seeing
rubrics or expected source IDs. No arm-only switch exists. Legacy context experiments also always
request both arms; their provider and evidence authorization gates remain in force.

## Enable and inspect

Use the skill's `scripts/memory-context.sh` launcher with these subcommands:

```bash
scripts/memory-context.sh opportunity-configure --workspace /absolute/workspace --answer-pairs-per-day 12
scripts/memory-context.sh opportunity-status
scripts/memory-context.sh opportunity-drain --limit 2
scripts/memory-context.sh opportunity-disable
```

Repeat `--workspace` for additional roots. Descendants are allowed, but only the active task's
`STATE.md`, `CLAUDE.md`, `AGENTS.md` and `README.md` are read, with a 64 KiB per-file cap and 40
bounded sections. No recursive scan, transcript ingestion, procedural execution, new index of
claude-mem/OpenWolf, or provider credential is involved. Secret-shaped inputs are skipped; this
heuristic does not constitute a general-purpose redactor. Configure only workspaces whose
canonical documents may be used with the host's existing subscription.

Configuration defaults disabled until explicitly written. Data defaults to
`~/.local/share/rhize/context-manager/memory-context/paired-opportunities-v1`, or the memory root
selected by `RHIZE_CONTEXT_HOME` / `XDG_DATA_HOME`. `--data-dir` selects a separate private store
for explicit commands. Hooks follow the environment-selected root. Never write to installed
plugin caches to configure this feature.

## Native events and activation

`hooks/hooks.json` appends the nonblocking Python supervisor to SessionStart, UserPromptSubmit,
PostToolUse and Stop. Claude uses `CLAUDE_PLUGIN_ROOT`; current Codex supplies compatible plugin
variables and its own `PLUGIN_ROOT`, which identifies the host. Native hook trust must be reviewed
through the host. Installation alone does not prove trust or execution. Older clients can pipe
the native event JSON into `opportunity-event --host claude|codex` explicitly.

SessionStart records the native model identity. Eligible prompts concern recall, prior context,
procedures, source verification or related work. Both retrieval paths run on a frozen source
snapshot; duplicate deliveries are suppressed. PostToolUse and Stop update task observations,
without inferring correctness. Codex turn IDs prevent late events updating a different turn.
Without a Claude turn ID, duplicate identical prompts within a session are conservatively deduped;
late-event attribution is best-effort and these observations are not paired outcome evidence.

Prompt/stop events start a detached, single-worker answer drain. Both answer arms use the same
question and explicit model in fresh temporary directories. Claude tools and MCP are disabled;
Codex uses read-only isolation with shell, web, apps, browser, memory and agent features disabled.
The children suppress measurement hooks. Subscription authentication is checked separately for
both arms, environment API keys are removed, and no paid fallback occurs. Native model completion,
structured answers, matching model identities and actual execution are required for a complete
answer pair. A failure or timeout still permits the other arm's attempt.

Default budget is 12 **whole answer pairs per host per UTC day**. Excess pairs defer together.
At most 100 private queue packets are retained; full-queue receipts say `deferred_queue_full`
and require a fresh opportunity. Pack bodies use temporary storage; queued questions/context are
private 0600 data and removed after processing. Queue expiry is one hour, cleaned lazily when a
worker next runs, including at an exhausted budget. Interrupted answer claims become incomplete
on the next drain; they are never converted to successful runs. Disabling stops new capture and
new pair starts; an already running pair finishes both arms. Status exposes queued and pending
retrieval pairs, configuration and per-host observed event health. No recurring poller is installed.

## Hook health and recovery

The four passive hook commands always allow the user task to continue. Their stdlib supervisor
is independent of the capture engine's imports. It bounds foreground execution below the host's
10-second limit, validates a small outcome protocol, discards raw child output and records a
categorical failure without prompt, tool, transcript, path or exception-body content. Warnings
contain only a fixed `systemMessage`, never a decision or continuation request.

`opportunity-status.hookHealth` separates runtime status from receipt completeness. If that runner
cannot import, use the standalone command from the installed plugin's root:

```bash
python3 scripts/memory_context/hook_runtime.py status
```

Statuses are `not_run`, `operational`, `degraded` or `unavailable`; this standalone command returns
1 for the latter two. Records include the CLI host (`claude`/`codex`), event or worker lane,
installation fingerprint, last outcome, sanitized failure category/count, timestamps and worker
launch identity. `disabled`, `ineligible`, `scope_denied`, `unavailable` source material and
`payload_too_large` are explicit non-capture outcomes, not complete measurements. An operational
runtime must still be evaluated against actual A/B receipts and their `actuallyRan` fields.

Private state uses 0700 directories, 0600 files, a 64 KiB document and at most 32 records. Old
installation records are evictable; current-install failures remain until recovery. Atomic incident
reporting deduplicates concurrent warnings. Each event/host/install has its own lane, so a shared
broken import can warn once for each of the four events. Changing error categories without recovery
does not repeat the warning. A repaired event clears its runtime failure; it does not backfill lost
measurements or clear a failed worker. A later recurrence warns again.

Detached workers hold an inherited launch lock, with all stdio disconnected from the host. Their
starting/running/completed/failed state is distinct from foreground capture. A released launch lock
with a persisted active worker marks `worker_died` on the next event/status inspection, including
abrupt termination. A held lock indicates a live worker regardless of age; status adds a `longRunning` advisory
after 900 seconds without claiming the worker is dead. There is no additional
supervisor timeout or automatic provider retry. Existing arm deadlines, queue reconciliation and
budgets remain authoritative. A busy drain does not resolve a prior failure. Worker failures appear
in standalone status immediately after recording and warn on the next native event; no poller is
installed. Worker completion means the drain ran, not that every answer pair succeeded.

A missing Python interpreter or reporter produces a static shell warning. Corrupt, unsafe or
unwritable diagnostic storage warns at SessionStart or on actual capture failure, without exposing
raw errors; successful tool events do not repeatedly warn. These cases cannot promise persistent
deduplication. Transient document-lock contention alone skips diagnostics quietly and
reports unavailable to a concurrent status check. If capture itself failed during contention, the
hook still emits a static warning. Native hook trust/reload is required after package updates;
packaged shell tests do not prove activation in an already-running host task.

## Interpretation and promotion

Retrieval and answer comparisons are separate. A/B retrieval metrics include catalog maintenance
time and catalog-plus-details byte/4 token estimates. Actual answer usage measures the native
model calls; B receives selected details, while deterministic local selection handles its catalog.
Do not describe this as an LLM choosing topics. Both arms' real CLI overhead is retained, including
Claude auxiliary-model usage. Missing usage is null, never zero. CLI list-price fields are not
subscription charges and are not reported as paid spend.

Natural receipts omit raw prompts, source bodies and source paths; private queue packets contain
the bounded question and evidence needed for actual execution. Natural answers have no automatic
correctness grade. Tool errors and successful Stop events do not measure task success. Curated
gauntlet rubrics score explicit answer terms and source citations, not whole-task correctness.

Reports stratify curated/natural evidence, host, model, source/implementation hashes and corpus.
Only complete pairs enter paired differences. Repeated snapshots do not inflate the independent
case count. Bootstrap intervals are descriptive for this small corpus; even an all-zero interval
cannot establish non-inferiority. Keep RTK/Headroom and other stack choices fixed within each pair.
No default catalog injection, procedural adapter, or promotion follows from a token-only win.
Use the prior research plan's held-out correctness and privacy gates before adoption.

## Evidence-quality revision

Model provenance is now explicit (`hook_event`, `session_transcript_last_assistant`,
`session_event_cache`, `unavailable`). Transcript fallback is restricted to the hook's matching
Claude session and a bounded tail; it never guesses from another session or a global model alias.
The last observed assistant model may precede a user model switch, so the provenance matters.
The answer worker always pins its own model and separately checks the returned identity.

Natural prompts are classified before queuing: candidate informational questions can reach the
answer probe; tool/action and unclassified requests retain local construction evidence but get
`ineligible_answer_task`. This heuristic is routing evidence, not proof of answerability.
Natural semantic quality stays ungraded unless an explicit reviewed task rubric is supplied by a
curated experiment. The common report retains both Claude and Codex rows and separates missing
model, queue, auth, grading and completed-pair counts.

Auth preflight is outside the shared receipt lock and before daily budget consumption. A failed
login check yields `deferred_auth`; it cannot become a zero-cost success, and it does not extend
the existing one-hour private-packet retention period. The next legitimate drain can retry auth.
Curated runs may explicitly retain blinded full-answer review packets; this does not change
passive retention. See the marketplace's `evals/memory-context/README.md` for the controlled runner.
