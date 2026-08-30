---
description: Required entry point whenever parallel agents are discussed, planned, reviewed, or employed; assess first, then use the self-contained Rhize strategy
argument-hint: "[assess <question or task> | apply <task> | compare <replayable task or fixture> | report [observational|controlled|all] | audit-pending]"
---
<!-- canonical: rhize-ops:parallel-agent-optimization -->

# Parallel Optimize

Invoke the `rhize-ops:parallel-agent-optimization` skill (Skill tool) for this request. Pass
`$ARGUMENTS` unchanged as the mode, task, or report scope. Follow the skill's dependency graph,
isolation, one-writer, verification, receipt-lifecycle, and evidence-separation
contracts without reimplementing them here.

This is the required pre-dispatch entry point whenever parallel or multi-agent work is mentioned,
discussed, proposed, planned, reviewed, or employed. Use `assess` for discussion-only requests; it
does not dispatch agents or write receipts. For execution, prefer parallel agents when the skill's
independence, isolation, and benefit gates pass, and invoke the skill before the first agent spawn.

This command does not grant authority to duplicate live tasks, mutate production or shared external
state, load vendor routing skills, or broaden commit/push/merge/deploy authority.

Canonical runtime contract: `rhize-ops:parallel-agent-optimization`.
