---
name: learning-curation
description: "This skill should be used when deciding whether a session learning, correction, or rule deserves persistent storage — and where to put it so it actually fires: always-loaded config, a reference skill, a hook, or nowhere. Covers drop tests, redundancy and contradiction resolution, the retrieval-cue placement test, and rule phrasing that survives contact with a future session. Route memory *architecture* (vector stores, knowledge graphs, temporal validity) to memory-systems, context-consumption audits to context-budget, and session handoff summaries to context-compression."
metadata:
  rhize:
    topics: [learning-curation, context-engineering]
    stacks: []

---

# Learning Curation: Save What Fires, Where It Fires

A learning is worth persisting only if it changes behavior at the moment the failure would otherwise recur. Most saved learnings fail in one of three ways: stored where nothing will ever surface them, written so the reader doesn't recognize the moment they apply, or buried in an always-loaded pile so large that nothing in it is salient. This skill is the procedure for avoiding all three — and for refusing to save at all when that's the right call.

This is the *editorial* layer, not the storage layer. It governs what a human- or agent-authored rule store should contain. For how persistence is implemented, see `memory-systems`.

## When to Activate

Activate this skill when:

- Extracting a lesson from a session (`/learn`, `/learn-eval`, retrospectives)
- Deciding between always-loaded config (CLAUDE.md / AGENTS.md), a skill file, a hook, or in-repo docs
- The same correction has come up more than once
- A rule store, skill library, or CLAUDE.md has grown heavy and needs pruning
- A new rule appears to contradict something already saved

## Gate 1: Should this be saved anywhere?

Drop the learning if any of these hold:

- **It won't recur.** The cause was a one-off — a since-fixed bug, a changed environment, a task ending with this project phase.
- **A mechanism already enforces it** — type system, test, lint rule, CI check, hook. And if a mechanism *could* enforce it cheaply, **add the mechanism instead of the memo.** Prose asks the next session to remember; a failing check makes forgetting impossible and costs zero context.
- **The codebase records it.** Config values, file locations, anything grep finds in seconds. Save a pointer if the lookup is genuinely non-obvious; never a copy — copies rot silently.
- **It restates docs or framework defaults** the agent already gets right unaided.
- **It's session-local context dressed as standing intent** ("user wanted terse output today").

Rough threshold: expected recurrence cost (how often × how expensive a miss) must clearly exceed the standing tax of the entry. The tax differs by destination — see Gate 3. The bar for a reference store is low; the bar for always-loaded context is high.

## Gate 2: Search before drafting

Grep the skill directories, memory indexes, and always-loaded config by keyword **before** writing anything. Decisions made on evidence beforehand beat decisions defended afterward. Four outcomes:

- **Duplicate** → drop, or strengthen the existing entry (add the new scar as a second receipt).
- **Same rule, weaker form** → amend in place; don't add a sibling.
- **Adjacent but distinct** → keep separate, cross-reference. The test: *would one trigger correctly surface both?* If the triggering moments differ ("about to hand the user a manual checklist" vs. "about to declare a setup step impossible"), collapsing them buries the new rule under the wrong trigger. Adjacency is not overlap.
- **Contradicts an existing rule** → resolve it now, in the files. Rewrite or delete the old rule in the same edit. Two live rules that disagree are worse than either alone, because the conflict gets re-litigated by every future session. If the stale belief is likely to be re-derived from stale evidence, leave a visible correction ("a previous note claimed X; verified wrong on DATE") rather than a silent deletion.

## Generalize accumulated corrections

When two or more saved corrections share the same *shape* — "X actually exists, don't claim otherwise"; "Y actually is provisioned"; "Z actually can be done programmatically" — the store is missing its most important entry: the general rule they are all instances of.

Write the cause as its own rule, and explicitly reframe the existing entries as symptoms of it ("the entries about A, B, C are instances of this"). Otherwise the store accumulates a fourth, fifth, sixth instance forever, and each one only ever prevents its own literal recurrence.

## Gate 3: Placement — the cue test

Retrieval requires a cue. Reference material gets consulted when the failure moment emits a searchable signal — a task keyword, a tool name, a distinctive error string. But some failures emit nothing: the session has already reached a wrong conclusion, and nothing about a wrong conclusion says "go check memory."

Ask: **at the moment this failure occurs, what is actually in context, and does it cue a lookup?**

| At the failure moment… | Placement |
|---|---|
| The task type is recognizable in advance (deploying, migrating, releasing) | Reference skill / topic doc, triggers matching the task |
| A distinctive error message or symptom appears | Reference entry keyed to that string — agents search on errors |
| A mechanical checkpoint exists (commit, build, edit of file X) | Hook / test / lint. Mechanism beats memory |
| **No cue exists** — silent wrong conclusion, omission, premature stop | Always-loaded context. A reference-only entry cannot fire here |
| Repo-specific and tied to particular code | In-repo doc or comment at the site, so it dies when the code does |
| A lookup fact (IDs, endpoints, where credentials live) | Project facts / memory index, timestamped |

For cueless failures, use the **tripwire + reference** split: two or three enforcement lines in always-loaded context pointing at a full reference file. The tripwire buys firing; the pointer keeps the always-loaded footprint small. Don't put the whole essay in always-loaded, and don't put the tripwire only in reference.

Always-loaded context is taxed on every turn of every future session (audit that cost with `context-budget`). When adding to it, ask what you can remove or merge to pay for the slot. If unsure a cueless rule earns the placement, park it in reference and promote it the first time it demonstrably failed to fire.

## Writing rules that fire

- **Name the failure behavior, not the remedy.** "Look for a CLI first" is a remedy; it reads as advice and gets skimmed. "The failure is stopping at the first surface that says no" names what the reader is doing *right now*, which is what lets a session mid-mistake recognize itself. Write so the guilty reader sees their own behavior.
- **Include the scar.** One or two lines of what it actually cost: what was wrongly concluded, what shipped instead of the feature, the one-line correction that exposed it. A rule with a receipt is obeyed; an abstract rule is agreed with and ignored. Keep vendor specifics as *evidence*, not subject — the rule must survive the vendor changing.
- **Every "do more of X" rule needs a stop condition.** State when to stop, what distinguishes a real finding from a non-finding, and any hard limits. Without these, "be more thorough" degenerates into unbounded digging. Symmetrically, every "never X" rule should say what to do instead.
- **Make claims falsifiable and dated.** "Endpoint returns 500 as of 2026-07-27 — re-verify before relying" survives the endpoint being fixed. "The endpoint is broken" becomes a lie future sessions obey.

## Keeping the store from rotting

- Timestamp any claim about an external system, and note how it was verified.
- Prefer pointers over copies for anything the repo or a dashboard already records.
- Delete rules whose referenced file, tool, or system no longer exists — on sight, not in a someday-cleanup.
- When correcting a rule, rewrite it; don't stack a third correction on two others.
- Periodically, or when always-loaded context feels heavy, run a prune pass: every entry either fired recently, guards a plausible recurrence, or goes.

## Failure modes of this technique itself

- **Over-extraction.** Not every session yields a rule. A store where every session added something converges on a store where nothing is salient — the bloat *causes* the failures it was meant to prevent.
- **Contradiction accretion.** Handled at Gate 2, but it is the most common decay mode: new rules written without reading old ones.
- **Eternalizing the temporary.** A workaround for last month's outage, written undated, becomes permanent policy.
- **Remedy-phrased rules** that never fire because nobody recognizes the moment.
- **Meta-bloat.** Rules about the rule system that no session consults. This should be the only skill of its kind in the store.

## Procedure

1. **Gate 1** — does it clear the drop tests? If a mechanism could enforce it, build the mechanism and stop.
2. **Gate 2** — grep existing stores. Decide drop / amend / distinguish+cross-ref / new. Resolve any contradiction in the same edit.
3. **Check for siblings** — is this the general rule behind existing entries? If so, write the cause and demote the instances to symptoms.
4. **Gate 3** — apply the cue test; choose placement from the table. Cueless → tripwire + reference split.
5. **Draft** — behavior-named, scarred, stop-conditioned, dated.
6. **Pay for the slot** — if adding to always-loaded context, identify what this displaces or why it earns a net-new one.
7. **Verify the write landed** — re-read the edited region, and confirm the file is actually in the load path. An entry in a file nothing includes is a silent no-op.

## Worked example

A session declared a vendor setup step impossible ("no MCP server for it, so nothing can be automated") and shipped a handoff document instead of the feature. The user rejected it in one line: an artifact from that vendor already existed, so something had created it programmatically. It had.

Curation decisions that followed:

- **Gate 1** — recurring, not mechanically enforceable → save.
- **Gate 2** — the store already held four corrections of the same shape, each written as an isolated vendor fact. → write the general rule; reframe the four as symptoms.
- **Gate 3** — the failure is a silent wrong conclusion with no cue. A reference-only skill could not fire. → tripwire in always-loaded config + full technique in a reference skill.
- **Phrasing** — named the behavior ("stopping at the first surface that says no"), embedded the scar, and added stop conditions so it wouldn't license unbounded digging.

## Related skills

- `memory-systems` — how persistence is implemented (graph/vector retrieval, temporal validity, consolidation)
- `context-budget` — measuring what always-loaded rules and skills actually cost
- `context-optimization` — token efficiency once placement is settled
- `strategic-compact` — preserving context across phases within a single session
