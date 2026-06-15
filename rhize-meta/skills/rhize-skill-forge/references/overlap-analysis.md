# Overlap Analysis — how the similarity score works

`overlap_scan.py` is a fast, dependency-free heuristic, not a semantic oracle. Understand what it
measures so you know when to trust it and when to override.

## What it computes

For the candidate and each existing Rhize skill, it builds a token set from the `name` +
`description` (and, when present, the keyword-ish phrases in the body), removes stopwords, and
computes two numbers:

1. **Jaccard overlap** of the token sets — `|A ∩ B| / |A ∪ B|`. Rewards shared vocabulary.
2. **Keyword containment** — fraction of the candidate's distinctive trigger phrases that also
   appear in the Rhize skill's description. Rewards overlapping *intent*, not just words.

The reported score is a weighted blend (containment weighted higher, because two skills can share
generic words like "Next.js" yet do different jobs). Scores are 0–1.

## How to read it

| Score | Reading | Default prior |
|-------|---------|---------------|
| ≥ 0.45 | Strong overlap — likely the same domain | ABSORB (or REJECT if ours is better) |
| 0.20–0.45 | Partial overlap — adjacent domains | FORK, or ABSORB one piece |
| < 0.20 | Little overlap — new capability | DEFER or FORK as a new skill |

The script prints the **nearest** Rhize skill and the full ranked table. The nearest skill is the
ABSORB target if you go that route.

## When to override the heuristic

The heuristic sees words, not behavior. Override it when:

- **Shared vocabulary, different job.** Two SEO skills may score high but one does keyword research
  and the other does technical audits. Read both bodies before trusting a high score.
- **Different words, same job.** A skill called "mutation hygiene" and our `data-mutation-
  consistency` may score low on tokens but do the same thing. Read descriptions, not just scores.
- **Quality/license dominates.** A perfect-overlap candidate with a bad license is still REJECT.
- **Stack mismatch.** High text overlap but the candidate assumes a foreign stack → FORK or REJECT,
  not ABSORB.

## Practical tip

Run the scan, then actually open the nearest 1–2 Rhize skills and the candidate side by side. The
score tells you *where to look*; your read of the two bodies makes the call. Record the final verb
and the reason in the ingestion report regardless of what the heuristic suggested — the reason is
what makes the next ingestion faster.
