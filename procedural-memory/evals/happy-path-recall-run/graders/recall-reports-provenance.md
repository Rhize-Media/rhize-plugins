---
name: recall-reports-provenance
type: regex
pattern: 'trust.{0,60}unreviewed'
flags: i
match: contains
target: last_message
---

The agent's response must report the recalled artifact's trust tier (not just its name/score) —
per SKILL.md's "Recall results carry their own honesty signal." The fixture stub returns
`trust=unreviewed`, `health=degraded`; the response should surface that, not just "found a
match."

The window is 60 characters, not 20: the stub's own refusal line (`REFUSED: trust:
fixture-artifact@1.0.0 is unreviewed for this digest`) has 28 characters between the two words,
and the first real run (2026-09-15) graded a correct with-plugin answer as a miss because of it.
