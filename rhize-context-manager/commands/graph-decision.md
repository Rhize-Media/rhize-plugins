---
description: Preview or inspect a source-bound decision through the governed graph-memory contract
model: sonnet
---

# /graph-decision

Follow the canonical `rhize-context-manager:graph-memory` skill and its host-neutral CLI. Use only
the typed `graph-decision` operations exposed there: `preview`, `record`, `explain`, `impact`,
`precedents`, `correct`, and `status`. This command must not reproduce validation, policy,
authorization, tenancy, nonce, optimistic-concurrency, retention, or query-budget rules.

Default to read-only `preview`. Require the owning workflow's current source/evidence/policy and an
authenticated actor plus approval before `record` or `correct`. Never infer a decision from an agent
transcript, store prompts or hidden reasoning, issue raw Cypher, connect directly to Neo4j, or install
Semantica. If the shared CLI has not exposed a requested operation yet, return `unavailable`; do not
create a local shadow decision record.
