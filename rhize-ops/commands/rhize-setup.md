---
description: Fleet-level setup wizard — pick your plugins, run their own expert wizards, establish evaluation baselines, and wire opt-in guardrail hooks
---

# /rhize-ops:rhize-setup

**One-release compatibility adapter (repo-shape R-B, Codex F6).** This wizard's canonical home
moved to the `rhize-core` plugin as `/rhize-core:setup`. If `rhize-core` is installed — its
`.claude-plugin/plugin.json` exists under the discovered marketplace root, or `enabledPlugins` in
`~/.claude/settings.json` lists `rhize-core@<marketplace>`: `true` — invoke `rhize-core:setup` via
the **Skill tool** with `$ARGUMENTS` and **stop**; the rest of this file never runs. Otherwise,
continue with the full orchestrator prose below (a verbatim copy of `rhize-core/commands/
setup.md`, kept byte-identical and drift-tested by `tests/config-lint/
test_platform_fallback_drift.py`) so this plugin keeps working standalone, and at the end
(Phase 8), recommend `claude plugin install rhize-core@rhize-plugins` so the next run uses the
canonical, actively-developed copy. This adapter — and the four fallback scripts, the fallback
`setup/evaluation-catalog.json`, `templates/claude-home.gitignore`, and `schemas/*.json` it
depends on — are scheduled for removal in the next `rhize-ops` minor version; see CHANGELOG.md.

---

# /rhize-core:setup

Fleet-level setup wizard. Discovers installed Rhize plugins, lets you pick which ones to set up
this run, then orchestrates: each selected plugin's own expert setup wizard (when it has one), a
shared dependency and version-control preflight, evaluation-coverage baselines, and an opt-in
guardrail-hook menu — finishing with one report of what's wired, what's tracked, and what to
verify next.

Installing a plugin never auto-wires guardrail hooks, starts capture, runs networked/paid work,
or schedules a job. This wizard offers policy and hook choices separately, and active capture also
requires a verified component adapter. Free deterministic validation is recommended immediately;
every other effect remains an explicit user choice.

Every deterministic step below calls `rhize-core/scripts/setup_orchestrator.py`,
`evaluation_setup.py`, or `git_preflight.py` by path — this file supplies the questions,
confirmations, and Skill-tool invocations, not the discovery, path-resolution, or settings-merge
logic itself.

## Tier semantics

- **T3 (advisory)** — injects `hookSpecificOutput.additionalContext` into the model's context.
  Never blocks a tool call; just adds guidance.
- **T4 (blocking)** — exits 2 to block the tool call outright, with its stderr shown to the
  model as the reason.

## Phase 0 — Flags

- `--plugin <name>` (repeatable) — pre-select a plugin, skipping it in the Phase 2 picker.
- `--all` — pre-select every enabled plugin; skips the Phase 2 picker entirely.
- `--evaluations` — after Phase 5 (Evaluation baselines) completes for the selected plugins,
  **stop** — do not run Phase 6 (Hooks) or later. This is what a plugin wizard's own handshake
  suggests when run standalone (see `devflow-setup.md`/`context-setup.md`).
- `--skip-plugin-wizards` — run every phase except Phase 4 (useful for re-running the hook menu
  or evaluation baselines without re-running every plugin's interview wizard).
- Any other flag is rejected, printing this list.
- `--from-rhize-setup` is never accepted here — that token is what this orchestrator *passes to*
  the plugin wizards it invokes in Phase 4, so they know to stop instead of re-invoking this
  command. Accepting it here would let a plugin wizard's suggestion loop back into itself.

Generate one run id for the whole invocation and reuse it in every subcommand call below — the
run state and the final report are keyed by it:

```bash
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
```

## Phase 1 — Discover

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/setup_orchestrator.py" discover --json --run "$RUN_ID"
```

Read `source` (`kind`: `"dev-repo"` or `"marketplace-clone"`; `clone_name`; `portability`),
`plugins[]`, and `warnings[]`. For each plugin: `enabled`/`enabled_reason`; `clone_version` vs
`installed_version` (`clone_ahead_of_installed: true` means `claude plugin marketplace update`
ran more recently than `claude plugin update` — mention it once in Phase 8, it isn't blocking);
`manifest.evaluation_status` (`"missing"` for a schema-1 manifest — flag it, never count it as
evaluation coverage); and each item's `status` (`not wired` / `wired` / `wired but disabled
(ECC_DISABLED_HOOKS)` / `wired but ECC_GATEGUARD=off` / `wired (machine-specific path)` — the
last one means an existing entry already does the job with an absolute, non-portable path; never
touch it, just don't re-offer it).

## Phase 2 — Select

Use `AskUserQuestion` (`multiSelect: true`) listing every plugin with `enabled: true`. Each
option's description is that plugin's own `.claude-plugin/plugin.json` `description`, plus —
when its manifest declares a `wizard` — the wizard's `when` tag in parentheses (e.g.
"(required)"). Default: every enabled plugin pre-selected (`--plugin`/`--all` on the invocation
line pre-answer this question instead of asking). Plugins with `enabled: false` are never
offered; they appear in the final report as `skipped — disabled`. Plugins the user leaves
unchecked appear as `skipped — not selected` and get no further phases.

## Phase 3 — Shared preflight

Run once for the union of every selected plugin, not once per plugin.

### 3a. Dependency check

For every selected plugin's `manifest.dependencies` (already in the Phase 1 JSON — don't
re-read manifests), probe each entry's presence according to its `"kind"`:

- `plugin` — check `enabledPlugins` in `~/.claude/settings.json` for
  `"<name>@<marketplace>": true`, and confirm the plugin directory exists under the source root
  from Phase 1. Treat "listed but directory missing" the same as missing.
- `cli` — `command -v <binary>` (use the dependency's `"binary"` field, falling back to a
  slugified `"name"` only when `"binary"` is absent).
- `mcp` — check whether the server is listed among the currently configured/connected MCP
  servers (the plugin's own `.mcp.json` if bundled, or the user/session MCP config).
- `data` — check the referenced file/credential exists (env var set, file present at the
  stated path).

Print a present/missing table before asking anything:

| plugin | dependency | kind | required | status |
| --- | --- | --- | --- | --- |
| `<plugin>` | `<name>` | `plugin\|cli\|mcp\|data` | yes/no | `present` / `missing` |

For every entry marked `missing`, use `AskUserQuestion` (one question per missing dependency, or
grouped by plugin if there are several) offering exactly these choices:

1. **Install the upstream now — recommended.** Show the dependency's one-line `"purpose"` as
   the reason. If installing is itself automatable (e.g. a plugin install command, an
   `npm install -g` for a CLI), do it on confirmation; otherwise tell the user the exact
   command/step and wait for them to confirm it's done before continuing.
2. **Proceed degraded.** State the dependency's `"degradedBehavior"` verbatim so the user knows
   exactly what won't work.
3. **Adopt the replacement suggestion** (only offered when the manifest entry has a
   `"replacement"` object). Show `replacement.suggestion` as the option, and display
   `replacement.warning` **verbatim** — never paraphrase or shorten it.

Record every choice for Phase 8, then persist the table:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/setup_orchestrator.py" report record --run "$RUN_ID" \
  --section dependency_check --data <path-to-a-json-file-shaped-like-{"rows":[...]}>
```

### 3b. Version-control preflight

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/git_preflight.py" report --project "$(pwd)" --json
```

For each row that is not `rollback_ready`, one `AskUserQuestion`:

1. **Track now — recommended** (existing paths inside a work tree): show the exact commands
   `git_preflight.py track` will run, note `other_staged` if non-zero, and on confirmation call:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/git_preflight.py" track \
     --path <path> --message "chore(setup): baseline before rhize-setup"
   ```
2. **Proceed without version control** — recorded verbatim in the report.
3. **Show the recipe** (`NOT_IN_REPO` rows, including `~/.claude`): print the commands from
   `rhize-core/README.md` → Rollback, using the shipped allowlist template
   `rhize-core/templates/claude-home.gitignore`, then pause and re-run the `report` command above
   to verify before continuing. **Never run `git init` on `~/.claude` yourself.**

Persist the resulting table the same way as 3a, under `--section version_control`.

### 3c. Skill-map install

Only when `rhize-context-manager` is among the selected plugins:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/setup_orchestrator.py" install-skill-map \
  --source <Phase 1 source.root> --run "$RUN_ID"
```

Read `overlay_status` — `"local overlay unavailable in installed mode"` is expected and fine
when running from an installed plugin (no `build_local_skill_map.py` available at that source
root); `context-setup` keeps its config-only boundary and is never the one to install this.

### 3d. skill-forge init hint

If `npx --no-install @rhize/skill-forge --version` succeeds but
`~/.skill-forge/config.json` is absent, print "run `npx @rhize/skill-forge init`" and pause for
the user to run it (or explicitly skip) before continuing. This wizard never runs `init` for
them — skill-forge's own init has its own interactive Git-preflight prompts.

### 3e. Artifacts baseline snapshot

Before any plugin wizard or hook write happens this run, snapshot what already exists:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/setup_orchestrator.py" artifacts snapshot --before \
  --run "$RUN_ID" --plugin <each selected plugin, repeated>
```

## Phase 4 — Plugin wizards

For every selected plugin whose Phase 1 manifest declares a `wizard`, in this fixed order:
rhize-ops → rhize-context-manager → rhize-devflow → rhize-tasks → obsidian-second-brain → every
other selected plugin with a wizard, alphabetically.

For each:

- State the wizard's `purpose` and `when` tag.
- `when: "required"` runs without asking. `when: "optional"`/`"recommended"` ask once
  (run it now / skip).
- On "run", invoke `<wizard.skill>` via the **Skill tool** with `args: wizard.args` (the manifest
  default is `["--from-rhize-setup"]` when `args` is omitted) — this is exactly the marker the
  wizard's own handshake step checks for to avoid looping back into this command.
- Record `completed` / `skipped (user)` / `failed: <reason>` per plugin.
- A **failed `required`** wizard marks that plugin `blocked — required setup failed`: skip its
  Phase 5 and Phase 6 entirely, and say why in Phase 8. A failed optional/recommended wizard only
  annotates the report — the plugin's other phases still run.

Persist the outcome the same way as 3a, under `--section plugin_wizards`.

## Phase 5 — Evaluation baselines

Do this for every selected, non-`blocked` plugin. When the user invoked this command with
`--evaluations`, **stop after this phase** — do not run Phase 6 or later.

1. Resolve the marketplace/repository root from Phase 1 and run the central validator:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/evaluation_setup.py" validate --repo-root <source.root>
   ```

   Stop the evaluation phase on a validation failure. Do not bypass an omitted skill, unsafe
   runner path, unknown dependency kind, or missing benchmark protocol.
2. Present the catalog grouped by product domain. The canonical grouping is:
   - **Platform:** Rhize Core (this setup engine itself).
   - **Knowledge & Context:** Obsidian Second Brain, Rhize Context Manager, Procedural Memory.
   - **Operations:** Rhize Ops, Rhize Tasks.
   - **Engineering & Delivery:** Rhize Devflow, Project Launcher, Rhize Cowork.
   - **Content Intelligence:** SEO/AEO/GEO.
   - **Toolchain:** SkillForge.

   Rhize Core owns this setup engine and is itself the Platform domain's one component; every
   other domain groups by subject matter, not by which plugin happens to run the engine.
3. For each selected benchmark, ask the user to classify Arm A as one of:
   - an exact existing manual workflow/checklist;
   - an exact existing script, command, skill, or tool;
   - no existing implementation (`greenfield`);
   - decline baseline establishment.

   A confirmed incumbent requires a non-empty label, version/SHA/date, and validation method.
   Never infer these fields. `greenfield` records no invented identity; the first verified
   production version can become a future frozen baseline.
4. Ask for one capture policy:
   - **Aggressive local capture (`aggressive_local`) — recommended:** reserve a privacy-safe
     receipt for every eligible execution and finalize it immediately.
   - **Deterministic gates only (`deterministic_only`):** run local change/setup gates without
     observing natural runs.
   - **Disabled (`disabled`):** retain the user's explicit choice and make no evidence claim.
5. Write the answers to a private temporary decisions JSON, invoke `evaluation_setup.py setup`
   with the selected component(s), capture mode, decisions file, and `--run-free-smoke`, then
   remove the temporary file. The setup engine writes only to `~/.rhize/evals/` (0700
   directories, 0600 files). It executes only cataloged free/offline Python runners with no
   shell interpolation and an environment allowlist.
6. Configuration alone does not instrument a component. Verify that its eligible execution path
   actually reads the policy and invokes `reserve` before work plus `finalize` afterward. Until
   that adapter exists and is enabled, report `capture_adapter_unavailable`; never call capture
   active merely because `aggressive_local` was recorded.
7. Treat SkillForge as `blocked — explicit checkout or binary required` until the user supplies
   that input. Never benchmark whichever executable happens to be first on PATH.
8. Do not run a controlled live cohort during installation merely because a protocol exists.
   Offer the three-pair seed separately after the deterministic smoke, with literal authorization
   for any networked, credentialed, paid, scheduled, or externally mutating effect.

Persist the resulting table the same way as 3a, under `--section evaluations`.

## Phase 6 — Hooks

For every selected, non-`blocked` plugin's items with `status: "not wired"` in Phase 1:

1. Use `AskUserQuestion` with `multiSelect: true`. Group questions by plugin (one question block
   per plugin, or a combined block if the total item count is small). Each option's label is the
   item's `title`; its description is `<tier> · <event>[/<matcher>] — <description>`. Append
   `" (recommended)"` to the title for any item with `"default": true` — `AskUserQuestion` has no
   pre-selection mechanism, so this is how the recommendation surfaces. Items already labeled
   `wired`/`wired but disabled`/`wired but ECC_GATEGUARD=off`/`wired (machine-specific path)` in
   Phase 1 are shown in the final report for visibility but not re-offered.
2. For every newly selected item:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/setup_orchestrator.py" hooks plan \
     --plugin <plugin> --item <id> --json --run "$RUN_ID"
   ```
   Read `smoke_test.passed`. **Never proceed to wire an item whose smoke test failed** — record
   it as `smoke-test failed` in the final table instead of silently skipping it.
3. Collect every passing plan's `{plugin, item, event, matcher, resolved_command}` into one JSON
   array and apply them together in a single call:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/setup_orchestrator.py" hooks apply \
     --plan <path-to-the-plans-array.json> --run "$RUN_ID"
   ```
   This merges into the target project's tracked `.claude/settings.json` `hooks` block only —
   never `.claude/settings.local.json` — and never rewrites an existing entry, including a
   `wired (machine-specific path)` one.

## Phase 7 — Post-write tracking

Re-run the version-control preflight, scoped to whatever this run just created (e.g.
`.claude/settings.json` if Phase 6 wired anything for the first time, or a plugin wizard's own
config file):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/git_preflight.py" report --project "$(pwd)" \
  --paths <path-this-run-created> --json
```

Offer the same track/proceed/recipe choices as 3b, running any confirmed `track` through
`git_preflight.py` — never a raw `git` command written into this file.

## Phase 8 — Report

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/setup_orchestrator.py" artifacts snapshot --after \
  --run "$RUN_ID" --plugin <each selected plugin, repeated>
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/setup_orchestrator.py" report --run "$RUN_ID"
```

Print the rendered tables from `report` (dependency, hook, evaluation, version-control, and
artifacts — `declared | present-before | present-after`, never claiming "written this run" for a
row that already existed). Do not merge deterministic coverage, observational natural receipts,
and controlled benefit evidence into one status — a benefit claim remains unavailable until its
matched controlled cohort passes the predeclared gates.

Finish with one "verify with `<doctor>`" line per selected plugin whose manifest declares a
`doctor`: `kind: "skill"` → tell the user to run that command; `kind: "shell"` → print the exact
command line, never execute it yourself.

## Manifest schema reference

See `rhize-core/README.md` → "Setup manifest schema" for the canonical `setup/manifest.json`
shape this command reads (schema 3: the same `items`/`dependencies`/`evaluations` as schema 2,
plus the optional `wizard`, `doctor`, and `artifacts` blocks this wizard drives Phases 4 and 8
from). `rhize-core` owns that spec; other plugins ship manifests conforming to it, not the other
way around.
