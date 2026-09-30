---
name: stage-check
type: tool_used
tool: Bash
input_match: 'procedural-memory\.sh[^\n]*recipe-stage[^\n]*--check'
min: 1
arm: both
---

The staged fixture is checked against the same synthetic ledger without promotion or execution.
