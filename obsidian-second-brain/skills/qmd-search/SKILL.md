---
name: qmd-search
description: >
  ALWAYS invoke this skill (via the Skill tool) for any qmd semantic search, vector search, or vault indexing request.
  Local-first semantic search for Obsidian vaults using qmd — combines BM25 full-text,
  vector semantic search, and LLM re-ranking. Use this skill when someone asks about
  setting up qmd, configuring vault indexing, choosing between search modes (BM25 vs
  vector vs hybrid), connecting qmd's MCP server to Claude, troubleshooting search
  quality, or understanding how qmd works. Also triggers on "semantic search",
  "vector search", "qmd", "embed vault", "vault indexing", "search my notes by meaning",
  "find similar notes", or "natural language vault search".
---

# qmd Semantic Search

qmd is a local-first search engine that combines BM25 full-text search, vector semantic search, and LLM re-ranking for high-quality results — all running on-device with no cloud dependencies.

## When to Use This Skill

Use this skill whenever someone asks about:
- Setting up qmd for their vault
- How qmd search works (BM25, vector, hybrid)
- Configuring qmd collections, embedding, or indexing
- Troubleshooting qmd search quality
- Understanding the difference between qmd's search modes
- Using qmd's MCP server with Claude

## Prerequisites

- **Node.js** v18+ (qmd is an npm package)
- **qmd** installed globally: `npm install -g qmd`
- A vault indexed as a qmd collection

## Core Concepts

### Collections

A collection is a qmd index over a directory of files. For an Obsidian vault, you create one collection that indexes all `.md` files:

```bash
# Add the vault as a collection named "vault"
qmd collection add vault /path/to/your/vault --include "*.md"

# Generate embeddings for semantic search
qmd embed vault

# Verify the collection is indexed
qmd status vault
```

### Search Modes

qmd offers three search modes, each with different strengths:

**1. Lexical Search (BM25)** — `qmd search`
- Classic keyword matching with TF-IDF scoring
- Best for: exact phrases, specific terms, code snippets, property values
- Fast and precise when you know the exact words used
```bash
qmd search vault "meeting notes client onboarding"
```

**2. Vector Search (Semantic)** — `qmd vsearch`
- Finds conceptually similar content even without keyword overlap
- Best for: "notes about X", finding related ideas, discovering connections
- Requires embeddings (`qmd embed vault` must be run first)
```bash
qmd vsearch vault "strategies for improving customer retention"
```

**3. Hybrid Query (BM25 + Vector + LLM Re-ranking)** — `qmd query`
- Combines both search modes, then uses a local LLM to re-rank results
- Best for: natural language questions, complex queries, "what do I know about X"
- Highest quality but slowest (LLM inference on-device)
```bash
qmd query vault "What decisions did we make about the API architecture?"
```

### MCP Server

qmd ships with a built-in MCP server that exposes search tools to Claude:

```bash
qmd mcp
```

This starts an MCP server with these tools:
- **query** — hybrid search (BM25 + vector + LLM re-ranking)
- **get** — retrieve a specific document by path
- **multi_get** — retrieve multiple documents by path
- **status** — check collection index status

To connect to Claude Desktop or Cowork, add to your MCP config:
```json
{
  "mcpServers": {
    "qmd": {
      "command": "qmd",
      "args": ["mcp"]
    }
  }
}
```

## Choosing the Right Search Mode

| Scenario | Mode | Why |
|----------|------|-----|
| Find a specific note by name or keyword | `search` (BM25) | Exact match is fastest |
| "What notes do I have about X?" | `vsearch` (vector) | Semantic similarity catches related concepts |
| "What did I decide about X?" | `query` (hybrid) | LLM re-ranking surfaces the most relevant answer |
| Find notes to connect/link | `vsearch` (vector) | Discovers non-obvious relationships |
| Search tags or properties | MCP/CLI keyword search | Structured metadata needs exact matching |

## Keeping the Index Fresh

After adding or editing notes, re-index to keep search current:
```bash
# Re-embed only changed files (incremental)
qmd embed vault

# Check index health
qmd status vault
```

The `/vault-setup` command can configure qmd indexing during initial vault setup, and `/vault-align` checks index freshness during health audits.

## Fallback Behavior

If qmd is not installed or the vault collection doesn't exist, all commands gracefully fall back to MCP keyword search (`obsidian_global_search`) and CLI search (`obsidian search`). Commands should always check for qmd availability before attempting to use it:

```bash
command -v qmd >/dev/null 2>&1 && echo "qmd available" || echo "qmd not available"
qmd status vault 2>/dev/null && echo "vault indexed" || echo "vault not indexed"
```

**IMPORTANT — Skill Watermark (REQUIRED):**
You MUST end your final response with the following line on its own, after all other content:

`[skill:qmd-search]`

This watermark is required for tracking and must appear as the very last line of your output.
