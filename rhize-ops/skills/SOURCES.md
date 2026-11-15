# Rhize Skill Forge — Provenance Ledger

One entry per external-skill ingestion decision.

## parallel-agent-optimization — 2026-08-30
- **Source:** https://github.com/affaan-m/ECC/tree/main/skills/parallel-execution-optimizer
- **Additional source:** https://github.com/obra/superpowers/tree/main/skills/dispatching-parallel-agents
- **Upstream ref:** ECC 2.2.0; Superpowers 6.3.0
- **Upstream skill digests:** ECC `b44def0f7c24ab2505bd2eee10ceb777d591724dbe32dfdf5220354385e1e3ab`; Superpowers `1968923066f3b707eb01d1992cdf4c42284c3855f70253b9cd5000ff45fca13c`
- **License:** MIT (both upstream plugins)
- **Verb:** CONSOLIDATE (human-authorized)
- **Graph relation:** provenance-only
- **Target:** rhize-ops:parallel-agent-optimization
- **Took:** high-level dependency/lane planning, deliberate polling, focused self-contained agent briefs, and coordinator integration review; no examples or source bodies vendored
- **Verified:** exact installed source and MIT license inspection; focused lifecycle/privacy/readiness tests; legacy v1 compatibility
- **Drift check:** `use existing ai-stack-version-drift review to compare the recorded installed versions and skill digests; human-review changes without altering runtime automatically`
- **Notes:** Runtime is self-contained. Sources are attribution/update references only. The 2026-08-27 four-arm smoke remains archived non-comparable screening evidence; new comparisons are baseline versus Rhize.
- **Additional source (2026-09-27):** https://github.com/paperclipai/paperclip @ `0f14d26`, MIT (repo-root LICENSE, "Copyright (c) 2025 Paperclip AI"). Pattern taken: goal ancestry → task-graph v2 (required `objective` with `done_signal`, plus per-lane `purpose`). No Paperclip code, prompts or skill bodies vendored.
- **Paperclip decision (2026-09-27, human-authorized):**
  - ABSORB here and into two targets outside this marketplace: claude-routines `scheduled/codex/run_guard.py` (slot-idempotent admission, coalesce-if-active lease, skip-missed, owner record, invocation budget) and the rhize-infra Sentry triage spend breaker.
  - WATCH the platform: CLI adapters bypass permissions and send telemetry by default, and it overlaps claude-routines, Puppetmaster and rhize-bridge.
  - REJECT 31 shippable skills.
  - DEFER `simplified-english` into `~/.agents/skills` (ledger: agents-skills `skills/SOURCES.md`).
  - Gate evidence: skill-forge 0.21.0 scanned all 32 SKILL.md files plus the MCP server; skill-map overlap < 0.2 everywhere (control self-match 0.982); independent Codex reviews on rhize-bridge jobs `6f1c2a8e` and `9a4d7c21`.
  - Revisit the WATCH if permission bypass or telemetry becomes opt-in.
  - Vault: "Forge decision - paperclip (2026-09-27)".
- **Harness-loop prompt decision (2026-11-14, human-authorized):**
  - REJECT as a skill: "Harness Loops + Task Graphs — One Prompt for Claude Code and Codex", a paste-ready prompt that Muse drafted from a public Instagram post by @0xsojalsec (2026-11-08; a one-page framework credited to "rari"). User-supplied file, SHA-256 `d013e4cc02bcf19a6f3f78e7da775f1a2932ae29f8c49118ee799ab032c5d6d8`. No upstream repository and no license stated.
  - Nothing vendored. Three ideas were restated in original Rhize wording as proposals for the agent-coordination plan's `develop` procedure: a build-and-check loop of at most three attempts that stops on the same failure twice; a repository's checks must be seen to fail before they are trusted; a repeated failure files a candidate lesson for human review.
  - Already here: dependency levels, `retry.max_attempts` of 3 at most and one writer per checkout (this skill's task-graph schema); single-node repair (procedural-memory `graph-workflow-builder`); code-only checks (rhize-devflow `check`).
  - Left behind: a Stop hook that blocks stopping while the check fails (it conflicts with the prompt's own attempt limits and does not cover subagents); a generic allow/ask/deny table (it conflicts with the push-class lists); `STATE.md` as a run ledger (the name already means project state); automatic promotion of repeated failures into CLAUDE.md or AGENTS.md.
  - Gate evidence: skill-forge 0.20.1 scanned the file wrapped in a SKILL.md, because the CLI refuses a bare prompt. License `NONE STATED`; safety `BLOCK` (three MP1 MEDIUM findings on the rule-promotion lines; `skillspector-unavailable` HIGH, which is no signal); skill-map top match `graph-workflow-builder` at 0.085 of 70 skills; no control scan was run. Independent Codex review on rhize-bridge job `6a0e20ce` reached the same verdict (served model unattested).
  - Recorded here and not under its own heading: the skill-map build fails on a non-retired heading that has no SKILL.md.
  - Do not re-evaluate unless the author publishes a licensed source. There is no upstream identifier to drift-check.
  - Vault: "Forge decision - harness-task-graph (2026-11-14)".
- **Outside libraries decision (2026-11-15, human-authorized by delegation):**
  - Four public repositories, all Apache-2.0, read at these commits: `google-research/rrsi` `be50316`, `google-research/harness2` `6868817`, `vercel-labs/agent-desktop` `8ffecc1`, `NVIDIA/auto-ontology` `9fba324`.
  - `rrsi`: REJECT as a dependency, ideas only. Its rules were restated in original Rhize wording in the agent-coordination plan (section 3.9): a history of hypotheses, a leakage screen before evaluation, a noise band, a cost rule, held-out tasks, pruning. It needs a scored task suite that does not exist yet, and it bills by API key.
  - `harness2`: REJECT, ideas only. One idea was restated: a stored lesson needs a cue, the lesson and its evidence. It spends four runs and three improver sessions on each task, and its Codex executor starts with the sandbox and hook trust switched off.
  - `agent-desktop`: WATCH. No procedure needs native desktop control today, and accessibility access on the Mac reaches every signed-in app.
  - `auto-ontology`: REJECT for the Obsidian vault. It builds terms from SQL schemas and query history and cannot read notes.
  - Nothing vendored. Three of the four ship their own `SKILL.md` files; none was copied or installed.
  - Gate evidence: no skill-forge scan was run, because the candidates are libraries, not skills. Licenses come from each repository's GitHub metadata and README. Independent Codex review on rhize-bridge job `4627c2a2` reached the same four verdicts (served model unattested).
  - Authorization: on 2026-11-15 Jim delegated the open decisions of the agent-coordination plan to the session's recommendation where the Codex review agrees.
  - Re-evaluate `rrsi` when the golden-task suite exists and proposing is the limit of the improvement loop; `agent-desktop` when a procedure needs native desktop control; `auto-ontology` when a SQL reporting need appears. Drift-check against the commits above.
  - Vault: "Forge decision - rrsi, harness2, agent-desktop, auto-ontology (2026-11-15)".

## decision-premortem — 2026-10-17
- **Source:** Five user-supplied screenshots of a dominatingtech carousel, numbered 1–5: pre-mortem prompt, verdict, rebuild, adversary, tripwire.
- **Verb:** ADAPT concepts; original Rhize wording. No image or source prompt body redistributed.
- **Target:** rhize-ops:decision-premortem
- **Gap:** A reusable decision pre-mortem with evidence separation, causal failures, cost-aware rebuild, adversarial revision and dated owner/action tripwires. Existing project planning and product diagnostics do not supply this complete sequence.
- **Scope:** Renamed from `business-premortem`; extends the same method to concrete nonbusiness decisions, with financial analysis conditional on relevance.
- **Review:** User-requested Fable consultation; proposed rigid counts, a new option flag and unsupported numeric heuristics were not adopted. Hypothetical scenarios and residual risk remain explicit.
- **Graph relation:** provenance-only
