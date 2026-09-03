# rhize-core

Rhize Media's **marketplace control plane** — the one command that discovers every Rhize plugin
you have installed, runs each plugin's own expert setup wizard, establishes free/offline
evaluation-coverage baselines, and offers an opt-in, smoke-tested guardrail-hook menu. Installing
this plugin never starts capture, schedules work, runs live/paid benchmarks, or wires a hook by
itself — every effect the wizard offers is an explicit user choice.

This plugin ships no skills of its own; it is pure infrastructure other plugins build on. It grew
out of `rhize-ops` (repo-shape R-B, 2026-09) once the setup engine outgrew being one operations
plugin's side project — `rhize-ops` keeps a working, drift-tested fallback copy of this wizard for
one release (see [Compatibility](#compatibility-with-rhize-ops-one-release-window) below).

## Setup

`/rhize-core:setup` is itself the fleet-level setup wizard — run it whenever you want to review or
change which plugins are set up, which plugin guardrail hooks are active in a project, or refresh
evaluation baselines. Nothing about installing this plugin requires running it first; other
plugins' commands and skills work without it, and only lose the one-stop fleet workflow.

Claude Code loads the thin command plus the four platform scripts from `.claude-plugin/
plugin.json`. Codex loads the same metadata from `.codex-plugin/plugin.json`. After installing or
updating either host, start a fresh session before checking discovery so a previously cached
plugin snapshot is not mistaken for the release.

## Skills

<!-- SKILL-MAP:BEGIN -->
| Skill | Description | Topics |
| --- | --- | --- |
<!-- SKILL-MAP:END -->

rhize-core ships no skills — see [Commands](#commands) for its one command, and the
[Evaluation setup engine](#evaluation-setup-engine) section for the deterministic interface behind
it.

## Commands

### `/setup`

Fleet-level setup wizard. Discovers installed plugins, lets you pick which ones to set up this
run, then orchestrates eight phases: discover → select → a shared dependency/version-control/
skill-map preflight → each selected plugin's own expert setup wizard (invoked via the Skill
tool) → evaluation-coverage baselines → an opt-in guardrail-hook menu (smoke-tested before
anything is wired) → post-write version-control tracking → one final report. Installation alone
never starts capture, schedules work, runs live/paid benchmarks, or wires hooks — every effect is
an explicit choice. `rhize-core/scripts/setup_orchestrator.py` does the deterministic
discovery/path-resolution/settings-merge work; the command itself only asks questions,
confirms choices, and invokes plugin wizards. See `rhize-core/commands/setup.md` for the
full phase-by-phase spec.

**Invoked as:** `/rhize-core:setup`

### What setup writes

Every file or directory a plugin's setup wizard (or day-to-day use) can write is declared in
that plugin's `setup/manifest.json` `artifacts` array and rendered into one table by
`rhize-core/scripts/setup_artifacts.py --markdown` — see
[`docs/setup-artifacts.md`](./docs/setup-artifacts.md) for the full list (artifact, producer,
path, how to view, lifetime, confidentiality, source, and whether it's tracked). Nothing on that
list is written just by installing a plugin.

### Rollback

Git is the rollback story for everything the plugins write into your
project's `.claude/` directory or your home `~/.claude/` config. `skill-forge
refine rollback <backup-id>` only undoes a `skill-forge refine` promotion —
for hook entries, skills, commands, and `CLAUDE.md` edits, a Git commit is
the only way back.

Check where you stand — tracked/dirty/committed/missing, plus other staged
files, so nothing you didn't ask for gets swept into a commit:

```bash
python3 rhize-core/scripts/git_preflight.py report --project /path/to/project
```

Nothing here runs `git init` on `~/.claude` for you — that's your call, since
it's easy to commit the wrong things (transcripts, plugin caches, tokens in
`settings.json`) into a directory that big. The recipe:

```bash
git init ~/.claude
cp rhize-core/templates/claude-home.gitignore ~/.claude/.gitignore
# review the .gitignore, then:
cd ~/.claude && git add .gitignore skills commands agents hooks CLAUDE.md
git commit -m "chore: baseline before customization"
```

## Setup manifest schema

`rhize-core` owns this spec. Every custom Rhize plugin ships a `setup/manifest.json` so the central
wizard can account for its evaluation coverage; plugins with opt-in guardrails also declare them in
the same file. Shipping a manifest never starts capture or auto-wires anything.

```jsonc
{
  "schema": 3,
  "plugin": "<plugin-directory-name>",
  "items": [
    {
      "id": "kebab-id",                                       // stable, unique within the plugin
      "title": "Human-readable name shown in the picker",
      "tier": "T3",                                           // "T3" (advisory) | "T4" (blocking)
      "event": "PreToolUse",                                  // PreToolUse | PostToolUse | SessionStart | Stop | UserPromptSubmit
      "matcher": "Write|Edit",                                // omit the key entirely if N/A (e.g. SessionStart)
      "command": "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/x.sh",  // resolved to the plugin's real install path at wire time
      "description": "One line shown next to the tier in the picker",
      "default": false                                        // true = wizard marks it "(recommended)"; never pre-selects it
    }
  ],
  "dependencies": [                                           // always present; may be empty
    {
      "name": "Human-readable dependency name",
      "kind": "plugin",                                       // plugin | cli | mcp | data | runtime | platform
      "capability": "kebab-capability-slug",                  // scopes degradation to exactly this capability
      "binary": "executable-name",                            // kind: "cli" only — see below
      "purpose": "One line: what this unlocks",
      "required": false,                                      // false = plugin degrades gracefully without it
      "degradedBehavior": "What happens without it",
      "replacement": {                                        // optional — only when a DIY alternative is plausible
        "suggestion": "The custom/DIY alternative",
        "warning": "Explicit reinventing-the-wheel caveat — replacing a maintained upstream means taking on its maintenance and forgoing its updates; recommend installing the upstream outright"
      }
    }
  ],
  "wizard": {                                                 // optional — declares this plugin's own expert setup wizard
    "skill": "<plugin>:<command>",                            // a plugin:command the Skill tool can invoke
    "purpose": "One line: what running it does",
    "when": "recommended",                                    // "optional" | "recommended" | "required"
    "args": ["--from-rhize-setup"]                            // optional — this is the default when omitted
  },
  "doctor": {                                                 // optional — the verification step shown in the final report
    "kind": "skill",                                          // "skill" (a plugin:command) | "shell" (printed, never executed)
    "value": "<plugin>:doctor"
  },
  "artifacts": [                                              // optional; if "wizard" is present this must be non-empty
    {
      "id": "kebab-id",                                       // unique within the plugin
      "path": "<home>/.rhize/widgets/config.json",            // only <project>, <home>, <vault> placeholders; no absolute paths or ".."
      "kind": "file",                                         // file | directory | glob
      "purpose": "One line: what this is",
      "viewer": "cat ~/.rhize/widgets/config.json",           // how a human looks at it
      "lifetime": "persistent",                               // persistent | per-run | append-only | regenerated
      "confidentiality": "config",                            // none | config | personal | client | secret
      "source": "authored",                                   // authored | derived | transcript-derived
      "tracked": "outside-repo",                               // project | home | ignored | outside-repo
      "optional": false                                       // false = expected to exist once the plugin is used
    }
  ],
  "evaluations": {
    "catalog": "rhize-evaluations-v1",                       // central catalog owned by rhize-core
    "component": "<plugin-directory-name>"                    // must match plugin
  }
}
```

Schema 1 (`{schema, plugin, items, dependencies}` — no `evaluations` key at all) remains readable
for its hook and dependency inventory during migration, but it reports `evaluation catalog
missing` and cannot satisfy the release coverage gate. Schema 2 adds the exact five keys above
through `evaluations`, no more, no less. Schema 3 allows those same five keys plus any of the
optional `wizard`/`doctor`/`artifacts` blocks — nothing else. Both schema 2 and 3 keep runner
paths out of distributed component manifests: the central
`setup/evaluation-catalog.json` owns repository-relative paths, Arm A/Arm B definitions, domain
taxonomy, and suite metadata. The validator rejects absolute paths, traversal, escaping symlinks,
unknown runner types, networked/paid automatic suites, and timeouts above ten minutes.

**`wizard.skill` must be Skill-tool-invocable.** A plugin command is only reachable via the Skill
tool — with `args` substituted into its `$ARGUMENTS` — when its `.md` file opens with a `---`
frontmatter block containing a `description:` key (verified empirically 2026-09-02). The
validator checks both that `<plugin>/commands/<command>.md` exists and that it starts with that
frontmatter; a `wizard.skill` pointing at a slash-only command (no frontmatter) fails validation
rather than silently invoking nothing at wizard time. `args` defaults to
`["--from-rhize-setup"]` — the token a wizard's own command checks for to stop instead of
re-invoking `/rhize-core:setup` (see `devflow-setup.md`/`context-setup.md` for the pattern; the
token's name is a historical carry-over from before this engine split out of `rhize-ops`, and is
unchanged so every existing wizard command keeps working without a rename).

**`artifacts[].path` placeholders.** `<project>` is the directory `/rhize-core:setup` was run in;
`<home>` is `$HOME`; `<vault>` resolves through
`obsidian-second-brain/hooks/scripts/vault_resolve.py`'s `resolve_vault_paths()` — exactly one
vault must resolve for the placeholder to fill in, otherwise it's reported
`unresolved (<reason>)`. A path may use only one of these three placeholders, as its first
segment; absolute paths, `~`, and `..` are all rejected outright.

**A plugin that never writes anything personal or client-specific** (like `seo-aeo-geo`, which
only reads env vars) should still ship an explicit empty `"artifacts": []` rather than omitting
the key — that documents the absence instead of leaving it unstated. A plugin that declares a
`wizard`, though, must give it a *non-empty* `artifacts` array: a plugin with its own setup
wizard by definition writes something worth declaring.

The catalog's product taxonomy deliberately separates ownership from subject matter. Obsidian,
Context Manager, and Procedural Memory are **Knowledge & Context** components; Rhize Core owns
their shared setup/evidence engine and sits in its own **Platform** domain rather than folding
into any of the subject-matter domains it serves.

**Tier semantics:**
- **T3 — advisory.** The hook injects `hookSpecificOutput.additionalContext` and never blocks the tool call.
- **T4 — blocking.** The hook exits `2` to block the tool call, with stderr shown to the model as the reason.

**Dependencies:** any Rhize plugin can declare a top-level `"dependencies"`
array describing the external plugins, CLIs, MCP servers, or data files it relies on — separate
from the opt-in hooks in `"items"`. `/rhize-core:setup` reads this array (see the command's own
doc) to probe presence, print a status table, and offer install/degrade/replace choices before the
opt-in hook menu. `"required": false` means the plugin keeps working without it (describe exactly
how in `"degradedBehavior"`); `"required": true` means the dependent feature has no fallback path.
`"replacement"` is optional — include it only when a plausible DIY alternative exists, and always
pair the suggestion with a `"warning"` that names the maintenance tradeoff: replacing a maintained
upstream means taking on its maintenance and forgoing its updates, so the warning should recommend
installing the upstream outright rather than reinventing it.

**`kind: "cli"` detection:** an entry with `"kind": "cli"` is presence-checked with `shutil.which()`
against its `"binary"` field (the literal executable name expected on `PATH` — e.g. `"codegraph"`),
not against configured MCP servers. Omitting `"binary"` falls back to a slugified form of `"name"`,
so declare `"binary"` explicitly rather than relying on that inference. Every other kind (`mcp`,
`plugin`, `data`, `runtime`, `platform`) is detected by name-matching against configured MCP
servers (`.mcp.json`, `~/.claude.json`, `~/.codex/config.toml`) — see rhize-devflow's
`docs/codegraph-setup.md` for a worked `kind: "cli"` example end to end.

## Evaluation setup engine

`scripts/evaluation_setup.py` is the deterministic interface behind the wizard:

```bash
python3 rhize-core/scripts/evaluation_setup.py validate --repo-root /path/to/rhize-plugins
python3 rhize-core/scripts/evaluation_setup.py setup \
  --repo-root /path/to/rhize-plugins \
  --capture-mode deterministic_only \
  --run-free-smoke
python3 rhize-core/scripts/evaluation_setup.py audit
```

The `setup` command can be scoped with repeated `--plugin` flags and accepts a private
`--baseline-decisions` JSON produced by the interactive wizard. Confirmed baselines require an exact
label, version/SHA/date, and validation method. Greenfield and declined states contain no invented
identity. Reruns preserve unchanged baseline IDs and other components' state.

Aggressive local capture stores an HMAC fingerprint of the input, never the input or its path.
`reserve` appends a pending row before work; `finalize` appends a terminal row with strict common
metrics. Missing token/tool counters require an explicit unavailable reason. `audit` reports stale
pending reservations. Raw state stays under `~/.rhize/evals/` with 0700 directories and 0600 files.
Natural rows remain observational; only matched controlled cohorts can support benefit claims.
Recording `aggressive_local` is policy, not proof that a host lifecycle adapter is active. A
component reports capture as active only after its eligible execution path actually invokes
`reserve` before work and `finalize` afterward; otherwise setup must show
`capture_adapter_unavailable` rather than implying background collection.

**Wiring contract the wizard relies on:**
- Every `PreToolUse`/`PostToolUse` item's `command` must read the tool-call payload from stdin and exit `0` on a no-op smoke test (`echo '{"tool_name":"Write","tool_input":{"file_path":"/tmp/x"}}' | <command>`). Items on `SessionStart`/`Stop`/`UserPromptSubmit` are smoke-tested with empty stdin instead. The wizard refuses to wire anything that fails this check.
- `${CLAUDE_PLUGIN_ROOT}` in `command` is a template token — plugin authors write it literally; the wizard resolves it to the actual install path (marketplace clone or dev repo) at wire time. Don't hardcode an absolute path in a manifest.

## Compatibility with rhize-ops (one-release window)

Before this split, this engine shipped inside `rhize-ops` as `/rhize-ops:rhize-setup`.
`rhize-ops` keeps a **working, drift-tested fallback copy** for one release: its own
`commands/rhize-setup.md` checks whether `rhize-core` is installed and, if so, forwards to
`/rhize-core:setup` and stops; otherwise it runs the same orchestrator prose from its own
byte-identical fallback copies of the four platform scripts, `setup/evaluation-catalog.json`,
`templates/claude-home.gitignore`, and `schemas/*.json` (`tests/config-lint/
test_platform_fallback_drift.py` enforces the drift check and self-containment). See
[`docs/contract.md`](./docs/contract.md) for the exact stability contract this fallback and every
other consumer of this engine can rely on, and its deprecation policy.

Once `rhize-core` is installed, `/rhize-ops:rhize-setup` simply forwards here — install it with
`claude plugin install rhize-core@rhize-plugins`.
