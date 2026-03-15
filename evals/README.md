# Plugin Eval Harness

Programmatic testing and benchmarking for rhize-plugins. Measures two things:

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
└── results/               # Auto-generated benchmark reports
```

Each plugin has its own subdirectory with `trigger_evals.json` and `quality_evals.json`. The harness auto-discovers plugin directories or you can target a specific one with `--plugin`.

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
```

## CLI Flags

| Flag | Description |
| ---- | ----------- |
| `--plugin <name>` | Target a specific plugin (`seo-aeo-geo`, `obsidian`) or `all` (default) |
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

The harness uses **deterministic detection** via `--output-format stream-json --verbose`. It parses the actual `tool_use` blocks from Claude's response stream, looking for `Skill` tool invocations. Each SKILL.md also includes a watermark instruction (`[skill:{name}]`) as a secondary signal. Detection: `triggered = skill_tool_called or has_watermark`.

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

1. Create `evals/<plugin-name>/` directory
2. Add `trigger_evals.json` and/or `quality_evals.json`
3. The harness auto-discovers directories containing eval files

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
- Trigger evals are self-contained (no API calls)
- 22 trigger cases, 7 quality cases

### obsidian

- All evals are self-contained (reference knowledge only, no MCP server needed)
- Command evals (testing `/vault-search`, `/vault-setup`, etc.) are deferred — they require an Obsidian instance with the MCP Server connected
- 32 trigger cases, 8 quality cases
