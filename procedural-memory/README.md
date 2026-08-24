# procedural-memory

Wraps the `rhize-skill` CLI from `Rhize-Media/procedural-memory` — a Git-backed registry of
proven, working code (skills and CLI-library functions) indexed by description in
Postgres + pgvector, so a task similar to one already solved re-executes the code that solved
it instead of an LLM recomposing the workflow from scratch. This plugin is a thin client: it
never reimplements the registry's provenance, trust-gating, digest-checking, or verification
logic — every one of those lives in the CLI, and this plugin's job is to invoke it correctly and
report its output honestly.

Distinct from claude-mem's session-search skills: those retrieve what happened in past
conversations; this plugin executes proven code that already solves a task.

## Setup

The `rhize-skill` CLI is not published to PyPI — it's a Rhize-internal registry you build from
source once:

```bash
cd ~/dev-local/RHIZE/procedural-memory   # or wherever you clone Rhize-Media/procedural-memory
python3 -m venv .venv
.venv/bin/pip install -e ".[test]"
.venv/bin/rhize-skill doctor              # confirms PATH, Postgres, pgvector, migrations, Keychain
```

This plugin never assumes that checkout lives at any particular path (see "How the CLI is
resolved" below) — `doctor`'s job is entirely the registry's own readiness, not this plugin's.

Every command here talks to Postgres at the CLI's own default DSN
(`postgresql://<user>@localhost:5432/procedural_memory`) unless you pass `--dsn` through as an
extra argument. No plugin-level configuration is needed beyond having a working `rhize-skill`
somewhere this plugin can find it.

## How the CLI is resolved (portability)

`rhize-plugins` is distributed to more than one machine; a hardcoded path to one person's
checkout would break everywhere else. Every command and the skill call
`scripts/rhize-skill-launcher.sh` instead of the CLI directly. It resolves the binary in order:

1. `RHIZE_SKILL_BIN` env var — an exact path to the `rhize-skill` executable.
2. `rhize-skill` on `PATH` (`command -v`) — the portable case for anyone who installed it
   normally (a venv/pipx install with its `bin/` on `PATH`).
3. `~/dev-local/RHIZE/procedural-memory/.venv/bin/rhize-skill` — a convenience default for this
   developer's own machine layout. Used only if that exact file exists and is executable; never
   assumed.
4. Neither found: **refuse loudly**, exit `78` (`EX_CONFIG`), naming exactly what was checked
   and how to fix it (`export RHIZE_SKILL_BIN=...`, or build the CLI per Setup above). This
   plugin never silently no-ops and never lets a missing CLI surface as a confusing downstream
   error — see `docs/mcp-secret-launcher.md` in this repo's root for the same pattern applied to
   MCP credential delivery, which this shim's resolution order mirrors.

It then runs a **version-compatibility check**: this plugin was built against a known minimum
`rhize-skill` version (`MIN_VERSION` in the script). Since the CLI has no `--version` flag, the
shim reads the installed package version via the interpreter that owns the resolved binary's
own install (`importlib.metadata.version("rhize-skill")` against the `python3`/`python` sibling
next to the resolved binary — true for both a venv and a pipx install). If the resolved CLI is
older than `MIN_VERSION`, the shim refuses and names both versions. If no sibling interpreter is
found (an install shape the shim doesn't recognize), it prints a warning and skips the check
rather than guessing — this degrades to "unchecked," never to a false pass.

## Skills

<!-- SKILL-MAP:BEGIN -->
| Skill | Description | Topics |
| --- | --- | --- |
| `procedural-memory` | Execute a proven, already-working artifact from the procedural-memory registry (Rhize-Media/procedural-memory) instead of recomposing a tas… | automation, workflow-patterns |
<!-- SKILL-MAP:END -->

## Commands

### `/promote`

Verify, classify trust, write provenance, commit, and index a staged artifact
(`rhize-skill promote <path>`). Commits and indexes unconditionally (write-through) but does
**not** run the smoke test — a freshly promoted artifact is `health=unverified`, not
`health=ok`. Run `/verify` next for a real health signal.

**Invoked as:** `/procedural-memory:promote`

### `/recall`

Ranked semantic recall for a task description (`rhize-skill recall "<task>"`), reporting each
hit's similarity score, trust tier, health, last-verified date, and success rate — never just
the name. A high-similarity hit that's `unreviewed` or `degraded` is not a safe recommendation
on similarity alone.

**Invoked as:** `/procedural-memory:recall`

### `/run`

Execute a registry artifact by name (`rhize-skill run <name> [args] [--offline]`) —
registry-only resolution, content-digest check (transitive over anything it pins), trust gate,
health gate. Never adds `--approve-unreviewed` on the user's behalf; a refusal is surfaced
verbatim, not retried with a bypass.

**Invoked as:** `/procedural-memory:run`

### `/verify`

Re-run a promoted artifact's sandboxed smoke test, or every function under a CLI namespace
(`rhize-skill verify <name> | --cli <cli> [--offline] [--fixture <path>]`). The only command
that ever sets `health=ok`/`health=degraded` with a real `last_verified` date.

**Invoked as:** `/procedural-memory:verify`

## Not implemented: `/prune`

An earlier handoff for this plugin proposed a fifth `/prune` command. It was deliberately
dropped — see `docs/decisions/0001-no-prune-command.md` for why. `rhize-skill stale` (a
read-only 90-day decay report) is reachable directly via
`scripts/rhize-skill-launcher.sh stale` if you want it without a dedicated command.

## Architecture

```
procedural-memory/
├── .claude-plugin/plugin.json
├── commands/{promote,recall,run,verify}.md   # thin wrappers — no reimplemented logic
├── skills/procedural-memory/SKILL.md         # natural-language trigger, same 4 verbs
├── scripts/rhize-skill-launcher.sh           # portable CLI resolver + version gate
├── hooks/hooks.json                          # scaffold only — no hooks wired yet
├── docs/decisions/                           # recorded scope decisions (e.g. no /prune)
├── README.md                                 # this file
└── GUIDE.md                                  # user-facing walkthrough
```

## Trust model this plugin never bypasses

Every artifact in the registry carries a provenance contract: input schema, required
environment as parameters (never a baked-in path), declared secrets (Keychain references only),
a verification spec, and a trust tier. `run`/`run --offline` refuse if the on-disk content
digest no longer matches what was verified, or if trust/health don't clear the gate. This
plugin's commands report those refusals verbatim rather than working around them — see each
command's `.md` file and the skill's "trust/health gate is not optional" section. Full model:
the registry's own `README.md` and `STATE.md` at `Rhize-Media/procedural-memory`.

## Eval coverage

Not yet added. A `claude plugin eval` reachability spike (done alongside this scaffold) found
the sandbox's filesystem-exec and network-access policies for reaching a home-directory binary
and a local Postgres are **undocumented** in the current reference material — neither confirmed
reachable nor confirmed blocked. A future eval suite for this plugin should default to a
fixture/mock mode rather than assuming it can reach the real CLI and a live Postgres, and treat
a real-CLI/real-DB path as something to verify empirically per environment, not assume from this
note.
