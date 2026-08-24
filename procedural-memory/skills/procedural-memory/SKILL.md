---
name: procedural-memory
description: >-
  Execute a proven, already-working artifact from the procedural-memory registry
  (Rhize-Media/procedural-memory) instead of recomposing a task from scratch. Use when a task
  looks like something the registry may already have solved: recall() finds the closest match by
  semantic similarity over Postgres/pgvector (ranked with trust tier, health, and success rate),
  and run() executes it registry-only, content-digest-checked, and trust/health-gated — never a
  caller-supplied path, never a silently bypassed gate. Also covers promoting a newly captured
  script into the registry (verify -> classify trust -> write provenance -> commit -> index) and
  re-running an artifact's sandboxed smoke test to refresh its health state. This skill is about
  EXECUTING proven code with a provenance contract, not retrieving past conversation or session
  history — for "what did we discuss/decide/do before" use claude-mem's search/recall skills
  instead, and for a knowledge graph over an Obsidian vault use graphify. Trigger on "is there
  already a tool for this", "run the registry version of X", "promote this script to the
  registry", "recall a proven artifact for <task>", "re-verify <artifact-name>", or "has this
  been automated before".
metadata:
  rhize:
    topics: [automation, workflow-patterns]
    stacks: []

---

# procedural-memory: execute proven registry artifacts

Wraps the `rhize-skill` CLI (Rhize-Media/procedural-memory) so a task that looks like something
already solved re-executes the artifact that solved it, instead of an LLM recomposing the
workflow from scratch. Every artifact carries a provenance contract — input schema, required
environment as *parameters* (never a baked-in path), declared secrets (Keychain references
only), a verification spec, and a trust tier — and `run`/`run --offline` refuse unconditionally
if the on-disk content digest no longer matches what was verified.

## This is execution, not retrieval — pick the right tool

| You want to... | Use |
| --- | --- |
| Re-run proven code that already does the task | **this skill** (`/procedural-memory:recall`, `/procedural-memory:run`) |
| Recall what happened in a past session/conversation | claude-mem's search/recall skills |
| Build or query a knowledge graph over vault notes | `graphify` (rhize-context-manager) |
| Store/retrieve general declarative facts | claude-mem, or the vault (`obsidian-second-brain`) |

If a request is genuinely "what did we do/decide before", that's claude-mem's job. If it's "is
there already working code for this, and can I just run it", that's this skill's job.

## All invocations go through the launcher, never a raw path

`${CLAUDE_PLUGIN_ROOT}/scripts/rhize-skill-launcher.sh` resolves the `rhize-skill` binary
portably (env override -> PATH -> known dev-machine default -> loud refusal) and checks it isn't
older than this plugin expects before every call. Never construct or hardcode a path to
`rhize-skill` directly — always go through the launcher, in every command and here.

```
${CLAUDE_PLUGIN_ROOT}/scripts/rhize-skill-launcher.sh recall "<task description>"
${CLAUDE_PLUGIN_ROOT}/scripts/rhize-skill-launcher.sh run <name> [args...] [--offline]
${CLAUDE_PLUGIN_ROOT}/scripts/rhize-skill-launcher.sh promote <path>
${CLAUDE_PLUGIN_ROOT}/scripts/rhize-skill-launcher.sh verify <name> | --cli <cli> [--offline]
```

The four slash commands (`/procedural-memory:recall`, `/procedural-memory:run`,
`/procedural-memory:promote`, `/procedural-memory:verify`) are thin wrappers around exactly
these four calls — reach for this skill when the trigger is natural language rather than an
explicit slash command, and follow the same rules either way.

## The trust/health gate is not optional and not this skill's to bypass

- `promote` commits and indexes unconditionally but never executes the smoke test — it lands
  `health=unverified`, not `health=ok`. Don't describe a freshly promoted artifact as verified.
- `run`/`run --offline` refuse an `unreviewed` artifact unless it has a valid, digest-bound
  approval (`rhize-skill approve`, not wrapped by a slash command here — run it directly via
  Bash only if the user explicitly asks for a durable approval) or the caller passes the
  one-shot `--approve-unreviewed` bypass.
- **Never add `--approve-unreviewed` on the user's behalf.** Surface the refusal verbatim — it
  names the exact reason (trust, digest mismatch, degraded/missing/corrupt health) and the
  remediation command — and let the user decide whether to bypass or fix it.
- A passing exit code with a failing assertion is still `degraded`, never `ok` — report which
  specific assertion failed, not just pass/fail.

## Recall results carry their own honesty signal

`recall`'s output already reports trust, health, last-verified date, and success rate per hit —
surface all of it, not just the name and similarity score. A high-similarity hit with
`trust=unreviewed` or `health=degraded` is not a safe recommendation to run without saying so.

## Read the registry, never write to it directly

This plugin only ever talks to the registry through `rhize-skill`. Never hand-edit files under
`~/dev-local/RHIZE/procedural-memory/registry/` or its Postgres tables directly — that bypasses
the digest/provenance guarantees the whole trust model depends on. If a user wants to inspect
what's there, read the registry's own `README.md`/`STATE.md` (informational only) rather than
patching artifacts by hand.
