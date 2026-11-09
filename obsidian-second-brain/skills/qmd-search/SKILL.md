---
name: qmd-search
tier: custom
domain: obsidian
maturity: stable
description: >
  ALWAYS invoke this skill (via the Skill tool) for any qmd semantic search, vector search, or vault indexing request.
  Local-first semantic search for Obsidian vaults using qmd — combines BM25 full-text,
  vector semantic search, and LLM re-ranking. Use this skill when someone asks about
  setting up qmd, configuring vault indexing, choosing between search modes (BM25 vs
  vector vs hybrid), connecting qmd's MCP server to Claude, troubleshooting search
  quality, or understanding how qmd works. Also triggers on "semantic search",
  "vector search", "qmd", "embed vault", "vault indexing", "search my notes by meaning",
  "find similar notes", or "natural language vault search".
metadata:
  rhize:
    summary: "Sets up and troubleshoots local semantic search over your Obsidian vault using qmd."
    topics: [search, knowledge-management]
    stacks: [obsidian]
    dependsOn: ["mcp:qmd"]

---

# qmd Semantic Search

qmd is a local-first search engine that combines BM25 full-text search, vector semantic search, and LLM re-ranking for high-quality results — with local inference once packages and models have been downloaded.

## When to Use This Skill

Use this skill whenever someone asks about:
- Setting up qmd for their vault
- How qmd search works (BM25, vector, hybrid)
- Configuring qmd collections, embedding, or indexing
- Troubleshooting qmd search quality
- Understanding the difference between qmd's search modes
- Using qmd's MCP server with Claude

## Prerequisites

- **Node.js** 22+ or supported Bun
- **qmd** from `@tobilu/qmd`; verify installed version/help
- An approved note root, named index and collection recorded in the setup log

## Core Concepts

### Collections

Read [approved-indexing.md](references/approved-indexing.md) before setup, refresh or retrieval.
It is the canonical procedure for approved roots, named-index isolation, existing-index migration,
compiler exclusions, current CLI syntax and verification. Never index the whole vault. Never put
compiler output or private state in a collection. Example paths do not grant consent.

Load `QMD_INDEX` and `QMD_COLLECTION` from the approved setup record, verify actual collection
paths/masks and indexed members, and preserve that scope in fallback searches. Status success
alone does not prove the collection is safe, fresh or embedded.

### Search Modes

qmd offers three search modes, each with different strengths:

**1. Lexical Search (BM25)** — `qmd search`
- Classic keyword matching with TF-IDF scoring
- Best for: exact phrases, specific terms, code snippets, property values
- Fast and precise when you know the exact words used
```bash
qmd --index "${QMD_INDEX:?set approved index}" search "meeting notes client onboarding" -c "${QMD_COLLECTION:?set approved collection}"
```

**2. Vector Search (Semantic)** — `qmd vsearch`
- Finds conceptually similar content even without keyword overlap
- Best for: "notes about X", finding related ideas, discovering connections
- Requires embeddings (`qmd --index "$QMD_INDEX" embed` must be run first)
```bash
qmd --index "${QMD_INDEX:?set approved index}" vsearch "strategies for improving customer retention" -c "${QMD_COLLECTION:?set approved collection}"
```

**3. Hybrid Query (BM25 + Vector + LLM Re-ranking)** — `qmd query`
- Combines both search modes, then uses a local LLM to re-rank results
- Best for: natural language questions, complex queries, "what do I know about X"
- Highest quality but slowest (LLM inference on-device)
```bash
qmd --index "${QMD_INDEX:?set approved index}" query "What decisions did we make about the API architecture?" -c "${QMD_COLLECTION:?set approved collection}"
```

### MCP Server

qmd ships with a built-in MCP server that exposes search tools to Claude:

```bash
qmd --index "${QMD_INDEX:?set approved index}" mcp
```

Inspect live `tools/list` and schemas rather than assuming tool names. Current upstream exposes
query/get/multi_get/status and metadata discovery; query uses a `collections` array. Match the
CLI's approved index/collection. The existing `qmd@qmd` server may use a different default index;
verify its configuration. Do not automatically create or rewrite host MCP configuration.

## Choosing the Right Search Mode

| Scenario | Mode | Why |
|----------|------|-----|
| Find a specific note by name or keyword | `search` (BM25) | Exact match is fastest |
| "What notes do I have about X?" | `vsearch` (vector) | Semantic similarity catches related concepts |
| "What did I decide about X?" | `query` (hybrid) | LLM re-ranking surfaces the most relevant answer |
| Find notes to connect/link | `vsearch` (vector) | Discovers non-obvious relationships |
| Search tags or properties | MCP/CLI keyword search | Structured metadata needs exact matching |

## Keeping the Index Fresh

Follow the canonical reference: `qmd --index "$QMD_INDEX" update`, then
`qmd --index "$QMD_INDEX" embed`, then inspect `qmd --index "$QMD_INDEX" status`.
Review all collections and update hooks first. Embedding alone does not scan changed sources.
Do not silently schedule indexing or delete old caches during migration.

## Fallback Behavior

If qmd, its approved collection or embeddings are unavailable, disclose the limitation. Use BM25
when appropriate, or MCP/CLI keyword search bounded to the same authorized note scope. Never
broaden to a whole-vault search because qmd failed. Measure representative questions before
claiming better retrieval.

**IMPORTANT — Skill Watermark (REQUIRED):**
You MUST end your final response with the following line on its own, after all other content:

`[skill:qmd-search]`

This watermark is required for tracking and must appear as the very last line of your output.
