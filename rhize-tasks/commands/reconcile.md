---
description: Preview and reconcile local Rhize task drift
argument-hint: "[source or issue filter]"
allowed-tools: [Bash, Read]
---

Use `$reconcile-rhize-tasks` for this request. Pass `$ARGUMENTS` as user context, resolve the installed CLI from its manifest, review existing TodayView reconciliation-required operations, and submit only explicitly approved operation IDs and the displayed revision to the local `/v1/reconcile` route. Never ask for secrets in chat.
