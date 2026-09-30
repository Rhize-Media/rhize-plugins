---
name: functionize
description: >-
  Mine repeated CLI usage and multi-call procedures into redacted Functionize candidates,
  compile inert proposal bundles, inspect the recipe review queue, or record an explicitly
  supplied human recipe decision through the rhize-skill CLI. Use when asked to
  "Functionize" a CLI, inspect repeated shell-history patterns, generate a safe wrapper proposal,
  review a Functionize candidate, or find repeated multi-step procedures agents run (recipe
  candidates), inspect recipe status, or record a human recipe review. This skill never registers,
  approves for execution, promotes, verifies, stages, or runs a generated
  artifact; use procedural-memory only when a later gate is separately authorized.
metadata:
  rhize:
    topics: [automation]
    stacks: [functionize]
---

# Functionize: compile inert CLI proposals

Use Functionize to turn repeated, locally mined CLI shapes into source-free proposal evidence. The
compiler may emit an inert wrapper, synthetic fixture, contract tests, deterministic grader,
provenance, and an eval record. Compilation is measurement, not registry admission.

## Use only the compile-boundary launcher

Call the self-relative launcher from this skill. It exposes exactly six modes and verifies that
the installed `rhize-skill` CLI actually supports the selected command before continuing:

```bash
bash scripts/functionize.sh mine <cli> [--history-file <path>] [--json]
bash scripts/functionize.sh mine <cli> --export-candidate <fingerprint> --proposal-dir <dir>
bash scripts/functionize.sh mine <cli> --auto-compile --proposal-dir <dir>
bash scripts/functionize.sh generate <candidate-manifest> --proposal-dir <dir> [--baseline-sha <sha>]
bash scripts/functionize.sh review <candidate-manifest> <review-manifest> --ledger <path>
bash scripts/functionize.sh recipes [--since 30d] [--eligible-only] [--json]
bash scripts/functionize.sh recipe-status --ledger <path> [--reviewer <handle>] [--json]
bash scripts/functionize.sh recipe-review <bundle> --ledger <path> --decision <approve|reject|defer> --reason-code <code> --reviewer <handle>
```

- `mine` maps to `rhize-skill functionize`: it locally reads shell history, redacts and aggregates
  shapes, and optionally exports or auto-compiles candidates. History text is never evaluated or
  executed; do not copy raw history into chat, proposals, Jira, or eval records.
- `generate` maps to `rhize-skill functionize-generate`: it compiles one exported v2 candidate
  without requiring a review decision.
- `review` maps to `rhize-skill functionize-review`: it validates and appends a digest-bound human
  decision. It never generates code.
- `recipe-review` maps to `rhize-skill functionize-recipe-review`: it records an explicitly supplied
  human decision on a single- or cross-call recipe bundle. It never stages or promotes it.
- `recipe-status` maps to `rhize-skill functionize-recipe-status`: it reads the latest recipe
  decisions from the selected ledger. It never records a decision.

`--auto-compile` can compile eligible candidates and still exit nonzero when other candidates are
refused. Report each outcome rather than collapsing the run to its exit code. A `promotable: true`
field means only that the deterministic grader cleared the proposal-quality check; it grants no
registration, trust, approval, promotion, verification, or execution authority.

## Agent sources

`mine` also reads agent-run commands instead of, or alongside, shell history:

```bash
bash scripts/functionize.sh mine <cli> --source agent [--hosts claude,codex] [--since 30d] \
  [--project GLOB] [--transcripts-dir DIR] [--codex-sessions-dir DIR] [--capture-file FILE]
bash scripts/functionize.sh mine <cli> --source agent --discover
```

`--source agent` draws from three places: Claude Code session transcripts under
`~/.claude/projects`, Codex session files under `~/.codex/sessions`, and the live capture file
this plugin's async `functionize-capture.py` hook writes (`agent-bash.jsonl`, one record per
successful Bash call). `--discover` lists what each source finds without mining it. Every source
is read the same way plain shell history is: only the command text and a success/failure signal
are read — never a tool's stdout/stderr or any other transcript field — so the resulting shape
class is `agent_transcript`, and the compile-only boundary below is unchanged. Set
`RHIZE_FUNCTIONIZE_CAPTURE=off` to opt a session out of the live capture file entirely.

## Recipe candidates

Most of what agents repeat is a multi-step procedure inside one Bash call, not a single CLI, so the
wrapper compiler above finds little in agent history. `recipes` maps to
`rhize-skill functionize-recipes` and mines those procedures instead:

```bash
bash scripts/functionize.sh recipes [--hosts claude,codex] [--since 30d] [--project GLOB] \
  [--min-count 3] [--min-sessions 2] [--min-steps 2] [--top 20] [--eligible-only] \
  [--hide-covered] [--max-variants N] [--json]
bash scripts/functionize.sh recipes --export <fingerprint> --proposal-dir <dir>
bash scripts/functionize.sh recipes --export-all --proposal-dir <dir>
bash scripts/functionize.sh recipes --cross-call --max-calls 4 --max-glue 1 --since 30d --eligible-only --json
```

- A recipe is keyed by its ordered step shapes: program, known subcommand, flag names, and a typed
  target (for example `host:*.sanity.io` or `script:refactor_gate.py`). Exploration steps such as
  `grep` and `head` do not count toward the key. Only allowlisted names reach any output;
  everything else becomes a typed placeholder, so paths, values and hostname prefixes never appear.
- Each candidate reports its count, distinct sessions, number of variants, a risk class and any
  `possibly_covered_by` hint naming a registry artifact or learned skill that already has the same
  steps. Risk is the union across the retained eligible calls.
- Credential, destructive, privileged, upload, remote-exec, database and publish steps (including
  any `git push`) are refused and never exported. A group may remain eligible when its clean
  subset still meets the repetition thresholds; report the dropped-call evidence as well.
- An export writes `recipe-<fingerprint>/` with `recipe.json` (structured steps), `REVIEW.md` and a
  `review.json` decision template. The whole bundle is secret-scanned in memory before anything is
  written, then published atomically. It contains no runnable script.

Report the fingerprint, counts, risk and coverage hint for each recipe you surface. A recipe is a
review candidate, not a reusable artifact.

`--cross-call` finds procedures spread across adjacent Bash calls in one session. `--max-calls`
bounds the window and `--max-glue` bounds intervening exploration-only calls. These existing runtime
flags pass through unchanged; do not merge steps across sessions. Clean-subset eligibility can retain
safe repeated calls while refusing unsafe occurrences; it does not authorize exporting unsafe steps.
Report the runtime's refusal and coverage evidence rather than inferring safety from a candidate's rank.

## Human recipe decisions and review status

Start with `recipe-status --ledger <path> --json` to inspect the queue. Read the exported `REVIEW.md`,
`recipe.json` and `review.json` before requesting a decision. Require an explicit human decision for
that exact bundle, a matching reason code and reviewer handle. Never infer approval from general
agreement, select a decision for the human, impersonate the reviewer, or fill risk acknowledgements
without the human's explicit instructions. The handle is informational, not authenticated identity;
the wrapper cannot technically distinguish human input from agent-supplied arguments.

For approval, the human must acknowledge every listed risk flag in `review.json`. Use
`--reason-code steps_reviewed` or `useful_procedure` for approve; obtain the valid reject/defer codes
from the selected command's `--help`. The runtime revalidates the bundle, binds the append-only
decision to the recipe fingerprint and exact `recipe.json` digest, and requires the applicable
acknowledgements. Missing required decision/reviewer arguments or invalid codes refuse the write.
Status reports latest decisions; a later reject/defer supersedes an earlier approval for staging.

Approval here is a recipe review decision, not execution authorization. When the human separately
requests documentation-only staging, hand off to the
[`procedural-memory` skill](../procedural-memory/SKILL.md#stage-an-approved-recipe-explicit-request-only).
Do not invoke `recipe-stage`, `promote`, `approve`, `verify` or `run` through Functionize.

## Stop at the proposal boundary

After mining, recipe export, generation, or review, report the candidate fingerprint, proposal/evidence paths,
grader status, promotability reason, and refusals. Stop there unless the user separately requests a
later registry action. A later action uses the `procedural-memory` skill and retains its existing
digest, provenance, trust, health, approval, and execution gates; never feed a generated proposal
directly to a target CLI or registry table.
