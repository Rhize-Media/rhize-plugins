---
name: supabase-service-role-in-client
enabled: true
event: file
action: block
conditions:
  - field: new_text
    operator: regex_match
    pattern: (SUPABASE_SERVICE_ROLE_KEY|service_role)
  - field: new_text
    operator: contains
    pattern: 'use client'
---

🛡️ **Supabase service-role key referenced in a `'use client'` file — blocked**

The Supabase **service role** key bypasses Row Level Security. If it lands in a client component, it ships to every browser and grants full DB access to the world.

**Fix:**

1. Move the service-role client into a **Server Action**, **Route Handler** (`app/**/route.ts`), or a server-only module (filename ending in `.server.ts` or guarded by `import 'server-only'`).
2. In client components, use the **anon key** via `createBrowserClient` from `@supabase/ssr` — RLS will protect data.
3. If you need privileged mutations from the client, expose them through a Server Action that calls the service-role client server-side.

**Quick pattern (Rhize convention):**

```ts
// lib/supabase/server.ts (server-only, never imported by client)
import 'server-only';
import { createClient } from '@supabase/supabase-js';
export const supabaseAdmin = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.SUPABASE_SERVICE_ROLE_KEY!, // server-only env var
);
```

Override only if you've confirmed the file is actually server-side (e.g., a misleading `'use client'` comment in a string).
