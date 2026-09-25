---
name: rhize-outreach-run
description: Start the local Rhize Outreach operator and resume the selected-business agent graph. Use after setup when preparing or reviewing a prospect package.
metadata:
  rhize:
    topics: [automation, workflow-patterns]
    stacks: []
---

# Rhize Outreach Run

Resolve the installed plugin root by moving two directories above this skill file.

1. Run `/rhize-outreach:doctor`. If setup is blocked, stop and follow its remediation.
2. Start the foreground service with `node "<plugin-root>/scripts/rhize-outreach.mjs" start`. It opens the authenticated loopback UI in the default browser and withholds the session URL from the transcript. Keep the terminal running.
3. In the UI, choose the campaign area and industry, review generated candidates or add a business you found manually, and select a business. Selection starts/resumes its durable workflow.
4. Inspect the website concept and report yourself. The background runner cannot use an actual browser or run external design-system skill commands; its receipt records that limitation. Do not call a deliverable visually reviewed unless you actually reviewed the rendered pages.
5. Accept the package only after review. That explicit action resumes email drafting. Review the draft; acceptance records review only. There is no send action.

The graph can pause for package review and email review. Never treat retries, a ready UI, or synthetic test data as permission to run paid discovery. Keep source coverage and uncertain results explicit.
