---
name: vault-templates
description: >
  Library of proven note templates and archetypes for Obsidian vaults — meeting notes,
  book reviews, project briefs, weekly reviews, literature notes, permanent notes, and more.
  Use this skill when someone asks to create a specific type of note (e.g., "meeting note",
  "book review", "project brief"), wants a template for a recurring note type, asks about
  frontmatter conventions for different note types, or says things like "set up a template for",
  "what properties should a X note have", or "create a note for my meeting/book/project/review".
  Also triggers on "note template", "note archetype", "weekly review template", "daily template",
  or any request to scaffold a structured note.
---

# Vault Templates — Note Archetypes for Obsidian

This skill provides ready-to-use note structures for common use cases. Each template defines the frontmatter properties, section structure, and linking conventions that make the note type work well in an Obsidian vault.

When creating a note from one of these templates, adapt it to the user's existing vault conventions. If they already use `status: active` instead of `status: in-progress`, follow their pattern. The templates below are starting points, not rigid schemas.

## Meeting Notes

For capturing discussions, decisions, and action items from meetings.

```markdown
---
type: meeting
date: {{date}}
attendees:
  - Person Name
tags:
  - meeting
  - project-or-topic
status: open
---

# Meeting: {{title}}

## Context
Why this meeting was called and what we hoped to accomplish.

## Discussion
Key points discussed, organized by topic.

## Decisions
- **Decision 1**: What was decided and why
- **Decision 2**: What was decided and why

## Action Items
- [ ] Action item — @owner — due {{date}}
- [ ] Action item — @owner — due {{date}}

## Follow-up
- [[Next meeting or related note]]
- Open questions to resolve before next time
```

**Properties**: `date` (when it happened), `attendees` (who was there), `status` (open/closed — close when all action items are done).

## Book Review / Literature Note

For processing books, articles, papers, or any substantial source material. Supports progressive summarization — start with captures, refine over time.

```markdown
---
type: literature
source: "{{title}} by {{author}}"
author: {{author}}
date-read: {{date}}
rating:
tags:
  - literature
  - topic
status: processing
summarization-layer: 1
---

# {{title}}

> [!abstract] Summary
> (Fill this in on your second or third pass — not on first read.)

## Key Ideas
- Idea 1 — in your own words, not a quote
- Idea 2
- Idea 3

## Quotes
> "Notable quote from the source" (p. XX)

> "Another quote" (p. XX)

## My Reactions
What surprised me, what I disagree with, what connects to things I already know.

## Connections
- [[Related permanent note]]
- [[Another related note]]
- Reminds me of [[concept or experience]]

## Action Items
- [ ] Write a permanent note about key idea 1
- [ ] Revisit in 2 weeks for progressive summarization pass
```

**Properties**: `source` (full citation), `author`, `date-read`, `rating` (optional, 1-5), `summarization-layer` (1-5 for progressive summarization tracking), `status` (processing/complete).

## Project Brief

For defining and tracking a project from inception to completion.

```markdown
---
type: project
status: active
priority: high
start-date: {{date}}
due-date:
tags:
  - project
  - area
---

# {{project name}}

## Objective
One sentence: what does "done" look like?

## Background
Why this project exists. What problem it solves. Link to any [[related notes]] or prior work.

## Scope
What's included:
- Deliverable 1
- Deliverable 2

What's explicitly excluded:
- Out-of-scope item

## Tasks
- [ ] Task 1
- [ ] Task 2
- [ ] Task 3

## Resources
- [[Related document or reference]]
- External link or tool

## Log
### {{date}}
- Started project, defined scope
```

**Properties**: `status` (active/paused/complete/archived), `priority` (high/medium/low), `start-date`, `due-date`. Move to Archive folder when complete.

## Weekly Review

For reflecting on the past week and planning the next one. Best used with a recurring schedule (every Friday or Sunday).

```markdown
---
type: review
review-type: weekly
date: {{date}}
week: {{week number}}
tags:
  - review
  - weekly
---

# Weekly Review — {{date range}}

## What Happened
### Completed
- Thing I finished this week
- Another accomplishment

### In Progress
- What's still moving forward
- What got stalled and why

### Unexpected
- Surprises, interruptions, new information

## Reflection
- What went well and why?
- What didn't go well and what would I change?
- What did I learn?

## Next Week
### Priorities
1. Most important thing
2. Second priority
3. Third priority

### Calendar
- Monday: ...
- Key meetings or deadlines

## Notes to Self
Anything worth remembering for future weeks.
```

**Properties**: `review-type` (weekly/monthly/quarterly), `date`, `week`. Link back to daily notes from the week with `[[daily note]]` references.

## Permanent / Evergreen Note

For atomic, self-contained ideas that become building blocks of the knowledge graph. The title should be a statement, not a topic label.

```markdown
---
type: permanent
created: {{date}}
tags:
  - topic/subtopic
---

# {{Claim or insight as a complete statement}}

{{2-4 paragraphs explaining the idea in your own words. Write as if explaining to a curious colleague. Include enough context that the note makes sense on its own without reading linked notes.}}

## Evidence
- Source or experience that supports this idea
- [[Literature note]] that this insight came from

## Connections
- Supports: [[another permanent note]]
- Contradicts: [[a different perspective]]
- Extends: [[a foundational concept]]

## Open Questions
- What I still don't understand about this
- Edge cases where this might not apply
```

**Properties**: `type: permanent`, `created` date, topic tags. Keep property set minimal — the value is in the content and links, not the metadata.

## Daily Note Sections

For users who want a structured daily note template rather than freeform journaling.

```markdown
---
type: daily
date: {{date}}
tags:
  - daily
---

# {{date}}

## Plan
- [ ] Top priority for today
- [ ] Second priority
- [ ] Third priority

## Log
- {{timestamp}} — What happened, what I did, what I learned

## Captures
- Ideas, quotes, links, and fleeting thoughts go here throughout the day

## End of Day
- What got done vs. what was planned?
- Anything to carry forward to tomorrow?
```

This template works well with `obsidian daily` to auto-create and `obsidian daily:append` to add entries throughout the day.

## Person / Contact Note

For tracking information about people you interact with professionally or personally.

```markdown
---
type: person
company: {{company}}
role: {{role}}
met-via: {{context}}
tags:
  - person
  - context
last-contact: {{date}}
---

# {{Person Name}}

## About
How I know them, what they do, shared context.

## Notes
### {{date}}
- What we discussed, what I learned

## Links
- [[Project we collaborated on]]
- [[Meeting note where they were mentioned]]
```

## Choosing a Template

When a user asks to "create a note" without specifying a type, infer from context:

| User says | Template |
|-----------|----------|
| "meeting note", "meeting with..." | Meeting Notes |
| "book review", "article summary", "reading notes" | Literature Note |
| "project plan", "new project", "project brief" | Project Brief |
| "weekly review", "reflect on my week" | Weekly Review |
| "I had an insight about...", "I realized that..." | Permanent Note |
| "note about [person]", "remember [person]" | Person Note |
| No clear type, short content | Append to daily note |
| No clear type, substantial content | Standalone note with minimal frontmatter |

## Adapting to User Conventions

Before applying a template, check if the user's vault already has conventions:

1. Look at existing notes of the same type — do they use different property names or structures?
2. Check for an existing templates folder — the user may have their own Obsidian templates
3. Match existing tag patterns (flat vs. nested, singular vs. plural)
4. Preserve any property naming conventions already in use (`dateRead` vs `date-read` vs `date_read`)

The goal is consistency with the vault, not strict adherence to these templates.
