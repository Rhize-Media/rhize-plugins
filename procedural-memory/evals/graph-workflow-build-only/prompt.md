---
schema_version: "1.1"
name: graph-workflow-build-only
description: Build-only goal and dynamic completion contract
tags: [graph-workflow-builder, routing, authority]
plugins: ["../.."]
runs: 2
max_turns: 16
timeout_seconds: 240
allowed_tools: [Skill, Read, Write, Bash]
---
Build a reusable graph workflow for researching a changing set of local source cards and
drafting a checked summary. Use graph-workflow-builder. Define the goal and named finished
criteria, include bounded dynamic node creation and a final integrated evidence check.
Build and validate only; do not stage, promote, approve or run anything. Use subscription
models only. If this runtime lacks graph validate/workflow support, report the limitation
honestly rather than substituting an API runner.
