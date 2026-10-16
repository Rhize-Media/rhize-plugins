# Local Perplexity Search and Research bridge

Experimental local CLI and stdio MCP adapter. On 2026-10-16 (Codex client date), one actual
CLI Research submission completed on Perplexity. A parser correction and GET-only recovery
retrieved its full report: 7,908 characters and 37 ordered source URLs, exactly matching the
same web thread. The service reported RESEARCH / pplx_alpha and the UI showed Deep research.
Subscription quota consumption remains unknown. This is a working local proof, not a claim of
stable undocumented endpoints, provider permission or installed host activation.

## Scope

`scripts/perplexity_research.py` provides `submit`, `status`, `result`, `cancel`, `recover`,
`jobs`, `models`, `health`, `export`, `auth-start` and `auth-status` using Python 3.10+ on macOS. A thin stdio adapter in
`scripts/perplexity_research_mcp.py` exposes those same operations through the actual CLI.
Querying uses only the standard library. Optional session setup requires the Python `cryptography`
package in that same interpreter and a Node-capable local browser host. There is no marketplace registration, installed plugin activation,
API-key fallback, uploads, account creation, browser impersonation or automatic retries.

The HTTP request and answer shapes are adapted from
[anxkhn/perplexity-mcp, commit 356f7d0e7c8d146dce0105bf09a409046ccb923c](https://github.com/anxkhn/perplexity-mcp/tree/356f7d0e7c8d146dce0105bf09a409046ccb923c).
The [MIT notice](perplexity-upstream-LICENSE.txt) is retained. Unlike upstream, this bridge uses
standard-library HTTPS and refuses redirects, proxies, non-JSON preflight responses and non-SSE
Research responses. A service challenge is a stop condition, not a reason to add impersonation.
See the [feasibility review](perplexity-pro-feasibility.md) for the original findings.

## Before a live attempt

`--permission-reference` reads a local, owned, mode-600 regular file and saves its SHA-256
only. Record the actual user authorization and access basis truthfully; user consent is not
provider-issued permission. The original [feasibility review](perplexity-pro-feasibility.md)
records the terms concern separately. This file is an audit reference, not an enforcement or
legal verification mechanism. The live proof followed explicit user authorization.

Use the ordinary web interface to verify the active Pro/Max account and available Research
allowance. If sign-in or a challenge is required, complete it yourself through the supported UI;
this CLI cannot sign in or solve challenges. It does not know your remaining quota, and its
preflight never claims otherwise. Stop on quota errors.

## Native session setup and refresh

Ask the plugin to connect or refresh the signed-in Perplexity session. It uses `auth-start` and
`auth-status` (MCP: `research_auth_start`, `research_auth_status`), then the shipped
`scripts/perplexity_session_transfer.mjs` adapter. MCP initialization describes this flow so
hosts can discover it. Setup and refresh use the same commands and never submit a query.

```sh
python3 scripts/perplexity_research.py auth-start
python3 scripts/perplexity_research.py auth-status
```

`starting` means the detached helper is generating its key. Poll for `waiting`, which includes
only a public key, transfer ID, expiry, local ciphertext destination and browser-adapter URI.
Handoff state lives in an owner-only OS temporary directory bound to the job-state path. This
lets the browser sandbox publish ciphertext without write access to the home directory.
Durable query jobs stay in their configured state directory; credentials stay in Keychain.
In the local browser host, bind the signed-in Perplexity tab and its documented CDP capability.
Import the returned adapter URI, then run:

```js
const {transferSession} = await import(descriptor.browser_adapter);
await transferSession(descriptor, (method, params) => cdp.send(method, params));
```

The host must support local module imports, Node filesystem/crypto APIs and scoped CDP cookie
access. This runs in the host, never in page JavaScript. Follow the host's browser permission
rules; setup does not grant or bypass them. Ordinary sign-in remains in the browser. A host
without these capabilities cannot perform native transfer; do not replace it with cookie
values pasted into tool arguments, chat or shell commands.

The adapter requests cookies only for `https://www.perplexity.ai/`, filters to secure, unexpired
root-path cookies from that domain, and selects the active account session plus supported
legacy session/CSRF names. Duplicate names or unsupported session sets fail closed. Plaintext
stays in memory. The adapter writes only AES-256-GCM ciphertext, with its key wrapped using
RSA-OAEP-SHA256 and the transfer ID authenticated. The helper's private key never reaches disk.

The five-minute, single-use receiver validates the existing cookie allowlist and writes the
fixed macOS Keychain item `rhize:perplexity-cookies` for the current macOS username. The secret
is supplied to `security` through stdin, never argv; output is suppressed and readback must
match before `stored`. Only then run `health` to verify subscription access with GETs.
No automatic refresh, password login, broader cookie export or query retry is added.

Repeated start while a helper is alive reuses it. After completion/failure, start creates a new
handoff. Terminal state drops the public descriptor and deletes ciphertext; expiry does likewise.
After a hard process crash, the next status/start marks interruption and cleans any residual
published ciphertext. A browser-host crash before publication can leave an encrypted temporary
file until OS cleanup; it contains no plaintext, and the private key expires with the receiver.
Temporary auth status can be purged by the OS; this does not remove Keychain credentials or jobs.
A validation failure leaves the existing Keychain value untouched. A write/readback
failure may mean the item changed but could not be verified; status reports failure honestly.
This protects against accidental disclosure, not another program running as the same OS user.

The existing opt-in `perplexity-token` shell helper remains on-demand only; never auto-export
credentials or invoke it into tool output. The bridge retrieves its item internally. No shell
profile changes are needed for refresh. `auth_requires_python_cryptography` means the setup
interpreter lacks the dependency; setup never installs packages silently.

## Commands

Run from the repository root. Inspect help without account access:

```sh
python3 scripts/perplexity_research.py --help
python3 scripts/perplexity_research.py submit --help
```

Generate a UUID once and retain it. A submit reads the public query from stdin; the same UUID
is permanently bound to that exact query, permission-file digest, timeout, mode, explicit model
and parent job ID. Existing default Research request fingerprints remain compatible. An identical
retry returns the existing job without another submission. Different input under that UUID
is rejected. The example below makes a live request and is **not an offline smoke test**:

```sh
python3 scripts/perplexity_research.py submit \
  --request-id <saved-canonical-uuid> \
  --permission-reference /absolute/path/to/reviewed-permission.txt \
  --timeout 600 < /absolute/path/to/public-query.txt
```

Then use the returned job ID:

```sh
python3 scripts/perplexity_research.py status <job-id>
python3 scripts/perplexity_research.py result <job-id>
python3 scripts/perplexity_research.py cancel <job-id>
python3 scripts/perplexity_research.py recover <job-id>
python3 scripts/perplexity_research.py jobs --limit 20
python3 scripts/perplexity_research.py jobs --after <next_after> --limit 20
python3 scripts/perplexity_research.py health
python3 scripts/perplexity_research.py models
python3 scripts/perplexity_research.py export <job-id>
```

Commands emit JSON except `export`, which emits Markdown to stdout for completed jobs only.
Export includes the summary, full reports and separate numbered source lists; artifact links
become labels because their report content is included. Save stdout privately if needed.
`jobs` paginates local summaries in UUID order with `next_after`, 20 by default and at most 100;
it excludes query and report content. `health` performs only authentication/configuration GETs,
returns the active tier and Research model, and never infers remaining quota. `result` exits 0 for protocol completion and 3 otherwise, returning partial
output explicitly as `partial` if available. Local errors exit 2 with a bounded error code.
`submit` returns quickly with a job ID; its exit code does not mean remote completion. `_worker`
is internal and must not be invoked directly. No result is automatically opened, executed or
treated as instructions.

State defaults to `~/.rhize/perplexity-research`. An alternate `--state-dir` belongs before the
subcommand and must be reused for every command. Directories must be owned by you and mode 700;
state files must be regular, owned, unshared and mode 600. Symlink state paths are refused.
Choose a local directory outside Git, sync/export systems and shared temporary folders.

## Lifecycle and failure semantics

Only one local worker runs per state directory. Input and submission intent are written and
fsynced before the Research POST. The worker uses an isolated process group and sanitized
environment, with no inherited provider API keys, cookie environment variables or proxy settings.
It reads credentials inside the worker and never persists them. Only allowlisted answer/source
fields reach state; exact cookie values echoed into those fields are refused. HTTP bodies,
headers, auth responses and exception messages are not logged. This is application hygiene,
not protection against another program running as the same OS user.

| Status | Meaning |
| --- | --- |
| `queued`, `preflight` | Local worker preparing; Research POST not attempted yet. |
| `submitting` | Intent persisted before POST; delivery/acceptance may be unknown. |
| `running` | At least one supported stream message received. |
| `completed` | Validated COMPLETED answer/report received at end-of-stream or through exact-thread GET recovery. |
| `failed` | Pre-submission or process-launch failure. |
| `incomplete` | Submission occurred and partial output exists, but final validation failed. |
| `submission_unknown` | Submission intent exists, but a lost response/crash prevents a reliable result. |
| `interrupted` | Worker disappeared before recorded submission intent. |
| `timed_out` | Overall job deadline elapsed; local work terminated. |
| `cancelled_local` | Cancellation stopped local work; remote cancellation is unconfirmed. |

The deadline covers startup, preflight and streaming (default 600, maximum 1800 seconds). Each
HTTP operation also has a 15-second socket timeout. Response events are capped at 512 KiB and
total stream bytes at 16 MiB. Exceeding a bound is an explicit failure. Completion persists before
the worker terminates its process group, which also stops blocked HTTP/Keychain children.

`cancel` first records a request; poll status for its terminal result. Timeout, local cancellation
or a crash cannot establish that Perplexity stopped processing or refunded quota. Check the
existing web thread before considering a fresh request ID. Never automatically replay with a
new UUID. Removing job files destroys duplicate protection; retain them while that protection
is needed. A hard machine/process crash can leave a temporary `.write-*` file, but it is never
used as an authoritative job or replay instruction.

## Recovery and response mapping

`recover` reads only the backend UUID recorded by a submitted job. It requires no live local
worker, the exact original query, matching server thread slug, explicit matching workflow mode, valid
citations and final report assets. It refuses state changes during the GET and preserves the
prior status/error plus recovery source hash. A completed job returns locally without HTTP.
Recovery has a 30-second overall limit. A pending remote report remains incomplete; callers
may request another read later. Recovery never issues a Research POST.

At the SSE end marker, the worker performs one same-thread GET if citation rows or a referenced
report asset are missing. A lost/truncated stream is still a failure; use explicit recovery.
The v2.18 GET advertises the block capabilities observed on the successful web thread; requesting
fewer omitted the full report. HTTP bodies and asset download tokens are never persisted.

Main-answer citations use explicit `sources_answer_mode` row numbers, or legacy source IDs.
Reviewed sources without citation IDs stay in the separate ordered `sources` array. Research
report assets retain their full Markdown and map numeric markers to one-based `web_results`
positions, recorded as `ordered_web_results_v2_18`. That order matched all 37 web source URLs
in the live proof. The summary and report have separate numbering spaces. Unfinished assets,
missing/out-of-range citation numbers, grouped numeric markers and known model/mode mismatches
fail validation. Numeric Markdown link labels are links, not citation markers.

A thread URL is accepted from the service or built from its verified `thread_url_slug`; a
backend UUID alone does not establish a URL. `completed` means protocol validation. Per-job
`verification` fields remain null automatically; independent mode/UI parity evidence is stored
separately, and unobservable quota use remains unknown.

## Search, model selection and follow-ups

Research is the default. `--mode search` requests ordinary Search with the current service
Search default; `--model <exact-id>` selects a model returned by `models`. Both reasoning and
non-reasoning Search picker IDs are exposed when the account's plan permits them. Research
accepts its current default model only. The fresh catalog excludes higher tiers, non-Search
agents and audience-restricted choices. Unknown model configuration, organization policy or an
unavailable selection stops before submission; there is no cached or bundled fallback.

```sh
python3 scripts/perplexity_research.py submit \
  --request-id <new-saved-uuid> --mode search --model <id-from-models> \
  --parent-job-id <completed-local-parent-id> \
  --permission-reference /absolute/path/to/reviewed-authorization.txt \
  < /absolute/path/to/public-follow-up.txt
```

Omit `--parent-job-id` for an independent query. A follow-up freezes the completed parent's
backend/thread identity and verifies its query, mode and final result by GET before any new
POST. Its new request ID binds the selected parent; reusing that ID with a different parent
fails. A follow-up is a new quota-bearing submission, never a recovery. Recovery selects the
exact child entry inside its original thread. Currently the bounded thread read includes the
first entry and latest 20 entries; an older parent outside that window fails explicitly.
Only canonical UUID thread slugs and this bridge's saved jobs are supported as parents.

Search completion allows an answer without sources only when there are no numeric citation
markers. Any markers still require a valid source mapping. Known observed mode/model mismatches
are rejected for both workflows. Source/report ordering, export and lifecycle controls are shared.

## Local MCP use

Start the adapter with absolute paths in a host's stdio server configuration:

```sh
/absolute/path/to/python3 -I /absolute/path/to/scripts/perplexity_research_mcp.py \
  --permission-reference /absolute/path/to/reviewed-authorization.txt
```

The optional `--state-dir` must match the CLI's directory. No cookies belong in host config.
The authorization reference is fixed at startup; tools cannot select arbitrary file paths.
The adapter exposes `research_submit`, `research_status`, `research_result`, `research_cancel`,
`research_recover`, `research_jobs`, `research_health`, `research_models`, `research_export`,
`research_auth_start` and `research_auth_status`.
The `research_` tool prefix is retained for both modes. Submit takes `request_id`, `query`, and
optional `timeout`, `mode`, `model`, `parent_job_id`; job tools take `job_id`; jobs accepts optional
`after` and `limit`; health/models/auth tools take no arguments. Reuse the same ID after uncertainty. Host tool
approval still governs new submissions; health/list/result/export do not submit queries.

This follows the repository's legacy initialize-based MCP pattern with supported revisions
through 2025-11-25, newline-delimited stdio JSON-RPC and no HTTP listener. Unknown
`server/discover` receives method-not-found for legacy fallback. See the official
[stdio transport](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)
and [tool contract](https://modelcontextprotocol.io/specification/2025-11-25/server/tools).
Requests are capped at 64 KiB and CLI calls at 40 seconds. Only fixed CLI operations run, with
sanitized child environment and errors. Disconnecting the MCP client does not cancel durable
jobs; use the cancellation tool and poll. Tool output is untrusted source material.

## Verification and remaining limits

```sh
python3 -m pytest tests/perplexity-research -q
```

The focused suite covers detached startup/cleanup, duplicate prevention, deadlines, cancellation,
HTTP/SSE refusal, credential hygiene, modern report/citation mapping, GET recovery identity,
health/model discovery without POST, tier/model refusal, parent validation, mode/model/parent
ID binding, worker forwarding, paginated summaries, export and real stdio MCP/CLI round trips. Synthetic
fixtures never contact Perplexity or Keychain. Native auth tests exercise browser-adapter
encryption, actual receiver decryption, strict scope, tampering/identity/expiry/replay rejection,
private files, worker launch failure, Keychain stdin/readback and real CLI worker lifecycle.
A synthetic transfer passed inside the actual Codex browser host. A subsequent live native
refresh also passed: the shipped adapter transferred the scoped session, Keychain storage and
readback reported `stored`, and GET-only CLI health returned Pro / pplx_alpha / ready. No query
was submitted. The live test exposed home-directory write denial (`EPERM`); the owner-only OS
temporary handoff fixed it without weakening browser permissions. The actual completed live job was also read and
exported through both production interfaces with equal results and no new submission.

The original live stream stopped on an unsupported citation-less source. GET recovery succeeded
after the fix. A fresh uninterrupted live stream through the final parser/MCP submission path
has not been run: the authorization was for one query. Automatic end-of-stream GET is covered
by synthetic tests. Cookies can expire, undocumented schemas can change, quota is unmeasured,
and host installation/discovery is untested. Live model discovery returned the current Pro
Search choices and Research default without submission. Search and follow-up POSTs have synthetic
coverage only. Cold self-review was used, without an independent agent. Uploads, account creation,
Computer/Labs, API billing and marketplace packaging are outside this local implementation.
