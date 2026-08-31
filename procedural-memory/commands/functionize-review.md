---
description: Validate and append a digest-bound human Functionize candidate decision without generating or promoting code
argument-hint: <candidate.json> <review.json> --ledger <path>
allowed-tools: Bash
---

Record a completed human Functionize review: $ARGUMENTS

Run:

    ${CLAUDE_PLUGIN_ROOT}/skills/functionize/scripts/functionize.sh review $ARGUMENTS

The completed review manifest is the decision source. Do not infer acceptance from conversation
prose or fill missing review fields on the user's behalf. Recording a review does not generate,
register, assign trust, approve, promote, verify, invoke, or execute anything. Report whether the
exact digest-bound decision was recorded or already present.
