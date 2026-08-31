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
