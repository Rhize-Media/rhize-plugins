# Impact Map Reference

Detailed rationale, examples, and troubleshooting for the compact
[`/rhize-devflow:impact-map`](../commands/impact-map.md) command. Load this reference only when the
task needs the relevant detail; the command owns the executable contract.

Map a change before implementation, then reconcile the completed diff against the same evidence.

## Core Contract

- **CodeGraph is authoritative for current structural truth:** symbols, callers, callees,
  references, tests, and dependency paths that exist now.
- **The impact map is authoritative for intended change:** business behavior, data scope,
  invariants, planned symbols, operational effects, risks, and acceptance criteria.
- Do not copy CodeGraph's full dependency output into the map. Record only the relevant evidence
  and the semantic delta the graph cannot express.
- Label facts as **evidence**, **inference**, or **planned**. Never present an inferred edge as a
  confirmed caller.

## Triggers

Use before implementing or materially changing a feature, bug fix, refactor, schema, migration,
cache path, authorization rule, external integration, or cross-repository contract.

## Phase 1: Establish Scope and Repository Rules

1. Read repository instructions and required context files.
2. Check Git state and preserve unrelated work.
3. Identify every repository root involved. A frontend/backend workspace is two graphs, not one.
4. Check `COMPONENT_REGISTRY.md` or the project's equivalent when present.
5. State the requested outcome and any ambiguity that would materially change implementation.

Do not write implementation code yet. Follow the repository's confirmation rule: present the map
and pause only when confirmation is required or a material product choice remains unresolved.
Existing explicit implementation authorization is not invalidated by this command.

## Phase 2: Discover Current Structural Truth

Run this decision for **each repository root**.

### When `.codegraph/` exists

Use CodeGraph before text search or manual file reading:

```bash
codegraph status
codegraph explore "<entry points, symbols, behavior, callers, and tests>"
codegraph impact <symbol>
codegraph affected <changed-or-planned-existing-files>
```

Prefer the `codegraph_explore` MCP tool when available. Use its health/status metadata when the
interface exposes it; when it exposes only exploration, begin with a narrow query and treat a
successful indexed response as availability evidence. An MCP error indicating a missing, stale, or
corrupt index triggers the fallback below. Do not require a shell preflight when MCP is the active
interface.

If the MCP tool is unavailable, use the shell CLI only after `command -v codegraph` succeeds. Treat
`codegraph status` as the CLI preflight: do not run or trust shell graph queries until it exits zero
and reports a healthy, current index. If neither interface is available, status exits nonzero, the
index is missing or corrupt, or synchronization fails, record the exact unavailable/stale condition
and fall back to `rg` plus targeted reads. If status reports a stale but otherwise healthy index,
run `codegraph sync` and repeat status before querying. Never silently treat unhealthy graph output
as current. Use `codegraph node`, `callers`, or `callees` only for a narrower follow-up.

### When `.codegraph/` does not exist

Do not initialize CodeGraph. Indexing is a project/user decision. Fall back to `rg` and targeted
reads:

```bash
rg -n "<symbol-or-route>" .
rg --files | rg "<feature-or-domain>"
```

Use the same fallback when CodeGraph cannot parse a relevant language or generated/runtime edge.

### Structural questions to answer

- What are the public, administrative, job, CLI, or event entry points?
- Which symbols own the behavior, and which callers consume them?
- What types, schemas, migrations, caches, query keys, permissions, and transactions participate?
- Which tests currently cover those paths?
- Are there dynamic dispatch, reflection, generated code, configuration, environment, or external
  systems that CodeGraph cannot see?
- For multiple repositories, where is the API/event/schema boundary between their separate graphs?

## Phase 3: Build the Semantic Impact Map

Use this output. Omit empty sections, but never omit invariants, acceptance tests, or explicitly
unaffected paths for a material change.

```markdown
# Impact Map: <change>

## Current behavior and evidence
- <observed behavior, entry point, and concise CodeGraph/source evidence>

## Intended semantic delta
- <what users/data/system behavior must change>

## Invariants and must-not-change boundaries
- <historical attribution, authorization, idempotency, transaction, compatibility, etc.>

## Invariant clauses (optional for static evidence)
| Clause | Owning symbol/path | Structural evidence | Independent acceptance check | Static hint / unresolved gap |
|---|---|---|---|---|
| <invariant> | <owner> | <confirmed source or graph edge> | <behavioral oracle> | <advisory Skylos rule, or unavailable> |

## Current structural touchpoints
| Repository | Entry point or symbol | Why affected | Evidence |
|---|---|---|---|

## Planned additions and deletions
- <new routes, commands, migrations, tests, or removals that do not exist in CodeGraph yet>

## External and operational effects
- <database migration, cache, queue, analytics, deployment order, repair/backfill, credentials>

## Reuse opportunities
- <registry entry or existing implementation to reuse>

## Acceptance tests
- <observable behavior and failure/concurrency/boundary cases>

## Explicitly unaffected paths
- <nearby behavior that must remain scoped as it is>

## Unknowns and confidence
- <known graph blind spots, assumptions, and how they will be verified>

## Implementation order
1. <smallest failing test or contract first>
2. <source-system implementation>
3. <integration/cache/UI>
4. <validation and reconciliation>
```

Persist the map only when project instructions require a plan file or the work must survive a
session boundary. Otherwise, keep it in the response or active plan. Do not create a generic
`IMPACT_MAP.md` by default.

## Phase 4: Execute From the Map

### Record the enforcement receipt

Persist the map in the repository's required plan location, then run the gate CLI before the
first production/source edit. Use the installed script path printed by the refactor gate's prompt
hook. In Claude installations that expose the plugin root, the equivalent command is:

```bash
python3 "$CLAUDE_PLUGIN_ROOT/scripts/refactor_gate.py" prepare \
  --workspace "<workspace-root>" \
  --plan "<workspace-root>/.claude/plans/<descriptive-name>.md" \
  --query "<entry points, symbols, behavior, callers, and tests>"
```

The receipt command performs the structural preflight for every discovered Git root, reads and
hashes any component registry, and records explicit `rg` fallback evidence where CodeGraph is
absent or unhealthy. It never initializes CodeGraph. Do not bypass the gate merely because a
repository lacks one of the optional artifacts.

The map must live inside `--workspace`. When the workspace is a linked Git worktree (an
executor's isolated checkout), a map in the primary checkout is also accepted, so an
orchestrator can prepare the subagent's worktree from its own `.claude/plans/` without copying
the file. Prepare the executor's worktree before dispatching it: a worktree nested in a pending
parent checkout is an untracked directory there, so the parent's after-the-fact check cannot see
edits inside it.

### Shell writes: static block plus after-the-fact check

Native edit tools are checked before they write. Shell commands are checked twice, because no
static reading of a shell command is complete:

- **Before the command (`hook-command`, PreToolUse).** The gate parses the command and blocks,
  with the same exemptions and `prepare` instructions as an edit tool, when it would write
  source while the receipt is `pending`: output redirects (`>`, `>>`, `>|`, `&>`), `tee`,
  in-place editors (`sed -i`, `perl -i`, `ruby -i`), `cp`/`mv`/`install` destinations,
  `git apply`/`patch` targets read from the patch, and `open(..., 'w')`, `write_text`,
  `writeFileSync` and similar calls in Python/Node/Ruby/Perl `-c`/`-e` snippets or heredoc
  bodies. Snippet targets count when they are literals, `Path('…')`, or a name assigned a literal
  or looped over a literal list; files a snippet only reads are not charged. Quoted or escaped
  operator characters (`grep -c '>' f`) are arguments, and comments follow bash's word-start
  rule. A leading `rtk`/`rtk proxy`, `env`, `VAR=value`, `npx`, `uv run` or `pnpm exec` prefix is
  ignored. A target counts only when it is tracked, or is a new, non-ignored code file inside the
  workspace; scratch and `/tmp` paths, ignored build output, logs, docs and plans pass. After
  `prepare`, the same commands are allowed and move the receipt to `implementation` with the
  session as an owner.
- **After the command (`hook-command-post`, PostToolUse).** While `pending`, the tree is compared
  with the dirty snapshot taken when the prompt armed the receipt, using the same source rule.
  When the command itself ran `git commit`, the commit's files are compared too; other HEAD moves
  (pull, checkout, rebase) only advance the stored HEAD, so someone else's commits are never
  charged. The commit is recognised from the command text (so `bash -c '… && git commit'`
  counts); a command that merely mentions `git commit` right after HEAD moved outside the hooks
  would charge that move, a deliberate narrow false positive. New source changes are reported once, recorded as `unprepared_source_changes`, and
  kept as evidence: `prepare` reuses the arm-time snapshot (with a fresh `HEAD`), and `reconcile`
  requires every recorded path in the map even if a later prompt re-armed the receipt.

The trade-off: the static check stops the common cases before they happen but misses commands
it cannot read — `bash -c`, `eval`, running a script, `npm run`/`make` targets, `xargs`,
`find -exec`, formatters with `--write`/`--fix`, `rm`, `git checkout`/`restore`, a `cd` on its own
line or inside a subshell, snippet targets built from expressions, and paths held in shell
variables. Commands over 100 KB skip static parsing. The after-the-fact check sees every one of
those, but only once the write has happened; it cannot undo it. It makes the bypass visible and
keeps it from disappearing into the baseline, including a hidden write committed in the same
command. Writes through tools that have no hook at all (for example an MCP filesystem server)
surface at the next shell command's comparison or at `prepare`, unless a new material prompt
re-arms the receipt first and folds them into the fresh snapshot.

### Optional local context-pack bridge

When `rhize-context-manager` is installed, the persisted semantic map may guide its native local
discovery. Use the exact installed `runner.py` path printed by the context selector (or resolve it
from that plugin) and pass the same plan explicitly:

```bash
python3 "<installed-rhize-context-manager>/scripts/context_experiments/runner.py" pack \
  --provider native \
  --repo "<workspace-root>" \
  --query "<the same entry points, symbols, behavior, callers, and tests>" \
  --impact-map "<workspace-root>/.claude/plans/<descriptive-name>.md"
```

The bridge is local-only. It stores only the map content hash, normalized term-set hash, and seed
count in the pack manifest. It never stores the plan path/text, initializes CodeGraph, or upgrades
a planned edge into structural evidence. A healthy existing CodeGraph remains first; absent,
stale, corrupt, dynamic, generated, or unsupported edges take the documented `rg`/targeted-read
fallback, and unsafe packs remain rejected.

1. Start with a failing acceptance or contract test.
2. Implement the smallest source-system change satisfying the semantic delta.
3. Preserve every must-not-change boundary.
4. Update the map when implementation evidence disproves an assumption or reveals a new consumer.
5. Run focused tests first, then the repository's required broader gates.

The graph suggests coverage; it does not prove runtime correctness, transaction ordering,
authorization, cache timing, or external-system behavior. Those require tests and, when relevant,
deployment-specific evidence.

## Phase 5: Reconcile After Implementation

Ordinary `.md`/`.markdown` notes under a detected `.obsidian/` vault are documentation for
write, reconciliation and release classification. Detection resolves symlinks and stops at
embedded Git/plugin roots and hidden runtime directories; it does not exempt `SKILL.md`,
MDX or executable files. A mixed note/source change still requires mapped source evidence.
Existing named-context and configuration exemptions remain unchanged.

For every repository root, repeat the same discovery branch used before implementation.

For roots with a healthy existing CodeGraph index:

```bash
codegraph sync
codegraph explore "<the same entry points, symbols, behavior, callers, and tests>"
codegraph affected <actual-changed-files>
```

Use equivalent MCP synchronization/health operations when exposed. Otherwise use the CLI only when
available. If the index cannot be refreshed after the implementation, record it as stale and take
the fallback branch; do not claim that the graph agrees.

For roots that used the fallback — including roots where CodeGraph is still unavailable or
unhealthy — repeat the original `rg` queries and targeted reads against the completed source. Map
the actual changed files, their consumers, and their tests. Do not award `IN_SYNC` merely because
that root has no graph.

Then compare the actual diff and graph with the impact map:

- Every changed production file traces to the intended semantic delta.
- Every new symbol/route/migration/test now appears in the graph where supported.
- Expected callers, caches, permissions, and tests remain connected.
- No explicitly unaffected path changed accidentally.
- Any deliberate deviation requires you to update the impact map with its rationale.

Report one **Reconciliation verdict**:

- `IN_SYNC` — structural evidence (CodeGraph or fallback), actual diff, and semantic map agree.
- `IN_SYNC_WITH_EXCEPTIONS` — named dynamic/generated/external edges require manual evidence.
- `OUT_OF_SYNC` — missing consumer, unexplained diff, stale graph, or unverified invariant remains.

Do not declare completion while the verdict is `OUT_OF_SYNC`.

Record that verdict in the enforcement receipt before commit or completion:

```bash
python3 "$CLAUDE_PLUGIN_ROOT/scripts/refactor_gate.py" reconcile \
  --workspace "<workspace-root>"
```

If the map changed, run `prepare` again before further source edits. If the task was classified as
a material change incorrectly, record the false positive rather than silently bypassing it:

```bash
python3 "$CLAUDE_PLUGIN_ROOT/scripts/refactor_gate.py" dismiss \
  --workspace "<workspace-root>" \
  --reason "<specific non-implementation reason>"
```

## Common Failure Modes

- **Context classified as source:** routine `.planning/STATE.md`, `docs/` prose, and standard
  context Markdown filenames (including nested projects) do not require a source impact map.
  The write, reconciliation, and release classifiers share this exemption. Executable files,
  MDX, and mixed source/context edits still require the source evidence gate.
- **File-list map:** duplicates CodeGraph and omits why behavior changes.
- **Graph-only planning:** cannot represent planned code, business invariants, or operational risk.
- **Blind graph trust:** misses dynamic dispatch, runtime configuration, external systems, and data
  semantics.
- **Unrequested indexing:** creates `.codegraph/` in a repository whose owner did not choose it.
- **Single-root analysis:** misses the other side of a frontend/backend or service boundary.
- **No reconciliation:** leaves a pre-implementation map stale as soon as the code changes.

## Related Workflows

- `/rhize-context-manager:done` — final verification after reconciliation.
- `/rhize-context-manager:context-hygiene` — preserve the map when work crosses a session boundary.
- `dev-flow-foundations` — rationale and reusable impact-analysis principles (same plugin).

## Optional local Laya shadow signal

When `RHIZE_LAYA_DEVFLOW_SHADOW=1`, after the deterministic impact map and its evidence file exist, invoke `scripts/typed_checkpoint.py --stage impact-map --mode shadow` with the bounded state in [the adapter contract](typed-checkpoint.md). Record the private receipt beside Arm A's impact-map verdict. An unavailable signal leaves the mapping obligations unchanged.
