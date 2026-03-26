# SEO/AEO/GEO Plugin

Comprehensive search optimization plugin powered by DataForSEO API. Covers traditional SEO, Answer Engine Optimization (AEO), and Generative Engine Optimization (GEO) with built-in support for Next.js + Sanity CMS codebases.

## Setup

### Required Environment Variables

```bash
export DATAFORSEO_USERNAME=your_username
export DATAFORSEO_PASSWORD=your_password
```

Get credentials at [dataforseo.com](https://dataforseo.com).

### DataForSEO Modules Enabled

SERP, Keywords Data, OnPage, DataForSEO Labs, Backlinks, AI Optimization, Domain Analytics, Content Analysis, Business Data.

## Commands

| Command | Description |
|---------|-------------|
| `/seo-audit <url>` | Full SEO audit (on-page, technical, structured data) |
| `/keyword-research <topic>` | Keyword discovery, clustering, gap analysis |
| `/serp-check <keyword>` | SERP features, rankings, AI Overviews |
| `/backlink-audit <domain>` | Backlink profile analysis and opportunities |
| `/content-optimize <url or file>` | On-page SEO + AEO + structured data optimization |
| `/competitor-analysis <domain> <competitor>` | Competitive SEO comparison |
| `/ai-visibility <domain>` | AI/LLM visibility audit (AEO/GEO) |
| `/technical-audit <url>` | Core Web Vitals, crawlability, indexation |
| `/rank-track <domain>` | Historical rankings and visibility trends |
| `/code-seo-review [path]` | Review Next.js/Sanity codebase for SEO issues |

## Skills

| Skill | Triggers On |
|-------|-------------|
| **seo-site-audit** | SEO audits, site health checks, crawl analysis |
| **keyword-intelligence** | Keyword research, gap analysis, clustering |
| **content-seo** | On-page optimization, meta tags, structured data, E-E-A-T |
| **aeo-geo-optimization** | AI Overviews, LLM visibility, generative search |
| **backlink-intelligence** | Backlink analysis, link gaps, anchor text audit |
| **serp-intelligence** | SERP features, rank tracking, visibility trends |
| **nextjs-sanity-seo** | Next.js metadata, Sanity schemas, codebase SEO review |

## What's Included

### Traditional SEO
- Full site crawling and technical audits via DataForSEO OnPage API
- On-page optimization (titles, meta descriptions, headings, content)
- Core Web Vitals analysis (LCP, INP, CLS)
- Internal linking and site architecture audit
- Structured data validation and generation
- XML sitemap and robots.txt analysis

### Keyword Intelligence
- Keyword research with volume, difficulty, CPC, and trends
- Intent classification (informational, commercial, transactional)
- Competitor keyword gap analysis
- Keyword clustering and topic mapping
- Question-based keyword discovery (People Also Ask)
- Decision-stage and commercial keyword templates

### Backlink Analysis
- Backlink profile with authority scoring (DataForSEO 0-1000 scale)
- Anchor text distribution analysis
- Competitor link gap identification
- Broken link detection and reclamation
- Toxic link detection
- Unlinked brand mention discovery

### AEO/GEO (AI Visibility)
- Google AI Overview citation tracking
- LLM brand mention monitoring (ChatGPT, Claude, Perplexity, Gemini)
- AI crawler management (robots.txt configuration)
- Content optimization for AI extraction
- GEO monitoring and measurement framework
- AI-ready structured data patterns

### SERP Intelligence
- Real-time SERP analysis with feature detection
- Historical rank tracking and visibility trends
- SERP feature mapping (snippets, PAA, AI Overviews)
- Competitive SERP comparison
- AI Overview source tracking

### Next.js + Sanity Implementation
- Sanity schema patterns (SEO fields, authors, FAQs, redirects)
- Next.js App Router metadata implementation
- Dynamic sitemap and robots.ts generation
- JSON-LD structured data components
- Image optimization with next/image + Sanity
- Codebase SEO audit checklist
- Direct code fixes for SEO issues

## DataForSEO Prompt Templates

The plugin includes ready-to-use DataForSEO prompt templates for:
- Technical SEO audits (crawlability, meta tags, speed, internal links)
- Keyword research (decision-stage, clustering, questions, commercial, informational)
- Backlink analysis (top links, gaps, broken links, toxic detection)
- SERP analytics (visibility trends, competitive comparison)

## Hooks

| Hook | Matcher | Behavior |
|------|---------|----------|
| **SessionStart** | All sessions | Loads command menu, DataForSEO modules list, and tech stack focus into context |
| **PreToolUse** | `Write\|Edit` on SEO-related files | Detects files with SEO-related path segments (`metadata`, `sitemap`, `robots`, `json-ld`, `jsonld`, `structured-data`, `schema-markup`, `seo`) and reminds about structured data best practices. Suggests `/content-optimize` or `/code-seo-review` to validate changes. |
| **PostToolUse** | `Read` on SEO-related files | When reading SEO-related files (same patterns plus `head.tsx`, `head.jsx`, `layout.tsx`, `layout.jsx`), suggests `/code-seo-review` for issue detection or `/content-optimize` for on-page improvements. |

All hooks are scoped to SEO file patterns — non-SEO files pass through silently. Hooks fail silently on error (3s timeout) and never block operations.

## Architecture

```
seo-aeo-geo/
├── .claude-plugin/plugin.json
├── .mcp.json                          # DataForSEO MCP server config
├── commands/                          # 10 slash commands
├── skills/
│   ├── seo-site-audit/               # + 3 reference files
│   ├── keyword-intelligence/          # + 2 reference files
│   ├── content-seo/                   # + 2 reference files
│   ├── aeo-geo-optimization/          # + 3 reference files
│   ├── backlink-intelligence/         # + 1 reference file
│   ├── serp-intelligence/             # + 1 reference file
│   └── nextjs-sanity-seo/            # Implementation patterns
├── hooks/
│   ├── hooks.json                     # SessionStart + PreToolUse + PostToolUse
│   └── seo-context.md                 # Available commands summary + hooks reference
└── README.md
```
