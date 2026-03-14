---
description: Check AI/LLM visibility and AEO/GEO optimization status
argument-hint: <domain or brand name> [keywords]
allowed-tools: Read, WebSearch
---

Audit AI visibility and AEO/GEO optimization for $ARGUMENTS using the aeo-geo-optimization skill.

## Process

1. Read the aeo-geo-optimization skill at `${CLAUDE_PLUGIN_ROOT}/skills/aeo-geo-optimization/SKILL.md`.

2. **Check AI Overview presence** via DataForSEO SERP API:
   - Which target keywords trigger Google AI Overviews?
   - Is the domain cited in AI Overviews? For which queries?
   - What competitor domains are being cited instead?
   - Extract all sources referenced in AI Overviews

3. **Check Google AI Mode references:**
   - Use DataForSEO to scrape AI Mode citations
   - Track which sources appear in AI-generated responses

4. **Monitor LLM brand visibility** via DataForSEO AI Optimization module:
   - Is the brand mentioned by ChatGPT, Claude, Perplexity, Gemini?
   - Is the information accurate and current?
   - How does brand visibility compare to competitors?

5. **Audit content for AI readiness:**
   - Is content structured for AI extraction? (headings, lists, tables)
   - Are answers direct and front-loaded?
   - Is FAQPage structured data implemented?
   - Are publish/update dates visible?

6. **Check AI crawler access:**
   - Review robots.txt for GPTBot, ClaudeBot, PerplexityBot, Google-Extended
   - Are crawlers being inadvertently blocked?

7. **Generate AI visibility report** with:
   - AI Overview citation rate and sources
   - LLM mention audit across platforms
   - Content readiness assessment
   - Crawler access status
   - Optimization action plan for AEO/GEO improvement
