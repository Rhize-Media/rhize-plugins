---
name: scroll-craft
description: >-
  Use only for an explicit Scrollcraft request or a brief where an original scroll-driven
  narrative is a primary marketing or editorial requirement. Plan the page grammar,
  one memorable moment and optional signature interaction, then test the built page.
  Not for ordinary transitions, functional dashboards, or reproducing supplied motion.
metadata:
  rhize:
    summary: "Plans and verifies original scroll-driven marketing and editorial experiences."
    topics: [frontend, ui, visual-design]
    stacks: []
    router:
      phrases: ["use scrollcraft", "use scroll craft", "scrollcraft narrative"]
---

# Scrollcraft in Rhize Dev Flow

This is Rhize's opt-in adaptation of [Scrollcraft by Nate Herk](https://github.com/nateherkai/scroll-craft/tree/75d81f74e83692add18cd7a8a8e078b8a887a579).
It brings the design and verification method into the existing project stack, not the
upstream engine, asset generators, bootstrap, or screenshot scripts. The [MIT license](LICENSE)
covers the upstream skill; it does not grant rights to client files or example-site assets.

## Decide whether scrolling serves the story

Read the brief, repository instructions, design tokens, existing components and manifest.
State the audience, intended belief, primary action, verified proof, and owned or licensed
assets. Use existing decisions and explicit creative delegation; ask only about choices that
block delivery. Keep real content, brand, framework, accessibility and performance rules
authoritative. Use Scrollcraft as the single direction owner if the narrative needs it, not
as a second house style on top of Taste. Use Reanimate instead for matching supplied
reference motion and ordinary CSS transitions for ordinary UI changes.

## Score the experience before building it

1. Choose the structure that suits the job: editorial chapters, a live surface, a gallery,
   a split stage, a continuous world, a poster, a filmic sequence or rhythmic cuts. Describe
   how the opening, navigation, sequence and close fit together. Explain why scrolling is
   the right input rather than a simple readable page.
2. Walk the visitor from recognition to a useful next action. For each beat, note what
   they should learn or feel, what triggers that shift, and what is visible at the start,
   midpoint and exit. Give one moment the most emphasis; remove empty scroll unless a
   pause has a deliberate purpose. A bespoke interaction is useful only if it carries
   meaning or helps the visitor. Do not use motion, device, media or length quotas.
3. Compare structure, navigation, hero, sequence, close and signature interaction against
   relevant patterns in this project. If the concept merely re-skins an earlier page,
   revise it. Use the existing project plan or PRD; do not create or read a global registry,
   compare unrelated client files, or add a separate tracking system.
4. Sketch the main focal plane and, if helpful, separate backdrop, subject and foreground
   with convincing contact points and modest movement. Compose narrow screens independently:
   protect focal crop, text contrast, reachability and touch controls before adding effects.
   A static composition is valid if it serves the brief better.

## Implement inside the app

Preserve semantic HTML, DOM reading order, real selectable text, navigation and primary
actions. Prefer native scroll and existing CSS or motion libraries. Avoid scroll trapping
or pointer-only controls. Keep essential content and actions present with reduced motion,
failed media or JavaScript off. Provide an appropriate poster or image fallback, and clean
up observers, listeners and animation timelines on unmount. Follow project performance
budgets, especially for initial content, mobile media and scroll responsiveness.

Use supplied or approved assets locally. This workflow does not run upstream scripts,
install packages, access credentials, call Kie.ai or another paid provider, upload assets,
open LAN servers, create global files, or grant publishing/deployment authority.

## Verify the page, not just the score

Use [Rhize Browser QA](../../commands/browser-qa.md) with an authorized, isolated local
or preview build. Capture opening, midpoint and exit of each affected sequence on desktop
and mobile, then inspect the images. Check composited text contrast at the worst frame,
unintended dead scroll, readable copy, failed media and posters stuck in place. Exercise
keyboard navigation, touch or equivalent, focus visibility, reduced motion, and whether
the CTA and useful controls work without depending on the effect. If the page depends on
mobile video seeking, verify on a real phone where available; emulation alone is not proof
of iOS decoding, playback or touch behavior.

Record the URL/build, device or viewport, motion/media state, observed behavior and
artifact. Report checks not performed without calling them passes. Keep the design plan,
rendered evidence, and human acceptance distinct.
