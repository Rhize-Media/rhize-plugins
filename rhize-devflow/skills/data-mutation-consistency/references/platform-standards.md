# Platform Standards: Vercel + Next.js + Supabase

This document defines the required patterns for data mutations on the Vercel/Next.js/Supabase platform.

## Core Principles

1. **All mutations must handle errors** - Supabase operations can fail silently
2. **All mutations must revalidate cache** - Next.js caches aggressively
3. **All mutations must be type-safe** - TypeScript prevents runtime errors
4. **User-facing mutations need optimistic UI** - Better UX

---

## Server Actions

### Standard Pattern

```typescript
'use server'

import { revalidatePath, revalidateTag } from 'next/cache';
import { createClient } from '@/lib/supabase/server';
import { z } from 'zod';

// Input validation schema
const updatePlayerSchema = z.object({
  firstName: z.string().min(1),
  lastName: z.string().min(1),
  email: z.string().email(),
});

export async function updatePlayer(
  id: string,
  data: z.infer<typeof updatePlayerSchema>
): Promise<{ success: boolean; error?: string }> {
  // 1. Validate input
  const validated = updatePlayerSchema.safeParse(data);
  if (!validated.success) {
    return { success: false, error: validated.error.message };
  }

  // 2. Create typed client
  const supabase = await createClient();

  // 3. Perform mutation with error handling
  const { data: player, error } = await supabase
    .from('players')
    .update(validated.data)
    .eq('id', id)
    .select()
    .single();

  if (error) {
    console.error('Failed to update player:', error);
    return { success: false, error: error.message };
  }

  // 4. Revalidate cache
  revalidateTag('players');
  revalidatePath(`/players/${id}`);
  revalidatePath('/players');

  return { success: true };
}
```

### Required Elements

| Element | Why Required |
|---------|--------------|
| `'use server'` directive | Marks as server action |
| Input validation (zod) | Prevents invalid data |
| Error destructuring | Catches Supabase failures |
| revalidateTag/Path | Prevents stale cache |
| Return type annotation | Type safety |

---

## API Routes

### Standard Pattern

```typescript
// app/api/players/[id]/route.ts

import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@/lib/supabase/server';
import { z } from 'zod';

const updateSchema = z.object({
  firstName: z.string().min(1).optional(),
  lastName: z.string().min(1).optional(),
});

export async function PATCH(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  try {
    // 1. Parse and validate
    const body = await request.json();
    const validated = updateSchema.parse(body);

    // 2. Create client
    const supabase = await createClient();

    // 3. Perform mutation
    const { data, error } = await supabase
      .from('players')
      .update(validated)
      .eq('id', params.id)
      .select()
      .single();

    // 4. Handle RLS errors specifically
    if (error) {
      if (error.code === 'PGRST301') {
        return NextResponse.json(
          { error: 'Not authorized to update this player' },
          { status: 403 }
        );
      }
      throw error;
    }

    return NextResponse.json(data);

  } catch (error) {
    console.error('API error:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}
```

### Required Elements

| Element | Why Required |
|---------|--------------|
| try/catch wrapper | Catches all errors |
| Input validation | Prevents invalid data |
| RLS error handling | Proper auth feedback |
| Error response format | Consistent API |

---

## Supabase Mutation Patterns

### Error Handling

```typescript
// ❌ WRONG: Ignores errors
const { data } = await supabase.from('players').update(data).eq('id', id);

// ✅ CORRECT: Handles errors
const { data, error } = await supabase.from('players').update(data).eq('id', id);
if (error) throw error;
```

### RLS-Aware Error Handling

```typescript
const { data, error } = await supabase
  .from('players')
  .update(data)
  .eq('id', id)
  .select()
  .single();

if (error) {
  // RLS policy violation
  if (error.code === 'PGRST301') {
    throw new Error('Not authorized to modify this record');
  }
  // Other Supabase errors
  throw new Error(`Database error: ${error.message}`);
}
```

### Typed Mutations

```typescript
// Define types that match your database schema
interface Player {
  id: string;
  first_name: string;
  last_name: string;
  email: string;
  team_id: string | null;
  created_at: string;
  updated_at: string;
}

interface PlayerUpdate {
  first_name?: string;
  last_name?: string;
  email?: string;
  team_id?: string | null;
}

// Use types in mutations
async function updatePlayer(id: string, data: PlayerUpdate): Promise<Player> {
  const supabase = await createClient();

  const { data: player, error } = await supabase
    .from('players')
    .update(data)
    .eq('id', id)
    .select()
    .single();

  if (error) throw error;
  return player;
}
```

---

## Cache Revalidation Strategy

### When to Use revalidateTag

Use for category-wide invalidation:

```typescript
// After updating any player
revalidateTag('players');

// After modifying team roster
revalidateTag('teams');
revalidateTag('players'); // Players list also changes
```

### When to Use revalidatePath

Use for specific page invalidation:

```typescript
// After updating a specific player
revalidatePath(`/players/${id}`);
revalidatePath('/players'); // List page too
```

### Combined Strategy

```typescript
// Best practice: Use both
revalidateTag('players');           // Invalidate all player data
revalidatePath(`/players/${id}`);   // Ensure specific page refreshes
revalidatePath('/players');         // Ensure list refreshes
```

### Cache Tag Naming Convention

```typescript
// Use plural entity names for tags
revalidateTag('players');   // ✅ Consistent
revalidateTag('games');
revalidateTag('teams');

// Match with React Query key factories
export const playerKeys = {
  all: ['players'] as const,  // Matches tag name
  // ...
};
```

---

## Input Validation Pattern

```typescript
import { z } from 'zod';

// 1. Define schema
const createPlayerSchema = z.object({
  firstName: z.string().min(1, 'First name required'),
  lastName: z.string().min(1, 'Last name required'),
  email: z.string().email('Invalid email'),
  teamId: z.string().uuid().optional(),
});

// 2. Type inference
type CreatePlayerInput = z.infer<typeof createPlayerSchema>;

// 3. Validate in action/API
export async function createPlayer(input: unknown) {
  // Parse throws on invalid input
  const data = createPlayerSchema.parse(input);

  // Or use safeParse for graceful handling
  const result = createPlayerSchema.safeParse(input);
  if (!result.success) {
    return { error: result.error.flatten() };
  }

  // Proceed with validated data
  // ...
}
```

---

## Quick Reference

```
┌─────────────────────────────────────────────────────────────────┐
│         PLATFORM STANDARDS (Vercel/Next.js/Supabase)            │
├─────────────────────────────────────────────────────────────────┤
│  SERVER ACTIONS:                                                 │
│  ✓ 'use server' directive                                       │
│  ✓ Zod input validation                                         │
│  ✓ const { data, error } = await supabase...                    │
│  ✓ if (error) throw/return error                                │
│  ✓ revalidateTag('entity') after mutation                       │
│  ✓ revalidatePath('/path') for specific pages                   │
│  ✓ Typed return value                                           │
├─────────────────────────────────────────────────────────────────┤
│  API ROUTES:                                                     │
│  ✓ try/catch wrapper                                            │
│  ✓ Input validation                                              │
│  ✓ RLS error handling (PGRST301)                                │
│  ✓ Consistent error response format                             │
├─────────────────────────────────────────────────────────────────┤
│  CACHE TAGS:                                                     │
│  • Use plural entity names (players, games, teams)              │
│  • Match React Query key factories                               │
│  • Invalidate related entities too                              │
└─────────────────────────────────────────────────────────────────┘
```
