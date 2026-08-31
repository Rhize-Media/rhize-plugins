---
name: functionize
description: >-
  Mine repeated CLI usage into redacted Functionize candidates, compile inert proposal bundles,
  or record a digest-bound human review through the rhize-skill CLI. Use when asked to
  "Functionize" a CLI, inspect repeated shell-history patterns, generate a safe wrapper proposal,
  or review a Functionize candidate. This skill never registers, approves, promotes, verifies, or
  runs a generated artifact; use procedural-memory only when a later gate is separately authorized.
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

Call the self-relative launcher from this skill. It exposes exactly three modes and verifies that
the installed `rhize-skill` CLI actually supports the selected command before continuing:

```bash
bash scripts/functionize.sh mine <cli> [--history-file <path>] [--json]
bash scripts/functionize.sh mine <cli> --export-candidate <fingerprint> --proposal-dir <dir>
bash scripts/functionize.sh mine <cli> --auto-compile --proposal-dir <dir>
bash scripts/functionize.sh generate <candidate-manifest> --proposal-dir <dir> [--baseline-sha <sha>]
bash scripts/functionize.sh review <candidate-manifest> <review-manifest> --ledger <path>
```

- `mine` maps to `rhize-skill functionize`: it locally reads shell history, redacts and aggregates
  shapes, and optionally exports or auto-compiles candidates. History text is never evaluated or
  executed; do not copy raw history into chat, proposals, Jira, or eval records.
- `generate` maps to `rhize-skill functionize-generate`: it compiles one exported v2 candidate
  without requiring a review decision.
- `review` maps to `rhize-skill functionize-review`: it validates and appends a digest-bound human
  decision. It never generates code.

`--auto-compile` can compile eligible candidates and still exit nonzero when other candidates are
refused. Report each outcome rather than collapsing the run to its exit code. A `promotable: true`
field means only that the deterministic grader cleared the proposal-quality check; it grants no
registration, trust, approval, promotion, verification, or execution authority.

## Stop at the proposal boundary

After mining, generation, or review, report the candidate fingerprint, proposal/evidence paths,
grader status, promotability reason, and refusals. Stop there unless the user separately requests a
later registry action. A later action uses the `procedural-memory` skill and retains its existing
digest, provenance, trust, health, approval, and execution gates; never feed a generated proposal
directly to a target CLI or registry table.
