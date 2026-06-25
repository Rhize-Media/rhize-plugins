# rhize-visual-plan — Provenance

Forked from BuilderIO's `visual-plan` skill via `rhize-skill-forge` on 2026-06-25.

- **Upstream:** https://github.com/BuilderIO/skills/tree/main/skills/visual-plan
- **Upstream ref:** git commit `6294124fdb96fb3cf4726c78ea505e4d3a7af00e` (2026-06-24)
- **License:** MIT — Copyright (c) 2026 Builder.io (permissive). Full text: https://github.com/BuilderIO/skills/blob/main/LICENSE
- **Verb:** FORK (with a companion ABSORB into `project-launcher`)

## What was taken (MIT — attribution retained here)

- The planning **methodology / discipline**: plan-as-approval-gate, lead-with-reuse, decide-the-hard-to-reverse-bets-first, self-review-before-handoff, and visual-surface-choice.
- The **wireframe / canvas / document-quality** quality bars (re-skinned to the Rhize stack and a single canonical `--wf-*` token + surface contract).

## What is original to Rhize (not from BuilderIO)

- The `plan.mdx` component vocabulary and format (`references/mdx-plan-format.md`).
- The Next.js/Vercel renderer (`templates/mdx-components.tsx`, `templates/plan-route.tsx`), the Obsidian fallback, and the JSON Canvas export path.
- All stack assumptions (Next.js / Sanity / Payload / Supabase / Vercel / Obsidian).

## Deliberately NOT taken (removed — no runtime dependency)

BuilderIO's hosted Plan UI, the `@agent-native` CLI/connector, the localhost bridge, the hosted/local
`create-*`/`update-visual-plan`/`get-plan-blocks` tool surface, and the live block registry. This fork
has **zero** dependency on any hosted plan service.

## Secondary source — Obsidian plugin shell (`obsidian-plugin/`)

The `obsidian-plugin/` directory (the "Obsidian shell" that renders `plan.mdx`
natively in Obsidian) reuses our own renderer core (`viewer/src/*.tsx`) verbatim
— that code is original to Rhize. The **Obsidian-specific plumbing patterns** were
adapted from a permissively-licensed reference:

- **Upstream:** https://github.com/ddunnock/mdx-support (Obsidian MDX plugin)
- **License:** MIT (permissive).
- **Verb:** ADAPT (patterns, not verbatim files).
- **What was taken (patterns, re-implemented from scratch):** the conventional
  Obsidian wiring shape — `registerView(VIEW_TYPE, …)` paired with
  `registerExtensions(["mdx"], VIEW_TYPE)`; gating the `.mdx` binding on an
  "auto-render/auto-open" setting (falling back to the built-in `markdown` view
  when off); the `PluginSettingTab` layout with a toggle; and the file-view
  lifecycle hook points. These are idiomatic Obsidian-plugin conventions also
  found in the official Obsidian sample plugin.
- **What was NOT taken:** mdx-support's own MDX compilation/rendering approach,
  its icons, its Storybook/JSX settings, and any of its component handling. Our
  shell compiles MDX at runtime with `@mdx-js/mdx` `evaluate()` and renders with
  OUR `planComponents` + `PlanShell` — none of that comes from mdx-support.

No mdx-support source files were copied into the repo; the adaptation is
limited to the boilerplate patterns enumerated above.

## Drift check

```bash
git ls-remote https://github.com/BuilderIO/skills.git HEAD   # compare to 6294124fdb96fb3cf4726c78ea505e4d3a7af00e
```

Re-run `rhize-skill-forge` on the delta if upstream moved. Central audit ledger:
`rhize-meta/skills/rhize-skill-forge/SOURCES.md`.
