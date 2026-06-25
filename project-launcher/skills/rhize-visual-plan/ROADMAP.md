# rhize-visual-plan — Roadmap

## Shipped (v1 — 2026-06-25)

- **Local viewer + CLI** (`viewer/`): `rhize-plan serve` (live local preview, HMR) + `rhize-plan build`
  (single self-contained offline `plan.html`). Vite + `@mdx-js` + React 18, **no external plan service**.
  Project-agnostic — renders any `plan.mdx` from the vault or any client repo. Audience: internal (Jim +
  Tom); the static HTML export is the sharing/approval artifact.
- **Canonical renderer core:** `viewer/src/components.tsx`.

## Roadmap (all → packaged into the Rhize plugins)

1. **Hosted app — `plans.rhize.dev`** (Next.js + Supabase on Vercel). Client-facing: shareable links,
   login / org-scoping, inline comments on the plan. Imports the **same** renderer core;
   `templates/mdx-components.tsx` + `templates/plan-route.tsx` are the starting point. Trigger when a client
   actually needs to comment in-plan.
2. **Obsidian-native plugin.** Render the plan components directly in the vault (zero context-switch) and
   give first-class `.mdx` rendering. Complements — doesn't replace — the static export.
3. **Marketplace packaging.** Distribute the CLI + renderer (and later the hosted app + Obsidian plugin)
   via the `rhize-plugins` marketplace so every Rhize project gets the viewer. Extract the renderer core to
   `@rhize/plan-viewer` once there's a second consumer (CLI + hosted app).

## Open items

- **`.md` vs `.mdx` in the vault.** Obsidian renders `.md` natively but not `.mdx`. Plan: store vault plans
  as `.md`, make the CLI accept both `.md`/`.mdx`, keep `.mdx` for repo-committed plans. Update the format
  doc's "default vault location" accordingly.

## Principle

**One renderer core, many shells.** Every shell (CLI, hosted app, Obsidian plugin) consumes
`viewer/src/components.tsx` — never a second divergent implementation.
