---
description: Optimize a page's content for SEO, AEO, and structured data
argument-hint: <url or file path> [target keyword]
allowed-tools: Read, Write, Edit, Grep, Glob, WebFetch
---

Optimize content for SEO and AI visibility using the content-seo skill.

## Process

1. Read the content-seo skill at `${CLAUDE_PLUGIN_ROOT}/skills/content-seo/SKILL.md`.

2. **Analyze the content:**
   - If a URL: fetch the page and extract title, meta, headings, content, links, structured data
   - If a file path: read the file and analyze the code/content

3. **Optimize on-page elements:**
   - Title tag (50-60 chars, keyword front-loaded)
   - Meta description (150-160 chars, CTA included)
   - H1 (exactly one, contains primary keyword)
   - H2-H4 hierarchy (logical, contains secondary keywords)
   - Internal links (3-5 per 1,000 words, descriptive anchor text)
   - Image alt text (descriptive, keyword-relevant)

4. **Optimize for AI extraction (AEO/GEO):**
   - Lead with direct answers under question-format headings
   - Add definition paragraphs (40-60 words) for key concepts
   - Structure with lists and tables for easy AI parsing
   - Implement FAQPage schema for FAQ sections

5. **Implement structured data:**
   - Generate appropriate JSON-LD (Article, FAQ, HowTo, Product, etc.)
   - Validate against Google Rich Results requirements
   - Add @graph for multiple schema types

6. **Check E-E-A-T signals:**
   - Author attribution and credentials
   - Publish/update dates
   - Source citations
   - Trust signals

7. If a file path was provided, **apply optimizations directly** to the code.
   If a URL, **provide optimized code snippets** the user can implement.
