---
name: graphiti-memory
description: >-
  Adoption and usage guide for Graphiti — Zep's temporal knowledge-graph memory layer for
  agents. Use when the user wants queryable long-term agent memory with entities,
  relationships, and time-awareness (beyond claude-mem's observation stream), when
  setting up the Graphiti MCP server, or when deciding between Graphiti, claude-mem,
  graphify, and the Obsidian vault for a piece of knowledge. Graphiti is OPT-IN: this
  plugin documents the wiring but does not install or require it.
metadata:
  rhize:
    topics: [knowledge-graph, memory-systems]
    stacks: []
    dependsOn: ["mcp:graphiti"]

---

# Graphiti — Temporal Knowledge-Graph Memory (opt-in)

Graphiti (github.com/getzep/graphiti) builds a temporally-aware knowledge graph from
agent interactions and business data: entities, relationships, and validity intervals
(what was true, when). Unlike claude-mem's append-only observation stream, Graphiti
supports incremental updates, point-in-time queries, and hybrid retrieval
(semantic + BM25 + graph traversal) without full re-ingestion.

## When Graphiti (vs the rest of the stack)

- **claude-mem**: automatic session observations, zero setup — keep as the default.
- **graphify**: human-browsable vault knowledge graphs — for reading, not agent recall.
- **Graphiti**: when agents need to QUERY structured memory — "what did we decide about
  X and when did it change", cross-project entity relationships, client/product state
  that evolves. Reach for it when claude-mem recall keeps missing relationship-shaped
  questions.

## Setup (not performed automatically — requires a graph backend)

1. **Backend**: Neo4j (Desktop or Docker) or FalkorDB (lighter, Docker one-liner):
   `docker run -p 6379:6379 -p 3000:3000 falkordb/falkordb`
2. **MCP server** (recommended integration path for Claude Code):
   ```bash
   claude mcp add --scope user graphiti -- uvx graphiti-mcp-server
   ```
   Required env: `OPENAI_API_KEY` (or configured alternative LLM for extraction),
   `NEO4J_URI`/`NEO4J_USER`/`NEO4J_PASSWORD` (or FalkorDB connection vars).
   Store keys in the macOS Keychain per the Rhize credential pattern; retrieve
   on-demand — never hardcode in the MCP config.
3. Verify: the server exposes add-episode / search-nodes / search-facts style tools;
   add a test episode and query it back.

## Usage patterns

- **Episodes in, queries out**: feed session outcomes/decisions as episodes; query by
  entity or natural language during later sessions.
- **Namespace per project** (group_id) so client/project graphs stay separated.
- **Don't double-write**: if a fact is already in claude-mem AND the vault, only promote
  it to Graphiti when it's relationship- or time-shaped. Graphiti is not a third dump.

## Status at Rhize

Approved for full adoption (2026-07-20) but NOT a dependency of this plugin — backend
standing-up is a separate infra task. Until it exists, treat this skill as the
design/decision reference and route memory per the `context-stack` skill.
