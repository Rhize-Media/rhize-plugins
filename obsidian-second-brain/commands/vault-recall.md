---
description: Ask your vault a natural language question and get a synthesized answer
allowed-tools: ["mcp__obsidian-mcp-server__obsidian_global_search", "mcp__obsidian-mcp-server__obsidian_read_note", "mcp__obsidian-mcp-server__obsidian_list_notes", "Bash"]
argument-hint: <natural language question about your vault>
---

Answer a natural language question by searching the vault, reading the most relevant notes, and synthesizing an answer grounded in the user's own knowledge base. This is a "talk to your notes" interface.

**Requires qmd for best results.** Without qmd, falls back to keyword search which may miss conceptually relevant notes.

Parse "$ARGUMENTS" as the user's question.

## Step 1: Check qmd Availability

```bash
command -v qmd >/dev/null 2>&1 && QMD_AVAILABLE=true || QMD_AVAILABLE=false
if [ "$QMD_AVAILABLE" = true ]; then
  qmd status vault 2>/dev/null && QMD_INDEXED=true || QMD_INDEXED=false
fi
```

If qmd is not available, warn the user: "For the best recall experience, install qmd (`npm install -g qmd`) and index your vault. I'll do my best with keyword search, but I may miss notes that discuss your question using different words."

## Step 2: Search for Relevant Notes

**With qmd (preferred):**
1. Run `qmd query vault "<user's question>"` — this uses hybrid search (BM25 + vector + LLM re-ranking) for the highest quality results.
2. If the question is broad, also run `qmd vsearch vault "<rephrased question>"` with a different phrasing to catch notes the first query missed.

**Without qmd (fallback):**
1. Extract 3-5 key terms from the question.
2. Run `obsidian_global_search` for each key term.
3. Run `obsidian search query="[tag:<relevant-tag>]"` if the question maps to known tags.
4. Combine and deduplicate results.

## Step 3: Read and Analyze Top Results

1. Take the top 5-8 most relevant results from the search.
2. Use `obsidian_read_note` to read the full content of each.
3. As you read, note which parts of each note are relevant to the question.

## Step 4: Synthesize an Answer

Compose an answer that:
- **Draws directly from the user's notes** — cite specific notes with `[[wikilinks]]` inline.
- **Attributes claims to their source notes** — "According to your note [[API Architecture Decisions]], you decided to..."
- **Distinguishes what the vault says from what you know** — if the vault doesn't cover part of the question, say so explicitly: "Your notes don't address X, but based on general knowledge..."
- **Highlights contradictions** — if two notes disagree on something, surface it: "Interestingly, [[Note A]] says X while [[Note B]] suggests Y."
- **Identifies gaps** — note what the vault is missing: "You have extensive notes on the API design but nothing about deployment strategy."

## Step 5: Offer Next Steps

After presenting the answer, offer relevant follow-ups:
- "Want me to create a permanent note synthesizing this?" (if the answer spans multiple sources)
- "Want me to search the web to fill in the gaps?" (if the vault has coverage holes)
- "Want me to connect the notes I found?" (if the relevant notes aren't already linked via `/vault-connect`)
- "Want me to add this Q&A to today's daily note?" (for reference)

## Example Interactions

**User**: `/vault-recall What was our strategy for the SJ Glass SEO project?`
→ Searches vault → finds SJ Glass client notes, meeting notes, email tracking docs → synthesizes: "Based on your notes, the SJ Glass SEO strategy focused on... [[SJ Glass Meeting Notes]] mentions... [[SJ-Glass-Email-Tracking-Implementation-Guide]] details..."

**User**: `/vault-recall What are my main takeaways about options trading?`
→ Searches vault → finds trading notes, strategies, call notes → synthesizes: "Your trading notes center around... [[Trading MOC]] links to X notes on the topic. Key insights include..."

**User**: `/vault-recall Have I written anything about prompt engineering?`
→ Searches vault → finds relevant notes or not → either synthesizes or reports: "I found 3 notes touching on prompt engineering: [[Note 1]], [[Note 2]], [[Note 3]]. Here's what they cover..." or "I didn't find any notes specifically about prompt engineering in your vault."
