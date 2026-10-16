# Local Perplexity Research bridge

Experimental CLI, verified offline only. The user chose to preserve it locally without a live
submission on 2026-10-16. Full-feature implementation remains conditional on a permitted live
Research proof. Nothing here establishes current Perplexity web compatibility or automation rights.

## Scope

`scripts/perplexity_research.py` provides `submit`, `status`, `result` and `cancel` using Python
3.10+ on macOS. It has no third-party dependencies, MCP registration, installed plugin changes,
API-key fallback, uploads, account creation, browser impersonation or automatic retries.

The HTTP request and answer shapes are adapted from
[anxkhn/perplexity-mcp, commit 356f7d0e7c8d146dce0105bf09a409046ccb923c](https://github.com/anxkhn/perplexity-mcp/tree/356f7d0e7c8d146dce0105bf09a409046ccb923c).
The [MIT notice](perplexity-upstream-LICENSE.txt) is retained. Unlike upstream, this bridge uses
standard-library HTTPS and refuses redirects, proxies, non-JSON preflight responses and non-SSE
Research responses. A service challenge is a stop condition, not a reason to add impersonation.
See the [feasibility review](perplexity-pro-feasibility.md) for the original findings.

## Before a live attempt

The [consumer terms, section 5.2](https://www.perplexity.ai/en-GB/hub/legal/terms-of-service) restrict
automated access/extraction, subject to their exceptions or written permission. Establish a
permitted access basis first. `--permission-reference` reads a local, owned, mode-600 regular
file and saves its SHA-256 only. The argument is an audit reference, **not proof of permission**;
do not manufacture one merely to make the command run. No permission reference was created in
the local-only implementation session.

Use the ordinary web interface to verify the active Pro/Max account and available Research
allowance. If sign-in or a challenge is required, complete it yourself through the supported UI;
this CLI cannot sign in or solve challenges. It does not know your remaining quota, and its
preflight never claims otherwise. Stop on quota errors.

Only after establishing the access basis, provision a macOS Keychain generic-password item
with service `rhize:perplexity-cookies` and account equal to your macOS username. Its value is a
JSON object containing only the necessary Perplexity session cookies. Current supported names
are `__Host-pplx-last-active-account` plus `__Secure-pplx.session.<that-account>`; legacy
`next-auth.session-token`, `__Secure-next-auth.session-token`, `next-auth.csrf-token` and
`__Host-next-auth.csrf-token` are also accepted. Unrelated browser cookies are refused.

Use Keychain Access's secure password field or an unrecorded interactive Keychain prompt.
Never paste cookies into chat, a shell command, a config, a query, source control or a report.
Follow the repository's credential convention when provisioning a new item: an opt-in helper
may retrieve it on demand, but never auto-export it into every shell. The CLI retrieves the
item internally; no helper invocation or secret environment variable is needed. This session
did not provision or read an item or edit shell configuration.

## Commands

Run from the repository root. Inspect help without account access:

```sh
python3 scripts/perplexity_research.py --help
python3 scripts/perplexity_research.py submit --help
```

Generate a UUID once and retain it. A submit reads the public query from stdin; the same UUID
is permanently bound to that exact query, permission-file digest and timeout. An identical
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
```

Commands emit JSON. `result` exits 0 for protocol completion and 3 otherwise, returning partial
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
| `completed` | End-of-stream plus a COMPLETED answer and valid supported citation mapping received. |
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

## What completed does and does not verify

The supported response adapter accepts upstream FINAL text-step or `ask_text` block answers.
It preserves source order from `web_results`/`citations` or `web_result_block.web_results`, but
requires each source to have an explicit positive numeric `id` or `citation_id`, HTTP(S) URL and
optional title/name. Numeric `[1]` markers must map to those IDs without duplicates. Grouped
numeric markers, sources without IDs and unsupported event/schema shapes are refused; the
bridge never guesses a missing citation mapping. These shapes are **synthetically tested**.

The CLI records the requested Research model from a fresh authenticated configuration and
refuses known mismatches in an observed `model_preference`. It does not substitute search or
Computer when Research is unavailable. An observed model field alone is not proof of actual
mode execution. A provided Perplexity `/search/` thread URL is preserved; a URL is never invented
from the backend UUID. If the service omits a URL, use the recorded backend identifier and UI
history to establish the same thread manually.

The result always leaves these acceptance fields `null` until independent evidence exists:
`actual_research_mode`, `subscription_quota_used`, `web_answer_and_citations_match`. This CLI
does not fill them based on successful transport, active subscription or a requested model ID.
`completed` therefore means local protocol validation, not completion of the live acceptance
proof. Current web schemas may require a small adapter correction before the first usable result.

## Verification and expansion gate

Run the offline checks without credentials or network:

```sh
python3 -m pytest tests/perplexity-research/test_bridge.py -q
```

The initial 43 checks cover real detached-process startup/cleanup, ID deduplication, one-worker
admission, orphan recovery, deadlines, cancellation, synthetic end-to-end HTTP-to-durable-result
flow, SSE framing/truncation/error bounds, auth/HTTP/quota refusal, credential handling and
citation mapping. They do not use the user's Keychain or Perplexity account. A cold self-review
was used; no independent agent review or live integration test is claimed.

The next gate remains one permitted public LotVue/MarkSystems query from the feasibility
review: verify actual Research execution, compare the complete answer and ordered citations
against the **same** web thread, and observe subscription quota usage without concurrent account
activity. Keep unobservable usage as unknown. Full features, MCP registration and installed
activation follow only after that proof; they are not justified by these offline test results.
