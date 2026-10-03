# Workflow decision measurement pilot

This opt-in pilot measures whether a task should consult the content workflow family,
a general executable workflow family, or neither. Arm A is the existing authoritative task
path. Arm B records a local Laya recommendation only. Neither the score nor the context
assertion grants execution, publishing, credential, deployment or approval authority.

Two cohorts remain separate. Legacy v1 uses eleven allowlisted prompt tokens; that input can
miss negation and conversation context. V2 uses an explicit bounded task envelope sealed
before consultation or selection. Historical v1 records, comparisons and experiments are not
rewritten as v2 evidence. A successful Arm A task is not an Arm B productivity result.

## Activate and verify

Merge `"decisionPilot":{"enabled":true,"mode":"shadow","cohort":"v2"}` into the existing
private workflow-selection config alongside `"schemaVersion":1,"enabled":true`. Preserve the
procedural launcher and other settings. Omitting `cohort` retains v1 behavior; upgrading source
alone does not switch cohorts. Set the pilot's `enabled` false to stop new pilot capture.
Existing pending observations remain available for explicit drain. Do not also set the older
`RHIZE_LAYA_WORKFLOW_SHADOW` flag; the configured pilot takes precedence.

The existing UserPromptSubmit hook first writes an opportunity. In v2 it seals a redacted
request snapshot before instructing the task agent to record enum context before recall,
consultation or `decide`. Only eligible sealed context
starts detached scoring. Missing context does not block the authoritative task; it remains a
visible missing measurement. V1 continues enqueuing its original token-based observation.

Workers serialize on a nonblocking lock, process at most 20 pending observations within a
45-second batch plus at most one bounded request, and disconnect host pipes. Duplicate delivery
cannot replace the first observation/result. Failed inference is retained without automatic
retry. Changed collection source holds pending work rather than reconstructing old questions.

Run a pinned Laya `typed-decisions` checkpoint at `http://127.0.0.1:8000`. Manage startup using
the host's existing service mechanism; verify package version, checkpoint files and a real
synthetic request, not merely a listening port. Keep downloads offline after provisioning.
The worker validates the returned checkpoint and usage. Source digests identify client code;
server checkpoint-file identity must also be retained in the local deployment evidence.

Install/update the plugin through each host's normal lifecycle. Review changed hooks through
its native trust UI; never hand-edit approval hashes. Start a fresh task after cache updates.
A source release does not prove an already-running task loaded it. Verify both hosts using
actual native tasks and private receipts. Synthetic hook payloads establish contract behavior
only. The optional Stop hook records exact native host/session/turn matches; hosts without
that identity record an unavailable diagnostic rather than attaching to the latest task.
Stop never means passed checks or accepted work.

## V2 task lifecycle

From the plugin directory, record the actual request as enum metadata before consulting a
workflow. For example, an authorized implementation request can use:

```sh
python3 scripts/workflow_selection.py context --id OPPORTUNITY_ID \
  --event-kind new_task --action implement --domain software --exclude deployment
```

Choose fields from the user's full request; the example is not a default classification.
`event-kind` supports `new_task`, `changed_intent`, `continuation`, `status`, `approval`,
`context_update`, `background_observer`, `summarizer`, `tool_callback`, `worker_handback`,
`scheduled`, and `unknown`. Only `new_task` and `changed_intent` with valid known action/domain
are independent routing decisions. Actions are `create`, `revise`, `investigate`, `implement`,
`review`, `validate`, `research`, `explain`, `handoff`, or `unknown`; domains are `content`,
`software`, `operations`, `general`, or `unknown`. Repeat `--exclude` for `content_creation`,
`publishing`, `deployment`, or `external_messages` when the request explicitly excludes them.
The content-creation exclusion masks the content candidate in the shared decoder; all authority
still belongs to the existing deterministic workflow rules.

A continuation uses `--event-kind continuation --parent-id EARLIER_OPPORTUNITY_ID`, with the
parent's action/domain. It must reference an earlier v2 opportunity in the same session.
Only continuations accept a parent ID; `changed_intent` starts a fresh task root. Ancestry is
bounded to 32 levels; missing, cyclic, incompatible or historical v1 ancestry holds. A held
ancestor also invalidates its inherited evidence.
Continuation inherits the parent's shadow recommendation without fresh inference. Parent Arm A
consultation and execution evidence never enter the model input. Record a genuinely changed
request as `changed_intent`, rather than disguising it as an unchanged continuation.

Scheduled/prebound work can record `--prebound-family content|general`; it follows its existing
runbook and is excluded from new routing decisions. Callbacks, observers, summaries, status and
approval updates also remain operational events. Fresh ECC observers are classified only when
the existing launcher flags, dedicated canonical working directory, native session and transcript
identity, and exact request hash all agree. Classification remains `agent_asserted`, with
`nativeOrigin: unknown`; this bounded launcher check is not verified human-origin attestation.
Prompt tags cannot become trusted host metadata. Unknown context remains unknown.

`context --evidence PRIVATE_JSON` is an alternative to enum flags, not an additional input.
It requires the closed `rhize-workflow-task-context-v2` schema and exact opportunity, prompt and
session bindings. It accepts no free-text field. Identical retries are idempotent. Conflicting,
late or mismatched context leaves a durable hold and does not overwrite the first assertion.
A context recorded after consultation or selection cannot produce a fresh shadow score.
A missing evidence file or temporary storage I/O error leaves a source-bound diagnostic without
holding otherwise valid context, so it can be corrected before Arm A consultation/selection.
Malformed, late or conflicting assertions do hold. `request_seal_failed` is a permanent hold
for that opportunity: preserve the failed attempt and wait for a genuinely new opportunity;
do not retry or relabel history to repair the measurement.

Next, actually consult the appropriate procedure and preserve its result privately, then record:

```sh
python3 scripts/workflow_selection.py consult --id OPPORTUNITY_ID \
  --family general --evidence PRIVATE_RECALL_RESULT
python3 scripts/workflow_selection.py decide --id OPPORTUNITY_ID \
  --decision no_match --reason no_suitable_workflow
```

This example truthfully records a general-family consultation followed by no catalog match.
V2 Arm A remains `general`; `no_match` describes the catalog result, not the consultation.
Use `none` only for an actual decision not to consult either family, supported by its private
rationale. Consultation is immutable, operator-reported evidence and must precede `decide`.
The file digest proves binding, not that the asserted consultation happened. Existing execution,
validation and capture commands continue recording their real workflow/run evidence separately.
Neither consultation nor stage receipts are human correctness labels.

## Source-bound request context and capture errors

Fresh v2 native hooks write immutable `request-snapshots/ID.json` sidecars beside `receipts`.
Requests are redacted before persistence, limited to the existing request budget, and bound to
opportunity, prompt, session, selector and source receipt hashes. Directories are private (0700),
files 0600. First capture must precede enum context, consultation and decision; retries preserve
that first snapshot. No historical prompt is reconstructed into a new capture. Hashes detect
binding changes but are not cryptographic origin attestations.

For a short changed request whose meaning depends on an earlier user request, explicitly link it:

```sh
python3 scripts/workflow_selection.py context --id OPPORTUNITY_ID \
  --event-kind changed_intent --action implement --domain software \
  --context-id EARLIER_OPPORTUNITY_ID
```

Repeat `--context-id` at most four times. Each link requires an earlier sealed request and valid
context in the same native session; it creates a separate immutable request-context sidecar.
These links supply labeling context, not continuation inheritance. Assistant plans and routing
results are never copied into label input. A request such as “proceed” without verifiable material
user context can still require abstention; adding a link does not prove adequate context.

The labeler independently verifies native transcript identity, request hash, timestamps and
redacted content before using snapshots. Native hosts may publish the matching user turn after the pre-decision hook snapshot. Publication lag is allowed only within the existing 60-second window around the hook observation; exact native session, raw request hash and redacted content must still match. Snapshot creation must still precede context and decision artifacts. Missing snapshots retain the existing user-only
transcript fallback and earliest-pilot cutoff. Present but invalid snapshots never silently fall
back. Private provenance records the source references and context hashes; exposure stays unknown,
not claimed blind. Symlink, FIFO, oversized and unavailable sources defer with bounded error codes.

Capture errors are fail-open for Arm A and fail-closed for unverified label context. Private
capture diagnostics distinguish observer-source verification, missing enum context, storage and
binding failures. Label summaries distinguish missing/ambiguous context from I/O, binding and late
snapshot faults; actionable faults also appear as warnings. Diagnostics contain codes and hashes,
not request text. Keep failed and interrupted runs for investigation; retention removes only
successful completed runs. Snapshot retention is an explicit private operator policy, never an
implicit public export or automatic retroactive repair.

`report.v2Coverage.collectionFunnel` separates raw events from independent eligible task roots,
missing context from source-change holds, and Claude/Codex/unknown hosts. Arm A/B variant fields
and measured-check denominators remain explicit. `pilot_labels.py report.byCollectionSource`
counts recorded policy-accepted and explicitly judged labels by originating digest. Those counts
are label coverage, not current-source export readiness. Preserve reviewed old runtime pins to
report/research their exact historical cohort; do not pool historical/current exports to meet
the 200-label floor. A local daily operator may alternate frozen historical/current runtimes
under one existing schedule, lock and deadline while preserving unsuccessful run artifacts.

## Measure normal checks once

Wrap a check at its normal invocation boundary; do not rerun completed work just to collect a
measurement. For example, when the task actually calls for a test command:

```sh
python3 scripts/decision_measure.py --id OPPORTUNITY_ID --timeout 300 -- \
  python3 -m pytest /absolute/path/to/relevant/tests -q
```

The wrapper executes the supplied argv without a shell, forwards check output best-effort
without blocking the child, and returns the child status even if measurement capture fails.
It hashes all child output it reads and reports `forwardTruncated` when caller backpressure
prevents forwarding everything. The timeout defaults to 300
seconds and is bounded to 900; timeout, interruption, launch failure and nonzero exit remain
visible. It records duration, return status and output digests as `automatic_artifact`, bound
to source/session/task root where available, with `executedVariant: A_incumbent`.
Missing or changed context yields an unbound/held measurement without preventing the requested
check. The receipt stores no raw command, output, path or credentials. Output shown by the
check itself remains ordinary task output. It creates no acceptance, quality score, token count
or independent review. Existing Dev Flow, Content Engine and Ops checks can use this wrapper
where the agent explicitly invokes their normal checks; it does not instrument every host tool.

## Operator commands

Run `python3 scripts/decision_pilot.py` from the Context Manager plugin:

- `report`: original v1 counters plus `totalRawEvents`, separate `v2Coverage` and `dailyPacket`.
  V2 raw opportunities reconcile into eligible, excluded, held, unknown and missing buckets;
  task outcomes, measured checks, usage missingness and evidence bases remain separate.
- `queue`: the original v1 `items` list plus a separate v2 `dailyPacket`. The packet contains
  at most 10 deterministic representatives across disagreement, abstention, agreement, pending
  baseline, context hold and pending score groups. Duplicate counts and full opportunity IDs
  preserve provenance; omitted groups stay visible. Excluded operational events do not become
  new routing-label requests. This assistant triage is not a random population accuracy sample
  or human adjudication. Inspect original task context before labeling.
- `drain`: process pending work; `--cohort v1|v2` selects an explicit cohort when needed.
- `adjudicate --id ID --evidence PRIVATE_JSON`: import an actual human-reviewed label.
  New labels using the richer taxonomy go through `pilot_labels.py` instead (see below).
- `outcome --id ID --evidence PRIVATE_JSON`: attach measured task results, including failures.
- `export --out NEW_PRIVATE_JSONL --cohort v2`: export eligible, bound human-labeled v2 cases;
  never overwrite. Omitting `--cohort` exports the historical v1 contract.

The default storage is `$XDG_DATA_HOME/rhize/workflow-selection/pilot`, or
`~/.local/share/rhize/workflow-selection/pilot`. `--root` and `--receipts` support isolated
fixtures and explicit storage. Reports fail explicitly on malformed records or inventories
over 10,000 files. Historical workflow receipts without the pilot marker are excluded. Missing
observation files still count against the opportunity denominator. Enum-only scoring records
capture no raw prompts, code, paths, customer text or transcripts. Fresh request snapshots contain
bounded, redacted user text and private transcript references outside Git and model-scoring input.
Host/session/task identities are hashes; these attest binding, not human origin. V2
observations/results/labels/outcomes/measurements live below `pilot/v2`; context and consultation
sidecars live alongside the workflow `receipts` directory. Old v1 records remain in place.

Each evidence document includes the exact `opportunityId` and collection `sourceSha256` from
`pilot/observations/ID.json` for v1 or `pilot/v2/observations/ID.json` for v2. All remaining
keys are required; unknown values are JSON null. The import validates the current source/context
binding; only eligible v2 decisions can receive routing labels.

Human label fields:

```json
{"opportunityId":"<64 hex>","sourceSha256":"<64 hex>","choice":"general","reviewer":"human-reviewer-id","basis":"human_adjudicated","stratum":"ordinary","reviewEvidenceSha256":"<64 hex>"}
```

`choice` is `content`, `general` or `none`: adjudicate the consultation-family question,
not whether a catalog match existed. `stratum` is `ordinary`, `critical_safety` or
`critical_authorization`. A model may propose a label in a separate review artifact but cannot
mark it human-adjudicated. Preserve the original human review evidence privately. Record hashes
bind evidence; they do not attest its truth. Labels are immutable; corrections require a reviewed
new cohort rather than silently changing the answer key.

Evidence bases remain distinct: context is `agent_asserted`; consultation and task outcomes
are operator-reported; measured checks are `automatic_artifact`; labels require explicit
`human_adjudicated` evidence imported through `adjudicate`. Reading or approving an assistant
review packet does not silently create labels.

Task outcome fields:

```json
{"opportunityId":"<64 hex>","sourceSha256":"<64 hex>","outcome":"undetermined","qualityScore":null,"checksPassed":null,"reviewPassed":null,"criticalFailureCount":null,"reworkCount":null,"wallMs":null,"usage":{"input_tokens":null,"output_tokens":null},"rubricSha256":null}
```

`outcome` is `accepted`, `rejected` or `undetermined`. Accepted requires a quality score 0–100,
passed required checks, passed independent review, zero critical failures and the frozen rubric
digest. A cold self-review alone is not independent review. Usage and wall time must come from
actual host measurements; do not infer them from local Laya tokens, receipt counts or task text.
The task agent records the outcome at completion. This operator-reported evidence is separate
from workflow-selection execution/validation/capture stages; do not invent a workflow run to
complete an outcome. Unfinished tasks and missing host usage remain visible.

## Versioned taxonomy labels

`scripts/pilot_labels.py` imports labels that use the richer workflow taxonomy
(`rhize-workflow-taxonomy-v1`): one `family` (feature_delivery, defect_resolution, code_health,
platform_operations, content_growth, research_analysis, knowledge_management, coordination,
direct_response), one immediate `phase` (triage, research, plan_design, implement, review,
validate, release_operate, not_applicable), the affected `areas` (or sole `not_applicable`), a
risk `stratum` (routine, elevated, critical) with optional `riskFlags`, and the routing `choice`
(content, general, none). The module sits outside the collection source digest, so releasing it
does not strand live observations, and it stores records under `pilot/v2/taxonomy-labels`, never in
the legacy human label store. Labels bind the current source and an eligible v2 decision, are
immutable except for the supersession rule below, and re-importing an identical record is
idempotent. The category and routing-choice definitions live in
[workflow-taxonomy.md](workflow-taxonomy.md).

```json
{"schema":"rhize-workflow-taxonomy-label-v1","opportunityId":"<64 hex>","sourceSha256":"<64 hex>","taxonomyVersion":"rhize-workflow-taxonomy-v1","basis":"ai_model_reviewed","family":"feature_delivery","phase":"implement","areas":["backend_api"],"stratum":"routine","riskFlags":[],"choice":"general","choiceBasis":"explicit","reviewer":"ai-review-claude-fable-5-1","reviewEvidenceSha256":"<64 hex>"}
```

`basis` is `human_adjudicated` or `ai_model_reviewed`. AI labels are never recorded as human.
`choiceBasis` is `explicit` when someone judged the route directly, or `derived:family-map-v1`
when it was filled from the family (content_growth→content, direct_response→none, otherwise
general). Research scores the route itself, so it uses only explicit choices; a family does not
decide the route (a small feature fix can correctly need no workflow). Derived choices still count
in coverage reports. The [daily AI labeler](#daily-ai-labeling) judges the choice directly.

**Supersession.** A stored label is replaced only through an explicit opt-in (`--supersede`,
`import_batch(..., supersede=True)`) and only in two cases: an AI label whose choice was merely
derived may be replaced by a label (AI or human) with an explicit choice, and any AI label may be
replaced by a human label. A human label is never replaced, and an AI label whose choice was
already judged directly stays as it is. The replaced record is moved, never deleted, to
`pilot/v2/taxonomy-labels-superseded/<opportunityId>-<16 hex of its evidence digest>.json` with a
`supersededBy` summary, the reason (`derived_to_explicit_choice` or `ai_to_human`) and a timestamp.
The archive is written as `pending` and marked `committed` only after the replacement is stored, so
a crash between the two steps never counts as a supersession; a retry re-validates a pending archive
against the replacement being applied, and the next import commits one whose replacement is already
stored. Only committed archives are counted. Loading, reporting and export read only the live label
directory, so a superseded label can never be scored. Without the opt-in an import of a different label still fails with
`immutable label already exists`.

Commands, run from the plugin directory:

- `pilot_labels.py import --id ID --evidence PRIVATE_JSON [--supersede]` — one label.
- `pilot_labels.py import-batch --annotations FILE [--dry-run] [--supersede]` — convert a reviewed
  `rhize-ai-taxonomy-annotations-v1` batch. Only `labeled` records whose model review actually ran
  with an `accept` or `revise` verdict, and that bind an eligible current-source v2 decision,
  are imported; every skip is counted by reason. `--dry-run --supersede` reports
  `would_supersede` for each replacement without writing.
- `pilot_labels.py policy show` / `policy set [--accept-ai] --reason TEXT --actor ID` — the private
  label policy. The default accepts only human labels. `--accept-ai` lets research use
  model-reviewed labels too; running `set` without it restores human-only. Each change is
  appended to `label-policy-history.jsonl` with the previous and next policy.
- `pilot_labels.py report` — counts by basis, family, phase, stratum, choice and choice basis,
  the research-usable count, the number of superseded labels and the coverage gates below.
- `pilot_labels.py export --out NEW_PRIVATE_JSONL` — research rows under the current policy.

A model-reviewed label is a model judgment, not human ground truth. Any research result that uses
one says so (`labelBasis`, `claimScope`) and supports no human-accuracy, holdout or promotion claim.

### Daily AI labeling

`scripts/pilot_autolabel.py` produces explicit-choice AI labels on a schedule, so research has
labels that judge the routing choice itself. It sits outside the collection source digest, like
`pilot_labels.py`, and never touches the legacy human label store or any research gate.

```bash
python3 scripts/pilot_autolabel.py run --no-import      # inspect first: writes only the private run directory
python3 scripts/pilot_autolabel.py run                  # daily: label, then import with supersession
python3 scripts/pilot_autolabel.py run --prepare-only   # select cases and write packets; no model call
python3 scripts/pilot_autolabel.py import-run <runDir>  # import a saved run (after --no-import, a failed import or a signal)
python3 scripts/pilot_autolabel.py status               # latest daily run summary
```

Each pass:

1. **Select** eligible, current-source v2 decisions that have no explicit-choice label, no human
   taxonomy label and no legacy human label, oldest first, up to `--max-cases` (default 15).
2. **Recover context** from local transcripts (`~/.claude/projects`, `~/.codex/sessions`,
   `~/.codex/archived_sessions`, or `--transcript-root`). A transcript matches only when the SHA-256
   of its session UUID equals the receipt's `sessionHash` and the SHA-256 of a user message equals
   its `promptHash`. A packet holds the redacted request (6,500 characters at most) and at most
   four preceding turns. Only turns the user typed are context: assistant prose (where agents
   restate pilot results), sub-agent (`isSidechain`) and compact-summary records, and injected
   boilerplate anywhere in a turn are skipped, and a user turn that talks about the pilot's own
   arms, scores, consultations or labels is dropped whole. That word filter is only a second layer.
   The structural rule is a time boundary: a turn is context only if it was typed strictly before
   both the opportunity's prompt and the session's first pilot artifact (the earliest receipt
   `observedAt`, observation `createdAt` or result `at` of that session), because from then on pilot
   output could have been surfaced and restated. A session whose boundary cannot be established (a
   receipt without a usable timestamp), a prompt record without a timestamp, or a turn without a
   timestamp yields no preceding context (for the turn: that turn is left out). Missing or
   ambiguous context becomes `insufficient_context` with no model call.

   **Redaction** covers the whole message before any truncation (a partial token at the cut is
   trimmed; a message over 200,000 characters is first cut at a token edge). Matching runs on a
   normalized view (NFKC, zero-width and format characters dropped, Unicode whitespace as a
   space, look-alike Cyrillic and Greek letters as Latin, `\uXXXX` and `\xNN` escapes decoded,
   bounded), and the replacement lands on the original span, so obfuscated keys and split tokens do
   not survive. It covers private keys, API and access token families (Anthropic, OpenAI, GitHub,
   GitLab, Slack incl. webhooks, Supabase, Google, npm, Vercel, Sanity, Resend, Stripe, Shopify,
   DigitalOcean, Hugging Face, Notion, AWS, JWTs), hex runs of 64 or more, `Authorization`,
   `Bearer` and `Basic` credentials, URL credentials (a password may contain `@`) and secret query
   parameters, webhook path secrets, `sshpass -p`, `curl -u user:pw`, `mysql -p<pw>`, credential
   flags, e-mail addresses, phone numbers, long numbers, CRM ids, unbroken 32-plus character
   key-like runs and longer random-looking base64 runs. Any line whose key name carries a
   credential word (`"password": "x"`, `api key: x`, `service role key: x`, `SUPABASE_SERVICE_ROLE_KEY=`,
   `pw:`, `pin:`, `session:`) is redacted whole, together with a value written on the following
   lines (JSON, YAML, YAML block scalars), and so is natural language such as `the password is x`.
   Long credential words match inside names (`PGPASSWORD`, `dbPassword`, `GITHUBTOKEN`, `_authToken`), short ones
   need a left edge or a camelCase boundary (`userAuth`), and `npm config set <key> <value>` is covered. A word that
   sits where the value would be (`{"name":"DB_PASSWORD","value":..}`, `<password>..`, a table header, `ENV SECRET v`,
   netrc `password v`, `Set X to v`) takes its line and the value line below it, and a value below its key inside
   `[..]`/`{..}` (string-aware, also one the key line itself opens) or a YAML list or block (any header:
   `|2`, `>2-`, `!!binary |`, `&a |`, `| # c`) is redacted to its end, k8s `name:` / `valueFrom:` / `value:` included.
   `pwd=`, `DB_PWD=` and the arrow `→` are covered while the bare `pwd` command is not; `pass is v` counts only with a
   credential context (`my`/`your`/`our` pass, an admin/root/db/user/login/wifi/account pass) or as a bare statement ending
   in one token (`pass is v`), so `the first pass is done` and `lint pass was clean` stay; npm/pnpm/yarn/bun
   `set`/`c set`/`config set` (flags and flag values such as `--location=user`, `-L user`, `--global=true`
   allowed) and `--otp` are covered. Every bound fails closed: a container still open at
   50 lines or 4K characters (counted from where it started), a YAML block open at the cap, or more than 20,000
   escapes redacts the rest of the message. Base64 runs are judged by entropy, so one with no digit is caught, unless the run is a path or URL path made of
identifier-like segments with no `+` or `=`. That path check is a linear character scanner, not a regex (the first
regex for it backtracked exponentially: `docs/archive/error-lifecycle-management-ARCHITECTURE-PROPOSAL` took about half a
second to sanitize and longer names never finished). A segment is lower case and Capitalized words, digits, `_`/`-` and
ALLCAPS words (after a separator, at the start or as the trailing word: `SKILL-context-hygiene-v1`, `marketA`, `workerV2`,
`PanelUI`); a capital glued inside a lower case run that is not a hump (`aGVs`), or a long segment whose words average
under three letters, is not a path. Random base64 with a `/` still redacts; residual: roughly one random blob in twenty
thousand happens to parse as words and is left to the other rules. Only the head of a message is ever kept.
   Every quantifier is bounded (two anchored whitespace runs aside), every scan is linear, and a test runs every module-level regex over adversarial
5,000-character strings against a time limit. It is defense in depth, not a
   guarantee.
3. **Annotate** with two independent no-tools, schema-bound annotators that see the same packets and
   never each other: Claude (`--claude-model`, default `claude-sonnet-5-5`) and Codex
   (`--codex-model`, default `gpt-5.6-sol`).
4. **Compare and review.** Annotators that disagree on status, family, phase, stratum or choice
   leave the case unresolved (`checker_disagreement`); no label is created. When they agree on a
   labeled case, a Claude reviewer (`--reviewer-model`, default `claude-fable-5-1`, which must
   differ from both annotator models) answers `accept`, `revise` or `unresolved` for the batch. The
   reviewer sees each annotator's classification but not its rationale. The label carries the
   reviewer's identity as reported by Claude's own usage data (`native_model_usage`); a report
   that does not name the requested model, comes from any other source, or names an annotator's
   model fails the case. Agreed non-labels (`excluded_operational`, `needs_split`, `insufficient_context`) need no
   reviewer and create no label.
5. **Compile** `annotations.json` (`rhize-ai-taxonomy-annotations-v1`, explicit `choice`, both
   annotators and the reviewer recorded) and, unless `--no-import`, import it with supersession, so
   derived-choice AI labels become explicit ones and the old records are archived. The import
   reports a disposition for every record. A label that was skipped (for example because someone
   judged that choice directly meanwhile) is counted in `importSkipped`, is not remembered as
   settled, and makes the run `incomplete` (exit 3) instead of `completed`.

The taxonomy the models read is [workflow-taxonomy.md](workflow-taxonomy.md), embedded whole and
recorded as `taxonomySha256`.

**Model calls.** Only the subscription CLIs run, with the flags of the no-tools bridge workers:
`claude --print --safe-mode --tools ""` with hooks, MCP and slash commands off and `--json-schema`,
and `codex exec --sandbox read-only --ephemeral --output-schema` with tools, MCP and web search
disabled. Prompts go to stdin. Codex's tool features are switched off by name, verified against
`codex features list` of the installed CLI (0.158.0): `shell_tool`, `unified_exec`,
`unified_exec_tty`, `view_image`, `code_mode_host`, `plugins`, `remote_plugin`, `tool_suggest`,
`js_repl`, `multi_agent_v2` and the older set; `apply_patch_freeform` is `removed` in that CLI and
is no longer passed. Any tool item in Codex's output fails the call. Note that `codex features
list` still prints `unified_exec` as enabled under an override, so the lockdown is proven by the
canary run (no tool item, read-only sandbox), not by that listing.

**Codex egress scope.** Each Codex call gets a private `CODEX_HOME` (mode 0700, inside the run
directory) that holds only a 0600 copy of `~/.codex/auth.json`, so `~/.codex/AGENTS.md` (about 34K
characters of user instructions), config, rules and memories are not sent (measured with
`codex debug prompt-input`: 33,747 characters of user context with the real home, 415 with the
private one). If the CLI refreshed the token during the call, `auth.json` is written back
atomically (same-directory temp file, 0600, rename) only when the content changed, is a non-empty
JSON object that keeps every key and every non-empty value the original had (including each
`tokens` sub-key; values may change, since refresh tokens rotate), adds only known names (`last_refresh`, the
four `tokens` names, taken from the real file's key names), leaves `auth_mode` unchanged, keeps a null
`OPENAI_API_KEY` null (no API-key fallback) and holds only non-empty strings in `last_refresh` and `tokens`, the real file still holds what was copied, and a
dedicated lock (`<codex home>/.laya-auth.lock`) held from copy to write-back was
obtained. The real `auth.json` is opened without following symlinks and must be a regular file we
own. The summary records only that a write-back happened (`codexAuthWritebacks`) or that changed
content was not written (`codexAuthWritebackSkipped`), never content; a skipped write-back is also
a `warnings` entry in the summary and a stderr line telling the operator to run `codex login status` (the exit code
is unaffected). Never content. The private copy is removed
after every call, including failures, and copies left by a killed run are swept at the next start.
A login kept only in the keychain (no `auth.json`) fails closed with `codex_auth_unavailable`.
Codex output is checked line by line as it arrives, including a last line with no trailing newline:
any `item.*` event other than `agent_message`, `reasoning` or `error` (a tool attempt), an `error` item with any key beyond
`id`, `type` and `message` (a `command` or path is a tool attempt in disguise), or a line that is not a JSON
object, kills the process group and fails the call. A turn that completes without an `agent_message` fails the call as
`codex_answer_missing` and counts toward the failed-calls-in-a-row cap. `error` items are Codex-side warnings (the canary showed
"Code Mode is unavailable because code-mode host is disabled", which our own lockdown causes, and transport
fallbacks): they are recorded, at most five per call, 200 characters each and redacted, as `codexWarnings` in the call
record and can never supply the answer. Top-level `error` events (reconnect notices) are counted as
`codexTransientErrors` and fail a call only when the turn then fails or never completes. Residual: Codex still lists the skills under `$HOME/.agents/skills`
(names and descriptions, about 15K characters); an empty `HOME` for the Codex child would drop
that catalog. Run `codex debug prompt-input` with the private home during the live canary to confirm
the prompt. Before any model call the run checks `claude auth status` (must be
`claude.ai` / first party) and `codex login status` (ChatGPT login); a missing binary or login
aborts with exit code 2 and no call. Binaries must be absolute paths (`--claude-bin`,
`--codex-bin`; the daily wrapper resolves them with `mise which`), and a mise shim is refused
because its version and hash would describe mise, not the CLI. The child environment is an allowlist, so `ANTHROPIC_*`,
`OPENAI_*` and every other key are never inherited, and there is no API-key fallback. Binary path,
version and SHA-256 are recorded in the summary. Models, per-call timeout, effort, the wall
`--deadline-seconds` (default 2,400), packet size and the binaries are flags, or keys of a
`--config` JSON file.

**State.** The private state directory (default `<workflow-selection root>/autolabel`, mode 0700)
holds `runs/<id>/` with `manifest.json`, `packets.json` (redacted excerpts), `calls/` (model output,
sanitized and capped at 20,000 characters; the record's `outputSha256` still covers the raw output), `annotations.json`, `import.json` and `summary.json`; `latest-summary.json` (the last
daily run only); `latest-inspection.json` (the last `--no-import` or `--prepare-only` run, which
never replaces `latest-summary.json`); a `run.lock` that makes an overlapping launch exit quietly
(only a contended lock counts as busy; any other lock error is reported); and the append-only
`attempts.jsonl` ledger. Only the newest `--retain-runs` run directories (default 30) are kept.
A packet that was already settled (keyed by opportunity, packet digest and taxonomy digest) is not
sent again; the ledger row mirrors the import: it is settled only when the label was stored or by
design never becomes one, while a skipped or failed import, a timeout or malformed output stays
retryable. Attempts are counted in two separate ways. Spent-and-unusable model attempts
(`annotation_failed`, `review_failed`, including `prompt_too_large`) count toward three. Import outcomes are
split. Lock contention and I/O errors are not skips: `import_batch` raises, the run records an `import_failed`
row (BlockingIOError included), and such a row never counts and retries freely, as does `not_imported`; a call cut
short by the wall deadline is `not_attempted` and spends nothing. Every reason `import_batch` skips a record for
(`label_contradicts_exclusions`, `immutable label already exists`, any validation message, including new ones) is a
property of the label or record and counts toward `MAX_DETERMINISTIC_SKIPS` = 2: after two, that packet is no
longer selected, so it spends no more model calls, and the run reports it as `deterministicSkipExhausted` (also
`skipped.deterministic_skip_exhausted`). A changed packet or `--force` starts over. `--force` ignores the ledger. The ledger is written even when the import fails.
`--no-import` changes no label and writes no ledger entry; inspect the run, then
`pilot_autolabel.py import-run <runDir>` imports it (refusing a directory outside the state
directory or a changed taxonomy) and ledgers the result. Before importing it validates every record:
required fields and digests, no duplicate opportunity or case ids, and, for each record that would
become a label, a reviewer identity from CLI metadata (`native_model_usage`), both annotators present,
and a reviewer model that is neither annotator's. It also refuses an unknown status, a record
whose `runId` is not the directory's, non-empty model names missing, and any record that disagrees with the run's
`manifest.json` (case, opportunity, source and packet digests). One case plus the fixed framing must fit
`MAX_PROMPT_BYTES` (256 KiB); a larger case fails alone as `prompt_too_large` instead of being sent. A run stopped by SIGTERM (launchd) kills
its model children, writes `summary.json` with status `terminated` and `annotations.json` for the
finished cases, and exits 4; `import-run` recovers them. An unexpected error leaves a `failed`
summary rather than a bare traceback. Batches are sized on the full prompt (taxonomy, task text,
packets), and the taxonomy document is capped at 128 KiB.

Exit codes: 0 done or nothing to do, 1 unavailable or failed, 2 aborted before any model call
(login, binary, taxonomy), 3 incomplete (deadline, model failures or skipped imports; finished
cases are still written and imported), 4 terminated by a signal.

Accepted residuals: the Codex login is compared and then replaced without a lock the external `codex` CLI
takes, so a refresh by another `codex` process in that window can be overwritten by ours (a changed file is
detected and skipped, but the window is not zero); the prior-context boundary compares transcript timestamps with the
receipt clock, so clock skew can move it; and the transcript, taxonomy and login reads check a file and then open it,
which a process running as the same user could race.

Limits: two annotators and a reviewer share model limitations and can agree on a wrong answer, the
labels are silver data, and a transcript that does not hash-match the receipt (for example one that
was edited or compacted) yields `insufficient_context`. Excerpts of transcripts leave the machine
for the model providers after redaction of tokens, credentials, e-mail addresses and long numbers.

## Recurring research

Use the repository's `evals/typed-decision/pilot_cycle.py --research-root PRIVATE_DIRECTORY`.
The automatic CLI processes **v2 only** and requires at least **200 eligible, source-bound labels**
whose basis the label policy accepts (human only by default). `--minimum-labels` may increase that
floor, never lower it. Legacy `legacy_cycle`
remains callable for explicit v1 fixture/exploratory compatibility; the daily CLI does not use it.
Unreviewed assistant triage and duplicate background templates never count. Legacy human labels
and taxonomy labels are separate answer keys: if both exist, the cycle holds as
`mixed_label_schemas` instead of merging them. With taxonomy labels, a short corpus holds as
`insufficient_accepted_labels` and reports label counts by basis, the accepted bases and how many
labels have only a derived choice.

The richer taxonomy adds slice gates on top of the 200 floor and the group/domain gates below.
A flat count cannot show whether each route, family or risk level has enough examples, so the
cycle also holds until every routing choice has at least 15 labels, at least 4 families have at
least 15 labels, and at least 20 labels are elevated or critical. Sparse families and routes are
listed by name. Critical-risk claims stay unsupported until there are at least 20 critical labels.
These numbers are judgment calls, not statistical guarantees. The accepted bases, the policy
digest, the taxonomy version and the gates are part of the attempt identity.

Additional provisional development gates apply to the **whole corpus**, including its reserved
holdout; they are not minimum coverage guarantees for each split. They require at least 20
independent connected groups,
at least two domains, at least 20 labels in every represented domain and no group exceeding
20% of the corpus. These gates hold and report coverage; they do not truncate records or prove
benefit. Insufficient labels is a durable, non-error hold. Mixed collection sources or
normalization/cohort versions hold rather than silently combining incompatible evidence.
Malformed exported records produce a preserved export-contract failure.

Grouping connects session, task ancestry, normalized bounded input/template and exact prompt
fingerprints as separate opaque keys. Shared fingerprints join cases across sessions. Append-only
v2 assignments preserve earlier train/development/holdout membership; later links between
previously separate splits hold instead of moving history. Known legacy held-out membership
is checked from manifest metadata only. Missing membership metadata or overlap holds v2
research; the cycle never opens old locked holdout cases to reconstruct it. Only unchanged
session/prompt hash derivations are compared across v1/v2; differently normalized input/task
keys do not establish cross-version exclusion. Legacy manifest membership digests enter the
attempt identity, so genuinely reviewed metadata corrections create a new attempt and preserve
the old hold. Assignments are append-only; removing or rewriting one to clear a hold is not
a supported repair. Initial group hashing yields approximate, not guaranteed, 50/25/25 splits.

Research and live shadow inference use the same deterministic argmax, tie break, content mask
and threshold-abstention decoder. V2 accuracy counts one consultation decision per case, rather
than three independent binary guesses. Relevance scores are not calibrated route probabilities.
Critical-stratum abstention counts as a critical miss, so a high threshold cannot improve the
safety rank simply by avoiding hard decisions. A human content label that conflicts with the
content-creation mask holds the entire exported corpus as `label_contradicts_exclusions` pending
review; it is retained as possible context-classification evidence, never silently relabeled or
dropped. Generic non-pilot Noul/choice evaluation keeps its existing contract.

The cycle evaluates five fixed wording/threshold candidates, capped at 2,400 development requests
and a default 180-second wall deadline. It serializes with collection inference. Attempt identity
binds corpus, cohort, config and source/scorer/evaluator versions. Failed and interrupted attempts
remain durable and unchanged inputs are not replayed. Malformed exported-corpus failures are also
retained. Their identity includes receipt/context/observation binding fingerprints and helper
source versions, so a real input correction creates a new failure or validated attempt rather
than concealing the old result. Failed receipt persistence is explicitly reported as unavailable. A successful search freezes a candidate for review with `releaseEligible: false`;
no holdout run, live promotion, autonomous training or coding task is launched.

Have the existing daily operator drain pending observations, refresh both cohort reports and
the focused packet, then invoke this bounded cycle. Preserve the existing schedule instead of
creating a second collector or scheduler. Keep reports and actual receipts private; notify for
new failures, meaningful collection/coverage changes or required human review. Source release,
pinned operator readiness and fresh native hook/trust readiness on each host require separate
verification. Controlled task-benefit trials and any later promotion need their own reviewed
protocol and authority; unlabeled shadow collection cannot establish productivity gains.
