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

<!-- SKILL-MAP:BEGIN -->
| Skill | Description | Topics |
| --- | --- | --- |
| `aeo-geo-optimization` | ALWAYS invoke this skill (via the Skill tool) for any AI visibility, AEO, or GEO request. | ai-visibility, seo, seo-audit |
| `backlink-intelligence` | ALWAYS invoke this skill (via the Skill tool) for any backlink analysis or link profile request. | backlink-analysis, seo, seo-audit |
| `content-seo` | ALWAYS invoke this skill (via the Skill tool) for any content SEO optimization or structured data request. | content-optimization, seo, seo-audit |
| `keyword-intelligence` | ALWAYS invoke this skill (via the Skill tool) for any keyword research or keyword analysis request. | content-optimization, keyword-research, seo |
| `nextjs-sanity-seo` | ALWAYS invoke this skill (via the Skill tool) for any Next.js + Sanity SEO implementation request. | cms-development, content-optimization, nextjs, sanity, seo, seo-audit |
| `seo-site-audit` | ALWAYS invoke this skill (via the Skill tool) for any SEO audit or site health check request. | observability, seo, seo-audit |
| `serp-intelligence` | ALWAYS invoke this skill (via the Skill tool) for any SERP analysis or rank tracking request. | rank-tracking, seo, seo-audit |
<!-- SKILL-MAP:END -->

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
| **PreToolUse** | `Write\|Edit` on SEO-related files | Detects files with SEO-related path segments (`metadata`, `sitemap`, `robots`, `json-ld`, `jsonld`, `structured-data`, `schema-markup`, `seo`) and reminds about structured data best practices. Suggests `/content-optimize` or `/code-seo-review` to validate changes. |
| **PostToolUse** | `Read` on SEO-related files | When reading SEO-related files (same patterns plus `head.tsx`, `head.jsx`, `layout.tsx`, `layout.jsx`), suggests `/code-seo-review` for issue detection or `/content-optimize` for on-page improvements. |

> **SessionStart banner removed (2026-08-09):** the conditional SEO-context banner moved to
> [`rhize-context-manager`'s `session-disclosure.js`](../rhize-context-manager/README.md#hooks) —
> Phase 3 of the skill-map plan (`docs/skill-map.md`). It fingerprints the repo against the
> compiled skill map's stack tags instead of this plugin's fixed signal list.

All hooks are scoped to SEO file patterns — non-SEO files pass through silently. Hooks fail silently on error (3s timeout) and never block operations.

The PreToolUse and PostToolUse hooks are implemented in `hooks/scripts/seo-edit-hint.py` and
`hooks/scripts/seo-read-hint.py`. They read the tool-call payload from stdin (as Claude Code
delivers it — `{"tool_name": ..., "tool_input": {...}}`) and emit advisory context via the
standard `hookSpecificOutput` contract; both are auto-wired through `hooks/hooks.json`, so no
setup step is required to use them.

## Setup Manifest

`setup/manifest.json` lists opt-in capabilities this plugin could offer beyond what's
auto-wired in `hooks/hooks.json` — read by the `/rhize-setup` wizard (in the `rhize-ops`
plugin) so a project can pick which ones to wire into its `.claude/settings.json`. It's
currently empty: every hook this plugin ships is already scoped tightly (SEO file patterns
only, 3s timeout, advisory-only) and auto-wired, so there's nothing here that needs to be
opt-in rather than on-by-default. It does declare a `dependencies` array (the DataForSEO
MCP server) that the wizard's dependency check reads.

**Fleet setup:** `/rhize-ops:rhize-setup` is what actually wires opt-in items and checks
`dependencies` for you — it requires the `rhize-ops` plugin. Without it, wire an item
manually per the snippet in [rhize-ops/README.md § Setup manifest
schema](../rhize-ops/README.md#setup-manifest-schema).

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
│   ├── seo-context.md                 # Available commands summary + hooks reference
│   └── scripts/
│       ├── seo-edit-hint.py           # PreToolUse Write|Edit implementation
│       └── seo-read-hint.py           # PostToolUse Read implementation
├── setup/
│   └── manifest.json                  # Opt-in capabilities for /rhize-setup (currently empty)
└── README.md
```
