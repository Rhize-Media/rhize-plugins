# Cross-Layer Validation: Backend ↔ Frontend Alignment

This document explains how to ensure cache consistency between backend mutations and frontend query caches.

## The Problem

```
┌─────────────────────────────────────────────────────────────────┐
│  BACKEND (Payload CMS / Server Actions)                         │
│  ═══════════════════════════════════════                        │
│  • Modifies data in database                                    │
│  • Calls revalidateTag('players')                               │
│  • Next.js data cache invalidated                               │
│                                                                  │
│  ↓ But what about...                                            │
│                                                                  │
│  FRONTEND (React Query)                                          │
│  ══════════════════════                                          │
│  • Has its own in-memory cache                                  │
│  • Doesn't know about revalidateTag                             │
│  • May show stale data until page refresh                       │
└─────────────────────────────────────────────────────────────────┘
```

## Solution: Aligned Naming

### Step 1: Use Consistent Entity Names

```typescript
// Backend cache tags
revalidateTag('players');
revalidateTag('games');
revalidateTag('teams');

// Frontend query key factories
export const playerKeys = {
  all: ['players'] as const,  // ✅ Matches 'players' tag
  // ...
};

export const gameKeys = {
  all: ['games'] as const,    // ✅ Matches 'games' tag
  // ...
};

export const teamKeys = {
  all: ['teams'] as const,    // ✅ Matches 'teams' tag
  // ...
};
```

### Step 2: Map Relationships

When a mutation affects multiple entities, invalidate all:

```typescript
// Backend: Player update might affect team roster
afterChange: [
  createAfterChangeInvalidator({
    tags: ['players', 'teams'],  // Invalidate both
    paths: ['/players', '/players/{id}', '/teams'],
  }),
],

// Frontend: Invalidate related queries
onSettled: () => {
  queryClient.invalidateQueries({ queryKey: playerKeys.all });
  queryClient.invalidateQueries({ queryKey: teamKeys.all });
},
```

## Alignment Table

Create a reference table for your project:

| Entity | Backend Tag | Frontend Key Factory | Related Entities |
|--------|-------------|---------------------|------------------|
| players | `players` | `playerKeys.all` | teams |
| games | `games` | `gameKeys.all` | teams, schedule |
| teams | `teams` | `teamKeys.all` | players, games |
| seasons | `seasons` | `seasonKeys.all` | games, divisions |

## Admin Panel Considerations

When Payload CMS admin panel modifies data:

```typescript
// Payload collection hook
const handlePlayerAfterChange: CollectionAfterChangeHook = async ({
  doc,
  operation,
  req,
}) => {
  // Always invalidate Next.js cache
  revalidateTag('players');
  revalidateTag('teams');

  // If you have a mechanism to notify frontend (e.g., websockets):
  // notifyFrontend({ type: 'INVALIDATE', entities: ['players', 'teams'] });

  return doc;
};
```

### For Real-Time Sync

If you need immediate frontend updates after admin changes:

1. **Polling Strategy**
   ```typescript
   useQuery({
     queryKey: playerKeys.lists(),
     queryFn: getPlayers,
     refetchInterval: 30000,  // Refetch every 30 seconds
   });
   ```

2. **Stale-While-Revalidate**
   ```typescript
   useQuery({
     queryKey: playerKeys.lists(),
     queryFn: getPlayers,
     staleTime: 60000,       // Consider fresh for 1 minute
     refetchOnWindowFocus: true,  // Refetch when tab focused
   });
   ```

3. **WebSocket/SSE Notifications**
   ```typescript
   // Listen for invalidation events
   useEffect(() => {
     const socket = connectToServer();
     socket.on('invalidate', (entities: string[]) => {
       entities.forEach(entity => {
         queryClient.invalidateQueries({ queryKey: [entity] });
       });
     });
     return () => socket.disconnect();
   }, []);
   ```

## Detection Algorithm

The skill automatically checks alignment:

```python
def validate_cross_layer(project_root, mutations):
    """Check that backend cache tags have frontend query key matches."""

    # Extract cache tags used in mutations
    backend_tags = set()
    for mutation in mutations:
        if mutation.has_cache_revalidation:
            backend_tags.add(mutation.table_or_entity)

    # Find query key factories
    frontend_keys = set()
    for key_file in project_root.glob('**/*Keys.ts'):
        # Extract factory names (e.g., playerKeys -> 'player')
        matches = re.findall(r'export const (\w+)Keys', key_file.read_text())
        frontend_keys.update(m.lower() for m in matches)

    # Check alignment
    misaligned = []
    for tag in backend_tags:
        # Check if tag matches any frontend key (singular/plural)
        tag_singular = tag.rstrip('s')
        if not any(tag_singular in key or key in tag_singular for key in frontend_keys):
            misaligned.append(tag)

    return misaligned
```

## Fixing Misalignments

### Missing Query Key Factory

If analysis finds `teams` tag but no `teamKeys`:

```bash
# Create the factory
touch lib/query-keys/team-keys.ts
```

```typescript
// lib/query-keys/team-keys.ts
export const teamKeys = {
  all: ['teams'] as const,
  lists: () => [...teamKeys.all, 'list'] as const,
  list: (filters: TeamFilters) => [...teamKeys.lists(), filters] as const,
  details: () => [...teamKeys.all, 'detail'] as const,
  detail: (id: string) => [...teamKeys.details(), id] as const,
} as const;
```

### Missing Cache Invalidation

If mutation uses `teamKeys` but doesn't invalidate `teams` tag:

```typescript
// Add to server action
revalidateTag('teams');
```

## Dependency Graph

For complex applications, document the cache dependency graph:

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   players   │────▶│    teams    │────▶│   seasons   │
└─────────────┘     └─────────────┘     └─────────────┘
       │                   │                   │
       ▼                   ▼                   ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│ playerKeys  │     │  teamKeys   │     │ seasonKeys  │
└─────────────┘     └─────────────┘     └─────────────┘

Mutation in 'players' → Invalidate: players, teams
Mutation in 'teams'   → Invalidate: teams, players, games
Mutation in 'seasons' → Invalidate: seasons, games, divisions
```

## Quick Reference

```
┌─────────────────────────────────────────────────────────────────┐
│              CROSS-LAYER VALIDATION CHECKLIST                    │
├─────────────────────────────────────────────────────────────────┤
│  FOR EACH ENTITY:                                                │
│  □ Backend uses revalidateTag('entity')                         │
│  □ Frontend has entityKeys factory                               │
│  □ Tag name matches key factory base name                        │
│  □ Related entities also invalidated                             │
├─────────────────────────────────────────────────────────────────┤
│  ADMIN PANEL CHANGES:                                            │
│  □ Payload hooks call revalidateTag                              │
│  □ Frontend has refetch strategy (polling/SWR/websocket)        │
├─────────────────────────────────────────────────────────────────┤
│  DETECTION:                                                      │
│  Run @analyze-mutations to check alignment                       │
│  Misaligned tags appear in "Cross-Layer Validation" section     │
└─────────────────────────────────────────────────────────────────┘
```
