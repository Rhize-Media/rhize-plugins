---
name: error-lifecycle-management
tier: custom
domain: error-lifecycle
maturity: stable
description: >-
  End-to-end production error lifecycle for Next.js/TypeScript on Vercel — triage, root-cause
  analysis, deployment correlation, and fix verification using Sentry, Vercel, and GitHub. Use
  whenever the user mentions an "error", "bug", "crash", "exception", "stack trace", "500/404",
  "timeout", "failed deployment", "production issue/incident", "memory leak", "bundle size", or
  something is "slow" or "broken" — and when correlating an error spike to a recent deploy or
  commit. Leads the operational response (Sentry+Vercel correlation, P0/P1/P2 severity, incident
  protocol); complements the official engineering:* and sentry:* skills.
version: 2.0.0
metadata:
  rhize:
    topics: [observability, workflow-patterns]
    stacks: [sentry, vercel, nextjs]
    extends: [dev-flow-foundations]

---

## Overview
This skill provides systematic error lifecycle management from prevention through resolution, integrating Sentry for error tracking, Vercel for deployment monitoring, and GitHub for change correlation. It enables proactive error prevention, rapid root cause analysis, and performance optimization.

## Triggers
**Keywords:** error, bug, crash, exception, performance, slow, timeout, failed deployment, production issue, debug, troubleshoot, sentry, stack trace, memory leak, bundle size
**Scenarios:** Production errors, build failures, performance degradation, user-reported issues, deployment problems, API failures

## Quick Start Workflow

When an error occurs, follow this decision tree:
1. Identify error source (Runtime/Build/Performance/Unknown)
2. Execute appropriate analysis workflow
3. Perform root cause analysis
4. Generate and validate fix
5. Deploy and monitor

## Project Configuration

Create `.error-lifecycle.json` in your project root to configure paths:

```json
{
  "project_type": "monorepo",
  "frontend": {
    "root": "apps/web",
    "scan_dirs": ["app", "lib", "components", "hooks", "providers", "src"]
  },
  "backend": {
    "root": "apps/api",
    "scan_dirs": ["src", "lib"]
  },
  "api_patterns": ["fetch\\s*\\(", "axios\\.", "\\.get\\(", "\\.post\\("],
  "exclude_patterns": ["node_modules", "\\.next", "dist", "build", "__tests__"]
}
```

For single-repo projects:
```json
{
  "project_type": "single",
  "scan_dirs": ["app", "lib", "components", "src"],
  "api_patterns": ["fetch\\s*\\("]
}
```

## Primary Workflows

### 1. Production Error Response (CRITICAL PATH)
When production error is detected:
1. **Immediate Assessment** → Execute `scripts/triage_error.py`
2. **Fetch Context** → `Sentry:get_issue` with issue ID
3. **Check Impact** → `Sentry:get_issue_events` for affected users
4. **Correlate Changes** → `GitHub:get_commits` for recent deploys
5. **Generate Fix** → Follow fix patterns in `reference/error-patterns.md`

### 2. Build Failure Analysis
For Vercel build/deployment failures:
1. **Get Build Logs** → `Vercel:get_build_logs` 
2. **Identify Pattern** → Check `reference/error-patterns.md`
3. **Verify Dependencies** → Run `scripts/check_dependencies.js`
4. **Test Locally** → Use `scripts/reproduce_build.sh`

### 3. Performance Degradation
When performance issues arise:
1. **Collect Metrics** → `Sentry:get_performance_issues`
2. **Analyze Queries** → Run `scripts/analyze_performance.js`
3. **Check Bundle** → Execute `scripts/bundle_analyzer.js`
4. **Generate Report** → Use `templates/performance-report.md`

## MCP Tools Required

```typescript
// Sentry MCP Server
Sentry:get_issues          // List recent issues
Sentry:get_issue           // Get specific issue details
Sentry:get_issue_events    // Get events for an issue
Sentry:get_performance_issues // Performance monitoring

// Vercel MCP Server  
Vercel:get_deployments     // List recent deployments
Vercel:get_build_logs      // Get build output
Vercel:get_functions_logs  // Runtime logs
Vercel:get_environment     // Check env vars

// GitHub MCP Server
GitHub:get_commits         // Recent changes
GitHub:get_pull_request    // PR that may have caused issue
GitHub:create_issue        // Create bug ticket
GitHub:get_diff           // View code changes
```

## Error Prevention Setup

For new projects or features, implement proactive monitoring:
1. Run `scripts/setup_error_boundaries.ts` to add React error boundaries
2. Execute `scripts/implement_sentry.ts` for comprehensive Sentry setup
3. Add performance monitoring with `scripts/add_performance_tracking.ts`
4. Validate coverage using `scripts/validate_error_coverage.py`

## Critical Decision Points

**High Severity Error?** (>100 users affected)
→ Create incident with `templates/incident-response.md`
→ Notify team immediately
→ Begin war room protocol

**Performance Regression?** (>20% degradation)
→ Rollback deployment via `Vercel:rollback_deployment`
→ Analyze with `scripts/performance_bisect.sh`

**Data Corruption Risk?**
→ STOP all operations
→ Run `scripts/data_integrity_check.py`
→ Follow `reference/data-recovery.md`

## Scripts

### 🔧 EXECUTE - Validation Scripts
> **Usage:** Claude should RUN these scripts to validate codebase and generate reports.

| Script | Command | Purpose |
|--------|---------|---------|
| `validate_error_coverage.py` | `python3 scripts/validate_error_coverage.py --root .` | Scan for error handling gaps |
| `validate_server_action_errors.py` | `python3 scripts/validate_server_action_errors.py --root .` | Validate Server Action patterns |
| `validate_react_query_errors.py` | `python3 scripts/validate_react_query_errors.py --root .` | Validate React Query error handling |
| `triage_error.py` | `python3 scripts/triage_error.py` | Emergency triage for production incidents |

### ⚡ ONE-TIME EXECUTE - Project Setup Scripts
> **Usage:** Claude should RUN these ONCE per project for initial setup. Not for repeated use.

| Script | Command | Purpose |
|--------|---------|---------|
| `setup_error_boundaries.ts` | `npx ts-node scripts/setup_error_boundaries.ts` | Add React error boundaries to app routes |

### 📚 REFERENCE - Shared Modules (Do Not Execute Directly)
> **Usage:** These are imported by the validation scripts. Claude should NOT run these directly.

| Module | Purpose |
|--------|---------|
| `common/config.py` | Project configuration loader |
| `common/models.py` | Shared data models (Issue, Severity, Report) |
| `common/base_validator.py` | Base class for validators |
| `common/cli.py` | CLI argument parsing |
| `common/output.py` | Report formatting (JSON, Markdown) |

---

## References
> **Usage:** Claude should READ these for patterns and guidance.

- `reference/error-patterns.md` - Common error patterns and fixes
- `reference/sentry-queries.md` - Advanced Sentry query patterns
- `reference/performance-optimization.md` - Performance tuning guide

## Templates
> **Usage:** Claude should READ and FILL IN these templates when generating reports.

- `templates/incident-response.md` - Incident management template
- `templates/triage-summary.md` - Error triage output format
- `templates/pattern-doc.md` - Pattern documentation format
- `templates/validation-summary.md` - Validation report format
