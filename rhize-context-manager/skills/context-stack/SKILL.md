---
name: context-stack
description: >-
  Routing and coexistence brain for the Rhize context stack. Use when deciding WHICH
  context tool to reach for (Headroom, claude-mem, OpenWolf, Serena, CodeGraph, RTK,
  graphify, Graphiti, Obsidian), when two context layers appear to duplicate or conflict
  (same context injected twice, slow session start, stacked hooks), or when setting up a
  new repo and choosing which context tooling it should run. Triggers: "which memory
  tool", "context is duplicated", "session start is slow", "set up context tooling",
  "where should this knowledge live".
---

# Context Stack — Routing & Coexistence

The Rhize context stack has independent layers. Each solves a different problem; the
failure mode is running overlapping layers without noticing they compete.

## The layers

| Layer | Tool | Scope | Problem it solves |
|---|---|---|---|
| Wire | **Headroom** (proxy `127.0.0.1:8787`) | per-repo (via `.claude/settings.local.json`) | Compresses API traffic; token savings on the wire |
| Wire | **RTK** (`rtk` CLI proxy) | global (hook-rewritten commands) | Token-optimized CLI output (60–90% savings) |
| Memory | **claude-mem** (plugin, dashboard `:37777`) | global, cross-session | Persistent observation memory + recall injection |
| Memory | **Graphiti** (opt-in, see `graphiti-memory` skill) | project/org | Temporal knowledge-graph memory with entity relationships |
| File intel | **OpenWolf** (`.wolf/`) | per-repo (only where installed) | In-session file index + correction hooks |
| Code nav | **Serena** (MCP) | per-repo | Symbol-level semantic navigation and edits |
| Code nav | **CodeGraph** (`.codegraph/`, MCP + CLI) | per-repo (only where indexed) | Call-path + blast-radius answers in one query |
| Knowledge | **graphify** (skill) | vault/global | Any input → knowledge graph (Obsidian-linked) |
| Knowledge | **Obsidian vault** | global | Durable human-readable notes, plans, decisions |

## Routing rules

**Config layer:** before applying the rules below, check for
`$HOME/.claude/rhize-context-manager/stack.config.json` (schema:
`references/stack.config.schema.json`). If it exists, treat its `layers` list as the
authoritative inventory of what's running, where, and for which repos — it can add,
remove, or repoint layers without a plugin update. If it's absent, fall back to the
built-in default inventory below (the table and rules are unchanged either way).

**Code understanding:** `.codegraph/` exists → CodeGraph first. Otherwise Serena for
symbol operations in large codebases; plain Grep/Glob for small repos or one-off lookups.
Never run Serena and CodeGraph on the same question — pick by what's indexed.

**Storing knowledge:** session-scoped facts → claude-mem captures automatically (don't
duplicate by hand). Durable decisions/plans → Obsidian vault. Relationship-heavy
knowledge (entities, timelines, cross-project) → graphify (vault graph) or Graphiti
(queryable temporal graph) — graphify for human browsing, Graphiti for agent recall.

**Compression:** never manually compress what a wire layer already handles. Headroom
compresses API traffic; RTK compresses CLI output. In-context compression (compaction,
summarization) is governed by the `context-compression` and `strategic-compact` skills.

## Coexistence watch (from Rhize RULES.md — do not silently tolerate)

Repos running Headroom + claude-mem + OpenWolf simultaneously are the highest-risk
overlap zone. Watch for:

- Noticeably slow SessionStart or lag before tool calls (stacked hooks firing in series).
- The SAME context injected twice — claude-mem recall overlapping OpenWolf file-index.
- Headroom compressing content OpenWolf already summarized; claude-mem storing
  already-compressed proxy output.
- Errors/timeouts in `~/.headroom/guard.log`, the claude-mem dashboard, or the OpenWolf
  token ledger.

When noticed: **flag it explicitly** with the symptom + repo, then diagnose (guard.log,
token ledgers, SessionStart wall-time). The two MEMORY layers (claude-mem global +
OpenWolf per-repo) are the real overlap; Headroom is wire-level and rarely conflicts.
If one must be dropped in a repo, keep the one actually being used there.

Run `/context-doctor` for a structured health check of the whole stack.

## New-repo setup guidance

- Every repo: RTK (global) + claude-mem (global) come for free.
- Heavy/long-lived repos: add Headroom (`.claude/settings.local.json` proxy config).
- Large codebases needing semantic nav: `codegraph init` (preferred) or Serena.
- Only add OpenWolf where its correction-hook value is proven — it overlaps claude-mem.
