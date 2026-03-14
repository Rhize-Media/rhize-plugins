# Keyword Clustering Strategies

How to organize keywords into actionable content clusters.

## Clustering Methods

### Intent-Based Clustering
Group keywords by search intent:

| Intent | Keywords | Content Type |
|--------|----------|-------------|
| Informational | how to, what is, guide, tutorial, tips | Blog posts, guides, videos |
| Commercial | best, review, compare, vs, alternative | Comparison pages, reviews |
| Transactional | buy, pricing, demo, sign up, free trial | Product pages, landing pages |
| Navigational | [brand name], [product name] login | Homepage, product pages |

### Topic Clustering (Hub and Spoke)
Organize around pillar topics:

**Pillar page** (comprehensive, 3,000+ words):
- Targets the primary broad keyword
- Links to all spoke pages
- Covers the topic at a high level

**Spoke pages** (focused, 1,000-2,000 words):
- Each targets a specific subtopic or long-tail variation
- Links back to the pillar page
- Links to related spoke pages

**Example cluster: "Project Management"**
- Pillar: "The Complete Guide to Project Management"
- Spokes: "Agile vs Waterfall", "Best PM Tools for Remote Teams", "How to Create a Project Timeline", "Project Management for Startups", "Kanban Board Best Practices"

### Semantic Clustering
Group keywords that share semantic meaning:
- Use DataForSEO's keyword_suggestions endpoint for related terms
- Cluster keywords that appear in the same SERP results (SERP overlap = same topic)
- One page should target the entire semantic cluster, not individual keywords

## Prioritization Framework

Score each cluster on four dimensions:

1. **Volume** (1-5): Total monthly search volume of all keywords in cluster
2. **Difficulty** (1-5 inverted): Average keyword difficulty (lower difficulty = higher score)
3. **Intent alignment** (1-5): How well the intent matches your business goals
4. **Business value** (1-5): Revenue potential from ranking for these terms

**Priority Score = (Volume + Difficulty + Intent + Business Value) / 4**

Target clusters scoring 3.5+ first.

## Keyword-to-URL Mapping

After clustering, map every keyword to a specific URL:

| Cluster | Primary Keyword | Target URL | Status | Priority |
|---------|----------------|------------|--------|----------|
| Remote Work | best project management tools for remote teams | /blog/remote-pm-tools | To create | High |
| Remote Work | remote team collaboration | /blog/remote-pm-tools | Same page | — |
| Pricing | project management software pricing | /pricing | Exists - optimize | Medium |

Rules:
- One primary keyword per URL
- 5-10 secondary keywords per URL (same page)
- No two URLs targeting the same primary keyword (avoid cannibalization)
- Keywords without assigned URLs are wasted research
- Review and update this mapping quarterly
