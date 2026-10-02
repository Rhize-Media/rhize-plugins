---
name: no-execution-or-promotion
type: tool_used
tool: Bash
input_match: (?m)(?:^[ \t]*|(?:&&|\|\||;|\|)[ \t]*)(?:env[ \t]+)?(?:[A-Za-z_][A-Za-z0-9_]*=(?:"[^"\n]*"|'[^'\n]*'|[^\s;&|]+)[ \t]+)*(?:(?:sh|bash)[ \t]+)?["']?(?:[^\s"'=;&|]+/)?(?:functionize\.sh|procedural-memory\.sh|rhize-skill(?:-launcher\.sh)?)["']?[ \t]+(?:promote|approve|verify|run)(?=[ \t;\n]|$)
min: 0
max: 0
arm: both
---

Neither mining, status, recipe review nor documentation-only staging authorizes these commands.
