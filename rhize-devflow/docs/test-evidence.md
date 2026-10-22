# Behavioral test-evidence contract

`test-evidence` is an explicitly invoked pre-review writer. It classifies a claimed test contract
and binds that claim to an exact Git state. Without `--sandbox-image`, clean claims receive
`execution_unavailable`; dirty checkouts receive `mutation_unavailable_dirty_state`. Opting in with
an existing local Docker **full sha256 image ID** enables isolated execution. No image is pulled,
dependency installed, host test command run, or provider called. `/review` remains read-only.

## Classes and verdicts

- **Behavior**: ultimately requires a sandbox-executed independent oracle or killed mutant.
  A declared oracle is metadata, not proof that the test ran.
- **Artifact**: exact text/schema/config is the contract and must include its scoped rationale.
  A rationale alone cannot produce a supported verdict.
- **Structural**: cites an architecture invariant and should use AST/schema/graph evidence.

The complete verdict vocabulary is defined in `schemas/test-evidence-v1.schema.json`. A stale or
unknown packet is rejected. Legacy runner1.1.0 execution claims remain rejected. Runner1.2.0
supports `oracle_supported`, `artifact_contract` or `killed` only with a matching private execution
receipt, clean source binding, passing baseline and restored final rerun, and verified cleanup.
`killed` specifically requires the fixed Python harness's assertion-failure classification (exit10),
at least one exercised test and a changed snapshot. Collection/setup/import/syntax errors, skips,
timeouts and opaque package-script failures cannot count as a killed mutant. A surviving mutant
remains unsupported. The selected test and oracle still need independent review; the harness does
not prove that an intentionally dishonest test describes the governing invariant.

## Safety and recovery

The runner refuses protected mutation targets after canonical path resolution: workflows,
migrations, generated output, deployment files, billing/payment code, every `.env*` form (including
`.envrc`), and declared external effects. Repository inputs, packet outputs, lease paths, and their
parents cannot be symlinks. Invocations are either a named `test`/`test:*` package script, or an exact
`.py` file also listed in `test_files` with source `python_unittest` or `python_pytest`. The Python
path and bytes are digest-bound. The adapter constructs fixed argv; prose cannot supply commands.
Package scripts run through `npm --ignore-scripts run NAME`, without pre/post lifecycle hooks.
Python uses the bundled isolated unittest/pytest harness for that exact file; glob/selector names
are refused. The workspace is added to the import path after trusted runner modules load. Pytest
cache and plugin autoload are disabled; repository conftest remains candidate code inside isolation.

The Docker adapter uses an empty client configuration and explicit local Unix socket, avoiding
ambient proxy/credential settings. It rejects image-declared volumes, overrides entrypoints and
clears the candidate environment. Containers run as nonroot with network disabled, read-only root
and snapshot, no capabilities, no healthcheck/log persistence, a64MiB noexec temporary filesystem,
64-process/512MiB/one-CPU limits and no host socket. Dependencies must already exist in the chosen
trusted image. Only tracked regular files matching immutable Git blob identities enter the snapshot;
Git metadata, `.env*`, credential directories, node_modules and host virtualenvs are excluded.
Candidate code has no writable host mount. Snapshot size is bounded; symlinks/submodules refuse.

A private outer directory protects the readable container snapshot. Mutation preserves bytes and
mode; restoration runs in `finally` and rechecks the whole snapshot before a fresh final container.
A nonblocking per-repository lease prevents concurrent execution. Docker client deadlines terminate
and reap its process group; every container is force-removed with volumes and absence verified.
Uncertain cleanup yields `cleanup_failed`, a named resource, and `FAIL_REQUIRES_HUMAN`; never retry
or restore the live checkout automatically. Unavailable isolation yields an unsupported packet.

Receipts live under `~/.rhize/test-evidence/receipts` (0700 directory,0600 write-once files). They
bind the packet, image and both producer/adapter source hashes. They prevent a candidate container or an
edited packet from manufacturing supported execution. The host owner, local Docker daemon/CLI and
selected image remain trusted: these are local operational receipts, not signed third-party
attestations against a malicious same-user host writer. An independent oracle's rationale remains
operator-supplied and still needs skeptical review. A passing test does not establish task acceptance.

Docker flag behavior and automatic proxy injection: [run reference](https://docs.docker.com/reference/cli/docker/container/run/),
[client proxy configuration](https://docs.docker.com/engine/cli/proxy/).

Packet output and lease paths must live outside the target repository. Packets bind the live
checkout's initial and final fingerprints; a changed or incomplete binding is not accepted as
regression evidence.

## Explicit Python invocation

Use the existing run spec with `test_invocation: {"source":"python_unittest","name":"tests/test_calc.py"}`
(or `python_pytest`), and include that same path in `test_files`. The remaining contract, oracle,
mutation and base fields are unchanged. Run the writer with `--sandbox-image sha256:FULL_LOCAL_IMAGE_ID`.
Dependency discovery, image selection and the regression oracle remain the reviewer's responsibility.

Provider-free live acceptance is explicit: `python3 evals/test-evidence/run_acceptance.py --image
sha256:FULL_LOCAL_PYTHON_IMAGE_ID` from the repository root. An optional `--node-image` checks the
package-script lane too. It tests known-defect mutation, blocked network/host reads/writes/ambient
credentials, timeout with a forked child, source preservation and removal of every container.
This disposable fixture acceptance is separate from the normal test suite and real task benefit.

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
