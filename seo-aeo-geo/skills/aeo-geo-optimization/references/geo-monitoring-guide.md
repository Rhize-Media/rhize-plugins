# GEO Monitoring Guide

How to track and measure AI visibility using DataForSEO and manual monitoring.

## DataForSEO AI Optimization Module

### Brand Mention Tracking
Use the AI Optimization module to monitor brand mentions across LLM platforms:
- ChatGPT responses mentioning your brand
- Claude responses referencing your content
- Perplexity citations to your pages
- Gemini mentions and recommendations

### Keyword-Level AI Visibility
Track which of your target keywords trigger AI responses that cite your content:
1. Submit target keywords to the AI Optimization endpoint
2. Record which LLMs mention your brand per keyword
3. Track mention sentiment (positive, neutral, negative)
4. Monitor accuracy of AI-generated information about your brand

## DataForSEO SERP API — AI Overview Tracking

### Scraping AI Overview References
Use SERP API with AI Overview extraction to:
1. Check which target keywords trigger Google AI Overviews
2. Extract all sources cited in the AI Overview
3. Track whether your domain appears as a cited source
4. Monitor competitor citations in AI Overviews

### Google AI Mode References
Use SERP API to extract citations from Google AI Mode:
1. Identify which queries activate AI Mode responses
2. Extract referenced websites per keyword
3. Track your citation rate vs competitors
4. Identify patterns in content that gets cited

## Manual Monitoring Workflow

### Weekly AI Visibility Check
1. Take your top 20 target keywords
2. Search each in:
   - Google (check for AI Overview and citations)
   - ChatGPT (ask "What is [topic]?" and note sources)
   - Perplexity (search and check cited sources)
   - Claude (ask about your topic area)
3. Record: mentioned? accurate? positive? linked?

### Monthly Competitive Comparison
1. Run the same queries for your brand vs competitors
2. Track: who gets mentioned more frequently?
3. Analyze: what content characteristics correlate with AI citations?
4. Action: optimize underperforming content based on patterns

## Key Metrics to Track

| Metric | Measurement | Target |
|--------|-------------|--------|
| AI Overview Citation Rate | % of target keywords where you're cited | > 30% |
| LLM Mention Rate | % of brand queries mentioning you across LLMs | > 60% |
| Mention Accuracy | % of AI mentions with accurate information | > 90% |
| AI Referral Traffic | Visitors from AI platforms (GA4) | Growing MoM |
| Featured Snippet Rate | % of target keywords where you own the snippet | > 20% |
| SERP Feature Coverage | Number of SERP features owned | Growing |

## Google Analytics Setup

Track AI-referral traffic in GA4:
- Filter referral traffic from: chat.openai.com, perplexity.ai, claude.ai, bing.com/chat
- Create a custom channel group for "AI Referral"
- Set up alerts for significant traffic changes from AI platforms
- Compare AI referral vs organic search trends

## Alerting Strategy

Set up alerts for:
- **Critical:** Brand mentioned inaccurately by an AI system
- **High:** Significant drop in AI Overview citations (> 20% change)
- **Medium:** Competitor gains AI visibility for your core keywords
- **Low:** New AI platform starts citing your content (opportunity)
