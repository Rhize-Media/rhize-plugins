# 0001 — No `/prune` command

**Status:** decided, 2026-08-24 (this plugin's initial scaffold)

## Context

The task brief handing off this plugin's scaffold proposed a fifth slash command,
`/prune`, alongside `/promote`, `/recall`, `/run`, `/verify`.

## Decision

`/prune` is **not implemented**. This plugin ships exactly four commands.

## Why

Nothing in the `rhize-skill` CLI implements pruning. The closest existing verb is
`rhize-skill stale`, which is explicitly read-only: a 90-day decay **report** naming
artifacts that haven't been re-verified recently. It does not delete, quarantine, or
otherwise act on anything — see this plugin's own registry README, "Running the CLI":
`stale` is listed alongside `doctor`/`reindex` as a reporting/reconciliation command,
never a mutating one.

Actually removing or retiring a registry artifact is a decision with real
consequences — Git history, Postgres rows, approval records
(`registry/.approvals/`), and any live routine still pointing at that artifact's
name/version. The registry's own STATE.md repeatedly treats decisions of this shape
(e.g. the approval-vs-provenance-rewrite ruling, the whole-vault-vs-prose-scope
ruling) as **Jim's call, not a static classifier's or a wrapper plugin's** — see
"Approval" in the registry README for the precedent: an equivalent shortcut (`trust`
promoted by fiat) was considered and explicitly rejected because it wasn't bound to
the artifact's actual state.

So a `/prune` command here would have to be one of:

1. A thin re-wrap of `stale`'s read-only report under a name that implies mutation —
   misleading, and redundant with `/procedural-memory:verify` plus reading `stale`'s
   output directly.
2. A real deletion/deprecation workflow — out of scope for a CLI wrapper plugin, and
   the registry itself doesn't expose that workflow yet (there is no `rhize-skill
   deprecate`/`rhize-skill remove`).

Neither is worth shipping. If the registry later grows an actual prune/deprecate
verb, this plugin should wrap it then — the same way `/promote`/`/recall`/`/run`/
`/verify` wrap verbs that already exist. Until then, `rhize-skill stale` is
reachable directly (via `scripts/rhize-skill-launcher.sh stale`) for anyone who
wants the decay report without a dedicated slash command.

## Consequences

- No `/procedural-memory:prune` command or `skills/procedural-memory` trigger phrase.
- `stale` remains a plain CLI passthrough, not elevated to a dedicated command.
- Revisit if `rhize-skill` ever grows a real deprecate/remove verb.
