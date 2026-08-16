# Dev Flow Control-Plane Evals

Deterministic, offline evals for the `rhize-devflow` plugin's control plane (Task 9 of
[`.claude/plans/rhize-devflow-v3-engineering-control-plane.md`](../../.claude/plans/rhize-devflow-v3-engineering-control-plane.md)).
Two things are measured:

1. **Trigger precision** — does a prompt's phrasing match the skill/command that *should*
   handle it, and stay quiet on near-miss prompts that shouldn't route to Dev Flow?
2. **Output quality** — do the `/check` and `/review` command contracts declare the exact
   verdict vocabulary, evidence tables, safety rules, and scope-preservation language the
   plan requires?

## Why this directory looks different from `evals/seo-aeo-geo/` and `evals/obsidian/`

The house harness (`evals/run_evals.py`, `evals/assertions.py`) drives its trigger and
quality evals by invoking `claude -p` — a real, paid model call per case, scored by whether
the `Skill` tool actually fired and whether the live output satisfies assertions. That's the
right tool for evaluating an LLM's actual routing/generation behavior, but the
control-plane plan (see "Compatibility and Release Strategy") is explicit that **automated
tests must not make live paid-service calls**. This directory is fully offline instead:

- **Trigger evals** are scored against a **fixed keyword-substring heuristic**
  (`keywords.json`), not a live Claude session. This is *not* the real Skill-invocation
  decision — see "Method and limits" below.
- **Quality evals** re-run the same assertion engine the house harness uses
  (`evals/assertions.py`'s `evaluate_all`), but against the **static contract text** of
  `check.md`/`review.md` instead of live command output.

Consequently the fixture files here are named `trigger_cases.json` / `quality_cases.json`,
**not** `trigger_evals.json` / `quality_evals.json`. That's deliberate: `evals/run_evals.py`
auto-discovers any subdirectory containing files with those exact names and would sweep this
directory into its live `claude -p` run — crashing immediately on the schema difference
(`target` vs. `target_skill`, `target_file` vs. `skill`) even before it got to the live-call
problem. Renaming the fixtures is what keeps `python evals/run_evals.py --plugin all` safe
for `seo-aeo-geo` and `obsidian` while this directory runs entirely through its own
`run_evals.py`.

## Running

```bash
python3 evals/rhize-devflow/run_evals.py            # human-readable report, exit 0/1
python3 evals/rhize-devflow/run_evals.py --json      # machine-readable report
```

Also wired into the normal test suite as `tests/rhize-devflow/test_control_plane_evals.py`,
so `python3 -m pytest tests/ -q` fails the same way any other regression would.

A per-run JSON snapshot is written to `evals/results/` (gitignored, matching the house
harness's convention).

## Method and limits — trigger precision

**Method:** `keywords.json` hand-curates a list of trigger phrases per skill/command id,
extracted from that target's own live frontmatter `description:` field (SKILL.md for
`skill:*`, the command `.md` file for `command:*`) — mostly the quoted example phrases the
skill/command authors already wrote for AI routing. A case in `trigger_cases.json` is scored
`predicted = true` iff any of its target's keyword phrases appears as a case-insensitive
substring of the prompt. Precision/recall are computed per target and overall, exactly the
way `evals/skill-map/eval_routing.py` scores its router (see that file for the house
precision-over-recall framing this mirrors).

**Keyword-drift self-check:** every run first asserts each curated keyword phrase still
appears verbatim in its target's live source file. If a SKILL.md/command `.md` description
is edited and a keyword no longer appears, the run fails loudly with a `DRIFT:` line naming
the stale keyword — `keywords.json` cannot silently go stale.

**What this measures:** whether the skill/command authors' own declared trigger phrases are
lexically distinctive enough to discriminate real requests from near-misses. That is a real,
useful signal for catching an over-broad or ambiguous `description:` field.

**What this does NOT measure:** the actual Claude Skill-invocation decision. Real routing is
an LLM judgment call over the full conversation context, not a substring match — it can (and
should) infer relevance without an exact keyword hit, and it can also fire on phrasing this
heuristic doesn't anticipate. Concretely:

- **False negatives are likely undercount** here: Claude may correctly route a prompt this
  heuristic scores as a non-match (e.g. a paraphrase that never uses the exact quoted
  phrase). `trigger-check-neg-testing-theory` is a fixture that exists specifically to
  demonstrate this brittleness (`"a focused test"` singular vs. the keyword `"focused
  tests"` plural).
- **False positives are possible on generic single words** if a keyword phrase is short and
  common (e.g. `"cache"`, `"mutation"`, `"crash"`, `"exception"`) — a real prompt using that
  word in an unrelated sense would fire the heuristic even though a careful human reviewer
  (or Claude) would not route it to Dev Flow. The curated keyword lists deliberately favor
  multi-word phrases over bare generic words for this reason (see `error-lifecycle-management`
  and `mutation-check`'s lists, which specifically exclude the bare words `"error"`, `"bug"`,
  `"timeout"`, `"slow"`, `"broken"`, and standalone `"mutation"` for exactly this reason), but
  the risk isn't eliminated for words like `"cache"` that remain in the list.
- **Negated example phrases are excluded by hand.** `chrome-devtools-mcp`'s own description
  gives `"test in the browser"` as an explicit **non**-trigger contrast (routes to
  `browser-qa` instead) — the extraction is not fully automatic, so a negated example like
  this has to be recognized and left out by whoever curates `keywords.json`, not caught by a
  generic parser.

Given these limits, the ≥90% precision target from the plan's Task 9 "Target measures after
the observation window" is treated here as a **heuristic floor for this fixture set**, not a
claim about real-world routing precision. The 3.0 cleanup's actual go/no-go decision (Task 11)
must additionally draw on the skill-monitor usage data this task also adds (see below) — real
session transcripts, not this synthetic heuristic.

## Method and limits — quality assertions

`quality_cases.json` runs `evals/assertions.py`'s `contains`/`regex` assertion types against
the raw text of `rhize-devflow/commands/check.md` and `review.md`, covering the four buckets
the plan names: exact-verdict vocabulary, evidence-table presence, safety rules (no external
mutation), and scope preservation. This deliberately overlaps with (and is a lighter-weight
mirror of) the much more exhaustive pytest coverage in
`tests/rhize-devflow/test_command_contracts.py` — that file is the actual enforcement
mechanism (e.g. it also asserts there is no *rogue* verdict token outside the stable
vocabulary, which these lighter fixtures don't check). This eval's job is to make the "100%
exact-verdict compliance" target measure directly reportable through the same eval-runner
interface as trigger precision, not to duplicate every edge case pytest already covers.

## Target measures — observation window checklist (Task 11)

From the plan's Task 9 "Target measures after the observation window" — carried here so
Task 11 (3.0 cleanup) has a single checklist to work from:

- [ ] **≥90% precision on should-trigger/near-miss fixtures.** This eval's `run_evals.py`
      reports it every run (heuristic method above); Task 11 should also sanity-check against
      real routing behavior via the skill-monitor usage data, not this heuristic alone.
- [ ] **100% exact-verdict compliance for check/review fixtures.** Enforced here
      (`quality_cases.json`) and by `tests/rhize-devflow/test_command_contracts.py`.
- [ ] **Zero missing-asset or duplicate-canonical-command findings.** Enforced by
      `tests/rhize-devflow/test_plugin_integrity.py` and the canonical-marker tests in
      `test_command_contracts.py`.
- [ ] **Zero deprecated-command invocations before removal, or explicit acceptance of
      remaining users.** Measured by `rhize-ops/skill-monitor/monitor.py`'s
      "Dev Flow Control-Plane Usage" report section (deprecated → canonical mapping table;
      absent telemetry reports as `no data`, never as zero usage — see that script's
      `DEVFLOW_DEPRECATED_TO_CANONICAL` and `build_devflow_control_plane_section`).
- [ ] **No client incident caused by a missed required gate or review-side external write.**
      Not mechanically measurable by an eval; a human judgment call for Task 11 informed by
      the `/check`/`/review` safety-rule tests above and any incident record.

## Files

| File | Role |
|---|---|
| `run_evals.py` | Standalone runner. `python3 run_evals.py` exits 0/1. |
| `keywords.json` | Curated trigger-phrase keyword sets, one list per `skill:<name>`/`command:<name>` id. |
| `trigger_cases.json` | Should-trigger / should-not-trigger prompt fixtures (33 cases: 3 per target × 11 targets — 6 skills, 5 canonical commands). |
| `quality_cases.json` | Assertion fixtures against `check.md`/`review.md` (8 cases covering verdict vocabulary, evidence tables, safety, scope preservation). |

`evals/results/rhize-devflow-*.json` (gitignored) holds one timestamped snapshot per run.
