# Payload CMS Hooks Sub-Skill

> **Parent Skill:** [data-mutation-consistency](../SKILL-data-mutation-consistency-v1.md)
> **Status:** Foundation Draft v1
> **Last Updated:** 2024-12-05
> **Library:** payload (v3.x)

---

## Overview

Extends the Data Mutation Consistency skill with Payload CMS lifecycle hook patterns. Enforces beforeChange validation, afterChange side effects, and cache coordination with Next.js revalidation.

## Detection

This sub-skill activates when `package.json` contains:
- `payload`
- `@payloadcms/next`

---

## Pattern Standards

### Collection Hook Structure (Required)

```typescript
// ✅ REQUIRED: app/payload/collections/{Entity}.ts

import { CollectionConfig } from 'payload';
import { 
  validateEntity,
  computeEntityFields,
  handleEntityCacheInvalidation,
  handleEntitySideEffects,
  cleanupEntityReferences,
} from '@/payload/hooks/{entity}';

export const Entities: CollectionConfig = {
  slug: 'entities',
  
  hooks: {
    // 1. BEFORE CHANGE (validation, computed fields)
    beforeChange: [
      validateEntity,           // Input validation
      computeEntityFields,      // Auto-calculated values
    ],
    
    // 2. AFTER CHANGE (side effects, cache)
    afterChange: [
      handleEntityCacheInvalidation,  // Next.js revalidation
      handleEntitySideEffects,        // Notifications, etc.
    ],
    
    // 3. AFTER DELETE (cleanup, cache)
    afterDelete: [
      handleEntityCacheInvalidation,
      cleanupEntityReferences,  // Remove from related records
    ],
  },
  
  // ... fields, access, etc.
};
```

### Cache Invalidation Hook (Required)

```typescript
// ✅ REQUIRED: payload/hooks/cache-invalidation.ts

import { CollectionAfterChangeHook, CollectionAfterDeleteHook } from 'payload';
import { revalidateTag, revalidatePath } from 'next/cache';

interface CacheConfig {
  tags: string[];
  paths?: string[];
}

export function createAfterChangeInvalidator(
  config: CacheConfig
): CollectionAfterChangeHook {
  return async ({ doc, operation }) => {
    // Invalidate cache tags
    for (const tag of config.tags) {
      revalidateTag(tag);
    }
    
    // Invalidate specific paths
    if (config.paths) {
      for (const path of config.paths) {
        // Support dynamic paths with doc data
        const resolvedPath = path.replace('{id}', doc.id);
        revalidatePath(resolvedPath);
      }
    }
    
    console.log(`[Cache] Invalidated: ${config.tags.join(', ')} (${operation})`);
    return doc;
  };
}

export function createAfterDeleteInvalidator(
  config: CacheConfig
): CollectionAfterDeleteHook {
  return async ({ doc }) => {
    for (const tag of config.tags) {
      revalidateTag(tag);
    }
    
    if (config.paths) {
      for (const path of config.paths) {
        const resolvedPath = path.replace('{id}', doc.id);
        revalidatePath(resolvedPath);
      }
    }
    
    console.log(`[Cache] Invalidated on delete: ${config.tags.join(', ')}`);
    return doc;
  };
}

// Usage in collection:
const Players: CollectionConfig = {
  slug: 'players',
  hooks: {
    afterChange: [
      createAfterChangeInvalidator({
        tags: ['players', 'teams'],  // Also invalidate related
        paths: ['/players', '/players/{id}'],
      }),
    ],
    afterDelete: [
      createAfterDeleteInvalidator({
        tags: ['players', 'teams'],
        paths: ['/players'],
      }),
    ],
  },
};
```

### beforeChange Validation Hook

```typescript
// ✅ STANDARD: payload/hooks/{entity}/validate.ts

import { CollectionBeforeChangeHook } from 'payload';
import { z } from 'zod';

const playerSchema = z.object({
  firstName: z.string().min(1),
  lastName: z.string().min(1),
  email: z.string().email(),
  teamId: z.string().optional(),
});

export const validatePlayer: CollectionBeforeChangeHook = async ({
  data,
  operation,
}) => {
  // Validate on create and update
  if (operation === 'create' || operation === 'update') {
    const result = playerSchema.safeParse(data);
    
    if (!result.success) {
      throw new Error(`Validation failed: ${result.error.message}`);
    }
  }
  
  return data;
};
```

### beforeChange Computed Fields Hook

```typescript
// ✅ STANDARD: payload/hooks/{entity}/compute.ts

import { CollectionBeforeChangeHook } from 'payload';

export const computePlayerFields: CollectionBeforeChangeHook = async ({
  data,
  operation,
}) => {
  // Computed: full name
  if (data.firstName && data.lastName) {
    data.fullName = `${data.firstName} ${data.lastName}`;
  }
  
  // Computed: slug
  if (operation === 'create' && data.fullName) {
    data.slug = data.fullName.toLowerCase().replace(/\s+/g, '-');
  }
  
  // Timestamp tracking
  data.updatedAt = new Date().toISOString();
  if (operation === 'create') {
    data.createdAt = new Date().toISOString();
  }
  
  return data;
};
```

### afterChange Side Effects Hook

```typescript
// ✅ STANDARD: payload/hooks/{entity}/side-effects.ts

import { CollectionAfterChangeHook } from 'payload';

export const handlePlayerSideEffects: CollectionAfterChangeHook = async ({
  doc,
  operation,
  req,
}) => {
  // Send welcome email on create
  if (operation === 'create' && doc.email) {
    await queueEmail({
      to: doc.email,
      template: 'welcome-player',
      data: { name: doc.firstName },
    });
  }
  
  // Notify team on status change
  if (operation === 'update' && doc.status === 'active') {
    await notifyTeam(doc.teamId, {
      type: 'player-activated',
      playerId: doc.id,
    });
  }
  
  // Audit log
  await createAuditLog({
    entity: 'player',
    entityId: doc.id,
    operation,
    userId: req.user?.id,
    timestamp: new Date(),
  });
  
  return doc;
};
```

### afterDelete Cleanup Hook

```typescript
// ✅ STANDARD: payload/hooks/{entity}/cleanup.ts

import { CollectionAfterDeleteHook } from 'payload';

export const cleanupPlayerReferences: CollectionAfterDeleteHook = async ({
  doc,
  req,
}) => {
  const payload = req.payload;
  
  // Remove from team roster
  if (doc.teamId) {
    await payload.update({
      collection: 'teams',
      id: doc.teamId,
      data: {
        players: doc.team?.players?.filter(p => p !== doc.id) || [],
      },
    });
  }
  
  // Delete related registrations
  await payload.delete({
    collection: 'registrations',
    where: {
      playerId: { equals: doc.id },
    },
  });
  
  return doc;
};
```

---

## Required Elements

| Element | Requirement | Weight | Check Pattern |
|---------|-------------|--------|---------------|
| afterChange hook | Required | 1.5 | Hook array not empty |
| Cache invalidation | Required | 1.5 | Uses revalidateTag/Path |
| afterDelete hook | Required | 1.3 | Hook array not empty |
| Delete cache invalidation | Required | 1.3 | revalidateTag in afterDelete |
| beforeChange validation | Recommended | 1.0 | Validation logic present |
| Computed fields | When needed | 0.8 | Auto-calculated values |
| Side effects | When needed | 0.8 | Emails, notifications |
| Cleanup on delete | When needed | 1.0 | Related record handling |
| Audit logging | Recommended | 0.6 | Operation tracking |

---

## Analysis Agent

### Detection Patterns

```yaml
patterns:
  collection_config:
    regex: "CollectionConfig\\s*=\\s*\\{"
    extract:
      - slug
      - hooks.beforeChange
      - hooks.afterChange
      - hooks.afterDelete
      
  cache_invalidation:
    regex: "revalidate(?:Tag|Path)\\s*\\("
    context: afterChange|afterDelete
    
  missing_hooks:
    regex: "hooks:\\s*\\{\\s*\\}"
    flag: violation
    
  empty_after_change:
    regex: "afterChange:\\s*\\[\\s*\\]"
    flag: violation
```

### Cross-Reference with Frontend

```yaml
cross_reference:
  # For each collection, check frontend query keys match cache tags
  
  collection: players
  cache_tags: ['players', 'teams']
  expected_query_keys:
    - playerKeys.all
    - playerKeys.lists
    - teamKeys.details  # Related invalidation
```

### Analysis Output

```markdown
# Payload CMS Hooks Analysis

## Collections Overview

| Collection | beforeChange | afterChange | afterDelete | Cache Tags | Score |
|------------|--------------|-------------|-------------|------------|-------|
| Players | ✅ 2 hooks | ✅ 2 hooks | ✅ 2 hooks | players, teams | 10.0 |
| Games | ✅ 1 hook | ✅ 1 hook | ❌ Missing | games | 7.5 |
| Teams | ✅ 1 hook | ❌ Missing | ❌ Missing | - | 5.0 |
| Seasons | ❌ Missing | ❌ Missing | ❌ Missing | - | 2.0 |

## Cache Invalidation Coverage

| Collection | afterChange Tags | afterDelete Tags | Related Collections |
|------------|------------------|------------------|---------------------|
| Players | ✅ players, teams | ✅ players, teams | Teams |
| Games | ✅ games, schedule | ❌ Missing | Schedule |
| Teams | ❌ Missing | ❌ Missing | Players, Games |
| Seasons | ❌ Missing | ❌ Missing | Games, Divisions |

## Frontend Cache Alignment

| Backend Tag | Frontend Query Keys | Aligned |
|-------------|---------------------|---------|
| players | playerKeys.all, playerKeys.lists | ✅ |
| games | gameKeys.all, gameKeys.lists | ✅ |
| teams | ❌ No teamKeys factory | ⚠️ |
| schedule | scheduleKeys.all | ✅ |

## Hook Implementation Quality

### Players Collection
- beforeChange: ✅ Validation, ✅ Computed fields
- afterChange: ✅ Cache invalidation, ✅ Welcome email
- afterDelete: ✅ Cache invalidation, ✅ Reference cleanup

### Games Collection  
- beforeChange: ✅ Validation
- afterChange: ✅ Cache invalidation
- afterDelete: ❌ Missing - stale cache on delete!

### Teams Collection
- beforeChange: ✅ Validation
- afterChange: ❌ Missing - frontend won't update!
- afterDelete: ❌ Missing - orphaned references!
```

---

## Scoring

### Score Calculation

```typescript
function scoreCollection(collection: CollectionAnalysis): number {
  const weights = {
    afterChangeHook: 1.5,
    afterChangeCacheInvalidation: 1.5,
    afterDeleteHook: 1.3,
    afterDeleteCacheInvalidation: 1.3,
    beforeChangeValidation: 1.0,
    computedFields: 0.8,
    sideEffects: 0.8,
    deleteCleanup: 1.0,
    auditLogging: 0.6,
  };
  
  let score = 0;
  let maxScore = 0;
  
  // Required
  if (collection.hasAfterChange) score += weights.afterChangeHook;
  maxScore += weights.afterChangeHook;
  
  if (collection.hasCacheInvalidation) score += weights.afterChangeCacheInvalidation;
  maxScore += weights.afterChangeCacheInvalidation;
  
  if (collection.hasAfterDelete) score += weights.afterDeleteHook;
  maxScore += weights.afterDeleteHook;
  
  if (collection.hasDeleteCacheInvalidation) score += weights.afterDeleteCacheInvalidation;
  maxScore += weights.afterDeleteCacheInvalidation;
  
  // Recommended
  if (collection.hasBeforeChangeValidation) score += weights.beforeChangeValidation;
  maxScore += weights.beforeChangeValidation;
  
  // Conditional
  if (collection.hasComputedFields) score += weights.computedFields;
  if (collection.needsComputedFields) maxScore += weights.computedFields;
  
  if (collection.hasSideEffects) score += weights.sideEffects;
  if (collection.needsSideEffects) maxScore += weights.sideEffects;
  
  if (collection.hasDeleteCleanup) score += weights.deleteCleanup;
  if (collection.hasRelatedCollections) maxScore += weights.deleteCleanup;
  
  if (collection.hasAuditLogging) score += weights.auditLogging;
  maxScore += weights.auditLogging;
  
  return (score / maxScore) * 10;
}
```

---

## Fix Templates

### Add afterChange Cache Invalidation

```typescript
// Add to collection hooks:

import { createAfterChangeInvalidator } from '@/payload/hooks/cache-invalidation';

hooks: {
  afterChange: [
    createAfterChangeInvalidator({
      tags: ['{collection}'],
      paths: ['/{collection}', '/{collection}/{id}'],
    }),
  ],
}
```

### Add afterDelete Hook

```typescript
// Add to collection hooks:

import { createAfterDeleteInvalidator } from '@/payload/hooks/cache-invalidation';

hooks: {
  afterDelete: [
    createAfterDeleteInvalidator({
      tags: ['{collection}'],
      paths: ['/{collection}'],
    }),
  ],
}
```

### Add beforeChange Validation

```typescript
// Create: payload/hooks/{collection}/validate.ts

import { CollectionBeforeChangeHook } from 'payload';
import { z } from 'zod';

const schema = z.object({
  // Define schema based on collection fields
});

export const validate{Collection}: CollectionBeforeChangeHook = async ({
  data,
  operation,
}) => {
  if (operation === 'create' || operation === 'update') {
    const result = schema.safeParse(data);
    if (!result.success) {
      throw new Error(`Validation failed: ${result.error.message}`);
    }
  }
  return data;
};
```

### Add Related Collection Invalidation

```typescript
// When collection affects others:

createAfterChangeInvalidator({
  tags: [
    '{collection}',           // Primary
    '{relatedCollection1}',   // Also invalidate related
    '{relatedCollection2}',
  ],
  paths: [
    '/{collection}',
    '/{collection}/{id}',
    '/{relatedCollection1}',  // Related paths
  ],
}),
```

---

## Anti-Pattern Triggers

Add to parent skill's deprecated-triggers:

```typescript
'payload-empty-hooks': {
  regex: /hooks:\s*\{\s*\}/,
  replacement: 'Add afterChange and afterDelete hooks',
  reason: 'Collections without hooks cause stale frontend cache',
  severity: 'error',
  context: 'collections/',
},

'payload-empty-after-change': {
  regex: /afterChange:\s*\[\s*\]/,
  replacement: 'Add cache invalidation hook',
  reason: 'afterChange must invalidate frontend cache',
  severity: 'error',
},

'payload-no-after-delete': {
  regex: /hooks:\s*\{[^}]*afterChange[^}]*\}(?![^}]*afterDelete)/s,
  replacement: 'Add afterDelete hook for cache invalidation',
  reason: 'Deleted records leave stale cache entries',
  severity: 'warning',
},

'payload-direct-revalidate': {
  regex: /afterChange.*revalidateTag\s*\(\s*['"][^'"]+['"]\s*\)/,
  replacement: 'Use createAfterChangeInvalidator helper',
  reason: 'Centralized cache invalidation is more maintainable',
  severity: 'info',
},
```

---

## Admin Panel Coordination

### The Problem

When admins modify data through Payload's admin panel, the same hooks fire. Ensure hooks handle both API and admin contexts:

```typescript
export const handlePlayerAfterChange: CollectionAfterChangeHook = async ({
  doc,
  operation,
  req,
}) => {
  // Cache invalidation runs for both API and admin
  revalidateTag('players');
  
  // Some side effects only for API (user-initiated)
  if (req.user && !req.payloadAPI) {
    // Admin panel operation
    await notifyAdminAction(doc, operation);
  }
  
  return doc;
};
```

---

## Integration

### With Parent Skill

```yaml
sub_skill_interface:
  name: payload-cms-hooks
  
  detection:
    packages:
      - "payload"
      - "@payloadcms/next"
      
  analysis:
    entry_points:
      - "app/payload/collections/**/*.ts"
      - "payload/collections/**/*.ts"
      - "collections/**/*.ts"
    
  scoring:
    contributes_to: backend_hooks
    weights_override:
      cache_invalidation: 1.5  # Critical for Next.js
      
  output:
    section: "Payload CMS Hooks"
    append_to: parent_report
```

### With React Query Sub-Skill

Cross-reference cache tags with query keys:

```yaml
cross_validation:
  - payload_tag: "players"
    expected_query_key: "playerKeys.all"
    
  - payload_tag: "games"  
    expected_query_key: "gameKeys.all"
```

---

## Quick Reference

```
┌─────────────────────────────────────────────────────────────────┐
│                 PAYLOAD CMS HOOKS SUB-SKILL                      │
├─────────────────────────────────────────────────────────────────┤
│  REQUIRED FOR ALL COLLECTIONS:                                   │
│  ✓ afterChange hook with cache invalidation                     │
│  ✓ afterDelete hook with cache invalidation                     │
│  ✓ Cache tags align with frontend query keys                    │
├─────────────────────────────────────────────────────────────────┤
│  RECOMMENDED:                                                    │
│  ✓ beforeChange validation (zod schema)                         │
│  ✓ beforeChange computed fields                                 │
│  ✓ afterChange side effects (emails, notifications)             │
│  ✓ afterDelete cleanup (related records)                        │
│  ✓ Audit logging                                                │
├─────────────────────────────────────────────────────────────────┤
│  CACHE INVALIDATION PATTERN:                                     │
│  Use createAfterChangeInvalidator({                             │
│    tags: ['primary', 'related'],                                │
│    paths: ['/route', '/route/{id}'],                            │
│  })                                                              │
├─────────────────────────────────────────────────────────────────┤
│  VIOLATIONS TO DETECT:                                           │
│  • Empty hooks object                                            │
│  • Missing afterDelete                                           │
│  • No cache invalidation                                         │
│  • Cache tags don't match frontend keys                         │
└─────────────────────────────────────────────────────────────────┘
```

---

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| v1 | 2024-12-05 | Initial - Payload v3 patterns with Next.js cache |
