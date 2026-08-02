# SEO/AEO/GEO Plugin — User Guide

This guide explains what the SEO/AEO/GEO plugin does, how each piece works, and how to get the most out of it when auditing and optimizing a site for traditional search, AI answer engines, and generative search.

## What This Plugin Does

The plugin turns Claude into a full-stack search optimization practitioner — someone who can crawl your site, research keywords, analyze backlinks, track rankings, optimize content, and check whether AI systems like ChatGPT and Google AI Overviews are citing you. All of it is powered by live data from DataForSEO rather than guesswork or stale training knowledge.

It's built for anyone responsible for a site's visibility: SEO practitioners running audits and reporting on health, content teams optimizing pages before publish, marketers sizing up competitors, and developers who need to fix SEO issues directly in a Next.js + Sanity codebase.

The plugin contains two types of components:

**Skills** are reference knowledge that Claude loads automatically when your request matches certain trigger phrases. You don't invoke them directly — Claude reads them behind the scenes to produce better output. Think of skills as "expertise modules," each backed by a specific DataForSEO workflow.

**Commands** are actions you invoke explicitly with a slash prefix (e.g., `/seo-audit`). They run a full workflow end-to-end and hand you a finished report (or, for code-facing commands, finished edits).

## Quick Mental Model

Six of the seven skills — and all ten commands — are **DataForSEO-backed data skills**. They pull live numbers (search volume, rankings, backlink authority, AI citation rates) and turn them into analysis and recommendations. You don't need to touch the DataForSEO API yourself; just describe what you want to know or fix, and Claude calls the right endpoints.

The seventh skill, **nextjs-sanity-seo**, is different: it's a **code implementation** skill. It doesn't call DataForSEO at all — it knows the actual Next.js App Router and Sanity CMS patterns (schema fields, `generateMetadata`, sitemaps, JSON-LD components) needed to *fix* the issues the data skills find. In practice, the data skills tell you what's wrong; this skill (and its `/code-seo-review` command) tells Claude how to write the fix.

A useful way to think about the seven skills:

| Skill | Answers |
|---|---|
| `seo-site-audit` | "Is this site healthy?" |
| `keyword-intelligence` | "What should we target?" |
| `content-seo` | "How do we optimize this specific page?" |
| `aeo-geo-optimization` | "Are AI systems citing us?" |
| `backlink-intelligence` | "Who links to us, and who should?" |
| `serp-intelligence` | "Where do we rank, and what does the SERP look like?" |
| `nextjs-sanity-seo` | "How do we fix this in the actual codebase?" |

## Prerequisites

The data skills and every command need DataForSEO credentials set as environment variables (`DATAFORSEO_USERNAME` and `DATAFORSEO_PASSWORD`). Get an account at [dataforseo.com](https://dataforseo.com) — see the README for exact setup steps. Without credentials, Claude can still reason about SEO in general terms, but it can't pull live rankings, search volume, backlink, or AI-citation data.

The `nextjs-sanity-seo` skill and `/code-seo-review` command don't need DataForSEO — they work directly against your codebase.

## Skills Reference

### seo-site-audit

**When it activates:** You ask for a site health check, an SEO audit, a crawl for problems, a Core Web Vitals check, or anything about "what's wrong with my SEO."

**What it knows:** How to run a DataForSEO OnPage crawl (with JS rendering enabled for SPA/Next.js sites) and turn the results into a prioritized report — on-page elements (titles, meta descriptions, headings, images), technical health (Core Web Vitals, crawlability, indexation), and structured data validation, all scored and ranked Critical → High → Medium → Low.

**How to use it effectively:**
- Ask "audit example.com for SEO issues" — it crawls the whole domain and produces an executive summary with a 0-100 health score.
- Ask "why isn't this page ranking?" with a URL — it runs a page-level audit instead of crawling the whole site.
- Ask "just check the technical stuff" to focus on Core Web Vitals, crawlability, and indexation without the full content review (this is also what `/technical-audit` does).
- Mention competitors and it will benchmark your content depth and structure against theirs.

### keyword-intelligence

**When it activates:** You ask for keyword research, gap analysis, clustering, "what should I write about," or intent classification.

**What it knows:** How to expand a handful of seed keywords into 50-200 candidates using DataForSEO's Keywords Data, Labs, and SERP APIs — question keywords, comparison keywords, modifier keywords, long-tail variations, and commercial-intent keywords — then classify each by search intent and cluster them into content-pillar groups with a priority score (volume × low difficulty × intent alignment).

**How to use it effectively:**
- Give it a topic ("content marketing tools") and it returns a full opportunity table sorted by priority, not just a raw list.
- Give it your domain alongside the topic and it runs a competitor gap analysis — keywords competitors rank for that you don't, plus page-2 "quick win" keywords you're already close to ranking for.
- Ask specifically for "question keywords" or "People Also Ask keywords" if you're building FAQ content.
- Don't dismiss zero-volume long-tail keywords — the skill treats high-intent, low-volume queries as worth evaluating on business fit, not just traffic.

### content-seo

**When it activates:** You ask to optimize a specific page, fix meta tags, write SEO titles, add structured data, or improve E-E-A-T signals.

**What it knows:** Title tag and meta description formulas (with exact character targets), heading hierarchy rules, E-E-A-T implementation (experience, expertise, authoritativeness, trustworthiness), internal linking density guidelines, JSON-LD templates for every common schema type, and featured-snippet formatting patterns.

**How to use it effectively:**
- Give it a URL or a file and a target keyword — it audits current state first, then optimizes title, meta description, headings, and internal links against that keyword.
- Ask for "structured data for this FAQ page" — it generates ready-to-use FAQPage JSON-LD.
- Ask "is this content good enough for a YMYL topic?" (health, finance, legal) — it checks for the stricter E-E-A-T signals those topics require.
- Ask "how do I win the featured snippet for this question" — it applies the paragraph/list/table snippet formatting rules.

### aeo-geo-optimization

**When it activates:** You ask about AI Overview visibility, getting cited by ChatGPT/Perplexity/Claude/Gemini, AI crawler management (GPTBot, ClaudeBot, PerplexityBot), or "how do I show up in AI answers."

**What it knows:** The difference between AEO (getting selected as the answer in Google AI Overviews and featured snippets) and GEO (visibility across generative engines like ChatGPT, Perplexity, and Google AI Mode) — plus how to structure content to be extraction-friendly (answer-first, question-formatted headings, definition paragraphs), which robots.txt directives control which AI crawlers, and how to monitor citation rates over time.

**How to use it effectively:**
- Ask "is my brand mentioned by ChatGPT or Perplexity" — it checks DataForSEO's AI Optimization module for LLM brand mentions and accuracy.
- Ask "are we cited in AI Overviews for our target keywords" — it pulls AI Overview source lists and tells you who's cited instead.
- Ask "should I block GPTBot" — it walks through the tradeoff (blocking prevents training use but reduces citation chances) rather than giving a one-size-fits-all answer.
- Ask it to rewrite a section "for AI extraction" — it restructures the content answer-first with a 40-60 word definition paragraph up top.

### backlink-intelligence

**When it activates:** You ask about backlink audits, referring domains, anchor text distribution, toxic links, or link-building opportunities.

**What it knows:** How to read a DataForSEO Backlinks API profile — total backlinks, referring domain authority (on DataForSEO's 0-1000 scale), dofollow/nofollow ratio, anchor text health bands, and how to run competitor link-gap analysis (domains that link to a competitor but not to you) and broken-link reclamation (your own 404 pages that still hold backlinks).

**How to use it effectively:**
- Ask "audit our backlink profile" for a standalone health check with a quality-distribution breakdown and red flags (spam score, over-optimized anchors).
- Give it a competitor domain alongside yours to get a prioritized outreach list, sorted by referring-domain authority.
- Ask "find broken link opportunities" — it cross-references your 404 pages against inbound backlinks to flag content worth restoring or redirecting.
- Ask about anchor text health specifically if you're worried about manipulative-pattern penalties — it flags any single keyword anchor over 10% of the profile.

### serp-intelligence

**When it activates:** You ask about current rankings, SERP features (featured snippets, PAA, knowledge panels), rank tracking over time, or "who ranks for this keyword."

**What it knows:** How to pull live SERP results and historical rank data from DataForSEO's SERP and Labs APIs, map which SERP features exist for a query and who owns them, detect significant rank drops or gains, and read AI Overview presence/citations as part of the same SERP snapshot.

**How to use it effectively:**
- Ask "check the SERP for [keyword]" for a live snapshot — organic positions, featured snippet owner, PAA questions, and AI Overview citations in one pass.
- Ask "track our rankings over the last quarter" for historical trend data with peaks, drops, and algorithm-update correlation.
- Ask "who owns the featured snippet for [keyword]" if you're specifically hunting for snippet-capture opportunities.
- Combine with a competitor domain to get head-to-head visibility and "who's gaining/losing ground" analysis.

### nextjs-sanity-seo

**When it activates:** You mention Next.js metadata, `generateMetadata`, Sanity SEO schema fields, `sitemap.ts`/`robots.ts`, JSON-LD components in a Next.js app, or ask for a codebase SEO review.

**What it knows:** Production-ready implementation patterns specific to Next.js App Router + Sanity — the reusable Sanity `seo` object schema, author schema with E-E-A-T fields, FAQ schema for AEO, dynamic `generateMetadata` with Open Graph and Twitter cards, dynamic sitemap and robots generation (including AI crawler rules), a `JsonLd` component pattern, CMS-driven redirects, and `next/image` + Sanity URL builder usage. Unlike the other six skills, this one works entirely from your codebase — no DataForSEO calls involved.

**How to use it effectively:**
- Ask "does every page have `generateMetadata`?" — it greps your codebase and reports gaps.
- Ask "set up a redirect system driven by Sanity" — it scaffolds the `redirect` document schema and the `next.config.ts` wiring.
- Ask "audit my codebase for SEO issues" — this runs the full 10-point codebase checklist (metadata, sitemap, robots, structured data, images, canonicals, redirects, performance, schema fields, author E-E-A-T) and can apply fixes directly if you ask it to.
- Remember `stega: false` — the skill flags any `sanityFetch` call inside `generateMetadata` that's missing it, since stega markers leaking into metadata break titles and descriptions.

## Commands Reference

### /seo-audit

**Usage:** `/seo-audit <url> [keyword]`

Runs the full `seo-site-audit` workflow end-to-end: crawl, on-page analysis, technical health, structured data, and AI-visibility check, then produces an executive summary with a 0-100 score and a prioritized action plan.

**Examples:**
- `/seo-audit example.com`
- `/seo-audit example.com/blog/seo-tips "content marketing"`

### /keyword-research

**Usage:** `/keyword-research <topic or seed keyword> [domain for gap analysis]`

Runs the full `keyword-intelligence` workflow: expands seeds into scored keyword candidates, classifies intent, clusters into content pillars, and — if you supply a domain — layers in competitor gap analysis and page-2 quick wins.

**Examples:**
- `/keyword-research "project management software"`
- `/keyword-research "project management software" example.com`

### /serp-check

**Usage:** `/serp-check <keyword> [domain]`

Pulls a live SERP snapshot for a keyword — organic results, featured snippets, PAA, knowledge panels, and AI Overview citations — and maps which features exist and who owns them. Add a domain to get its current ranking position and feature-capture opportunities.

**Examples:**
- `/serp-check "best crm for small business"`
- `/serp-check "best crm for small business" example.com`

### /backlink-audit

**Usage:** `/backlink-audit <domain> [competitor domain]`

Analyzes a domain's backlink profile — authority distribution, anchor text health, new/lost link trends — and, with a competitor domain, runs link-gap analysis and broken-link reclamation opportunities.

**Examples:**
- `/backlink-audit example.com`
- `/backlink-audit example.com competitor.com`

### /content-optimize

**Usage:** `/content-optimize <url or file path> [target keyword]`

Optimizes a single page or file for SEO and AI extraction: title, meta description, heading hierarchy, internal linking, structured data, and E-E-A-T signals. If given a file path, it edits the file directly; if given a URL, it hands back optimized snippets to implement yourself.

**Examples:**
- `/content-optimize src/app/blog/[slug]/page.tsx "email marketing"`
- `/content-optimize https://example.com/services "seo consulting"`

### /competitor-analysis

**Usage:** `/competitor-analysis <your domain> <competitor domain> [competitor 2]`

Runs a full competitive teardown across keywords, backlinks, and SERP features — domain overview comparison, keyword gap analysis (opportunities, advantages, battleground terms), backlink comparison, and SERP feature ownership — then delivers strategic recommendations.

**Examples:**
- `/competitor-analysis example.com competitor.com`
- `/competitor-analysis example.com competitor1.com competitor2.com`

### /ai-visibility

**Usage:** `/ai-visibility <domain or brand name> [keywords]`

Runs the full `aeo-geo-optimization` workflow: checks AI Overview citation rates, Google AI Mode references, LLM brand mentions across ChatGPT/Claude/Perplexity/Gemini, content AI-readiness, and AI crawler access — then produces an optimization action plan.

**Examples:**
- `/ai-visibility example.com`
- `/ai-visibility "Rhize Media" "workflow automation"`

### /technical-audit

**Usage:** `/technical-audit <url or domain>`

A focused subset of the full site audit — just Core Web Vitals, crawlability, indexation, security/infrastructure, and performance bottlenecks. Use this when you don't need the full content/on-page review.

**Examples:**
- `/technical-audit example.com`

### /rank-track

**Usage:** `/rank-track <domain> [keywords comma-separated]`

Pulls 12-month historical visibility trends plus current position for specified keywords, tracks week-over-week or month-over-month changes, and benchmarks against competitor visibility trends.

**Examples:**
- `/rank-track example.com`
- `/rank-track example.com "seo audit, keyword research, backlink analysis"`

### /code-seo-review

**Usage:** `/code-seo-review [project path]`

Audits a Next.js + Sanity codebase against the `nextjs-sanity-seo` checklist — metadata, sitemap, robots, structured data, Sanity schema fields, images, internal linking, and performance patterns — and can apply fixes directly to the code if you ask it to.

**Examples:**
- `/code-seo-review`
- `/code-seo-review apps/web`

## How the Skills and Commands Work Together

**Keyword research feeds content optimization.** `/keyword-research` tells you which keyword to target and what content format to use; `/content-optimize` (or the `content-seo` skill directly) then optimizes a specific page against that keyword. Run them in sequence when building new content: research first, write/optimize second.

**Site audit feeds technical audit.** `/technical-audit` is a narrower, faster pass through the same `seo-site-audit` skill — use `/seo-audit` for a full report including content and structured data, and `/technical-audit` when you only care about Core Web Vitals and crawlability.

**AEO/GEO layers on top of traditional SEO, it doesn't replace it.** `aeo-geo-optimization` and `/ai-visibility` assume the on-page and technical fundamentals from `content-seo` and `seo-site-audit` are already in decent shape — AI systems cite well-structured, well-established content more readily. Run a standard audit before chasing AI Overview citations.

**Backlinks and keywords combine in competitive analysis.** `/competitor-analysis` pulls together `keyword-intelligence`, `backlink-intelligence`, and `serp-intelligence` in one pass, because a real competitive picture needs all three — who ranks for what, who links to whom, and who owns which SERP features.

**Data skills diagnose, the code skill fixes.** Any of the six DataForSEO-backed skills can tell you metadata is missing or a schema type isn't implemented, but only `nextjs-sanity-seo` (via `/code-seo-review`) knows how to actually write the Next.js/Sanity code to fix it. If `/seo-audit` on a Next.js site turns up structured-data gaps, follow up with `/code-seo-review` to close them in the codebase.

**Rank tracking closes the loop.** After running `/content-optimize`, `/backlink-audit` outreach, or `/code-seo-review` fixes, use `/rank-track` a few weeks later to confirm the changes actually moved rankings or visibility.

## Tips for Getting the Best Results

**Be specific about scope.** "Audit my site" triggers a full crawl; "just check Core Web Vitals" routes to the technical-only path. The more specific you are, the less time Claude spends crawling things you don't need.

**Always mention a target keyword when optimizing content.** `content-seo` and `/content-optimize` produce much sharper title tags, headings, and internal-link recommendations when they know exactly which keyword the page should win.

**Give gap-analysis commands a domain, not just a topic.** `/keyword-research`, `/backlink-audit`, and `/competitor-analysis` all become dramatically more useful once you supply your own domain — without it, they return general research rather than a gap analysis against your actual site.

**Treat AEO/GEO as ongoing, not one-time.** AI Overview citations and LLM brand mentions shift as models update and competitors publish new content. Re-run `/ai-visibility` periodically rather than treating one audit as final.

**For codebases, ask before assuming a fix is safe.** `/code-seo-review` and `nextjs-sanity-seo` can apply edits directly, but structured data mismatches (schema not matching visible content) can trigger manual actions from Google — review generated JSON-LD against the actual page content before shipping.

**Use `/technical-audit` as a fast pre-flight check.** Before a big content push or migration, a quick technical audit catches crawlability or Core Web Vitals regressions before they compound.

## Troubleshooting

**Commands return no data or fail silently:** `DATAFORSEO_USERNAME` and `DATAFORSEO_PASSWORD` aren't set, or are set in a shell session Claude isn't inheriting. Confirm both are exported and re-run — every data skill and command depends on them.

**"Authentication failed" or 401 errors from DataForSEO calls:** Credentials are wrong, expired, or the account doesn't have access to the API module being called (SERP, Labs, Backlinks, AI Optimization, etc. are billed/enabled separately on some plans). Check your DataForSEO dashboard for account status and enabled APIs.

**Crawl results look incomplete for a JS-heavy site:** Confirm the audit is running with `enable_javascript` and `enable_browser_rendering` enabled — without them, React/Next.js/SPA content that renders client-side won't show up in the crawl. This is on by default in the plugin's workflows, but worth confirming if a page looks "empty" in results.

**AI Overview or LLM mention data looks sparse or missing:** AI Overviews don't trigger for every query, and LLM mention tracking depends on DataForSEO's AI Optimization module coverage for your niche/region. Absence of data isn't always absence of visibility — cross-check manually by asking ChatGPT/Perplexity the query directly.

**`/code-seo-review` doesn't find your metadata/sitemap/robots files:** It greps for standard Next.js App Router paths (`app/sitemap.ts`, `app/robots.ts`, `generateMetadata` exports). If your project uses the Pages Router or nonstandard paths, point the command at the specific directory or mention the actual file paths so it looks in the right place.

**Backlink or rank numbers don't match another tool (Ahrefs, Semrush, etc.):** Different providers crawl the web with different bots, on different schedules, using different authority scales. DataForSEO's authority score is 0-1000, not comparable 1:1 with another vendor's 0-100 Domain Rating. Use one provider consistently for trend tracking rather than cross-comparing absolute numbers.

**Structured data validates locally but doesn't show rich results in Google:** Validation confirms the JSON-LD is well-formed, not that Google chooses to display it. Rich results are earned, not guaranteed — check Google Search Console's Enhancements reports over 1-2 weeks after deployment before concluding something is broken.
