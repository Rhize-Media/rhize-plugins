---
description: "Scaffold a project directory and prepare for GSD v2 autonomous handoff"
---

# Scaffold for GSD v2

Create a project directory with CLAUDE.md, .planning/ docs, and GSD v2 framework — ready for autonomous development.

## Instructions

This command runs Phases 5-6 of the project-launcher pipeline. It assumes a PRD already exists.

### Required Input

The user must provide either:
- A path to an existing PRD: `$ARGUMENTS`
- A project directory that already contains a PRD in `prd/` or `.claude/plans/`

If no PRD is found, tell the user to run `/launch-project` for the full pipeline, or `/write-prd` to create a PRD first.

### Process

1. **Read the PRD** — Extract all requirements, architecture, tech stack, integrations
2. **Create project directory** (if it doesn't exist) — Ask user for location
3. **Generate CLAUDE.md** — Using `references/claude-md-template.md`, populate with PRD details
4. **Generate .planning/ docs**:
   - `PROJECT.md` — Vision, stakeholders, constraints from PRD
   - `REQUIREMENTS.md` — All FRs and NFRs from PRD
   - `ROADMAP.md` — Break PRD into phases and plans (see `references/gsd-handoff-guide.md`)
   - `STATE.md` — Initialize at Phase 01
   - `config.json` — Default GSD config
5. **Install GSD v2** — `npx get-shit-done-cc --claude --local`
6. **Initialize git** — `git init`, create `.gitignore`
7. **Create deliverable directories** — Based on project type (workflows/, src/, scripts/, templates/)
8. **Copy PRD** — Into `prd/` directory
9. **Run handoff checklist** — Verify all files exist and are consistent
10. **Brief user** — How to start `/gsd:autonomous`
