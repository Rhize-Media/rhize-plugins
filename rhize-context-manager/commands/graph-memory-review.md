---
description: Review and reverse governed offline graph identity proposals
argument-hint: "status|list|show|lease|preview|decide|defer|reverse|consolidate|quality [options]"
allowed-tools: Bash
---

# Graph Memory Review

Use the canonical `rhize-context-manager:graph-memory` skill and its host-neutral graph-memory CLI:
`graph-memory hygiene $ARGUMENTS`. This file is only the Claude Code adapter; Codex uses the same
skill metadata and CLI. Do not reproduce review policy or state transitions here.

Run `status` first. In this release, every stateful/read operation returns structured `unavailable`
with reason `governed_private_state_adapter_not_configured`. Preserve that result even when the user
supplies a state path; the CLI intentionally does not read or create it.

Never physically merge source entities, mutate immutable Claims/provenance/ACL/trust, connect
directly to live Neo4j, or infer `SAME_AS` from a score. A future consolidation adapter may only
propose candidates; reversal will require its own current bounded preview.

Preserve the actor-effective ACL lane (`current review ACLs ∩ authenticated actor ACLs`) for every
preview, dependency, transition, supersession, ledger, and reversal operation. Broad actor grants
must not widen the current review or reveal another lane's entities or decision identifiers.

Do not invent a plugin-local ledger, hydrate private module fields, or claim a successful offline
decision. The in-process lifecycle is test evidence only until its owning domain supplies a
versioned private-state adapter with authenticated actor/partition bindings, CAS, atomic writes,
and interruption/replay tests.
