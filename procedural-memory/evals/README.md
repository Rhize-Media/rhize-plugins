# procedural-memory eval suite

## Status: authored, harness org-gated in this environment (2026-08-24)

`claude plugin eval` is currently in early access, enabled per organization. Confirmed blocked
on **both** surfaces in this environment, not just one:

```
$ claude plugin eval init --bare probe-test
`plugin eval` is currently in early access

$ claude plugin eval . --case probe --allow-tools Bash
`plugin eval` is currently in early access
```

There is a documented enablement path for organizations whose Claude Code client can't reach
Anthropic's server-side feature flags (Bedrock/Vertex/Foundry, or clients with certain telemetry
env vars set) — an environment variable provided during onboarding. This install doesn't match
that profile and the variable wasn't available to this session. **Whether to pursue enablement
is Jim's call, not something resolved here.**

This is "I found the wall," not "I didn't find a door": the suite below is fully authored per
the real schema (confirmed via `claude plugin eval --help` and cross-checked against a
`claude-code-guide` agent's read of the embedded CLI reference), ready to run the moment the
gate opens. It has never been run through the actual harness — every case here is unverified by
`claude plugin eval` specifically. What follows is what could be verified another way, and
exactly how far that substitute goes.

## What actually got verified, and how

### 1. The launcher's own logic — real, automated, repeatable

`../tests/test-launcher.sh` tests `scripts/rhize-skill-launcher.sh`'s resolution order and
version gate directly via Bash — no Claude Code session, no eval harness, nothing gated. It:

- Confirms the "nothing resolvable" refusal (exit 78, names all three checked locations).
- **Is the deliberately-broken-case-that-goes-red**: a stub CLI reporting version `0.0.1` against
  `MIN_VERSION=0.1.0` must be refused (exit 1, names both versions) *and* must never actually be
  executed (the stub logs its own invocations; the log stays empty). Verified by intentionally
  flipping one assertion's expected value, confirming exactly one `FAIL` line and a non-zero
  harness exit, then reverting.
- Confirms the good-version passthrough case (exit 0, real argv reaches the stub, proven via its
  invocation log).
- Confirms `RHIZE_SKILL_BIN` pointed at a non-executable path refuses loudly (exit 78).

Run it: `sh tests/test-launcher.sh`. This is real, running, CI-able coverage of the one piece of
this plugin's own code with actual logic (everything else is thin command wrappers).

### 2. Trigger/negative routing and the real happy path — manually verified against a live session

`claude` ships a `--plugin-dir <path>` flag that loads a plugin directory for a single session
without installing it — exactly what's needed to drive this uncommitted, marketplace-unpublished
plugin through a real Claude Code session. Every prompt below is copied verbatim into each eval
case; this is not a different test, it's the same test run once by hand because the harness that
would normally run it and score it is gated.

```
claude -p "<prompt>" --plugin-dir /path/to/procedural-memory --allowedTools "Bash,Skill" \
  --dangerously-skip-permissions
```

Results, 2026-08-24:

| Case | Prompt | Result |
| --- | --- | --- |
| `trigger-recall` | "Is there already a proven, working tool... for deploying an n8n workflow safely?" | Correctly invoked recall. Found a real hit (`n8n-safe-deploy@1.0.0`, sim=0.740) against **this developer's actual live registry + Postgres** — not a fixture — and correctly reported `trust=unreviewed`, `health=degraded`, `success_rate=0%`, declining to recommend running it. |
| (happy-path continuation) | "Run the n8n-safe-deploy artifact..." | The launcher's real trust/health gate refused it (`REFUSED: health: n8n-safe-deploy@1.0.0 is degraded`), reported verbatim, and the agent explicitly did **not** retry with `--approve-unreviewed`, naming that as the user's call. |
| `negative-memory-search` | "What did we discuss last week... about the skill-forge product?" | Correctly routed to claude-mem ("Searching our memory (claude-mem) for...") and never touched procedural-memory. |
| `negative-generic-task` | "Write a one-line bash command that reverses a string..." | Answered directly with `rev`; never touched procedural-memory. |

The trigger and happy-path-refusal results are a genuine surprise worth being explicit about:
this developer's machine already has a working `rhize-skill` CLI and a live Postgres registry
(the companion repo, `~/dev-local/RHIZE/procedural-memory`, is under active parallel
development), so `--plugin-dir` runs on it exercised the **real end-to-end path**, not fixture
mode — real `recall`, real trust/health signals, a real `run` refusal. That is not something this
suite can rely on in general (a CI runner or a different developer's machine won't have that
registry), which is exactly why `evals/happy-path-recall-run/` is fixture-mode by design (see
below) rather than assuming reachability.

This manual pass is real evidence, not a substitute in the weak sense — but it is one run each,
by hand, not the harness's own multi-run statistical scoring (`runs: 3` per case, with variance
across runs is what the real suite is *for*). Re-run these once the gate opens, using the
authored case files as-is, to get that.

### 3. `evals/probe-sandbox-reachability/` — never run, that's the point

This is the literal probe the original brief asked for: exec an absolute path, attempt a TCP
connect to `127.0.0.1:5432`, run the launcher's `doctor` subcommand. It could not be run here
because the harness itself is gated — so the open question in the main README ("Eval coverage")
is still open. **Run this case first**, the moment `claude plugin eval` is enabled, and update
this section with the actual answer before trusting any assumption about sandbox reachability
baked into the other cases.

## Suite layout

```
evals/
├── README.md                        # this file
├── probe-sandbox-reachability/       # run this first once the gate opens
│   ├── prompt.md
│   └── graders/reachability-report.md
├── happy-path-recall-run/            # fixture mode BY DESIGN, not provisional — see below
│   ├── case.yaml
│   ├── scripts/setup-stub-cli.sh
│   └── graders/{recall-reports-provenance,run-refusal-not-bypassed}.md
├── trigger-recall/
│   ├── prompt.md
│   └── graders/skill-invoked.md
├── negative-memory-search/
│   ├── prompt.md
│   └── graders/skill-not-invoked.md
└── negative-generic-task/
    ├── prompt.md
    └── graders/skill-not-invoked.md
```

## Why `happy-path-recall-run` is fixture-mode permanently, not "until the sandbox proves reachable"

Even a sandbox that turns out to fully reach an absolute path and `localhost:5432` must never run
this suite's happy path against the *real* `rhize-skill` CLI and the *real* registry: `run`
executes registry artifacts, and `promote` commits to the registry and its Postgres index. An
eval suite that occasionally does either of those as a side effect of being scored is not
something to ship, regardless of how permissive the sandbox is. So `happy-path-recall-run`'s
`scripts/setup-stub-cli.sh` scaffold always installs a stub `rhize-skill` (plus a fake `python3`
sibling for the version check) at the launcher's own documented convenience-default path
(`$HOME/dev-local/RHIZE/procedural-memory/.venv/bin/`, inside the eval sandbox's fresh `$HOME` —
never touching the real machine's checkout) before the agent starts. The launcher finds it via
its normal resolution order, no cooperation needed from the agent or the case's `env:` block
(which can only carry `EVAL_`-prefixed variables — `RHIZE_SKILL_BIN` doesn't qualify, which is
also part of why this approach was chosen over asking the agent to `export` it itself: the Bash
tool doesn't persist env vars across separate tool calls anyway).

## Grader-schema caveat

One grader (`happy-path-recall-run/graders/run-refusal-not-bypassed.md`) uses `type: llm`
instead of a `regex` grader against raw tool-call text, because this suite could not confirm the
valid `target` enum for a regex grader beyond `last_message` — the harness itself being gated
means the schema came from `--help` text and a documentation read, not a real run's output.
Re-check that grader once the gate opens; a `regex` grader against actual tool-call text would
be more precise than an LLM judge for a literal-string check like this one.
