# /rhize-ops:rhize-setup

Fleet-level guardrail wizard. Discovers every installed Rhize plugin's opt-in hook catalog
(`<plugin>/setup/manifest.json`), shows you what's already wired versus merely available, and
lets you turn hooks on for the **current project** by editing its `.claude/settings.json` —
without hand-writing hooks JSON or hunting for `${CLAUDE_PLUGIN_ROOT}` paths.

Installing a plugin never auto-wires any of its guardrail hooks — a manifest item only fires
once this wizard (or a manual edit) adds it to a project's `.claude/settings.json`. That's the
whole point of the manifest: it's a catalog of *available* hooks, not a set of defaults.

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
- Validate each manifest has `"schema": 1` and a `"plugin"` field matching the directory name;
  skip (with a warning in the final report) any manifest that doesn't parse or doesn't match
  the schema documented in `rhize-ops/README.md`.
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

### 3. Present the opt-in menu

- Use `AskUserQuestion` with `multiSelect: true`. Group questions by plugin (one question block
  per plugin, or a combined block if the total item count is small).
- Each option's label is the item's `title`; its description is
  `<tier> · <event>[/<matcher>] — <description>`. Append `" (recommended)"` to the title for any
  item with `"default": true` in its manifest — `AskUserQuestion` itself has no pre-selection
  mechanism, so this is how the recommendation surfaces.
- Items already labeled `wired` in step 2 are shown in the final report table for visibility but
  are **not** re-offered as toggles unless the user explicitly asks to review already-wired
  items.

### 4. Wire selected items

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

### 5. Print the final tier table

One row per manifest item across every discovered plugin (wired or not), in this shape:

| item | tier | event/matcher | wired where | status |
| --- | --- | --- | --- | --- |
| `<id>` | T3/T4 | `<event>`/`<matcher or —>` | `.claude/settings.json` or `—` | `wired` / `already wired` / `skipped (user declined)` / `smoke-test failed` / `plugin disabled` |

Keep the table complete even for items the user didn't select — that's what makes it a fleet-wide
guardrail inventory, not just a summary of this run's changes.

## Manifest schema reference

See `rhize-ops/README.md` → "Setup manifest schema" for the canonical `setup/manifest.json`
shape this command reads. `rhize-ops` owns that spec; other plugins ship manifests conforming to
it, not the other way around.
