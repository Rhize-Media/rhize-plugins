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

`hooks/hooks.json` appends the silent Python entry point to SessionStart, UserPromptSubmit,
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
