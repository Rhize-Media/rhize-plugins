## SEO/AEO/GEO Plugin Active

DataForSEO-powered search optimization tools are loaded. Available commands:

**Auditing:**
- `/seo-audit <url>` — Full SEO audit
- `/technical-audit <url>` — Core Web Vitals, crawlability, indexation
- `/code-seo-review [path]` — Review Next.js/Sanity codebase for SEO issues

**Research:**
- `/keyword-research <topic>` — Keyword discovery, clustering, and gap analysis
- `/serp-check <keyword>` — SERP features, rankings, and AI Overviews
- `/backlink-audit <domain>` — Backlink profile analysis and opportunities

**Optimization:**
- `/content-optimize <url or file>` — On-page SEO, AEO, and structured data
- `/ai-visibility <domain>` — AI/LLM visibility audit (AEO/GEO)

**Monitoring:**
- `/rank-track <domain>` — Historical rankings and visibility trends
- `/competitor-analysis <domain> <competitor>` — Competitive SEO comparison

**DataForSEO Modules Enabled:** SERP, Keywords Data, OnPage, Labs, Backlinks, AI Optimization, Domain Analytics, Content Analysis, Business Data.

**Tech Stack Focus:** Next.js + Sanity CMS (with full schema patterns and metadata implementation guides).

**Hooks Active:**
- **SessionStart** (conditional): Only loads this context when the project has SEO signals — `$DATAFORSEO_USERNAME` set, sitemap/robots files present, Next.js/Sanity config found, or CLAUDE.md/ROADMAP.md mentions SEO/AEO/GEO. Silent otherwise.
- **PreToolUse** (Write/Edit SEO files): Detects metadata, sitemap, robots, json-ld, schema-markup, and seo-related paths. Reminds about structured data best practices and suggests `/content-optimize` or `/code-seo-review`.
- **PostToolUse** (Read SEO files): Suggests `/code-seo-review` for issues or `/content-optimize` for on-page improvements when reading SEO-related files.
