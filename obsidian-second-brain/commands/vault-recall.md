---
description: Ask your vault a natural language question and get a synthesized answer
allowed-tools: ["mcp__obsidian-mcp-server__obsidian_search_notes", "mcp__obsidian-mcp-server__obsidian_get_note", "mcp__obsidian-mcp-server__obsidian_list_notes", "Bash", "Read", "Glob", "Grep"]
argument-hint: <natural language question about your vault>
model: haiku
---

Answer a natural language question by searching the vault, reading the most relevant notes, and synthesizing an answer grounded in the user's own knowledge base. This is a "talk to your notes" interface.

**qmd is optional.** Keyword search may miss conceptual matches; compare representative questions before claiming a quality improvement.

Parse "$ARGUMENTS" as the user's question.

## Step 1: Check qmd Availability

Load `qmd-search` and its [approved indexing procedure](../skills/qmd-search/references/approved-indexing.md).
Read `QMD_INDEX` and `QMD_COLLECTION` from the approved setup record; verify installed CLI,
actual collection path/mask, indexed members and embedding readiness before choosing qmd.
Never guess a default `vault` collection, create an index while searching, or treat status's
exit code as evidence of scope/freshness. Keep compiler output and private state unindexed.
If qmd is unavailable or scope cannot be verified, use MCP/CLI/filesystem search bounded to the
same authorized note scope. Never silently broaden fallback search to the whole vault.

## Step 2: Search for Relevant Notes

**With qmd (preferred):**
1. Run `qmd --index "${QMD_INDEX:?set approved index}" query "<user's question>" -c "${QMD_COLLECTION:?set approved collection}"` — this uses hybrid search (BM25 + vector + LLM re-ranking) to rank candidate results.
2. If the question is broad, also run `qmd --index "${QMD_INDEX:?set approved index}" vsearch "<rephrased question>" -c "${QMD_COLLECTION:?set approved collection}"` with a different phrasing to catch notes the first query missed.

**Without qmd (fallback):**
1. Extract 3-5 key terms from the question.
2. Run `obsidian_search_notes` (`mode: "text"`) for each key term.
3. Run `obsidian search query="[tag:<relevant-tag>]"` if the question maps to known tags.
4. Combine and deduplicate results.

## Step 3: Read and Analyze Top Results

1. Take the top 5-8 most relevant results from the search.
2. Re-check that each result is within the authorized scope, then use `obsidian_get_note` to read the live source. Do not cite an indexed snippet without verifying it.
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

**User**: `/vault-recall What was our strategy for the Acme Co. SEO project?`
→ Searches vault → finds Acme Co. client notes, meeting notes, email tracking docs → synthesizes: "Based on your notes, the Acme Co. SEO strategy focused on... [[Acme Co. Meeting Notes]] mentions... [[Acme-Co-Email-Tracking-Implementation-Guide]] details..."

**User**: `/vault-recall What are my main takeaways about options trading?`
→ Searches vault → finds trading notes, strategies, call notes → synthesizes: "Your trading notes center around... [[Trading MOC]] links to X notes on the topic. Key insights include..."

**User**: `/vault-recall Have I written anything about prompt engineering?`
→ Searches vault → finds relevant notes or not → either synthesizes or reports: "I found 3 notes touching on prompt engineering: [[Note 1]], [[Note 2]], [[Note 3]]. Here's what they cover..." or "I didn't find any notes specifically about prompt engineering in your vault."
