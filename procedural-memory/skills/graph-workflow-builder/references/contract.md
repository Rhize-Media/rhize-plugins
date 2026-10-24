# Authoring and dynamic expansion

Use a fresh candidate directory with `graph.provenance.json`, `prompts/`, `edges/`,
and `fixtures/`. Use the installed runtime's `graph validate` as schema authority.
The runtime contract is documented in procedural-memory's `docs/graph-workflow-v1.md`.

Required top-level fields:

| Field | Contract |
| --- | --- |
| kind, workflow_schema | `graph`, `rhize-workflow-v1` |
| name, version, description | Slug, semantic version, concrete purpose |
| objective | Nonempty `goal` and `done_signal` |
| templates | Approved immutable agent, expand, and join contracts |
| nodes | Initial required task instances |
| finish | ID of a final checked join; every node is its ancestor |
| limits | Positive `concurrency` (coordinator included), `max_nodes`, `max_depth`, `max_attempts`, `max_seconds` |
| resources | Named shared-resource capacities; workers declare what they occupy |
| gates | Named deterministic checkers plus known-good and must-reject fixtures |
| env | Standard provenance; include `model_map` in params |
| verification | Standard graph scope/assertions; not a claim of task completion |

Each template has exactly `type, purpose, writes, resources, gate, max_attempts,
timeout_seconds`. Agent/expand templates also have `prompt_ref` under prompts/.
Expand templates additionally have `child_templates, allow_empty, join_gate`; they and joins
have no writes. A checker is `edges/name.py`; every gate has exactly `id, class:
deterministic, checker, must_reject_fixture, known_good_fixture`. Fixtures live under fixtures/.
Checkers receive one JSON file and return 0 for accepted, 1 for rejected; crashes are failures.
During execution the packet includes objective, task, inputs, output, dependencies, repository,
and phase. Check real files in that repository, not just an agent's `ok: true` assertion.
A subjective review is an ordinary native agent node; its evidence packet is checked
deterministically against the frozen rubric's required fields and threshold. A rubric score
alone is insufficient when the criterion requires verifiable evidence.

Each initial node has exactly `id, template, task, depends_on, inputs`. Dependencies are
required completion barriers. Use compact inputs and artifact references rather than complete
conversation histories. Prompts should contain the global goal, this lane's purpose, bounded
input facts, allowed output territory, output contract, evidence/check instructions, and stop
conditions. Do not request raw chain-of-thought or speculative subprojects.

## Dynamic nodes in V1

An expand worker returns only this shape:

```json
{"children":[
  {"key":"source-a","template":"research","task":"Check source A","depends_on":[],"inputs":{"source":"A"}},
  {"key":"synthesis","template":"synthesize","task":"Combine evidence","depends_on":["source-a"],"inputs":{}}
]}
```

The coordinator checks approved templates, all fields, unique stable keys, resolvable sibling
dependencies, acyclicity, input shape, remaining node/attempt budget, and maximum depth before
one atomic state commit. Child IDs are parent/key. All children are required and belong to the
sealed parent join, including recursively expanded groups. Empty expansion is allowed only
when the parent contract explicitly permits it and its join check passes.

Use expansion for discovered sources, test failures, or reconciliation groups whose membership
is unknown initially. Prefer a fixed graph when the members are already known. Templates must
cover the possible tasks before admission; a genuinely new capability requires a new graph
version. Expansion is append-only within a pending group: never revise completed nodes, rewire
in-flight contracts, weaken acceptance criteria, or expand after its proposal is sealed.
Unrelated in-flight results remain valid because their attempt and request digests stay bound.

A native dynamic-workflow feature can execute the requests only if its retries, worktree roots,
waiting, cancellation, selected models, and concurrency meet this contract. Native replay may
rerun completed agents and exhausted agents may return null. Null required results fail.
Count native internal retries too; if the host does not expose or bound them, do not claim that
its advertised size/turn setting is an enforced Rhize attempt/token cap.
