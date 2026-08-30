---
description: Produce fail-closed, state-bound metadata for explicit regression claims
---
<!-- canonical-skill: rhize-devflow:test-evidence -->

# Test Evidence

Invoke the canonical `rhize-devflow:test-evidence` skill and follow it completely. This command is
the explicit pre-review writer; it binds only authorized package-script declarations but does not
execute them until a trusted sandbox adapter exists. It never mutates the live checkout. Pass
`$ARGUMENTS` unchanged as the requested claim/spec boundary. `/review` remains read-only and treats
the resulting unavailable packet as unsupported.
