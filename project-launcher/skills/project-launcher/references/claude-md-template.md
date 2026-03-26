# CLAUDE.md Template

Generate a project-specific CLAUDE.md using this template. Every section should be populated with real values from the PRD — no placeholders or TODOs.

---

```markdown
# {Project Name}

## Project Overview
{2-3 sentences: what this is, who it serves, core value proposition}

## Tech Stack
- **{Category}:** {Technology} ({version/instance details})
{Repeat for each technology. Lock versions where stability matters.}

## Architecture: {N} {Component Type}
{Numbered list of major components with one-line descriptions}

## Development Approach
- {Primary deliverable format — e.g., "n8n workflow JSON files", "Next.js pages", "Python scripts"}
- {Testing strategy — e.g., "Use DataForSEO Sandbox for API testing"}
- {Build order — e.g., "Build and test each workflow independently, then integrate"}
- {Reference implementations — e.g., "Reference: ../existing-project/"}
- {First tenant/user — e.g., "Rhize Media is the first tenant; SJ Glass is second"}

## {Domain-Specific Design Section}
{e.g., "Multi-Tenant Design", "CMS Architecture", "API Gateway Design"}
{Key structural decisions and how they affect development}

## MCP Servers Available
- **{server-name}** (`{id}`) — {one-line purpose}
{List every MCP server relevant to this project}

## Skills to Use
| Skill | When to Use |
|-------|-------------|
| `{skill-name}` | {specific workflow/phase where this skill applies} |

## Key Files
```
{project-name}/
├── {file/dir}    # {description}
```

## Post-Phase Verification
After completing each GSD phase, run:
`/sc:reflect on whether all tasks were implemented and then /simplify your code changes where needed for an optimal solution`

## Important Notes
- Never push commits — user pushes manually
- {Error investigation approach — e.g., "Check Sentry first, then n8n execution logs"}
- {Cost considerations — e.g., "DataForSEO is pay-per-call — use bulk endpoints"}
- {Data limits — e.g., "Google Sheets has 10M cell limit — archival policy required"}
- {Multi-tenant gotchas — e.g., "Always use schema mapping layer, never hardcode field paths"}
```

## Generation Guidelines

When populating this template:

1. **Be specific** — Don't write "various MCP servers"; list each one with its purpose
2. **Include credentials context** — Where are API keys stored? (env vars, n8n credentials, etc.)
3. **Reference real paths** — Use actual file paths from the scaffold, not abstract descriptions
4. **Match the PRD** — Every technology, integration, and design decision from the PRD should appear here
5. **Write for an autonomous Claude** — This file is read by `/gsd:autonomous`; it needs enough context to make good decisions without asking
