# SKILL.patch.md
# Patches for: project-launcher
# Generated: 2026-06-25
# Source: ABSORB from BuilderIO visual-plan (MIT) via rhize-skill-forge — see rhize-meta/skills/rhize-skill-forge/SOURCES.md
# Refinement: FORGE-2026-0625-visual-plan
#
# Tracked record of the visual-plan ABSORB. The pointer edits below were also applied directly to
# SKILL.md (kept in sync); the absorbed methodology lives in references/plan-discipline.md.

## PATCH: writing-the-prd
<!-- ACTION: insert-after "needs to understand every detail" -->

See `references/plan-discipline.md` for the cross-cutting review-surface methodology: plan-as-approval-gate, lead-with-reuse, decide-the-hard-to-reverse-bets-first, a cheap adversarial self-review pass, and when to add diagrams/wireframes. For a rich, reviewable `.mdx` plan (diagrams, file maps, wireframes, data/API contracts) that renders in our Next.js viewer and the Obsidian vault, hand the PRD to the **`rhize-visual-plan`** skill.

## PATCH: obsidian-integration
<!-- ACTION: append -->
- For the reviewable plan artifact itself, use `rhize-visual-plan` to write `Projects/<Project>/Plans/<slug>/plan.mdx` as the second-brain source of truth
