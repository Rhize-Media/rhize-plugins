---
description: Repo-level setup wizard — scan the repo, probe the active context stack, propose a tailored per-repo config, and write it on confirmation
---

# /context-setup

Set up the Rhize context stack for **this repo**: infer what kind of project it is,
find out which stack layers are actually running here, propose a tailored
enable/disable list with reasons, and — once the user confirms — write that decision
to the file the `context-stack` skill reads.

**Boundary (read this before running):** `/context-setup` owns stack **CONFIG** only.
It writes `$HOME/.claude/rhize-context-manager/stack.config.json` (which layers this
repo should use) and nothing else. It does **not** install any tool, does not start any
process, and does not wire any Claude Code hook. Hook wiring across all plugins is
`/rhize-setup` (in `rhize-ops`, a fleet-level wizard that reads every plugin's
`setup/manifest.json` and lets the user opt in per hook). If a probe below finds a tool
that isn't installed, or flags a hook this plugin ships as opt-in
(`rhize-context-manager/setup/manifest.json`), say so and point at `/rhize-setup` —
don't attempt to install or wire it yourself.

## Triggers
**Keywords:** context setup, set up context tooling, configure the stack, context wizard, onboard this repo

## What This Does

### Step 1 — Scan the repo and infer project type
Run the config generator against the current repo:
```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/context-engineering/scripts/config_generator.py" \
  --scan "${CLAUDE_PROJECT_DIR:-$(pwd)}" --json
```
This reports detected languages/frameworks (`package.json`, `requirements.txt` /
`pyproject.toml`, `Cargo.toml`, `go.mod`, `ios/`/`android/`) and an inferred project
type (`web_fullstack`, `api_backend`, `mobile_app`, `data_ml`, `cli_library`, `generic`).
Use this as one signal for the proposal in Step 3 — a `generic`/no-framework repo (like
a plugin marketplace or a docs repo) skews the proposal toward lighter tooling; a large
`web_fullstack` repo skews toward semantic code nav.

Team size isn't inferred (the script only accepts `--team` or `--interactive`) — ask the
user with `AskUserQuestion` if it matters to the proposal, otherwise default to `solo`
and don't block on it.

### Step 2 — Probe which stack layers are actually active
Reuse the exact probe logic from `/context-doctor` (checks 1–5 in
`commands/context-doctor.md`): Headroom proxy + `.claude/settings.local.json`, RTK,
claude-mem dashboard, `.wolf/` (OpenWolf), `.codegraph/` + Serena MCP connection,
Only probe implemented layers. You can either run `/context-doctor` first and read its persisted
JSON (`~/.claude/context-manager/doctor/<latest>.json`) if one exists from this session,
or run the checks directly — either is fine, don't duplicate work if a fresh doctor run
already exists.

Also read `$HOME/.claude/rhize-context-manager/stack.config.json` if it exists (schema:
`skills/context-stack/references/stack.config.schema.json`, `schemaVersion: 2`) — it may
already have a `layers` entry or a `repoOverrides` entry for this repo from a prior run.
Treat a prior run as the starting point to revise, not a reason to skip.

### Step 3 — Propose a tailored stack, with one-line reasons
For each layer in the `context-stack` skill's table (Headroom, RTK, claude-mem,
OpenWolf, Serena, CodeGraph, graphify, memory-context), decide **enable / disable / leave as
global-default** for this repo, and give a one-line reason grounded in Steps 1–2. Apply
the `context-stack` skill's routing rules and coexistence watch list, in particular:

- Flag **redundant indexers** — Serena and CodeGraph both active/proposed for the same
  repo is a duplicate; recommend keeping whichever is already indexed
  (`.codegraph/` present → CodeGraph; otherwise Serena) and disabling the other.
- Flag **redundant memory** — OpenWolf + claude-mem both heavily used in one repo per the
  coexistence watch list; recommend dropping OpenWolf unless its correction hooks are
  proven valuable here (per the skill's guidance), keeping claude-mem (global, free).
- RTK and claude-mem are global-scope and free by default — don't propose disabling them
  without a concrete reason found in Step 2 (e.g. RTK genuinely dead in this repo).
- Heavy/long-lived repos (inferred project type isn't `cli_library`/`generic`, or repo
  has a large file count) → propose adding Headroom if not already wired.
- A `generic` project with no detected framework (e.g. this plugin marketplace repo) →
  don't propose semantic-code-nav layers (Serena/CodeGraph) unless one is already active.
- `memory-context` is preview-only and needs explicit supported adapters. Never propose Graphiti;
  Neo4j memory remains a later gated adapter, not setup work here.

Present the proposal as a compact table: layer | current state | proposed | reason.

### Step 4 — Confirm and write
Use `AskUserQuestion` to confirm the proposal (accept as-is / adjust specific rows /
cancel). Do not write anything before an explicit confirmation.

On confirmation, write `$HOME/.claude/rhize-context-manager/stack.config.json`
conforming to `schemaVersion: 2`:

- If the file doesn't exist yet, create it with `schemaVersion: 2`, a `layers` array
  built from the `context-stack` skill's built-in table (only include layers this repo's
  proposal actually touches — you do not need to enumerate the whole stack), and a
  `repoOverrides` entry for this repo.
- If the file exists, **merge, don't overwrite**: keep every existing `layers` entry and
  every other repo's `repoOverrides` entry untouched. For a layer whose global `scope`
  correctly describes this repo's proposal, just add this repo's name to its `repos`
  array if `scope` is `per-repo` and it isn't already listed. For any disable/enable
  decision that doesn't fit the shared `layers` catalog cleanly, record it under
  `repoOverrides[<this repo's name>].decisions` per the schema (`layer`, `enabled`,
  `reason`), with `updatedAt` set to the current timestamp.
- Validate the result is well-formed JSON conforming to the schema before writing (a
  broken config file breaks the `context-stack` skill for every repo, not just this one).

### Step 5 — Report
Print what was written (file path, which layers/overrides changed) and what the user
should expect to see change (e.g. "Headroom's proxy is not yet running — the config now
says this repo wants it, but you still need to start Headroom itself; run
`/context-doctor` after starting it to confirm"). If any probed layer needs installation
or hook wiring, name it explicitly and point at `/rhize-setup` rather than attempting it.

## Output Format

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🧭 Context Setup: [repo name]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📦 Detected: [languages/frameworks] → inferred type: [type]

🔎 Probed Stack:
  layer | state | note

🎯 Proposal:
  layer | current | proposed | reason

✅ Written: ~/.claude/rhize-context-manager/stack.config.json
  [summary of what changed]

⚠️ Not handled here (see /rhize-setup):
  [any hook-wiring or install steps still needed]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### Step 6 — Establish the evaluation baseline

After writing and reporting the context stack, continue with:

```text
/rhize-ops:rhize-setup --plugin rhize-context-manager --evaluations
```

Register the exact pre-plugin context workflow and frozen version/SHA as Arm A. Preserve the
existing strict comparability rules: immediate deterministic validation is recommended, natural
capture is observational, and same-day rows are not a matched cohort without input identity,
step timing, and ordered execution. This command still owns stack config only; the central Ops
subflow owns evaluation state and receipts.

## Related Commands
- `/context-doctor` — read-only health check; run this first if you want fresh probe data
- `context-stack` skill — the routing/coexistence rules this command applies
- `/rhize-setup` (rhize-ops) — fleet-level opt-in hook wiring, separate from this command's config-only scope
