---
description: "Generate a PRD through research, interviews, and critical gap analysis"
---

# Write a PRD

Research, interview, and generate a comprehensive Product Requirements Document with critical gap analysis.

## Instructions

This command runs Phases 1-4 of the project-launcher pipeline (research through gap analysis), producing a PRD v2 ready for scaffolding.

### Process

1. **Phase 1: Research** — Search Obsidian vault, scan codebases, scrape docs, query MCPs
2. **Phase 2: Interview** — Ask targeted questions informed by research
3. **Phase 3: Generate PRD** — Use the `project-launcher` skill's `references/prd-template.md` structure
4. **Phase 4: Gap Analysis** — Use the `grill-me` skill (if available) or follow Phase 4 question categories from SKILL.md to challenge the PRD

### Arguments

- Project idea or description: `$ARGUMENTS`
- If no arguments, ask the user what they want to build

### Output

- PRD v2 saved to `{project_root}/prd/{project-name}-prd-v2.md` if project dir exists
- Otherwise saved to `~/.claude/plans/{project-name}-prd-v2.md` (temporary)
- Ready for `/scaffold-gsd` to turn into a project directory

### Key Rules

- Complete research BEFORE asking questions
- Present questions in batches of 5-10
- Number all requirements (FR-XX.Y, NFR-XX)
- Include MCP servers and skills map in the PRD
- Always run gap analysis — never skip Phase 4
- After gap analysis, incorporate all resolved questions into PRD v2
