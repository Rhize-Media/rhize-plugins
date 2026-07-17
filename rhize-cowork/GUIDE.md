# rhize-cowork — Guide

## What problem this solves

Every Cowork project runs better when Claude knows the business, the voice, and the win before the first real task. Without that context layer, every deliverable starts generic and gets corrected into shape. With it, the first draft is already on-ICP, in-voice, and outcome-led.

`project-kickoff` stands that layer up in one session: four small files in the project root that every later task reads.

| File | What it holds |
| --- | --- |
| `CLAUDE.md` | Operating manual — scope, output defaults, constraints, definition of done |
| `BUSINESS.md` | The business — offer, pricing, ICP, competitors, unique mechanism, current goal |
| `PERSONALITY.md` | Voice & tone — whose voice, tone words, always/never phrases, a swipe sample |
| `INFO.md` | Reference — links, tools, key people, where brand assets live |

## When to reach for it

- Starting any new Cowork project (internal or client)
- Onboarding a new client and you want their context captured once, properly
- You dropped a website or strategy doc into a project and want the context files built from it

## Example prompts

- "Set up a new project for [client]."
- "Kick off this project — here's their website: [url]"
- "Create the project files / CLAUDE.md for this folder."
- "Onboard [business name] — I've attached their brand doc."

Even naming just one file ("build me a CLAUDE.md") triggers the full four-file set unless you say otherwise.

## Tips

- **Give it a website or a strategy doc if you have one.** The skill extracts first and only interviews for the gaps — the more you feed it, the shorter the Q&A.
- **Paste one sample of copy that nails the voice.** This single input lifts output quality more than any other — the skill will push for it, let it.
- **Don't force answers you don't have.** A clean `[TBD — confirm]` is correct output; the hand-off gives you a punch-out list to fill in later.
- Anything pulled from a website rather than your mouth is tagged `[inferred]` — verify those before the files are treated as settled truth.

## Troubleshooting

- **Files feel generic** → you skipped the voice sample or the ICP questions. Re-run the voice group and paste a swipe.
- **A fact in the files is wrong** → it should be carrying an `[inferred]` tag; correct it and remove the tag. If an untagged fact is wrong, that's a skill bug — flag it.
- **Website couldn't be fetched** → the skill falls back to the interview; paste key pages manually if you want extraction.
