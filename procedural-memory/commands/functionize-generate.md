---
description: Compile one exported Functionize v2 candidate into an inert isolated proposal bundle
argument-hint: <candidate.json> --proposal-dir <path> [--baseline-sha <sha>] [--observed-at <timestamp>]
allowed-tools: Bash
---

Compile one exported Functionize candidate: $ARGUMENTS

Run:

    ${CLAUDE_PLUGIN_ROOT}/skills/functionize/scripts/functionize.sh generate $ARGUMENTS

This compiles only. It does not review, register, assign trust, approve, promote, invoke, or execute
the generated wrapper. Report the candidate fingerprint, bundle path, grader status, promotability
fields, idempotency, and any refusal exactly as emitted. Never substitute a different candidate or
baseline after a refusal.
