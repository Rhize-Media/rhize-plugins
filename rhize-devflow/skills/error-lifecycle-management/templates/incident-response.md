# Incident Response Template

## Incident Information

| Field | Value |
|-------|-------|
| **Incident ID** | INC-YYYY-MM-DD-### |
| **Severity** | P1 / P2 / P3 / P4 |
| **Status** | Investigating / Identified / Monitoring / Resolved |
| **Started** | YYYY-MM-DD HH:MM UTC |
| **Resolved** | YYYY-MM-DD HH:MM UTC |
| **Duration** | X hours Y minutes |
| **Responder** | @name |

## Summary

_Brief description of the incident_

## Impact

- **Users Affected**: ~X users
- **Features Impacted**: List affected features
- **Revenue Impact**: If applicable
- **SLA Breach**: Yes/No

## Timeline

| Time (UTC) | Event |
|------------|-------|
| HH:MM | Issue first detected via [Sentry/User Report/Monitoring] |
| HH:MM | On-call engineer alerted |
| HH:MM | Root cause identified |
| HH:MM | Fix deployed |
| HH:MM | Issue resolved, monitoring |

## Root Cause

_Technical explanation of what caused the incident_

## Resolution

_What was done to fix the immediate issue_

```typescript
// Code changes if applicable
```

## Action Items

### Immediate (This Week)
- [ ] Deploy hotfix
- [ ] Update monitoring thresholds
- [ ] Notify affected users

### Follow-up (Next Sprint)
- [ ] Add additional error handling
- [ ] Improve alerting
- [ ] Update documentation
- [ ] Create regression tests

## Lessons Learned

### What Went Well
- 

### What Could Be Improved
- 

### Where We Got Lucky
- 

## Related Links

- Sentry Issue: [link]
- PR with fix: [link]
- Slack thread: [link]
- Related incidents: [links]

---

## MCP Commands Used

```bash
# Sentry - Get issue details
mcp__sentry__get_issue(issueId="xxx")

# Sentry - Get related events
mcp__sentry__get_issue_events(issueId="xxx", limit=10)

# Vercel - Check recent deployments
mcp__vercel__list_deployments(projectId="xxx")

# Vercel - Get build logs
mcp__vercel__get_deployment_build_logs(deploymentId="xxx")

# GitHub - Check recent commits
mcp__github__get_commits(owner="xxx", repo="xxx", since="YYYY-MM-DD")
```
