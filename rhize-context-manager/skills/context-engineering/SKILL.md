---
name: context-engineering
tier: custom
domain: dev-flow
maturity: stable
version: 2.0.0
description: >-
  Systematic context, session, and memory management for Claude Code development sessions:
  start/resume/close a working session, preserve and restore context, extract durable memories,
  and keep long sessions lean. Use whenever the user says "start", "begin", "where were we",
  "restore session", "new session", "save context", "remember this", "context is getting heavy",
  "I'm confused/lost", or "done/finished/commit" — and proactively when a session exceeds ~25
  messages and needs hygiene, or before implementing a feature when impact-mapping and the
  component registry should be checked first. Based on Google's Context Engineering guide,
  enhanced with practical automation hooks and slash commands.
---

# Context Engineering Skill

> Systematic management of LLM context through Sessions (immediate), Memory (persistent), and automation hooks.

## Quick Start

### 1. Install Hooks (Optional but Recommended)

Copy hooks to your project's `.claude/hooks/` directory:

```bash
# From your project root
mkdir -p .claude/hooks
cp /path/to/context-engineering/hooks/*.sh .claude/hooks/
chmod +x .claude/hooks/*.sh
```

### 2. Configure Hooks

Add to `.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [{
      "type": "command",
      "command": ".claude/hooks/session-init.sh"
    }],
    "PreToolUse": [
      {
        "type": "command", 
        "command": ".claude/hooks/duplicate-check.sh",
        "toolNames": ["write_file", "create_file"]
      },
      {
        "type": "command",
        "command": ".claude/hooks/pre-commit-guard.sh", 
        "toolNames": ["bash"]
      }
    ],
    "UserPromptSubmit": [{
      "type": "command",
      "command": ".claude/hooks/skill-suggester.sh"
    }]
  }
}
```

### 3. Create Context Files

```bash
# Sprint/context tracking
touch CURRENT_SPRINT.md

# Component inventory (prevents duplication)
touch COMPONENT_REGISTRY.md
```

---

## Core Architecture

### The Two-System Model

```
┌─────────────────────────────────────────────────────────────────┐
│                     CONTEXT ENGINEERING                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────┐          ┌──────────────────────────────┐ │
│  │     SESSIONS     │          │           MEMORY             │ │
│  │  (Working Memory)│          │   (Persistent Knowledge)     │ │
│  ├──────────────────┤          ├──────────────────────────────┤ │
│  │ • Current task   │  ──────► │ • Extracted insights         │ │
│  │ • Conversation   │  Extract │ • User preferences           │ │
│  │ • Active files   │          │ • Project decisions          │ │
│  │ • Recent errors  │  ◄────── │ • Learned patterns           │ │
│  │                  │  Retrieve│ • Error solutions            │ │
│  └──────────────────┘          └──────────────────────────────┘ │
│         │                                   │                    │
│         ▼                                   ▼                    │
│  ┌──────────────────┐          ┌──────────────────────────────┐ │
│  │   Ephemeral      │          │   Persistent                 │ │
│  │   Single session │          │   Cross-session              │ │
│  │   High detail    │          │   Distilled knowledge        │ │
│  └──────────────────┘          └──────────────────────────────┘ │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    AUTOMATION LAYER                       │   │
│  ├──────────────────────────────────────────────────────────┤   │
│  │ Hooks: session-init | duplicate-check | skill-suggester  │   │
│  │ Commands: /start | /done | /context-hygiene | /impact-map│   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Commands

Structured workflows for common development operations.

| Command | Trigger Keywords | Purpose |
|---------|------------------|---------|
| [/start](../../commands/start.md) | start, begin, new session | Initialize session with context loading |
| [/done](../../commands/done.md) | done, finished, commit | Post-implementation validation |
| [/context-hygiene](../../commands/context-hygiene.md) | confused, slow, cleanup | Manage context window health |
| [/impact-map](../../commands/impact-map.md) | implement, create new, build | Map dependencies before changes |

### Command Usage

Commands can be invoked explicitly or detected automatically via the skill-suggester hook.

---

## Hooks

Automated triggers that run at specific points in the Claude Code lifecycle.

| Hook | Trigger Point | Purpose |
|------|---------------|---------|
| [session-init.sh](hooks/session-init.sh) | SessionStart | Load context, check freshness, show status |
| [duplicate-check.sh](hooks/duplicate-check.sh) | PreToolUse (write) | Block duplicate component creation |
| [skill-suggester.sh](hooks/skill-suggester.sh) | UserPromptSubmit | Suggest relevant skills based on keywords |
| [pre-commit-guard.sh](hooks/pre-commit-guard.sh) | PreToolUse (bash) | Warn about unstaged related files |

### Hook Configuration

Hooks use environment variables for customization:

```bash
# session-init.sh
CONTEXT_SPRINT_FILE="CURRENT_SPRINT.md"
CONTEXT_REGISTRY_FILE="COMPONENT_REGISTRY.md"

# duplicate-check.sh  
DUPLICATE_CHECK_PATTERNS="components/|hooks/|utilities/"
COMPONENT_REGISTRY_FILE="COMPONENT_REGISTRY.md"

# skill-suggester.sh
SKILL_IMPLEMENTATION="/skill:impact-map"
SKILL_BUGFIX="/skill:debug"
SKILL_COMPLETION="/skill:done"
```

---

## Session Management

### Session Types

| Type | Duration | Messages | Context Loading | Save Trigger |
|------|----------|----------|-----------------|--------------|
| Feature Implementation | 1-2 hours | 15-30 | Architecture, patterns, related files | Feature complete |
| Bug Fix / Debugging | 30min-2hr | 10-50 | Error context, logs, recent changes | Issue resolved |
| Exploration / Research | Variable | 5-20 | Minimal, grows as needed | Findings documented |
| Code Review / Refactor | 1-2 hours | 10-25 | Style guides, patterns, file context | Review complete |

### Session Boundaries

**Mandatory New Session:**
- Repository/project switch
- Feature/task complete
- Context exhaustion (>80% usage)
- Major topic change

**Recommended New Session:**
- Message count > 25-30
- Duration > 90 minutes
- After long debugging session
- Before starting unrelated work

### Context Exhaustion Signs

- Responses becoming less coherent
- Forgetting earlier conversation details
- Repeated questions about established context
- Circular debugging (same fixes attempted)

---

## Memory Lifecycle

### Memory Types

**Declarative Memory** - Facts and preferences
- User preferences: Language, framework, tooling choices
- Project facts: Architecture decisions, tech stack
- Technical context: Versions, configurations

**Procedural Memory** - Workflows and patterns
- Debug workflows: Investigation patterns
- Implementation patterns: Data fetching, state management
- Review processes: Pre-commit checks, validation

### Extraction Triggers

**DO Extract:**
- Explicit preference stated
- Architecture decision made
- Pattern discovered that worked
- Error resolved with solution

**DON'T Extract:**
- Conversational filler
- Temporary debug attempts that failed
- Common knowledge
- Superseded decisions

---

## MCP Integration

### Available MCP Servers

| Server | Purpose | Key Operations |
|--------|---------|----------------|
| Zen MCP | Session persistence | save_context, restore_context |
| Sentry | Error tracking | search_issues, get_issue_events |
| Vercel | Deployment info | get_deployment_logs |
| Git | Version control | status, diff, log |
| Serena | Project memory | activate_project, list_memories |

### Context Hydration (Session Start)

```
1. Load user preferences (Memory MCP)
2. Load project context (CLAUDE.md, CURRENT_SPRINT.md)
3. Restore saved session (Zen) if continuing work
4. Query relevant memories based on task
```

### Context Persistence (Session End)

```
1. Extract memories from session
2. Save session state (Zen) if incomplete
3. Update sprint/status files
4. Store new entities if using knowledge graph
```

See [MCP-INTEGRATIONS.md](references/MCP-INTEGRATIONS.md) for detailed patterns.

---

## Context Files

### CURRENT_SPRINT.md

Track active work within a sprint:

```markdown
# Current Sprint: [Sprint Name]

## Primary Work Item
- [Active task description]

## Status
- [x] Completed items
- [ ] Pending items

## Decisions Made
- [Decision]: [Rationale]

## Blockers
- [Any blockers]

## Completed This Session
- [Items finished today]
```

### COMPONENT_REGISTRY.md

Prevent duplicate components:

```markdown
# Component Registry

## UI Components
| Component | Location | Purpose |
|-----------|----------|---------|
| Button | components/ui/Button.tsx | Base button |
| Modal | components/ui/Modal.tsx | Dialog wrapper |

## Hooks
| Hook | Location | Purpose |
|------|----------|---------|
| useAuth | lib/hooks/useAuth.ts | Auth state |

## Utilities
| Utility | Location | Purpose |
|---------|----------|---------|
| formatDate | lib/utils/date.ts | Date formatting |
```

---

## Bundled Resources

### Reference Documentation
> **Usage:** Claude should READ these for detailed guidance, not execute.

- [SESSIONS.md](references/SESSIONS.md) - Detailed session management
- [MEMORY-LIFECYCLE.md](references/MEMORY-LIFECYCLE.md) - Extraction/consolidation patterns
- [MCP-INTEGRATIONS.md](references/MCP-INTEGRATIONS.md) - MCP server integration guides
- [WORKFLOWS.md](references/WORKFLOWS.md) - Step-by-step workflow procedures
- [PATTERNS.md](references/PATTERNS.md) - Common patterns and anti-patterns
- [CONFIGURATION.md](references/CONFIGURATION.md) - Project-type templates
- [EVALUATION.md](references/EVALUATION.md) - Memory quality metrics
- [ADVANCED-SCENARIOS.md](references/ADVANCED-SCENARIOS.md) - Multi-project, failure handling

### Hooks (AUTO-TRIGGERED by Claude Code)
> **Usage:** These run automatically via Claude Code hooks system. Copy to `.claude/hooks/` and configure in `.claude/settings.json`. Claude does NOT invoke these directly.

| Hook | Trigger Point | Purpose |
|------|---------------|---------|
| [session-init.sh](hooks/session-init.sh) | `SessionStart` | Load context, show status |
| [duplicate-check.sh](hooks/duplicate-check.sh) | `PreToolUse` (write) | Block duplicate components |
| [skill-suggester.sh](hooks/skill-suggester.sh) | `UserPromptSubmit` | Suggest relevant skills |
| [pre-commit-guard.sh](hooks/pre-commit-guard.sh) | `PreToolUse` (bash) | Warn about unstaged files |

### Commands (READ for workflow guidance)
> **Usage:** These are the plugin's registered slash commands, at the top-level
> `commands/` directory (not duplicated under this skill). Claude should READ them
> to understand workflow steps, then execute the steps described within.

- [start.md](../../commands/start.md) - Session initialization workflow
- [done.md](../../commands/done.md) - Post-implementation checklist
- [context-hygiene.md](../../commands/context-hygiene.md) - Context management steps
- [impact-map.md](../../commands/impact-map.md) - Dependency mapping procedure

### Scripts

#### 🔧 EXECUTE - Analysis & Automation Scripts
> **Usage:** Claude should RUN these scripts to perform analysis or generate outputs.

| Script | Command | Purpose |
|--------|---------|---------|
| `context_analyzer.py` | `python3 scripts/context_analyzer.py --doc-dir .` | Analyze context usage metrics |
| `session_manager.py` | `python3 scripts/session_manager.py handoff --topic "X"` | Generate session handoffs |
| `config_generator.py` | `python3 scripts/config_generator.py --scan .` | Generate project configs |
| `memory_consolidator.py` | `python3 scripts/memory_consolidator.py --demo` | Analyze memory for consolidation |

---

## Quick Reference

```
┌─────────────────────────────────────────────────────────────────┐
│                    CONTEXT ENGINEERING v2.0                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  SESSION START           SESSION END            CONTEXT HEAVY   │
│  ─────────────           ───────────            ─────────────   │
│  □ /start command        □ /done command        □ /context-     │
│  □ Load preferences      □ Extract memories         hygiene     │
│  □ Load sprint context   □ Save if incomplete   □ Summarize     │
│  □ Check freshness       □ Update sprint file   □ New session?  │
│                                                                  │
│  NEW FEATURE             BUG FIX                COMMIT          │
│  ───────────             ───────                ──────          │
│  □ /impact-map first     □ Check Sentry         □ /done first   │
│  □ Check registry        □ Map dependencies     □ Build passes? │
│  □ Reuse existing?       □ Systematic debug     □ All staged?   │
│  □ Plan impl order       □ Test the fix         □ Zen review    │
│                                                                  │
│  HOOKS (automatic)       COMMANDS (explicit)    FILES           │
│  ─────────────────       ──────────────────     ─────           │
│  • session-init          • /start               • CURRENT_      │
│  • duplicate-check       • /done                    SPRINT.md   │
│  • skill-suggester       • /context-hygiene     • COMPONENT_    │
│  • pre-commit-guard      • /impact-map              REGISTRY.md │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```
