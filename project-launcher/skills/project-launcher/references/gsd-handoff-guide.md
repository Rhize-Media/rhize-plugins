# GSD v2 Handoff Guide

How to prepare a project for handoff to GSD v2's autonomous development mode.

## What GSD v2 Expects

GSD v2 (Get Shit Done, `get-shit-done-cc` npm package) drives autonomous development through:
- **Phases** → **Plans** → **Execution** → **Verification**
- It reads `.planning/ROADMAP.md` to determine what phases exist
- It reads `.planning/STATE.md` to know where it is
- It reads `CLAUDE.md` for project context
- It re-reads ROADMAP.md after each phase for dynamically inserted phases

### Installation

```bash
cd {project-dir} && npx get-shit-done-cc --claude --local
```

This installs:
- `.claude/commands/gsd/` — All /gsd:* slash commands
- `.claude/agents/` — 18 specialized agents
- `.claude/hooks/` — Context monitor, prompt guard, statusline
- `.claude/get-shit-done/` — Core framework (workflows, templates, references)

### Work Hierarchy

```
Milestone (e.g., v1.0)
  └── Phase (e.g., "ingestion-pipeline", 1-2 weeks)
       └── Plan (fits in one context window)
            └── Execution steps
```

## .planning/ Directory

### PROJECT.md

Extract from PRD:
- Vision statement
- Core value proposition
- Business context
- Stakeholders
- Success criteria (measurable)
- Constraints (technical, budget, timeline)
- Key technical decisions (with rationale)

### REQUIREMENTS.md

Copy from PRD sections 4-5:
- All Functional Requirements (FR-XX.Y format)
- All Non-Functional Requirements (NFR-XX format)
- Group by feature area, preserve numbering

### ROADMAP.md

Transform PRD into phases:

```markdown
# {Project Name} — Roadmap

## Milestone: v1.0 — {Milestone Name}

### Phase 01: {phase-name} (Week N)
**Goal**: {One sentence}

**Plans**: {count} plans

Plans:
- [ ] 01-01-PLAN.md — {Plan description}
- [ ] 01-02-PLAN.md — {Plan description}

**Deliverables**: {What's produced by this phase}

---
```

**Phase sizing guidelines:**
- Each phase = 1-2 weeks of work
- Each plan within a phase = 1 Claude context window (~30min autonomous work)
- Phases ordered by dependency (foundation → features → integrations → monitoring → validation → docs)
- 4-7 plans per phase is typical
- Total phases: 8-15 for a medium project

### STATE.md

```yaml
---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: {name}
status: Ready for autonomous execution
last_updated: "{ISO timestamp}"
progress:
  total_phases: {N}
  completed_phases: 0
  total_plans: {N}
  completed_plans: 0
---
```

### config.json

```json
{
  "workflow": {
    "_auto_chain_active": false
  }
}
```

## Handoff Checklist

Before telling the user the project is ready:

1. **CLAUDE.md completeness**
   - [ ] Tech stack is fully listed with versions
   - [ ] All MCP servers documented with purposes
   - [ ] Skills mapped to workflow steps
   - [ ] Key files tree matches actual directory structure
   - [ ] Important notes include credential locations and gotchas
   - [ ] Post-Phase Verification section includes `/sc:reflect` + `/simplify` command

2. **Planning docs consistency**
   - [ ] PROJECT.md vision matches PRD executive summary
   - [ ] REQUIREMENTS.md covers every PRD requirement
   - [ ] ROADMAP.md phases are ordered by dependency
   - [ ] ROADMAP.md plan count matches STATE.md total_plans
   - [ ] STATE.md initialized at Phase 01, Plan 0

3. **GSD framework**
   - [ ] `.claude/get-shit-done/VERSION` exists
   - [ ] `.claude/commands/gsd/` directory populated
   - [ ] `.claude/agents/` directory populated
   - [ ] `.claude/hooks/` directory populated

4. **Project structure**
   - [ ] Git initialized
   - [ ] .gitignore includes secrets, node_modules, .env
   - [ ] PRD v2 saved in `prd/` directory
   - [ ] Deliverable directories created (with .gitkeep if empty)

## Starting Autonomous Execution

The user opens a new Claude Code session in the project directory and runs:

```
/gsd:autonomous
```

GSD will:
1. Read ROADMAP.md to find the current phase
2. Run `discuss` phase to gather context
3. Run `plan` phase to break down the first plan
4. Run `execute` phase to implement
5. Run `verify` phase to validate
6. **Post-phase reflection**: `/sc:reflect on whether all tasks were implemented and then /simplify your code changes where needed for an optimal solution`
7. Move to next plan, repeat
8. Pause only for explicit user decisions or blockers

## Post-Phase Verification

Every project CLAUDE.md should include this post-phase verification pattern:

```markdown
## Post-Phase Verification
After completing each GSD phase, run:
`/sc:reflect on whether all tasks were implemented and then /simplify your code changes where needed for an optimal solution`
```

This ensures:
- **`/sc:reflect`** catches missed requirements or incomplete implementations
- **`/simplify`** eliminates dead code, finds reuse opportunities, and optimizes before moving on
- Quality compounds across phases — each phase starts from a clean, simplified codebase

## Additional Tools for Autonomous Execution

These tools should be available to the autonomous Claude instance:

| Tool | When Used | Purpose |
|------|-----------|---------|
| `tdd` | During `execute` phase | Red-green-refactor for any code written |
| `prd-to-issues` | Before execution | Break work into GitHub issues (optional, alongside ROADMAP) |
| `/simplify` | After each phase | Code review and simplification |
| `/batch` | During `execute` phase | Parallel file operations and batch generation |
| `n8n-executor` (MCP) | During `verify` phase | Test n8n workflows directly on n8n Cloud |
| `n8n-builder` (MCP) | During `execute` phase | Node search, template lookup, workflow validation |
