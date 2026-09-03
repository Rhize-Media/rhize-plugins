# rhize-core 1.0.0 stability contract

rhize-core is the marketplace control plane every other Rhize plugin's setup wizard, and the
`rhize-ops` one-release fallback (see `README.md` → "Compatibility with rhize-ops"), depends on.
This document names exactly what 1.0.0 promises to keep stable, and the deprecation policy for
anything that has to change. Everything here is enforced by `tests/rhize-core/` and
`tests/config-lint/test_platform_fallback_drift.py` — this is a description of what those tests
pin, not a separate promise made only in prose.

## setup/manifest.json — schema 3

Every consuming plugin's `setup/manifest.json` is read by `evaluation_setup.py` and
`setup_orchestrator.py`. The stable fields:

| Key | Required | Notes |
| --- | --- | --- |
| `schema` | yes | `2` or `3`. Schema 1 (inventory-only) is read leniently but never satisfies the evaluation-coverage gate. |
| `plugin` | yes | Must equal the plugin's own directory name. |
| `items` | yes | Array; may be empty. Each item: `id`, `title`, `tier` (`T3`\|`T4`), `event`, optional `matcher`, `command`, `description`, `default`. |
| `dependencies` | yes | Array; may be empty. Each entry: `name`, `kind` (`plugin`\|`cli`\|`mcp`\|`data`\|`runtime`\|`platform`), `purpose`, `required`, `degradedBehavior`, optional `binary` (kind `cli` only) and `replacement` (`suggestion` + `warning`). |
| `evaluations` | schema 2/3 only | Exactly `{"catalog": "rhize-evaluations-v1", "component": "<plugin>"}`. |
| `wizard` | optional, schema 3 only | `{"skill", "purpose", "when", "args"}`; `skill` must resolve to a `<plugin>/commands/<command>.md` that opens with `---`/`description:` frontmatter. Declaring `wizard` requires a non-empty `artifacts` array. |
| `doctor` | optional, schema 3 only | `{"kind": "skill"\|"shell", "value"}`. |
| `artifacts` | optional, schema 3 only | Array (may be explicitly empty); each entry: `id`, `path` (must start with `<project>`, `<home>`, or `<vault>`, no `..`), `kind`, `purpose`, `viewer`, `lifetime`, `confidentiality`, `source`, `tracked`, `optional`. |

The exact-keys enforcement (schema 2: precisely the four core keys plus `evaluations`; schema 3:
those plus only `wizard`/`doctor`/`artifacts`) is pinned by `tests/rhize-core/
test_setup_manifest_schema.py`.

## setup/evaluation-catalog.json — the one central catalog

Owned exclusively by rhize-core. Its top-level shape (`schema_version`, `policy`, `domains`,
`components`) and the `policy` block's exact values (`deterministic_release_gate: true`,
`matched_controlled_claim_gate: true`, `natural_evidence_class: "observational"`,
`controlled_repetitions: 3`, and the three-member `capture_modes` set) are pinned — a plugin's
own manifest never re-declares any of this. Each `plugin`-kind component's `skills` array must
exactly match the plugin's discovered `<id>/skills/*/SKILL.md` inventory (an empty array is valid
for a plugin with none, as rhize-core itself demonstrates); every component needs at least one
free, offline, `network: none`/`cost: free` Python suite and at least one benchmark record.

## Orchestrator subcommands and their JSON schemas

`scripts/setup_orchestrator.py` exposes these subcommands, each emitting a JSON object whose
`"schema"` field is the pinned identifier below (unchanged from before the split — the schema
strings are a stable wire contract, not tied to the plugin's own name):

| Subcommand | Schema |
| --- | --- |
| `discover --json` | `rhize-setup-discover-v1` |
| `hooks plan` | `rhize-setup-hooks-plan-v1` |
| `hooks apply` | `rhize-setup-hooks-apply-v1` |
| `artifacts snapshot` | `rhize-setup-artifacts-snapshot-v1` |
| `install-skill-map` | `rhize-setup-install-skill-map-v1` |

`scripts/git_preflight.py report` emits `rhize-git-preflight-v1`, also unchanged.

`scripts/evaluation_setup.py`'s `setup`/`reserve`/`finalize` commands read and write
`CONFIG_VERSION = "rhize-evaluation-config-v1"` and `RECEIPT_VERSION =
"rhize-evaluation-receipt-v1"` — see the JSON Schema files under `schemas/` for the exact shape
of each.

## Run-state and receipt layouts under `~/.rhize/`

| Path | Written by | Shape |
| --- | --- | --- |
| `~/.rhize/setup/runs/<run-id>.json` | `setup_orchestrator.py` (every subcommand accepting `--run`) | One JSON object per run id, keyed by section name (`discover`, `hooks_plan:<plugin>:<item>`, `hooks_apply`, `artifacts_before`, `artifacts_after`, `install_skill_map`, plus any `report record --section <name>`). 0700/0600. |
| `~/.rhize/evals/config.json` | `evaluation_setup.py setup` | One object per component under `plugins`, schema `rhize-evaluation-config-v1`. 0600. |
| `~/.rhize/evals/receipts/<YYYY-MM>.jsonl` | `evaluation_setup.py reserve`/`finalize` | Append-only JSONL, one row per line, schema `rhize-evaluation-receipt-v1`. 0600. |
| `~/.rhize/evals/hmac.key` | `evaluation_setup.py setup` (aggressive_local) / `reserve` | 32 random bytes, 0600, never rotated automatically. |
| `~/.rhize/evals/runtime-home/` | `evaluation_setup.py run_suite()` | Isolated `HOME`/`TMPDIR` for suite subprocesses. Not itself a receipt; contents are whatever a suite happens to write, and are not read back by this engine. |

## The `--from-rhize-setup` handshake

Every `wizard.skill` target command receives `args` (default `["--from-rhize-setup"]`) via the
Skill tool when the orchestrator invokes it in Phase 4. A target command's contract:

1. Parse `$ARGUMENTS` for the literal token `--from-rhize-setup` before doing anything else that
   reads `$ARGUMENTS` for its own keywords.
2. If present: run the wizard's own interview/config work, then **stop** without suggesting
   `/rhize-core:setup` (or the old `/rhize-ops:rhize-setup` name) — the orchestrator that invoked
   it is already mid-run and will continue its own remaining phases.
3. If absent (standalone invocation): after finishing, suggest running the fleet evaluation
   subflow (`/rhize-core:setup --plugin <this-plugin> --evaluations`).

The token's name is a historical carry-over from before the engine split out of `rhize-ops`. It is
deliberately **not** renamed to something like `--from-rhize-core` in this release — every existing
wizard command (`devflow-setup.md`, `context-setup.md`, `vault-setup.md`,
`rhize-tasks/commands/setup.md`, `rhize-ops/commands/delegate-setup.md`) already checks for it
verbatim, and renaming it would be a breaking change to all five with no functional benefit.
`tests/rhize-core/test_evaluation_setup.py::test_every_wizard_target_tolerates_the_handshake_flag`
pins this.

## Deprecation policy

A breaking change to any contract in this document — a manifest key, a JSON schema string, a
run-state/receipt path or shape, or the handshake token — gets **one full release's** advance
notice: the old shape stays readable (or the old token still accepted) for one minor version
after the new shape ships, with a `CHANGELOG.md` entry naming the removal version, a drift/
compatibility test guarding the transition window the same way `test_platform_fallback_drift.py`
guards the `rhize-ops` fallback, and the removal itself recorded as its own `CHANGELOG.md` entry
in the release that drops it.
