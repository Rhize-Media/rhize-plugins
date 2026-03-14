# SERP Features Guide

Complete guide to search engine results page features and how to optimize for them.

## SERP Feature Types

### Featured Snippet (Position 0)
**What:** A highlighted answer box above organic results.
**Types:** Paragraph, list, table, video.
**How to win:**
- Answer the question directly in 40-60 words
- Use question-format H2/H3 headings
- Include lists, numbered steps, or tables
- Currently ranking in top 10 for the query is usually required

### People Also Ask (PAA)
**What:** Expandable accordion of related questions.
**How to appear:**
- Implement FAQPage structured data
- Use question-format headings
- Provide concise, direct answers (2-3 sentences)
- Cover related questions on the same page

### Google AI Overview
**What:** AI-generated summary with cited sources.
**How to get cited:**
- Structure content for AI extraction (direct answers, lists, tables)
- Build domain authority and E-E-A-T
- Use structured data (FAQPage, HowTo, Article)
- Allow AI crawlers in robots.txt
- See `aeo-geo-optimization` skill for detailed strategies

### Knowledge Panel
**What:** Information card about entities (brands, people, places).
**How to appear:**
- Establish entity presence (Wikipedia, Wikidata)
- Implement Organization/Person schema
- Consistent NAP across directories
- Claim Google Business Profile

### Local Pack
**What:** Map with 3 local business listings.
**How to appear:**
- Optimize Google Business Profile
- Implement LocalBusiness schema
- Build local citations (directories, chambers of commerce)
- Collect Google reviews

### Image Pack
**What:** Row of image thumbnails in results.
**How to appear:**
- Use original, high-quality images
- Descriptive alt text with target keywords
- Descriptive file names
- Image sitemap
- Proper image dimensions and compression

### Video Pack
**What:** Video thumbnails (usually YouTube).
**How to appear:**
- Create YouTube videos targeting the keyword
- Optimize video title, description, and tags
- Add VideoObject schema to embedded videos
- Create video chapters with timestamps

### Sitelinks
**What:** Additional links under the main result.
**How to earn:**
- Clear site structure and navigation
- Descriptive internal linking
- Breadcrumb navigation with schema
- Brand authority signals

### Shopping Results
**What:** Product listings with images and prices.
**How to appear:**
- Google Merchant Center feed
- Product schema with price and availability
- Optimized product titles and descriptions

## SERP Feature Detection with DataForSEO

Use the SERP API to detect features for any keyword:
- `type: "featured_snippet"` — paragraph, list, or table snippets
- `type: "people_also_ask"` — PAA questions and sources
- `type: "knowledge_graph"` — knowledge panel data
- `type: "local_pack"` — local business results
- `type: "images"` — image pack results
- `type: "video"` — video results
- `type: "ai_overview"` — AI Overview presence and citations
- `type: "related_searches"` — related search suggestions

## SERP Analytics Prompts

### Long-Term Visibility Trends
"Using google_historical_rank_overview in DataForSEO Labs API, show how the visibility and SERP position distribution of [domain] changed in [location] in [language] over the past 12 months. Focus on the top 3, top 10, and top 100 rankings, and highlight any traffic peaks."
- **API:** DataForSEO Labs API

### Competitive Traffic Comparison
"Compare the monthly organic traffic trends and ranking distribution of [domain] vs [competitor] in [location] in [language] using google_domain_rank_overview. Highlight who has better top 10 visibility and estimated traffic this month."
- **API:** DataForSEO Labs API
