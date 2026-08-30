---
description: Review and reverse governed graph identity proposals
argument-hint: "list|show|preview|lease|decide|defer|reverse|status [options]"
allowed-tools: Bash
---

# Graph Memory Review

Use the canonical `rhize-context-manager:graph-memory` skill and its host-neutral graph-memory CLI for `$ARGUMENTS`. This file is only the Claude Code adapter; do not reproduce review policy or state transitions here.

Require host-authenticated, tenant-and-namespace-bound `identity_reviewer` authority for leases, decisions, reads, and reversals. Before a decision, show the exact candidate revision and a current bounded impact preview. Use only enumerated rationale codes, preserve optimistic revision and lease preconditions, and return the canonical privacy-safe receipt.

Never physically merge source entities, mutate immutable Claims/provenance/ACL/trust, connect directly to live Neo4j, or infer `SAME_AS` from a score. Consolidation may only propose candidates. Use `status` for aggregate health and a dry-run reversal preview before any reversal.
