# Typed decision adapters

`rhize-context-manager` owns the decision proposal, preview, record, and query contracts. Consumer
plugins may map their authoritative records into that contract, but they must not create another
ledger, graph client, policy engine, or Jira client.

## Common adapter output

An adapter emits one strict `decision proposal` JSON object accepted by
`graph_memory.decisions.InMemoryDecisionLedger.preview`. Every value comes from an authoritative
source or a deterministic digest:

- `source` binds the canonical system, opaque hashed id, revision, and content digest;
- `evidenceSet` is a non-empty immutable selection with current availability status;
- `policySnapshot` and `policyEvaluation` bind an exact version/digest and reproducible result;
- `approval` is source-bound, scoped, granted, unexpired, and bound to the same actor;
- `rationaleSummaryHash` commits to a separately governed concise rationale, not hidden reasoning;
- `workflow` names the producing plugin and its contract revision.

Adapters must pass proposal data to `graph-memory decision preview`. They must never scrape agent
transcripts, prompts, hidden reasoning, credentials, client content, or unredacted paths. Preview
artifacts are private, short-lived, nonce-bound, single-use, and written outside repositories.

## Consumer mappings

| Consumer | Eligible first-release decisions | Canonical source and evidence | Forbidden behavior |
|---|---|---|---|
| `rhize-devflow` | reviewed release, rollback, or completed-branch promotion | Git/PR/deployment revisions plus the applicable repository policy and approval | A green check cannot approve or record a release; no deployment is inferred from Git state. |
| `rhize-ops` | experiment/adoption or promotion/hold decisions | Jira measurement issue plus privacy-safe receipt/report digests and predeclared thresholds | A receipt cannot mutate Jira or upgrade observational evidence into controlled evidence. |
| `rhize-tasks` | approved external-effect routing or reconciliation choice | local plan/revision and exact approved operation, with Jira only as a referenced canonical task | The adapter cannot approve an operation, contact a connector, or copy the local SQLite task store. |

Each consumer will supply current source/evidence/policy/approval bindings again at `record`. If any
revision or digest changed, recording must fail closed. Durable recording is unavailable in the
offline CLI because there is no accepted governed projection to update atomically.

## Offline and live boundaries

The shipped CLI exposes the complete bounded vocabulary:

```text
graph-memory decision preview
graph-memory decision record
graph-memory decision explain
graph-memory decision impact
graph-memory decision precedents
graph-memory decision correct
graph-memory decision status
```

Only `preview` executes in the offline CLI. The underlying in-memory adapter exercises preview,
record, correction, query, nonce, TTL, idempotency, and compare-and-swap behavior in one process for
deterministic tests, but it is not durable state. `record` and all projection operations return
`governed_decision_projection_not_configured` with `status=unavailable` until the RT-161 canary
enables the governed adapter. Consumers must preserve that state; they may not fall back to a local
file, plugin database, raw Cypher, direct Neo4j, or live Jira access.

The deterministic fixtures under `evals/decision-accountability/fixtures/` are synthetic contract
examples only. Their hashes and opaque refs contain no live identity, tenant data, credentials, or
operational authority.
