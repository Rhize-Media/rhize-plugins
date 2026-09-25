---
name: rhize-outreach-setup
description: Set up or resume the local Rhize Outreach selected-business workflow. Use when installing the plugin, configuring local storage, or repairing an incomplete setup.
metadata:
  rhize:
    topics: [automation, workflow-patterns]
    stacks: []
---

# Rhize Outreach Setup

1. Resolve the installed plugin root by moving two directories above this skill file. Run `node "<plugin-root>/scripts/rhize-outreach.mjs" wizard`. The command binds only to `127.0.0.1`, opens the setup UI in the default browser and withholds the session URL from chat and terminal output.
2. Review the prerequisite status, pinned runtime commit and private data location. Change the data location or port if needed.
3. Select “Install pinned workflow” to fetch the exact runtime revision, install locked dependencies and create private local data/artifact directories. The wizard never collects credentials.
4. When the wizard confirms completion, start `/rhize-outreach:run`; use `/rhize-outreach:doctor` to check local health.

The current graph worker uses the Codex CLI and private local PostgreSQL. GHL, Gmail/Workspace, Supabase, Resend and Vercel are not connected. Setup does not run paid discovery, send email or publish a site.
