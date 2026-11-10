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
| Recreate motion from a supplied site, recording, video, GIF or Lottie file | `reanimate` | Measure the requested animation, implement in the project's existing tools, then record and compare the copy. Default to motion-only; follow the scope and rights rules below. |
| A suitable animated React component | `react-bits` | Fetch current source from `https://reactbits.dev/r/{name}.json`; inspect code/imports/dependencies. Never reconstruct catalog components from memory. Match JS/TS and CSS/Tailwind to the project. |
| Small CSS state transitions or existing motion refinement | `transitions-dev`; add `transitions-polish` when refining timing/easing | Prefer simple state motion; do not introduce GSAP for an ordinary transition. |
| Existing/requested GSAP, complex timelines or scroll choreography | `gsap-core` plus the relevant subset | `gsap-timeline`, `gsap-scrolltrigger`, `gsap-react`, `gsap-frameworks`, `gsap-plugins`, `gsap-utils`, `gsap-performance`; check cleanup and reduced-motion behavior. |
| UX/craft/accessibility review or polish | `impeccable` and its relevant command reference | Load actual project context; use audit/critique/polish as appropriate. A detector pass is not visual or accessibility acceptance. |
| One existing screen that looks AI-generated, fixed and then done | `unslop` | Run its nine passes in order (spacing, color, icons, copy, type, layout, details, visuals, motion), then stop. Never connect a paid image service without approval; leave the visual slot empty and report the prompt. Its story video needs project-local Playwright and ffmpeg only when requested. |
| Rendered page/interaction verification | `playwright-cli` for an isolated CLI browser, or a sufficient available native browser connector | Use `/rhize-devflow:browser-qa` for acceptance sequencing and the chosen tool's own skill/schema for mechanics. |

Current component behavior and dependencies require current source/help evidence. If a live registry
fetch or probe cannot run, keep those details unverified; catalog expectations are not findings.

If an existing ECC design/a11y/motion skill or repository workflow better fits, use it and explain
the choice. Select one primary direction owner; avoid conflicting aesthetic defaults. The anti-slop
skills divide up: Impeccable stays in the project as ongoing vocabulary and detectors, Taste owns
creative direction, and Unslop fixes one screen and stops. An explicit Impeccable command keeps
Impeccable even though Unslop also triggers on "polish". Flag conflicting guidance; never drop one
of them to resolve it. SEO, CMS
and mutation/cache correctness remain with their existing specialist workflows when affected.

React Bits registry setup belongs in the actual app's `components.json` only when needed;
preserve other registries. Impeccable product context belongs in the product, never a global
placeholder PRODUCT.md. Do not invent claims, force a framework, or add decorative motion.

## Reference animation with Reanimate

Load the independently installed `reanimate` skill and its source-specific references. Keep the
target to the requested section, interaction or time range. Copy motion by default, preserving the
project's own brand, content and assets. Use "match it exactly" only when explicitly requested
and the client has the right to use the reference's fonts, images, code and other assets; the
skill's MIT license does not grant rights to a reference site. For login-walled pages, YouTube
or Loom, request a supplied screen recording instead of trying to record the page directly.

Follow upstream capture/spec/build/compare mechanics using the existing CSS, Framer Motion,
GSAP or three.js stack. Compare matching viewport, crop, trigger, duration and frame rate;
inspect the frame sheets and report measured timing/easing and remaining differences. A matching
animation is separate from keyboard, reduced-motion and broader browser acceptance below.

Installation belongs to an explicit global environment-setup task, never a client repository.
Verify Bun and the current setup script's dependency/ffmpeg/Chromium results; the README's
minimum Bun version alone does not prove compatibility with its current lockfile. Report setup
errors and fallbacks, and distinguish fresh-host skill invocation from a successful file install.
Do not upgrade global runtimes or silently replace lockfiles to make setup pass.

## Reconcile upstream defaults with the brief

After loading the selected skills, re-read this section before producing the design. The project
brief and real content override upstream house styles and inspector scores. Do not turn upstream
image counts, motion counts or decorative effects into requirements; omit them unless the brief
or user task needs them. A static, image-free design can be the correct result. Name any conflicting
defaults you rejected. Keep unsupplied claims, capacity, services and signup destinations unresolved;
propose content fields to confirm, never present invented facts as copy. Use labeled field names
in examples, not made-up times or counts. Do not select a mailto/form fallback when the signup
destination is unsupplied; leave that integration decision open.

## Implement and verify affected behavior

Keep motion purposeful and honor `prefers-reduced-motion`. Preserve disclosure/dialog semantics:
clipping or opacity alone does not remove hidden controls from keyboard or assistive technology.
Keep closing content mounted for its animation, prevent focus in collapsed content (for example
with `inert`), and restore focus before hiding it. Preserve the existing semantic component.
For async controls, guard re-entry
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
