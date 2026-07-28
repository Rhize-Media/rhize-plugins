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

### Curated third-party (ingested via skill-forge, safety-gated, provenance in [skills/SOURCES.md](skills/SOURCES.md))

From **muratcankoylan/Agent-Skills-for-Context-Engineering**: `context-fundamentals`,
`context-degradation`, `context-compression`, `context-optimization`, `memory-systems`,
`filesystem-context`, `tool-design`.

From **everything-claude-code (ecc)**: `iterative-retrieval`, `strategic-compact`,
`context-budget`, `token-budget-advisor`.

Coverage per feature goal: compression (context-compression, strategic-compact),
retrieval (iterative-retrieval), ranking/budgeting (context-budget,
token-budget-advisor), memory (memory-systems, graphiti-memory), degradation
(context-degradation).

## Commands

| Command | Purpose |
|---|---|
| `/context-doctor` | Read-only health check of every layer (Headroom proxy, RTK savings, claude-mem dashboard, OpenWolf state, Serena/CodeGraph, Graphiti) + overlap flags |
| `/start` | Session bookend — resume from `STATE.md` with real memory (moved from rhize-devflow) |
| `/done` | Session bookend — verifier PASS + `STATE.md` update before commit (moved from rhize-devflow) |
| `/context-hygiene` | Mid-session context cleanup when a session gets heavy (moved from rhize-devflow) |
| `/impact-map` | Pre-feature impact mapping against the component registry (moved from rhize-devflow) |

## Hooks

| Hook | Event | Purpose |
|---|---|---|
| `context-window-monitor.js` | `PreToolUse` (`Edit\|Write`) | Warns once per 10% band past 75% of the **real** context window |

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

## Maintenance

- Third-party skill drift: `npx @rhize/skill-forge watch` reads [skills/SOURCES.md](skills/SOURCES.md)
  and reports upstream movement.
- New intake: always via `npx @rhize/skill-forge add -y -t rhize-context-manager/skills <source>`
  so the gate + provenance ledger stay authoritative.
