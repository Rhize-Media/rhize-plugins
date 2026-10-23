---
schema_version: "1.1"
name: graph-workflow-negative-simple
tags: [graph-workflow-builder, negative]
plugins: ["../.."]
runs: 2
max_turns: 8
timeout_seconds: 120
allowed_tools: [Skill]
---
Give me a one-line shell command that counts lines in one local file. There is no reusable
workflow to build. Do not invoke graph-workflow-builder.
