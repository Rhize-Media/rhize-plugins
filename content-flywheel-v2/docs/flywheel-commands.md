# Content Flywheel — Command Reference

Slash commands for managing the content pipeline from Claude Code sessions. All commands persist data to Neo4j and present results inline.

## Prerequisites

- **Dev server** running (`npm run dev`) for API-based commands, OR
- **MCP servers** connected (Neo4j + DataForSEO) for direct execution
- **SEO Utils desktop app** running for `/flywheel-gsc`, `/flywheel-indexing`, `/flywheel-gap`, `/flywheel-autocomplete`

## Quick Reference

| Command | Purpose | Requires |
|---------|---------|----------|
| `/flywheel-status` | Pipeline overview or content detail | Neo4j |
| `/flywheel-research` | Keyword research + clustering | DataForSEO |
| `/flywheel-discover` | Site audit for content opportunities | DataForSEO |
| `/flywheel-optimize` | SEO scoring for a content piece | DataForSEO |
| `/flywheel-monitor` | SERP, backlink, or AI visibility tracking | DataForSEO |
| `/flywheel-publish` | Publish content to Sanity CMS | Sanity |
| `/flywheel-distribute` | Schedule social posts via GoHighLevel | GHL |
| `/flywheel-gsc` | Query Google Search Console data | SEO Utils |
| `/flywheel-indexing` | Check/submit URLs to Google and Bing | SEO Utils |
| `/flywheel-gap` | Content or backlink gap vs competitors | SEO Utils |
| `/flywheel-autocomplete` | Discover autocomplete keywords | SEO Utils |

---

## Pipeline Commands

### `/flywheel-status [content-id | "summary"]`

Show pipeline status. Without arguments, shows the full pipeline funnel (count per stage), recent workflow runs, and key metrics. With a content ID, shows detailed status for that piece.

**Examples:**
```
/flywheel-status
/flywheel-status summary
/flywheel-status abc-123-def
```

### `/flywheel-publish <content-id> [create-draft | publish]`

Push content to Sanity CMS. Creates a draft first, then publishes. Updates the Neo4j pipeline stage automatically.

**Examples:**
```
/flywheel-publish abc-123 create-draft
/flywheel-publish abc-123 publish
```

### `/flywheel-distribute <content-id> <platform> [scheduled-time]`

Schedule a social media post via GoHighLevel. Generates platform-appropriate copy from the content piece. Supports Facebook, Instagram, LinkedIn, Twitter.

**Examples:**
```
/flywheel-distribute abc-123 linkedin
/flywheel-distribute abc-123 twitter 2026-04-15T10:00:00Z
```

---

## Research Commands (DataForSEO)

These commands call the DataForSEO API (works both locally and on Vercel).

### `/flywheel-research <seeds> [domain]`

Keyword research from seed terms. Expands via DataForSEO suggestions, ideas, and related keywords. Classifies intent, clusters semantically via Gemini embeddings, and stores everything in Neo4j. Optionally runs competitor gap analysis.

**Examples:**
```
/flywheel-research "content marketing, content flywheel"
/flywheel-research "AI search optimization" rhize.media
```

**Output:** Keyword opportunity table, cluster map, gap analysis, quick wins.

### `/flywheel-discover <domain> [max-pages]`

Run a site audit to find SEO issues and content opportunities. Crawls the site via DataForSEO On-Page API and scores pages for technical issues.

**Examples:**
```
/flywheel-discover rhize.media
/flywheel-discover rhize.media 200
```

**Output:** Issue summary by severity, affected page counts, prioritized action plan.

### `/flywheel-optimize <content-id> <url> [primary-keyword]`

Run a full SEO analysis on a published content piece. Scores title, meta, headings, E-E-A-T, internal links, and structured data. Stores the score in Neo4j.

**Examples:**
```
/flywheel-optimize abc-123 https://rhize.media/blog/ai-search
/flywheel-optimize abc-123 https://rhize.media/blog/ai-search "AI search optimization"
```

**Output:** Overall score (A-F), per-dimension breakdown, prioritized recommendations.

### `/flywheel-monitor <serp|backlinks|ai> <content-id or domain>`

Run monitoring workflows for ongoing content tracking.

**Subcommands:**
- `serp` — Check current SERP positions and features for a content piece
- `backlinks` — Analyze backlink profile (referring domains, anchors, new/lost)
- `ai` — Monitor AI engine brand mentions (ChatGPT, Perplexity, Gemini)

**Examples:**
```
/flywheel-monitor serp abc-123
/flywheel-monitor backlinks rhize.media
/flywheel-monitor ai abc-123
```

---

## SEO Utils Commands (Local Only)

These commands require the **SEO Utils desktop app** running at `localhost:19515`. They provide capabilities that DataForSEO doesn't offer: real GSC data, indexing API access, autocomplete scraping, and competitive gap analysis.

> **Note:** These commands only work in local Claude Code sessions. They cannot run on Vercel. For future VPS-hosted access, see M15 in the roadmap.

### `/flywheel-gsc <report-type> [date-range] [page-filter]`

Query your actual Google Search Console data for rhize.media. Shows real clicks, impressions, CTR, and positions — not estimates.

**Report types:**
- `queries` or `top-queries` — Top queries by clicks
- `pages` — Top pages by impressions
- `declining` — Queries losing position (content decay detection)
- `branded` — Branded vs non-branded traffic split

**Date ranges:** `7d`, `30d`, `90d` (default: `30d`)

**Examples:**
```
/flywheel-gsc top-queries
/flywheel-gsc declining 7d
/flywheel-gsc pages 90d
/flywheel-gsc branded
```

**Output:** Query/page tables with metrics, content decay alerts, CTR optimization opportunities. Cross-references with Neo4j content pieces.

### `/flywheel-indexing <action> <url or content-id>`

Check whether content is indexed by Google, and submit URLs for indexing after publishing.

**Actions:**
- `check` — Check if URL is in Google's index
- `submit-google` — Submit to Google Indexing API
- `submit-bing` — Submit to Bing via IndexNow
- `submit-all` — Submit to both Google and Bing

**Examples:**
```
/flywheel-indexing check https://rhize.media/blog/ai-search
/flywheel-indexing submit-all abc-123
/flywheel-indexing check abc-123
```

**Output:** Indexing status, submission confirmation. Updates Neo4j with `googleIndexed` and `lastIndexCheck` properties.

### `/flywheel-gap <gap-type> <our-domain> <competitor1> [competitor2] [competitor3]`

Run competitive gap analysis to find keywords or backlink sources your competitors have but you don't.

**Gap types:**
- `content-gap` — Keywords competitors rank for that we don't
- `backlink-gap` — Domains linking to competitors but not us

**Examples:**
```
/flywheel-gap content-gap rhize.media searchengineland.com moz.com
/flywheel-gap backlink-gap rhize.media ahrefs.com semrush.com
```

**Output:** Gap keyword/domain tables with volume, difficulty, and authority scores. Stores findings in Neo4j as Keyword and BacklinkSource nodes linked to Competitor nodes.

### `/flywheel-autocomplete <seed keyword>`

Discover autocomplete suggestions and question keywords from Google. Useful for finding FAQ content ideas, long-tail variations, and "People Also Ask" style queries.

**Examples:**
```
/flywheel-autocomplete "AI search optimization"
/flywheel-autocomplete "content marketing strategy"
```

**Output:** Keywords grouped by type (questions, comparisons, long-tail, commercial), with volume and difficulty where available. High-value discoveries stored in Neo4j.

---

## Typical Workflows

### New content from scratch
```
/flywheel-research "topic keywords" rhize.media     # Discover and cluster keywords
/flywheel-autocomplete "topic"                       # Find question/long-tail variants
/flywheel-gap content-gap rhize.media competitor.com # Find gaps to fill
# → Use dashboard: Generate Outline → Generate Draft → Check Brand Voice
/flywheel-optimize <id> <url>                        # Score the published piece
/flywheel-indexing submit-all <id>                   # Push to Google + Bing
```

### Monitor existing content
```
/flywheel-gsc declining 7d                           # Find pages losing traffic
/flywheel-monitor serp <content-id>                  # Check current rankings
/flywheel-monitor backlinks rhize.media              # Review backlink profile
/flywheel-monitor ai <content-id>                    # Check AI engine visibility
```

### Competitive intelligence
```
/flywheel-gap content-gap rhize.media competitor.com # Keyword opportunities
/flywheel-gap backlink-gap rhize.media competitor.com # Link building targets
/flywheel-discover competitor.com                    # Audit their site
```

### Post-publish checklist
```
/flywheel-publish <id> publish                       # Push to Sanity CMS
/flywheel-indexing submit-all <id>                   # Request indexing
/flywheel-distribute <id> linkedin                   # Schedule social posts
/flywheel-monitor serp <id>                          # Baseline ranking check
```
