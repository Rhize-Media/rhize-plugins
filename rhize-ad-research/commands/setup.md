---
description: Run ad research setup
argument-hint: "[client and task]"
allowed-tools: [Skill, Bash, Read, Write, mcp__meta-ads__ads_library_search]
---

Invoke `rhize-ad-research:rhize-ad-research-setup` with `$ARGUMENTS`. Use the shared CLI and preserve its gates.

When `$ARGUMENTS` contains `--from-rhize-setup`, remove that handshake token before forwarding the remaining client/task context. It does not authorize paid work.
