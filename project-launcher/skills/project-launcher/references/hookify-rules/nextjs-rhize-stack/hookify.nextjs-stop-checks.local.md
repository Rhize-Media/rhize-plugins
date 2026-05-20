---
name: nextjs-stop-checks
enabled: true
event: stop
action: warn
conditions:
  - field: transcript
    operator: not_contains
    pattern: (pnpm|npm|yarn|bun)\s+(run\s+)?(typecheck|tsc|lint|build|test)
---

✅ **Before stopping — Next.js sanity checks not detected in this session**

I don't see evidence in the transcript that you ran the standard verification commands. If you wrote or modified TypeScript/React code, please run at least one of:

```bash
pnpm typecheck    # or: pnpm tsc --noEmit
pnpm lint         # ESLint + project rules
pnpm build        # full production build (catches Server/Client component boundary errors)
pnpm test         # unit tests (if present)
```

**Minimum bar for the Rhize stack:**

- Type-checked code (no `tsc` errors)
- Lint clean (or intentionally suppressed with comment)
- If you touched routes, layouts, or server actions → `pnpm build` must pass (App Router catches RSC/CC boundary issues only at build)
- If you touched Sanity schemas → run `pnpm typegen` (or `npx sanity@latest schema extract && npx sanity@latest typegen generate`)
- If you touched Supabase migrations → run `supabase db diff` and review

This is a **warning**, not a block — but don't claim the task is done until checks pass. If checks were intentionally skipped (e.g., docs-only PR), say so explicitly.
