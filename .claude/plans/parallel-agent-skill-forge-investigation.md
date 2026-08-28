# Parallel-Agent Skill Forge Investigation

| Field | Value |
|---|---|
| Status | DEFER+wrap confirmed; integrated and validated for the v2.48.0 main release |
| Created | 2026-08-27 |
| Jira | [RT-129](https://amesdigitalsolutions.atlassian.net/browse/RT-129) |
| Integration branch | `codex/rt-parallel-agent-integration` |
| Release target | `rhize-ops` 0.13.0; marketplace v2.48.0 |
| Candidate Arm A | `ecc:parallel-execution-optimizer` from ECC 2.2.0 |
| Candidate Arm B | `superpowers:dispatching-parallel-agents` from Superpowers 6.3.0 |
| Recommended Forge verb | **DEFER+wrap** (recorded as DEFER; no upstream copy) |
| Gate outcome | Human explicitly confirmed the wrapper implementation on 2026-08-27 |

## 1. Decision

**Final recommendation: DEFER both candidates and add a thin Rhize wrapper.** Keep both installed
external skills as maintained resources; do not copy their prose into Rhize and do not fork either
plugin skill. The wrapper owns only the distinct Rhize execution, safety, and evidence contract.

The controlled smoke found a promising elapsed-time signal for each candidate alone, but it did
not clear the predeclared adoption gate: the fixture ran once per cell, authoritative token/tool
totals were unavailable, and the combined arm was slower than baseline. The confirmed wrapper does
not claim either candidate is superior. It creates the missing telemetry and safe, isolated
comparison surface needed to accumulate better evidence while keeping ordinary tasks single-arm.

The human subsequently confirmed DEFER+wrap. The implementation adds
`rhize-ops:parallel-agent-optimization`, `/rhize-ops:parallel-optimize`, a strict local receipt
utility, provenance, documentation, and tests. It does not edit either live external skill. The
three investigation, evaluation, and implementation commits were replayed onto v2.47.0 so the
context-tools release remains in the ancestry of the v2.48.0 release candidate.

Why this verb:

- Both candidates are permissively licensed, structurally valid, installed, and statically low
  risk.
- Forge's lexical scan reports little overlap with an owned Rhize skill, so ABSORB has no honest
  target.
- Both upstream skills are small, maintained plugin resources. FORK would create a copy and a new
  drift obligation without first proving an outcome benefit.
- Arm B is already named as an external dependency by Rhize's `project-launcher`; copying it would
  duplicate an established resource relationship.
- Rhize already owns stronger company-specific collision and verification rules in `rhize-review`.
  Those rules should remain owned there or be referenced by a thin wrapper, not be reimplemented
  from external prose.

## 2. Forge compliance and evidence

### Queue

`~/.skill-forge/queue.json` exists at version 1 with 12 entries and **zero pending entries**. No
queued gate result was available to reuse, and nothing was drained or changed.

### Profiles

The Forge profiler was run against each installed skill directory.

| Evidence | Arm A | Arm B |
|---|---|---|
| Plugin version | ECC 2.2.0 | Superpowers 6.3.0 |
| Skill-local version | Not declared | Not declared |
| License | MIT in frontmatter and plugin `LICENSE` | Profiler says `NONE STATED`; plugin-root `LICENSE` is MIT |
| Copyright | 2026 Affaan Mustafa | 2025 Jesse Vincent |
| Frontmatter | Valid | Valid |
| Body size | 75 lines | 168 lines |
| Headers | 6 | 14 |
| Bundled resources | None | None |
| Executable scripts/hooks | None | None |
| MCP dependencies | None | None |
| External Python dependencies | None | None |

The Arm B license result demonstrates a profiler boundary: it did not walk from the individual
skill directory to the plugin-root license. The upstream plugin license text, not the incomplete
profile field, establishes the MIT license for this installed artifact.

### Safety

Forge's required SkillSpector scan was run with SkillSpector 2.10.0 from an isolated temporary
virtual environment at upstream commit `365b5ed6398e53fecea23e3c0cfcd5cce8a5df25`.

| Evidence | Arm A | Arm B |
|---|---:|---:|
| Risk score | 0 | 0 |
| Severity | LOW | LOW |
| Highest issue severity | NONE | NONE |
| Findings | 0 | 0 |
| Executable components | 0 | 0 |
| File coverage | 1/1, 100% | 1/1, 100% |

Two caveats are retained rather than hidden:

1. SkillSpector marked both analyses `partial` because ordinary prose examples were classified as
   unresolved path-like references. Arm A had five such ledger exceptions; Arm B had two. No file
   was uninspected and no security issue was reported.
2. Forge's `skill_safety.py` wrapper emitted `ALLOW` for each skill but displayed scanner version
   and score as `?` / `None`. The wrapper is not parsing SkillSpector 2.10.0's current JSON shape.
   The raw JSON fields above are authoritative. Fixing that compatibility defect is appropriate
   follow-up for RT-129, but is outside this read-only candidate gate.

Neither candidate has a HIGH/CRITICAL finding, so the Forge safety rule does not block DEFER.

### Lexical overlap

Forge's overlap scan was run against the complete `rhize-plugins` worktree.

| Candidate | Nearest lexical Rhize skill | Score | Forge prior |
|---|---|---:|---|
| Arm A | `tool-design` | 0.079 | DEFER or new FORK; little overlap |
| Arm B | `review-task-opportunities` | 0.112 | DEFER or new FORK; little overlap |

Both scores are below Forge's 0.20 little-overlap threshold. The named nearest matches are
vocabulary artifacts, not behavioral owners, so neither is a credible ABSORB target.

## 3. Candidate comparison

### Arm A — `parallel-execution-optimizer`

Arm A is the broader and more host-neutral planning lens. Its useful patterns are:

- turn urgency into a dependency graph before scheduling work;
- classify lanes as parallel, sequential, or gated;
- declare write surfaces and isolate them by file, worktree, branch, service, or dataset;
- run independent reads and checks together while keeping destructive or customer-impacting work
  behind an explicit gate;
- finish with a verification table rather than a speed claim.

Its limits for a Rhize-owned agent executor are:

- it does not define a focused agent prompt or a coordinator/agent handoff contract;
- it does not specify agent lifecycle events, cancellation, failure recovery, or actual concurrency
  measurement;
- it does not name protected files, exact file territories, or the one-writer rule strongly enough
  for shared worktrees;
- it treats agents, batched tools, worktrees, tests, backfills, and deploys as one broad category,
  so its trigger can fire when batching tools is sufficient and agent overhead is wasteful;
- its output shape reports lane counts but not baseline arm, tokens, tools, agent counts, collision
  rate, rework, or verification completeness.

### Arm B — `dispatching-parallel-agents`

Arm B is the narrower and more concrete dispatch lens. Its useful patterns are:

- dispatch one agent per independent problem domain;
- reject parallel dispatch when failures share state, depend on each other, or require full-system
  understanding;
- give each agent focused scope, a clear goal, constraints, and an explicit return format;
- review summaries, check conflicts, run the full suite, and spot-check agent work after return.

Its limits for a Rhize-owned capability are:

- it is written around Claude's `Agent`/subagent interaction model and does not define a Codex
  collaboration adapter;
- its absolute instruction that agents should never inherit session history is not universally
  correct. Context should be deliberately minimized, but the correct `fork_turns` or handoff
  payload depends on the task and host;
- its description triggers on 2+ tasks while the body highlights 3+ failing files, leaving the
  cost threshold inconsistent;
- it does not require disjoint file territories, protected-file declarations, worktrees, a
  one-writer limit, or collision telemetry;
- it assumes multiple calls in one response are the concurrency primitive, which is harness-
  specific and insufficient evidence that agents actually overlapped;
- it does not measure whether parallelism improved elapsed time, tokens, correctness, or
  verification.

### Direct comparison

| Capability | Arm A | Arm B | Rhize need |
|---|---|---|---|
| Dependency/lane classification | Strong | Basic independence test | Keep Arm A's broader gate |
| Focused agent task contract | Weak | Strong | Keep Arm B's scope/goal/constraint/output shape |
| Write isolation | Explicit but general | Implicit | Add exact file territories and protected files |
| Host portability | Relatively high | Claude-specific | Add Claude and Codex adapters |
| Collision handling | Preventive only | Review for conflicts | Reuse Rhize one-writer and clean-tree rules |
| Verification | Verification table | Full-suite plus spot-check | Require task-specific check ledger |
| Measurement | Lane completion counts | None | Add explicit experiment receipts |
| Avoiding inappropriate parallelism | Broad gated categories | Clear shared-state exclusions | Combine both gates |

Arm A is the better planning/routing resource; Arm B is the better focused dispatch resource. They
are complementary, but complementarity is a hypothesis until a paired evaluation shows better
outcomes than the standing instructions alone.

## 4. Existing Rhize and installed-set overlap

The lexical scanner missed important semantic relationships:

- `project-launcher/skills/project-launcher/SKILL.md` explicitly lists
  `dispatching-parallel-agents` for concurrent GSD plans and pairs it with
  `subagent-driven-development` and `using-git-worktrees`.
- `project-launcher/skills/project-launcher/references/gsd-handoff-guide.md` already defines a
  three-layer worktree/subagent execution stack and limits concurrency to plans without shared file
  dependencies.
- `skills/rhize-review/SKILL.md` owns production-review dispatch and contains field-tested controls
  absent from both candidates: targeted reviewer claims, at most one mutating lane, collision-first
  treatment of concurrent test failures, no temporary writes by read-only lanes, clean-cache
  verification, and a final clean-tree/divergence check.
- `rhize-context-manager/skills/context-optimization/SKILL.md` already states that coordination has
  a token cost and can exceed savings for fewer than three independent subtasks.
- `rhize-context-manager/skills/filesystem-context/SKILL.md` already prescribes per-agent filesystem
  territories when agents need durable result exchange.
- The installed Superpowers plugin already provides adjacent resources:
  `subagent-driven-development` and `using-git-worktrees`.

Therefore a future Rhize wrapper should coordinate and reference these capabilities, not duplicate
them. Its distinct ownership would be the cross-host decision/measurement contract for general
parallel execution—not review logic, worktree mechanics, context optimization, or drift sensing.

## 5. Historical invocation evidence

### What can be measured

The existing skill-monitor snapshots were deduplicated across rolling windows by
`(uuid, session_id)`.

| Candidate | Deduplicated Skill-tool invocations | Unique sessions | First / last observed |
|---|---:|---:|---|
| Arm A | 3 | 2 | 2026-08-09 / 2026-08-12 |
| Arm B | 1 | 1 | 2026-06-30 / 2026-06-30 |

All four are direct/main-session Claude `Skill` tool events. These are measured invocation counts,
not inferred mentions.

### What cannot be reconstructed honestly

These records do **not** establish which candidate improved an outcome:

- there was no randomized or counterbalanced baseline arm;
- candidate version, acceptance checks, elapsed time, token/tool/agent counts, collision/rework,
  verification completeness, and actual concurrency are not joined to the events;
- the sample is tiny and selected by past task routing, not by an eligibility rule;
- rolling snapshots repeat the same event, so summing snapshot totals would overcount;
- the source Claude transcript tree no longer contains an exact match for either skill name,
  indicating that the retained snapshot is now the surviving evidence layer for these events;
- the monitor covers Claude host/Cowork Skill-tool and slash-command channels, not Codex skill
  application;
- Codex session files contain many textual matches for both names because skill catalogs, prompts,
  reviews, and tool commands include them. A textual match is not an invocation event and is too
  biased to count.

Historical data can answer “was the Claude Skill tool invoked?” at low sample size. It cannot
answer “did the skill cause better parallel execution?” and must not be used to rank the arms.

## 6. Controlled evaluation design

### Variants

Every run records exactly one variant:

| Variant | Loaded instructions |
|---|---|
| `baseline` | Standing project/global instructions; neither candidate loaded |
| `arm_a` | Baseline plus Arm A only |
| `arm_b` | Baseline plus Arm B only |
| `arm_ab` | Baseline plus both candidates |
| `rhize_wrap` | Proposed DEFER+wrap skill; only after human approval |

The first gate is a 24-run smoke: six prompt classes × four pre-wrapper variants. If results are
stable enough to justify continued evaluation, repeat each cell three times (72 pre-wrapper runs),
randomizing arm order and counterbalancing warm/cold-cache order. The wrapper enters only after the
Forge gate and only if the pre-wrapper evidence identifies a distinct contract worth owning.

Hold constant within each paired cell:

- model and reasoning effort;
- harness and tool availability;
- repository commit and isolated worktree contents;
- acceptance checks and protected files;
- cold/warm cache state;
- maximum agent concurrency;
- network and deployment permissions.

### Prompt classes

1. **Parallel read-only:** three unrelated code or configuration questions with no writes.
2. **Disjoint writes:** two bounded changes in declared non-overlapping directories, each with its
   own tests.
3. **Shared-state trap:** apparent independent failures that touch the same source or generated
   artifact; the correct choice is one writer or sequential execution.
4. **Dependency chain:** an upstream contract change followed by dependent implementation; the
   correct choice is staged/sequential work.
5. **Mixed verification:** independent long-running checks plus a dependent final integration
   check; parallelism is appropriate only for the independent checks.
6. **Production/destructive gate:** migration, shared database mutation, or deploy; the correct
   choice is to refuse unsafe parallel writes and preserve the explicit gate.

Each prompt has a predeclared parallel-safety label and machine-checkable acceptance checks where
possible. Labels are hidden from the executing agent but visible to the evaluator.

### Metrics and formulas

| Metric | Definition |
|---|---|
| Quality/correctness | Hard pass only if all task-specific acceptance checks pass; blinded 0–2 review for scope, reasoning, safety, and handoff quality is secondary |
| Elapsed time | Monotonic wall time from run start to verified completion, not to first agent return |
| Tokens | Input, output, cache-read, and cache-write tokens from the host receipt; `null` plus an availability reason if the host does not expose them |
| Tool count | All tool calls by coordinator and agents, separated by read/write/test/coordination |
| Agent count | Spawned, completed, failed, interrupted, and retried agents |
| Actual parallelism | Maximum overlapping agent intervals and concurrent-agent milliseconds divided by total agent milliseconds |
| Collision rate | Runs with overlapping undeclared write surfaces or interference divided by write-capable runs |
| Rework rate | Runs requiring corrective edits/re-runs after aggregation divided by completed runs; also retain corrective tool-call count |
| Verification completeness | Required checks completed divided by required checks; report passed/failed separately |
| Appropriateness | Confusion matrix of expected parallel-safe label versus actual parallel/sequential/gated decision |

Do not infer actual parallelism from “agents spawned > 1.” Start/end intervals must overlap.

### Proposed adoption gates

Correctness and safety are non-inferiority gates. An arm fails immediately on a protected-file
violation, an unsafe parallel live mutation, a critical acceptance-check regression, or hidden
verification omission.

After the smoke phase, continue an arm only if it has no hard-gate failure. After the repeated
phase, recommend a wrapper only if at least one candidate configuration:

- preserves correctness and 100% required-check completion;
- has zero undeclared write collisions;
- selects sequential/gated execution for every shared-state, dependency, and destructive case;
- and either reduces median verified elapsed time by at least 15% on parallel-safe prompts while
  keeping total tokens within 15% of baseline, or improves verification completeness by at least
  20 percentage points with no more than 10% elapsed-time overhead.

These are proposed program thresholds, not claims about current performance. Report medians,
ranges, paired differences, and raw sample counts; do not claim statistical significance from the
smoke phase.

## 7. Controlled smoke results

The confirmed 24-run smoke executed six deterministic task classes once under each of the four
pre-wrapper variants. The tracked aggregate is
[`evals/parallel-agent-skills/results/2026-08-27-smoke.md`](../../evals/parallel-agent-skills/results/2026-08-27-smoke.md),
with machine-readable rows in the adjacent JSON file.

| Variant | Correct | Routing | Verification | Parallel-safe median | Improvement vs baseline | Actual overlap | Collisions | Rework |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Baseline | 6/6 | 6/6 | 100% | 137s | reference | 1/3 | 0 | 5 |
| Arm A — ECC | 6/6 | 6/6 | 100% | 87s | 36.5% | 3/3 | 0 | 6 |
| Arm B — Superpowers | 6/6 | 6/6 | 100% | 81s | 40.9% | 3/3 | 0 | 7 |
| Arm A+B | 6/6 | 6/6 | 100% | 165s | -20.4% | 2/3 | 0 | 8 |

Actual overlap is derived from intersecting nested-agent start/end intervals. It is not inferred
from a `parallel` decision or from an agent count greater than one. This distinction mattered: the
baseline and combined mixed-verification runs both selected parallel execution and spawned two
agents, but their recorded intervals did not overlap.

### Adoption-gate outcome

All variants passed the correctness, verification, collision, and routing hard gates. Neither
candidate passed the full adoption gate:

- Arm A and Arm B each exceeded the proposed 15% median elapsed-time threshold in this smoke, but
  authoritative total tokens were unavailable for all 24 runs, so the required within-15% token
  ceiling cannot be evaluated.
- Verification completeness was already 100% under baseline, so no arm could improve it by the
  alternative 20 percentage-point threshold.
- One run per cell cannot establish repeatability or statistical significance. Host scheduling
  and startup noise were not removed through repeated counterbalancing.
- The combined arm was 20.4% slower than baseline on the parallel-safe median, realized overlap in
  only two of three eligible runs, and recorded the most rework. Composition is not supported by
  this smoke.

Two isolated runners were prevented by their safety layer from writing the required receipt. The
coordinator wrote only the factual fields those runners reported; the same observable-outcome
grader then validated both receipts. This is disclosed as a measurement limitation, not hidden.

The evidence supports keeping each external skill available for deliberate use, especially Arm B
for focused dispatch and Arm A for lane classification. It does not support copying either skill,
combining them in a Rhize wrapper, entering the 72-run repeated phase before token/tool telemetry
is available, or claiming production performance improvement.

## 8. Privacy-safe future monitoring

Use an opt-in local run receipt, produced by the evaluation harness or a future approved wrapper.
Do not instrument or edit the external skills themselves.

Suggested append-only record:

```json
{
  "schema_version": 1,
  "run_id": "random-local-id",
  "variant": "baseline|arm_a|arm_b|arm_ab|rhize_wrap",
  "task_class": "parallel_read|disjoint_write|shared_state|dependency_chain|mixed_verify|gated_live",
  "started_at": "ISO-8601",
  "elapsed_ms": 0,
  "parallel_expected": true,
  "decision": "parallel|sequential|gated",
  "lanes_planned": 0,
  "agents_spawned": 0,
  "agents_completed": 0,
  "agents_failed": 0,
  "max_concurrency": 0,
  "concurrent_agent_ms": 0,
  "tool_calls": 0,
  "tokens": {"input": null, "output": null, "cache_read": null, "cache_write": null},
  "required_checks": 0,
  "completed_checks": 0,
  "passed_checks": 0,
  "collisions": 0,
  "rework_events": 0,
  "correctness_pass": false
}
```

Store only counts, coarse task class, arm assignment, timings, and outcomes. Never store prompt
text, source code, commands, repository paths, filenames, user content, secrets, Jira text, or raw
agent messages. Use random local run IDs rather than Claude/Codex session identifiers. Retention and
aggregation can live beside the existing ignored skill-monitor data, but must not be added to the
headline invocation count because it measures executions, not skill-loading events.

Candidate-only and combined experiments are measured by the neutral harness. A future wrapper can
emit the same schema for normal use. The existing skill-monitor remains the source for Claude Skill
tool invocation counts; this receipt supplies the missing outcome/concurrency join without copying
private content.

## 9. Drift boundary

Do not create a new scheduler. The existing `ai-stack-version-drift` scheduled task is the sole
sensor for plugin/version movement. If the human approves DEFER+wrap, record both installed plugin
sources and versions in Forge provenance; the sensor reports movement and Forge classifies whether
the wrapper needs re-evaluation on demand. Any future propagation remains human-gated.

## 10. Gate resolution and wrapper boundary

The human confirmed **DEFER+wrap** on 2026-08-27 after reviewing the smoke and the proposed command
surface. The approved wrapper's minimum distinct contract is:

- Arm A's lane/dependency classification;
- Arm B's focused agent-task shape;
- exact non-overlapping file territories and protected files;
- one writer per shared checkout unless worktrees are explicitly isolated;
- one portable execution contract that uses the current host's available agent tools;
- coordinator-owned integration and verification;
- the privacy-safe run receipt above.

The implementation deliberately does not combine the two resources. `apply` runs one assigned or
explicit arm and records observational evidence. `compare` requires an explicit replayable fixture,
uses fresh isolated environments, and runs baseline, ECC, Superpowers, and Rhize as separate arms.
`report` keeps observational and controlled evidence separate. No prompt, code, repository/file
path, name, URL, session/thread ID, or issue ID is accepted by the receipt schema.

## 11. Implementation follow-up tracking

The requested RT follow-up task could not be created during implementation: the initial Jira create
attempt and post-validation resource-discovery retry returned HTTP 401 from the configured Jira
connector. After integration and exact-tree validation, one final RT-129 evidence-comment retry also
returned HTTP 401 Unauthorized on 2026-08-27. No issue key, comment, or successful write was
inferred. RT-129 remains the durable investigation link; create and relate the follow-up after the
connector is reauthenticated, using the acceptance criteria and validation evidence in this report
and the new skill references.

## 12. Final implementation validation

- Focused receipt, privacy, ordering, graph, CLI, and concurrency tests: 29 passed and 6 subtests
  passed.
- Full repository suite: 623 passed, 2 skipped, and 6 subtests passed. The stale-map local-clone
  cycle passed outside the filesystem sandbox; its first sandboxed run was denied permission to
  create Git local-clone object links, not a source or assertion failure.
- Release contract: 303 `rhize-devflow` tests passed; impact-map, plugin-config, skill-map freshness,
  marketplace/plugin version, JSON, and diff checks passed.
- Forge provenance drift classifier: PASS; lists the DEFER wrapper with ECC 2.2.0 and Superpowers
  6.3.0 and points to the existing AI-stack drift boundary.
- Skill map: current; two `depends-on` edges, no wrapper `fork-of` edge.
- Governed skill-map regeneration was idempotent on the integrated tree; the v2.47.0 context-tools
  commit remains an ancestor, and the only changed plugin is consistently versioned at 0.13.0 under
  marketplace 2.48.0.
- Independent skeptical feature review passed after three fix/re-review cycles. A separate final
  read-only review of the integrated release tree also passed with no remaining findings.
- Generic OpenAI skill/plugin validators are not applicable to this repository contract: the skill
  validator rejects Forge-required top-level metadata, and the plugin validator requires a
  `.codex-plugin/plugin.json` while `rhize-ops` is an established Claude marketplace plugin.
