# PRD Template

Use this structure when generating PRDs in Phase 3. Adapt sections based on project type — not every project needs every section, but all projects need the core sections.

---

```markdown
# {Project Name} — Product Requirements Document

**Version**: v1 (pre-gap-analysis) | v2 (post-gap-analysis)
**Date**: {date}
**Author**: Claude + {user name}
**Status**: Draft | Under Review | Approved

---

## 1. Executive Summary

{2-3 sentences: what is this system, what problem does it solve, who benefits}

## 2. System Architecture

{High-level component diagram in text/mermaid format}
{Data flow: input sources → processing → output destinations}
{Key integration points}

## 3. Workflow Overview

{For automation projects: numbered workflow list with trigger → process → output}
{For web apps: feature list with user flows}

### Workflow N: {Name}
- **Trigger**: {What starts this workflow}
- **Process**: {What happens step by step}
- **Output**: {Where results go}
- **Human Gate**: {Where humans review, if applicable}
- **Error Path**: {What happens on failure}

## 4. Functional Requirements

### FR-{NN}: {Feature Group Name}

- **FR-{NN}.1**: {Specific requirement with enough detail to implement}
- **FR-{NN}.2**: {Next requirement}
- ...

{Repeat for each feature group}

## 5. Non-Functional Requirements

### NFR-01: Reliability
- {Failure rate targets, retry strategy, circuit breakers}

### NFR-02: Cost Efficiency
- {API call budgets, caching strategy, bulk endpoint usage}

### NFR-03: Scalability
- {Tenant limits, data volume projections, archival policy}

### NFR-04: Security
- {Credential management, data isolation, access control}

### NFR-05: Observability
- {Error tracking, performance monitoring, alerting}

## 6. Multi-Tenancy Design (if applicable)

### Tenant Configuration
- {What's shared vs. per-tenant}
- {Master registry structure}
- {Per-tenant data storage design}

### Tenant Onboarding
- {Steps to add a new tenant}
- {What's automated vs. manual}

## 7. Integration Map

| Service | Purpose | API/Protocol | Auth Method | Rate Limits |
|---------|---------|-------------|-------------|-------------|
| {name}  | {role}  | {REST/WS/etc} | {key/OAuth/etc} | {limits} |

## 8. Approval Gates

| Gate | Trigger | Approval Method | Timeout Behavior |
|------|---------|----------------|-----------------|
| {#}  | {when}  | {Sheets/Slack/both} | {action on timeout} |

## 9. Error Handling Strategy

### Detection
- {How errors are detected at each stage}

### Retry Logic
- {Retry count, backoff strategy, per-workflow retry rules}

### Escalation
- {When retries are exhausted: Sentry severity, Slack notification, manual intervention}

### Recovery
- {Workflow 0 / retry handler design}

## 10. Monitoring & Observability

### Error Tracking
- {Sentry project, error grouping, alert rules}

### Analytics
- {PostHog events, UTM strategy, custom dashboards}

### Content Performance (if applicable)
- {Tiered monitoring cadence, optimization workflow}

## 11. Data Architecture

### Storage Design
- {Google Sheets structure, database schema, CMS schemas}

### Data Flow
- {How data moves through the system, transformation points}

### Archival Policy
- {When data is archived, retention periods}

## 12. MCP Servers & Skills Map

| Phase/Workflow | MCP Server | Purpose |
|---------------|------------|---------|
| {step}        | {server}   | {what it does here} |

| Phase/Workflow | Skill | Purpose |
|---------------|-------|---------|
| {step}        | {skill} | {what it does here} |

## 13. Open Questions

- [ ] {Anything still unresolved}
- [ ] {Decisions deferred to implementation}

## 14. Appendix

### A. API Reference Notes
{Key API details discovered during research}

### B. Schema Definitions
{Data schemas, field mappings, type definitions}

### C. Cost Estimates
{Per-API-call costs, monthly projections, optimization strategies}
```
