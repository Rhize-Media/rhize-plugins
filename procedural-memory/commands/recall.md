---
description: Find the closest-matching proven artifact in the procedural-memory registry for a task, ranked by semantic similarity plus trust/health signals
argument-hint: <task description>
allowed-tools: Bash
---

Recall the closest-matching registry artifact(s) for: $ARGUMENTS

Run:

    ${CLAUDE_PLUGIN_ROOT}/scripts/rhize-skill-launcher.sh recall "$ARGUMENTS"

Report each hit exactly as the CLI prints it — name, similarity score, trust tier, health,
last-verified date, success rate, run count — do not paraphrase or drop provenance signals.

If the top hit's `trust` is `unreviewed` or `health` isn't `ok`, say so plainly before
suggesting `/procedural-memory:run` next. `run`'s own trust/health gates will refuse an unsafe
execution regardless, but naming the reason up front saves a round trip. If nothing scores as a
real match, say so — never treat a low-similarity hit as a recommendation.
