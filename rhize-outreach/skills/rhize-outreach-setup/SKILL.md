---
name: rhize-outreach-setup
description: Install or resume the seven-stage Rhize Outreach setup wizard on a Mac. Use for first install, runtime alignment, Supabase workspace connection, connector configuration or a no-send dry run.
metadata:
  rhize:
    topics: [automation, outreach, workflow-patterns]
    stacks: [postgresql, supabase]
---

# Rhize Outreach Setup

Run the supported local wizard. Never ask for, repeat or paste a secret in chat.

1. Run `uname -s`; stop with a Mac-side runbook unless it returns `Darwin`.
2. Resolve this plugin root from the current `SKILL.md` location. Run `python3 <plugin-root>/scripts/outreach_setup.py bootstrap --check`, inspect the exact plan, then run `bootstrap` when the local install is authorized.
3. Run `python3 <plugin-root>/scripts/outreach_setup.py serve`. Open the emitted loopback URL locally without copying it into chat or a persistent log.
4. Complete the resumable stages: platform/runtime, operator profile, input environment variables, Supabase workspace, agent host/skills, adapters and no-send dry run.
5. Secret fields are posted only to loopback and written to macOS Keychain. The browser must clear each secret input after a successful write. Config stores secret names and readiness only.
6. Gmail begins `draft_only`; GHL begins `draft_only`; Vercel begins disabled. Do not enable send or publish during setup.
7. Finish with `python3 <plugin-root>/scripts/outreach_setup.py doctor --json`. Report the redacted result and exact repair steps.

When invoked by Rhize Core with `--from-rhize-setup`, stop after doctor; otherwise suggest the Rhize Core evaluation flow.
