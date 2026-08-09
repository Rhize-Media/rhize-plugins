# rhize-context-manager

Context engineering and optimization plugin: **compression, management, retrieval, and
storage**. It orchestrates the external context tools already in the Rhize stack (rather
than forking them) and ships a curated, safety-gated skill library.

## Design: orchestrate, don't vendor

Headroom, claude-mem, Serena, OpenWolf, RTK, CodeGraph, and Graphiti are living external
tools with their own release cycles. This plugin owns the *decision layer* — which tool
to use when, how they coexist, and how to health-check the stack — while the binaries
and their own hook plugins stay externally installed and updated.

## Skills

### Rhize-authored (orchestration layer)

| Skill | Purpose |
|---|---|
| `context-stack` | Routing + coexistence brain for the whole stack; encodes the Headroom / claude-mem / OpenWolf overlap watch policy |
| `context-engineering` | Session/memory/hygiene workflow (moved here from rhize-devflow v2.4.x) |
| `graphify` | Any input → knowledge graph (promoted from user-level skill) |
| `graphiti-memory` | Opt-in Graphiti temporal knowledge-graph memory: adoption guide + MCP wiring (NOT a dependency) |
| `refinement-pipeline` | Gated skill-refinement loop: headroom learn / claude-mem / skill-monitor signals → human-triaged queue → skill-forge evolve with auto-promote rules |
| `learning-curation` | Decide whether a session learning deserves persistence and where it should live |

### Curated third-party (ingested via skill-forge, safety-gated, provenance in [skills/SOURCES.md](skills/SOURCES.md))

From **muratcankoylan/Agent-Skills-for-Context-Engineering**: `context-fundamentals`,
`context-degradation`, `context-compression`, `context-optimization`, `memory-systems`,
`filesystem-context`, `tool-design`.

Per the marketplace curation rule, context/token budgeting, iterative retrieval, and
strategic compaction are NOT re-shipped here — `ecc@everything-claude-code` owns them.

Coverage per feature goal: compression (context-compression), retrieval/budgeting
(ecc's skills, by design), memory (memory-systems, graphiti-memory), degradation
(context-degradation), refinement (refinement-pipeline, learning-curation).

## Commands

| Command | Purpose |
|---|---|
| `/context-doctor` | Read-only health check of every layer (Headroom proxy, RTK savings, claude-mem dashboard, OpenWolf state, Serena/CodeGraph, Graphiti) + overlap flags. Persists each run to `~/.claude/context-manager/doctor/<YYYY-MM-DD-HHMM>.json`, prints a delta against the previous run, and — if the `ecc` plugin's `harness-audit` skill is available — chains into it as a final deeper pass (graceful one-line skip otherwise). |
| `/context-setup` | Repo-level setup wizard: scans the repo (`config_generator.py`), probes which stack layers are actually active, proposes a tailored per-repo enable/disable list with reasons, and on confirmation writes `~/.claude/rhize-context-manager/stack.config.json`. Owns stack **config** only — hook wiring is `/rhize-setup` (rhize-ops). |
| `/start` | Session bookend — resume from `STATE.md` with real memory (moved from rhize-devflow) |
| `/done` | Session bookend — verifier PASS + `STATE.md` update before commit (moved from rhize-devflow) |
| `/context-hygiene` | Mid-session context cleanup when a session gets heavy (moved from rhize-devflow) |
| `/impact-map` | Pre-feature impact mapping against the component registry (moved from rhize-devflow) |
| `/learn-harvest` | Harvest refinement signals (headroom learn dry-run, claude-mem, skill-monitor) into the pending queue — never writes skills or CLAUDE.md |
| `/skill-refine` | `review`: human triage of queued signals · `run`: gated skill-forge evolve pass with auto-promote for SKILL.md-only ALLOW verdicts |

`/start`, `/done`, `/context-hygiene`, and `/impact-map` are registered only under
`commands/` — the `skills/context-engineering/commands/` copies were removed
2026-08-04 (they had drifted behind: `commands/` had gained frontmatter, a verifier-
subagent step in `/done`, and a `STATE.md` update step that the skill-side copies
lacked). `skills/context-engineering/SKILL.md` now links to the `commands/` originals.

## Hooks

| Hook | Event | Purpose |
|---|---|---|
| `context-window-monitor.js` | `PreToolUse` (`Edit\|Write`) | Warns once per 10% band past 75% of the **real** context window |

This one hook is auto-wired in `hooks/hooks.json` — it ships active by default.

### Opt-in hooks (`setup/manifest.json`)

Four generalized hooks from `skills/context-engineering/hooks/` are declared in
`setup/manifest.json` as opt-in items (`default: false`) for `/rhize-setup` (rhize-ops)
to wire per-repo — they are **not** in `hooks/hooks.json` and do nothing until enabled.
They require project-specific files (`COMPONENT_REGISTRY.md`, `CURRENT_SPRINT.md`) to be
useful, so auto-wiring them for every repo would be noise.

| id | Event | Tier | Purpose |
|---|---|---|---|
| `session-init` | `SessionStart` | T3 (advisory) | Session banner: project name, sprint/registry freshness, active work item, uncommitted count |
| `duplicate-check` | `PreToolUse` (`Write`) | T4 (blocking, exit 2) | Blocks creating a new component/hook/utility whose name closely matches an existing `COMPONENT_REGISTRY.md` entry |
| `pre-commit-guard` | `PreToolUse` (`Bash`) | T3 (advisory) | On `git commit`, flags unstaged related files via `additionalContext` — never blocks |
| `skill-suggester` | `UserPromptSubmit` | T3 (advisory) | Pattern-matches the prompt and surfaces a suggested skill via `additionalContext` — never blocks |

`tier` follows the shared convention: T3 = advisory (never blocks, exits 0, must use
`hookSpecificOutput.additionalContext` to reach Claude on events where plain stdout
isn't auto-added to context), T4 = blocking (`exit 2`, stderr becomes the reason shown
to Claude). Verified 2026-08-04 against `code.claude.com/docs/en/hooks`: `SessionStart`
and `UserPromptSubmit` auto-add plain stdout as context, but `PreToolUse`/`PostToolUse`
advisory hooks do not — plain stdout/stderr on `exit 0` there is invisible to the model.
`pre-commit-guard.sh` and `skill-suggester.sh` were fixed to this contract 2026-08-04:
the former printed warnings to stderr on `exit 0` (never reached Claude), the latter both
read the wrong input field (`user_prompt` instead of `prompt` — a permanent no-op) and
wrote its suggestion to `systemMessage` (user-only, not `hookSpecificOutput.additionalContext`).

`setup/manifest.json` also declares a `dependencies` array (`@rhize/skill-forge`, `headroom`,
`ecc:harness-audit`, and the orchestrated stack tools) that the wizard's dependency check reads.

**Fleet setup:** `/rhize-ops:rhize-setup` is what actually wires these opt-in items and checks
`dependencies` for you — it requires the `rhize-ops` plugin. Without it, wire an item manually
per the snippet in [rhize-ops/README.md § Setup manifest
schema](../rhize-ops/README.md#setup-manifest-schema).

### Refinement-pipeline hooks (bundled, opt-in, not yet in `setup/manifest.json`)

Two more hooks arrived in `hooks/` on 2026-08-09, moved here from `rhize-devflow` (they
predate this plugin and were stranded there by the 2.5.0 command migration). Like the four
above they are **not** wired in `hooks/hooks.json` and require manual `.claude/settings.json`
wiring — they aren't in `setup/manifest.json` yet either, so `/rhize-setup` won't offer them
until that's added in a follow-up.

| Script | Event | Tier | Purpose |
|---|---|---|---|
| `refinement-pipeline__refinement-detector.sh` | `UserPromptSubmit` | T3 (advisory) | Detects "skill doesn't work" / "false positive" / "missing trigger" style phrasing and suggests `/rhize-context-manager:learn-harvest` → `/skill-refine review` |
| `refinement-pipeline__session-end.sh` | `Stop` | T3 (advisory) | At session end, if the session was substantial (>20 tool calls, any error, >60min, or >10 files touched — computed from the transcript JSONL), suggests capturing a refinement via the same two commands |

To enable one, add it to your project's `.claude/settings.json`, e.g.:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/refinement-pipeline__refinement-detector.sh"
          }
        ]
      }
    ]
  }
}
```

Both suggest the same next step — `/rhize-context-manager:learn-harvest` to queue the signal,
then `/skill-refine review` to triage it — rather than a bare `npx @rhize/skill-forge refine`,
which would skip the human-gate/machine-gate trust model the `refinement-pipeline` skill
documents.

### Why this replaces ECC's `suggest-compact`

ECC's hook sizes the window by sniffing the model id for a literal `[1m]`
marker, defaulting to 200k. Opus 5 has a 1M window and carries no marker, so it
divided ~195k by 200k and reported **97% when the true figure was 20%** —
verified against the client's own context readout on 2026-07-28. It self-corrects
only above 200k (its `tokens > 200_000 → assume 1M` fallback), so it is wrong for
the entire run below that and the error is invisible from the message alone.

A marker sniff can only detect windows a model id happens to advertise. This
hook resolves in strongest-signal-first order — env override → `[1m]` marker →
**verified known-model table** → observed-usage evidence → 200k default — and
the table is the part upstream structurally cannot have.

**Both hooks will fire unless you disable ECC's.** Add to `~/.claude/settings.json`:

```json
"env": { "ECC_DISABLED_HOOKS": "pre:edit-write:suggest-compact" }
```

### Maintaining the known-model table

`KNOWN_WINDOWS` in the hook is deliberately sparse — it holds only entries
confirmed against a client readout or vendor docs. A wrong entry is worse than
no entry, because it outranks the observed-usage evidence beneath it. An
unlisted model degrades to the same heuristics ECC used, which is today's
behaviour, not a regression.

Verify any change with the built-in self-test (9 cases, including the exact
197.3k-on-Opus-5 regression):

```bash
node hooks/context-window-monitor.js --self-test
```

## The stack this plugin orchestrates

| Tool | Layer | Install (external) |
|---|---|---|
| Headroom | wire compression proxy (:8787) | github.com/chopratejas/headroom (own hooks plugin) |
| RTK | CLI output compression | `brew`-installed `rtk` |
| claude-mem | global session memory (:37777) | github.com/thedotmack/claude-mem (own plugin) |
| OpenWolf | per-repo file intel (`.wolf/`) | `openwolf` binary, per-repo opt-in |
| Serena | semantic code navigation | MCP server (user scope) |
| CodeGraph | code knowledge graph | `codegraph` CLI + MCP, `codegraph init` per repo |
| graphify | vault knowledge graphs | skill (vendored here) |
| Graphiti | temporal KG memory | opt-in — see `graphiti-memory` skill |

### Per-repo stack config

`skills/context-stack/references/stack.config.schema.json` (`schemaVersion: 2`) is the
schema for `$HOME/.claude/rhize-context-manager/stack.config.json` — read by the
`context-stack` skill's routing logic, written by `/context-setup`. v2 added
`repoOverrides` (per-repo enable/disable decisions with reasons) alongside the original
`layers` catalog, so one repo's setup run never has to mutate the shared inventory other
repos also read. `skills/context-engineering/scripts/config_generator.py --scan <path>`
(used by `/context-setup` Step 1 to infer project type) had a bug where scanning `.`
produced an empty project name (`Path(".").name == ""`); fixed 2026-08-04 to resolve the
path first.

## Maintenance

- Third-party skill drift: `npx @rhize/skill-forge watch` reads [skills/SOURCES.md](skills/SOURCES.md)
  and reports upstream movement.
- New intake: always via `npx @rhize/skill-forge add -y -t rhize-context-manager/skills <source>`
  so the gate + provenance ledger stay authoritative.
