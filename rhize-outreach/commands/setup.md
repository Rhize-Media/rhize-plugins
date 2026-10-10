---
description: Install or resume the local Rhize Outreach workflow
argument-hint: "[--from-rhize-setup]"
allowed-tools: [Skill, Bash, Read]
---

Invoke `rhize-outreach:rhize-outreach-setup` with `$ARGUMENTS`. The skill opens the token-protected loopback setup wizard. Running setup alone does not install files; the operator must choose “Install pinned workflow” in the browser.

Also reachable from `/rhize-core:setup --plugin rhize-outreach`. When that orchestrator launches this wizard it passes `--from-rhize-setup`; strip that token from `$ARGUMENTS` before handing the rest to the skill, and when the wizard ends, stop rather than pointing the user at `/rhize-outreach:run` or other setup commands — the orchestrator continues with its own remaining phases.
