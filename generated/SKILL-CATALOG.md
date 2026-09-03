# Skill Catalog

Generated cross-plugin index of every skill in this marketplace, grouped by plugin. Source:
`generated/skill-map.static.json`. Never hand-edit the managed section below — regenerate with
`python3 scripts/render_skill_map_docs.py` (see `docs/skill-map.md` for the full pipeline).

<!-- SKILL-MAP:BEGIN -->
## seo-aeo-geo

| Skill | Description | Topics |
| --- | --- | --- |
| `aeo-geo-optimization` | Checks and improves whether AI systems like ChatGPT and Google AI Overviews cite and reference your content. | ai-visibility, seo, seo-audit |
| `backlink-intelligence` | Analyzes a website's inbound links to find link-building opportunities and spot risky backlinks. | backlink-analysis, seo, seo-audit |
| `content-seo` | Optimizes a page's on-page SEO — meta tags, headings, structured data, and E-E-A-T signals — to help it rank better. | content-optimization, seo, seo-audit |
| `keyword-intelligence` | Researches, clusters, and scores keywords to find what to target for SEO or content strategy. | content-optimization, keyword-research, seo |
| `nextjs-sanity-seo` | Implements SEO fixes directly in a Next.js and Sanity CMS codebase — metadata, sitemaps, structured data. | cms-development, content-optimization, nextjs, sanity, seo, seo-audit |
| `seo-site-audit` | Crawls a website and reports SEO health issues — technical problems, page speed, and on-page fixes. | observability, seo, seo-audit |
| `serp-intelligence` | Tracks search rankings and analyzes search results pages to show where you rank and what's around you. | rank-tracking, seo, seo-audit |

## obsidian-second-brain

| Skill | Description | Topics |
| --- | --- | --- |
| `defuddle` | Pulls clean, readable text from a web page for saving into your Obsidian vault. | content-authoring, obsidian, web-clipping |
| `json-canvas` | Creates visual Obsidian canvas boards with connected notes, diagrams, and mind maps. | knowledge-management, obsidian, visualization |
| `knowledge-compiler` | Compile captured Obsidian sources into cited, invalidatable knowledge-page previews and apply an exact reviewed diff. | knowledge-management, obsidian, provenance, python, workflow-patterns |
| `obsidian-bases` | Creates and edits Obsidian Base files for database-like views, filters, and dashboards. | content-authoring, knowledge-management, obsidian |
| `obsidian-cli` | Automates Obsidian vault operations from the terminal using the official command-line tool. | automation, content-authoring, obsidian |
| `obsidian-markdown` | Writes and formats Obsidian-flavored Markdown — wikilinks, embeds, callouts, and frontmatter. | content-authoring, knowledge-management, obsidian |
| `qmd-search` | Sets up and troubleshoots local semantic search over your Obsidian vault using qmd. | knowledge-management, obsidian, search |
| `second-brain` | Applies knowledge-management methods like Zettelkasten and PARA to organize your vault. | knowledge-management, obsidian, workflow-patterns |
| `vault-alignment` | Checks your Obsidian vault's health and organization against best practices. | knowledge-management, observability, obsidian |
| `vault-templates` | Provides ready-made note templates for meetings, book reviews, project briefs, and more. | content-authoring, knowledge-management, obsidian |

## project-launcher

| Skill | Description | Topics |
| --- | --- | --- |
| `project-launcher` | Takes a project idea through research, requirements, a PRD, and a scaffolded project folder. | automation, obsidian, project-planning, workflow-patterns |
| `rhize-visual-plan` | Turns an implementation plan into a reviewable visual document with diagrams and file maps. | nextjs, obsidian, project-planning, visualization |

## rhize-devflow

| Skill | Description | Topics |
| --- | --- | --- |
| `chrome-devtools-mcp` | DevTools-protocol mechanics reference for the `chrome-devtools` MCP server, used by `/rhize-devflow:browser-qa` when that server is the act… | automation, nextjs, observability, testing |
| `completed-branch-promotion` | Promote a completed feature or task branch through Rhize's repository-governed protected-branch workflow. | testing, vercel, workflow-patterns |
| `data-mutation-consistency` | Enforce consistent data-mutation patterns across Next.js apps on Vercel with Supabase, Sanity, and Payload CMS — so cache tags, query keys,… | data-consistency, nextjs, sanity, sentry, vercel, workflow-patterns |
| `dev-flow-foundations` | Foundational workflow patterns for large-codebase development — CodeGraph-first structural discovery paired with semantic impact mapping, c… | project-planning, workflow-patterns |
| `error-lifecycle-management` | End-to-end production error lifecycle for Next.js/TypeScript on Vercel — triage, root-cause analysis, deployment correlation, and fix verif… | nextjs, observability, sentry, vercel, workflow-patterns |
| `sanity-development` | Rhize-opinionated best practices for Sanity Studio config, schema design, GROQ queries, TypeGen, Portable Text, visual editing, page builde… | cms-development, content-authoring, nextjs, sanity, sentry |
| `sentry-instrumentation` | Rhize conventions for instrumenting Next.js/TypeScript code with Sentry — exception capture (captureException), custom performance spans (s… | nextjs, observability, sentry, workflow-patterns |
| `simplify` | Safely simplify recent or explicitly scoped code changes by consolidating duplicated policy, removing accidental complexity, and eliminatin… | nextjs, testing, workflow-patterns |
| `test-evidence` | Classify changed regression tests as behavior, artifact, or structural contracts and produce or validate fail-closed, state-bound evidence… | evidence, review, testing |

## rhize-context-manager

| Skill | Description | Topics |
| --- | --- | --- |
| `context-compression` | This skill should be used when long-running agent sessions need context compression, structured summarization, compaction, token-per-task o… | context-compression, context-engineering |
| `context-degradation` | This skill should be used for diagnosing and mitigating context degradation: lost-in-middle failures, context poisoning, context clash, con… | context-degradation, context-engineering |
| `context-engineering` | Systematic context, session, and memory management for Claude Code development sessions: start/resume/close a working session, preserve and… | context-engineering, project-planning, workflow-patterns |
| `context-fundamentals` | This skill should be used to explain or reason about the foundational concepts of context engineering: what context is, the anatomy of a co… | context-engineering, context-optimization |
| `context-optimization` | This skill should be used for improving context efficiency: context budgeting, observation masking, prefix or KV-cache strategy, partitioni… | context-engineering, context-optimization |
| `context-pack` | Build or verify a private, deterministic source-bound code context preview for a specific implementation, diagnosis, impact-analysis, or re… | context-engineering, search |
| `context-stack` | Routing and coexistence brain for the Rhize context stack. | context-engineering, obsidian, workflow-patterns |
| `filesystem-context` | This skill should be used when agent work needs file-backed context: durable scratchpads, tool-output offloading, just-in-time discovery, c… | context-engineering, memory-systems |
| `graph-memory` | Govern Graphify graph.json artifacts for a Rhize Neo4j projection. | knowledge-graph, memory-systems, neo4j, security |
| `graphify` | Use for any question about a codebase, its architecture, file relationships, or project content — especially when graphify-out/ exists, whe… | knowledge-graph, memory-systems, obsidian, search |
| `graphiti-memory` | Historical design reference for Graphiti concepts. | knowledge-graph, memory-systems |
| `learning-curation` | This skill should be used when deciding whether a session learning, correction, or rule deserves persistent storage — and where to put it s… | context-engineering, learning-curation |
| `memory-context` | Assemble, verify, or explicitly purge a private bounded preview across authorized Rhize memory sources while preserving source authority, c… | context-engineering, memory-systems |
| `memory-systems` | This skill should be used for persistent semantic memory in agent systems: cross-session knowledge retention, entity tracking, temporal val… | knowledge-graph, memory-systems |
| `refinement-pipeline` | Operate and reason about the gated skill-refinement pipeline: headroom learn + claude-mem + skill-monitor signals flow into a human-triaged… | learning-curation, workflow-patterns |
| `tool-design` | This skill should be used for the tool-interface layer of an agent system specifically: writing tool descriptions agents can route on, desi… | context-engineering, tool-design |

## rhize-ops

| Skill | Description | Topics |
| --- | --- | --- |
| `delegate-to-teammate` | Delegate tasks to a configured teammate by gathering session context, formatting clear instructions, creating a Jira issue, publishing the… | automation, obsidian, workflow-patterns |
| `parallel-agent-optimization` | Required whenever parallel or multi-agent work is mentioned, discussed, proposed, planned, reviewed, benchmarked, optimized, or employed—in… | automation, observability, testing, workflow-patterns |
| `skill-dashboard` | Render the live skill-monitor audit dashboard. | observability, visualization |

## rhize-tasks

| Skill | Description | Topics |
| --- | --- | --- |
| `manage-task-preferences` | Review and update Rhize Tasks planning preferences through the authenticated local dashboard. | project-planning, workflow-patterns |
| `plan-my-day` | Build, inspect, and approve a today-first Rhize Tasks plan from the local planning authority. | automation, project-planning |
| `reconcile-rhize-tasks` | Compare local Rhize task state with approved connector state and resolve drift through prompted reconciliation. | data-consistency, workflow-patterns |
| `review-task-opportunities` | Review urgent unassigned Jira work suggested for the configured user by Rhize Tasks competency rules. | project-planning, search |
| `rhize-tasks-doctor` | Diagnose Rhize Tasks installation, local service, source freshness, and scheduling health without mutating connectors. | automation, observability |
| `rhize-tasks-setup` | Set up or resume the seven-stage local Rhize Tasks wizard, including connector discovery, scope approval, planning preferences, routines, a… | automation, project-planning, workflow-patterns |

## rhize-cowork

| Skill | Description | Topics |
| --- | --- | --- |
| `project-kickoff` | Scaffold the four standard Cowork client-context files — CLAUDE.md (operating manual), BUSINESS.md (the business/offer/market), PERSONALITY… | content-authoring, knowledge-management, project-planning |

## procedural-memory

| Skill | Description | Topics |
| --- | --- | --- |
| `functionize` | Mine repeated CLI usage into redacted Functionize candidates, compile inert proposal bundles, or record a digest-bound human review through… | automation, functionize |
| `procedural-memory` | Execute a proven artifact from the procedural-memory registry instead of recomposing a task. | automation, workflow-patterns |
<!-- SKILL-MAP:END -->
