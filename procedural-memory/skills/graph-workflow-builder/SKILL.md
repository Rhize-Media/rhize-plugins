---
name: graph-workflow-builder
description: >-
  Build or revise a reusable execution graph with explicit completion checks, bounded dynamic
  task expansion, and worktree-isolated parallel workers. Use for requests to design a graph
  workflow, convert a multi-step goal into an executable workflow, or repair its dependencies
  and done criteria. Builds and validates by default; runs only when requested. Does not build
  knowledge graphs over notes or replace a simple one-step command.
metadata:
  rhize:
    topics: [automation, workflow-patterns]
    stacks: []
    router:
      phrases: [build graph workflow, completion gates]
---

# Graph workflow builder

Turn the user's goal into the smallest graph that can prove it finished. Use the versioned
`rhize-workflow-v1` contract; existing serial graphs retain their original runner.

1. **Freeze the contract.** State the desired outcome, deliverables, scope, authority, inputs,
   and named acceptance criteria. Map each criterion to a gate, evidence source, and final
   integrated check. Ask only for information that changes correctness or permission.
   Objective checks take priority; subjective criteria need an explicit rubric with evidence
   anchors and pass/revise/hold thresholds. Missing evidence stays incomplete.
2. **Reuse before composing.** Use the self-relative launcher below for one bounded metadata
   recall. Follow the host's existing workflow-selection context/consult/decision lifecycle
   where available; record reuse, adapt, no_match, or unavailable honestly. The decision layer's
   authoritative policy remains in charge: shadow recommendations never promote themselves.
3. **Design the graph.** Read [the authoring contract](references/contract.md). Prefer one
   worker and a checked finish for a small goal. Add independent workers when the work and
   verification justify their setup/context/integration overhead. Reserve coordinator capacity.
   Name data dependencies, shared resources, per-template write territories, gates, attempt
   limits, deadlines, and the integration owner. Every required node must feed the finish.
4. **Expand only what cannot be known yet.** A checked `expand` node may instantiate approved
   templates with bounded inputs and sibling dependencies. It cannot generate executable
   code, new tools, permissions, checkers, model routes, or limits. Validate the entire proposal
   atomically before admitting children. Its parent is a completion barrier until all children
   and the group check pass. Read the expansion rules in the contract.
5. **Build and validate.** Write the candidate graph, minimal prompts, deterministic evidence
   checkers, and known-good/must-reject fixtures. Run `graph validate <candidate>`; this does
   not stage or execute. Deliver the graph, criterion-to-gate map, validation result, intended
   model routing, and unresolved limitations. A build-only request stops here.
6. **Run only when requested.** Read [execution and recovery](references/execution.md).
   Probe the selected CLI's command support. Use normal stage, promote, verification, health,
   and digest-bound approval gates when their separate intent exists. Never add
   `--approve-unreviewed`, manufacture approval/health, or mutate an existing frozen artifact.
   Changed reusable behavior needs a version successor and fresh normal admission.

All CLI calls use `bash scripts/graph-workflow.sh <args>` from this skill. It delegates to
the plugin's portable launcher and refuses an older runtime without this workflow surface.
Example: `bash scripts/graph-workflow.sh recall "<goal>" --json`.
Check actual `--help` before composing flags.

Execution uses subscription-native host agents, including rubric judges, graders, repairs,
and child threads. No metered API fallback. Pin the admitted model per template from the
host's available subscription models; use a capable planner/final reviewer and a cheaper
qualified executor for bounded tasks. Escalation requires the same authority and a newly
admitted route; record the model reported by the host and whether backend identity is exposed.
Unknown token usage is null. Do not equate subscription use with zero resource cost.

Every parallel thread gets its own actual Git worktree at the admitted base. Verify the root
and HEAD before tools run; a directory instruction alone is not isolation. For non-Git tasks,
use a dedicated local artifact repository. Worktrees share Git metadata and external services:
use host permissions and resource locks, and serialize external effects under existing approval
rules. Workers may not delegate beyond the admitted budget or publish/merge on their own.

A node is done only after its checker passes against its actual output; the goal is done only
after integration and the final acceptance gate pass. Failed required work blocks dependents;
useful independent work may finish within budget. Never hide failed children or call a
budget/timeout/quota stop completed. Use [evaluation and telemetry](references/evaluation.md)
for source-bound trials and [research notes](references/sources.md) for the design rationale.
