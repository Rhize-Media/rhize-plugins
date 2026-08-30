---
name: graphiti-memory
description: >-
  Historical design reference for Graphiti concepts. Use only when reviewing the prior
  Graphiti decision or comparing its temporal-memory ideas with Rhize's governed Neo4j plans.
  Do not use this skill to install, configure, route to, or claim adoption of Graphiti.
metadata:
  rhize:
    topics: [knowledge-graph, memory-systems]
    stacks: []

---

# Graphiti — historical design reference only

Graphiti (github.com/getzep/graphiti) builds a temporally-aware knowledge graph from
agent interactions and business data: entities, relationships, and validity intervals
(what was true, when). Unlike claude-mem's append-only observation stream, Graphiti
supports incremental updates, point-in-time queries, and hybrid retrieval
(semantic + BM25 + graph traversal) without full re-ingestion.

## Current routing instead

- **claude-mem**: automatic session observations, zero setup — keep as the default.
- **graphify**: human-browsable vault knowledge graphs — for reading, not agent recall.
- **memory-context**: bounded, private multi-source previews with authority and conflicts preserved.
- **Neo4j**: later read-only semantic projection only after the approved ontology/hygiene gates.

## Concepts retained for design comparison

- Temporal validity and supersession must survive retrieval.
- Every project/client needs an enforced namespace and ACL boundary.
- A graph projection must not become a second canonical source or accept implicit writes.

## Status at Rhize

Graphiti was never implemented and is not adopted. Neo4j is the available graph database, with
Graphify and CodeGraph retaining their existing responsibilities. The canonical `memory-context`
skill assembles preview-only source-bound context; a Neo4j semantic adapter remains blocked on the
separate ontology and graph-hygiene gates. Do not install Graphiti or add it to setup/doctor routing.
