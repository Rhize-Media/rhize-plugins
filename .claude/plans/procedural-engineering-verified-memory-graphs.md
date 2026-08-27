# Procedural Engineering: Verified Memory and Execution Graphs

**Status:** Proposed for review
**Owner:** Rhize Tools
**Repos:** `procedural-memory`, `rhize-plugins`, scheduler sources in `~/Documents/Claude/Scheduled/`
**Primary outcome:** Prove, with comparable local evidence, which stored procedures and execution-graph capabilities improve Rhize's daily work; package only the capabilities that clear their promotion gates.

## Decisions incorporated

1. **Keep four evidence lanes separate:** leaf A/B performance, graph B/G performance, correctness/reliability, and productization.
2. **Adopt the correctness ledger now.** It is not an exception to the wall-time candidacy floor and is never summed into cost or latency metrics.
3. **Use one canonical scheduler per routine.** Drift remains Monday-only during the benchmark period unless a separate operational need justifies Thursday. Weekly Skill Audit remains in Claude Code Registry B. Daily Completed Summary is re-enabled in Desktop/Cowork Registry A because its artifact-update dependency does not exist in Registry B.
4. **Graph health changes only through explicit verification.** Promotion writes `unverified`; production success alone cannot write `ok`. A graph health verifier must re-check digest parity, deterministic fixtures, required live receipts, and model-map freshness before writing `ok`.
5. **G1 thin transport follows the contract/truth pass.** G2 model routing and G3 structural trims remain sequential experiments after a clean G1 row.
6. **Graph commands enter the Rhize plugin only after clean Arm-G row 2.** Documentation/doctor/eval groundwork may ship earlier.
7. **Implement Functionize's remaining half as a review-gated proposal compiler.** Mined history never directly creates executable code or registry entries. Human selection, generated-wrapper verification, promotion, and Secure-Enclave approval remain distinct gates.
8. **Jira umbrella:** `Procedural Engineering: Verified Memory and Execution Graphs`, with one story per independently verifiable slice below.

## Verified baseline (freeze before changes)

| Surface | Baseline |
|---|---|
| `procedural-memory` tests | 472 passed, 2 deselected |
| skill-monitor tests | 136 passed |
| procedural-memory plugin eval definitions | 5 schema-valid cases |
| registry artifacts | 11 skills, 5 functions, 1 graph |
| graph telemetry | 2 graph runs, 15 node runs |
| health sidecars | 16 `ok`, Content Engine graph `unverified` |
| Content Engine graph evidence | one composite/shakeout G row; not a clean performance baseline |
| Functionize live mining refresh | 16 CLIs sampled; only `npm` and `claude` produced heuristic candidates, both `flag_allowlist`-only weak signals |
| Daily Completed Summary | one nonrepresentative 46-day-backfill A row; recurring schedule disabled before this plan |

The first implementation commit must record these values in the eval baseline. If a value changes because another session lands work first, refresh it and record the new commit/date instead of silently preserving the stale number.

## Experiment contract

### Variant taxonomy

- **A:** current LLM-recomposed routine.
- **B:** retrieved, versioned leaf/function artifacts; orchestration otherwise unchanged.
- **G:** compiled execution graph using the same eligible leaf functions.
- **G1:** native thin transport, current model map and graph structure.
- **G2:** G1 plus receipt-bound per-node model routing.
- **G3:** G2 plus one structural change (initial candidate: fold `humanize_pass` into `write`).

Every metric row must include `variant`, artifact/graph digest, input fingerprint, model map, environment/surface, task scope, and whether every expected step ran. Rows with unequal scope are retained but marked non-comparable.

### Evidence lanes

1. **Performance:** wall time and attributable step time; cost only when measured on a common basis.
2. **Output parity:** item counts, source failures, produced artifact types, effect count, and schema validity.
3. **Correctness:** fabricated-clean, silent no-op, gate rejection, revise loop, unsafe effect prevented, and human correction required.
4. **Operability:** script edit, retry count, approval cycles, preflight cycles, and recovery from interrupted state.

Never create a composite score across these lanes. A change can win latency and lose correctness; the asymmetry is the finding.

## Phase 0 — Establish the control plane

These tasks can run in parallel except where noted. Phase 1 cannot begin until P0.1–P0.4 are complete.

### P0.1 Scheduler truth and observation windows

- Re-enable `daily-completed-summary` in Claude Desktop Registry A at its existing daily 8:00 p.m. cadence.
- Keep the Registry B copy absent/disabled; the Cowork artifact dependency is load-bearing.
- Reconcile Drift to one active schedule. Recommended experiment cadence: Monday only, in its existing capable runtime, with no duplicate Mon/Thu copy.
- Verify Weekly Skill Audit is enabled only in Registry B.
- Record `enabled`, cron, runtime, last run, and next run in the benchmark plan after each change.

**Acceptance:** a read-after-write of both registries shows exactly one enabled entry per routine; the next scheduled date is calendar-verified; no routine is duplicated.

### P0.2 Authoritative truth reconciliation

Correct together:

- graph contract header/version and obsolete no-Postgres statements;
- core README's “not implemented” Phase-2 statement;
- graph CLI help's stale contract version;
- `doctor` migration coverage from 001–003 to every required migration through 005;
- generated Obsidian registry mirror from 15 to 17 artifacts;
- benchmark milestone dates and the distinction between 16 healthy leaves and one unverified graph.

**Acceptance:** docs agree with Git, database, CLI output, and sidecars; `doctor` fails in a fixture missing 004 or 005; full tests pass.

### P0.3 Explicit graph-health lifecycle

Add an explicit post-promotion graph health verification path. It must:

1. recompute and compare the graph digest with the promoted sidecar;
2. rerun hermetic deterministic must-reject/known-good fixtures;
3. validate every required LLM receipt against digest and supplied model map;
4. perform no effectful graph nodes and no implicit network call;
5. write `health=ok` and `last_verified` only after every check passes;
6. write/retain a non-ok result on failure without erasing the evidence;
7. expose the result through `graph status` and tests.

`graph verify --live` remains the opt-in network operation that creates receipts. A successful production run does not replace either verification step.

**Acceptance:** neuter tests prove stale digest, stale model map, failing deterministic fixture, and missing receipt cannot write `ok`; the promoted Content Engine graph can earn `ok` through the explicit path.

### P0.4 Freeze eval schemas and baselines

Version deterministic schemas for:

- routine A/B rows;
- graph G/G1/G2/G3 rows and per-node telemetry;
- correctness incidents;
- Functionize candidate/proposal/promotion outcomes.

Add code-based validators and a baseline snapshot tied to Git SHAs. Make missing required fields a loud eval failure.

**Acceptance:** existing valid rows parse; the known composite G row parses as `comparable=false`; deliberately mixed-scope fixtures fail or are marked non-comparable.

## Phase 1 — Harvest representative Arm-A data

### P1.1 Daily Completed Summary

- Observe the first run after re-enablement; do not count the 46-day backfill as representative.
- Confirm before/after row-count delta, telemetry event, and explicit run summary.
- Collect at least three representative A rows before building or activating `capture-daily` Arm B.
- Repair the known zsh `for e in REG` defect before calling an A row representative, while preserving A semantics and documenting the repair.
- Track truncation separately (`gh --limit`, Jira pagination, Slack page completeness).

**Promotion decision:** proceed to B only if deterministic Steps 1–5 clear the floor on representative rows or if the correctness ledger independently justifies freezing them. Never infer qualification from phase-level timing alone.

### P1.2 AI Stack Drift

- Observe the next correctly scheduled step-timed A run.
- Calculate inventory, upstream-fetch, and semver-classification shares separately.
- Treat network wait as non-convertible unless B changes the fetch behavior.
- Below the floor: close the wall-time candidacy track for Drift and retain any correctness rationale separately.

### P1.3 Weekly Skill Audit

- Verify the first post-reenable run completes.
- Confirm refinement-queue drain, dashboard refresh, benchmark watchdog, and trust-classed stack metrics.

**Acceptance for Phase 1:** every expected natural run has a row or a loud `row_missing` incident; no missing measurement is interpreted as zero.

## Phase 2 — Functionize proposal compiler

### Product decision

Build the remaining half, but keep it deliberately narrow. The current two real-history candidates are weak `flag_allowlist` signals and must not generate wrappers. A `flag_allowlist` signal alone is insufficient for proposal eligibility; it needs a second independent gotcha type or explicit human override with rationale.

### P2.1 Candidate identity and safe export

- Preserve `rhize-skill functionize <cli>` compatibility.
- Add stable candidate fingerprints over normalized, redacted shape plus CLI name.
- Allow export of a selected candidate into a local proposal manifest containing counts, source classes, gotcha enum values, and hashes—not raw shell-history text.
- Treat all mined content as hostile data; never interpolate it into a model instruction or shell command.
- Add optional source adapters for scheduled-task files and approved telemetry, each labeled separately from zsh history. No source is enabled implicitly.

### P2.2 Human review gate

The operator must select a candidate and define:

- intended behavior and parameters;
- the gotcha(s) the wrapper must encode;
- the observable behavior difference from the bare CLI;
- output/schema contract and exit taxonomy;
- language choice (bash for simple process composition, Python for structured parsing/state);
- permitted effects and secret references.

Rejected candidates remain recorded with reason so repeated mining does not create review churn.

### P2.3 Agent-assisted draft, deterministic grading

The Rhize procedural-memory plugin may use the reviewed manifest to draft a complete proposal in an isolated, unregistered directory. It must generate:

- complete executable wrapper;
- provenance sidecar;
- smoke test plus a behavior-difference test for every declared gotcha;
- secret-scan and path-parameterization evidence;
- one-line indexed description;
- proposed semantic version and consumer list.

The model may propose code; deterministic tests decide whether the gotcha becomes `verified`. No incomplete files or TODO implementations enter Git.

### P2.4 Promotion remains separate

- Run existing promoter checks against the proposal.
- Human reviews diff and eval report.
- `rhize-skill promote` performs the registry write/indexing only after review.
- Secure-Enclave approval remains separate from generation and promotion.
- Retrofitting a consumer routine is opt-in, one routine per change, after enough A data exists.

### Functionize evals

Capability fixtures must cover all six gotcha enum types plus thin-alias refusal, prompt-injection text, residual-secret rejection, privileged operations, and interrupted proposal recovery.

Track:

- candidates discovered and source class;
- accepted/rejected/overridden;
- proposal generation attempts and edit count;
- deterministic pass@1 and pass@3;
- secret/redaction findings;
- promotion/approval outcome;
- first three real runs, script edits, and correctness incidents.

**Release gate:** deterministic regression pass^3 = 100%, no raw-history leakage, one reviewed real proposal successfully promoted and run, and no automatic registry write path. Automatic candidate queuing remains out of scope until at least three real proposals establish demand.

## Phase 3 — Execution graph iteration

### P3.1 G1 precondition audit

- Map every node input to declared input, upstream state, or `run_params`.
- Define freshness owner/TTL for Sanity IDs and internal-link snapshots.
- Make `state.json` authoritative over crash-litter `pending_llm_call.json`.
- Correct printed Git path prefixes and document runner-sidecar provenance.
- Amend the contract for a network-capable driver and adversarially review the trust boundary.

### P3.2 G1 thin transport

- Generalize the existing native LLM-gate transport for LLM nodes.
- Validate returned schemas, use bounded retries only on named validation/transport failures, and clock wall time in the driver.
- Preserve prompt/model/digest receipts and pre-effect gate semantics.
- Re-drive the fixed Content Engine input with unchanged model map and graph structure.

**Acceptance:** clean Arm-G row 2, every node has measured wall time, no manual pending-call bridge, same expected effects, and no unresolved script edit.

### P3.3 G2 model routing

- Harden the publish rubric first with deterministic alignment fixtures and a documented aggregation rule if multi-judge voting is used.
- Change only the per-node model map.
- Re-receipt the changed map and run a matched input.
- Judge on correctness, cost, latency, and gate/revise outcomes separately.

### P3.4 G3 structural trim

- Change only graph structure: initial hypothesis is folding `humanize_pass` into `write`.
- Keep banned-pattern and revise-loop backstops.
- Require multiple matched runs before removing the node from the default graph.

## Phase 4 — Rhize plugin packaging

After G1 row 2 passes:

- expose graph status/preflight/run/resume/health-verification through the procedural-memory plugin;
- expose the review-gated Functionize proposal flow, not raw-history code generation;
- add positive and negative plugin evals for command routing and unsafe requests;
- update README, GUIDE, changelog, plugin version, and marketplace version atomically;
- validate plugin installation from a clean cache and run the launcher tests.

Do not vendor knowledge-graph functionality already supplied by Graphify/Graphiti. Document the boundary: execution graphs run procedures; knowledge graphs retrieve facts/relationships.

## Phase 5 — Decision reviews and operating cadence

Review evidence after each milestone rather than on a fixed calendar:

1. three representative Daily Summary A rows;
2. Drift's next step-timed row;
3. clean G1 row 2;
4. first reviewed Functionize proposal;
5. three G2 matched runs;
6. three G3 matched runs if G3 is attempted.

Each review produces one decision: continue, change one variable, promote/package, or stop. Stopping because the eligible deterministic share is too small is a successful experiment outcome.

## Jira backlog mapping

Create after this plan is approved:

1. **Epic:** Procedural Engineering: Verified Memory and Execution Graphs
2. Scheduler truth and representative observation windows
3. Reconcile graph contract, README, CLI help, doctor, and vault mirror
4. Implement explicit graph-health verification
5. Version procedural-memory eval schemas and freeze baselines
6. Re-enable and measure Daily Completed Summary Arm A
7. Measure AI Stack Drift step-level Arm A
8. Verify Weekly Skill Audit recovery and observability
9. Implement Functionize safe candidate export and review ledger
10. Implement Functionize reviewed proposal generation and deterministic graders
11. Prove and promote the first real Functionize-generated artifact
12. Audit G1 inputs, crash recovery, freshness, and network trust boundary
13. Implement G1 native thin transport and collect clean Arm-G row 2
14. Run G2 model-routing experiment
15. Run G3 structural-trim experiment
16. Package proven graph and Functionize surfaces in the Rhize plugin
17. Hold evidence review and update/close follow-up stories

Each story must contain its variant, baseline SHA, deterministic acceptance tests, required human gate, and evidence artifact location. Do not estimate performance gains in Jira before measurement.

## Execution routing

- **Sol / highest-capability tier:** contract changes, threat modeling, eval design, review gates, evidence conclusions.
- **Terra:** G1/G2 integration, graph health, Functionize proposal compiler, cross-repo/plugin packaging.
- **Luna:** bounded documentation corrections, schema fixtures, mechanical test additions after contracts are fixed.

## Completion criteria

This program is complete when:

- every surviving claim is tied to comparable, variant-labeled evidence;
- silent measurement failure is detectable;
- graph health and Functionize promotion have explicit, testable gates;
- at least one clean graph comparison and one real Functionize proposal have been evaluated;
- only capabilities supported by the evidence are packaged;
- rejected hypotheses and stopped work are retained as findings rather than silently abandoned.
