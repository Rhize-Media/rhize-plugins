# graphify reference: extra exports and benchmark

Load this when the user passed one of the export flags (`--wiki`, `--neo4j`, `--neo4j-push`, `--falkordb`, `--falkordb-push`, `--svg`, `--graphml`, `--mcp`), or when the corpus is large enough for the token-reduction benchmark. Each step runs only for its own flag. Neo4j flags use the governed graph-memory handoff below; they never invoke Graphify's direct Neo4j exporter for Rhize data.

### Step 6b - Wiki (only if --wiki flag)

**Only run this step if `--wiki` was explicitly given in the original command.**

Run this before Step 9 (cleanup) so `.graphify_labels.json` is still available.

```bash
graphify export wiki
```

### Step 7 - Governed Neo4j handoff (only if --neo4j or --neo4j-push flag)

Do **not** run `graphify export neo4j` or its `--push` form for Rhize governed data. Raw ids are not
tenant identities, per-record autocommit is not atomic publication, and that export loses required
provenance and parallel evidence.

- For `--neo4j`, finish `graphify-out/graph.json`, then invoke the canonical
  `rhize-context-manager:graph-memory` workflow to create a hashed manifest and run `validate` plus a
  private `preview`. The governed adapter consumes the portable artifact; it never consumes generated
  Cypher.
- For `--neo4j-push`, explain that live push is unavailable in this release. RT-159 owns the first
  credentialed canary, backup, restore rehearsal, and promotion decision. Do not ask for Neo4j
  credentials or substitute Graphify's direct exporter.

The graph-memory fake adapter can exercise checksummed migrations, stage/publish, idempotency,
bounded reads, purge, and restore without opening a network connection. That is verification—not a
claim that live Neo4j changed.

If the portable artifact later produces possible duplicate identities, use `graph-memory hygiene
status` to inspect capability. Stateful review is unavailable until its owning domain supplies a
private-state adapter. Do not substitute a plugin-local ledger. Similarity and scheduled
consolidation may eventually enqueue review proposals only; they can never export Cypher, alter
`graph.json`, or create `SAME_AS` automatically.

### Step 7a - FalkorDB export (only if --falkordb or --falkordb-push flag)

**If `--falkordb`** - generate a Cypher file. The statements are OpenCypher, but FalkorDB's `GRAPH.QUERY` runs one statement at a time (no bulk script import like Neo4j's `cypher-shell`), so prefer `--falkordb-push` to load a graph. Use this only when you want the portable `cypher.txt` artifact:

```bash
graphify export falkordb
```

**If `--falkordb-push <uri>`** - push directly to a running FalkorDB instance. Credentials are optional; ask the user only if the instance requires auth:

```bash
graphify export falkordb --push falkordb://localhost:6379
```

Default URI is `falkordb://localhost:6379` (the scheme is informational - `redis://` or a bare `host:port` work too), auth is optional, and the target graph defaults to `graphify`. Uses MERGE - safe to re-run without creating duplicates.

### Step 7b - SVG export (only if --svg flag)

```bash
graphify export svg
```

### Step 7c - GraphML export (only if --graphml flag)

```bash
graphify export graphml
```

### Step 7d - MCP server (only if --mcp flag)

```bash
$(cat graphify-out/.graphify_python) -m graphify.serve graphify-out/graph.json
```

This starts a stdio MCP server that exposes tools: `query_graph`, `get_node`, `get_neighbors`, `get_community`, `god_nodes`, `graph_stats`, `shortest_path`. Add to Claude Desktop or any MCP-compatible agent orchestrator so other agents can query the graph live.

To configure in Claude Desktop, add to `claude_desktop_config.json`. Claude Desktop can't run `$(...)`, and under `uv tool install` the system `python3` can't import graphify — so set `command` to the **absolute interpreter path** printed by `cat graphify-out/.graphify_python`:
```json
{
  "mcpServers": {
    "graphify": {
      "command": "<absolute path from: cat graphify-out/.graphify_python>",
      "args": ["-m", "graphify.serve", "/absolute/path/to/graphify-out/graph.json"]
    }
  }
}
```

### Step 8 - Token reduction benchmark (only if total_words > 5000)

If `total_words` from `graphify-out/.graphify_detect.json` is greater than 5,000, run:

```bash
graphify benchmark
```

Print the output directly in chat. If `total_words <= 5000`, skip silently - the graph value is structural clarity, not token compression, for small corpora.
