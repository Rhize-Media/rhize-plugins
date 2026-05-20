---
name: sanity-schema-skill-hint
enabled: true
event: file
action: warn
conditions:
  - field: file_path
    operator: regex_match
    pattern: (sanity/(schemas?|desk|structure)/|/schemaTypes/|\.schema\.(ts|js)$|sanity\.config\.(ts|js)$)
---

📐 **Sanity schema/config edit detected — load the Sanity best-practices skill**

You're editing a Sanity schema, structure, or config file. Before making non-trivial changes, invoke:

- `/sanity-plugin:sanity-best-practices` — content-modeling patterns, field naming, GROQ
- `/sanity-plugin:typegen` — regenerate TypeScript types after schema changes
- `/sanity-plugin:deploy-schema` — when you're ready to push

**Things to check on every schema change:**

- Field `name` follows kebab-case consistency with rest of project
- New required fields have a `initialValue` or migration plan (existing docs will fail validation otherwise)
- Reference fields use `to: [{type: '...'}]` with all valid targets enumerated
- Block content uses the project's shared portable-text config (don't reinvent)
- After saving: run `pnpm typegen` (or `npx sanity@latest typegen generate`) so `sanity.types.ts` stays in sync — downstream code will type-error until you do

If this is a brand-new schema type, also update the studio's desk structure and any GROQ queries that should surface it.
