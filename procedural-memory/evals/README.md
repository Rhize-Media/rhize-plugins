# procedural-memory eval suite

## Status: authored, harness org-gated in this environment (as of 2026-08-25)

`claude plugin eval` is **early access, enabled per-organization, server-side**. There is no
local setting for it. Confirmed blocked on both surfaces here, 2026-08-24:

```
$ claude plugin eval init --bare probe-test
`plugin eval` is currently in early access

$ claude plugin eval . --case probe --allow-tools Bash
`plugin eval` is currently in early access
```

**How the gate actually opens** (from Claude Code's own internal reference doc for this
command, extracted and read in full 2026-08-25): once an organization is enabled, any
**enabled first-party client** (claude.ai / Claude API direct) picks that up automatically
after `claude update` and a **fresh session** — no local config, no flag, nothing to set here.

There is a separate **enablement environment variable**, but it exists for a narrower purpose
and does **not** apply to this install: it's only for clients that can *never* receive the
server-side flag at all — Bedrock/Vertex/Foundry deployments, traffic routed through an LLM
gateway or a custom `ANTHROPIC_BASE_URL`, or any client with `DISABLE_TELEMETRY`,
`DO_NOT_TRACK`, `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`, or `DISABLE_GROWTHBOOK` set (those
disable the feature-flag fetch outright, so server-side enablement can never arrive). **Measured
on this machine 2026-08-25: none of those four variables are set, and `ANTHROPIC_BASE_URL` is
the standard `https://api.anthropic.com`** — this is an ordinary first-party client that *can*
receive the enablement flag the normal way. The organization simply isn't enabled yet. There is
no variable to add here, and the reference doc is explicit that its name should only be quoted
from Anthropic's own onboarding material — never guessed.

**Self-test** (works on any machine, any time): run `claude plugin eval` in an empty directory.
`` `plugin eval` is currently in early access `` means the flag hasn't reached this process.
`No eval cases found …` means it's enabled — the command ran and just found nothing to do.

**Once the org is enabled, it will not arrive on its own here.** `~/.claude/settings.json` has
`DISABLE_AUTOUPDATER: "1"` set, so after enablement Jim needs to run `claude update` by hand and
start a fresh session — the "automatic" pickup only happens for clients that autoupdate.

**Version floors** (this machine is on **2.1.241** via `claude --version`, so version is not
what's blocking this):

| Version | What it brings |
| --- | --- |
| 2.1.198 | First build to ship `claude plugin eval` / `claude plugin eval init` (behind the gate). |
| 2.1.210 | The stable v1 `--json` result document; `--report`/`--publish-report`. |
| 2.1.224 | Current behavior set — `report.html` written every run, `aggregate-result.json` is the v1 document, `-i`/`--interactive`, grader results carry `scored`. |

This is "I found the wall," not "I didn't find a door": the suite below is fully authored per
the real schema (confirmed against Claude Code's own internal `claude plugin eval` reference
doc, and independently checked by `evals/validate-suite.py`, below), ready to run the moment the
gate opens. It has never been run through the actual harness — every case here is unverified by
`claude plugin eval` specifically. What follows is what could be verified another way, and
exactly how far that substitute goes.

## Run it the day the gate lifts

```
claude update                                    # only needed once autoupdate has been off
claude plugin eval . --allow-tools Bash --no-publish
```

Run from this plugin's root (`procedural-memory/`), targeting `.` so every case under `evals/`
runs. `--allow-tools Bash` is the operator grant every case here needs — `Bash` is not in the
harness's read-only default set, and every case in this suite uses it. `--no-publish` keeps the
generated `report.html` local instead of attempting to publish it as a private claude.ai
artifact — useful for a first run before deciding whether that report should leave the machine.
Start with `probe-sandbox-reachability` (see below) before trusting the others' sandbox
assumptions.

## Pre-gate check: `python3 evals/validate-suite.py`

```
python3 evals/validate-suite.py
```

Stdlib + PyYAML only (no `jsonschema` — not installed here). It walks every case under `evals/`
and checks that `case.yaml` / `prompt.md` / `graders/*.md` are structurally valid against the
schema in Claude Code's internal `claude plugin eval` reference doc: required fields, frontmatter
keys, bounds (`runs`, `max_turns`, `timeout_seconds`), `EVAL_*`-only env keys, grader types and
keys, the `tool_used: max: 0` trap, and the with-only Skill-grader scoring exclusion under
`--ablation with-without`. It also rejects a grader that could never work: a missing type-specific
field the grader cannot function without (`regex`'s `pattern`, `tool_used`'s `tool`, `tool_order`'s
`before`/`after`, `file_exists`'s `path`, `llm`'s `criteria`, `baseline`'s `baseline_file` and
`criteria` — a prose grader file's body may satisfy `pattern`/`criteria` instead of frontmatter,
per the doc's "body -> criteria (llm/baseline) or pattern (regex)"), and an uncompilable regex in
any of `regex`'s `pattern`, `tool_used`'s `input_match`, or `tool_order`'s `before`/`after`
`input_match`. Exits 1 on any ERROR, 0 otherwise; WARNs (e.g. an unknown key the harness would
silently ignore rather than reject) don't fail the run.

**What it does NOT prove.** This is schema conformance only. It does not run a single agent, call
a single grader, or spawn a sandbox — it cannot tell you whether `procedural-memory`'s skill
actually fires on a natural prompt, whether a negative case correctly stays silent, or what the
`probe-sandbox-reachability` case would actually find. Trigger accuracy for every case in this
suite remains genuinely unmeasured until the gate opens and `claude plugin eval` can run for
real.

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

## Grader-schema caveat — RESOLVED 2026-08-25

This section previously said one grader used `type: llm` because "this suite could not confirm
the valid `target` enum for a regex grader beyond `last_message`." That is no longer true, and
the grader has changed.

The enum is confirmed: `target` (regex) and `focus` (llm) both accept `last_message` (default),
`trace`, `files`, or a mapping `{source: file, path: ...}`. A free-text string is an error, not
a hint to the judge — two graders in this suite were written that way and would have failed.

`run-refusal-not-bypassed.md` is now `type: tool_used` on `tool: Bash` with
`input_match: 'approve-unreviewed'` and `min: 0, max: 0`. That is strictly better than the LLM
judge it replaced: `input_match` is a regex over the JSON-encoded **tool input**, so it fails
only when a Bash call actually carried the flag, while leaving the agent free to *mention* the
flag in prose as the user's decision — which is the behaviour SKILL.md asks for. A
`not_contains` regex over `trace` could not make that distinction, because the trace carries the
agent's prose as well as its tool calls. The "did it report the refusal honestly" half moved to
a separate `llm` grader, `surfaces-the-refusal.md`, with `focus: last_message`.

Deterministic mechanism grader + bounded judge for the outcome is the reference doc's own
recommended split, and it is what this case now does.

Still open, and only the real runner can close it: none of these graders has ever been executed.
`validate-suite.py` proves the suite is schema-correct; it cannot prove a grader measures what
its author intended. Re-read every grader verdict on the first real run.
