---
description: "Critically analyze a PRD for architectural and technical gaps"
---

# Grill a PRD

Run a critical gap analysis on an existing PRD to find architectural holes, missing edge cases, and unrealistic assumptions.

## Instructions

This command runs Phase 4 of the project-launcher pipeline as a standalone operation.

### Input

The user provides:
- A path to an existing PRD: `$ARGUMENTS`
- Or the PRD content directly in the conversation

**If neither is provided**: Ask the user to provide a PRD path or paste the content. If they don't have a PRD yet, redirect them to `/write-prd` or `/launch-project` to create one first.

### Process

1. **Read the PRD thoroughly** — Understand every requirement, integration, and design decision
2. **Run gap analysis** — Use the `grill-me` skill if available. If not, conduct the analysis yourself using the question categories below. Challenge:
   - Architectural decisions and failure modes
   - Missing error handling paths
   - Scalability assumptions
   - Integration risks (API rate limits, auth, data formats)
   - Security considerations
   - MCP server and skill assignments
   - Single points of failure
   - Cost estimates and resource assumptions
3. **Compile answers** — After the analysis session, update the PRD with all resolved questions
4. **Save PRD v2** — Save as new version with `-v2` suffix in the same directory as the original

### Additional Analysis Categories

Also check these domains:
- **Reliability**: What happens when each external API is down?
- **Multi-tenancy**: Data leakage risks? Per-tenant resource limits?
- **Cost**: API call budgets? Caching strategies? Growth projections?
- **Observability**: Can you debug failures from Sentry alone?
- **Human Gates**: Approval UX? Dual-trigger? Timeout handling?
- **Content Pipeline**: Format conversion? Brand voice? SEO validation?

### Output

- Updated PRD v2 with all gaps resolved
- Summary of changes made (new requirements added, assumptions validated, sections rewritten)
