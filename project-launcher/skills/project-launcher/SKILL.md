---
name: project-launcher
description: >
  ALWAYS invoke this skill (via the Skill tool) for any request to start a new project, create a PRD,
  plan a new automation, scaffold a project for GSD v2, or prepare for autonomous development.
  End-to-end project launcher that takes an idea from research through PRD creation, critical gap analysis,
  project scaffolding, and GSD v2 handoff. Triggers on: "start a new project", "create a PRD",
  "plan an automation", "scaffold for GSD", "prepare for autonomous development", "launch a project",
  "set up a new n8n workflow project", "I want to build...", "let's plan...", "new project idea",
  "prepare handoff for GSD", "research and plan", "write requirements for", "scaffold and hand off",
  "gsd handoff", "project kickoff", or any request involving turning a project idea into a structured
  plan ready for autonomous execution. Also triggers when users mention wanting to research a topic
  before building, gather requirements, interview about a project, analyze a PRD for gaps,
  or prepare a CLAUDE.md and .planning directory for a new codebase.
  Do NOT handle project planning with general tools — this skill has a proven 6-phase methodology
  with integrated MCP server orchestration and GSD v2 framework knowledge.
---

# Project Launcher

Take a project idea from initial concept through research, requirements gathering, PRD creation, critical gap analysis, project scaffolding, and GSD v2 handoff — producing everything needed for autonomous development.

This skill codifies a proven methodology. Each phase has specific outputs that feed the next, and the entire pipeline is designed to produce a project that can be handed to `/gsd:autonomous` and run unattended.

## The 6-Phase Pipeline

```
Phase 1: Research & Context Gathering
  ↓ (context brief)
Phase 2: Requirements Interview
  ↓ (answered requirements)
Phase 3: PRD Generation
  ↓ (comprehensive PRD v1)
Phase 4: Critical Gap Analysis (/grill-me)
  ↓ (PRD v2 with gaps resolved)
Phase 5: Project Scaffolding
  ↓ (directory + CLAUDE.md + .planning/)
Phase 6: GSD v2 Handoff
  ↓ (ready for /gsd:autonomous)
```

---

## Phase 1: Research & Context Gathering

**Goal**: Build a comprehensive understanding of the problem space before asking the user anything.

**Why this matters**: Coming to the requirements interview already informed means fewer questions for the user, better questions when you do ask, and a PRD grounded in reality rather than assumptions.

### Sources to Check (in parallel where possible)

1. **Obsidian Vault** — Search for related notes, past ideas, existing plans
   - Use `obsidian-second-brain:vault-search` skill or Obsidian MCP (`obsidian_global_search`)
   - Look for: prior art, related projects, decision history, domain knowledge
   - Check memory files for existing project context

2. **Existing Codebase** — Scan for patterns, conventions, reusable infrastructure
   - Check `~/dev-local/` for related projects
   - Read CLAUDE.md files from similar projects for tech stack patterns
   - Look for shared infrastructure (n8n workflows, Sanity schemas, API integrations)

3. **External Documentation** — Scrape API docs, framework guides, service documentation
   - Use Firecrawl MCP (`firecrawl_scrape`, `firecrawl_map`) for targeted doc scraping
   - Use Context7 MCP for framework/library documentation
   - Use WebSearch for market research, competitor analysis, pricing

4. **MCP Servers** — Query specialized data sources
   - DataForSEO for SEO/keyword data if content-related
   - Slack for team context and prior discussions
   - Google Drive for existing documents and spreadsheets
   - Jira/Atlassian for related project history

### Output: Context Brief

Compile findings into a structured summary:

```markdown
## Context Brief: [Project Name]

### Prior Art (from vault/codebase)
- [What exists already, related projects, reusable patterns]

### Domain Research
- [API capabilities, framework constraints, market context]

### Technical Landscape
- [Available MCP servers, existing integrations, infrastructure]

### Key Assumptions to Validate
- [Things discovered that need user confirmation]
```

---

## Phase 2: Requirements Interview

**Goal**: Fill gaps in understanding through targeted questions — not a generic questionnaire, but questions informed by Phase 1 research.

### Interview Strategy

The research from Phase 1 should shape your questions. If you already know the answer from research, don't ask it — confirm it. Focus questions on:

1. **Architecture decisions** the research can't answer (multi-tenant vs single? approval flows? human gates?)
2. **Business constraints** (budget, timeline, team size, existing commitments)
3. **Integration specifics** (which platforms, which accounts, which APIs)
4. **Scope boundaries** (what's in v1 vs later, what's explicitly out of scope)
5. **Quality bar** (error handling expectations, monitoring needs, SLA requirements)

### Question Categories

See `references/interview-question-bank.md` for a categorized question bank. Draw from it based on project type:

- **Automation projects**: Input sources, processing logic, output destinations, error handling, monitoring
- **Web applications**: Tech stack, CMS, auth, deployment, analytics, SEO
- **Content systems**: Sources, transformation pipeline, approval gates, distribution channels
- **Integration projects**: APIs, data mapping, sync frequency, conflict resolution

### Interview Format

Present questions in numbered batches of 5-10, grouped by theme. This lets the user answer efficiently and you can adapt follow-up questions based on their responses.

After the user answers, compile all decisions into the PRD — don't make them repeat themselves later.

---

## Phase 3: PRD Generation

**Goal**: Produce a comprehensive Product Requirements Document that captures everything needed to build the system.

### PRD Structure

Use the template at `references/prd-template.md`. Key sections:

1. **Executive Summary** — One paragraph explaining what this is and why it matters
2. **System Architecture** — Visual overview of components and data flow
3. **Workflow Overview** — Numbered workflows with trigger, process, output, human gate, error path
4. **Functional Requirements** — Grouped by workflow/feature, numbered (FR-XX.Y)
5. **Non-Functional Requirements** — Reliability, cost, scalability, security
6. **Multi-Tenancy Design** (if applicable) — Data isolation, per-tenant config
7. **Integration Map** — Every external service with its role and API details
8. **Approval Gates / Human Checkpoints** — Where humans review before proceeding
9. **Error Handling Strategy** — How failures are detected, retried, and escalated
10. **Monitoring & Observability** — What's tracked, where alerts go
11. **Data Architecture** — Storage design, data flow, archival policy
12. **MCP Servers & Skills Map** — Which tools to use at each stage of development
13. **Open Questions** — Anything still unresolved
14. **Appendix** — API reference notes, schema definitions, cost estimates

### Writing the PRD

- Number every requirement (FR-01.1, NFR-03, etc.) so they're referenceable
- Be specific about API endpoints, data shapes, and integration patterns
- Include the skills and MCP servers needed at each workflow step
- Call out assumptions explicitly so the gap analysis can challenge them
- Write for the audience: a Claude instance running `/gsd:autonomous` that needs to understand every detail

### Save Location

Save the PRD to the appropriate location:
- If project dir exists: `{project_root}/prd/{project-name}-prd.md`
- If not yet scaffolded: `~/.claude/plans/{project-name}-prd.md` (temporary, moves to `prd/` in Phase 5)
- After Phase 4 gap analysis, the file becomes `{project-name}-prd-v2.md`

---

## Phase 4: Critical Gap Analysis

**Goal**: Stress-test the PRD for architectural gaps, missing edge cases, and unrealistic assumptions before committing to implementation.

### Invoke the Grill-Me Skill

Use the `grill-me` skill to conduct a rigorous analysis. The grill-me process will:

1. Challenge architectural decisions and ask "what if X fails?"
2. Probe for missing error handling paths
3. Question scalability assumptions
4. Identify integration risks (API rate limits, auth complexity, data format mismatches)
5. Check for missing security considerations
6. Validate that the MCP server and skill assignments are correct
7. Look for single points of failure
8. Challenge cost estimates and resource assumptions

### Question Categories to Ensure Coverage

- **Reliability**: What happens when each external API is down? Retry strategy? Circuit breakers?
- **Multi-tenancy**: Data leakage risks? Per-tenant resource limits? Onboarding automation?
- **Cost**: API call budgets? Caching strategies? Growth cost projections?
- **Observability**: Can you debug a failure at 2am from Sentry alone? What's the alert chain?
- **Content Pipeline** (if applicable): Format conversion fidelity? Brand voice enforcement? SEO validation?
- **Human Gates**: What's the approval UX? Dual-trigger (Sheet + Slack)? Timeout handling?

### Incorporate Answers

After the grill-me session, update the PRD with all resolved questions and new requirements. This produces **PRD v2** — the version that gets handed to GSD.

---

## Phase 5: Project Scaffolding

**Goal**: Create the project directory with everything a Claude instance needs to start autonomous development.

### Directory Structure

```
{project-name}/
├── CLAUDE.md                    # Full project context (see template below)
├── .gitignore
├── .planning/                   # GSD v2 planning docs
│   ├── PROJECT.md               # Vision, stakeholders, constraints
│   ├── REQUIREMENTS.md          # All FRs and NFRs from PRD
│   ├── ROADMAP.md               # Phases and plans
│   ├── STATE.md                 # Current position tracker
│   └── config.json              # GSD workflow config
├── prd/
│   └── {project-name}-prd-v2.md # Final PRD (post gap analysis)
├── {deliverable-dirs}/          # Project-specific (workflows/, src/, etc.)
└── .claude/                     # GSD v2 framework (installed via npx)
    ├── settings.json
    ├── agents/
    ├── commands/gsd/
    ├── hooks/
    └── get-shit-done/
```

### Install GSD v2

```bash
cd {project-dir} && npx get-shit-done-cc --claude --local
```

### CLAUDE.md Template

The CLAUDE.md is the most important file — it's what the autonomous Claude instance reads first. See `references/claude-md-template.md` for the full template. It must include:

- **Project overview** — What this is, in 2-3 sentences
- **Tech stack** — Every technology, locked versions where applicable
- **Architecture summary** — Component overview matching the PRD
- **Development approach** — How to build/test each component
- **MCP servers available** — Every MCP server with its purpose
- **Skills to use** — Table mapping skills to workflow steps
- **Key files** — Directory tree with descriptions
- **Execution Strategy: Worktree + Subagent-Driven Development (MANDATORY)** — The 3-layer execution stack (GSD parent → worktree agent → per-task subagents with review gates) that prevents context window exhaustion while maintaining quality. See `references/gsd-handoff-guide.md` for the full template text to include.
- **Post-Phase Verification** — The `/sc:reflect` + `/simplify` command to run after each GSD phase
- **Important notes** — Deployment patterns, credentials, gotchas

### .planning/ Documents

Generate from the PRD:

- **PROJECT.md**: Extract vision, stakeholders, constraints, success criteria, technical decisions
- **REQUIREMENTS.md**: Copy all FRs and NFRs, organized by feature group
- **ROADMAP.md**: Break PRD into phases (1-2 weeks each), each phase into plans (1 context window each)
- **STATE.md**: Initialize at Phase 01, Plan 0, status "Ready for autonomous execution"
- **config.json**: `{ "workflow": { "_auto_chain_active": false } }`

### Roadmap Planning Guidelines

- Each **phase** should be completable in 1-2 weeks
- Each **plan** within a phase should be completable in one Claude context window
- Order phases by dependency: foundation → core features → integrations → distribution → monitoring → validation → docs
- Include a final "multi-tenant validation" phase if the project is multi-tenant
- Include a "documentation-handoff" phase at the end

---

## Phase 6: GSD v2 Handoff

**Goal**: Verify everything is in place and brief the user on how to start autonomous execution.

### Handoff Checklist

Verify all of these exist and are consistent:

- [ ] `CLAUDE.md` references correct file paths and MCP servers
- [ ] `CLAUDE.md` includes `## Execution Strategy: Worktree + Subagent-Driven Development (MANDATORY)` section
- [ ] `CLAUDE.md` includes `## Post-Phase Verification` section with `/sc:reflect` + `/simplify` command
- [ ] `.claude/settings.json` has `superpowers@claude-plugins-official` set to `true`
- [ ] `.planning/PROJECT.md` matches PRD executive summary
- [ ] `.planning/REQUIREMENTS.md` covers all PRD requirements
- [ ] `.planning/ROADMAP.md` has realistic phases with concrete plans
- [ ] `.planning/STATE.md` is initialized correctly
- [ ] `.planning/config.json` exists
- [ ] `prd/` contains the final PRD v2
- [ ] `.claude/` contains GSD v2 framework (check `.claude/get-shit-done/VERSION`)
- [ ] Git repo is initialized
- [ ] Deliverable directories exist (even if empty with .gitkeep)

### Handoff Brief

Present to the user:

```markdown
## Ready for Handoff

**Project**: {name}
**Location**: {path}
**GSD Version**: {version}
**Phases**: {count} phases, {plan_count} plans
**Estimated Duration**: {weeks} weeks

### To Start Autonomous Execution:
1. Open a new Claude Code session in `{project-dir}`
2. Run `/gsd:autonomous`
3. GSD will drive: discuss → plan → execute → verify for each phase

### What You'll Need:
- {list any credentials, API keys, or manual setup needed}
- {list any external services that need provisioning}

### Monitoring:
- Check `.planning/STATE.md` for progress
- GSD pauses for explicit decisions or blockers
- Slack notifications on `#content-errors` (if configured)
```

---

## MCP Server Reference

These MCP servers are commonly used across the 6 phases:

| MCP Server | Phase(s) | Purpose |
|------------|----------|---------|
| Obsidian | 1 | Vault search for prior art and domain knowledge |
| Firecrawl | 1 | External documentation scraping |
| Context7 | 1, 3 | Framework/library documentation |
| DataForSEO | 1, 2, 3 | SEO keyword data (content projects) |
| Slack | 2, 4, 6 | Team context, approval flows, notifications |
| Google Drive | 1, 2 | Existing documents and spreadsheets |
| Atlassian | 1 | Jira project history and context |
| Sentry | 3, 5 | Error tracking setup references |
| PostHog | 3, 5 | Analytics integration references |
| Sequential Thinking | 3, 4 | Complex reasoning during PRD and gap analysis |
| Serena | 1, 5 | Codebase exploration and session memory |
| n8n-builder | 3, 5 | n8n node search, template lookup, workflow validation |
| n8n-executor | 5, 6 | Execute and test n8n workflows directly on n8n Cloud instance |

## Skills Reference

> **Note**: Skills marked with † are external dependencies — they must be installed separately (via plugins, user-level skills, or built-in skills). If a skill is not available, follow the inline guidance in the relevant phase section above. The `grill-me` skill is particularly critical to Phase 4; if unavailable, conduct gap analysis manually using the question categories in Phase 4.

| Skill | Phase(s) | Purpose |
|-------|----------|---------|
| `obsidian-second-brain:vault-search` † | 1 | Search vault for related ideas |
| `obsidian-second-brain:vault-research` † | 1 | Deep research on topics |
| `grill-me` † | 4 | Critical gap analysis of PRD |
| `write-a-prd` † | 3 | PRD generation (can complement this skill) |
| `seo-aeo-geo:*` † | 1, 3 | SEO skills for content projects |
| `brand-voice:*` † | 3 | Brand voice for content projects |
| `n8n-automation` † | 3, 5 | n8n workflow projects (user-level: `~/.claude/skills/`) |
| `engineering:system-design` † | 3 | System architecture decisions |
| `engineering:architecture` † | 3, 4 | ADR creation |
| `tdd` † | 5, 6 | TDD workflow for code written during execution |
| `prd-to-issues` † | 4→5 | Break PRD into vertical-slice GitHub issues |
| `simplify` † | 6, Post-phase | Review code changes for reuse, quality, efficiency |

## Commands & Execution Flags

| Command/Flag | Phase(s) | Purpose |
|-------------|----------|---------|
| `Agent(isolation: "worktree")` | All GSD execution | **MANDATORY** — Every plan runs in a worktree-isolated sub-agent to prevent context window exhaustion |
| `subagent-driven-development` | Inside each worktree | Per-task dispatch with spec compliance + code quality review gates |
| `dispatching-parallel-agents` | GSD execution | Run independent plans concurrently in separate worktrees |
| `using-git-worktrees` | Plan execution | Worktree creation, .gitignore safety, branch management |
| `/batch` | 5, 6 | Batch parallel operations during scaffold and multi-file generation |
| `/sc:reflect` | Post-phase | Validate all planned tasks were implemented |
| `/simplify` | Post-phase | Review and simplify code changes |

---

## Post-Phase Verification Pattern

After each GSD phase completes during autonomous execution, the following verification prompt should be applied:

```
/sc:reflect on whether all tasks were implemented and then /simplify your code changes where needed for an optimal solution
```

This ensures:
1. **`/sc:reflect`** — Validates all planned tasks were actually implemented, catches missed requirements
2. **`/simplify`** — Reviews the code just written for reuse opportunities, dead code, and unnecessary complexity

This pattern should be documented in the project's `CLAUDE.md` under "Important Notes" so the autonomous Claude instance applies it consistently. When generating the CLAUDE.md in Phase 5, include:

```markdown
## Post-Phase Verification
After completing each GSD phase, run:
`/sc:reflect on whether all tasks were implemented and then /simplify your code changes where needed for an optimal solution`
```

---

## PRD-to-Issues Alternative Path

When a project uses **GitHub Issues** instead of (or alongside) GSD's `.planning/ROADMAP.md`, use the `prd-to-issues` skill in Phase 4→5 to:

1. Break the PRD into independently-grabbable GitHub issues using tracer-bullet vertical slices
2. Each issue is a thin end-to-end slice (not a horizontal layer)
3. Issues can be assigned to parallel agents or sprints
4. This is complementary to GSD — you can have both a ROADMAP.md and GitHub issues

Use `prd-to-issues` when:
- The project will be worked on by multiple people/agents in parallel
- You want issue-level tracking in GitHub alongside GSD phase tracking
- The user prefers GitHub Projects over `.planning/STATE.md` for progress visibility

---

## TDD Integration

For projects that produce executable code (n8n Code nodes, scripts, API integrations), the `tdd` skill should be invoked during Phase 5 scaffolding to establish the test-first pattern:

1. Scaffold test directories alongside deliverable directories
2. Write test stubs for critical integration points before implementation
3. Document the TDD expectation in `CLAUDE.md` so autonomous execution follows red-green-refactor

---

## Obsidian Integration

After the project is scaffolded and handed off, offer to save a project summary note to the user's Obsidian vault:

- Location: `Projects/Personal Projects/{project-name}/` (or appropriate folder)
- Include: project overview, tech stack, key decisions, link to PRD, GSD status
- Tag with: `#project`, `#status/active`, `#gsd`
- This ensures the project is discoverable in future vault searches
