# /rhize-ops:rhize-setup

Fleet-level setup wizard. Discovers every installed Rhize plugin's manifest
(`<plugin>/setup/manifest.json`), validates complete evaluation coverage, establishes the user's
existing implementation as a benchmark baseline, records a privacy-safe capture policy, shows
what guardrails are already wired versus merely available, and lets the user turn hooks on for
the **current project** without hand-writing hooks JSON or hunting for
`${CLAUDE_PLUGIN_ROOT}` paths.

Installing a plugin never auto-wires guardrail hooks, starts capture, runs networked/paid work,
or schedules a job. This wizard offers policy and hook choices separately, and active capture also
requires a verified component adapter. Free deterministic validation is recommended immediately;
every other effect remains an explicit user choice.

## Tier semantics

- **T3 (advisory)** — injects `hookSpecificOutput.additionalContext` into the model's context.
  Never blocks a tool call; just adds guidance.
- **T4 (blocking)** — exits 2 to block the tool call outright, with its stderr shown to the
  model as the reason.

## Steps

### 1. Discover installed Rhize plugins

- Look for the installed marketplace clone at `~/.claude/plugins/marketplaces/rhize-plugins/`.
  If present, enumerate its top-level plugin directories — anything containing a
  `.claude-plugin/plugin.json`.
- Cross-reference `enabledPlugins` in `~/.claude/settings.json`. Only plugins with
  `"<name>@rhize-plugins": true` are active; note disabled ones explicitly in the final report
  (`skipped — disabled`) rather than silently omitting them.
- If the marketplace clone is absent, fall back to the dev repo: use the current working
  directory if it has `.claude-plugin/marketplace.json` at its root (i.e. you're running this
  from inside the `rhize-plugins` repo itself), otherwise ask the user for the repo path — don't
  guess a location.

### 2. Read manifests + effective hook state

- For each discovered (and enabled) plugin, read `<plugin-dir>/setup/manifest.json` if it
  exists. A plugin without one simply contributes nothing to the menu — that's not an error.
- Accept schema 1 for its existing hook/dependency fields, but report
  `evaluation catalog missing` and do not call evaluation coverage complete. Schema 2 requires
  a matching `evaluations` binding to the central `rhize-evaluations-v1` catalog. Skip (with a
  warning in the final report) any manifest that doesn't parse or doesn't match the schema
  documented in `rhize-ops/README.md`.
- Read the **target project's** (the directory you're running this command in) effective hook
  state — this is what's actually live, not what a manifest merely declares:
  - `.claude/settings.json` `hooks` block (tracked, shared with the team)
  - `.claude/settings.local.json` `hooks` block (untracked, personal)
  - `env.ECC_DISABLED_HOOKS` (comma-separated hook-id list) in either settings file — a hook can
    be wired and still be neutered by this
  - `env.ECC_GATEGUARD` — `"off"` disables ECC's own gate hooks specifically (informational for
    non-ECC items; doesn't affect them)
- For each manifest item, resolve whether an existing hook entry's `command` (after resolving
  `${CLAUDE_PLUGIN_ROOT}` to this plugin's actual install path) already appears under the
  matching `event`/`matcher` in either settings file. Label every item as one of:
  `not wired` · `wired` · `wired but disabled (ECC_DISABLED_HOOKS)` · `wired but ECC_GATEGUARD=off`.

### 3. Dependency check

- For every discovered (and enabled) plugin's manifest that has a top-level `"dependencies"`
  array (see `rhize-ops/README.md` → "Setup manifest schema"), probe each entry's presence
  according to its `"kind"`:
  - `plugin` — check `enabledPlugins` in `~/.claude/settings.json` for `"<name>@<marketplace>": true`,
    and confirm the plugin directory actually exists under the marketplace clone (or dev repo)
    found in step 1. Treat "listed but directory missing" the same as missing.
  - `cli` — `command -v <binary>` (use the dependency's `"name"` as the binary unless the
    manifest text makes the actual command clear, e.g. "@rhize/skill-forge" → `command -v npx`
    plus `npm ls -g @rhize/skill-forge` or a quick `npx --no-install @rhize/skill-forge --version`).
  - `mcp` — check whether the server is listed among the currently configured/connected MCP
    servers (the plugin's own `.mcp.json` if bundled, or the user/session MCP config).
  - `data` — check the referenced file/credential exists (env var set, file present at the
    stated path).
- Print a present/missing table before touching the opt-in menu:

  | plugin | dependency | kind | required | status |
  | --- | --- | --- | --- | --- |
  | `<plugin>` | `<name>` | `plugin\|cli\|mcp\|data` | yes/no | `present` / `missing` |

- For every entry marked `missing`, use `AskUserQuestion` (one question per missing dependency,
  or grouped by plugin if there are several) offering exactly these choices:
  1. **Install the upstream now — recommended.** Show the dependency's one-line `"purpose"`
     as the reason. If installing is itself automatable (e.g. a plugin install command, an
     `npm install -g` for a CLI), do it on confirmation; otherwise tell the user the exact
     command/step and wait for them to confirm it's done before continuing.
  2. **Proceed degraded.** State the dependency's `"degradedBehavior"` verbatim so the user
     knows exactly what won't work.
  3. **Adopt the replacement suggestion** (only offered when the manifest entry has a
     `"replacement"` object). Show `replacement.suggestion` as the option, and display
     `replacement.warning` **verbatim** as part of the option's description — never paraphrase
     or shorten that warning, it's the reinventing-the-wheel caveat the manifest author wrote
     deliberately.
- Record every choice (dependency name, choice made, and — for "proceed degraded" or "adopt
  replacement" — the exact text shown) for the final report in step 6. A `"required": true`
  dependency the user chooses to leave missing (degraded or replaced) still gets recorded
  faithfully; the wizard doesn't refuse to continue, it just carries that risk into the report.

### 4. Establish evaluation baselines and capture

Do this before the hook picker. When the user invokes the command with `--evaluations`, skip the
hook picker after this phase. When `--plugin <name>` is supplied, scope evaluation questions and
execution to that component while preserving the other components' existing local state.

1. Resolve the marketplace/repository root from step 1 and run the central validator using the
   actual `rhize-ops` plugin path:

   ```text
   python3 <rhize-ops-root>/scripts/evaluation_setup.py validate --repo-root <marketplace-or-repo-root>
   ```

   Stop the evaluation phase on a validation failure. Do not bypass an omitted skill, unsafe
   runner path, unknown dependency kind, or missing benchmark protocol.
2. Present the catalog grouped by product domain. The canonical grouping is:
   - **Knowledge & Context:** Obsidian Second Brain, Rhize Context Manager, Procedural Memory.
   - **Operations:** Rhize Ops, Rhize Tasks.
   - **Engineering & Delivery:** Rhize Devflow, Project Launcher, Rhize Cowork.
   - **Content Intelligence:** SEO/AEO/GEO.
   - **Toolchain:** SkillForge.

   Rhize Ops owns this setup engine; that does not make every component an operations product.
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
5. Write the answers to a private temporary decisions JSON, invoke
   `evaluation_setup.py setup` with the selected component(s), capture mode, decisions file, and
   `--run-free-smoke`, then remove the temporary file. The setup engine writes only to
   `~/.rhize/evals/` (0700 directories, 0600 files). It executes only cataloged free/offline
   Python runners with no shell interpolation and an environment allowlist.
6. Configuration alone does not instrument a component. Verify that its eligible execution path
   actually reads the policy and invokes `reserve` before work plus `finalize` afterward. Until
   that adapter exists and is enabled, report `capture_adapter_unavailable`; never call capture
   active merely because `aggressive_local` was recorded.
7. Treat SkillForge as `blocked — explicit checkout or binary required` until the user supplies
   that input. Never benchmark whichever executable happens to be first on PATH.
8. Do not run a controlled live cohort during installation merely because a protocol exists.
   Offer the three-pair seed separately after the deterministic smoke, with literal authorization
   for any networked, credentialed, paid, scheduled, or externally mutating effect.

### 5. Present the opt-in menu

- Use `AskUserQuestion` with `multiSelect: true`. Group questions by plugin (one question block
  per plugin, or a combined block if the total item count is small).
- Each option's label is the item's `title`; its description is
  `<tier> · <event>[/<matcher>] — <description>`. Append `" (recommended)"` to the title for any
  item with `"default": true` in its manifest — `AskUserQuestion` itself has no pre-selection
  mechanism, so this is how the recommendation surfaces.
- Items already labeled `wired` in step 2 are shown in the final report table for visibility but
  are **not** re-offered as toggles unless the user explicitly asks to review already-wired
  items.

### 6. Wire selected items

For every newly selected item, in order:

1. **Resolve** `${CLAUDE_PLUGIN_ROOT}` in the item's `command` to that plugin's real installed
   path from step 1 (the marketplace clone directory, or the dev repo path).
2. **Smoke-test** the resolved command before wiring anything. For `PreToolUse`/`PostToolUse`
   items (which read a tool-call payload from stdin):
   ```
   echo '{"tool_name":"Write","tool_input":{"file_path":"/tmp/x"}}' | <resolved command>
   ```
   For items on events with no stdin contract (`SessionStart`, `Stop`, `UserPromptSubmit`), run
   with empty stdin instead: `echo '' | <resolved command>`. In both cases, require **exit code
   0**. **Never wire an item that fails this smoke test** — record it as `smoke-test failed` in
   the final table instead of silently skipping it.
3. On a passing smoke test, append a hook entry to the target project's `.claude/settings.json`
   `hooks` block, in the correct Claude Code hooks JSON shape:
   ```json
   {
     "matcher": "<item.matcher, or omit the key entirely if the item has none>",
     "hooks": [{ "type": "command", "command": "<resolved command>" }]
   }
   ```
   Merge this into any existing array under `hooks.<event>` — never overwrite the file's other
   hook entries, and never touch `.claude/settings.local.json` (this wizard always writes to the
   tracked file so the guardrail is shared with the rest of the team, not just wired locally).

### 7. Print the final report

Two tables. First, the dependency-check outcome from step 3 — one row per manifest dependency
across every discovered plugin, including entries that were already `present`:

| plugin | dependency | required | status | choice |
| --- | --- | --- | --- | --- |
| `<plugin>` | `<name>` | yes/no | `present` / `missing` | `—` (present) / `installed` / `proceed degraded` / `adopted replacement` |

Then the opt-in hook table — one row per manifest item across every discovered plugin (wired or
not):

| item | tier | event/matcher | wired where | status |
| --- | --- | --- | --- | --- |
| `<id>` | T3/T4 | `<event>`/`<matcher or —>` | `.claude/settings.json` or `—` | `wired` / `already wired` / `skipped (user declined)` / `smoke-test failed` / `plugin disabled` |

Keep the table complete even for items the user didn't select — that's what makes it a fleet-wide
guardrail inventory, not just a summary of this run's changes.

Finish with an evaluation table:

| component | domain | skills | deterministic seed | Arm A | capture policy | capture status / blocker |
| --- | --- | ---: | --- | --- | --- | --- |
| `<component>` | `<domain>` | `<count>` | `pass/fail/not run/blocked` | `confirmed/greenfield/declined/unconfirmed` | `aggressive local/deterministic only/disabled` | `active/inactive/<reason>` |

Do not merge deterministic coverage, observational natural receipts, and controlled benefit
evidence into one status. A benefit claim remains unavailable until its matched controlled cohort
passes the predeclared gates.

## Manifest schema reference

See `rhize-ops/README.md` → "Setup manifest schema" for the canonical `setup/manifest.json`
shape this command reads. `rhize-ops` owns that spec; other plugins ship manifests conforming to
it, not the other way around.
