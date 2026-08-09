---
name: rhize-visual-plan
tier: custom
domain: dev-flow
maturity: beta
description: >
  ALWAYS invoke this skill (via the Skill tool) for any request to turn an implementation plan into a
  rich, reviewable `.mdx` visual plan — architecture diagrams, file maps, wireframes, data models, API
  contracts, annotated code/diffs, and open questions — authored as a portable `plan.mdx` rendered
  by our own local viewer (the `rhize-plan` CLI: live preview + a self-contained HTML export) and degrading
  to readable Markdown (with Mermaid + a `.canvas` export) in Obsidian. Triggers on: "visual plan", "make this plan reviewable", "turn this plan into mdx",
  "plan.mdx", "wireframe this", "rich plan document", "review surface for this plan", "canvas plan",
  "planning doc with diagrams", "plan as an approval gate", or whenever a multi-file, ambiguous, risky,
  data-heavy, or UI-heavy change needs a human sign-off before code. Rhize-OWNED format — no external
  plan service, hosted Plan UI, or `@agent-native` dependency. For the upstream PRD → GSD autonomous
  pipeline use `project-launcher`; this skill is the rich review surface for ANY plan, and writes the
  artifact into the Obsidian vault as the second-brain source of truth.
metadata:
  rhize:
    topics: [visualization, project-planning]
    stacks: [obsidian]

---

# Rhize Visual Plan

Turn the plan you would normally dump into chat into a **scannable, commentable review artifact** — a
single `plan.mdx` file with structured, editable blocks mixed into prose: inline diagrams, file maps,
wireframes, data-model and API contracts, annotated code, and a single open-questions block.

Two things make this skill ours, not a wrapper around someone else's product:

1. **The discipline is portable.** Research before drafting, lead with reuse, lock the hard-to-reverse
   bets early, treat the plan as the approval gate, and run one adversarial self-review before handoff.
2. **The format is ours.** `plan.mdx` uses a small Rhize component vocabulary (`references/mdx-plan-format.md`)
   rendered by **our own** local viewer (the `rhize-plan` CLI in `viewer/`) — and because MDX is a superset
   of Markdown, the same file is readable in Obsidian and exportable to a JSON Canvas. There is **no** hosted
   Plan service, localhost bridge, or `@agent-native` connector. We own the renderer and the data.

> Forked from BuilderIO's MIT-licensed `visual-plan` skill (the *methodology* and the wireframe/canvas
> quality bars). Re-skinned to the Rhize stack — Next.js, Sanity/Payload, Supabase, Vercel, Obsidian.
> See `SOURCES.md`.

## When To Use

Create or adapt a visual plan whenever the plan is **better as a reviewable artifact than a chat
paragraph**: multi-file work, an architecture or data-model decision, an API/contract change, a UI
surface with multiple states, a before/after product change, or anything ambiguous, risky, or
expensive to reverse. Also use it to upgrade a pasted/Codex/Claude-Code/Markdown plan into a richer
review surface, or when a `project-launcher` PRD would benefit from inline diagrams and wireframes.

**Skip it** for truly trivial work — typos, one-line fixes, a single well-specified function, anything
whose diff is easier to review than a plan. Never pad a plan with filler and never ship a single-step
plan.

## Plan Discipline

- **Research before you draft.** Read the real files, actions, schema, and patterns first; name actual
  files, symbols, and data shapes instead of inventing them. In our stack: check existing Sanity/Payload
  schemas and GROQ, Supabase tables and RLS, and `app/` route/server-action boundaries before proposing
  new ones. Delegate wide exploration to a sub-agent.
- **Lead with reuse.** For each step, name what it reuses — existing actions, schema, components, helpers
  — *before* what it adds, so the plan explains the genuinely new delta instead of redescribing what
  already exists.
- **Decide the hard-to-reverse bets first.** For non-trivial backend/data/API work, call out the
  decisions that are expensive to undo once data or callers depend on them — wire format, public ids,
  data-model shape, auth/ownership boundaries, Sanity document types, Supabase migrations — and get those
  right in the plan even if most of the feature ships later. Then scope to the smallest first cut that
  proves the approach without foreclosing it; state what is in and what is explicitly deferred.
- **Keep examples at the right altitude.** When the idea is a broad framework or operating-model change,
  don't collapse it into the first concrete example. Separate the core abstraction from motivating
  examples; label examples as examples.
- **Planning is read-only.** Make no source edits while building or reviewing the plan. Start editing
  only after the user approves the direction.
- **Clarify vs. assume.** Don't ask *how* to build it — explore and present the approach and options in
  the plan. Ask a clarifying question only when an ambiguity would change the design and you cannot
  resolve it from the code; batch 2–4 high-leverage questions before finalizing. Otherwise state the
  assumption explicitly and keep anything unresolved in the single bottom `<OpenQuestions>` block.
- **The plan is the approval gate.** After surfacing it, ask the user to review and approve before you
  write code, and name which files/areas the work touches. Presenting the plan and requesting sign-off
  *is* the approval step — don't ask a separate "does this look good?" question.
- **The document is the source of truth, not the chat.** When scope shifts, update `plan.mdx` and make
  it stand alone — don't only change course in chat. Re-read the approved plan before major steps.

## The Rhize Plan Format (`.mdx`)

The deliverable is ALWAYS a structured `plan.mdx` file in the vault, never a chat-only plan. The format
is defined in **`references/mdx-plan-format.md`** — read it before authoring. In brief:

- **Frontmatter:** `title`, `status` (`draft|in-review|approved|superseded`), `owner`, `created`, `repo`,
  `related` (`[[wikilinks]]`), `tags`. Status is the approval-gate state.
- **Body:** Markdown prose interleaved with Rhize plan components — `<Diagram>` (Mermaid), `<FileMap>`,
  `<DataModel>`, `<ApiEndpoint>`, `<Wireframe>`, `<Canvas>`, `<Diff>`, `<AnnotatedCode>`, `<Decision>`,
  and exactly one bottom `<OpenQuestions>`.
- **Portable + degrading:** every component is plain MDX. In our Next.js viewer it renders rich; in
  Obsidian it shows as readable Markdown with native Mermaid; `<Canvas>` can export to a `.canvas`
  (JSON Canvas) file via the `json-canvas` skill.

## Core Workflow

1. **Research.** Inspect the codebase/vault; delegate wide exploration when useful. If a source plan
   already exists (paste, file, or `project-launcher` PRD), carry its facts forward but rewrite the
   published plan as a clean standalone proposal (no "unlike the previous version" language).
2. **Choose the visual surface** (see below) — do not add visual chrome by default.
3. **Author `plan.mdx`** in the vault using the component vocabulary. Default location:
   `Projects/<Project>/Plans/<slug>/plan.mdx` (second-brain source of truth). Use the repo path
   `plans/<slug>/plan.mdx` instead when the plan should live in source control with the code.
4. **Render & view.** Preview locally with `rhize-plan serve <path>` (live reload), or produce a single
   self-contained `plan.html` to share with `rhize-plan build <path>` (the viewer is packaged in `viewer/`).
   Obsidian also renders the same file for a fast read. Always give the user the actual path so the next
   step is a click.
5. **Self-review before handoff** (see below) for high-stakes plans — run it concurrently while the user
   reads; never block the handoff on it.
6. **Iterate from feedback.** Treat comments (Obsidian, PR review, or chat) as edits to `plan.mdx`
   directly; re-render and report the updated URL. Keep the document standalone.
7. **Approval gate.** Flip frontmatter `status: approved` only after the user signs off, then begin code.

## Visual Surface Choice

Choose the surface before authoring. Match the surface to the work, not to habit:

- **No visual surface** for architecture-only, backend-only, data-migration, or copy-only plans. Use a
  strong prose document with **local inline `<Diagram>` blocks** only where relationships need a picture
  — usually one spatial diagram per decision. Prefer grouped regions / layers / before-after panels over
  a single-axis chain unless the relationship is truly sequential. Do not force a top canvas onto a
  non-visual plan.
- **Canvas only** (`<Canvas>` with `<Screen>` artboards) for one static screen, a before/after
  comparison, a component state, or a visual direction that doesn't require clicking. One artboard per
  user-visible state (default, empty, loading, error, overflow/popover).
- **Canvas + prototype note** for multi-step UI flows: keep the static artboards in `<Canvas>` and
  describe the interactive behavior in prose/`<Decision>` blocks beneath it (our format favors static
  wireframes + clear behavior notes over a separate live-prototype runtime).

Keep product wireframes and explanatory diagrams **separate**: pure screens that look like the real app
state, with arrows/labels/contracts in annotations or the document body, not baked into the UI. When the
plan touches an existing app, inspect the current shell/components first so the first artboard matches
real density (existing sidebars, toolbar, chrome).

## Rendering & Viewing (we own this)

The viewer is packaged in this skill at **`viewer/`** — a project-agnostic local tool (Vite + `@mdx-js` +
React, no external plan service) that renders ANY `plan.mdx` from anywhere on disk (the vault or any client
repo). One-time setup: `cd viewer && npm install` (optionally `npm link` for a global `rhize-plan`).

- **Live local preview:** `rhize-plan serve <path-to-plan.mdx|dir>` — opens the browser with HMR; edits to
  the plan reload instantly. The daily review driver.
- **Self-contained export (sharing / approval):** `rhize-plan build <path> [-o out.html]` — emits ONE
  offline `plan.html` (all CSS/JS inlined, Mermaid + wireframes included). Attach it to Jira/Slack/email or
  commit it; this is the internal approval artifact (no hosting needed).
- **Obsidian (fast read + second brain):** store vault plans as `.md` so Mermaid + frontmatter + prose
  render natively (Obsidian doesn't render `.mdx` yet — the Obsidian plugin on the roadmap will). Connect
  the plan to the project MOC with `[[wikilinks]]`.
- **JSON Canvas export:** `<Canvas>` artboards map onto an Obsidian `.canvas` via the
  `obsidian-second-brain:json-canvas` skill.

`viewer/src/components.tsx` is the **canonical renderer core**. The Next.js files in `templates/` are the
starting point for the roadmap hosted app (`plans.rhize.dev`) — see `ROADMAP.md`.

## Self-Review Before Handoff

For high-stakes plans (architecture, backend, data-model, migration, multi-file, risky) run **one**
adversarial self-review before treating the plan as final. Skip it for small, single-decision plans.

- **Surface first, review concurrently.** Post the link/path, let the user start reading, run the review
  in parallel — never make them wait.
- **Review the written plan; do not re-research.** Critique the plan text and its own blocks.
- **Spawn one skeptical reviewer** (sub-agent) whose only job is to find what is weak, missing, or wrong:
  hard-to-reverse decisions made implicitly or not at all; steps not anchored in real files/symbols; a
  menu of options where the plan should commit to one; obvious missing decisions ("what happens when
  X?"); padding or single-step filler.
- **Fix vs. ask.** Apply clear-cut fixes yourself; route genuine judgment calls to the user via the
  bottom `<OpenQuestions>` block or the normal ask-user flow. Don't silently decide them.

## Wireframe quality — read `references/wireframe.md`

Wireframes inside `<Wireframe>`/`<Screen>` must meet a strict bar — full-width chrome, pinned bottom
bars, real product content, before/after comparability, the right `surface` preset, `--wf-*` design
tokens instead of raw hex, and no `<html>`/`<style>`/font tags. Before authoring ANY wireframe, READ
`references/wireframe.md`. Do not author wireframes from memory.

## Document quality — read `references/document-quality.md`

The document is a serious technical plan, not marketing: outcome-first, prose-first, self-contained,
built from the right blocks, with open questions in a single bottom `<OpenQuestions>` and a pre-handoff
visual check. Before authoring the plan body, READ `references/document-quality.md`.

## Good vs. bad exemplar — read `references/exemplar.md`

For a worked example of the bar — a strong plan in our format plus the anti-patterns to avoid — READ
`references/exemplar.md` before authoring.

## Relationship to other Rhize skills

- **`project-launcher`** owns the research → PRD → gap-analysis → scaffold → GSD handoff pipeline. Use it
  to *produce* a plan/PRD; use **this** skill to turn that plan into a rich `.mdx` review surface and the
  approval gate. project-launcher's `references/plan-discipline.md` shares this skill's discipline.
- **`obsidian-second-brain:json-canvas`** renders `<Canvas>` artboards as a `.canvas` board.
- **`obsidian-second-brain:obsidian-markdown`** owns vault frontmatter/wikilink conventions the plan uses.
- **`rhize-devflow` / `sanity`** skills own the implementation patterns the plan should ground itself in
  (Sanity house style, data-mutation consistency, error lifecycle).

## Provenance

Methodology and the wireframe/canvas/document quality bars are forked from BuilderIO's MIT-licensed
`visual-plan` (`github.com/BuilderIO/skills`). The Rhize MDX format, the Next.js/Obsidian rendering, and
all stack assumptions are original to Rhize. Attribution and drift-check command live in `SOURCES.md`.
