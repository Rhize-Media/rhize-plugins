---
name: rhize-outreach-doctor
description: Diagnose local Rhize Outreach setup, runtime pin, private data directories, Codex CLI sign-in, and operator UI health without changing state.
metadata:
  rhize:
    topics: [observability, automation]
    stacks: []
---

# Rhize Outreach Doctor

Resolve the installed plugin root by moving two directories above this skill file, then run `node "<plugin-root>/scripts/rhize-outreach.mjs" doctor --json`. This command is read-only. Summarize each check and its remediation. Never print environment variables, local session URLs, credentials, or database connection strings.

A ready doctor result means only that the pinned runtime, local tools, and loopback UI are available. It does not prove a website/audit is visually correct, a live prospect source is complete, or a message/site was sent or published.
