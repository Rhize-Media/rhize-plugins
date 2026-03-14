---
name: second-brain
description: >
  Personal knowledge management methodology for Obsidian vaults — Zettelkasten,
  PARA, Maps of Content (MOCs), progressive summarization, and atomic notes.
  Use this skill whenever someone asks about organizing their vault as a second brain,
  building a knowledge system, creating MOCs or maps of content, linking notes together
  strategically, applying Zettelkasten or PARA methods, structuring a PKM workflow,
  deciding where a note should live, or asking "how should I organize this?" in the
  context of Obsidian. Also triggers on "evergreen notes", "literature notes",
  "fleeting notes", "permanent notes", "note-taking system", "knowledge graph",
  "linking my thinking", or "connect my notes".
---

# Second Brain — Knowledge Management Methodology

This skill teaches you how to make *intelligent organizational decisions* in an Obsidian vault — not just where to put files, but how to structure knowledge so it compounds over time. The methods below are complementary, not competing. Most effective vaults blend elements from several.

## Core Principle: Notes Should Earn Their Links

A link between two notes is a claim that they're related. Every `[[wikilink]]` should exist because the ideas genuinely connect, not because the topics share a keyword. When helping a user link notes, ask: "Would someone reading Note A benefit from knowing about Note B?" If yes, link. If not, a shared tag is probably sufficient.

## Zettelkasten Method

Zettelkasten ("slip box") is a system for developing ideas through small, densely-linked notes.

### Note Types

**Fleeting notes** — Quick captures of thoughts, quotes, or observations. They live in an inbox and get processed within 1-2 days into permanent notes or discarded. In Obsidian, these are daily note entries or quick captures.

**Literature notes** — Summaries of a source (article, book, video) written in your own words. They reference the source but express the ideas in a way you understand. One note per source.

```yaml
---
type: literature
source: "Book Title by Author"
tags:
  - literature
  - topic/subtopic
date: 2026-03-14
status: processed
---
```

**Permanent notes** — Atomic, self-contained ideas written in complete sentences. Each permanent note expresses exactly one idea and links to related permanent notes. These are the building blocks of the knowledge graph.

```yaml
---
type: permanent
tags:
  - topic/subtopic
created: 2026-03-14
---
```

Rules for permanent notes:
- One idea per note — if you need "and" to describe it, split it
- Write in full sentences as if explaining to someone else
- Title should be a statement or claim, not a topic label ("Spaced repetition strengthens recall" not "Spaced Repetition")
- Link to other permanent notes that support, contradict, or extend the idea
- Include a brief context line at the top explaining why this idea matters to you

### Processing Workflow

```
Fleeting note (daily capture)
  → Ask: "Is there an idea here worth keeping?"
    → Yes → Write a permanent note in your own words
           → Link it to 2-3 existing permanent notes
           → Update any relevant MOCs
    → No  → Archive or delete the fleeting note
```

## PARA Method

PARA organizes information by *actionability*, not topic. Created by Tiago Forte.

| Folder | Contains | Timeframe |
|--------|----------|-----------|
| **Projects** | Active work with a deadline or deliverable | Days to weeks |
| **Areas** | Ongoing responsibilities with standards to maintain | Indefinite |
| **Resources** | Topics of interest for future reference | As needed |
| **Archive** | Inactive items from the above three | Done |

### When to Use PARA in Obsidian

PARA works best as a top-level folder structure. Notes move between folders as their status changes — a project note moves to Archive when the project completes; a resource becomes a project when you decide to act on it.

```
vault/
├── Projects/
│   ├── Q2 Product Launch/
│   └── Blog Redesign/
├── Areas/
│   ├── Health/
│   ├── Finance/
│   └── Team Management/
├── Resources/
│   ├── Marketing/
│   ├── Machine Learning/
│   └── Recipes/
└── Archive/
    ├── 2025 Annual Review/
    └── Old Blog Redesign/
```

Use `obsidian move` (not filesystem moves) to relocate notes — it preserves all wikilinks.

### PARA + Zettelkasten Hybrid

Many effective vaults use PARA for folder structure and Zettelkasten for note-linking. Projects and Areas contain actionable notes organized by context. A separate `Notes/` or `Zettelkasten/` folder holds permanent notes organized by idea. MOCs bridge the two systems.

## Maps of Content (MOCs)

MOCs are hub notes that curate links to related notes around a theme. They're the index layer of a vault — not folders, but living documents that reflect how you think about a topic.

### Anatomy of a MOC

```markdown
---
type: moc
tags:
  - moc
  - topic
---

# Machine Learning

A map of my notes on ML concepts, tools, and projects.

## Core Concepts
- [[Gradient descent finds local minima by following the slope]]
- [[Overfitting happens when a model memorizes noise]]
- [[Regularization trades training accuracy for generalization]]

## Tools & Frameworks
- [[PyTorch vs TensorFlow — when to use each]]
- [[Hugging Face makes transformer models accessible]]

## My Projects
- [[Customer churn prediction model]]
- [[Sentiment analysis pipeline for reviews]]

## Open Questions
- How does few-shot learning change the training paradigm?
- When is fine-tuning better than prompt engineering?
```

### MOC Design Principles

- Group links by subtopic, not alphabetically — the grouping itself is knowledge
- Include brief annotations next to links when the title alone isn't enough context
- Add an "Open Questions" section — this is where future thinking starts
- MOCs should be *curated*, not exhaustive — leave out notes that don't add to the narrative
- A note can appear in multiple MOCs — that's a feature, not a problem
- Create a MOC when you have 5+ notes on a topic and keep finding yourself searching for them

### When to Create vs. Update a MOC

- **Create** when a topic cluster emerges (5+ related notes with no hub)
- **Update** when adding a new note that belongs to an existing MOC
- **Split** when a MOC section grows beyond 15-20 links — that section wants to be its own MOC
- **Merge** when two MOCs significantly overlap — combine and redirect

## Progressive Summarization

A technique for making notes increasingly useful over time through layered highlighting.

### The Five Layers

1. **Original content** — The full captured text (article, book notes, meeting notes)
2. **Bold passages** — Bold the most interesting or useful sentences on first review
3. **Highlighted passages** — ==Highlight== the best of the bolded content on second review
4. **Executive summary** — Write a 2-3 sentence summary at the top on third review
5. **Remix** — Transform into your own original content (blog post, presentation, permanent note)

The key insight: don't summarize everything upfront. Layer summaries *as you revisit notes*. Notes you never revisit don't need summaries — and that's fine.

### Implementation in Obsidian

```markdown
---
type: literature
source: "Article Title"
summarization-layer: 3
---

> [!abstract] Executive Summary
> The main argument is that X leads to Y because Z. The practical takeaway
> is to do A when B happens.

The full article text below with **bold passages** on first pass
and ==highlighted key insights== on second pass.
```

Use the `summarization-layer` property to track how processed each note is. This makes it queryable in Bases — you can build a view showing notes at layer 1 that are due for review.

## Atomic Notes

The principle that each note should contain exactly one idea, be self-contained, and be understandable without reading other notes.

### Test for Atomicity

Ask these questions about a note:
- Can I give this note a title that's a complete statement? (Good: "Compound interest rewards patience" — Bad: "Finance Notes")
- If I linked to this note from somewhere else, would the reader understand it without context? If not, it's not self-contained.
- Does this note try to explain more than one concept? If yes, split it.

### When NOT to Be Atomic

Not everything needs to be an atomic note:
- **Project notes** can be long and messy — they're working documents
- **Meeting notes** capture a session, not a single idea
- **Daily notes** are journals, not knowledge units
- **MOCs** are collections by design

Atomicity applies to permanent/evergreen notes — the ideas you want to link and build on.

## Choosing an Approach

When a user asks "how should I organize my vault?" the answer depends on their goals:

| Goal | Recommended Approach |
|------|---------------------|
| Building a long-term knowledge base | Zettelkasten + MOCs |
| Managing work and life projects | PARA folders |
| Both knowledge and project management | PARA structure + Zettelkasten notes + MOCs |
| Processing lots of reading material | Literature notes + Progressive Summarization |
| Just getting started | Start with daily notes + a single MOC for your main interest |

The most common mistake is over-engineering the system before you have enough notes. Start simple — daily captures, one MOC, a few permanent notes — and let the structure emerge from the content.
