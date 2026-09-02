# Context-experiment provider internals

Deep reference for the `/context-experiment` command and the `context-experiment-selector.js`
/ `context-experiment-finalizer.js` hooks: what each candidate retrieval provider is, how the
live gate decides whether an attempt is allowed to run, and how its evidence is recorded and
verified. See the README's Hooks section for the one-paragraph summary and the GUIDE.md entry
for when you'd reach for `/context-experiment` at all.

## Context-tool dogfood providers

The experiment selector does not install the official mgrep agent instructions or replace
CodeGraph/`rg`. The tested CLI is pinned to `@mixedbread/mgrep@0.1.13`; install and remove it
explicitly with `npm install -g @mixedbread/mgrep@0.1.13` and
`npm uninstall -g @mixedbread/mgrep`. `mgrep login` uses the vendor's device flow and writes
its token to `~/.mgrep/token.json`; `/context-experiment doctor` refuses that login when the
file is broader than mode `0600`. A dry-run may create or retrieve the named remote store but
does not upload files. Actual repository indexing always requires a separately reviewed local
manifest and explicit approval for the exact repository and `rhize-dogfood-*` store.

The current dogfood gate is stricter: do not create a Mixedbread account, run `mgrep login`, or
create a store until the dated provider-economics/privacy review in
[`mgrep-context-compiler-dogfood.md`](../../.claude/plans/mgrep-context-compiler-dogfood.md)
passes. Mixedbread's published free-tier data-use language is contradictory, so the plan tests a
pinned local semantic-retrieval candidate first and keeps managed mgrep as a separately measured,
explicitly approved arm.

The local comparison path pins grepai `0.35.0`, Ollama `0.33.1`, and
`nomic-embed-text:v1.5`. It runs only with loopback Ollama, cloud features disabled, a reviewed
configuration checksum, a GOB store, and a current independently generated snapshot marker.
Direct `grepai watch` execution in a real main worktree is prohibited: 0.35.0 automatically
discovers and initializes linked worktrees and has no supported opt-out. The first real isolated
six-case benchmark also failed correctness non-inferiority (five critical misses versus zero for
ripgrep), so `localRetrieval` remains disabled and unarmed pending a materially improved provider
or configuration. See [`evals/context-tools`](../../evals/context-tools/README.md).

The Context Compiler adapter runs an unmodified checkout pinned to revision
`4edb163911f9a6bc869f35970fa77acb3dd88b8f`, verifies the MIT license and source-file
checksums, and emits deterministic, repository-relative private prompt packs. `/context-pack`
is the explicit preview path and never injects its output. Repository-wide dynamic dispatch,
event decorators, callback registration, or unsupported Python syntax force a baseline fallback;
the 40,000-token, 50%-coverage, and 10-name-collision limits remain preliminary guardrails, not
evidence that a pack improves a coding task. The default checkout is
`~/.claude/rhize-context-manager/providers/context-compiler`; override it with
`RHIZE_CONTEXT_COMPILER_CHECKOUT`. See
[`evals/context-tools`](../../evals/context-tools/README.md).

The default `/context-pack --provider native` path is Rhize-owned and local-only. Native v2 uses
parser-backed multiline Python/JavaScript/TypeScript contracts, configured Python source roots,
JS/TS aliases, workspace imports, and package exports. It includes explicit targets in full,
renders safe dependencies as interfaces, widens uncertain interfaces to full source, and adds
related tests/configuration when they fit. Query discovery uses CodeGraph only after an existing
`.codegraph/` passes a read-only healthy/current status preflight; otherwise it records deterministic
`rg` fallback and never creates an index. An optional `--impact-map <repository-local-markdown>`
bridge expands semantic terms and consumes named source-file seeds while storing only the plan
content hash, normalized term-set hash, and seed count — never plan content or an absolute path.
Planned, dynamic, and unsupported edges remain untrusted and fail closed.
Every manifest records provider revision, task/query hashes, source/rendered hashes, the private
prompt hash, selection reasons, token budget, and warnings without source text. `verify-pack`
requires the matching manifest and prompt paths and rejects any identity, prompt, snapshot, or
entry-hash drift. The five-case native corpus plus the nine upstream cases totals 14 compiled-
context cases. The prior native-v1 corpus remains historical evidence; v2 adds separate contract,
alias/workspace, source-root, eligibility, exclusion-ledger, and hash-only impact-map/`rg` fixtures.
The three assisted discovery cases must improve supported recall while continuing to reject
dynamic or unsupported cases. This supports disabled-by-default controlled use, not an inference
of task correctness.

## The live P4 gate

The live P4 gate is stricter than preview mode. Selection refuses a dirty repository, unresolved
local dependency, truncated dependency traversal, required dependency omitted by budget, or a
preflight that exceeds `maxDurationSeconds`. It verifies the pack immediately after writing it,
then reserves the configured canary/continuous authority before returning context. The
non-reclaiming lease prevents a second
session from claiming the same repository/capability even after the ordinary lease TTL. Any Stop
outcome writes one terminal receipt: evidence-backed completion releases continuous single-flight
and leaves it enabled, while failed, incomplete, stale, or malformed evidence freezes it. Canary
mode preserves the prior one-shot freeze behavior. A later selector audit terminalizes expired
pending attempts as incomplete instead of reclaiming them.

On a compiled-context B claim, selector `additionalContext` prints the exact installed
`runner.py` path, the real experiment id, and a shell-quoted `record-evidence` command. It also
requires the agent to read and use the accepted prompt pack before implementation and validate
the task before recording success, so neither command location nor working directory is guessed.
The `validation-id-REPLACE_ME` token must be replaced with a source-free validation identifier;
the evidence parser rejects the unchanged placeholder.

A reviewer may record the minimum immutable task evidence while the attempt is pending:

```bash
python3 scripts/context_experiments/runner.py record-evidence \
  --experiment-id exp-REDACTED \
  --task-outcome completed \
  --pack-used \
  --validation-id pytest-context-tools \
  --executed-arm B \
  --skip-arm A:no_comparable_shadow_evidence
```

The sidecar contains only the experiment id, timestamp, outcome enum, pack-use boolean,
source-free validation ids, and exact arm accounting. It rejects prompts, source/output, paths,
URLs, duplicate writes, and evidence without a matching pending attempt. Receipt v2 binds its
SHA-256 digest, the claim/final pack-verification results, a terminal reason, and source-free
completeness state/booleans. The command records reviewer
assertions; it does not infer task correctness. A comparable Arm A remains a separate evidence
requirement, and `capture-health` flags a reviewed B-only run as non-comparable.

## Capture reliability

Capture reliability is independently queryable and fail-closed:

```bash
python3 scripts/context_experiments/runner.py capture-health
```

The command strictly parses every receipt, review sidecar, and pending selection; reconciles
sidecar digests and stored completed receipts against each capability's `completedRuns`; and keeps
completed/incomplete/skipped Arm A and Arm B counts separate per capability. Legacy receipt v1
still requires comparable A/B metrics. Receipt v2 requires exact arm accounting and reports
evidence state, terminal reasons, configured canary/continuous live/frozen state, comparable,
skipped, incomplete, and failed runs separately. It exits `2` for
malformed or mismatched artifacts, failed or incomplete receipts, missing-arm/metric/history
evidence, non-comparable A/B measurements, orphan evidence, or a pending selection that outlived
its lease without producing a receipt. It never generates benchmark evidence or substitutes a
provider double for a real dogfood run.
