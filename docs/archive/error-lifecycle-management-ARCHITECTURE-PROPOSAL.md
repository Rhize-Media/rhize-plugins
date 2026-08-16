# Error Lifecycle Management - Architecture Proposal

> **Status:** Proposal for v3.0 Restructure
> **Based On:** data-mutation-consistency v2 architecture
> **Goal:** Transform from workflow documentation to operational skill with commands, hooks, and sub-skills

---

## Platform & Configuration

### Supported Stack
- **Deployment:** Vercel (primary), extensible to other platforms
- **Framework:** Next.js (App Router)
- **Error Tracking:** Sentry
- **Version Control:** Git

### Command Prefix Configuration

Commands use a configurable prefix. Set in `.claude/skill-config.yaml`:

```yaml
error-lifecycle-management:
  command_prefix: "error"  # Results in /error:triage, /error:debug, etc.
  # Alternative: Use your initials like "jd" for /rhize-devflow:triage
```

**Default prefix:** `error` (e.g., `/error:triage`, `/error:debug`)

Throughout this document, `{prefix}` represents your configured prefix.

---

## Current State vs Target State

### Current (v2)
```
error-lifecycle-management/
├── SKILL.md                    # Workflow instructions only
├── reference/                  # Good - keep
├── reports/                    # Good - keep  
├── scripts/                    # Execution scripts exist but no CLI interface
└── templates/                  # Good - keep
```

### Target (v3)
```
error-lifecycle-management/
├── SKILL.md                    # Router (<500 lines)
├── README.md                   # Overview
├── commands/                   # ⭐ NEW: Slash commands
│   ├── triage-error.md
│   ├── debug-issue.md
│   ├── correlate-deployment.md
│   ├── analyze-coverage.md
│   └── incident-response.md
├── hooks/                      # ⭐ NEW: Automation triggers
│   ├── error-detector.sh
│   ├── sentry-context-loader.sh
│   ├── rca-enforcer.sh
│   └── regression-guard.sh
├── config/                     # ⭐ NEW: Configurable behavior
│   ├── severity-weights.yaml
│   ├── detection-patterns.yaml
│   └── workflow-modes.yaml
├── sub-skills/                 # ⭐ NEW: Specialized workflows
│   ├── production-errors.md
│   ├── build-failures.md
│   ├── performance-degradation.md
│   └── data-integrity.md
├── scripts/                    # Enhanced with CLI
│   ├── common/
│   ├── triage_error.py
│   ├── correlate_errors.py
│   ├── analyze_coverage.py
│   └── generate_rca.py
├── reference/                  # Expanded
│   ├── error-patterns.md
│   ├── sentry-queries.md
│   ├── performance-optimization.md
│   ├── rca-templates.md
│   └── incident-playbooks.md
└── templates/
    ├── triage-summary.md
    ├── rca-report.md
    ├── incident-response.md
    └── fix-verification.md
```

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│           ERROR LIFECYCLE MANAGEMENT SKILL (Router)             │
│           Platform: Configurable (Default: Vercel/Next/Sentry)  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────┐  ┌──────────────────┐  ┌────────────────┐ │
│  │  production-     │  │  build-          │  │  performance-  │ │
│  │  errors          │  │  failures        │  │  degradation   │ │
│  │  Sub-Skill       │  │  Sub-Skill       │  │  Sub-Skill     │ │
│  └──────────────────┘  └──────────────────┘  └────────────────┘ │
│         │                      │                     │          │
│         └──────────────────────┼─────────────────────┘          │
│                                │                                 │
│         ┌──────────────────────▼───────────────────────┐        │
│         │           Root Cause Analysis                │        │
│         │           (Mandatory Gate)                   │        │
│         └──────────────────────────────────────────────┘        │
│                                │                                 │
│         ┌──────────────────────▼───────────────────────┐        │
│         │     MCP Integration Layer                     │        │
│         │  Sentry ↔ Vercel ↔ Git ↔ Zen                 │        │
│         └──────────────────────────────────────────────┘        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Commands

### 1. `/{prefix}:triage`

**File:** `commands/triage-error.md`

```markdown
# /{prefix}:triage

Emergency triage for production errors.

## Aliases
- `@triage-error`
- `/{prefix}:triage [sentry-url|issue-id]`

## Usage
```
/{prefix}:triage https://sentry.io/issues/12345
/{prefix}:triage --recent          # Last 24h critical errors
/{prefix}:triage --user [user-id]  # Errors affecting specific user
```

## What This Command Does

1. **Fetch Error Context**
   - Sentry: get_issue details, events, breadcrumbs
   - Identify affected users, frequency, first/last seen
   - Extract stack trace and error fingerprint

2. **Correlate with Deployments**
   - Vercel: recent deployments around error time
   - Git: commits in deployment window
   - Identify likely culprit commit

3. **Assess Severity**
   - User impact (count, percentage)
   - Business impact (payments, auth, core features)
   - Data integrity risk

4. **Generate Triage Summary**
   - Write to `.claude/triage/triage-{issue-id}.md`
   - Return actionable summary to chat

## Execution

```bash
python3 scripts/triage_error.py \
    --sentry-url "$SENTRY_URL" \
    --output ".claude/triage"
```

## Example Output

```
## Triage: TypeError in FormSubmission

**Severity:** 🔴 CRITICAL (P0)
**Users Affected:** 47 (12% of active)
**First Seen:** 2024-12-14 10:23 UTC
**Likely Cause:** Deployment abc123 (2024-12-14 10:15)

**Root Files:**
- app/(routes)/submit/page.tsx:142
- lib/validation/schema.ts:28

**Correlation:**
- Commit: "Update form validation" by @developer
- Changed: schema.ts (validation rules)

**Next Steps:**
1. Run `/{prefix}:debug app/(routes)/submit/page.tsx`
2. Or rollback: `vercel rollback abc123`

📄 Full triage: `.claude/triage/triage-12345.md`
```
```

---

### 2. `/{prefix}:debug`

**File:** `commands/debug-issue.md`

```markdown
# /{prefix}:debug

Structured debugging workflow with mandatory RCA.

## Aliases
- `@debug`
- `/{prefix}:debug [file|description]`

## Usage
```
/{prefix}:debug "form submissions failing silently"
/{prefix}:debug app/actions/submit.ts --error "undefined is not iterable"
/{prefix}:debug --continue   # Resume previous debug session
```

## Workflow Phases

### Phase 1: Problem Definition
- What's the observable symptom?
- What's the expected behavior?
- When did this start?
- Reproducibility?

### Phase 2: Hypothesis Formation (REQUIRED)
Claude MUST list at least 3 hypotheses before ANY code changes:
1. [Hypothesis A] - Evidence for/against
2. [Hypothesis B] - Evidence for/against
3. [Hypothesis C] - Evidence for/against

### Phase 3: Evidence Gathering
- Sentry context (if available)
- Git history of affected files
- Related code patterns

### Phase 4: Root Cause Identification
- Must answer WHY, not just WHERE
- Document how this shipped

### Phase 5: Fix Planning
- Impact analysis (dependency graph)
- Test-first approach
- Smallest change possible

## Hard Stop Triggers

If Claude attempts these phrases, BLOCK and require RCA:
- "Let me try this quick fix..."
- "This should work..."
- "Let's just change this one line..."
- "Try this and see..."

## Output

Writes RCA document to `.claude/debug/rca-{timestamp}.md`
```

---

### 3. `/{prefix}:correlate`

**File:** `commands/correlate-deployment.md`

```markdown
# /{prefix}:correlate

Correlate errors with deployment timeline.

## Aliases
- `@correlate-errors`
- `/{prefix}:deployment-errors`

## Usage
```
/{prefix}:correlate                         # Last 24h
/{prefix}:correlate --since 2024-12-10
/{prefix}:correlate --deployment abc123
```

## What This Command Does

1. **Fetch Deployment History**
   - Vercel: list_deployments with timestamps
   - Extract: deployment IDs, git commits, status

2. **Fetch Error Timeline**
   - Sentry: issues sorted by first_seen
   - Match error timestamps to deployment windows

3. **Generate Correlation Matrix**

| Deployment | Time | Commit | New Errors | Error Spike |
|------------|------|--------|------------|-------------|
| abc123 | 10:15 | feat: add feature | 3 | +200% |
| def456 | 09:00 | fix: resolve issue | 0 | -10% |

4. **Identify Suspects**
   - Flag deployments with error spikes
   - Link to specific commits

## Example Output

```
## Deployment-Error Correlation

**Analysis Period:** 2024-12-13 to 2024-12-14

**🚨 Suspect Deployment:**
- **ID:** abc123
- **Time:** 2024-12-14 10:15 UTC
- **Commit:** "Update validation logic"
- **New Errors:** 3 unique issues
- **Error Rate:** +200% vs previous

**Recommendation:** Investigate or rollback

📄 Full report: `.claude/analysis/deployment-correlation-{date}.md`
```
```

---

### 4. `/{prefix}:coverage`

**File:** `commands/analyze-coverage.md`

```markdown
# /{prefix}:coverage

Analyze error handling coverage across codebase.

## Aliases
- `@error-coverage`
- `/{prefix}:analyze-coverage`

## Usage
```
/{prefix}:coverage                     # Full scan
/{prefix}:coverage --focus app/actions # Specific directory
/{prefix}:coverage --type server-actions
/{prefix}:coverage --type react-query
/{prefix}:coverage --type api-routes
```

## Analysis Types

### Server Actions
- try/catch wrapping
- Sentry.captureException usage
- Typed error responses
- User-facing error messages

### React Query
- onError handlers
- Error boundaries
- Retry configuration
- Error state UI

### API Routes
- Error response formats
- Status code usage
- Logging/monitoring

## Scoring

| Score | Status | Meaning |
|-------|--------|---------|
| ≥ 9.0 | ✅ Excellent | Comprehensive error handling |
| 7.0-8.9 | ⚠️ Warning | Gaps in coverage |
| < 7.0 | 🔴 Critical | Significant gaps |

## Example Output

```
## Error Coverage Analysis

**Overall Score:** 7.8/10 ⚠️

**By Category:**
- Server Actions: 8.2/10 ✅
- React Query: 7.1/10 ⚠️
- API Routes: 8.5/10 ✅

**Top Gaps:**
1. 🔴 Missing error boundary (app/(routes)/dashboard/page.tsx)
2. ⚠️ No onError handler (hooks/useUpdateItem.ts)
3. ⚠️ Silent failure (lib/api/fetch-data.ts)

📄 Full report: `.claude/analysis/error-coverage-{date}.md`
```
```

---

### 5. `/{prefix}:incident`

**File:** `commands/incident-response.md`

```markdown
# /{prefix}:incident

Initialize incident response protocol for critical production issues.

## Aliases
- `@incident`
- `/{prefix}:war-room`

## Usage
```
/{prefix}:incident --severity P0 "Payment processing failing"
/{prefix}:incident --sentry https://sentry.io/issues/12345
```

## Severity Levels

| Level | Criteria | Response Time |
|-------|----------|---------------|
| P0 | >50% users affected, payments, auth | Immediate |
| P1 | >10% users affected, core features | <1 hour |
| P2 | <10% users, non-critical | <4 hours |

## Incident Protocol

1. **Acknowledge**
   - Create incident document
   - Log start time
   - Identify owner

2. **Assess**
   - Run `/{prefix}:triage`
   - Determine blast radius
   - Decide: fix forward or rollback

3. **Mitigate**
   - If rollback: `vercel rollback [deployment-id]`
   - If hotfix: expedited review process

4. **Communicate**
   - Update status page (if applicable)
   - Notify stakeholders

5. **Resolve**
   - Verify fix in production
   - Monitor error rates
   - Close incident

6. **Post-Mortem**
   - Document timeline
   - Identify root cause
   - Define preventive actions

## Output

Creates incident document at `.claude/incidents/INC-{timestamp}.md`
```

---

## Hooks

### 1. `error-detector.sh` (UserPromptSubmit)

**File:** `hooks/error-detector.sh`

```bash
#!/bin/bash
# Hook: UserPromptSubmit
# Purpose: Detect error-related keywords and suggest appropriate commands

USER_MESSAGE="$1"
PREFIX="${SKILL_COMMAND_PREFIX:-error}"  # Configurable prefix

# Error keyword patterns
ERROR_PATTERNS=(
  "error|bug|crash|exception|broken"
  "not working|doesn't work|failed"
  "sentry|stack trace|traceback"
  "500|404|timeout|undefined"
  "production issue|prod down|outage"
)

# Check for matches
for pattern in "${ERROR_PATTERNS[@]}"; do
  if echo "$USER_MESSAGE" | grep -iE "$pattern" > /dev/null; then
    echo "🔍 Error-related query detected."
    echo ""
    echo "Available commands:"
    echo "  /${PREFIX}:triage [sentry-url]  - Emergency triage"
    echo "  /${PREFIX}:debug [description]  - Structured debugging"
    echo "  /${PREFIX}:correlate            - Check recent deployments"
    echo ""
    exit 0
  fi
done
```

---

### 2. `sentry-context-loader.sh` (UserPromptSubmit)

**File:** `hooks/sentry-context-loader.sh`

```bash
#!/bin/bash
# Hook: UserPromptSubmit
# Purpose: Auto-load Sentry context when issue URL detected

USER_MESSAGE="$1"
PREFIX="${SKILL_COMMAND_PREFIX:-error}"

# Detect Sentry URLs
SENTRY_URL=$(echo "$USER_MESSAGE" | grep -oE 'https://[^/]+\.sentry\.io/issues/[0-9]+')

if [ -n "$SENTRY_URL" ]; then
  echo "📡 Sentry issue detected. Loading context..."
  echo ""
  echo "Suggested: Run /${PREFIX}:triage $SENTRY_URL"
  echo ""
fi
```

---

### 3. `rca-enforcer.sh` (PreToolUse)

**File:** `hooks/rca-enforcer.sh`

```bash
#!/bin/bash
# Hook: PreToolUse (Write/Edit)
# Purpose: Enforce RCA before "quick fixes"

TOOL_NAME="$1"
FILE_PATH="$2"
PROPOSED_CONTENT="$3"

# Only check for write/edit operations
if [[ "$TOOL_NAME" != "Write" && "$TOOL_NAME" != "Edit" ]]; then
  exit 0
fi

# Check if we're in a debug session
DEBUG_SESSION=$(cat .claude/state/debug-session.json 2>/dev/null | jq -r '.active')

if [ "$DEBUG_SESSION" != "true" ]; then
  # Check if this looks like a bug fix without RCA
  QUICK_FIX_PATTERNS=(
    "// quick fix"
    "// temp fix"
    "// hack"
    "// TODO: investigate"
  )
  
  for pattern in "${QUICK_FIX_PATTERNS[@]}"; do
    if echo "$PROPOSED_CONTENT" | grep -i "$pattern" > /dev/null; then
      echo "⚠️ RCA ENFORCER: Quick fix detected without active debug session."
      echo ""
      echo "Before making this change, run:"
      echo "  /{prefix}:debug [description of issue]"
      echo ""
      echo "This ensures we understand the root cause before fixing."
      exit 1
    fi
  done
fi

exit 0
```

---

### 4. `regression-guard.sh` (PreToolUse)

**File:** `hooks/regression-guard.sh`

```bash
#!/bin/bash
# Hook: PreToolUse (Write/Edit)
# Purpose: Check if file was recently involved in a bug fix

TOOL_NAME="$1"
FILE_PATH="$2"

if [[ "$TOOL_NAME" != "Write" && "$TOOL_NAME" != "Edit" ]]; then
  exit 0
fi

# Check recent bug fixes involving this file
RECENT_FIXES=$(cat .claude/debug/recent-fixes.json 2>/dev/null | \
  jq -r --arg file "$FILE_PATH" '.[] | select(.files[] == $file) | .id')

if [ -n "$RECENT_FIXES" ]; then
  echo "⚠️ REGRESSION GUARD: This file was recently modified in bug fix(es):"
  echo "$RECENT_FIXES"
  echo ""
  echo "Please ensure your changes don't reintroduce previous issues."
  echo "Review: .claude/debug/rca-*.md for context."
  echo ""
fi

exit 0
```

---

## Sub-Skills

### 1. `production-errors.md`

**File:** `sub-skills/production-errors.md`

```markdown
# Production Errors Sub-Skill

> Specialized workflow for runtime production errors.

## Auto-Detect
Activates when:
- Sentry issue URL provided
- Keywords: "production", "prod", "live", "users affected"
- Error severity >= P1

## Workflow

### Immediate Actions (< 5 minutes)
1. Assess user impact via Sentry
2. Check if rollback is viable
3. Determine if data corruption risk exists

### Investigation (< 30 minutes)
1. Full triage with `/{prefix}:triage`
2. Deployment correlation
3. Root cause hypothesis

### Resolution
1. Decide: rollback vs hotfix
2. If hotfix: test in staging first
3. Deploy with monitoring
4. Verify resolution in Sentry

## Escalation Criteria
- >100 users affected → P0 incident
- Payment/auth failures → P0 incident
- Data integrity risk → STOP all operations
```

---

### 2. `build-failures.md`

**File:** `sub-skills/build-failures.md`

```markdown
# Build Failures Sub-Skill

> Specialized workflow for Vercel/Next.js build failures.

## Auto-Detect
Activates when:
- Vercel deployment failed
- Keywords: "build failed", "deployment error", "vercel error"
- TypeScript/ESLint errors in build log

## Common Patterns

### Type Errors
```
Error: Type 'X' is not assignable to type 'Y'
```
**Resolution:** Check recent type changes, run `pnpm typecheck` locally

### Import Errors
```
Module not found: Can't resolve 'X'
```
**Resolution:** Check package.json, verify import paths

### Environment Variables
```
Error: Missing required env var 'X'
```
**Resolution:** Check Vercel project settings, .env.example

## Workflow

1. **Get Build Logs**
   - Vercel MCP: `get_deployment_build_logs`
   - Extract error messages

2. **Categorize Error**
   - Type error → Check types
   - Import error → Check dependencies
   - Runtime error → Check SSR compatibility

3. **Local Reproduction**
   - Run `pnpm build` locally
   - Same error? Fix locally first

4. **Fix and Verify**
   - Apply fix
   - Push to preview branch
   - Verify deployment succeeds
```

---

### 3. `performance-degradation.md`

**File:** `sub-skills/performance-degradation.md`

```markdown
# Performance Degradation Sub-Skill

> Specialized workflow for performance issues.

## Auto-Detect
Activates when:
- Keywords: "slow", "performance", "timeout", "memory leak"
- Sentry performance issues flagged
- User complaints about speed

## Metrics to Gather

### Web Vitals
- LCP (Largest Contentful Paint)
- FID (First Input Delay)
- CLS (Cumulative Layout Shift)

### Server Metrics
- API response times
- Database query times
- Memory usage

## Common Causes

### Frontend
- Large bundle size
- Unoptimized images
- Blocking JavaScript
- Memory leaks in React

### Backend
- N+1 queries
- Missing database indexes
- Unoptimized API responses
- Connection pool exhaustion

## Workflow

1. **Identify Scope**
   - Specific page or global?
   - Frontend or backend?
   - Since when?

2. **Gather Metrics**
   - Vercel Analytics
   - Sentry Performance
   - Database metrics

3. **Profile**
   - React DevTools (frontend)
   - Database explain plans (backend)
   - Network waterfall

4. **Optimize**
   - Apply targeted fix
   - Measure improvement
   - Document baseline
```

---

### 4. `data-integrity.md`

**File:** `sub-skills/data-integrity.md`

```markdown
# Data Integrity Sub-Skill

> Specialized workflow for data corruption or inconsistency issues.

## Auto-Detect
Activates when:
- Keywords: "data corruption", "inconsistent data", "wrong data"
- Database constraint violations in errors
- User reports of missing or incorrect data

## CRITICAL: Stop Conditions

If data integrity is at risk:
1. **STOP** all write operations immediately
2. **DO NOT** attempt fixes without backup verification
3. **ESCALATE** to P0 incident

## Workflow

### Assessment
1. Identify scope of affected data
2. Determine if corruption is ongoing
3. Check for backup availability

### Investigation
1. Review recent migrations
2. Check for race conditions
3. Audit write operations in affected area

### Recovery
1. Restore from backup if needed
2. Apply surgical fixes with full audit trail
3. Verify data consistency post-fix

### Prevention
1. Add database constraints
2. Implement data validation
3. Add monitoring for anomalies
```



---

## Config Files

### `severity-weights.yaml`

**File:** `config/severity-weights.yaml`

```yaml
# Error Severity Scoring Weights
# Customize these for your application's priorities

user_impact:
  users_affected_percentage:
    ">50%": 10.0
    ">20%": 8.0
    ">10%": 6.0
    ">1%": 4.0
    "<1%": 2.0

feature_criticality:
  # Adjust these categories for your app
  payments: 10.0
  authentication: 10.0
  registration: 8.0
  core_features: 6.0
  secondary_features: 4.0
  cosmetic: 2.0

data_integrity:
  corruption_risk: 10.0
  inconsistency_risk: 7.0
  no_data_impact: 0.0

frequency:
  every_request: 10.0
  frequent: 7.0
  occasional: 4.0
  rare: 2.0

# Composite score = sum(weights) / max_possible * 10
# P0 >= 8.0, P1 >= 5.0, P2 < 5.0
```

---

### `detection-patterns.yaml`

**File:** `config/detection-patterns.yaml`

```yaml
# Error Detection Patterns
# Add project-specific patterns as needed

keywords:
  critical:
    - "payment failed"
    - "auth error"
    - "data corruption"
    - "500 error"
    - "production down"
  
  high:
    - "error"
    - "bug"
    - "broken"
    - "not working"
    - "exception"
  
  medium:
    - "slow"
    - "performance"
    - "timeout"
    - "warning"

sentry_patterns:
  - regex: 'https://[^/]+\.sentry\.io/issues/\d+'
    action: auto_triage
  
  - regex: 'SENTRY-\d+'
    action: lookup_issue

quick_fix_blockers:
  - "// quick fix"
  - "// temp fix"  
  - "// hack"
  - "// TODO: investigate later"
  - "// FIXME"

rca_required_triggers:
  - second_attempt_same_file
  - revert_detected
  - multiple_changes_same_area
```

---

### `workflow-modes.yaml`

**File:** `config/workflow-modes.yaml`

```yaml
# Workflow Mode Configuration

modes:
  strict:
    description: "Full RCA required for all fixes"
    rca_required: always
    hypothesis_minimum: 3
    test_first: required
    multi_model_validation: complex_fixes
  
  standard:
    description: "RCA required for P0/P1, recommended for P2"
    rca_required: P0_P1
    hypothesis_minimum: 2
    test_first: recommended
    multi_model_validation: P0_only
  
  expedited:
    description: "Quick response for emergencies"
    rca_required: post_fix
    hypothesis_minimum: 1
    test_first: optional
    multi_model_validation: never
    time_limit: 30_minutes

default_mode: standard

# Override per severity
severity_modes:
  P0: expedited  # Fix first, RCA after
  P1: standard
  P2: standard
```

---

## Project Configuration

Projects can customize skill behavior via `.claude/skill-config.yaml`:

```yaml
# Error Lifecycle Management Configuration

error-lifecycle-management:
  # Command prefix (default: "error")
  # Use "error" for /error:triage or your initials for /rhize-devflow:triage
  command_prefix: "error"
  
  # Output directories
  output:
    triage: ".claude/triage"
    debug: ".claude/debug"
    analysis: ".claude/analysis"
    incidents: ".claude/incidents"
  
  # Workflow mode (strict | standard | expedited)
  mode: standard
  
  # Scoring thresholds
  thresholds:
    warning: 9.0
    critical: 7.0
  
  # MCP integrations (enable/disable based on available servers)
  integrations:
    sentry: true
    vercel: true
    zen: true
  
  # Project-specific critical features (customize for your app)
  critical_features:
    - "checkout"
    - "authentication"
    - "payment"
```

---

## Integration Points

### Sentry MCP

```typescript
// Required Sentry MCP tools
Sentry:list_issues          // Get recent issues
Sentry:get_issue            // Get specific issue details
Sentry:get_issue_events     // Get events for an issue
Sentry:get_performance      // Performance metrics
Sentry:resolve_issue        // Mark as resolved
```

### Vercel MCP

```typescript
// Required Vercel MCP tools
Vercel:list_deployments     // Recent deployments
Vercel:get_deployment       // Specific deployment
Vercel:get_build_logs       // Build output
// Note: rollback may require CLI or API
```

### Zen MCP (Optional)

```typescript
// Memory and analysis integration
zen:chat(...)               // Store debug context
zen:thinkdeep(...)          // Complex RCA analysis
zen:precommit(...)          // Validate fix before commit
```

### Git (Native or MCP)

```typescript
// Code history analysis
git log                     // Recent commits
git diff                    // Changes between commits
git blame                   // Line-by-line history
```

---

## Cross-Skill Integration

### → data-mutation-consistency

When investigating stale data bugs:
1. Skill suggests running mutation analysis
2. Cross-references cache invalidation patterns
3. Identifies revalidation gaps

### → context-engineering

- Uses session management for long debug sessions
- Leverages impact mapping before fixes
- Integrates with duplicate-check for fix validation

### → skill-refinement

- Captures error patterns discovered during debugging
- Adds anti-patterns to deprecated list
- Documents successful fix strategies

---

## Migration Plan

### Phase 1: Structure
- [ ] Create directories (commands, hooks, config, sub-skills)
- [ ] Move existing content to appropriate locations
- [ ] Create SKILL.md router

### Phase 2: Commands
- [ ] Implement `/{prefix}:triage`
- [ ] Implement `/{prefix}:debug`
- [ ] Implement `/{prefix}:correlate`
- [ ] Implement `/{prefix}:coverage`
- [ ] Implement `/{prefix}:incident`

### Phase 3: Hooks
- [ ] Implement `error-detector.sh`
- [ ] Implement `sentry-context-loader.sh`
- [ ] Implement `rca-enforcer.sh`
- [ ] Implement `regression-guard.sh`

### Phase 4: Config
- [ ] Create `severity-weights.yaml`
- [ ] Create `detection-patterns.yaml`
- [ ] Create `workflow-modes.yaml`

### Phase 5: Sub-Skills
- [ ] Write `production-errors.md`
- [ ] Write `build-failures.md`
- [ ] Write `performance-degradation.md`
- [ ] Write `data-integrity.md`

### Phase 6: Integration Testing
- [ ] Test with Sentry MCP
- [ ] Test with Vercel MCP
- [ ] Test with Zen MCP (if available)
- [ ] Cross-skill integration

---

## Quick Reference (Target State)

```
┌─────────────────────────────────────────────────────────────────┐
│           ERROR LIFECYCLE MANAGEMENT v3.0                       │
│           Command Prefix: {prefix} (configurable)               │
├─────────────────────────────────────────────────────────────────┤
│  COMMANDS:                                                       │
│  /{prefix}:triage [url]     → Emergency triage                  │
│  /{prefix}:debug [desc]     → Structured debugging with RCA     │
│  /{prefix}:correlate        → Error ↔ deployment correlation    │
│  /{prefix}:coverage         → Coverage analysis                 │
│  /{prefix}:incident         → P0 incident protocol              │
├─────────────────────────────────────────────────────────────────┤
│  HOOKS:                                                          │
│  error-detector.sh          → Suggest commands on error keywords│
│  sentry-context-loader.sh   → Auto-load Sentry issue context    │
│  rca-enforcer.sh            → Block quick fixes without RCA     │
│  regression-guard.sh        → Warn on recently-fixed files      │
├─────────────────────────────────────────────────────────────────┤
│  SUB-SKILLS:                                                     │
│  production-errors          → Runtime error workflow            │
│  build-failures             → Build/deployment errors           │
│  performance-degradation    → Performance issue workflow        │
│  data-integrity             → Data corruption response          │
├─────────────────────────────────────────────────────────────────┤
│  INTEGRATIONS:                                                   │
│  Sentry MCP                 → Error details and events          │
│  Vercel MCP                 → Deployment correlation            │
│  Zen MCP                    → Complex RCA, context persistence  │
│  data-mutation-consistency  → Stale data debugging              │
└─────────────────────────────────────────────────────────────────┘
```

---

## Platform Extensibility

While this skill defaults to Vercel/Next.js/Sentry, the architecture supports other platforms:

### Alternative Deployment Platforms
- **Netlify:** Replace Vercel MCP calls with Netlify equivalents
- **AWS Amplify:** Use AWS SDK for deployment info
- **Railway/Render:** Adapt for respective APIs
- **Self-hosted:** Use SSH/API access to servers

### Alternative Error Tracking
- **Datadog:** Replace Sentry MCP with Datadog integration
- **Rollbar:** Adapt triage scripts for Rollbar API
- **LogRocket:** For frontend-focused error tracking
- **Custom:** Implement adapter for internal tools

### Configuration for Alternatives

```yaml
# .claude/skill-config.yaml
error-lifecycle-management:
  platform:
    deployment: vercel    # vercel | netlify | amplify | railway | custom
    error_tracking: sentry # sentry | datadog | rollbar | logrocket | custom
    
  # Custom platform adapters (when platform: custom)
  adapters:
    deployment: "./adapters/my-deployment-adapter.py"
    error_tracking: "./adapters/my-error-adapter.py"
```

---

## Changelog

### v3.0 (Proposed)
- Restructured from workflow documentation to operational skill
- Added commands, hooks, config, and sub-skills architecture
- Made platform-agnostic with configurable prefix
- Added cross-skill integration points

### v2.0
- Initial skill with SKILL.md workflow instructions
- Reference documentation for error patterns
- Template files for triage and RCA
