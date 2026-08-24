---
name: recall-reports-provenance
type: regex
pattern: 'trust.{0,20}unreviewed'
flags: i
match: contains
target: last_message
---

The agent's response must report the recalled artifact's trust tier (not just its name/score) —
per SKILL.md's "Recall results carry their own honesty signal." The fixture stub returns
`trust=unreviewed`, `health=degraded`; the response should surface that, not just "found a
match."
