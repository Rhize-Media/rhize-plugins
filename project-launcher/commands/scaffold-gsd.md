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
8. **Install hookify guardrails** — If the project uses the Rhize Next.js stack (Next.js + Supabase + Sanity), copy the starter rule set into `.claude/`:
   ```bash
   mkdir -p .claude
   cp "${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/plugins/marketplaces/rhize-plugins/project-launcher}/skills/project-launcher/references/hookify-rules/nextjs-rhize-stack/hookify."*.local.md .claude/
   ```
   This installs 7 rules: PR-review trigger, direct-push-to-main block, `NEXT_PUBLIC_` secret-leak block, Supabase service-role-in-client block, pre-stop verification, Sanity schema skill hint, and SEO skill hint. See `references/hookify-rules/nextjs-rhize-stack/README.md` for the full table. Tell the user which rules were installed and which are `block` vs `warn`.
9. **Copy PRD** — Into `prd/` directory
10. **Run handoff checklist** — Verify all files exist and are consistent
11. **Brief user** — How to start `/gsd:autonomous`
