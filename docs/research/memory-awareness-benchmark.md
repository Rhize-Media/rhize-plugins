# Memory awareness and measured retrieval implementation plan

Date: 2026-09-06 (environment date). Owner: Rhize context management. Status: first opt-in implementation and local validation complete; live effectiveness and procedural advancement gates remain open.

## Current behavior and evidence

- Evidence: marketplace baseline `e184246a5d325320126b18f6d3906b1d921fc025`, context-manager 0.28.0. `MemoryContextAssembler.assemble` consumes full explicit candidate bodies before ranking. `MemoryStore` owns private packs, TTL, source revision verification, revocation, and purge. `runner.main` owns both hosts' preview/verify CLI. CodeGraph was healthy and current at discovery; source inspection confirms these boundaries.
- Evidence: procedural runtime baseline `64cec3704d9a2ad20b24f73592765c99ba4386ae`; recall can invoke embeddings. Its machine-readable scoped metadata adapter is absent and the assembler deliberately reports it unavailable. Existing digest/health/registry primitives are possible future inputs, not a ready adapter.
- Evidence: Hipocampus 0.5.3 `df88ca19d42a3aba4caeaba4512da46cae7827da` and the supplied article motivated source-bound awareness before full retrieval. Review artifacts are in the session's `hipocampus-review` directory. Skill Forge study `STUDY-0876539964f6cece` passed review validation, with partial inventory and no independent corroboration. No whole upstream skill, hook, CLI, transcript capture, or provider is being installed.
- Evidence: claude-mem already owns Claude episodic capture/index/fetch; Codex native memory already supplies an awareness summary. RTK compresses command output, Headroom compresses transport context, OpenWolf owns per-repository file indexes, CodeGraph owns code relationships, and Obsidian owns canonical semantic material. QMD is optional and unavailable on this session's PATH. Graphiti is not an implemented memory lane.
- Inference: a bounded catalog can help discover useful memories without loading every body. It can also cost more for short documents or duplicate the host's existing summary. No agent-outcome advantage has yet been measured.

## Intended semantic delta

Extend the existing `memory-context` skill with a versioned, explicit metadata catalog and selected expansion. Keep one pack store and one freshness/revocation owner. Catalogs carry small labels/keywords and expected detail digests, plus existing typed source metadata; source IDs and revisions remain bound in envelopes. Expansion requires explicit selected catalog IDs, current source revisions, matching detail digests and unchanged authority/scope metadata. Retrieved labels and bodies remain inert.

Expose a reproducible component comparison and a preregistered live A/B protocol. The first implementation is a usable opt-in preview, not automatic activation. Cost accounting includes the rendered catalog plus selected details and clearly labels byte-based token estimates.

## Invariants and must-not-change boundaries

- Exact tenant/project/task and sensitivity checks precede catalog disclosure. No cross-client catalogs. No provider discovery or transcript scraping.
- Preserve canonical ownership, authority, distinct conflicting claims, TTL, content integrity, source revision invalidation, private modes, and exact-source purge. Duplicate suppression is exact source/revision/digest only; no fuzzy merging of facts.
- Catalog metadata is explicit input, not inferred permission. No recalled text grants instructions, tool execution, user approval, or write-back authority.
- Existing preview/verify/purge/cleanup interfaces remain compatible. Procedural and unsupported host adapters remain unavailable until implemented and separately validated.
- Keep no hooks, default injection, new database, new embedding provider, or secondary transcript archive. No `.env*`, workflow, or billing changes.
- Do not fabricate host/model outcomes from component tests. Missing measurements stay missing. Freeze and record which arm/variant actually ran.

## Current structural touchpoints

| Repository | Symbol or entry | Change | Evidence |
|---|---|---|---|
| rhize-plugins | memory_context/core.py assembler/store | Reuse existing contract through a bounded subclass; avoid changing default behavior | Live source |
| rhize-plugins | memory_context/runner.py and memory-context.sh | Add catalog and expand subcommands | Live CLI |
| rhize-plugins | evals/memory-context | Add adversarial contracts and executable A/B component harness | Existing pytest suite |
| rhize-plugins | memory-context skill, command, README, GUIDE, SOURCES | Document input, use, limitations, ownership, benchmark decision | Live docs |
| procedural-memory | registry, digest, health, recall | Future metadata-only adapter after effectiveness gate | Source inspection; no CodeGraph index |

## Planned additions and deletions

Add `memory_context/awareness.py`, awareness tests, an executable local component benchmark, and `docs/research/memory-awareness-benchmark.md` as the durable plan/result record. Extend the runner and existing documentation. Release version/marketplace/changelog and generated map/setup artifacts use repository scripts only. Delete no existing capability.

## Acceptance tests

1. CLI catalog -> select -> expand -> verify works in an isolated private store; existing preview still works.
2. No denied scope/sensitivity, future/expired source, or unsupported adapter leaks into catalog output. Malicious labels/bodies are inert references.
3. Reject mismatched revision, digest, source identity, request scope/query, trust/authority, provenance, selection IDs, missing selected details, duplicate ambiguous sources, stale/revoked/tampered packs, or unsafe paths. Preserve conflicts. Bound input size/count/selection and combined catalog+detail context cost.
4. Exact duplicate records are suppressed; distinct same-claim facts are retained. Already-present suppression requires exact bindings supplied by the caller, not text similarity.
5. Repeated frozen inputs produce identical packs. Empty/unavailable sources remain distinguishable. Default preview contract tests pass.
6. Component benchmark runs both arms with actual variants, fixed seed/time, varied long/short/sparse/conflicting/scoped/adversarial corpora, measured elapsed time and rendered estimated tokens, plus selection coverage. Report catalog maintenance input bytes and selection method. Oracle selection is explicitly component-only.

## Benchmark protocol and advancement gates

Arm A for component tests is the existing direct-body assembler; Arm B is explicit catalog plus selected verified expansion. No provider calls. Corpus outcomes are synthetic contract evidence, never real task success. Include negative/no-memory and short-document cases so overhead is visible. Save report hashes, seed, exact source revision, actuallyRan, and variants. Use the same context rendering for measurement; differences from the legacy budgeting heuristic are disclosed.

Live evaluation requires Jim's exact incumbent choice (question pending: current Codex, current Claude Code, or separate comparisons for both). Freeze model/version, plugin versions, hooks, memory sources, corpus revision, prompts, enabled compression, host configuration hashes, and budget before capture. Baseline includes existing native/claude-mem awareness. B differs only by the new explicit path. Add no-memory and catalog-only ablations; do not pool hosts/models. Run disjoint development and held-out task sets (at least 30 paired held-out tasks per host, balanced across recall, procedural selection, stale correction, long-session resumption, and no-memory-needed tasks). Randomize arm order with a stored seed; isolate sessions and prevent memory carryover. Grade source-grounded correctness against preregistered rubrics without exposing arm identity.

Record actual arm/variant execution, task correctness, source-selection precision/recall, false memory use, stale/cross-scope leaks, tool calls, retries, latency, uncached/cached/input/output tokens, index build/refresh/invalidation work, and provider cost. Missing billable usage is unavailable, not zero. Reserve/finalize through the existing benchmark receipt workflow only for real execution. Keep synthetic reports out of operational evidence.

Advance to a limited host canary only if: zero scope/revocation/instruction-authority failures; no material task-correctness regression (paired 95% confidence lower bound appropriate for binary outcomes above -5 percentage points (do not use a degenerate all-zero bootstrap to certify non-inferiority)); and at least one preselected improvement (>=15% mean total measured token reduction or >=10-point source recall improvement) with a paired 95% bootstrap CI excluding zero. Include catalog maintenance cost amortized at observed reuse, not an assumed reuse count. Tail latency p95 must stay within +20%; cost cannot silently rise. These are proposed release criteria, not measured achievements. If inconclusive, collect more held-out pairs; if worse, keep default direct retrieval and revise/reject the path.

## Implementation order

1. **Now / coordinator:** contract tests, catalog/expansion implementation, CLI, component harness; reuse the v1 store. Executor recommendation: Terra for cross-cutting work; highest-capability review. Current agent executes under existing authorization.
2. **Now / coordinator:** document source provenance, protocol, limitations and results; run focused and required release checks, skeptical review, impact reconciliation, version scripts and scoped commit/release policy.
3. **Gated by exact baseline and real evidence:** collect held-out host A/B runs and ablations through existing receipt controls. Paid calls need an explicit budget; do not invent an incumbent or simulate an outcome.
4. **Gated procedural integration:** in its own branch/impact map, add `rhize-procedural-recall-v1` metadata contract (artifact identifier, revision, digest, kind, short description, health, lastVerified; trusted tenant/project binding). Reuse registry/digest/health, reject drift/unhealthy results; never run artifacts or create embeddings. Add source contract tests before allowing the assembler's procedural adapter. Update runtime STATE and both plugin/runtime docs. Benchmark procedure selection against incumbent exact recall independently.
5. **Gated host canary:** reuse existing host adapters and receipt machinery. Add only a bounded catalog hook if actual parity and benefit are proven. Suppress exact already-present sources; do not stack duplicate native-memory/claude-mem summaries. Keep RTK/Headroom fixed across arms. No OpenWolf/QMD/CodeGraph replacement.
6. **Rollback:** opt-out returns to unchanged `preview`; no canonical data migration exists. Remove experimental catalog packs with existing TTL cleanup or explicit source purge. Revert the scoped release if contracts fail.

## External and operational effects

Local private packs and reports only. No database migrations, network model calls, new credentials, source-store mutation, or hook activation. Source revisions must be supplied by the trusted caller immediately before expansion; this is an explicit adapter contract, not a live connector.

## Unknowns and confidence

Confidence is high in current code boundaries and low in task-level effectiveness until measured. The metadata producer is an explicit caller, so automated catalog maintenance cost is not yet measured. CodeGraph cannot prove runtime external hook ordering. Current and future activation are separate: a released opt-in command is not evidence that it ran in a host or improved outcomes.

## Execution checklist

- [x] Review source, existing ownership and Skill Forge study.
- [x] Persist plan and feature branch.
- [x] Prepare impact receipt before source edits.
- [x] Implement and exercise opt-in catalog/expansion.
- [x] Run component benchmark and adversarial contracts.
- [x] Documentation and local release checks.
- [ ] Reconcile and publish the scoped release; Git history is the authoritative release receipt.
- [ ] Exact incumbent confirmed and held-out live benefit measured.
- [ ] Procedural adapter and default activation advancement gates met.

## Final scoped file map

- `.claude-plugin/marketplace.json`
- `CHANGELOG.md`
- `README.md`
- `docs/README.md`
- `evals/memory-context/README.md`
- `generated/skill-map.static.json`
- `rhize-context-manager/.claude-plugin/plugin.json`
- `rhize-context-manager/.codex-plugin/plugin.json`
- `rhize-context-manager/CHANGELOG.md`
- `rhize-context-manager/GUIDE.md`
- `rhize-context-manager/README.md`
- `rhize-context-manager/commands/memory-context.md`
- `rhize-context-manager/scripts/memory_context/runner.py`
- `rhize-context-manager/skills/SOURCES.md`
- `rhize-context-manager/skills/context-stack/SKILL.md`
- `rhize-context-manager/skills/memory-context/SKILL.md`
- `docs/research/memory-awareness-benchmark.md`
- `evals/memory-context/run_awareness_benchmark.py`
- `evals/memory-context/tests/test_awareness.py`
- `rhize-context-manager/scripts/memory_context/awareness.py`
- `rhize-context-manager/skills/memory-context/references/awareness.md`

## Verified implementation and benchmark results

The new entry points are `runner.command_awareness` -> `build_catalog`/`expand_catalog` -> the existing assembler/store. `core.py` remains byte-identical to pinned Arm A. The catalog never consumes original bodies; a trusted caller supplies labels, keywords, digest and verification time. Both CLI commands require current source-state and verify before printing context. Expansion includes catalog overhead, retains conflicts, and rejects changed digests, authority, provenance, scope, revisions, expiry and revocation. Unsupported procedural/episodic adapters stay unavailable. Direct preview remains unchanged.

Local validation: 57 memory-context tests passed, including the actual bash launcher and executed benchmark arms. The broader run passed 1,291 tests with five existing skips and 18 subtests; one local-clone test initially hit the sandbox hard-link restriction, then passed unchanged outside the sandbox (1,292 aggregate passing tests). The 359-test Dev Flow release suite, manifest validation, configuration lint, generated map freshness, setup-artifact freshness, renderer idempotence, Python compilation and Dev Flow doctor also passed. Doctor's optional deploy-correlation capability is degraded because Vercel MCP is absent from that configuration; it is unrelated to this local memory change. No tests were disabled.

The component run executed 120 seeded pairs (20 per cohort), both recorded variants, randomized arm order, fresh stores and an actual empty-memory control. The selection oracle knows the desired source IDs; therefore apparent source recall gains are **not** evidence of improved model selection or task correctness. All host/model usage, billed cost and task-correctness fields remain unavailable.

| Cohort | Arm A estimated rendered tokens | Arm B estimated rendered tokens | Reduction |
|---|---:|---:|---:|
| long | 7663.25 | 5522.00 | 27.94% |
| short | 545.00 | 605.00 | -11.01% |
| no-memory-needed | 2179.00 | 1690.00 | 22.44% |
| sparse | 7663.25 | 5522.00 | 27.94% |
| conflicting | 2010.00 | 1916.00 | 4.68% |
| scope-and-poison | 1908.00 | 1730.00 | 9.33% |

Decision: keep this capability opt-in. Short documents cost 11.01% more in this corpus. In no-memory-needed cases, the actual empty-memory control costs zero; both memory arms are inferior on context cost. Prefer direct retrieval for short/known sources and no memory for self-contained tasks. Long-body savings warrant a real evaluation, not default activation. The fixture intentionally varies rankings, so its oracle-assisted recall difference must not be generalized to real tasks. Automated source maintenance, native-host overlap, actual tokenization, and user task outcomes remain unmeasured.

Full local component receipt: `/Users/jamesdeola/.codex/visualizations/2026/09/06/01a07716-b02b-78c2-a03f-33e78160f5dd/hipocampus-review/awareness-component-benchmark.json`. SHA-256: `6dd45cd77f9bdd12c5372788027453a1d01590b1ecbe265d26331f924cbc471b`. Reproduce with the documented seed 130/repeats 20 command; elapsed timings vary. The report pins executable source hashes.

Procedural-memory runtime, hooks, third-party libraries and canonical source stores were not changed. The exact incumbent question is still pending; subsequent live captures must use the user-confirmed host baseline. No paid providers were called and no operational benchmark receipts were fabricated.
