# Perplexity Pro Research bridge: feasibility review

Reviewed 2026-10-16, using the Codex client date (America/New_York).

Follow-up: the [local CLI and MCP adapter](perplexity-local-bridge.md) now have one successful
CLI Research submission with GET recovery, full-report parity and all 37 ordered source URLs
matching the same web thread. Quota consumption remains unverified. The user explicitly
authorized the live attempt and scoped Keychain transfer. The review below is the historical
pre-implementation assessment; its statements about no account access and held validation
apply to that earlier phase, not the subsequent live proof.

## Original decision

**Do not install the upstream MCP unchanged. A subscription Research bridge is technically
plausible but unproven; live validation is held pending an established permission basis for
automated subscription access.** No working integration is claimed. No Perplexity account was
accessed, no cookies were collected, and no research query or API call was submitted.

The smallest conditional implementation is an adaptation of the existing client's Research
transport/parser with a local job interface. A new general bridge framework, REA installation,
browser bundle analysis and HAR capture would not resolve the current blockers.

## Sources and maintenance

- Reviewed [anxkhn/perplexity-mcp at commit
  356f7d0e7c8d146dce0105bf09a409046ccb923c](https://github.com/anxkhn/perplexity-mcp/tree/356f7d0e7c8d146dce0105bf09a409046ccb923c),
  obtained as a read-only inspection checkout. Package version: 0.3.1; MIT license,
  copyright helallao 2023–2026. Retain the license if adapting source.
- Git history's latest commit is dated October 2, 2026. Recent changes include July 31's
  block-only answer parsing fix and October 2's account-aware model discovery. This is evidence
  of maintenance, not evidence of successful live Research. The checkout has no tags, dependency
  lockfile or tracked GitHub workflows. The public issues view showed zero open issues; the
  releases page could not be fetched, so no claim is made about hosted release availability.
- [pyproject.toml](https://github.com/anxkhn/perplexity-mcp/blob/356f7d0e7c8d146dce0105bf09a409046ccb923c/pyproject.toml):
  Python >=3.10, curl_cffi >=0.5.7, mcp >=2.0.0, websocket-client >=1.9.0. Optional driver extras
  add Patchright and Playwright. Dependencies have lower bounds without upper pins. No package
  installation, dependency vulnerability audit or SDK interoperability test was performed.

## What the code actually does

All line references below are to the pinned commit above.

| Area | Observed behavior | Implication |
| --- | --- | --- |
| Authentication | `client.py:81–111` takes cookie JSON, impersonates Chrome via curl_cffi, adds `x-pplx-account`, and requests `/api/auth/session`. `own` is simply `bool(cookies)`; failed session reads become `{}`. | Cookie presence is not valid authentication. A failed login must stop Research explicitly. |
| Credentials | `mcp.py:144–165` reads cookie JSON or legacy next-auth tokens from environment. README examples put values inline in host configs. | Do not copy those credential examples into Rhize configs. Use local Keychain and the existing secret launcher; never print or return cookie values. |
| Plan/model | `models.py:31–38,120–146,173–236` detects subscription tier, refreshes config, and filters search choices. Research mapping is populated regardless of tier; refresh failure retains old/bundled mappings. | Search tier filtering does not prove Research entitlement, current authentication or quota. |
| Research request | `mcp.py:50–65,104–108` calls deep research. `client.py:253–274` POSTs `/rest/sse/perplexity_ask`, mode `copilot`, model preference from `default_models.research`; bundled default is `pplx_alpha`. | Requested workflow is identifiable. Actual server execution, current web-mode equivalence and billing are not established by this request field. |
| Completion | `client.py:299–317` returns the last chunk containing an answer, even after EOF without `end_of_stream`, and does not require `status=COMPLETED`. | Interrupted partial reports can appear successful. An end marker alone also does not establish final status. |
| Citations | `client.py:31–73` retains the surrounding payload while extracting answer/chunks. `mcp.py:104–108` returns only `.get("answer", "")`. | Source metadata, backend identifiers and status are discarded. Inline markers or links may survive in text, but citation-list parity cannot be guaranteed. |
| Deadlines/errors | Auth/model fetches specify 10 seconds. The Research POST has no explicit timeout or HTTP status check; its stream ignores non-message events. | Library defaults are not a job deadline. HTML/error responses can become empty results; auth, challenge and quota failures need explicit handling. |
| Quota | `client.py:93–96,201–205` sets enhanced queries to infinity when cookies exist and decrements that value. | This is not a real usage meter. It cannot demonstrate subscription quota consumption or available Research allowance. |
| Lifecycle | Five synchronous MCP tools; no durable submit/status/result/cancel operations. UUIDs are generated anew per search. | Retrying after a lost response can submit a second paid/quota-bearing job. Closing a client does not prove remote cancellation. |

The normal MCP Research path does not invoke account creation or Labs. Those utilities are
nevertheless included/imported by the package; do not expose or execute them in an adaptation.
The async client uses the same parser and similar streaming/completion logic, so switching to
it alone does not solve the lifecycle problem. The existing Rhize Claude/Codex bridge already
illustrates local job IDs, duplicate protection and cancellation, but it is tied to native CLI
workers; changing it for an unverified web transport would unnecessarily expand scope.

Logging defaults to stderr and file logging is opt-in. Model-refresh failures log exception
types, and the model cache stores configuration/timestamps under a cookie-derived hash rather
than raw cookies. Those are useful properties, not a complete credential-leak audit: HTTP/SDK
exceptions and dependencies still need review before exposing account credentials.

## Offline evidence

Executed the pinned `Client.search`, parser, `search_answer` and `perplexity_research` function
bodies through Python AST extraction, with an in-memory fake transport. No upstream package
imports, account initialization, external requests or dependencies were needed. These are
synthetic behavioral checks, not live Perplexity fixtures or a working bridge.

Five checks reproduced:

1. A stream ending after a `PENDING` answer returns that partial answer as an ordinary result.
2. The Research POST specifies no timeout, and the synthetic infinity quota remains infinity.
3. Adding `end_of_stream` still returns the `PENDING` answer without requiring completion.
4. A non-SSE login/challenge-shaped HTML body returns `{}` rather than an explicit failure.
5. The MCP Research function returns the partial text alone, discarding status and citation URLs.

Reproduction recipe: parse `perplexity/client.py` with `ast.parse`, compile only the `Client`
class and `parse_sse_message` function, construct `Client.__new__(Client)` to bypass network
initialization, and supply a fake session whose `post().iter_lines()` yields this sole event:

```text
event: message\r\ndata: {"status":"PENDING","blocks":[{"intended_usage":"ask_text","markdown_block":{"answer":"Incomplete report [1]"}}],"citations":["https://example.org/source"]}
```

The actual fixture encodes the displayed `\r\n` as CRLF characters.
Set `own=True`, `copilot=file_upload=float("inf")`, and
`model_mappings={"deep research": {None: "pplx_alpha"}}`; call `search` with a public fixture
query and `mode="deep research"`. Repeat with an end marker, then an HTML body. Extract the
two MCP functions and pass the partial result through a fake client to reproduce metadata loss.
Upstream tests cover FINAL/block parsing and mock tool forwarding; the reviewed client/MCP tests
do not prove truncated-stream rejection, durable jobs, cancellation or web citation parity.

## Access boundary

The [consumer terms](https://www.perplexity.ai/en-GB/hub/legal/terms-of-service), displayed as
last updated January 23, 2026, restrict reverse engineering and automated access/extraction in
section 5.2, subject to applicable-law exceptions or written permission. A Pro subscription and
acceptance of account risk do not themselves establish that permission. Browser automation does
not remove the restriction. This review does not determine whether a legal exception applies.

The missing live prerequisite is a documented basis permitting this subscription automation
(for example, Perplexity's written permission). After that, verify the actual signed-in account,
Research entitlement and available quota; request user sign-in only if needed. Do not collect
cookies in chat, bypass challenges, create replacement accounts or retry around quota limits.

The [official MCP](https://github.com/perplexityai/modelcontextprotocol) targets Perplexity's API
Platform. Its [plan documentation](https://www.perplexity.ai/help-center/en/articles/11187416-which-perplexity-subscription-plan-is-right-for-you)
describes API pay-as-you-go billing separately and no complimentary API credits. It is not proof
of subscription-backed Research and was not installed or used as a fallback.

## Smallest implementation after the prerequisite is resolved

Start with one local CLI, one active job, the pinned upstream transport/parser and the existing
Rhize Keychain launcher. Pin resolved dependency versions before execution. Do not register a
plugin or add MCP until the CLI proof passes. Retain the MIT notice for copied code.

- `submit(request_id, query)` persists the input hash and submission intent before network I/O;
  the same ID never automatically resubmits. Reject ID reuse with different input. Return a local
  job ID and persist any observed remote thread identifier. No private-file upload feature.
- `status(job_id)` reports submitted/running/completed/incomplete/failed/timed_out/cancelled_local/
  submission_unknown. A crash or lost acknowledgement after submission is unknown, not safe to
  retry. Reconcile the same thread in the web interface before any new submission.
- `result(job_id)` returns answer Markdown, ordered source IDs/URLs/titles and thread URL only
  for verified completion. Preserve partial output as explicitly incomplete. Require a verified
  terminal signal and nonempty answer; validate citation markers against source metadata.
- `cancel(job_id)` stops the local worker. Report remote cancellation as unconfirmed unless the
  server acknowledges it. Timeout likewise does not imply no quota consumption. Never relaunch
  automatically after cancellation, timeout, authentication failure, challenge or rate limit.

Use a bounded overall deadline and bounded stream size, sanitize errors rather than dumping
HTTP bodies/headers, and keep job state private (directories 700, files 600). Stream parsing must
handle actual SSE framing and error events. A live fixture must establish final-state and
citation schemas before treating any assumed fields as authoritative.

## One-job acceptance proof

Use only this public query: “Find official public ECI LotVue documentation describing its
relationship with MarkSystems. Distinguish product pages from technical/API documentation.
List source URLs and state explicitly when public integration details are unavailable.”

Before submission, record the actual account plan and Research allowance shown by the service;
do not persist account identifiers or cookies. Select Research explicitly and submit once. Capture
the returned thread identity, observed workflow evidence, terminal completion, full answer and
ordered citations. Compare the **same thread** in the web UI against the local result; a second
independent query can legitimately produce a different answer and is not a parity test. Check
usage afterward while no other account activity occurs. If allowance/delta is not observable,
report quota consumption as unverified. Success requires evidence of Research rather than search
or Computer, citation parity, completion and subscription quota use; a successful HTTP response
or configured model ID alone fails this acceptance gate.

## Verification limits and handoff

Cold self-review checked the findings against pinned source and the requested boundaries; no
independent agent was used. This is a documentation-only decision record: no runtime, manifest,
host configuration, credential, protected file, version or installed capability changed. No live
proof, full upstream test suite, dependency installation, anti-bot encounter, browser observation,
REA evaluation, API billing, quota measurement or citation parity test occurred. REA was not
needed because ordinary source inspection answered the bounded feasibility questions; it cannot
establish permission or replace account-level acceptance evidence.
