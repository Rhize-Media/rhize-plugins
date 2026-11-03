# Shared Claude/Codex bridge

`cross-model-handoff` wraps a small, standard-library Python 3.11+ MCP stdio server.
Each host starts its own connection to the same private job directory. The Claude
connection can request Codex work; the Codex connection can request Claude work.
Reviews return findings. File tasks return validated edits in an isolated copy for
the coordinator to test and integrate. Workers have no tools in either direction.

## Install and verify

Once `rhize-bridge` is registered in both hosts, install each new release with one command
from an up-to-date rhize-plugins checkout (`git fetch` first; the script does not fetch):

```bash
python3 rhize-ops/scripts/install_bridge.py 0.34.0 --dry-run
python3 rhize-ops/scripts/install_bridge.py 0.34.0 --codex-model gpt-6-luna --claude-model claude-haiku-5-5
```

It checks that `--ref` (default `origin/main`) is that `rhize-ops` version, checks both
subscription logins (step 1), copies `scripts/agent_bridge.py` to
`~/.rhize/agent-bridge-releases/<version>/` (700/600), handshakes both origins against the
new copy before touching any host, backs up `~/.claude.json` and `~/.codex/config.toml`, and
changes only the `rhize-bridge` script path in each host. Each host's other arguments, such
as its `--claude-bin` and Codex tool approvals, are carried forward unchanged. If either host
ends up with any other change, both are restored and it fails. With `--codex-model` and
`--claude-model` it also runs one synthetic review in each direction. It writes
`installation.json` with the hash, source commit, release tags, previous release and probe
results. An already-installed version is re-activated from its pinned copy after a SHA-256
check. Step 4's fresh-session check remains manual, and `installation.json` records it as
not run. The first install, or a host whose entry is missing, follows steps 1-3 by hand.

1. Verify `claude --version`, `codex --version`, `claude auth status --json` and
   `codex login status`. Require Claude's first-party `claude.ai` login and Codex's
   ChatGPT login. This server does not log in, install or upgrade either CLI.
2. Copy `scripts/agent_bridge.py` from a reviewed release to a versioned private
   installation directory, recording its SHA-256. Keep that directory and the default
   state directory `~/.rhize/agent-bridge` owned by the user, mode 700. Script mode 600
   is sufficient because Python invokes it. Use an absolute Python executable and
   script path; do not point a live server at a mutable plugin cache or worktree.
3. Back up host configs privately. Register `rhize-bridge` using each native host's MCP
   add command. Set the command to the absolute Python executable and arguments to
   `[absolute_script, "--origin", "claude"]` in Claude and the same with `"codex"`
   in Codex. Optional `--claude-bin`, `--codex-bin`, `--state-dir` pin absolute paths.
   Do not overwrite other MCP entries. For an explicitly authorized headless canary,
   Codex requires per-tool `mcp_servers.rhize-bridge.tools.<tool>.approval_mode="approve"`
   for those four tools when the parent uses `approval_policy="never"`; leaving the
   default can reject the handoff before a job exists. Scope any saved approval to
   the reviewed bridge tools, preserving other servers and shell approval policy.
   See the [Codex configuration reference](https://developers.openai.com/codex/config-reference/). Native CLI shims may require their original
   basename, so do not resolve a dispatch shim to its underlying manager executable.
4. Update the `rhize-ops` plugin through each host's plugin mechanism and start fresh
   sessions. Confirm the skill and all four MCP tools are discovered. Run synthetic
   review and task fixtures in both directions; verify the actual child result,
   coordinator tests and unchanged source files. A tools-list handshake alone does not
   establish that the parent successfully delegated work.
5. Move routine/policy callers to the shared tool contract after acceptance. Keep any
   still-needed legacy Codex server while its migration is pending. Removing a legacy
   entry and upgrading Codex are separate actions subject to the user's authorization.

## Runtime contract

The implementation uses the MCP [stdio transport](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)
and [tools protocol](https://modelcontextprotocol.io/specification/2025-11-25/server/tools).
It is a legacy (initialize-based) server, supporting protocol revisions 2024-11-05 through
2025-11-25. It answers a requested supported version verbatim. For any other version it answers
2025-11-25, the latest it supports, as the legacy
[lifecycle](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle) specifies.

It does not implement the stateless 2026-07-28 revision. A `server/discover` probe gets
`-32601 Method not found`, with the supported versions in `data.supported`. That is a
non-modern error, so a dual-era client falls back to `initialize`, as the
[2026-07-28 versioning rules](https://modelcontextprotocol.io/specification/2026-07-28/basic/lifecycle)
describe. A client that speaks only the stateless revision cannot use this server until it
gains dual-era support.
Only JSON-RPC goes to stdout. Requests return quickly with durable job IDs. SQLite
binds a UUID to one origin and input, so identical retries never spawn another worker;
changed requests using the same UUID are rejected. At most two workers run per
connection. Each worker has a 15-second authentication deadline followed by its
requested model deadline (15–600 seconds). No automatic retry or model fallback.

Native commands use argv arrays, sanitized environment allowlists and process groups.
Claude runs with no tools, hooks, MCP servers, skills or session persistence; Codex
ignores user config/rules and disables shell, patch, MCP and other execution features.
Both use native subscription authentication. Provider API keys, provider base URLs and
unrelated environment secrets are not inherited. USER/LOGNAME remain available for
macOS Keychain discovery. This is CLI capability confinement, not an OS security
boundary against a compromised CLI binary; install trusted native clients.

The server validates full structured answers before materializing any task changes.
Nonzero exits, missing completions, unexpected executable events, invalid JSON, model
identity mismatch and out-of-scope edits fail the job. Task tests always belong to the
coordinator. Exact file hashes bind the source state including uncommitted edits.
Review findings and patch contents remain untrusted suggestions.

## Model identity

New completed review/task results (and valid `needs_context` answers) expose these
`job_status` fields. Previously saved jobs retain their original metadata.

| Field | Meaning |
| --- | --- |
| `requested_model` | The explicit native CLI model argument. |
| `observed_model` | The model attested by native output, or null when unavailable. Never copied from the argument or assistant prose. |
| `model_identity_source` | `native_model_usage` for validated Claude usage; `unavailable` for Codex. |
| `model_identity_status` | `attested` for validated Claude identity; `unattested` for Codex. |
| `model_identity_reason` | Null for attested identity; otherwise explains that `codex exec --json` exposes no authoritative served model field. |
| `usage` | Native token/model usage when reported, independently of model attestation. |

Codex identity remains unattested even when the requested model appears in assistant
text or an unverified event field. A requested/served mismatch cannot be established
without authoritative evidence. Claude retains its existing failure on missing or
mismatched native model usage, including canonical-model matching; auxiliary usage
entries are not selected as the serving model. Failure/cancellation results may lack
identity metadata when parsing never completed. Completion and identity are separate.

On 2026-10-25, the installed CLI reported version 0.163.0. Its first-party tagged
[exec event schema](https://github.com/openai/codex/blob/rust-v0.163.0/codex-rs/exec/src/exec_events.rs)
defines `thread.started` with only a thread ID, `turn.started` with no fields and
`turn.completed` with only usage. The corresponding
[JSONL processor](https://github.com/openai/codex/blob/rust-v0.163.0/codex-rs/exec/src/event_processor_with_jsonl_output.rs)
discards `ModelVerification` notifications. It renders reroutes as error items,
which the bridge's existing unexpected-item guard rejects; these are not completion
attestations. The [official JSONL example](https://learn.chatgpt.com/docs/non-interactive-mode#make-output-machine-readable)
also reports completion usage without a served model. `--ephemeral` suppresses
session rollout persistence; configured/session model names alone do not prove service.

The single authorized live probe used the bridge's exact `worker_command`, requested
`gpt-6.1-sol` at low effort and asked only for an OK summary. It exited 1 before a
turn because in-process app-server initialization was denied by the host sandbox
(`Operation not permitted`). No JSON events were emitted, and no probe was retried.
[`codex-exec-0.163.0-probe.json`](../../tests/rhize-ops/fixtures/codex-exec-0.163.0-probe.json)
preserves the raw empty stdout, stderr and exit code without sensitive data. This is
a failed-probe fixture, not a live completed-event capture. Completion regressions
use synthetic events matching the first-party schema. Positive Codex attestation and
an attested Codex mismatch remain unverified/unsupported until an authoritative
same-run source is exposed; no hypothetical event parser is added.

## Failures and private data

State is local under `~/.rhize/agent-bridge` (override `--state-dir`). Directories must
be canonical, owned by the user and mode 700; files are mode 600. Job folders contain
frozen input, native output/stderr, validated answers and task artifacts. SQLite holds
status, hashes and native usage. These can contain source code and prompts: keep them
out of shared logs, vault exports and version control. There is no network telemetry,
automatic retention pruning or benchmark claim. Delete selected terminal job artifacts
when no longer needed; preserve the database if UUID retry protection must remain.

`subscription_auth_unavailable` requires repairing the native login; never add an API
key as fallback. Model or native-format changes require a fresh fixture check. A job
cancel or timeout kills the worker process group; normal server EOF/SIGTERM cancels and
joins its workers. A hard SIGKILL or machine crash cannot execute cleanup. On reconnect,
owner locks identify orphaned jobs as `interrupted`, without replay. Inspect any surviving
process before submitting fresh work. Cancellation of another connection's live job must
be requested through that connection.

## Rollback

1. Let jobs finish or cancel them through their original connections and confirm terminal
   states. Save required results privately.
2. Run `python3 rhize-ops/scripts/install_bridge.py --rollback` to re-point both hosts at
   the `previous_release` recorded by the active version (or name an installed version to
   re-activate it). Alternatively, remove only the `rhize-bridge` MCP registration from each host.
   Preserve unrelated configuration edits; whole-file backup restoration is appropriate
   only when the rest of the file is unchanged.
3. Restart hosts and verify discovery matches the intended prior state. The existing
   Codex CLI and any retained legacy MCP entry continue at their prior version.
4. Retain job evidence until reviewed. Remove the unused versioned script afterward.
   No database rollback is necessary: release 1 uses a stable additive job table.

## Verified baseline and review (2026-09-15)

The release was exercised with Codex 0.153.4 and Claude Code 2.1.270, using explicit
`gpt-5.6-terra` and `claude-sonnet-5` worker arguments. Native worker checks and fresh
parent MCP sessions each completed review/task cases in both directions. The seeded
subtraction bug was detected, isolated addition fixes passed coordinator assertions,
and the source fixture remained unchanged. These are synthetic compatibility checks,
not daily-task reliability or cost-savings measurements. Codex 0.154.0 was not installed
or tested; rerun compatibility checks before any separately authorized upgrade.

The scoped `rhize-devflow:simplify` review covered the bridge, tests, skill and catalog
follow-through using reuse, quality and efficiency passes. It produced a verified no-op:
provider-specific output parsing remains separate; process/deadline handling is shared;
SQLite deduplication and the explicit inventory check were retained. Collapsing these
boundaries would weaken evidence or remove missing-component detection. Cold self-review
was used; this statement is not an independent human or agent code-review claim.
