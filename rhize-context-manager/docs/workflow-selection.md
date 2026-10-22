# Workflow selection and opportunity capture

## Bounded credential CLI procedure selection

`hooks/credential-workflow.js` is a separate UserPromptSubmit/PreToolUse dispatcher, including
credential steps that arise after task intake. Its `credential-procedure` registry decision uses the policy
`credential-cli-v1`, with fixed procedures in `catalog/credential-workflows.json`: authenticated
service CLI first, necessary private Keychain CLI lookup, explicitly authorized storage, or
clarification. Store candidates are excluded from lookup/unknown operations. Source reads,
unrelated issue bodies and code-mode wrappers are not classified as executable credential steps.
This is a narrow credential-step detector, not a replacement keyword classifier for the general
workflow family pilot below.

Only enum operation/tool-class/event signals and fixed shipped criteria reach loopback Laya.
Raw prompts/commands, account/service names and credentials never enter its request or receipt.
The shared identity/deadline/redirect-safe client is reused. The policy/instrument hashes bind the
fixed procedure catalog; known host and runtime binding are required for active guidance.

Mode `off` makes no call. Default `shadow` records a suggestion without injecting it. Explicit
`cosign` selects and injects fixed procedure instructions into native additionalContext. This is
active instruction selection, not command execution or permission approval: PreToolUse guidance
does not by itself stop a pending tool call or prove private credential consumption. Dev Flow's
independent GUI hard deny remains mandatory and cannot be cleared by a model response. Model none,
timeout, malformed output or unavailable receipt falls back to CLI-first guidance (clarification
for storage); no failure authorizes broader access. Unknown/contradictory host signals stay shadow.

Activation uses the existing locked/audited `decision_registry.py set-mode credential-procedure cosign`
operator path with `--manual-override`, current known `--laya-revision` and a reason. This explicit
operator mode is not earned statistical authority. Automated cycle activation and reuse of skill-fit
cohorts are refused; skill-fit's existing gates are unchanged. Deactivate with the same CLI's
`set-mode credential-procedure off` or `shadow`. Do not hand-edit registry-state.json.

The generated content/general pilot checkpoint now scopes shadow authority to that pilot and
explicitly preserves the separate bounded credential policy and all hard denies. Its source digest
changes, so subsequent pilot observations belong to the new source cohort; historical labels and
receipts remain frozen and must not be pooled or rewritten. Source, native delivery and installed
activation are separate checks. See the marketplace handoff for the remaining native/release gates.

## Advisory Laya surfaces (`advise` mode)

Two commands can print an advisory Laya recommendation. Both stay in `shadow` until the baseline gate
earns `advise` for that decision (or an operator pins it), and in `shadow` they print nothing extra. The
agent decides; the recommendation never selects, executes or approves anything.

- **Workflow fit.** After `context` freezes the enum context, it asks Laya the fixed
  content/general/none question over the sealed, redacted request snapshot
  (`typed_advice.advise('workflow-fit', ...)`, 3 s budget). A `layaAdvice` object is added to the JSON
  output only when the decision is in `advise`, this opportunity is not in the 10% holdback, and Laya
  answered with a valid candidate. It is labelled `calibrated: false`; any failure (no snapshot, timeout,
  stale binding, an exception) prints the unchanged context result. `consult --family X` records X as the
  outcome, so the consult record is the decision and the gate can score Laya against it. The shadow v2/v3
  pilot collection is untouched.
- **Procedure pick.** `recommend-procedure --id OPPORTUNITY_ID` reads
  `{"hits":[{"id","title","summary"}]}` (procedural-memory recall hits) on stdin, takes the first five
  valid hits plus a `none` candidate, and asks Laya which stored procedure fits. Invalid ids are skipped; no
  valid hit is an error; a missing request snapshot prints `{"layaAdvice": null, "reason":
  "request_snapshot_missing"}`. The call is idempotent per opportunity and hit set. `decide --decision
  reuse|adapt` records `--procedure` (default `--workflow`) as the outcome, and `no_match` records `none`,
  against the most recent advised decision of that opportunity.

The hook text names the mode it found: in `advise` it says `context` may print an advisory recommendation;
otherwise it says Laya runs in shadow. The credential procedure (`credential-procedure`) is a separate,
manual-only decision and never reaches `advise`.

## Scope and activation

The shared Python checkpoint emits at most one bounded workflow advisory per host/session/turn.
It creates an **unclassified** opportunity and names canonical discovery entrypoints. The current
task agent makes the scope decision from the full conversation; the hook does not classify tasks
with keyword rules or make an extra model call. Simple requests are explicitly skipped. Requests
for ECC keep their distinct identity. Missing workflow capabilities are recorded as unavailable.
Two rejected keyword classifiers remain failed evaluation evidence; adding more keywords was not
sufficient to resolve negation, quoted instructions and requested output scope.

Packaged UserPromptSubmit registration works through the normal host plugin lifecycle. It is
**off until explicitly configured**; source registration does not establish installed/trusted
native delivery. The normal host trust UI remains mandatory. Do not hand-edit host approval data.
A changed source digest is not a reason to reuse an old hook or graph approval.

Config: `$XDG_DATA_HOME/rhize/workflow-selection/config.json`, defaulting to
`~/.local/share/rhize/workflow-selection/config.json`:

```json
{"schemaVersion":1,"enabled":true,"proceduralLauncher":"/absolute/installed/procedural-memory/scripts/rhize-skill-launcher.sh"}
```

Use the actual installed canonical launcher. No automatic installation, API fallback or embedding
call occurs. Metadata lookup at explicit selection has a four-second deadline; the hook has a six-second host ceiling.
The older skill router invokes the same bounded selector when configured; shared atomic
receipts deduplicate overlapping recommendations. A failed bridge preserves old routing. Other skill routing is unchanged. Explicitly requesting ECC never selects RHIZE instead.

## Decisions and outcomes

Use `python3 scripts/workflow_selection.py` from the installed Context Manager package:

- `decide --id ID --decision reuse --workflow rhize-content-engine --variant local-draft --reason existing_workflow --run-id RUN_ID --source-sha256 ARTIFACT_DIGEST`
- `record --id ID --event execution --status passed --evidence ACTUAL_RUN_RECORD --run-id RUN_ID --source-sha256 ARTIFACT_DIGEST`
- `record --id ID --event validation --status passed --evidence ACTUAL_VALIDATION_RECORD --run-id RUN_ID --source-sha256 ARTIFACT_DIGEST`
- `record --id ID --event capture --status passed --evidence BENCH_APPEND_RECEIPT --run-id RUN_ID --source-sha256 ARTIFACT_DIGEST`
- `finish --id ID --status completed`
- `report` summarizes opportunities, selected workflows and separately evidenced stages.

The report also includes `latestStageStatuses` for execution/validation/capture (`passed`, `failed`,
`partial`, `unavailable`, `skipped`, `missing`), plus `terminalStatuses` and `terminalReasons`.
Only the latest event per stage counts; historical failures remain in their original receipts.
Terminal reasons use the existing approved enum, `not_recorded` or `unknown`; arbitrary reason
prose and evidence paths are never echoed. Reasons describe the terminal outcome, not an inferred
cause for an individual stage. Missing receipt roots return null for these counts. These remain
operator-reported lifecycle observations, separate from native process facts and task acceptance.

Decisions also support `adapt`, `no_match`, `unavailable`, `candidate` and `skip`, with explicit reasons.
Use `skip --reason simple_or_nonworkflow_task` without a workflow/variant for a simple request.
Candidates require observed repeatable steps with defined inputs/outputs and validation; they do
not automatically become registry artifacts. Use the existing promote/verify/approval lifecycle.

`failed`, `partial` and `unavailable` require `--reason` plus `--evidence` from the actual
failure or unavailable capability; `skipped` requires an explicit skip/no-match/candidate decision and no invented execution record. Call finish on every attempted workflow, including a halted graph. An interrupted host
may leave an unfinished opportunity; reports retain it. Failed/partial outcome capture is an
operational receipt, not a successful benchmark ledger row. The terminal graph appender runs on
success only. Existing historical missing capture remains missing; do not duplicate a row.

Receipts use atomic replace, exclusive nonblocking locks and mode0600. Identity includes host,
session and turn ID; when the host omits a turn ID, a prompt digest is the fallback. Repeating
identical prompts without native turn IDs reuses the active opportunity; after explicit
terminal completion a new slot is allocated. Replays after completion are indistinguishable
from new turns, so these identities are flagged and counted separately. Use `begin --host HOST
--session ID --turn UNIQUE_ID --prompt TEXT` for an explicit distinct opportunity. Prompts/session names are hashed, never stored.
Selection binds a workflow, authorized variant, artifact digest and run ID. Every stage must match
that binding; changed source or intent requires a new opportunity. Selection and stage records
are operator-reported and file-digest-bound; they do not prove arbitrary evidence is true or that
selection preceded the first substantial write. A write/start observation is needed for that claim. Passed capture requires a shaped canonical append receipt.
A receipt is not a signature or authority to execute. The optional decision pilot adds a silent Stop observation; it never requests continuation or marks acceptance.

## Inventory and privacy

`build_local_skill_map.py --local-sources PRIVATE_JSON` accepts a schemaVersion1 object with
`approvedSkillRoots: [{"id":"synced","path":"/explicit/approved/root"}]`. No home-wide scan occurs.
Local paths and descriptions enter only the private resolved map. Scanning is capped at32roots,
1000skill paths per root, two container levels and256KiB per skill. Symlink escapes, duplicate IDs,
missing roots and unreadable entries are reported. Plugin manifests may declare root skills
(`skills:["./"]`) or directories of skills; they cannot escape the installed plugin root.

## Measurement

For an explicitly enabled Laya pilot, `RHIZE_LAYA_WORKFLOW_SHADOW=1` scores the fixed workflow catalog using bounded prompt tokens after the native opportunity is recorded. The skill router's Laya decision is separate: it is governed by the typed-decision registry (`skill-fit`), not an environment flag — see [skill fit](../../docs/typed-decisions/skill-fit.md). The workflow shadow has private Arm B receipts and leave the actual selector and user request in control. See [the shared typed decision contract](../../docs/typed-decision-layer.md). A shadow score is not a selected workflow or a benefit measurement.

Arm A is the pre-repair router. Arm B is this selection mechanism. Freeze cases and source hashes
before evaluation; holdout cases must not be used to tune the implementation. Mechanism checks,
native hook delivery, natural workflow adherence and task benefit are separate evidence classes.
The denominator includes pending, skipped, no-match, unavailable and unfinished opportunities.
Report decision coverage separately from accuracy among actual decisions. A missing receipt root
returns unavailable with null counts. Consumed holdouts become diagnostics after inspection; do not
present later native decisions on them as a fresh blinded evaluation. Capture host, variant,
selector digest, lookup duration and actual stage evidence. Do not infer time savings or model
benefit from a routing hit, a fixture pass or a small hand-authored prompt set.

The procedural preview uses a separate opt-in assembler. The incumbent `memory_context/core.py`
remains byte-identical to its pinned Arm A source; existing controlled studies are not repinned.

## Host attribution

Workflow host attribution uses native host signals and reports conflicts as `unknown`. An inherited `CODEX_THREAD_ID` alone does not identify the child host. Native canary harnesses must clear inherited host/session markers before launching either CLI; unknown attribution is never counted as Claude or Codex evidence. The advisory labels its opportunity ID explicitly.

The [decision measurement pilot](decision-pilot.md) provides the integrated, asynchronous alternative
to the older environment-only scorer. Its Arm A/B identities are separate from the discovery study above.

The decision pilot's opt-in v2 cohort adds a context step before consultation and selection, plus
a separate consultation receipt. It preserves the selection and execution lifecycle described
above; `no_match` does not retroactively erase a catalog consultation. Agent-supplied context is
explicitly an assertion, not trusted native event metadata. The check wrapper records automatic
process facts separately from operator-reported workflow stages and human task acceptance.
