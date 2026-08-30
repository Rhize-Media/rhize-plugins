---
description: Produce state-bound test evidence in an isolated disposable worktree for explicit regression claims
---
<!-- canonical-skill: rhize-devflow:test-evidence -->

# Test Evidence

Invoke the canonical `rhize-devflow:test-evidence` skill and follow it completely. This command is
the explicit pre-review writer; it accepts only authorized package test scripts and never mutates the
live checkout. Pass `$ARGUMENTS` unchanged as the requested claim/spec boundary. `/review` remains
read-only and only validates the resulting local packet.
