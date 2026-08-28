# Skill Catalog

Generated cross-plugin index of every skill in this marketplace, grouped by plugin. Source:
`generated/skill-map.static.json`. Never hand-edit the managed section below — regenerate with
`python3 scripts/render_skill_map_docs.py` (see `docs/skill-map.md` for the full pipeline).

<!-- SKILL-MAP:BEGIN -->
## seo-aeo-geo

| Skill | Description | Topics |
| --- | --- | --- |
| `aeo-geo-optimization` | ALWAYS invoke this skill (via the Skill tool) for any AI visibility, AEO, or GEO request. | ai-visibility, seo, seo-audit |
| `backlink-intelligence` | ALWAYS invoke this skill (via the Skill tool) for any backlink analysis or link profile request. | backlink-analysis, seo, seo-audit |
| `content-seo` | ALWAYS invoke this skill (via the Skill tool) for any content SEO optimization or structured data request. | content-optimization, seo, seo-audit |
| `keyword-intelligence` | ALWAYS invoke this skill (via the Skill tool) for any keyword research or keyword analysis request. | content-optimization, keyword-research, seo |
| `nextjs-sanity-seo` | ALWAYS invoke this skill (via the Skill tool) for any Next.js + Sanity SEO implementation request. | cms-development, content-optimization, nextjs, sanity, seo, seo-audit |
| `seo-site-audit` | ALWAYS invoke this skill (via the Skill tool) for any SEO audit or site health check request. | observability, seo, seo-audit |
| `serp-intelligence` | ALWAYS invoke this skill (via the Skill tool) for any SERP analysis or rank tracking request. | rank-tracking, seo, seo-audit |

## obsidian-second-brain

| Skill | Description | Topics |
| --- | --- | --- |
| `defuddle` | ALWAYS invoke this skill (via the Skill tool) for any web clipping or article extraction request. | content-authoring, obsidian, web-clipping |
| `json-canvas` | ALWAYS invoke this skill (via the Skill tool) for any Obsidian canvas or .canvas file request. | knowledge-management, obsidian, visualization |
| `obsidian-bases` | ALWAYS invoke this skill (via the Skill tool) for any Obsidian Bases or .base file request. | content-authoring, knowledge-management, obsidian |
| `obsidian-cli` | ALWAYS invoke this skill (via the Skill tool) for any Obsidian CLI or terminal automation request. | automation, content-authoring, obsidian |
| `obsidian-markdown` | ALWAYS invoke this skill (via the Skill tool) for any Obsidian markdown syntax or formatting request. | content-authoring, knowledge-management, obsidian |
| `qmd-search` | ALWAYS invoke this skill (via the Skill tool) for any qmd semantic search, vector search, or vault indexing request. | knowledge-management, obsidian, search |
| `second-brain` | ALWAYS invoke this skill (via the Skill tool) for any PKM methodology or vault organization request. | knowledge-management, obsidian, workflow-patterns |
| `vault-alignment` | ALWAYS invoke this skill (via the Skill tool) for any vault health, audit, or organization improvement request. | knowledge-management, observability, obsidian |
| `vault-templates` | ALWAYS invoke this skill (via the Skill tool) for any Obsidian note template or archetype request. | content-authoring, knowledge-management, obsidian |

## project-launcher

| Skill | Description | Topics |
| --- | --- | --- |
| `project-launcher` | ALWAYS invoke this skill (via the Skill tool) for any request to start a new project, create a PRD, plan a new automation, scaffold a proje… | automation, obsidian, project-planning, workflow-patterns |
| `rhize-visual-plan` | ALWAYS invoke this skill (via the Skill tool) for any request to turn an implementation plan into a rich, reviewable `.mdx` visual plan — a… | nextjs, obsidian, project-planning, visualization |

## rhize-devflow

| Skill | Description | Topics |
| --- | --- | --- |
| `chrome-devtools-mcp` | DevTools-protocol mechanics reference for the `chrome-devtools` MCP server, used by `/rhize-devflow:browser-qa` when that server is the act… | automation, nextjs, observability, testing |
| `data-mutation-consistency` | Enforce consistent data-mutation patterns across Next.js apps on Vercel with Supabase, Sanity, and Payload CMS — so cache tags, query keys,… | data-consistency, nextjs, sanity, sentry, vercel, workflow-patterns |
| `dev-flow-foundations` | Foundational workflow patterns for large-codebase development — CodeGraph-first structural discovery paired with semantic impact mapping, c… | project-planning, workflow-patterns |
| `error-lifecycle-management` | End-to-end production error lifecycle for Next.js/TypeScript on Vercel — triage, root-cause analysis, deployment correlation, and fix verif… | nextjs, observability, sentry, vercel, workflow-patterns |
| `sanity-development` | Rhize-opinionated best practices for Sanity Studio config, schema design, GROQ queries, TypeGen, Portable Text, visual editing, page builde… | cms-development, content-authoring, nextjs, sanity, sentry |
| `sentry-instrumentation` | Rhize conventions for instrumenting Next.js/TypeScript code with Sentry — exception capture (captureException), custom performance spans (s… | nextjs, observability, sentry, workflow-patterns |
| `simplify` | Safely simplify recent or explicitly scoped code changes by consolidating duplicated policy, removing accidental complexity, and eliminatin… | nextjs, testing, workflow-patterns |

## rhize-context-manager

| Skill | Description | Topics |
| --- | --- | --- |
| `context-compression` | This skill should be used when long-running agent sessions need context compression, structured summarization, compaction, token-per-task o… | context-compression, context-engineering |
| `context-degradation` | This skill should be used for diagnosing and mitigating context degradation: lost-in-middle failures, context poisoning, context clash, con… | context-degradation, context-engineering |
| `context-engineering` | Systematic context, session, and memory management for Claude Code development sessions: start/resume/close a working session, preserve and… | context-engineering, project-planning, workflow-patterns |
| `context-fundamentals` | This skill should be used to explain or reason about the foundational concepts of context engineering: what context is, the anatomy of a co… | context-engineering, context-optimization |
| `context-optimization` | This skill should be used for improving context efficiency: context budgeting, observation masking, prefix or KV-cache strategy, partitioni… | context-engineering, context-optimization |
| `context-stack` | Routing and coexistence brain for the Rhize context stack. | context-engineering, obsidian, workflow-patterns |
| `filesystem-context` | This skill should be used when agent work needs file-backed context: durable scratchpads, tool-output offloading, just-in-time discovery, c… | context-engineering, memory-systems |
| `graphify` | Use for any question about a codebase, its architecture, file relationships, or project content — especially when graphify-out/ exists, whe… | knowledge-graph, memory-systems, obsidian, search |
| `graphiti-memory` | Adoption and usage guide for Graphiti — Zep's temporal knowledge-graph memory layer for agents. | knowledge-graph, memory-systems |
| `learning-curation` | This skill should be used when deciding whether a session learning, correction, or rule deserves persistent storage — and where to put it s… | context-engineering, learning-curation |
| `memory-systems` | This skill should be used for persistent semantic memory in agent systems: cross-session knowledge retention, entity tracking, temporal val… | knowledge-graph, memory-systems |
| `refinement-pipeline` | Operate and reason about the gated skill-refinement pipeline: headroom learn + claude-mem + skill-monitor signals flow into a human-triaged… | learning-curation, workflow-patterns |
| `tool-design` | This skill should be used for the tool-interface layer of an agent system specifically: writing tool descriptions agents can route on, desi… | context-engineering, tool-design |

## rhize-ops

| Skill | Description | Topics |
| --- | --- | --- |
| `delegate-to-teammate` | Delegate tasks to a configured teammate by gathering session context, formatting clear instructions, creating a Jira issue, and notifying v… | automation, obsidian, workflow-patterns |
| `parallel-agent-optimization` | Choose whether a task should use parallel agents, run one bounded execution strategy, and record privacy-safe evidence. | automation, observability, testing, workflow-patterns |
| `skill-dashboard` | Render the live skill-monitor audit dashboard. | observability, visualization |

## rhize-tasks

| Skill | Description | Topics |
| --- | --- | --- |
| `manage-task-preferences` | Review and update Rhize Tasks planning preferences through the authenticated local dashboard. | project-planning, workflow-patterns |
| `plan-my-day` | Build, inspect, and approve a today-first Rhize Tasks plan from the local planning authority. | automation, project-planning |
| `reconcile-rhize-tasks` | Compare local Rhize task state with approved connector state and resolve drift through prompted reconciliation. | data-consistency, workflow-patterns |
| `review-task-opportunities` | Review urgent unassigned Jira work suggested for Tom by Rhize Tasks competency rules. | project-planning, search |
| `rhize-tasks-doctor` | Diagnose Rhize Tasks installation, local service, source freshness, and scheduling health without mutating connectors. | automation, observability |
| `rhize-tasks-setup` | Set up or resume the seven-stage local Rhize Tasks wizard, including connector discovery, scope approval, planning preferences, routines, a… | automation, project-planning, workflow-patterns |

## rhize-cowork

| Skill | Description | Topics |
| --- | --- | --- |
| `project-kickoff` | Scaffold the four standard Cowork client-context files — CLAUDE.md (operating manual), BUSINESS.md (the business/offer/market), PERSONALITY… | content-authoring, knowledge-management, project-planning |

## procedural-memory

| Skill | Description | Topics |
| --- | --- | --- |
| `procedural-memory` | Execute a proven, already-working artifact from the procedural-memory registry (Rhize-Media/procedural-memory) instead of recomposing a tas… | automation, workflow-patterns |
<!-- SKILL-MAP:END -->
