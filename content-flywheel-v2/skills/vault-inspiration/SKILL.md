---
name: vault-inspiration
description: >
  ALWAYS invoke this skill for capturing inspiration and research notes in the content flywheel.
  Creates and organizes Obsidian vault notes for content inspiration, using second-brain
  methodology (Zettelkasten + PARA) to build a knowledge graph of content ideas.
  Triggers on: "save inspiration", "capture idea", "content idea", "research note",
  "inspiration source", "bookmark for content", "add to vault", "content brainstorm",
  "save article for reference", "clip for content", "add inspiration".
  Uses Obsidian MCP server to create notes and Neo4j to track inspiration sources.
---

# Vault Inspiration (Content Flywheel)

Capture content inspiration and research notes into Obsidian vault, linking them to the Neo4j content graph. Combines second-brain methodology with the content pipeline.

## Workflow

### 1. Gather Input
- Source URL or text (the inspiration material)
- Topic/theme (what content area this relates to)
- Content piece ID (optional — link to existing content in pipeline)
- Notes (optional — user's thoughts on why this is relevant)

### 2. Create Vault Note
Use the Obsidian MCP server to create a note in the vault:

```markdown
---
type: inspiration
source: <url>
topic: <topic>
contentId: <content-id if linked>
captured: <date>
status: unprocessed
tags:
  - content-flywheel
  - inspiration
  - <topic-tag>
---

# <Title derived from source>

## Source
<URL or reference>

## Key Takeaways
<Extracted or user-provided insights>

## Content Angle
<How this could become content — user notes or AI-suggested angles>

## Related
<Wikilinks to related vault notes>
```

### 3. Store in Neo4j
Create an Inspiration node and link to the content graph:

```cypher
CREATE (i:Inspiration {
  id: randomUUID(),
  title: $title,
  sourceUrl: $sourceUrl,
  topic: $topic,
  notes: $notes,
  capturedAt: datetime()
})
```

If linked to existing content:
```cypher
MATCH (c:ContentPiece {id: $contentId}), (i:Inspiration {id: $inspirationId})
CREATE (c)-[:INSPIRED_BY]->(i)
```

### 4. Knowledge Organization
Following second-brain methodology:
- **Fleeting notes** → Quick captures go to an inbox folder
- **Literature notes** → Processed sources with key takeaways
- **Permanent notes** → Distilled ideas linked to content pipeline
- **MOCs** → Maps of Content for each topic cluster

### 5. Pipeline Integration
When inspiration is ready to become content:
- Create a ContentPiece node in "inspiration" stage
- Link via INSPIRED_BY relationship
- Move through pipeline: inspiration → research → draft → ...

## Note Templates

### Quick Capture
For fast idea capture without a source URL — creates a fleeting note.

### Article Clip
For saving and annotating web articles — creates a literature note with extracted content.

### Research Summary
For consolidating multiple sources on a topic — creates a permanent note with synthesis.
