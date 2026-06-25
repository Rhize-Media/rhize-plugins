# Plan document quality — single source of truth

This file is the canonical quality bar for the body of a Rhize `plan.mdx`: how
it reads, which blocks to use, how open questions are surfaced, and the
pre-handoff check. Read it in full before authoring any plan document; do not
write the document from memory or paraphrase these rules per session.

---

**The document is a serious technical plan, not marketing.** Write it the way a
strong implementation plan reads: outcome-first, prose-first, self-contained, and
specific. State the objective and what "done" means, the scope and non-goals, the
proposed approach with key decisions and their rationale, ordered steps that name
real files, symbols, actions, and data shapes, the risks, and a closing
verification step (tests, build, or a checkable behavior). Replace vague prose
with specifics; never ship a step like "make it work." No hero art, gradients,
logos, nav bars, slogans, value props, giant landing-page headings, or marketing
cards unless the user explicitly asks.

**Every published plan must stand alone.** Even when revising an existing plan,
the output is a plan to do the work, not a changelog of the conversation. Do not
write phrases like "preserve the previous plan," "as discussed above," "this
revision," "unlike the prior version," or "correction from the earlier plan."
Fold the right decisions into the plan as normal objective, architecture, scope,
and roadmap prose. A reviewer who opens the plan from a vault link with no chat
history should understand it. Avoid negative framing that only makes sense against
absent context ("not the old mode") unless the contrast is defined in the plan
and genuinely helps; state the positive model directly.

**Make abstract plans instantly legible.** If the idea is broad, strategic, or
intended for a third-party reviewer, put one concrete product snapshot near the
top before dense architecture, mode tables, manifests, or roadmaps. For
UI-capable concepts, that snapshot is usually a top-canvas app state plus a short
paragraph that says what the user sees and what changes under the hood. Then put
mechanics, data flow, and implementation detail in separate `<Diagram>` blocks or
document sections.

**Preserve the user's level of abstraction.** A motivating use case is not
automatically the architecture. When the prompt describes a broader framework,
product mode, or reusable primitive, separate the reusable core from specific
apps, providers, customers, scripts, or launch examples. Use the concrete example
to make the plan understandable, then make clear which parts are core, which are
app-specific adapters, and which are future examples.

**When top visuals exist, they and the document never duplicate each other.** For
UI work, the UI story lives in the top visual surface: `<Canvas>` artboards for
static inspection, with behavior described in prose/`<Decision>` blocks beneath
it. The document carries the technical depth the visuals cannot show — concrete
file/symbol maps, API and data contracts, code snippets, migration phases, risks,
and validation. For architecture or code-review plans, invert that: the document
is the visual surface, and each recommendation carries its own nearby inline
`<Diagram>` plus file evidence. Repeat a wireframe in the document body only for
a genuinely new detail view or comparison. Skip the visual surface entirely for
non-visual work and write a clean rich document.

---

## Use the right block, and make it carry substance

Each block type below maps to a component in `references/mdx-plan-format.md`.
Choose by what the reader needs, not by habit.

**`<Diagram>` — relationships and flow.** Use for two-dimensional architecture,
dependency, data-flow, or state relationships, only when a picture clarifies
something real. Author the body as a fenced ```mermaid block. Prefer grouped
regions, layered diagrams, swimlanes, dependency maps, or before/after panels
over a single left-to-right chain unless the relationship is truly sequential. Do
not use a body `<Diagram>` as the primary artifact for a requested product
canvas, UI flow, or screen flow; those belong in `<Canvas>` / `<Wireframe>` / `<Screen>`
artboards. Use `<Diagram>` below a canvas only for architecture, data flow, or
implementation mechanics. Leave room for labels: keep them short and do not let
them overlap nodes or connectors.

**`<FileMap>` — what changes where.** When load-bearing files are worth
highlighting, prefer a `<FileMap>` with the real paths and a verb + delta note
(add/edit/delete) rather than a bare prose list. Highlight only the files worth
reading; never an exhaustive list of every touched file.

**`<DataModel>` and `<ApiEndpoint>` — hard-to-reverse contracts.** Surface these
early for data-model changes (Sanity doc types, Supabase tables, TS types) and
API/route/server-action contracts because wire format, public ids, and data shapes
are expensive to undo once data or callers depend on them.

**`<AnnotatedCode>` over bare `<Diff>` when it carries real calls-to-attention.**
When a load-bearing file is worth showing, prefer `<AnnotatedCode>` with a few
high-signal annotations on the lines that actually change (the new action, the
changed schema, the wiring point), so the reader sees what matters and why. Keep
a few targeted annotations per file, not one per line. Drop to a plain `<Diff>`
only for a throwaway change with nothing to call out.

**`<Decision>` for committed bets.** If you have already chosen an approach, state
it as settled prose or in a `<Decision status="decided">` block, optionally
noting the alternatives you weighed. Do not restate a decided choice in `<OpenQuestions>`.
For a genuinely open either/or where the reviewer must still pick, put it in the
single bottom `<OpenQuestions>` block with a recommended default — not a mid-body
decision card.

**`<Canvas>` for side-by-side before/after or UI flows.** Use `<Canvas>` with
labeled `<Screen>` artboards for parallel visual comparisons. Label states with
`<Screen title="Before">` / `<Screen title="After">` — do not bake state labels
inside the wireframe `html`. Do not stack comparison artboards vertically when
parallel reading is the point.

**Prose carries the plan; components punctuate it.** A plan that is all
components and no prose has failed. Use `<Decision>`, `<FileMap>`, `<Diagram>`,
etc. to punctuate prose where a picture or contract beats a paragraph — not as a
substitute for a clear sentence.

---

## Open questions

**Open questions live at the bottom in a single `<OpenQuestions>` block.** Surface
answerable unresolved decisions in the one `<OpenQuestions>` block at the end of
the document. That is the ONLY place that enumerates open questions: never add a
second "Open Questions" heading, list, or recap of the same questions elsewhere in
the body. A one-line pointer in overview prose ("a few decisions are still open —
see Open Questions below") is fine, but do not reproduce the question list or a
parallel questions section above it.

Each entry in `<OpenQuestions>` must follow the format from `mdx-plan-format.md`:

```
- **Q:** <the question> — *Recommended:* <your default> — *Blocks:* <what it gates>
```

Use `Recommended` for the answer you would choose; use `Blocks` to show what
cannot proceed until this is resolved. Keep non-answerable assumptions or risks
as concise prose or `<Decision>` notes in the relevant section — do not route
them to `<OpenQuestions>`.

**Do not end a complex plan without an open-question audit.** If architecture,
scope, UX, data shape, rollout, or ownership still depends on a choice, either
commit to a recommendation with rationale in a `<Decision>` block, or add it to
`<OpenQuestions>` with a recommended default. A complex plan with no open
questions is fine only when every meaningful decision has been explicitly made.

---

## Verification

**Verification must exercise the real workflow.** The final verification section
should go beyond typecheck/unit tests when the plan changes UI, data, sync,
providers, or multi-service flows. Include at least one end-to-end smoke test
that matches the user journey — such as a fresh schema run, real data fixture,
browser interaction, save/sync action, and an on-disk or database assertion.
Name the command or manual browser path when known. For Rhize stack specifics:

- **Sanity/Payload changes:** confirm the schema deploys cleanly, existing
  documents pass validation, and at least one GROQ query returns the expected
  shape.
- **Supabase changes:** confirm the migration applies without error, RLS policies
  cover the new rows, and at least one server-action round-trip succeeds.
- **Next.js/Vercel routes:** confirm the route renders without error in preview
  and the page passes a basic Lighthouse accessibility check.

---

## Pre-handoff visual check

Before treating the plan as final and requesting approval:

1. Open the plan in Obsidian (fast local read) and confirm: frontmatter renders
   as Properties, Mermaid blocks render natively, and wikilinks are valid.
2. Open the plan in the Next.js viewer (or drop it into the preview route) and
   confirm: no overlapping elements, no excessive whitespace, no clipped
   fragments, no misleading inactive controls, no unreadable diagrams.
3. Fix any of the above before asking for approval — do not ask the reviewer to
   ignore visual defects.

Surface the plan first, run this check concurrently, and never make the user
wait for it.
