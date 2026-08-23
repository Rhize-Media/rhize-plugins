---
name: project-kickoff
tier: custom
domain: ops
maturity: beta
description: |
  Scaffold the four standard Cowork client-context files — CLAUDE.md (operating manual),
  BUSINESS.md (the business/offer/market), PERSONALITY.md (brand voice & tone), and INFO.md
  (links, tools, people). Use when onboarding a client or business into a Cowork workspace, when
  the user asks to "create the project context files" or "build CLAUDE.md", or when they drop a
  website or strategy doc and want business context extracted. Works from a website, from strategy
  docs, or from nothing via a guided interview. Trigger even if the user only names one file —
  build the full set unless told otherwise. Not for software projects; a new app, PRD, or code
  scaffold belongs to project-launcher instead.
metadata:
  rhize:
    topics: [project-planning, content-authoring, knowledge-management]
---

# Project Kickoff

Stand up a clean, reusable context layer for a new Cowork project. Output is four files in the project root: **CLAUDE.md**, **BUSINESS.md**, **PERSONALITY.md**, **INFO.md**. Filled-in versions are what make every later task in the project sharp instead of generic.

Templates live in `assets/`. Copy them, fill the `{{TOKENS}}`, save to the project root.

## Core principle
**Never fabricate business facts.** Everything in these files drives real client work, so a confident-but-wrong fact is worse than a blank. If something isn't confirmed, write `[TBD — confirm]` and surface it. When you pull a fact from a website or doc rather than the owner's mouth, tag it `[inferred]` so it gets verified. Flag any stat or claim that's shaky or dated.

## Step 1 — Inventory what's already provided
Before asking anything, figure out which scenario you're in:

- **A · Website given** → fetch it (web_fetch / browser). Extract offer, ICP signals, positioning, proof, contact info, socials, brand colors/voice cues. Mark all of it `[inferred]`.
- **B · Strategy docs / brand docs / uploads given** → read them. Pull everything the templates ask for. Docs from the owner are confirmed (not `[inferred]`).
- **C · Nothing given** → run the guided interview (Step 3) from scratch.

You can be in more than one (e.g. website + a positioning doc). Always extract first, then only ask for the gaps. Don't re-ask anything the inputs already answer.

## Step 2 — Confirm the frame (one quick question, always)
Even with rich inputs, confirm the two things that change everything else:
1. **Whose business is this** — one of the user's own (e.g. their agency / real estate brand) or a client? Name it.
2. **The win** — in one line, what does this project need to produce? (the outcome, not the activity)

## Step 3 — Fill the gaps (interview)
Ask **only what's still missing** after extraction. Batch questions, keep it tight, and prefer the `ask_user_input` tool for the multiple-choice-style ones (easier on mobile). Don't dump all of this at once — stage it in the small groups below, and skip any group already covered by inputs.

Use this as the question bank, grouped by the file each answer feeds:

**Frame (→ CLAUDE.md)**
- Scope: what are we actually producing in this project? (deliverables)
- Output default: files or inline? any formatting preferences?
- Any hard constraints / compliance notes? (real estate disclaimers, claim limits, legal)
- What does "done" look like for a deliverable here?
- Is this a build/dev project? If so, the stack.

**Business (→ BUSINESS.md)**
- What does the business sell, and what's the core offer + price point?
- Ideal customer: who they are, their #1 pain, their #1 desired outcome?
- Main competitors, and what makes this business different (the unique mechanism)?
- Primary goal right now — the number or milestone?

**Voice (→ PERSONALITY.md)**
- Whose voice should output use — personal brand, company, or a named persona?
- Three words for the tone you want, and any tone to avoid?
- Words/phrases to always use or never use?
- **Paste one sample of copy that nails the voice** (theirs or a swipe). This single input lifts quality more than any other — push for it.

**Reference (→ INFO.md)**
- Website + key links (funnel, socials, GBP, key docs)?
- Tools/platforms for this project (CRM, ad accounts, analytics)?
- Key people — decision-maker and day-to-day POC?
- Where brand assets live (logo, colors, fonts)?

If the user can't or won't answer something, leave it `[TBD — confirm]` and move on. Don't stall the whole setup on one blank.

## Step 4 — Write the files
Copy each template from `assets/`, replace every `{{TOKEN}}`, and save to the project root as `CLAUDE.md`, `BUSINESS.md`, `PERSONALITY.md`, `INFO.md`. Rules:
- Keep the prose tight — these are working files, not essays. Bullets and short lines.
- Preserve the `[inferred]` and `[TBD — confirm]` tags exactly so they stand out.
- Don't pad empty fields with filler. A clean `[TBD — confirm]` is the correct output for an unknown.
- In CLAUDE.md, keep the frameworks line and ground rules intact unless the user overrides them.

## Step 5 — Hand off
Present the four files and then surface, in one short list:
- Every `[TBD — confirm]` (what's still missing)
- Every `[inferred]` fact that needs the owner to verify

That list is the user's punch-out for a 100% accurate context layer. Offer to fill TBDs as answers come in.

## Optional add-ons (only if it fits the project)
Mention these but don't build unprompted:
- **SCOPE.md** — if the engagement is big enough to warrant a standalone deliverables/milestones doc instead of folding scope into CLAUDE.md.
- **OFFER.md** — if the project is offer/funnel-heavy and the offer stack deserves its own file.
- **ASSETS/** — if there are enough brand files to warrant a folder pointer beyond INFO.md's asset section.
