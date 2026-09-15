# procedural-memory eval suite

## Status: harness enabled, suite runs for real (since 2026-09-14)

`claude plugin eval` is **enabled for this organization**: measured 2026-09-14 on Claude Code
2.1.270 (`claude plugin eval` in an empty directory returns the trust-directory error, not
"currently in early access"; `--help` renders the full option set). The org-gated status this
file carried from 2026-08-25 is history; the self-test still works on any machine:
"early access" = gated, "not a trusted plugin directory" / "No eval cases found" = enabled.

**Machine prerequisite for the Bash-granting cases.** The sandbox refuses `--allow-tools Bash`
when `~/.docker` holds a symbolic link outside the directories it skips (`cli-plugins`, `buildx`,
`desktop`, `mutagen`, `run`, `desktop-build`) — on this machine Docker Model Runner's 16 versioned
dylib symlinks in `~/.docker/bin/lib`. `DOCKER_CONFIG` does not bypass the check. They were
replaced with hard links (`sh ~/.docker-eval/fix-docker-eval-symlinks.sh`, backup + rollback
printed); rerun that script if a Model Runner update restores the links and the harness reports
"holds a symbolic link inside it" again. Runs refused this way are recorded as `score: 0` with
`turns: 0` and no graders — an invalid observation, not a plugin failure.

## Run it

```
claude plugin eval . --trust-plugin --no-publish --allow-tools Bash --scaffold \
  --model claude-opus-5 --judge-model haiku --concurrency 4 --max-cost-usd 15 \
  --json evals/results/latest.json
```

From this plugin's root (`procedural-memory/`). `--allow-tools Bash` is the operator grant for
the Bash cases (every case declares `allowed_tools: [Bash, ...]`, but without the grant the
harness silently narrows it and a positive case can pass without the tool it was written to
exercise). `--scaffold` is required for `happy-path-recall-run` (stub CLI) and
`probe-sandbox-reachability` (plugin-root resolver); `--trust-plugin` does not imply it.
`--model`/`--judge-model` are pinned because the result JSON does not record them. `--no-publish`
keeps `report.html` local. Results land in `evals/results/<timestamp>/` (gitignored). Add
`--keep-temp` when you need transcripts beyond what the LLM judge embeds — traces under
`/private/tmp/e-*/out/trace.jsonl` are deleted otherwise. Only one `--case` glob is honored per
invocation (passing it twice keeps the last).

## First real run (2026-09-15) — what the suite measured

8 cases, 46 agent sessions, $7.99, 268 s, run model `claude-opus-5[1m]`, judge haiku. Routing:
both positive cases fired the skill in 3/3 with-plugin runs; all four negative cases stayed silent
in 12/12 runs across both arms. Per-case scores (with / without / Δ): trigger-recall 1.00 / 0.00
/ +1.00; functionize-trigger 1.00 / 0.00 / +1.00; the four negatives 1.00 / 1.00 / 0;
probe-sandbox-reachability 1.00 / 1.00 / 0; happy-path-recall-run 0.83 / 0.67 / +0.17. The
+1.00 deltas are routing evidence by construction (the baseline arm has no skill to fire), not
output uplift. The happy-path miss was a grader false negative (regex window), fixed the same
day — see the case section below. Turn caps were raised where every run hit them.

**Rerun after the fixes (2026-09-15, same day).** `probe-sandbox-reachability`: 1.00 / 1.00
(it grades honesty, so both arms pass; the findings are in "Probe result" below).
`happy-path-recall-run` with the widened regex, the new `uses-launcher` grader, and
`max_turns: 14`: **1.00 / 0.50 / +0.50** over 2 runs per arm, $0.90. Both with-plugin runs
matched the trust-tier regex, refused the bypass, satisfied the judge, and called the launcher
twice. Neither baseline run touched the launcher (it has no plugin commands to reach it
through); one baseline run found the stub CLI on its own and reported correctly (0.75), the
other never located a registry — the plugin source is on the baseline sandbox's read-deny list
— and honestly said so (0.25). That +0.50 is the plugin's procedural contribution, measured.

Under the default `--ablation with-without`, a `tool_used: Skill` grader with no `arm:` is
with-only and excluded from the score unless every grader in the case is with-only (then scored
normally) — which is why the single-grader trigger cases score. Add `arm: both` before mixing
such a grader with regex/LLM graders.

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
`probe-sandbox-reachability` case would actually find. Those are measured by the real runs
recorded above, not by this validator.

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
across runs is what the real suite is *for*). The harness runs of 2026-09-15 (above) superseded
this manual pass with 3 runs per arm per case.

### 3. `evals/probe-sandbox-reachability/` — Probe result (measured 2026-09-15)

Rewritten as a `case.yaml` after the first run showed the original prompt measured nothing:
the tool shell is **zsh** (`$0` = `/bin/zsh`), so bash's `/dev/tcp` pseudo-device opened a
literal path; and **`${CLAUDE_PLUGIN_ROOT}` is unset in the Bash tool's environment** (it is
substituted into plugin config text at load time, not exported), so the launcher probe expanded
to `/scripts/rhize-skill-launcher.sh` and exited 127. The case now uses `nc -z` and a scaffold
(`scripts/resolve-plugin-root.sh`) that records the plugin root, resolved from its own `$0`,
into the sandbox HOME.

Measured answers, both arms, identical unless noted:

| Probe | Result |
| --- | --- |
| Exec an absolute path outside the sandbox HOME (`/usr/bin/true`, `/usr/bin/id -u`) | Works; runs as the real uid (501). No `<sandbox_violations>`. |
| `nc -z -w 3 127.0.0.1 5432` | **exit 1 — unreachable**, while the same command on the host succeeds (Postgres 18 is listening). "Network is not blocked" does not extend to localhost from inside the sandbox. |
| Scaffold-recorded plugin root | Correct (`.../rhize-plugins/procedural-memory`, manifest present) — scaffold scripts run from their real location, `$0` resolves. |
| Real launcher `doctor` | With plugin: launcher runs, finds no CLI, refuses with exit 78 and the full resolution list (sandbox HOME's convenience path checked). Without plugin: `Operation not permitted`, exit 126 — the baseline arm cannot execute files under the plugin it is not loading. |
| `CLAUDE_PLUGIN_ROOT` | unset in both arms. |

Consequences for the rest of the suite: fixture mode is not just prudent, it is the only way —
the real registry's Postgres is unreachable from a case; and any case that needs a plugin
script must reach it through the plugin's own commands (where the root is substituted) or a
scaffold, never through the variable in a shell command.

## Suite layout

```
evals/
├── README.md                        # this file
├── probe-sandbox-reachability/       # measured 2026-09-15; see "Probe result"
│   ├── case.yaml
│   ├── scripts/resolve-plugin-root.sh
│   └── graders/reachability-report.md
├── happy-path-recall-run/            # fixture mode BY DESIGN, not provisional — see below
│   ├── case.yaml
│   ├── scripts/setup-stub-cli.sh
│   └── graders/{recall-reports-provenance,run-refusal-not-bypassed,surfaces-the-refusal,uses-launcher}.md
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

Functionize adds three sibling cases: `functionize-trigger`,
`functionize-negative-one-off`, and `functionize-negative-registry-promotion`. Together they cover
the explicit repeated-CLI trigger, a cheap one-off near miss, and the most important collision:
registry promotion belongs to `procedural-memory`, not Functionize. They are schema-validated
locally with the rest of this suite and ran for real on 2026-09-15 (see "First real run").

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

Closed on the first real run (2026-09-15): every grader executed. It also showed that
`validate-suite.py` proves schema-correctness only — the `recall-reports-provenance` regex was
schema-clean and still graded a correct answer as a miss (window 20 chars, refusal line needs
28; now 60). Re-read grader verdicts after every grader change.
