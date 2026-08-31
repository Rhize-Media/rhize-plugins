---
name: functionize-negative-one-off
tags: [negative, routing, functionize]
plugins: ["../.."]
runs: 3
max_turns: 6
timeout_seconds: 60
allowed_tools: [Bash, Skill]
---

Write a one-off shell wrapper around this curl command. There is no repeated CLI pattern or shell
history to mine.
