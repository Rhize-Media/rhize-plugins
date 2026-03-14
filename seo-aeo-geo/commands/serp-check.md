---
description: Check SERP features and rankings for keywords
argument-hint: <keyword> [domain]
allowed-tools: Read, WebSearch
---

Analyze the SERP landscape for $ARGUMENTS using the serp-intelligence skill.

## Process

1. Read the serp-intelligence skill at `${CLAUDE_PLUGIN_ROOT}/skills/serp-intelligence/SKILL.md`.

2. **Pull live SERP data** via DataForSEO SERP API:
   - Full organic results (positions 1-100)
   - Featured snippets and source URLs
   - People Also Ask questions
   - Knowledge panels
   - Local pack, image pack, video pack
   - Google AI Overview presence and cited sources
   - Related searches

3. **Map SERP features** — which features exist and who owns them.

4. If a domain was provided:
   - Check current ranking position
   - Identify SERP feature opportunities to capture
   - Compare against top-ranking competitors

5. **Assess AI Overview** — is there an AI Overview? What sources are cited? What content patterns do cited sources share?

6. **Generate report** with:
   - SERP feature map
   - Ranking positions
   - Opportunity analysis
   - Recommended actions to capture features
