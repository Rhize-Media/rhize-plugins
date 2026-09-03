---
description: Run or resume the safe local Rhize Tasks setup wizard
argument-hint: "[resume|stage number]"
allowed-tools: [Skill, Bash, Read]
---

Invoke the `rhize-tasks:rhize-tasks-setup` skill (Skill tool) for this request. Pass `$ARGUMENTS` as user context, preserve its approval and secret-handling boundaries, and use only the installed Rhize Tasks local CLI/dashboard. Never ask for secrets in chat.

This plugin ships no runtime code — the skill's first stage bootstraps a pinned-tag checkout of the separate `Rhize-Media/rhize-tasks` runtime repo (see `setup/manifest.json`) into `~/Library/Application Support/Rhize Tasks/source/<tag>/` before anything else can run.

Also reachable from `/rhize-core:setup --plugin rhize-tasks`. When that orchestrator launches this wizard it passes `--from-rhize-setup`; strip that token from `$ARGUMENTS` before handing the rest (`resume` or a stage number) to the skill, and when the wizard ends, stop rather than pointing the user at other setup commands — the orchestrator continues with its own remaining phases.
