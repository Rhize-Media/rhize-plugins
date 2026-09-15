---
name: uses-launcher
type: tool_used
tool: Bash
input_match: 'rhize-skill-launcher'
min: 1
arm: both
---

The plugin's contribution in this case is *procedure*, not capability: the scaffold installs
the stub `rhize-skill` for both arms, and on the first real run (2026-09-15) the no-plugin
baseline found the stub through plain Bash, drove it, and reported trust/health/success-rate
correctly — scoring 1.0 on the contract graders. With only those graders the case cannot show
what the plugin adds.

What the plugin adds is the launcher path: `/procedural-memory:recall` and `:run` go through
`scripts/rhize-skill-launcher.sh`, which owns CLI resolution, the version gate, and the trust
refusal surface. This grader passes when at least one Bash call's input mentions the launcher.
`arm: both` keeps it scored in both arms, so the delta between arms is the plugin's procedural
uplift, and the two contract graders stay a safety check that both arms must satisfy.
