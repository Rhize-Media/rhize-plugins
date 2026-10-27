# Advisory evidence checklist

Use the existing preview launcher with an explicit private source checklist:

```bash
scripts/memory-context.sh preview --input /absolute/private/request.json \
  --requirements /absolute/private/requirements.json
```

The requirements file follows `schemas/memory-evidence-requirements-v1.schema.json`:

```json
{"schemaVersion":1,"requirements":[{"id":"approved-policy","adapter":"canonical-files","sourceId":"policy","sourceRevision":"rev-2"}]}
```

Every ID/revision must be a safe identifier, and requirement IDs must be unique. Declare exact
revisions for current or historical questions; age alone never invalidates historical evidence.
The optional `evidenceCompleteness` result binds the exact `packId` and `payloadHash`. Requirement
IDs, source IDs and revision IDs are hashed; no candidate text is included. It is a source checklist,
not a semantic fact detector. An empty checklist returns `coverage: unknown`, never complete.

| Status | Meaning |
| --- | --- |
| selected | An admissible record for the exact source revision is in the preview. |
| excluded | An admissible exact record was removed by selection budgets. |
| empty | The named adapter successfully returned no records. |
| unavailable | The adapter was absent, denied, timed out, stale or otherwise unavailable. |
| missing | The exact revision is absent from the admissible snapshot. |
| unknown | The adapter returned partial results, so absence cannot establish missing evidence. |

Denied records are never used to disclose that a source exists. A source denied by scope/sensitivity
may therefore appear as missing from an otherwise available adapter. Existing aggregate exclusions
remain available separately. Content hashes sharing an explicit claim key are metadata conflict
signals; neither this report nor that grouping establishes semantic contradiction.

The report is computed before persistence from the same normalized input and frozen build time.
It cannot change ranking, relax scope, write memory back, inject content or authorize execution.
Do not make the report a blocking gate before comparing warnings with independent task review.
