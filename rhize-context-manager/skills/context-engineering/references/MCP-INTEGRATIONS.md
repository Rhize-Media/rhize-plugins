# MCP Integrations Reference

> Integration patterns for MCP servers in context engineering

---

## Integration Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    CONTEXT ENGINEERING LAYER                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │   ZEN MCP    │  │ GRAPHITI MCP │  │     DEBUG STACK      │  │
│  │   (Context)  │  │  (Knowledge) │  │  (Sentry/Vercel/Git) │  │
│  ├──────────────┤  ├──────────────┤  ├──────────────────────┤  │
│  │ save_context │  │ store_entity │  │ get_sentry_issues    │  │
│  │ get_context  │  │ query_graph  │  │ get_vercel_logs      │  │
│  │ list_keys    │  │ find_related │  │ git_log/blame/diff   │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
│         │                 │                      │              │
│         └─────────────────┴──────────────────────┘              │
│                           │                                      │
│                    ORCHESTRATION                                 │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Zen MCP Integration

### Purpose
Persist and restore session context across conversations.

### Key Operations

**Save Context:**
```typescript
// Save current session state
zen.save_context({
  key: "feature-auth-v2",
  content: {
    summary: "Implementing OAuth2 authentication",
    files_modified: ["src/auth/oauth.ts", "src/lib/session.ts"],
    decisions: ["Using PKCE flow", "Storing tokens in httpOnly cookies"],
    blockers: [],
    next_steps: ["Implement refresh token rotation"]
  },
  metadata: {
    project: "current-project",
    type: "feature",
    created_at: new Date().toISOString()
  }
});
```

**Restore Context:**
```typescript
// Restore saved session
const context = await zen.get_context({ key: "feature-auth-v2" });

// Returns saved content with metadata
// Use to hydrate new session
```

**List Saved Contexts:**
```typescript
// Find relevant saved contexts
const contexts = await zen.list_keys({
  prefix: "feature-",
  project: "current-project"
});
```

### Key Naming Convention

```
{type}-{feature/topic}-{version}

Examples:
- feature-auth-v1
- debug-payment-error-20240115
- research-state-management
- review-pr-123
```

### Zen MCP Patterns

**Session Continuation:**
```markdown
1. Check for saved context: zen.list_keys({ prefix: current_feature })
2. If found: zen.get_context({ key })
3. Load into session state
4. Continue work
5. On pause/complete: zen.save_context({ key, content })
```

**Multi-Model Validation:**
```markdown
1. Complete implementation with primary model
2. Save context: zen.save_context({ key: "validation-{feature}" })
3. Switch to validation model
4. Restore: zen.get_context({ key })
5. Request review/validation
6. Merge feedback
```

---

## Graphiti MCP Integration

### Purpose
Store and query entities and relationships in knowledge graph.

### Entity Types

```yaml
entity_types:
  component:
    description: Code component (file, function, class)
    properties:
      - name
      - path
      - type (file|function|class|hook)
      - dependencies
      
  pattern:
    description: Established coding pattern
    properties:
      - name
      - description
      - example_location
      - use_cases
      
  decision:
    description: Architecture/design decision
    properties:
      - description
      - rationale
      - date
      - alternatives_considered
      
  error:
    description: Known error type
    properties:
      - type
      - symptoms
      - common_causes
      
  solution:
    description: Verified fix for error
    properties:
      - error_ref
      - description
      - verification_status
```

### Key Operations

**Store Entity:**
```typescript
graphiti.store_entity({
  type: "pattern",
  name: "server-action-mutation",
  properties: {
    description: "Use server actions for data mutations",
    example_location: "src/actions/user.ts",
    use_cases: ["form submissions", "data updates"]
  },
  relationships: [
    { type: "used_in", target: "component:UserForm" }
  ]
});
```

**Query Relationships:**
```typescript
// Find all patterns used in a component
const patterns = await graphiti.query({
  from: { type: "component", name: "UserDashboard" },
  relationship: "uses_pattern",
  to: { type: "pattern" }
});

// Find solutions for an error type
const solutions = await graphiti.query({
  from: { type: "error", name: "NEXT_REDIRECT" },
  relationship: "solved_by",
  to: { type: "solution" }
});
```

**Find Related:**
```typescript
// Find components affected by a change
const affected = await graphiti.find_related({
  entity: { type: "component", path: "src/lib/auth.ts" },
  depth: 2,  // Up to 2 relationship hops
  relationship_types: ["imports", "depends_on"]
});
```

### Graphiti vs Vector DB

| Use Case | Graphiti | Vector DB |
|----------|----------|-----------|
| Entity relationships | ✅ Best | ❌ Not suited |
| Semantic similarity | ❌ Not suited | ✅ Best |
| Structured queries | ✅ Good | ⚠️ Limited |
| Pattern discovery | ✅ Good | ⚠️ Limited |
| Fuzzy text search | ⚠️ Limited | ✅ Good |

**Hybrid Approach:**
- Store entities and relationships in Graphiti
- Store memory embeddings in vector DB
- Query both for comprehensive retrieval

---

## Debug Stack Integration

### Sentry MCP

**Get Recent Issues:**
```typescript
const issues = await sentry.get_issues({
  project: "current-project",
  status: "unresolved",
  limit: 10,
  sort: "last_seen"
});
```

**Get Error Details:**
```typescript
const details = await sentry.get_error_details({
  issue_id: "12345",
  include: ["stacktrace", "breadcrumbs", "tags", "user"]
});
```

**Search Similar Errors:**
```typescript
const similar = await sentry.search({
  query: "TypeError: Cannot read property",
  project: "current-project",
  timeframe: "7d"
});
```

### Vercel MCP

**Get Deployment Status:**
```typescript
const deployment = await vercel.get_deployment({
  project: "current-project",
  environment: "production"
});
```

**Get Build Logs:**
```typescript
const logs = await vercel.get_deployment_logs({
  deployment_id: "dpl_xxx",
  type: "build"  // or "runtime"
});
```

**List Recent Deployments:**
```typescript
const deployments = await vercel.list_deployments({
  project: "current-project",
  limit: 5,
  status: "error"  // Filter to failed deployments
});
```

### Git Integration

**Recent Changes:**
```typescript
// Get recent commits
const commits = await git.log({
  paths: ["src/components/"],
  since: "3 days ago",
  limit: 20
});
```

**Blame Analysis:**
```typescript
// Find who changed what
const blame = await git.blame({
  path: "src/lib/auth.ts",
  line_range: [45, 60]
});
```

**Diff for Regression:**
```typescript
// Compare versions
const diff = await git.diff({
  from: "HEAD~5",
  to: "HEAD",
  paths: ["src/auth/"]
});
```

---

## Integrated Workflows

### Error Investigation

```markdown
1. GET ERROR CONTEXT
   └── sentry.get_error_details({ issue_id })
   
2. GET DEPLOYMENT CONTEXT  
   └── vercel.get_deployment({ time: error_time })
   
3. GET CODE CHANGES
   └── git.log({ since: last_working_deployment })
   
4. QUERY SIMILAR ERRORS
   └── graphiti.query({ type: "error", similar_to: current })
   
5. CHECK KNOWN SOLUTIONS
   └── graphiti.query({ 
         from: { type: "error" }, 
         relationship: "solved_by" 
       })
   
6. INVESTIGATE
   └── Use combined context to debug
   
7. STORE SOLUTION (if found)
   └── graphiti.store_entity({ 
         type: "solution",
         error_ref: error_id,
         description: fix_description
       })
```

### Feature Development

```markdown
1. RESTORE CONTEXT (if continuing)
   └── zen.get_context({ key: feature_key })
   
2. LOAD PATTERNS
   └── graphiti.query({ 
         type: "pattern",
         relevant_to: feature_area 
       })
   
3. CHECK DEPENDENCIES
   └── graphiti.find_related({
         entity: affected_components,
         relationship: "depends_on"
       })
   
4. IMPLEMENT
   └── Use loaded context to guide work
   
5. SAVE PROGRESS
   └── zen.save_context({ 
         key: feature_key,
         content: current_state 
       })
   
6. STORE NEW PATTERNS
   └── graphiti.store_entity({ 
         type: "pattern",
         discovered_during: feature
       })
```

---

## Fallback Patterns

### When Zen MCP Unavailable

```markdown
FALLBACK CHAIN:
1. SESSION_CONTEXT.md (file in project root)
2. CURRENT_SPRINT.md (project status file)
3. Manual context in conversation

RECOVERY:
- Note Zen was unavailable
- Offer to sync when available
- Mark context as "local only"
```

### When Graphiti MCP Unavailable

```markdown
FALLBACK CHAIN:
1. COMPONENT_REGISTRY.md (file-based registry)
2. Grep/ripgrep for code search
3. Manual dependency tracing

RECOVERY:
- Queue writes for later sync
- Use file-based patterns
- Note degraded search capability
```

### When Debug Stack Unavailable

```markdown
IF Sentry Down:
- Request error details from user
- Use local logs
- Manual reproduction

IF Vercel Down:
- Check deployment status manually
- Use git for change history
- Local build for testing

IF Git Down:
- Work with current file state
- Note history unavailable
- Document changes manually
```

---

## MCP Tool Quick Reference

### Zen MCP Tools

| Tool | Purpose | Key Parameters |
|------|---------|----------------|
| `save_context` | Persist session | key, content, metadata |
| `get_context` | Restore session | key |
| `list_keys` | Find saved contexts | prefix, project |
| `delete_context` | Remove saved | key |

### Graphiti MCP Tools

| Tool | Purpose | Key Parameters |
|------|---------|----------------|
| `store_entity` | Add to graph | type, name, properties, relationships |
| `query` | Search graph | from, relationship, to |
| `find_related` | Traverse graph | entity, depth, relationship_types |
| `update_entity` | Modify entity | id, properties |

### Debug Stack Tools

| Tool | Purpose | Key Parameters |
|------|---------|----------------|
| `sentry.get_issues` | List errors | project, status, limit |
| `sentry.get_error_details` | Error info | issue_id, include |
| `vercel.get_deployment` | Deploy status | project, environment |
| `vercel.get_deployment_logs` | Build/runtime logs | deployment_id, type |
| `git.log` | Commit history | paths, since, limit |
| `git.blame` | Line attribution | path, line_range |
| `git.diff` | Compare versions | from, to, paths |
