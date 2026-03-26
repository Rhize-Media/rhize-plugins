# Project Launcher Plugin

End-to-end project launcher for Rhize Media. Takes a project idea from napkin sketch through research, PRD generation, critical gap analysis, project scaffolding, and GSD v2 handoff for autonomous development.

## Commands

| Command | Description |
|---------|-------------|
| `/launch-project` | Full 6-phase pipeline: research → PRD → gap analysis → scaffold → GSD handoff |
| `/write-prd` | Phases 1-4: research → interview → PRD → gap analysis |
| `/scaffold-gsd` | Phases 5-6: create project directory + GSD v2 handoff from existing PRD |
| `/grill-prd` | Phase 4 standalone: critical gap analysis of an existing PRD |

## Skills

| Skill | Trigger |
|-------|---------|
| `project-launcher` | "start a new project", "create a PRD", "scaffold for GSD", "prepare for autonomous dev" |

## Reference Docs

| File | Purpose |
|------|---------|
| `references/interview-question-bank.md` | 65 categorized questions across 11 domains |
| `references/prd-template.md` | 14-section PRD structure template |
| `references/claude-md-template.md` | CLAUDE.md generation template with post-phase verification |
| `references/gsd-handoff-guide.md` | Complete guide to .planning/ docs and GSD v2 setup |

## Integrated MCP Servers

| MCP Server | Phase(s) | Purpose |
|------------|----------|---------|
| Obsidian | 1 | Vault search for prior art |
| Firecrawl | 1 | External documentation scraping |
| Context7 | 1, 3 | Framework/library documentation |
| DataForSEO | 1, 2, 3 | SEO keyword data (content projects) |
| Slack | 2, 4, 6 | Team context, approval flows |
| Google Drive | 1, 2 | Existing documents |
| Atlassian | 1 | Jira project history |
| Sentry | 3, 5 | Error tracking setup |
| PostHog | 3, 5 | Analytics integration |
| Sequential Thinking | 3, 4 | Complex reasoning |
| Serena | 1, 5 | Codebase exploration |
| n8n-builder | 3, 5 | n8n node search, workflow validation |
| n8n-executor | 5, 6 | Execute/test n8n workflows on n8n Cloud |

## Integrated Skills (external dependencies †)

| Skill | Phase | Purpose |
|-------|-------|---------|
| `obsidian-skills:vault-search` † | 1 | Vault search for prior art |
| `obsidian-skills:vault-research` † | 1 | Deep topic research |
| `grill-me` † | 4 | Critical gap analysis |
| `write-a-prd` † | 3 | PRD generation |
| `seo-aeo-geo:*` † | 1, 3 | SEO skills for content projects |
| `brand-voice:*` † | 3 | Brand voice for content projects |
| `n8n-automation` † | 3, 5 | n8n workflow building |
| `engineering:system-design` † | 3 | System architecture |
| `engineering:architecture` † | 3, 4 | ADR creation |
| `tdd` † | 5, 6 | Test-driven development |
| `prd-to-issues` † | 4→5 | PRD → GitHub issues (vertical slices) |
| `simplify` † | 6, post-phase | Code review and simplification |

## Commands & Execution Flags

| Command/Flag | Phase(s) | Purpose |
|-------------|----------|---------|
| `/batch` | 5, 6 | Batch parallel operations |
| `/sc:reflect` | Post-phase | Validate task implementation |
| `/simplify` | Post-phase | Review and simplify code |

## Post-Phase Verification Pattern

After each GSD phase, the autonomous Claude runs:
```
/sc:reflect on whether all tasks were implemented and then /simplify your code changes where needed for an optimal solution
```
