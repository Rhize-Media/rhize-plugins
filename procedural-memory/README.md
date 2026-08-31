# procedural-memory

Wraps the `rhize-skill` CLI from `Rhize-Media/procedural-memory` — a Git-backed registry of
proven, working code (skills and CLI-library functions) indexed by description in
Postgres + pgvector, so a task similar to one already solved re-executes the code that solved
it instead of an LLM recomposing the workflow from scratch. A separate Functionize skill uses
the same CLI to mine redacted CLI shapes and compile inert proposals without registering,
approving, promoting, verifying, or running them. This plugin is a thin client: it never
reimplements the runtime's provenance, trust-gating, digest-checking, verification, or proposal
compiler logic.

Distinct from claude-mem's session-search skills: those retrieve what happened in past
conversations; this plugin executes proven code that already solves a task.

The canonical skills and launcher contracts are shared by Claude Code and Codex. Claude Code
exposes the four registry slash commands and advisory hooks; both hosts discover the natural-language
`procedural-memory` and `functionize` skills with self-relative launchers. Codex does not claim
Claude's hook lifecycle. Unified memory may
consume procedural metadata only through the versioned, recall-only
`rhize-procedural-recall-v1` contract. That adapter is not available yet, so memory assembly must
report the procedural lane as unavailable. It must not parse human CLI output, query registry tables
directly, or call `run` as a fallback; similarity never grants execution authority.

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

Registry commands talk to Postgres at the CLI's own default DSN
(`postgresql://<user>@localhost:5432/procedural_memory`) unless you pass `--dsn` through as an
extra argument. Functionize mining/generation stays outside the registry and does not use Postgres;
it reads the explicitly selected local history or candidate manifest and writes only to the selected
proposal/ledger path. No plugin-level configuration is needed beyond having a working `rhize-skill`
somewhere this plugin can find it.

## How the CLI is resolved (portability)

`rhize-plugins` is distributed to more than one machine; a hardcoded path to one person's
checkout would break everywhere else. Claude Code commands call
`scripts/rhize-skill-launcher.sh` through `${CLAUDE_PLUGIN_ROOT}`. The shared skill uses its
self-relative `scripts/procedural-memory.sh`, which resolves the installed plugin root and delegates
to that same launcher from either host. The launcher resolves the binary in order:

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

The released runtime still reports package version `0.1.0` across older and newer command surfaces,
so semver alone cannot prove Functionize support. `skills/functionize/scripts/functionize.sh`
therefore probes the selected command's real `--help` interface before each call and refuses with
exit `78` if that exact command is unavailable. It exposes only `mine`, `generate`, and `review`;
registry and execution verbs are intentionally unreachable through that launcher.

## Skills

<!-- SKILL-MAP:BEGIN -->
| Skill | Description | Topics |
| --- | --- | --- |
| `functionize` | Mine repeated CLI usage into redacted Functionize candidates, compile inert proposal bundles, or record a digest-bound human review through… | automation, functionize |
| `procedural-memory` | Execute a proven artifact from the procedural-memory registry instead of recomposing a task. | automation, workflow-patterns |
<!-- SKILL-MAP:END -->

### Functionize proposal boundary

Use the `functionize` skill for three compile-only modes:

- `mine` → `rhize-skill functionize`: redact and aggregate repeated CLI shapes, optionally export
  or auto-compile candidates.
- `generate` → `rhize-skill functionize-generate`: compile one exported v2 manifest into an inert
  proposal bundle.
- `review` → `rhize-skill functionize-review`: validate and append a digest-bound human decision.

Generated proposals are not registry artifacts. Even a proposal reporting `promotable: true` has
no trust, approval, health, promotion, or execution authority. Those later actions remain behind
the existing `procedural-memory` skill and require separate intent.

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
├── .codex-plugin/plugin.json               # Codex skill discovery and UI metadata
├── commands/{promote,recall,run,verify}.md   # thin wrappers — no reimplemented logic
├── skills/functionize/                       # compile-only mine/generate/review boundary
│   ├── SKILL.md
│   ├── agents/openai.yaml
│   └── scripts/functionize.sh
├── skills/procedural-memory/
│   ├── SKILL.md                              # natural-language trigger, same 4 verbs
│   ├── agents/openai.yaml                    # Codex skill presentation metadata
│   └── scripts/procedural-memory.sh          # self-relative cross-host launcher
├── scripts/rhize-skill-launcher.sh           # portable CLI resolver + version gate
├── hooks/
│   ├── hooks.json                            # PostToolUse/Bash + Stop, wired
│   ├── post-bash-candidate-queue.sh          # Tier 1 — cheap, every Bash call
│   └── session-end-scan.py                   # Tier 2 — heavier, on Stop
├── docs/decisions/                           # recorded scope decisions (e.g. no /prune)
├── tests/test-launcher.sh                    # launcher resolution/version-gate tests, real+runnable
├── evals/                                    # claude plugin eval suite + validate-suite.py (see evals/README.md)
├── README.md                                 # this file
└── GUIDE.md                                  # user-facing walkthrough
```

## Hooks: capturing promotion candidates during a session

Two hooks, deliberately split by cost, both advisory-only (never block, never write to the
registry):

**`post-bash-candidate-queue.sh`** (PostToolUse, matcher `Bash`) fires on *every* Bash call in
*every* session. It pattern-matches `tool_input.command` against known test/build invocations
(`pytest`, `npm test`/`npm run build`, `yarn`/`pnpm` test/build, `cargo test`, `go test`/`go
build`, `vitest`, `jest`, `tsc`) and, on a match, appends one JSONL line to
`~/.claude/procedural-memory/candidate-queue.jsonl` (override with
`PROCEDURAL_MEMORY_CANDIDATE_QUEUE`). It never reads or derives an exit code — see "What was
wrong in the brief" below for why that's correct, not a shortcut. Pure POSIX shell, no
`rhize-skill`/CLI invocation, no network. Real measured latency on this machine (macOS, `/bin/sh`
= bash 3.2.57): **~6ms** for a non-matching command (the overwhelming majority of Bash calls —
essentially the platform's fork/exec floor, since this hook adds zero extra subprocess forks on
that path), **~15ms** for a matching command (one `grep`, one `date`), and a bounded ~120ms on a
pathological ~1MB-stdout command (still fast, no hang — see the script's own "SUBPROCESS BUDGET"
comment for why that distinction took real debugging to get right).

**`session-end-scan.py`** (Stop) is the heavier half. It fast-exits immediately unless the queue
has `pending` entries for the current `session_id` — most Stops in most sessions never touch a
transcript read at all. When there are pending entries, it reads the transcript once, confirms
each one's tool call really did complete without error (cross-referencing `tool_use_id` against
the transcript's `tool_result.is_error`), flips matched entries to `surfaced`, and prints an
advisory naming what passed its test/build command this session — plus any files the session
wrote or edited — with a pointer to `/procedural-memory:promote`. It never says "verified"; that
word is reserved for `/procedural-memory:verify`, the only thing that ever sets a real
`health=ok`.

**Queue file, not `rhize-context-manager`'s.** `~/.claude/procedural-memory/candidate-queue.jsonl`
follows the same JSONL shape as `~/.claude/context-manager/refinement-queue.jsonl`
(`id`/`ts`/`source`/`repo`/`pattern` fields, a `status` lifecycle) but is a separate file — that
queue is scoped to skill-refinement signals and triaged by `/skill-refine`, the wrong tool for
"code that passed a test this session, maybe worth promoting to this registry."

**Append safety.** A single `printf ... >>` is one `write(2)` syscall for a line this short,
which POSIX guarantees atomic on a local filesystem opened `O_APPEND` — concurrent sessions
interleave whole lines, never corrupt one. (`flock(1)` doesn't exist on macOS/BSD, so this is the
portable equivalent, not a fallback.) Verified directly: 60 concurrent invocations against the
same queue file produced exactly 60 valid, distinct JSON lines, zero corruption.

**What was wrong in the brief.** The original wiring brief assumed the post-Bash hook could
check whether a command "exited 0." Empirically, two things are true instead: the Bash
`tool_response` payload delivered to hooks carries no exit-code field at all (`{stdout, stderr,
interrupted, isImage, noOutputExpected}`, confirmed against the shipped `sdk-tools.d.ts` and real
transcript data), and — the more load-bearing fact — **PostToolUse for Bash does not fire at all
when the tool result is an error**, confirmed with a live probe (a 3-command pass/fail/pass
sequence in an isolated scratch session produced exactly two PostToolUse events, for the two
passing commands). So by the time this hook runs, the command has already succeeded; there was
never anything to check. Full writeup: `docs/decisions/0002-post-bash-hook-exit-code.md`.

## Trust model this plugin never bypasses

Every artifact in the registry carries a provenance contract: input schema, required
environment as parameters (never a baked-in path), declared secrets (Keychain references only),
a verification spec, and a trust tier. `run`/`run --offline` refuse if the on-disk content
digest no longer matches what was verified, or if trust/health don't clear the gate. This
plugin's commands report those refusals verbatim rather than working around them — see each
command's `.md` file and the skill's "trust/health gate is not optional" section. Full model:
the registry's own `README.md` and `STATE.md` at `Rhize-Media/procedural-memory`.

## Governance & integrations

Three facts worth stating precisely, since an earlier handoff for this plugin got them wrong
or left them undocumented — this section is the corrected, plugin-facing record; the engine
repo's `STATE.md` carries the fuller evidence for each.

**The skill-forge dedupe gate is already built — nothing here needs it added.**
`/procedural-memory:promote` (`rhize-skill promote`) runs the skill-forge dedupe gate
(`@rhize/skill-forge`'s `scan`/`add` gate pipeline) before writing provenance, and it *blocks*
a near-duplicate promotion rather than merely flagging one. Confirmed live in the registry:
`sanity-upsert-draft`'s first promote attempt was refused this way (lexical-overlap score
0.497 against `sanity-upload-asset`, above the 0.45 strong-match threshold) and only promoted
after its description was trimmed to cut the shared boilerplate. There is no separate dedupe
mechanism for this plugin to add on top — `promote` already has one, and it has already fired
for real.

**`skill-monitor` cannot write success rates back to an artifact's provenance — this is a
structural limitation, not a missing feature.** `rhize-ops/skill-monitor/monitor.py` works by
scanning session transcripts for **Skill-tool invocations**. A registry artifact's `scripts/`
runs as a plain Bash subprocess when `/procedural-memory:run` executes it — it never appears
in a transcript as a Skill-tool call, so skill-monitor structurally cannot see it, score it,
or write anything back about it. Success rates come from the registry CLI's own `runs` table
(what `/procedural-memory:recall` and `rhize-skill digest` read from), which is authoritative
on that question already and needs no help from skill-monitor. **What plugin-ization DOES
newly enable:** now that `/procedural-memory:recall` and `/procedural-memory:promote` are
themselves Skill-tool calls (this plugin's own commands, not the registry artifacts they
invoke), skill-monitor's transcript scan sees *those* two invocations — usage telemetry on
this plugin's commands, never on what the artifacts they execute actually do, and never a
success/fail correlation written into any artifact's provenance. Don't conflate the two when
reading a skill-monitor snapshot that mentions this plugin.

**The `ai-stack-version-drift` blast-radius integration is live, not proposed.** The scheduled
routine (`~/Documents/Claude/Scheduled/ai-stack-version-drift/SKILL.md`) calls
`scripts/blast-radius-check.sh <pkg>` in the registry repo after every safe CLI/library bump
and folds its `BLAST_RADIUS_OK`/`BLAST_RADIUS_BROKEN`/`BLAST_RADIUS_SKIPPED` verdict into the
same drift report — real, exact function names that broke, not a guess. Full diff and rollback
record: `docs/integrations/ai-stack-drift.patch.md` in `Rhize-Media/procedural-memory`.

## Eval coverage

Authored (`evals/`: a sandbox-reachability probe, a fixture-mode happy path, one trigger case,
two negative/routing cases), but `claude plugin eval` itself is **organization-gated
early-access** on this install — confirmed blocked on both `claude plugin eval init` and the
actual run path (`claude plugin eval . --case ...`), not just one.

**Corrected 2026-08-25.** This section previously said enablement was "per-org via an
onboarding-provided env var." That conflated two different mechanisms. Enablement is
**server-side, per organization**, and an enabled first-party client picks it up automatically
after `claude update` and a fresh session — no local setting at all. The env var exists only for
clients that can *never* receive server-side flags (Bedrock/Vertex/Foundry, an LLM gateway or
custom `ANTHROPIC_BASE_URL`, or `DISABLE_TELEMETRY` / `DO_NOT_TRACK` /
`CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` / `DISABLE_GROWTHBOOK` set). Measured on this machine:
none of those apply, the GrowthBook flag cache refreshed the same day and holds 544 flags, and
**none of them is eval-related** — so the flag fetch is healthy and the entitlement is simply
absent. The only unblock is an Anthropic-side grant for the org. See `evals/README.md`.

**Pre-gate check that does work now:** `python3 evals/validate-suite.py` statically validates
every case and grader against the real schema (exit 1 on any error). It caught three defects
that would have made the first real run worthless — a `tool_used` grader with `max: 0` and no
`min: 0` (can never pass, `min` defaults to 1), execution fields at the top level of a
`case.yaml` where unknown keys are silently ignored, and free-text strings in `focus:` where
only an enum is valid. It proves schema conformance only: it runs no agent, so trigger accuracy
stays unmeasured until the gate opens.

What's real instead: `tests/test-launcher.sh` runs the launcher's resolution-order and
version-gate logic directly (no Claude session needed) and includes a proven
deliberately-broken-case-that-goes-red. Separately, every trigger/negative/happy-path case was
manually run once through a real Claude Code session (`claude --plugin-dir <this-plugin>`) —
including a genuine end-to-end hit against this developer's live registry (recall found a real
degraded/unreviewed artifact; run correctly refused it; `--approve-unreviewed` was never added).
Full detail, including exactly what fixture-mode does and doesn't cover: `evals/README.md`.
