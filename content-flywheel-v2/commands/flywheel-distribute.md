---
description: Schedule social media distribution for published content via GoHighLevel
argument-hint: <content-id> <platform> [scheduled-time]
allowed-tools: Read, Bash(curl:*), WebFetch
---

Schedule social media distribution for $ARGUMENTS via the distribution adapter and track in Neo4j.

## Process

1. **Parse arguments:**
   - First argument: content piece ID (required)
   - Second argument: platform — e.g., `facebook`, `instagram`, `linkedin`, `twitter` (required)
   - Third argument (optional): scheduled time in ISO format (default: immediate)

2. **Generate post text** from content piece:
   - Fetch content details from Neo4j
   - Generate platform-appropriate copy (length, hashtags, tone)

3. **Schedule via API route:**
   ```
   POST /api/publish/social
   {
     "contentId": "<content-id>",
     "platform": "<platform>",
     "text": "<generated post text>",
     "scheduledAt": "<ISO datetime or null for immediate>"
   }
   ```

4. **Track distribution** in Neo4j:
   - DistributionChannel node created/updated
   - DISTRIBUTED_TO relationship links content to channel
   - Post status tracked (scheduled/posted/failed)

5. **Present results** to user:
   - Scheduled post confirmation with date/time
   - Platform and post preview
   - Neo4j tracking confirmation

6. **Verify** — query Neo4j:
   ```cypher
   MATCH (c:ContentPiece {id: "<content-id>"})-[:DISTRIBUTED_TO]->(d:DistributionChannel)
   RETURN d.platform, d.status, d.scheduledAt
   ```
