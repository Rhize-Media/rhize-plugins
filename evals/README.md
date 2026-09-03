# Plugin Eval Harness

Programmatic testing and benchmarking for rhize-plugins. The live-model harness measures two things:

1. **Trigger accuracy** — Do skills fire on the right prompts (and stay quiet on wrong ones)?
2. **Output quality** — When skills run, do they produce useful, correct results?

## Directory Structure

```text
evals/
├── README.md              # This file
├── run_evals.py           # Main harness (supports --plugin flag)
├── assertions.py          # Assertion evaluation engine
├── aggregate_results.py   # Cross-run aggregation
├── seo-aeo-geo/           # SEO plugin evals
│   ├── trigger_evals.json
│   └── quality_evals.json
├── obsidian/              # Obsidian Skills plugin evals
│   ├── trigger_evals.json
│   └── quality_evals.json
├── project-launcher/      # Project Launcher live + deterministic evals
├── rhize-cowork/          # Rhize Cowork live + deterministic evals
├── rhize-devflow/         # Dev Flow deterministic contracts
├── rhize-context-manager/ # Context Manager deterministic contracts
├── rhize-tasks/           # Rhize Tasks deterministic contracts + benefit protocol
├── procedural-memory/     # Procedural Memory deterministic contracts
├── skill-forge/           # External SkillForge safety/evolve integration harness
├── parallel-agent-skills/ # Rhize routing + isolated guide-comparison protocols
└── results/               # Auto-generated benchmark reports
```

Directories with `trigger_evals.json` or `quality_evals.json` are auto-discovered by the live-model
harness. Other components deliberately use offline runners with component-specific schemas so they
cannot be swept into a paid model run by accident.

The offline coverage gates account for all 56 currently published Rhize plugin skills. That is a
coverage statement, not a benefit claim: most live and controlled Arm A/Arm B cohorts are still
pending, and every checked-in benchmark contract says so explicitly.

## Prerequisites

- `claude` CLI installed and authenticated
- Python 3.10+
- **SEO evals**: DataForSEO credentials (`DATAFORSEO_USERNAME`, `DATAFORSEO_PASSWORD`)
- **Obsidian evals**: No external credentials needed (reference knowledge only)

## Quick Start

```bash
# Run everything across all plugins (1 run per eval)
python evals/run_evals.py --runs 1

# Run only obsidian plugin evals
python evals/run_evals.py --plugin obsidian --runs 1

# Run only seo plugin trigger evals
python evals/run_evals.py --plugin seo-aeo-geo --trigger-only --runs 3

# Output quality for a single skill
python evals/run_evals.py --quality-only --skill seo-site-audit --runs 1

# Full benchmark with baseline comparison
python evals/run_evals.py --with-baseline --runs 3 --verbose

# Immediate local/free coverage gates
python3 evals/seo-aeo-geo/run_local_evals.py
python3 evals/obsidian/run_local_evals.py
python3 evals/project-launcher/run_local_evals.py
python3 evals/rhize-cowork/run_local_evals.py
python3 evals/rhize-devflow/run_evals.py
python3 evals/rhize-context-manager/run_evals.py
python3 evals/parallel-agent-skills/scripts/evaluate_ops_skills.py
python3 evals/rhize-tasks/run_evals.py
python3 evals/procedural-memory/run_evals.py
```

## CLI Flags

| Flag | Description |
| ---- | ----------- |
| `--plugin <name>` | Target one discovered live-model eval directory or `all` (default) |
| `--trigger-only` | Run trigger accuracy tests only |
| `--quality-only` | Run output quality tests only |
| `--skill <name>` | Filter to a single skill (e.g., `seo-site-audit`, `obsidian-cli`) |
| `--with-baseline` | Include vanilla Claude (no plugin) for comparison |
| `--runs <n>` | Repetitions per eval case (default: 3) |
| `--verbose` | Print commands and outputs as they run |
| `--dry-run <file>` | Validate assertions against a sample output file (no claude invocation) |
| `--bypass-permissions` | Pass `--dangerously-skip-permissions` to claude |
| `--allowed-tools <list>` | Comma-separated tool whitelist to reduce context size |
| `--setting-sources <list>` | Setting sources for claude -p (default: `project,local`) |
| `--output <path>` | Write results to a specific path instead of auto-generated |

## How It Works

### Trigger Detection

The harness uses **deterministic detection** via `--output-format stream-json --verbose`. It parses
the actual `tool_use` blocks from Claude's response stream and treats a matching `Skill` tool call
as the trigger signal. Token/turn heuristics are diagnostic only and do not decide pass/fail.

All evals run from `REPO_ROOT` (the plugin directory) so skills are available. Tests measure selectivity — does the right skill fire, and do wrong skills stay quiet?

### Trigger Tests (`trigger_evals.json`)

Each case has a prompt, a target skill, and whether it should trigger. Computes precision/recall/F1 per skill.

### Quality Tests (`quality_evals.json`)

Each case has a prompt and a list of assertions (contains, regex, min_length, calls_tool, etc.). The harness runs the prompt, evaluates assertions against the output, and reports pass rates.

### Baseline Comparison (`--with-baseline`)

Runs each quality eval twice — once with the plugin, once without — and computes the delta in assertion pass rates.

## Output

Results are saved to `evals/results/`:

- `benchmark-{timestamp}.json` — Machine-readable results (organized by plugin)
- `benchmark-{timestamp}.md` — Human-readable report with tables per plugin

## Adding Test Cases

### Trigger eval format

```json
{
  "id": "trigger-skill-name-description",
  "prompt": "A realistic user prompt",
  "target_skill": "skill-name",
  "should_trigger": true
}
```

### Quality eval format

```json
{
  "id": "quality-skill-name-description",
  "skill": "skill-name",
  "prompt": "A realistic user prompt",
  "assertions": [
    {"type": "contains", "value": "expected text", "name": "Human-readable label"},
    {"type": "regex", "value": "pattern", "name": "Label"},
    {"type": "min_length", "value": 500, "name": "Label"},
    {"type": "calls_tool", "value": "tool_name_substring", "name": "Label"},
    {"type": "section_count", "value": 3, "name": "Label"}
  ]
}
```

### Adding a new plugin

1. Create `evals/<plugin-name>/`.
2. Add `trigger_evals.json` and/or `quality_evals.json` for the live-model harness, or a clearly
   named offline runner and documented schema for deterministic-only coverage.
3. Require one positive and two meaningful near-miss/collision negatives for every trigger-capable
   skill, plus a deterministic quality contract where feasible.
4. Define exact Arm A/Arm B implementations and record which arm actually ran. Never check in
   fabricated or placeholder results.

## Assertion Types

| Type | Value | Checks |
| ---- | ----- | ------ |
| `contains` | string | Output includes string (case-insensitive) |
| `not_contains` | string | Output must NOT include string |
| `regex` | pattern | Output matches regex pattern |
| `min_length` | number | Output has at least N characters |
| `max_length` | number | Output has at most N characters |
| `calls_tool` | string | An MCP tool matching this substring was called |
| `section_count` | number | At least N markdown `##` sections in output |
| `has_data` | number | At least N concrete data points (numbers, percentages, URLs, scores) |

## Suites

One paragraph per directory under `evals/` (excluding `results/`, which is auto-generated output,
and `__pycache__/`) — what it grades, how to run it, and what it writes. See "Plugin-Specific
Notes" below for narrative context on the live-model plugin suites.

### context-tools

Grades the real pinned context-tooling providers used by `rhize-context-manager`: the
capture-health gate validates live experiment receipts (schema, Arm A/B pairing, malformed,
missing, or expired captures) and exits `2` on actionable evidence loss, while the retrieval
runner grades real scoped `ripgrep` (Arm A) against real local `grepai` (Arm B-local) semantic
search. Run with `python3 rhize-context-manager/scripts/context_experiments/runner.py
capture-health` and `python3 evals/context-tools/run_retrieval_evals.py --output
evals/results/context-tools/retrieval-phase-1.5-real.json`. Writes JSON reports under
`evals/results/context-tools/`; these are measurement-pipeline checks, not a provider adoption
gate.

### decision-accountability

Grades the offline decision-accountability contract — deterministic policy reproduction,
source/evidence/policy/approval/effect/outcome separation, preview expiry, CAS/idempotency,
failure atomicity, ACL/tenant denials, and PROV-O interoperability — against synthetic fixtures
only. Run with `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s
evals/decision-accountability/tests -p 'test_*.py'`. Writes nothing to disk; it is a pass/fail
unittest run with no Neo4j or client data involved.

### graph-hygiene

Grades Rhize's candidate-only identity workflow independently of a live Neo4j database:
normalization, tenant/namespace/ACL/type/trust gates, poisoned and flooded inputs,
compare-and-swap review leases, and privacy-safe quality reporting. Run with
`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s evals/graph-hygiene/tests -p
'test_*.py'`. Writes nothing to disk; the labeled fixture is a deterministic contract corpus, not
a calibrated production threshold.

### graph-ontology

Grades the offline ontology release contract — deterministic ontology generation, extension
isolation, Graphify translation, tenant-safe identities, source provenance, purge/backup/restore,
and host-neutral CLI output — against synthetic, redacted fixtures. Run with
`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s evals/graph-ontology/tests -v`. Writes
nothing to disk; it is not evidence of a live Neo4j deployment.

### memory-context

Grades the host-neutral memory adapter for Claude Code and Codex: byte-equivalent manifests,
conflict preservation, inert untrusted content, scope denial, TTL/source-revision invalidation,
and (for the graph fixture) tenant/ACL denial and purge, without opening a database connection.
Run with `python3 -m pytest -q evals/memory-context/tests`. Writes nothing to disk; deterministic
contract evidence only, not operational retrieval evidence.

### obsidian

Grades the `obsidian-second-brain` plugin's skills: `run_local_evals.py` is the free
deterministic gate (routing substrings, keyword drift, one positive plus two collision negatives
per skill, static quality contracts); `trigger_evals.json`/`quality_evals.json` are live-model
cases for the shared `evals/run_evals.py` harness. Run the local gate with `python3
evals/obsidian/run_local_evals.py`. The local gate writes nothing; the live harness writes
results into `evals/results/`.

### parallel-agent-skills

Grades the `rhize-ops:parallel-agent-optimization` strategy against a `baseline` variant across
six deterministic task classes, three repetitions each, in counterbalanced order. Run a pair with
`scripts/prepare_run.py` (once per variant) then `scripts/grade_run.py`; the ops-skill
routing/collision gate runs via `python3 evals/parallel-agent-skills/scripts/evaluate_ops_skills.py`.
Writes a provisional then finalized `receipt.json` per run under an explicit `--output` directory
(not committed) and reservation state to `RUN_RESERVATION.json`.

### procedural-engineering

Grades nothing live — it validates that `baseline-2026-08-30.json` (the frozen
pre-implementation snapshot for the procedural-engineering evidence-gates plan) still matches its
receipt contract. Run with `python3 evals/procedural-engineering/validate_baseline.py
evals/procedural-engineering/baseline-2026-08-30.json`. Writes nothing; historical rows are never
upgraded in place.

### procedural-memory

Grades a free local collision contract (one positive, two negatives) for the `procedural-memory`
and `functionize` skills, plus the org-gated canonical suite in `procedural-memory/evals/` (still
the authoritative agent-eval suite). Run with `python3 evals/procedural-memory/run_evals.py` and
`python3 procedural-memory/evals/validate-suite.py --eval-dir procedural-memory/evals`. Writes
nothing to disk.

### project-launcher

Grades the `project-launcher` plugin's skills via the same local pattern as
obsidian/seo-aeo-geo/rhize-cowork: keyword drift, one positive plus two collision negatives per
skill, live-quality case presence, static operational contracts. Run with `python3
evals/project-launcher/run_local_evals.py`. Writes nothing to disk; `benchmark_spec.json` fixes
the future Arm A/Arm B pair, but no arm has run.

### rhize-context-manager

Grades all shipped `rhize-context-manager` skills: routing-keyword presence in each live
`SKILL.md`, one positive plus two collision negatives per skill, a static quality/ownership
contract, and a paired benchmark specification (Arm A/Arm B, common metric schema) per skill. Run
with `python3 evals/rhize-context-manager/run_evals.py` (add `--json` for machine output). Writes
no receipt or result file — it makes no model, network, provider, or live-mutation calls.

### rhize-cowork

Grades the `rhize-cowork` plugin's skill: keyword drift, one positive plus two collision
negatives, a live-quality case, and static operational contracts. Run with `python3
evals/rhize-cowork/run_local_evals.py`. Writes nothing to disk; `benchmark_spec.json` fixes the
future Arm A/Arm B pair, but no arm has run.

### rhize-devflow

Grades the `rhize-devflow` control plane offline (no live `claude -p` calls): trigger precision
via a fixed keyword-substring heuristic (`keywords.json`), output quality by re-running
`evals/assertions.py`'s assertion engine against the static contract text of `/check`, `/review`,
and the canonical skills, and benchmark readiness (every skill names an exact Arm A/Arm B and
common metrics). Run with `python3 evals/rhize-devflow/run_evals.py`. Writes nothing to disk.

### rhize-tasks

Grades all six `rhize-tasks` skills as one phrase-routing contract (so collisions are checked
together), plus safety-critical workflow anchors in each `SKILL.md`; `benefit-benchmark.json`/
`benchmark_contract.py` separately define and reserve/validate a six-task, three-repetition Arm
A/Arm B benefit protocol. Run with `python3 evals/rhize-tasks/run_evals.py` (and
`benchmark_contract.py reserve`/`validate` for the benefit protocol). Writes no receipts or
results by default; the benefit protocol writes reservation/validation state when actually run.

### seo-aeo-geo

Grades the `seo-aeo-geo` plugin's skills: `run_local_evals.py` is the free deterministic gate
(routing substrings, keyword drift, one positive plus two near-miss negatives per skill, static
contracts, no DataForSEO calls); `trigger_evals.json`/`quality_evals.json` are live-model cases
for the shared `evals/run_evals.py` harness (needs DataForSEO credentials). Run the local gate
with `python3 evals/seo-aeo-geo/run_local_evals.py`. The local gate writes nothing; the live
harness writes results into `evals/results/`.

### skill-forge

Grades the external SkillForge CLI/checkout without ever editing it: `inspect` detects
package/binary drift, `safety` runs a hand-labeled six-case precision/recall corpus plus local
scan latency, and `evolve_contract.py`/`evolve-benchmark.json` define a separate digest-pinned
pre/post non-inferiority protocol. Run with `python3 evals/skill-forge/integration_eval.py inspect
--checkout <path> --binary <path>` and the `safety` subcommand. Writes its safety results to an
explicit `--output` path outside Git; no receipts are committed.

### skill-map

Grades the skill-map subsystem's routing, disclosure, and remediation behavior against local
transcripts and hook subprocesses (not live `claude -p` calls) — a harness-integration entry
point since these evals don't fit `run_evals.py`'s trigger/quality-JSON discovery contract. Run
with `python3 evals/skill-map/run.py`, which runs `eval_routing.py`, `eval_disclosure.py`, and
`eval_remediation.py` in sequence. Writes one timestamped result file into `evals/results/`
(gitignored) in the same schema shape as `run_evals.py`'s output.

## Plugin-Specific Notes

### seo-aeo-geo

- Quality evals call DataForSEO APIs — requires credentials
- Local routing/contracts are self-contained and make no API calls
- 27 routing cases, 7 static contracts, and 7 live-quality definitions

### obsidian

- All evals are self-contained (reference knowledge only, no MCP server needed)
- Command evals (testing `/vault-search`, `/vault-setup`, etc.) are deferred — they require an Obsidian instance with the MCP Server connected
- 38 routing cases, 10 static contracts, and 10 live-quality definitions

### project-launcher and rhize-cowork

- Both ship immediate local/free routing and static contract gates plus live-quality definitions.
- Live benchmark results remain pending until their exact existing implementations are confirmed.

### devflow, context, ops, tasks, and procedural memory

- Their offline runners validate complete skill inventories, collision cases, static behavior
  contracts, and strict benchmark applicability without invoking a model.
- Context Manager binds `context-pack` to the existing executable provider harness; other benefit
  cohorts remain pending.
- Procedural Memory's portable vendor cases remain authored but organization-gated; its local
  deterministic runner and schema validator do not pretend to execute that vendor harness.

### parallel-agent guide comparison

`parallel-agent-skills/guide-comparison.manifest.json` defines separate isolated evidence for a
common baseline, the Superpowers dispatch guide, and Rhize's custom optimizer. Each guide is
compared with the same baseline in counterbalanced order. These rows never feed the canonical
baseline-versus-Rhize v2 readiness decision.

### SkillForge

The Rhize-side integration harness requires an explicit checkout/binary path, detects version
drift, measures a labeled safety precision/recall corpus and local scan latency, and defines a
digest-pinned pre/post evolve non-inferiority protocol. It never edits or adopts into SkillForge.
