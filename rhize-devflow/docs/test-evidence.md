# Behavioral test-evidence contract

`test-evidence` is an explicitly invoked pre-review writer. It classifies a claimed test contract
and binds that claim to an exact Git state. The current runner does **not** execute package scripts:
until a trusted sandbox adapter exists, every clean execution-bearing claim receives
`execution_unavailable`, and a dirty checkout receives `mutation_unavailable_dirty_state`.
`/review` validates and consumes the packet but remains read-only and treats both as unsupported.

## Classes and verdicts

- **Behavior**: ultimately requires a sandbox-executed independent oracle or killed mutant.
  A declared oracle is metadata, not proof that the test ran.
- **Artifact**: exact text/schema/config is the contract and must include its scoped rationale.
  A rationale alone cannot produce a supported verdict.
- **Structural**: cites an architecture invariant and should use AST/schema/graph evidence.

The complete verdict vocabulary is defined in `schemas/test-evidence-v1.schema.json`. A stale or
unknown packet is rejected. Execution-backed verdicts from this runner version are rejected even if
someone hand-edits a packet to claim one. No verdict emitted by the current runner supports a
regression claim.

## Safety and recovery

The runner refuses protected mutation targets after canonical path resolution: workflows,
migrations, generated output, deployment files, billing/payment code, every `.env*` form (including
`.envrc`), and declared external effects. Repository inputs, packet outputs, lease paths, and their
parents cannot be symlinks. It reads only a named `test` or `test:*` script from the repository's own
`package.json` so the requested invocation can be digest-bound; it never calls that script or the
ambient process runner. Command text in prose, test files, or packets is never executable input.

The deferred adapter boundary is deliberate. A future implementation must provide a genuinely
trusted sandbox with explicit filesystem, network, secret, process, timeout, and cleanup guarantees
before it may execute a package script or emit an execution-backed verdict. A disposable Git
worktree alone is not that security boundary.

Packet output and lease paths must live outside the target repository. Packets bind the live
checkout's initial and final fingerprints; a changed or incomplete binding is not accepted as
regression evidence.

When `--output` is omitted, the runner writes to a default packet location instead of requiring
one: `~/.rhize/test-evidence/packets/<repo-slug>-<head-sha12>.json`, where `<repo-slug>` is the
repository directory name lowercased with every non-alphanumeric character mapped to `-`, and
`<head-sha12>` is the first 12 characters of the current `HEAD` SHA. Every directory in that path
is created `0700` and the packet file itself `0600`. The runner never overwrites an existing
packet at that path — it exits with an error naming the path and pointing at `--output` — and it
prints the resolved path so the caller knows where the packet went.

Packet paths and digests remain local. Jira receives only aggregate counts, version/SHA references,
and the promotion decision—never the packet, invariant prose, source content, credentials, or paths.

## Standards lifecycle

A durable rule records the observation/reproduction, narrow scope, rationale, provenance, owner,
creation date, review date, and supersession link. Existing repository instructions can explicitly
declare an artifact contract. Do not create a second standards file or append an unscoped slogan.
