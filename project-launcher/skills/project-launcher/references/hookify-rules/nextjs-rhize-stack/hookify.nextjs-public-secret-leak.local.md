---
name: nextjs-public-secret-leak
enabled: true
event: file
action: block
conditions:
  - field: new_text
    operator: regex_match
    pattern: NEXT_PUBLIC_[A-Z0-9_]*(SECRET|TOKEN|PRIVATE|SERVICE_ROLE|API_KEY|PASSWORD|DSN)
---

🛡️ **NEXT_PUBLIC_ secret leak — blocked**

You're about to write a `NEXT_PUBLIC_*` env var whose name looks like a secret. **Any `NEXT_PUBLIC_` variable is inlined into the browser bundle** — this leaks the value to every visitor.

**Common offenders in the Rhize stack:**

- `NEXT_PUBLIC_SUPABASE_SERVICE_ROLE_KEY` → must be server-only as `SUPABASE_SERVICE_ROLE_KEY`
- `NEXT_PUBLIC_SANITY_API_TOKEN` / `NEXT_PUBLIC_SANITY_WRITE_TOKEN` → must be server-only as `SANITY_API_TOKEN`
- `NEXT_PUBLIC_*_SECRET` / `NEXT_PUBLIC_*_PRIVATE` → server-only
- `NEXT_PUBLIC_SENTRY_DSN` is **OK** for the browser SDK — rename the var to drop the secret-looking suffix if that's what you meant

**Fix:**

1. Rename: drop the `NEXT_PUBLIC_` prefix.
2. Read it on the server only (Route Handler, Server Action, `getServerSideProps`, or `app/.../route.ts`).
3. If the browser truly needs the value, route through a server endpoint and return a scoped, short-lived token.

Override only when you're confident the value is safe to expose to the public.
