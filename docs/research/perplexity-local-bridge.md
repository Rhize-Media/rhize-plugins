# Local Perplexity Search and Research bridge

## Large Research response recovered — 2026-10-17

Verified through the installed plugin in this chat (client date). Job
`4f40bde9-478e-40cd-9377-96df324d6d87` failed with `stream_too_large`, then the old MCP
recovery refused its 1,892,470-byte thread JSON as `response_too_large`. Most of that JSON
was workflow/source metadata; the normalized result was 104,306 bytes. The fix separates
[response and state budgets](#lifecycle-and-failure-semantics) instead of removing size limits.

After local plugin `0.1.0` was rebuilt and installed, `research_recover` completed **the same
job through GET only**, preserving its original request identity, source hash and prior error.
No `research_submit` call was made and the local job-ID set did not change. The unchanged MCP
adapter launched the updated sibling CLI in this chat without a reload.

- Server result: `COMPLETED / RESEARCH / pplx_alpha` on the
  [original thread](https://www.perplexity.ai/search/16578489-cb52-4973-9fdf-60586b5807e0).
- Full report: **24,834 characters and 243 citations**; summary: 3,274 characters and 21
  explicitly numbered citations. MCP result and Markdown export passed, with CLI export parity.
- Recovery CLI SHA-256:
  `8e28ac6797f8d5c68df82173b06c009c4214683180bda674fdd909dda4cba125`.
  Original submission SHA and `stream_too_large` remain in durable metadata.
- All **121 focused tests passed**. New tests reproduced failures before the fix and cover
  >512 KiB thread recovery, repeated 2 MiB snapshots exceeding the old 16 MiB stream cap,
  byte boundaries, multiline events/heartbeats, metadata-response refusal, invalid citations,
  no recovery POST and preservation of saved state on oversized writes.

Rollback snapshots are retained. The final installed documentation and runtime are hash-checked
against the source snapshot. The larger SSE budgets are tested synthetically; no fresh live
query was submitted to exercise them. This verifies retrieval and structural validation, not
factual accuracy, browser parity or quota accounting. Responses above the finite caps still
fail explicitly. The historical stream error cannot identify which old cap fired.

## Search citation fix verified — 2026-10-17

Verified through this chat's installed MCP tools, using the client date. Search now requests
`answer_modes` and `unified_assets` on thread GETs. The broad Research capability list returned
explicit citation rows but omitted the Search answer; the minimal Search list returns both.
Research requests and strict citation validation are unchanged. Reviewed-source order is
never substituted for main-answer citation IDs.

- Original failed job `6e386acb-8386-45dc-a470-e67dd1c494ae` recovered by GET only, with two
  explicit numbered citations. Its original error and source hash remain in recovery metadata.
- One fresh Search, job `2eb52984-0655-481d-a484-b7b1ed39a9e7`, completed as
  `COMPLETED / SEARCH / pplx_pro`: 572 answer characters, two explicit citations and 24 reviewed
  sources. [Live thread](https://www.perplexity.ai/search/0eaf7185-23bd-4a0b-8363-251726e72541).
  Result, Markdown export and identical-ID replay passed without manual recovery. The first
  submission was refused before job creation while another worker was busy; the same ID was
  reused after that worker released its lock. Only one new query was submitted for this test.
- Local plugin `0.1.0` was rebuilt and reinstalled with rollback snapshots retained. All ten
  installed file hashes match the snapshot. CLI SHA-256
  `99fe7213570f93708cc024f65d4620f463cff6e4724ad7422e823fe2b5e25800`
  matches both the recovery metadata and fresh job. The unchanged MCP adapter used the updated
  CLI in this chat without a reload; health remained ready.
- The regression failed before the fix. All 109 focused tests then passed, including rejection
  of unmatched numeric markers and preservation of Research capabilities. Required repository
  checks passed: 534 Dev Flow tests, seven impact-map contracts and static/config/setup checks.
  Cold self-review covered the diff, saved MCP results and installed hashes.

This proves transport/completion and explicit citation mapping, not factual accuracy or browser
parity. One returned official Python citation uses the rolling `/3/` URL rather than a pinned
`/3.14/` URL. Quota use remains unknown. Follow-ups and cancellation were not resubmitted for
this fix; their earlier direct-chat results and remote-cancellation limit are recorded below.

## Direct-chat live acceptance — 2026-10-17

After restarting Codex, all eleven plugin tools were present in this chat. Direct MCP health
and model discovery passed with Pro access; no browser query, app-server test harness, new
credential transfer or API billing was used. Three new request IDs were retained throughout.

| Test | Result | Evidence and limit |
| --- | --- | --- |
| Standalone Search, explicit pplx_pro | **Initially failed; recovered after fix above** | Job 6e386acb-8386-45dc-a470-e67dd1c494ae reached server COMPLETED / SEARCH / pplx_pro, but its stream had numeric [1]/[2] markers without explicit citation rows. Ten reviewed sources had null IDs. The broad-capability GET returned citation rows but omitted the answer, causing incomplete_answer_or_sources. Corrected GET-only recovery later completed with two explicit citations. |
| Search follow-up to completed Research | **Passed** | Job d1a0ee01-0ebd-4c6b-b558-bfde92f11a92 continued parent 7290aedb-2445-482f-8565-0476cdfc7341. The 637-character answer completed as SEARCH / pplx_pro, retained the parent's thread URL and had a distinct backend UUID. Result, Markdown export and same-ID replay passed. |
| Cancel a running Research job | **Passed locally** | Job 7810234b-582e-4fb8-a94c-3cbca6af0ce5 was submitted and running before cancellation. It became cancelled_local with remote_cancellation_unconfirmed; export was refused and same-ID replay remained cancelled without resubmission. |

The follow-up contains an inline official-documentation link and no numeric citation markers;
its citations and reviewed-source arrays are empty. That is accepted by the existing Search
contract and does not prove numeric-citation mapping works. The original standalone failure is
preserved in its recovery metadata; no citation order was guessed and no new-ID retry was issued
for that job. The completed Research parent was reused while the Search remained incomplete.
The follow-up used the same [Perplexity thread](https://www.perplexity.ai/search/7e3ba507-3b82-405b-b5d2-96219ef2e0ff).

Cancellation terminates local work only. Perplexity may continue remotely and quota may still
be consumed; neither remote cancellation nor a refund was established. No browser parity check
was performed. The source runtime remains unchanged from b2adf73 during these tests.

## Earlier Research proof — 2026-10-16

Experimental local CLI and installed Codex MCP plugin. On 2026-10-16 (environment date),
native Codex MCP discovery, encrypted session refresh, health/models, one new Research
submission, polling, result, export and same-ID replay passed. The new report contains 8,410
Markdown characters and 16 sources; Perplexity reported RESEARCH / pplx_alpha. CLI and MCP
results and exports match exactly. Subscription quota consumption remains unknown. This is
a verified local workflow, not a claim of stable undocumented endpoints or provider permission.

## Scope

`scripts/perplexity_research.py` provides `submit`, `status`, `result`, `cancel`, `recover`,
`jobs`, `models`, `health`, `export`, `auth-start` and `auth-status` using Python 3.10+ on macOS. A thin stdio adapter in
`scripts/perplexity_research_mcp.py` exposes those same operations through the actual CLI.
Querying uses only the standard library. Optional session setup requires the Python `cryptography`
package in that same interpreter and a Node-capable local browser host. A separate local Codex
marketplace packages this bridge; the eleven-plugin public marketplace remains unchanged.
There is no API-key fallback, uploads, account creation, browser impersonation or automatic retries.

## Install and activate in Codex

Run these commands from a reviewed source checkout, using the Python interpreter that has
`cryptography` installed. First create an owned, mode-600 authorization-reference file outside
the checkout, as described below. It records the user's actual authorization, never cookies.
The destination's parent must already exist and be private; the destination itself must be new.

```sh
python3 scripts/build_perplexity_plugin.py "$HOME/.rhize/perplexity-local" \
  --permission-reference "$HOME/.rhize/perplexity-research/mcp-authorization.txt"
codex plugin marketplace add "$HOME/.rhize/perplexity-local" --json
codex plugin add perplexity-research@perplexity-local --json
codex plugin list --marketplace perplexity-local --json
```

The builder copies only the three runtime files, documentation, MIT notice and manifests;
`snapshot.json` records their SHA-256 hashes. It never installs, reads credential values or
submits queries. It refuses an existing destination and removes an incomplete new snapshot
on failure. The package pins the selected Python executable and authorization-file path;
moving either requires a new snapshot. Core querying remains stdlib; the builder checks
`cryptography` so installed native session setup is available too.

The marketplace uses `.agents/plugins/marketplace.json`, with inline `mcpServers` in the
plugin's `.codex-plugin/plugin.json`. `cwd: "."` resolves the installed package, so the MCP
adapter finds its sibling CLI and browser adapter. This uses the native
[Codex local marketplace format](https://developers.openai.com/plugins/build/plugins#marketplace-metadata).
Codex 0.162.1 installed this version at
`~/.codex/plugins/cache/perplexity-local/perplexity-research/0.1.0` and reported it enabled.

Restart the desktop app or open a fresh host session to load the plugin into an already-running
tool catalog. Do not add a separate `mcp_servers.perplexity_research` config entry: it would
shadow the plugin. Native discovery should attribute all eleven tools to
`perplexity-research@perplexity-local`, with no `toolsError`. Then call `research_health`;
use the session setup flow below when credentials need refreshing. Installation itself does
not run a query or refresh credentials.

For a local update, stop active jobs first, retain the old snapshot as a rollback, rebuild at
the registered marketplace path, and repeat `codex plugin add`. The builder deliberately
does not overwrite snapshots. Verify installed hashes and check health. Reload the host when
the MCP adapter or manifest changes. For a CLI/docs-only update at the same installed path,
the unchanged adapter launches its sibling CLI on each call; verify the new job or recovery
source hash against the installed CLI to establish that the current chat used the update.
Never delete durable jobs to update a plugin. To uninstall only the plugin:

```sh
codex plugin remove perplexity-research@perplexity-local --json
```

Uninstall removes the plugin cache, not the Keychain item, local jobs, authorization reference
or source snapshot. Removing those separately discards credentials or duplicate protection.

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
HTTP operation also has a 15-second socket timeout. Size budgets are separate:

| Payload | Maximum | Overflow error |
| --- | --- | --- |
| Session/model JSON | 512 KiB | `response_too_large` |
| Thread GET JSON | 4 MiB | `response_too_large` |
| Individual SSE event, including framing/comments | 4 MiB | `sse_event_too_large` |
| Cumulative SSE bytes, including repeated snapshots/heartbeats | 64 MiB | `stream_too_large` |
| Encoded local job state | 16 MiB | `state_too_large` |

Thread metadata can be much larger than the normalized answer. JSON reads request at most
their budget plus one byte to detect overflow; SSE counters include UTF-8 bytes and multiline
events. State writes are size-checked before creating/replacing the saved file, preserving the
prior readable job on refusal. These are finite caps, not unlimited-response support. An overflow
never triggers an automatic query retry or marks a partial result completed. Use explicit
same-job recovery when the remote report is available. Completion persists before
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
The v2.18 Research GET retains the full block capability list needed for report assets.
Search requests only `answer_modes` and `unified_assets`: the broad Research list omitted
`ask_text` on the failed Search thread even though explicit citation rows were returned.
The minimal Search list returns the answer and numbered rows together. This shared read path
covers stream completion, explicit recovery and follow-up parent verification; citation
validation is unchanged. HTTP bodies and asset download tokens are never persisted.

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

The original CLI stream stopped on an unsupported citation-less source. After the parser fix,
GET recovery retrieved 7,908 Markdown characters and 37 ordered source URLs, exactly matching
that web thread. The separate installed-MCP acceptance run subsequently completed a fresh
Research job without manual recovery or resubmission. Its request ID was
`7290aedb-2445-482f-8565-0476cdfc7341`; the returned
[Perplexity thread](https://www.perplexity.ai/search/7e3ba507-3b82-405b-b5d2-96219ef2e0ff)
contains the Python 3.14 ProcessPoolExecutor migration report. Native `mcpServer/tool/call`
exercised the installed adapter and actual CLI, not a browser query or source-only test harness.
The host used an ephemeral diagnostic context with no model turn. Ten tools were exercised;
live cancellation was intentionally left to synthetic tests so the report could complete.

Codex 0.162.1 initially failed discovery because its `tools/list` includes
`_meta.progressToken`. The adapter now accepts that standard metadata and still rejects
unknown fields; a regression reproduces the exact handshake. Native discovery returned all
eleven tools attributed to the installed plugin, with no error. The installed browser adapter
also completed a fresh scoped transfer and Keychain readback before submission. The new
report has 8,410 Markdown characters, 16 report sources and six summary citations. Result
and export equal the CLI output; replay returned the same completed job. Calling recovery
on that completed job was a local no-op. Automatic end-of-stream GET remains part of the
normal completion path; this proof does not isolate whether that read was needed.

Cookies can expire, undocumented schemas can change and quota is unmeasured. The new report's
browser UI parity was not rechecked; the original proof established parity for its own thread.
The 2026-10-17 direct-chat tests above supersede the earlier untested Search/follow-up/cancellation
status: follow-up and local cancellation passed, while standalone numeric-citation Search failed.
Cold self-review was used, without an independent agent. Direct-chat activation is now verified.
Uploads, account creation, Computer/Labs, API billing
and public marketplace publication remain outside this local implementation.
