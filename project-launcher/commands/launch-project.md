---
description: "Full project launcher — research, PRD, gap analysis, scaffold, GSD v2 handoff"
---

# Launch Project

Run the complete 6-phase project launcher pipeline for a new project idea.

## Instructions

You are running the `project-launcher` skill's full pipeline. Follow all 6 phases in order:

1. **Research & Context Gathering** — Search Obsidian vault, scan existing codebases, scrape external docs, query MCP servers
2. **Requirements Interview** — Ask targeted questions informed by research (use `references/interview-question-bank.md`)
3. **PRD Generation** — Create comprehensive PRD using `references/prd-template.md`
4. **Critical Gap Analysis** — Use the `grill-me` skill (if installed) or run `/grill-prd` to stress-test the PRD
5. **Project Scaffolding** — Create directory structure, CLAUDE.md, .planning/ docs, install GSD v2
6. **GSD v2 Handoff** — Verify completeness, brief user on how to start autonomous execution

Read the full `project-launcher` SKILL.md for detailed instructions on each phase.

## Arguments

The user may provide:
- A project idea or description: `$ARGUMENTS`
- If no arguments, start Phase 1 by asking what they want to build

## Key Rules

- Always complete Phase 1 research BEFORE asking questions in Phase 2
- Present interview questions in numbered batches of 5-10
- Save PRD to `{project_root}/prd/` if project dir exists, otherwise `~/.claude/plans/` temporarily
- Always run gap analysis in Phase 4 — use `grill-me` skill if available, otherwise follow Phase 4 question categories from SKILL.md
- Install GSD v2 via `npx get-shit-done-cc --claude --local` in Phase 5
- Offer to save a summary note to Obsidian after Phase 6
