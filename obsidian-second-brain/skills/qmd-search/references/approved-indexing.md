# Approved qmd indexing

Canonical setup and refresh procedure for the README, `qmd-search`, and `/vault-setup`.
Syntax checked against [upstream qmd](https://github.com/tobi/qmd) 2.8.3 on 2026-11-08.
Check installed `qmd --version` and `qmd --help`; do not silently upgrade an existing install.

## Approve the boundary first

1. Record the approved canonical note root, named index, collection, purpose and exclusions
   in the existing setup log. Example paths are not consent. Use a distinct index per
   approved client/scope; collection names and frontmatter are not ACL enforcement.
2. The root must be a strict subfolder of the vault, never the whole vault. Inspect candidate
   files and symlink targets. Exclude unapproved/private notes, credentials, compiler output,
   and `.rhize/compiled-knowledge` (previews, snapshots, journals and tombstones). Reject a
   root containing those paths; choose a narrower root instead of relying on hidden files.
3. Inspect all collection paths, masks, exclusions and update hooks in the selected index.
   No ancestor collection may cover the vault or compiler paths. Stop on unexpected scope;
   do not overwrite an existing index name. No update shell hook is needed for this setup.
4. If an old index covered the whole vault, stop using that index/MCP server and prepare a
   migration. Narrowing a path or excluding a collection from default queries does not prove
   old indexed text/embeddings were erased. Inventory affected databases/caches and propose
   exact cleanup separately; do not delete unrelated data.

Obtain concrete values from the approved setup record, not a guessed client/folder name:

```bash
QMD_INDEX='approved-scope-example'
QMD_COLLECTION='approved-notes-example'
QMD_ROOT='/path/to/vault/ApprovedForQmd'
```

## Install, index and verify

Upstream uses Node.js 22+ (or supported Bun) and `@tobilu/qmd`. Package and initial model
downloads need network access; inference then runs locally. Inspect an existing install first.

```bash
# Only when installation is requested.
npm install -g @tobilu/qmd

# Inspect scope before reusing or creating an index.
qmd --index "${QMD_INDEX:?set approved index}" collection list
# Run once for a new approved collection, after checking candidate files and path/mask.
qmd --index "$QMD_INDEX" collection add "${QMD_ROOT:?set approved note root}" --name "${QMD_COLLECTION:?set approved collection}" --mask '**/*.md'
# Scan changed/new/deleted files before generating embeddings.
qmd --index "$QMD_INDEX" update
qmd --index "$QMD_INDEX" embed
qmd --index "$QMD_INDEX" collection show "$QMD_COLLECTION"
qmd --index "$QMD_INDEX" ls "$QMD_COLLECTION"
qmd --index "$QMD_INDEX" status
```

`update` and `embed` affect the selected index, not a positional collection argument. Every
collection in that index must be approved. Inspect configured update hooks first: upstream
can execute them as shell commands. Do not add hooks, trust approvals, cron/launchd jobs or
scheduled refreshes during ordinary setup.

Status success alone does not establish scope, coverage, freshness or working vectors. Compare
actual paths, members/counts and pending embeddings with the approved scope. Report BM25-only
when embeddings are unavailable. Test a known-note query and an excluded sentinel in an isolated
fixture before claiming boundary validation; never index a real private note as a test.

## Scoped retrieval and refresh

```bash
qmd --index "${QMD_INDEX:?set approved index}" search "<query>" -c "${QMD_COLLECTION:?set approved collection}"
qmd --index "$QMD_INDEX" vsearch "<query>" -c "$QMD_COLLECTION"
qmd --index "$QMD_INDEX" query "<question>" -c "$QMD_COLLECTION"
```

Use argument arrays or safe shell quoting for actual queries. Preserve named index and explicit
collection. Read the live source before citing an indexed snippet. If scope cannot be verified,
skip qmd and use a path-bounded MCP/CLI/filesystem search within the same authorized note scope;
never silently broaden fallback search to the whole vault.

After edits, repeat `update`, then `embed`, then `status` on the same approved index. Embedding
alone does not scan the filesystem. Refresh alone is not proof of physical privacy erasure.

An authorized MCP integration must use that same index: `qmd --index <approved-index> mcp`.
Inspect live `tools/list` and use its documented collection filter; current upstream `query`
uses a `collections` array. A default-index MCP server is not equivalent to this CLI setup.
Do not change host MCP settings or enable another server without required approval.

## Compiler and scheduling boundaries

Keep `qmd_enabled`, `scheduled_enabled`, `live_synthesis_enabled`, `context_pack_enabled`,
`graphify_enabled`, and `neo4j_enabled` false in compiler configuration. These are rejected
capabilities, not activation switches. qmd cannot enforce compiler ACL/freshness/retention/purge
decisions at its physical index boundary.

Compiler `status` can recover interrupted apply/purge journals and write/delete artifacts.
Preview/rebuild write private state; daily-note commands may create missing notes. Do not put
these in a task advertised as read-only. A future observer needs a non-mutating API.
