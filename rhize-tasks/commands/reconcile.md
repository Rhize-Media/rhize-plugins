---
description: Preview and reconcile local Rhize task drift
argument-hint: "[source or issue filter]"
allowed-tools: [Bash, Read]
---

Use `$reconcile-rhize-tasks` for this request. Pass `$ARGUMENTS` as user context, resolve the installed CLI from its manifest, read the TodayView `reconciliation` array, explain the exact IDs/system/kind/reason, and ask which exact IDs to resume. Require the actor name, then submit only those approved IDs with the displayed revision and actor to `/v1/reconcile`. Never retry automatically. Never ask for secrets in chat.
