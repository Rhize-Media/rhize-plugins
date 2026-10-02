---
name: stage-command
type: tool_used
tool: Bash
input_match: (?m)(?:^[ \t]*|(?:&&|\|\||;|\|)[ \t]*)(?:env[ \t]+)?(?:[A-Za-z_][A-Za-z0-9_]*=(?:"[^"\n]*"|'[^'\n]*'|[^\s;&|]+)[ \t]+)*(?:(?:sh|bash)[ \t]+)?["']?(?:[^\s"'=;&|]+/)?procedural-memory\.sh["']?[ \t]+recipe-stage\b(?![^\n;&|]*--check\b)(?=[^\n;&|]*--name\b)(?=[^\n;&|]*--ledger\b)
min: 1
arm: both
---

Staging belongs to the procedural-memory wrapper, outside Functionize's compile/review surface.

Requires the staging command with --name, not a --check-only invocation.
