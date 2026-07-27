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
