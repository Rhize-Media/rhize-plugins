---
description: Assemble or verify a private, scoped memory-context preview without injection
model: sonnet
---

# /memory-context

Use the canonical `memory-context` skill. This Claude command is only a thin adapter:

```bash
"${CLAUDE_PLUGIN_ROOT}/skills/memory-context/scripts/memory-context.sh" preview \
  --input /absolute/private/request.json
```

Inspect adapter statuses, exclusions, conflicts, authority classes, expiry, and warnings. Do not read
the private payload into a prompt automatically. Verification, exact-source purge, and expired-pack
cleanup use the same launcher and require the boundaries described by the canonical skill.

The optional graph-memory adapter is library-fed into this same explicit request after a bounded
`query_context` call. This command never accepts Cypher, graph writes, or live database credentials.
