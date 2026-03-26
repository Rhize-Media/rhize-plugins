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

## Execution Strategy: Worktree + Subagent-Driven Development (MANDATORY)

**Every GSD plan MUST be executed via a sub-agent running in a git worktree, using the `subagent-driven-development` pattern internally.** This is not optional — it prevents context window exhaustion during autonomous runs while maintaining quality through spec compliance and code quality review gates.

### Why This Is Required

A typical Rhize project loads ~60-80K tokens of standing context (SuperClaude framework + enabled plugins + MCP tool definitions) before any work begins. With a ~200K token context window, that leaves only ~120K for actual work. After reading plan files, CLAUDE.md, and a few source files, the agent hits the 75% context monitor warning almost immediately — resulting in a death spiral where the agent spends its remaining tokens trying to wrap up instead of doing real work.

Worktree sub-agents solve this because each one starts with a **fresh context window** containing only the CLAUDE.md and the plan file.

### The Execution Stack

```
Layer 3: GSD Autonomous (thin parent orchestrator)
  │  Reads ROADMAP.md + STATE.md only
  │  Never reads source files, never runs tools
  │  Dispatches one worktree agent per plan
  │
  └─ Layer 2: Agent(isolation: "worktree") — one per plan
       │  Fresh context window (~200K available)
       │  Reads CLAUDE.md + XX-YY-PLAN.md
       │  Uses subagent-driven-development pattern:
       │
       └─ Layer 1: Per-task subagents (fresh context each)
            ├── Implementer subagent (writes code, runs tests, commits)
            ├── Spec reviewer subagent (verifies plan compliance)
            └── Code quality reviewer subagent (catches bugs, style issues)
```

**Each layer has a single responsibility:**
- **Layer 3** (GSD parent): Phase sequencing, STATE.md updates, branch merging
- **Layer 2** (Worktree agent): Plan-level orchestration, task extraction, review loops
- **Layer 1** (Task subagents): Individual task implementation with focused scope

### The Execution Pattern

Every project CLAUDE.md scaffolded by this plugin MUST include this section:

```markdown
## Execution Strategy: Worktree + Subagent-Driven Development (MANDATORY)
Every GSD plan MUST be executed via a sub-agent running in a git worktree (`isolation: "worktree"`), using the `subagent-driven-development` pattern internally. This is not optional — it solves context window exhaustion while maintaining quality gates.

**Why**: This project has ~70K tokens of standing context (SuperClaude + plugins + MCP tools). A single context window cannot hold that overhead AND complete a meaningful plan. Worktree sub-agents start fresh with only the CLAUDE.md and plan file loaded.

**Pattern for `/gsd:autonomous` and `/gsd:execute-phase`**:
\```
For each plan in the phase:
  1. Agent(isolation: "worktree") → orchestrate the plan
  2. Worktree agent reads CLAUDE.md + .planning/XX-YY-PLAN.md
  3. Worktree agent extracts tasks, dispatches per-task implementer subagents
  4. Each task: implement → spec review → code quality review → fix loop
  5. Worktree agent commits completed work to worktree branch
  6. Parent merges worktree branch, updates STATE.md
  7. Next plan starts in fresh worktree
\```

**For parallel-safe plans** (no shared file dependencies):
Use multiple concurrent worktree agents via the `dispatching-parallel-agents` pattern.
```

### Parallel Execution of Independent Plans

When a phase contains plans that don't share file dependencies, they can run concurrently in separate worktrees:

```
Phase 02: ingestion-pipeline
  Plan 02-01 (RSS branch)        → Agent(isolation: "worktree") ─┐
  Plan 02-02 (email branch)      → Agent(isolation: "worktree") ─┤ parallel
  Plan 02-03 (YouTube branch)    → Agent(isolation: "worktree") ─┘
  Plan 02-04 (error handling)    → Agent(isolation: "worktree")   ← sequential (depends on 01-03)
```

Each worktree agent internally runs `subagent-driven-development`:
```
Worktree Agent (Plan 02-01: RSS branch)
  ├── Task 1: RSS feed reader node
  │   ├── Implementer subagent → builds it
  │   ├── Spec reviewer subagent → checks plan compliance
  │   └── Code quality reviewer → checks quality
  ├── Task 2: Client lookup logic
  │   ├── Implementer → builds it
  │   ├── Spec reviewer → checks compliance
  │   └── Code quality reviewer → checks quality
  └── commits all work, returns to parent
```

The parent agent's only job is orchestration: dispatch worktree agents, wait for completion, merge branches, update STATE.md.

### Plugin Dependency

The `superpowers` plugin MUST be enabled in settings.json — it provides three skills that compose into this stack:
- `using-git-worktrees` — worktree creation, .gitignore safety, branch management
- `subagent-driven-development` — per-task dispatch with two-stage review (spec + quality)
- `dispatching-parallel-agents` — concurrent worktree dispatch for independent plans

The scaffold step automatically enables `superpowers` in the project's `settings.json`.

### Quality Gates per Task

The `subagent-driven-development` pattern enforces these gates on every task within a plan:

1. **Implementer self-review**: Catches obvious issues before handoff
2. **Spec compliance review**: Fresh subagent verifies the implementation matches the plan — no over-building, no under-building
3. **Code quality review**: Fresh subagent checks for bugs, style, performance — only runs after spec compliance passes
4. **Fix loop**: If either reviewer finds issues, the implementer fixes and re-submits until approved

This means every committed piece of work has passed 3 independent reviews before the parent agent ever sees it.

## Starting Autonomous Execution

The user opens a new Claude Code session in the project directory and runs:

```
/gsd:autonomous
```

GSD will:
1. Read ROADMAP.md to find the current phase
2. Run `discuss` phase to gather context
3. Run `plan` phase to break down the first plan
4. **Dispatch a worktree-isolated sub-agent** to execute the plan using `subagent-driven-development`
5. Worktree agent extracts tasks, dispatches implementer + reviewer subagents per task
6. Merge the worktree branch upon completion
7. Run `verify` phase to validate
8. **Post-phase reflection**: `/sc:reflect on whether all tasks were implemented and then /simplify your code changes where needed for an optimal solution`
9. Move to next plan, repeat
10. Pause only for explicit user decisions or blockers

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
| `Agent(isolation: "worktree")` | **Every plan execution** | **MANDATORY** — Prevents context window exhaustion |
| `dispatching-parallel-agents` | Independent plans | Run multiple plans concurrently in separate worktrees |
| `superpowers:using-git-worktrees` | Plan execution | Worktree creation, safety verification, branch management |
| `tdd` | During `execute` phase | Red-green-refactor for any code written |
| `prd-to-issues` | Before execution | Break work into GitHub issues (optional, alongside ROADMAP) |
| `/simplify` | After each phase | Code review and simplification |
| `/batch` | During `execute` phase | Parallel file operations and batch generation |
| `n8n-executor` (MCP) | During `verify` phase | Test n8n workflows directly on n8n Cloud |
| `n8n-builder` (MCP) | During `execute` phase | Node search, template lookup, workflow validation |
