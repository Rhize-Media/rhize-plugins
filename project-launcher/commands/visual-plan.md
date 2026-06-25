---
description: "Turn a plan or PRD into a rich, reviewable .mdx visual plan — diagrams, wireframes, file maps, data/API contracts — rendered in Next.js and the Obsidian vault"
---

# Visual Plan

Invoke the `rhize-visual-plan` skill to turn an implementation plan into a structured `plan.mdx` review artifact that a human can scan, comment on, and approve before code starts.

## Instructions

You are running the `rhize-visual-plan` skill. Read its `SKILL.md` and `references/mdx-plan-format.md`, then follow the workflow:

1. **Research** the codebase/vault; ground the plan in real files, schema, actions, and symbols (lead with reuse).
2. **Choose the visual surface** — none / canvas / canvas+behavior-notes. Don't add visual chrome by default.
3. **Author `plan.mdx`** in the vault (`Projects/<Project>/Plans/<slug>/plan.mdx`) or repo (`plans/<slug>/plan.mdx`) using the Rhize component vocabulary.
4. **Render** in the Next.js viewer (`templates/`) and/or Obsidian; always give the user the actual URL/path.
5. **Self-review** the high-stakes plans with one adversarial sub-agent pass — surface first, review concurrently.
6. **Approval gate:** get sign-off, set frontmatter `status: approved`, then begin code.

## Arguments

- A plan, a `project-launcher` PRD path, or a task description: `$ARGUMENTS`
- If a PRD or pasted plan exists, use it as source material and produce a clean, standalone visual plan (no "unlike the previous version" language).
- If no arguments, ask what the plan is for, then start with research.

## Key Rules

- Rhize-owned format — **no external plan service or `@agent-native` dependency.**
- Planning is read-only; make no source edits until the plan is approved.
- Exactly one bottom `<OpenQuestions>` block; never scatter open questions through the body.
