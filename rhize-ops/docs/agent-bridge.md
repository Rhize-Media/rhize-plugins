# Shared Claude/Codex bridge

`cross-model-handoff` wraps a small, standard-library Python 3.11+ MCP stdio server.
Each host starts its own connection to the same private job directory. The Claude
connection can request Codex work; the Codex connection can request Claude work; an optional
Muse Code connection can request either.
Reviews return findings. File tasks return validated edits in an isolated copy for
the coordinator to test and integrate. Workers have no tools in either direction.

## Install and verify

Once `rhize-bridge` is registered in both hosts, install each new release with one command
from an up-to-date rhize-plugins checkout (`git fetch` first; the script does not fetch):

```bash
python3 rhize-ops/scripts/install_bridge.py 0.34.0 --dry-run
python3 rhize-ops/scripts/install_bridge.py 0.34.0 --codex-model gpt-6-astra --claude-model claude-fable-5-2
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

### Deployment model pins

The server accepts `--claude-model <native-id>` and `--codex-model <native-id>`.
A configured pin is enforced for every new job to that provider. Its tool schema
advertises the allowed model and default. Callers may omit `model` to use the pin;
an explicit different model is rejected before authentication or inference, with no
silent substitution. Without a pin, the existing explicit-model contract is unchanged.
The four MCP tools, subscription login, no-tools confinement and approval settings are
unchanged. Running connections retain their startup policy until restarted.

On 2026-11-09, the verified desired pins are `claude-fable-5-2` and `gpt-6-astra`,
per the [Claude Fable 5.2 model page](https://platform.claude.com/docs/en/models/fable-5-2/overview)
and [Codex model documentation](https://learn.chatgpt.com/docs/models).
These are exact, dated pins, not promises to auto-upgrade to future releases. Verify
official model availability and run a fresh synthetic review before changing them.
CLI model lists may lag a new release; a successful native result provides stronger
evidence than a cached list. Never use assistant prose as model identity proof.

For a pinned installation, append both flags to the existing server's arguments in
both hosts, preserving all other settings. The installer carries arguments forward
on upgrades. When rolling back to a script that predates pin support, remove these
two options as part of the scoped rollback; old scripts cannot parse them. Keep the
prior bridge entries in the private installation record. A stale caller must update
its explicit model or omit it, not retry another model.

New pending jobs and failures before successful output validation also retain
`requested_model` and explicitly unattested identity. Authentication or transport
failures never become model-verification claims. A later artifact-writing failure may
retain valid model attestation from the already completed native inference.

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
entries are not selected as the serving model. Historical failure/cancellation results
may lack identity metadata when parsing never completed. Completion and identity are separate.

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

### Muse Code as a request origin (2026-11-10)

Muse Code can *send* review and task requests; it is never a worker. Start the server with
`--origin muse`. A Muse connection may target `claude` or `codex` (both appear in the
tool schema's `target` enum); `target: "muse"` is rejected. With pins configured for both
workers, `model` is optional and resolves to the chosen target's pin; an explicit
different model is still rejected. Jobs stay scoped to the Muse origin.

Muse Code 1.4.x loads MCP servers from `${XDG_CONFIG_HOME:-$HOME/.config}/muse/settings.json`,
key `mcpServers` (camelCase). Never leave a legacy `mcp_servers` key beside it: the loader
then drops the whole MCP member. A new file is `{"schema_version": 1, "mcpServers": {...}}`:

```json
{"schema_version": 1, "mcpServers": {"rhize-bridge": {
  "command": "/opt/homebrew/bin/python3",
  "args": ["<release>/agent_bridge.py", "--origin", "muse",
           "--claude-bin", "<claude>", "--codex-bin", "<codex>",
           "--claude-model", "claude-fable-5-2", "--codex-model", "gpt-6-astra"]}}}
```

`install_bridge.py` manages only the Claude and Codex entries; re-point the Muse entry's
`args[0]` by hand after an upgrade. Muse Code must itself be logged in (`muse login`, a
device-code sign-in the user runs) before it can start sessions. Muse Code starts MCP servers only in a
trusted workspace: in an untrusted one the bridge tools are silently absent. Trust the
project when Muse Code prompts, or pass `--trust-workspace` for a single run; `muse mcp list`
shows whether the entry is loaded. Verified 2026-11-10 with Muse Code 1.4.15: a trusted
`muse exec` called `job_status` and read back a Muse-origin Codex job. The Muse desktop app
has no local stdio MCP loader (its connectors call Meta-hosted services), so it cannot
host this bridge; hand its prompts to Muse Code, Claude or Codex instead.

### Muse integration readiness (2026-11-09)

Muse is not an enabled Bridge target (worker). The personal Muse desktop app has no verified
headless request/response interface. Its connector platform lets Muse call external
services, which is the opposite direction from a Bridge worker.

The official [Muse Code CLI](https://dev.meta.ai/docs/muse-code) is the candidate
transport. Version 1.4.14 supports headless `exec`, JSONL output and a final-answer
JSON schema. It accepts `run.toolset=[]` in configuration, and exposes `--preset empty`,
`--contributor-mode off`, tool-disabling flags and `--no-session-log`. These controls
alone do not establish this Bridge's stronger no-tools/no-hooks/no-MCP/no-ambient-context
contract. The inspected interface has no authoritative effective lead-tool catalog;
untrusted mode still permits project memory, while foreign-context exclusion does not
exclude all native rules and memory. Do not enable a provider merely because a prompt
asks it not to use tools, or because a single smoke test did not use them.

Before adding the provider, verify a supported clean configuration that excludes all
tool registration, hooks, plugins, MCP, subagents, memory and ambient instruction sources.
Pin the tested binary rather than an auto-updating launcher. Then use official onboarding
with the authorized account and verify [Muse Code subscription access](https://dev.meta.ai/docs/muse-code/subscriptions).
Desktop access does not establish CLI subscription eligibility. Never copy desktop
credentials or silently fall back to a separately billed API key.

Only after those gates pass, capture and validate a synthetic structured-answer run,
its exact exec event schema, cancellation/timeout behavior and model provenance.
Keep requested and observed model identities separate. Configuration acceptance is not
runtime confinement, and installation is not authentication or successful integration.

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
2. If the target predates model-pin support, restore only each host's saved
   `registrations-before.json` Bridge entry, including its original argument list,
   while preserving all unrelated current settings. Do not use the generic installer
   rollback for this case: it carries pin flags into the older script, which rejects
   them during its pre-activation probe. Verify both origins afterward.
   Otherwise run `python3 rhize-ops/scripts/install_bridge.py --rollback` to re-point both hosts at
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
