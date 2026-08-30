---
description: Validate and preview a governed Graphify projection without live Neo4j access
model: sonnet
---

# /graph-memory

Follow the canonical `rhize-context-manager:graph-memory` skill. Resolve the shared host-neutral CLI
from `${CLAUDE_PLUGIN_ROOT}/scripts/graph_memory/cli.py`; do not reproduce its validation, tenancy,
trust, publication, or query rules in this command.

Default to `validate`, then offer a private `preview`. Never invoke `graphify export neo4j`,
`graphify export neo4j --push`, arbitrary Cypher, a Neo4j driver, or a live database from this
release. A live canary and restore rehearsal are deferred to RT-159.
