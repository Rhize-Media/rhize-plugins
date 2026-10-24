---
schema_version: "1.1"
name: graph-workflow-negative-knowledge
tags: [graph-workflow-builder, negative]
plugins: ["../.."]
runs: 2
max_turns: 8
timeout_seconds: 120
allowed_tools: [Skill]
---
Explain in two sentences how a knowledge graph connects Obsidian notes. Do not design an
execution workflow or invoke graph-workflow-builder.
