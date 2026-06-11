# React Query Mutations Sub-Skill

> **Parent Skill:** [data-mutation-consistency](../SKILL-data-mutation-consistency-v1.md)
> **Status:** Foundation Draft v1
> **Last Updated:** 2024-12-05
> **Library:** @tanstack/react-query (v5.x)

---

## Overview

Extends the Data Mutation Consistency skill with React Query / TanStack Query specific patterns. Enforces optimistic updates, cache management, and error handling conventions.

## Detection

This sub-skill activates when `package.json` contains:
- `@tanstack/react-query`
- `react-query` (legacy v3)

---

## Pattern Standards

### Query Key Factory (Required)

```typescript
// ✅ REQUIRED: lib/query-keys/{domain}-keys.ts

export const playerKeys = {
  all: ['players'] as const,
  lists: () => [...playerKeys.all, 'list'] as const,
  list: (filters: PlayerFilters) => [...playerKeys.lists(), filters] as const,
  details: () => [...playerKeys.all, 'detail'] as const,
  detail: (id: string) => [...playerKeys.details(), id] as const,
} as const;

// Usage
queryKey: playerKeys.detail(playerId)
```

**Violations:**
```typescript
// ❌ Inline keys - breaks invalidation
queryKey: ['player', id]

// ❌ String keys - no type safety
queryKey: 'players'
```

### Complete Mutation Hook (Required for User-Facing)

```typescript
// ✅ REQUIRED: hooks/{domain}/use-update-{entity}.ts

export function useUpdatePlayer() {
  const queryClient = useQueryClient();
  
  return useMutation({
    // 1. MUTATION FUNCTION (Required)
    mutationFn: async ({ playerId, data }: UpdatePlayerParams) => {
      return updatePlayer(playerId, data); // From lib/api/
    },
    
    // 2. OPTIMISTIC UPDATE (Required for user-facing)
    onMutate: async ({ playerId, data }) => {
      // Cancel in-flight queries
      await queryClient.cancelQueries({ 
        queryKey: playerKeys.detail(playerId) 
      });
      
      // Snapshot for rollback
      const previousPlayer = queryClient.getQueryData(
        playerKeys.detail(playerId)
      );
      
      // Optimistically update
      queryClient.setQueryData(
        playerKeys.detail(playerId),
        (old: Player | undefined) => old ? { ...old, ...data } : old
      );
      
      // Return rollback context
      return { previousPlayer };
    },
    
    // 3. ERROR ROLLBACK (Required if optimistic)
    onError: (error, { playerId }, context) => {
      // Rollback to snapshot
      if (context?.previousPlayer) {
        queryClient.setQueryData(
          playerKeys.detail(playerId),
          context.previousPlayer
        );
      }
      // User feedback
      toast.error(getErrorMessage(error));
    },
    
    // 4. SUCCESS FEEDBACK (Recommended)
    onSuccess: (data, { playerId }) => {
      toast.success('Player updated');
    },
    
    // 5. CACHE INVALIDATION (Required)
    onSettled: (data, error, { playerId }) => {
      // Always invalidate to ensure consistency
      queryClient.invalidateQueries({ 
        queryKey: playerKeys.detail(playerId) 
      });
      queryClient.invalidateQueries({ 
        queryKey: playerKeys.lists() 
      });
    },
  });
}
```

### Convenience Hook Pattern

```typescript
// ✅ Convenience hooks MUST inherit parent patterns

// Parent hook with full patterns
export function useUpdatePlayer() {
  // ... full implementation above
}

// Convenience hook - inherits everything
export function useApprovePlayer() {
  const mutation = useUpdatePlayer();
  
  return {
    ...mutation,  // ✅ Spread to inherit all handlers
    mutate: (playerId: string) => 
      mutation.mutate({ playerId, data: { status: 'approved' } }),
    mutateAsync: (playerId: string) =>
      mutation.mutateAsync({ playerId, data: { status: 'approved' } }),
  };
}

// ❌ BAD: Loses optimistic updates
export function useApprovePlayer() {
  const mutation = useUpdatePlayer();
  return {
    mutate: (id: string) => mutation.mutate({ id, data: { status: 'approved' } }),
  };
}
```

---

## Required Elements

| Element | Requirement | Weight | Check Pattern |
|---------|-------------|--------|---------------|
| Query Key Factory | Required | 1.5 | Uses `{domain}Keys.` pattern |
| mutationFn | Required | 1.0 | Present in useMutation config |
| onMutate (optimistic) | Required* | 1.2 | *If user-facing mutation |
| Rollback context | Required* | 1.4 | *If onMutate present |
| onError handler | Required | 1.3 | Present with rollback logic |
| onSettled invalidation | Required | 1.4 | invalidateQueries called |
| Toast/feedback | Recommended | 0.8 | User notification on result |
| TypeScript params | Required | 1.0 | Typed mutation params |

---

## Analysis Agent

### Detection Patterns

```yaml
patterns:
  mutation_hook:
    regex: "useMutation\\s*\\(\\s*\\{"
    extract:
      - mutationFn
      - onMutate
      - onError
      - onSuccess
      - onSettled
      
  query_key_factory:
    regex: "export\\s+const\\s+(\\w+)Keys\\s*="
    extract:
      - factory_name
      - key_structure
      
  inline_key:
    regex: "queryKey:\\s*\\[(['\"][^'\"]+['\"])"
    flag: violation
    
  missing_spread:
    regex: "const\\s+mutation\\s*=\\s*use\\w+\\(\\)[^}]*return\\s*\\{[^.]*mutate:"
    flag: potential_issue
```

### Analysis Output

```markdown
# React Query Mutation Analysis

## Query Key Factories

| Domain | Factory | Keys Defined | Usage Count |
|--------|---------|--------------|-------------|
| players | playerKeys | 5 | 12 |
| games | gameKeys | 5 | 8 |
| teams | ❌ Missing | - | 3 inline |

## Mutation Hooks

| Hook | Factory | Optimistic | Rollback | Invalidation | Score |
|------|---------|------------|----------|--------------|-------|
| useUpdatePlayer | ✅ | ✅ | ✅ | ✅ | 10.0 |
| useCreateGame | ✅ | ✅ | ✅ | ✅ | 10.0 |
| useApprovePlayer | ⚠️ | ❌ | ❌ | ⚠️ | 6.5 |
| useDeleteTeam | ✅ | ❌ | N/A | ✅ | 8.5 |

## Convenience Hooks

| Hook | Parent | Inherits Handlers | Issue |
|------|--------|-------------------|-------|
| useApprovePlayer | useUpdatePlayer | ❌ No | Missing spread |
| useRejectPlayer | useUpdatePlayer | ❌ No | Missing spread |

## Inline Query Keys (Violations)

| File | Line | Key | Should Use |
|------|------|-----|------------|
| use-teams.ts | 24 | ['team', id] | teamKeys.detail(id) |
| use-teams.ts | 45 | ['teams'] | teamKeys.all |
```

---

## Scoring

### Score Calculation

```typescript
function scoreMutation(mutation: MutationAnalysis): number {
  const weights = {
    queryKeyFactory: 1.5,
    mutationFn: 1.0,
    onMutate: 1.2,
    rollbackContext: 1.4,
    onError: 1.3,
    onSettled: 1.4,
    typedParams: 1.0,
    userFeedback: 0.8,
  };
  
  let score = 0;
  let maxScore = 0;
  
  // Required elements
  if (mutation.hasQueryKeyFactory) score += weights.queryKeyFactory;
  maxScore += weights.queryKeyFactory;
  
  if (mutation.hasMutationFn) score += weights.mutationFn;
  maxScore += weights.mutationFn;
  
  // Conditional: optimistic only for user-facing
  if (mutation.isUserFacing) {
    if (mutation.hasOnMutate) score += weights.onMutate;
    maxScore += weights.onMutate;
    
    if (mutation.hasOnMutate && mutation.hasRollbackContext) {
      score += weights.rollbackContext;
    }
    if (mutation.hasOnMutate) maxScore += weights.rollbackContext;
  }
  
  if (mutation.hasOnError) score += weights.onError;
  maxScore += weights.onError;
  
  if (mutation.hasOnSettled) score += weights.onSettled;
  maxScore += weights.onSettled;
  
  if (mutation.hasTypedParams) score += weights.typedParams;
  maxScore += weights.typedParams;
  
  // Recommended
  if (mutation.hasUserFeedback) score += weights.userFeedback;
  maxScore += weights.userFeedback;
  
  return (score / maxScore) * 10;
}
```

---

## Fix Templates

### Missing Query Key Factory

```typescript
// Generate: lib/query-keys/{domain}-keys.ts

export const {domain}Keys = {
  all: ['{domain}'] as const,
  lists: () => [...{domain}Keys.all, 'list'] as const,
  list: (filters: {Domain}Filters) => [...{domain}Keys.lists(), filters] as const,
  details: () => [...{domain}Keys.all, 'detail'] as const,
  detail: (id: string) => [...{domain}Keys.details(), id] as const,
} as const;
```

### Missing Optimistic Update

```typescript
// Add to existing useMutation:

onMutate: async (variables) => {
  await queryClient.cancelQueries({ 
    queryKey: {domain}Keys.detail(variables.id) 
  });
  
  const previous = queryClient.getQueryData(
    {domain}Keys.detail(variables.id)
  );
  
  queryClient.setQueryData(
    {domain}Keys.detail(variables.id),
    (old) => old ? { ...old, ...variables.data } : old
  );
  
  return { previous };
},
```

### Missing Rollback

```typescript
// Add/update onError:

onError: (error, variables, context) => {
  if (context?.previous) {
    queryClient.setQueryData(
      {domain}Keys.detail(variables.id),
      context.previous
    );
  }
  toast.error('Failed to update {entity}');
},
```

### Missing Cache Invalidation

```typescript
// Add onSettled:

onSettled: (data, error, variables) => {
  queryClient.invalidateQueries({ 
    queryKey: {domain}Keys.detail(variables.id) 
  });
  queryClient.invalidateQueries({ 
    queryKey: {domain}Keys.lists() 
  });
},
```

### Fix Convenience Hook

```typescript
// Before (broken):
export function use{Action}{Entity}() {
  const mutation = useUpdate{Entity}();
  return {
    mutate: (id: string) => mutation.mutate({ id, data: { ... } }),
  };
}

// After (correct):
export function use{Action}{Entity}() {
  const mutation = useUpdate{Entity}();
  return {
    ...mutation,  // Inherit all handlers
    mutate: (id: string) => mutation.mutate({ id, data: { ... } }),
    mutateAsync: (id: string) => mutation.mutateAsync({ id, data: { ... } }),
  };
}
```

---

## Anti-Pattern Triggers

Add to parent skill's deprecated-triggers:

```typescript
'rq-inline-query-key': {
  regex: /queryKey:\s*\[['"][^'"]+['"]/,
  replacement: 'Use query key factory (e.g., playerKeys.detail(id))',
  reason: 'Inline keys cause invalidation bugs and reduce type safety',
  severity: 'warning',
},

'rq-optimistic-no-rollback': {
  regex: /onMutate[\s\S]*?setQueryData(?![\s\S]*?onError[\s\S]*?setQueryData)/,
  replacement: 'Add onError with rollback using context.previous',
  reason: 'Optimistic updates without rollback cause data inconsistency',
  severity: 'error',
},

'rq-convenience-no-spread': {
  regex: /const\s+mutation\s*=\s*use\w+\(\)[^}]*return\s*\{\s*mutate:/,
  replacement: 'Use {...mutation, mutate: ...} to inherit handlers',
  reason: 'Convenience hooks must inherit parent optimistic/error handling',
  severity: 'warning',
},

'rq-mutation-no-invalidation': {
  regex: /useMutation\s*\(\s*\{[^}]*mutationFn[^}]*\}(?![^}]*onSettled|invalidateQueries)/s,
  replacement: 'Add onSettled with invalidateQueries',
  reason: 'Mutations must invalidate affected queries',
  severity: 'error',
},
```

---

## Integration

### With Parent Skill

```yaml
# Parent skill loads this when detected
sub_skill_interface:
  name: react-query-mutations
  
  detection:
    packages:
      - "@tanstack/react-query"
      - "react-query"
      
  analysis:
    entry_points:
      - "hooks/**/use-*.ts"
      - "lib/query-keys/**"
    
  scoring:
    contributes_to: client_mutations
    weights_override:
      optimistic_ui: 1.2  # Higher for RQ
      cache_invalidation: 1.4
      
  output:
    section: "React Query Mutations"
    append_to: parent_report
```

---

## Quick Reference

```
┌─────────────────────────────────────────────────────────────────┐
│               REACT QUERY MUTATIONS SUB-SKILL                    │
├─────────────────────────────────────────────────────────────────┤
│  REQUIRED FOR ALL MUTATIONS:                                     │
│  ✓ Query key factory ({domain}Keys.detail(id))                  │
│  ✓ mutationFn from lib/api/                                     │
│  ✓ onError with user feedback                                   │
│  ✓ onSettled with invalidateQueries                             │
│  ✓ TypeScript typed parameters                                   │
├─────────────────────────────────────────────────────────────────┤
│  REQUIRED FOR USER-FACING:                                       │
│  ✓ onMutate with optimistic update                              │
│  ✓ Rollback context (return { previous })                       │
│  ✓ onError restores previous on failure                         │
├─────────────────────────────────────────────────────────────────┤
│  CONVENIENCE HOOKS:                                              │
│  ✓ MUST spread parent: {...mutation, mutate: ...}               │
│  ✗ Never just return {mutate: ...}                              │
├─────────────────────────────────────────────────────────────────┤
│  VIOLATIONS TO DETECT:                                           │
│  • Inline query keys                                             │
│  • Optimistic without rollback                                   │
│  • Missing invalidation                                          │
│  • Convenience hooks without spread                              │
└─────────────────────────────────────────────────────────────────┘
```

---

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| v1 | 2024-12-05 | Initial - TanStack Query v5 patterns |
