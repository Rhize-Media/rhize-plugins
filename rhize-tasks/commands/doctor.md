---
description: Diagnose the local Rhize Tasks service safely
argument-hint: "[component to inspect]"
allowed-tools: [Skill, Bash, Read]
---

Invoke the `rhize-tasks:rhize-tasks-doctor` skill (Skill tool) for this request. Pass `$ARGUMENTS` as a diagnostic focus and keep the workflow read-only unless the user separately approves a bounded repair. Never ask for secrets in chat.

The skill checks source freshness against this plugin's pinned runtime tag (`setup/manifest.json`'s `rhize-tasks runtime` dependency), so a report may include whether the installed runtime matches or has drifted from that pin.
