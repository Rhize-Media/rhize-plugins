---
description: Preview or inspect a source-bound decision through the governed graph-memory contract
model: sonnet
---

# /graph-decision

Follow the canonical `rhize-context-manager:graph-memory` skill and its host-neutral CLI. Use only
the `graph-memory decision` operations exposed there: `preview`, `record`, `explain`, `impact`,
`precedents`, `correct`, and `status`. This command must not reproduce validation, policy,
authorization, tenancy, nonce, optimistic-concurrency, retention, or query-budget rules.

Run `decision status` first. Default to `preview`. Require the owning workflow's current
source/evidence/policy and an authenticated actor plus approval before requesting `record` or
`correct`. Never infer a decision from an agent transcript, store prompts or hidden reasoning, issue
raw Cypher, connect directly to Neo4j, or install Semantica. The offline CLI does not offer durable
recording. If a requested operation is not configured, return `unavailable` exactly as the CLI
reports it; do not create a local shadow decision record.
