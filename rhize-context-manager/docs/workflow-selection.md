# Workflow selection and opportunity capture

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
A receipt is not a signature or authority to execute. No Stop hook or continuation loop is added.

## Inventory and privacy

`build_local_skill_map.py --local-sources PRIVATE_JSON` accepts a schemaVersion1 object with
`approvedSkillRoots: [{"id":"synced","path":"/explicit/approved/root"}]`. No home-wide scan occurs.
Local paths and descriptions enter only the private resolved map. Scanning is capped at32roots,
1000skill paths per root, two container levels and256KiB per skill. Symlink escapes, duplicate IDs,
missing roots and unreadable entries are reported. Plugin manifests may declare root skills
(`skills:["./"]`) or directories of skills; they cannot escape the installed plugin root.

## Measurement

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
