---
name: ai-visibility
description: >
  ALWAYS invoke this skill for AI/Answer Engine visibility checks in the content flywheel.
  Monitors brand mentions across AI engines using DataForSEO AI Optimization API and persists
  AIVisibilitySnapshot nodes to Neo4j.
  Triggers on: "AI visibility", "AEO", "GEO", "answer engine optimization",
  "generative engine optimization", "AI overview", "AI mentions", "brand mentions in AI",
  "ChatGPT mentions", "Perplexity mentions", "AI search", "AI citation",
  "how does AI see my brand", "AI brand monitoring".
  Results are stored as AIVisibilitySnapshot nodes linked to ContentPiece via HAS_AI_VISIBILITY relationships.
---

# AI Visibility Monitoring (Content Flywheel)

Monitor how AI engines (ChatGPT, Perplexity, Google AI Overview) mention and cite your brand. Uses DataForSEO AI Optimization API. All results persist to Neo4j.

## Workflow

### 1. Gather Input
- Brand name (required — the brand to monitor)
- Content piece ID (optional — links visibility data to specific content)
- Queries (optional — specific queries to check; defaults to content keywords or brand variations)
- Location/language (default: US, English)

### 2. Run Analysis
```
POST /api/workflows/ai-visibility
{ "brand": "Acme Corp", "contentId": "abc123", "queries": ["best project management tools"] }
```

### 3. What's Monitored
- Whether the brand is mentioned in AI-generated responses
- Accuracy of AI mentions (factual correctness)
- Citation count (how many times cited per query)
- Which LLMs mention the brand
- Position within AI-generated responses

### 4. Optimization Strategies
Based on results, the skill recommends:

**For low mention rate:**
- Structure content with clear question-answer formatting
- Add FAQ schema markup (FAQPage JSON-LD)
- Create definitive "What is [Brand]?" content
- Build entity presence across authoritative sources

**For low accuracy:**
- Update factual claims across all content
- Ensure consistent entity information (name, description, offerings)
- Add structured data for organization and products
- Monitor and correct AI hallucinations about the brand

**For low citation count:**
- Optimize content for AI extraction (answer-first paragraphs)
- Implement HowTo and Article schema
- Create comprehensive, authoritative resource pages
- Build citations from high-authority domains

### 5. Output
- Overall mention rate (% of queries where brand appears)
- Overall accuracy score
- Per-query snapshot table
- AIVisibilitySnapshot nodes in Neo4j
- HAS_AI_VISIBILITY relationships to content pieces
- WorkflowRun node with status and timing
