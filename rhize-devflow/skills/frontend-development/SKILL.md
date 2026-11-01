---
name: frontend-development
description: >-
  Coordinate frontend design, UI implementation, motion and visual review using the relevant
  installed design skills and observed browser evidence. Use for pages, dashboards, components,
  visual design, UI polish or frontend motion; exclude backend-only and mechanical nonvisual work.
metadata:
  rhize:
    summary: "Selects frontend design and motion skills, preserves project authority, and connects implementation to browser acceptance."
    topics: [frontend, ui, visual-design]
    stacks: []
    router:
      phrases: ["dashboard design", "ui polish", "frontend motion"]
---

# Frontend development

Rhize owns conditional selection and acceptance; upstream skills own their craft and tool mechanics.
For a focused fix, use only the relevant row below. For substantial visual work, combine one
primary direction owner, relevant craft review and browser verification. Do not load every family.

## Establish the surface

Read the brief, repository instructions, existing components/design tokens and package manifest.
Keep the established brand, framework, real content and accessibility constraints authoritative.
For a new direction, record audience/task, primary action, visual direction/reference and affected
states in the existing plan or PRD. Reuse incumbent components before adding dependencies.
Backend-only and mechanical nonvisual work exits this workflow without design or motion work.

## Resolve capabilities in the current host

Use the current Claude or Codex skill inventory, including deferred discovery where supported.
Load each selected installed SKILL.md before applying it; report its actual name and why it fits.
Use the native callable name supplied by the host: global skills such as `impeccable` are bare
names, not invented `impeccable:impeccable` namespaces. Follow references relative to that selected
skill, keeping the working directory in the actual project. Impeccable has host-specific payloads.

File presence is not evidence that a skill is enabled or callable. Respect host overrides; if a
selected capability is missing or disabled, report the gap and use an appropriate available
alternative or repository conventions. Never reinstall, enable a disabled skill, bypass hook trust
or install application dependencies merely to satisfy this workflow. CLI availability is separate
from skill discovery. Use the skill's documented help/probe when execution is needed.

## Select the smallest relevant set

| Work | Installed skill family | Application |
| --- | --- | --- |
| New interface/direction or substantial redesign | `design-taste-frontend` | Art direction and browser self-review; follow its app-screen branch for dashboards. Preserve an established identity. |
| Extract a supplied reference website | `extract-design` | Run Designlang against the relevant URL when authorized; inspect extracted tokens/patterns before adapting them. |
| A suitable animated React component | `react-bits` | Fetch current source from `https://reactbits.dev/r/{name}.json`; inspect code/imports/dependencies. Never reconstruct catalog components from memory. Match JS/TS and CSS/Tailwind to the project. |
| Small CSS state transitions or existing motion refinement | `transitions-dev`; add `transitions-polish` when refining timing/easing | Prefer simple state motion; do not introduce GSAP for an ordinary transition. |
| Existing/requested GSAP, complex timelines or scroll choreography | `gsap-core` plus the relevant subset | `gsap-timeline`, `gsap-scrolltrigger`, `gsap-react`, `gsap-frameworks`, `gsap-plugins`, `gsap-utils`, `gsap-performance`; check cleanup and reduced-motion behavior. |
| UX/craft/accessibility review or polish | `impeccable` and its relevant command reference | Load actual project context; use audit/critique/polish as appropriate. A detector pass is not visual or accessibility acceptance. |
| Rendered page/interaction verification | `playwright-cli` for an isolated CLI browser, or a sufficient available native browser connector | Use `/rhize-devflow:browser-qa` for acceptance sequencing and the chosen tool's own skill/schema for mechanics. |

If an existing ECC design/a11y/motion skill or repository workflow better fits, use it and explain
the choice. Select one primary direction owner; avoid conflicting aesthetic defaults. SEO, CMS
and mutation/cache correctness remain with their existing specialist workflows when affected.

React Bits registry setup belongs in the actual app's `components.json` only when needed;
preserve other registries. Impeccable product context belongs in the product, never a global
placeholder PRODUCT.md. Do not invent claims, force a framework, or add decorative motion.

## Implement and verify affected behavior

Keep motion purposeful and honor `prefers-reduced-motion`. For async controls, guard re-entry
inside the handler, set the guard immediately before its try/finally, and always clear it in
finally. Disable/show pending feedback on a control that stays mounted; test failure recovery.

Use `/rhize-devflow:browser-qa` for the changed views, relevant states and responsive sizes.
Inspect screenshots; exercise affected keyboard/focus, reduced-motion and loading/empty/error/
success/permission behavior. Record URL/build, viewport, state, action, observed result and artifact.
Unavailable checks stay unavailable. Browser interaction retains existing external-write, test-account
and release permissions. A local trace, static detector or screenshot alone is not full acceptance.

Run repository-required code checks through `/rhize-devflow:check`; substantive user-visible
changes enter the UI risk category in `/rhize-devflow:review`. Neither this workflow nor upstream
skills grant permission to send, publish, deploy, change credentials or accept a client deliverable.

Handoff: name the selected skills, preserved design constraints, observed checks, unresolved gaps
and remaining acceptance. Keep discovery, actual skill use, runtime verification and human
acceptance distinct. Read [browser QA](../../commands/browser-qa.md) or
[release review](../../commands/review.md) only for the corresponding stage.
