# Parallel-agent consolidation impact plan

| Field | Frozen decision |
| --- | --- |
| Scope | `rhize-ops:parallel-agent-optimization`, its local receipt helper, parallel eval fixtures, RT-147 protocol text, plugin-local docs/version |
| Runtime strategies | `baseline` and self-contained `rhize` only |
| Historical evidence | Preserve v1 ECC/Superpowers/combined smoke as labeled screening evidence; never rewrite or pool it with v2 |
| External skills | Provenance and `ai-stack-version-drift` review inputs only; no runtime load/consume/dependency |
| Evidence policy | No fabricated production rows; token/tool counts remain null with a reason when unavailable |

## Source comparison

- ECC 2.2.0, MIT, skill SHA-256 `b44def0f7c24ab2505bd2eee10ceb777d591724dbe32dfdf5220354385e1e3ab`: retain dependency-graph/lane-matrix classification, deliberate polling, blocker propagation, and explicit verification reporting.
- Superpowers 6.3.0, MIT, skill SHA-256 `1968923066f3b707eb01d1992cdf4c42284c3855f70253b9cd5000ff45fca13c`: retain one independent domain per agent, focused self-contained briefs, explicit constraints/output shape, and coordinator review/integration.
- Rhize already owns eligibility, write isolation, protected-state gates, true interval overlap, privacy-safe receipts, and observational/controlled separation. Do not duplicate vendor examples or retain vendor invocation.

## Implementation and verification

1. Write failing focused tests for v2 begin/finalize lifecycle, deterministic expected routing, stale-pending audit, terminal failure/incomplete receipts, strict privacy, legacy v1 reads, two-arm comparisons, and readiness gates.
2. Make the skill self-contained and implement v2 receipt/reservation/report behavior in `parallel_metrics.py`; keep v1 parsing/reporting isolated and labeled.
3. Convert the eval manifest/preparer/grader/aggregator to repeated `baseline` versus `rhize` fixtures whose reservations always finalize, while retaining the 2026-08-27 smoke as legacy screening evidence.
4. Update `SKILL.md`, command/references, `SOURCES.md`, RT-147 investigation text, README/GUIDE, plugin changelog, and plugin-local version. Do not edit root marketplace/catalog/generated skill-map files.
5. Run focused pytest/unittest suites, plugin checks, relevant repository gates, cold-review the diff, and commit only these files.

Coordinator regeneration after integration: run the governed root version/catalog/skill-map generation commands so marketplace and generated graph artifacts reflect the plugin-local version and removed dependency edges, then rerun root freshness gates.
