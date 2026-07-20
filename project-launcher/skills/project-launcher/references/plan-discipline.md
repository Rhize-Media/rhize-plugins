# Plan Discipline (review-surface methodology)

Cross-cutting planning discipline that applies to every phase of the launcher, especially **Phase 3
(PRD Generation)** and **Phase 4 (Gap Analysis)**. Absorbed from BuilderIO's MIT-licensed `visual-plan`
skill and re-skinned to the Rhize stack (provenance in
`project-launcher/skills/rhize-visual-plan/SOURCES.md`). For turning any plan/PRD
into a rich, reviewable `.mdx` artifact, use the **`rhize-visual-plan`** skill.

## A plan is an approval gate, not a status update

The PRD exists so a human can **see, compare, comment on, and approve** a direction before code or
autonomous execution starts. Optimize it for review, not for completeness theater.

- **Presenting the PRD and requesting sign-off IS the approval step.** Don't append a separate "does
  this look good?" question — name which files/areas the work touches and ask for approval directly.
- **The document is the source of truth, not the chat.** When scope shifts, update the PRD and make it
  stand alone; don't only course-correct in conversation. Re-read the approved PRD before major steps.

## Research before you draft

- Read the real files, actions, schema, and patterns first; name **actual** files, symbols, and data
  shapes instead of inventing them. In our stack: existing Sanity/Payload schemas + GROQ, Supabase
  tables + RLS, `app/` route and server-action boundaries, n8n workflows.
- **Lead with reuse.** For each step, name what it reuses — existing actions, schema, components,
  helpers — *before* what it adds, so the PRD explains the genuinely new delta instead of redescribing
  what already exists.
- Delegate wide exploration to a sub-agent so the main thread stays on synthesis.

## Decide the hard-to-reverse bets first

For non-trivial backend/data/API work, explicitly call out the decisions that are **expensive to undo**
once data or callers depend on them, and get them right in the PRD even if most of the feature ships
later:

- wire format and public ids
- data-model shape (Sanity document types, Supabase migrations)
- auth and ownership boundaries
- API/route/server-action contracts

Then scope to the **smallest first cut** that proves the approach without foreclosing it. State both
what is in and what is explicitly deferred. A `<Decision>` block (in `rhize-visual-plan`) is the natural
home for each of these.

## Calibrate altitude and examples

When the idea is a broad framework, product, or operating-model change, do **not** collapse it into the
first concrete example, provider, or sync path mentioned. Separate the core abstraction from motivating
examples and adapters; label examples as examples unless they are the whole requested scope.

## Clarify vs. assume

Don't ask *how* to build it — explore and present the approach and options in the PRD. Ask a clarifying
question only when an ambiguity would change the design and you cannot resolve it from the code; batch
2–4 high-leverage questions before finalizing (use the interview bank). Otherwise state the assumption
explicitly and keep anything unresolved in a single **Open Questions** section with a recommended
default for each.

## Self-review before handoff (cheap adversarial pass)

This is a lightweight complement to the Phase 4 grill — run it on the **written PRD** before handoff,
not as a re-research:

- Surface the PRD first; run the review concurrently while the user reads. Never block handoff on it.
- Spawn **one** skeptical sub-agent whose only job is to find what is weak, missing, or wrong: implicit
  hard-to-reverse decisions, steps not anchored in real files/symbols, a menu of options where the PRD
  should commit, obvious missing decisions ("what happens when X?"), and padding or single-step filler.
- **Fix vs. ask:** apply clear-cut fixes yourself; route genuine judgment calls to the user via Open
  Questions or the normal ask-user flow. Don't silently decide them.

## Visual surface — only where it earns its place

Add diagrams/wireframes only where a picture beats prose; don't add visual chrome by default.

- **Prose + local `<Diagram>`** for architecture/backend/data/migration PRDs — usually one spatial
  diagram per decision (grouped regions / layers / before-after, not a single-axis chain unless truly
  sequential).
- **Wireframes/`<Canvas>`** for UI/product PRDs — one artboard per user-visible state.
- For the full quality bar and the renderer, hand off to **`rhize-visual-plan`** rather than hand-rolling
  visuals in the PRD.
