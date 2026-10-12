# Weekly router improvement: proven on traffic it has never seen

Once a week a Codex automation proposes small edits to the skill router's inputs (tags and trigger phrases). Nothing it proposes is merged on faith. Each candidate is **frozen** first, then **confirmed** only on router traffic recorded after the freeze, which neither the proposer nor the candidate has ever seen. The evaluator is a fixed program with a keep/discard ledger, in the style of the autoresearch runner in [`evals/typed-decision/`](../../evals/typed-decision/README.md).

- Design: [the plan](../superpowers/specs/2026-10-11-laya-parity-keepwarm-plan.md), section 7 (rows F7 and F8) and acceptance test A3. Sections 7 and 8 supersede sections 2 to 5.
- Evaluator: [`evals/skill-map-routing/real_traffic.py`](../../evals/skill-map-routing/real_traffic.py).
- Tests: [`tests/skill-map/test_real_traffic.py`](../../tests/skill-map/test_real_traffic.py).
- Routing harness (a different tool, and a hard gate for every candidate): [`evals/skill-map-routing/README.md`](../../evals/skill-map-routing/README.md).
- The records it reads: [skill fit](skill-fit.md).

## The loop

Each Sunday at 18:30 (local) the automation does these seven things, in order:

1. **Confirm** last week's frozen candidates with `real_traffic.py evaluate`. Every verdict goes to the ledger.
2. **Read** the week's `skill-fit-decisions` entries in `~/.claude/context-manager/refinement-queue.jsonl`, and run `real_traffic.py dev-report` for baseline metrics and the top routing misses by skill.
3. **Propose** at most 3 candidate edits, each in its own fresh git worktree on a local branch. An edit may change `catalog/tags.json`, or the tags and trigger phrases in a SKILL.md that this repo owns. Nothing else.
4. **Run the routing harness** on each candidate. A candidate that fails it is dropped before the freeze.
5. **Freeze** each remaining candidate with `real_traffic.py freeze`.
6. **Write** the patch and the reports to a private folder, `~/.local/share/rhize/typed-decisions/skill-fit/improvement/<date>/`.
7. **Notify** Jim with the verdicts.

It never pushes, merges or opens a PR. A `keep` verdict is a recommendation for Jim to review, not an applied change.

## The prospective design

A router edit tuned on last month's traffic will look good on last month's traffic. So the evaluator never judges a candidate on data that existed when the candidate was proposed.

- **Freeze first.** `freeze` records the candidate's identity and the split rule at a moment, `freezeAt`. The proposer's dev data (everything the dev-report saw) is every record with `ts` at or before `freezeAt`.
- **Confirm later.** `evaluate` considers only records whose `ts` is **strictly after** `freezeAt`. The split uses the record's own timestamp, not the time it was written. A record backfilled later from an older session keeps its old `ts`, so it counts as dev data and can never leak into confirmation. `freeze` refuses a `freezeAt` earlier than the newest existing record.
- **Same cases, two arms.** Each confirmatory case is replayed through the baseline arm and the candidate arm using the router's real code. The comparison counts only cases where exactly one arm is right.
- **One decisive look.** The sign test below is valid for a single look at a fixed candidate. The automation therefore treats `keep` and `discard` as final for that manifest and never evaluates it again. A candidate that is still `insufficient` is looked at again on later Sundays, up to 4 weeks after its freeze, and is then retired. A look with fewer than 10 discordant cases cannot produce `keep`, so waiting does not buy extra chances.

## Case types

A record becomes at most one case. The first matching type wins, in this order.

| Type | Which records | Correct means |
|---|---|---|
| labeled | A record with a non-ambiguous skill-fit label. The latest label wins, and `human_adjudicated` is preferred. | The route is in the label's acceptable set (`hit`), or there is no route and the acceptable set is empty (`silentCorrect`). Otherwise: no route with a non-empty set is a `miss`, a route inside the shortlist but outside the set is `wrong`, or a `falseFire` when the set is empty. |
| weak positive | Outcome `invoked_emitted`, `invoked_unlisted` or `invoked_other_shortlisted`, with `latencyTurns == 0`, via `skill_tool` or `slash_command` (never `skill_file_read`), on the nearest record of that turn. The invoked skill must not be in the mandated list (default `rhize-ops:parallel-agent-optimization`). | The arm routes to exactly the skill the user invoked. |
| silence negative | `sourceStratum` is `silent_sample`: the router stayed silent in production and was sampled anyway. | The arm stays silent. Any fire is bad. |

**Unscorable.** A labeled case whose route falls outside the record's original shortlist cannot be judged from the label. It is counted and reported separately and is never discordant. It still counts toward the unscorable share.

**Codex.** A Codex record is used only when its rollout's first line (read bounded, at most 512 KiB) is a `session_meta` with `thread_source` equal to `user`. Guardian reviews, subagents and automations (including this one) are excluded.

## The keep rule

**Discordant** means exactly one arm is correct. `wins` are cases only the candidate gets right, `losses` only the baseline. The verdict is `keep` only if **all five** hold:

| Condition | Blocker name |
|---|---|
| The routing harness passes on the candidate (`run.py --checkout C --check baseline.json`). | `harness` |
| At least 10 discordant cases. | `minDiscordant` |
| A one-sided exact sign test favors the candidate with p <= 0.05, and wins > losses. | `signTest` |
| The candidate's silence-negative fire count is no higher than the baseline's. | `silenceFireCount` |
| The candidate's unscorable share of its labeled cases is at most 0.20. | `unscorableShare` |

Otherwise the verdict is `blocked` when the harness gave no pass/fail answer (`not_run`, `unavailable`, `invalid_result` or `candidate_mismatch`). It is `insufficient` when fewer than 10 cases are discordant, and `discard` in every other case. The report lists every unmet condition in `blockers`. A real harness failure with fewer than 10 discordant cases is reported as `insufficient` with `harness` in `blockers`. `blocked` is never final: an infrastructure gap must not discard a candidate for good. The candidate is looked at again on a later Sunday, inside the same 4-week window.

The p-value is exact: P(X >= wins) for X distributed Binomial(n, 1/2), with n = wins + losses, computed with `math.comb` and rational arithmetic (the comparison with alpha is exact, with no floating-point rounding). The smallest passing result for a few sizes:

| Discordant n | Candidate wins needed | p |
|---|---|---|
| 10 | 9 | 0.0107 |
| 12 | 10 | 0.0193 |
| 15 | 12 | 0.0176 |
| 20 | 15 | 0.0207 |
| 30 | 20 | 0.0494 |

## Commands

All three are subcommands of `evals/skill-map-routing/real_traffic.py`. Each prints one JSON line (`status` plus counts and hashes, or a bounded `reason`). Exit codes: 0 done, 1 failed, 2 bad inputs, 3 refused.

```bash
# Record the candidate's identity and the rules. Never overwrites a manifest.
real_traffic.py freeze --baseline-checkout B --candidate-checkout C --out MANIFEST \
    [--root R] [--now T] [--mandated-skill REF ...] [--allow-dirty] \
    [--baseline-index P --baseline-map P --candidate-index P --candidate-map P]

# Confirm a frozen candidate on traffic recorded after the freeze; appends one ledger line.
real_traffic.py evaluate --manifest MANIFEST --root R --out REPORT \
    [--transcripts DIR ...] [--harness-result RESULT_JSON | --run-harness] [--candidate-checkout C]

# Baseline metrics on the data available now. No keep decision.
real_traffic.py dev-report --root R --baseline-checkout B --out REPORT [--transcripts DIR ...] [--top N]
```

`--root` is the typed-decisions root (`~/.local/share/rhize/typed-decisions`). `--transcripts` defaults to the same Claude and Codex session roots the backfill uses.

**What `freeze` records.** The git HEAD of both checkouts, the sha256 of the candidate's diff against the baseline, the sha256 of each arm's resolved router index and skill map, `freezeAt`, and the split and keep rules. Each arm's index and map are built by running that checkout's own `rhize-context-manager/scripts/build_local_skill_map.py --out-dir <tmp>` (so the candidate's catalog and phrases are in its arm), unless explicit paths are given. Private copies of both arms (repository data, not traffic) are kept next to the manifest in `<MANIFEST>.arms/`, so `evaluate` replays exactly what was frozen. `evaluate` refuses a manifest or arm file whose hash no longer matches. The manifest holds no prompt text.

**Harness status.** `evaluate` needs the harness result, from one of two sources:

- `--run-harness` runs `python3 evals/skill-map-routing/run.py --checkout C --check evals/skill-map-routing/baseline.json --out <tmp>` on the candidate checkout (the manifest's own, or `--candidate-checkout`). It first checks that the checkout is still at the frozen HEAD and diff, and reports `candidate_mismatch` if not.
- `--harness-result FILE` reads a small JSON file with `exitCode` (0 means pass), or `passed` (boolean), or `status` (`pass` or `fail`). An optional `candidateDiffSha256` binds it to the manifest's `diffSha256`; a mismatch counts as `candidate_mismatch`. The two options are mutually exclusive.

Anything other than `pass` (`fail`, `candidate_mismatch`, `invalid_result`, `unavailable`, `not_run`) blocks `keep`.

**What `dev-report` shows.** Baseline counts and metrics per case type, plus the top routing misses by skill (silent or misrouted, counts only) and the top false fires by skill. It uses all data available now, so it is the proposer's input and never a confirmation.

## What is recorded

**Ledger.** `<root>/skill-fit/improvement/ledger.jsonl` is append-only. One line is added per `evaluate`, holding hashes and counts only:

| Field | Meaning |
|---|---|
| `schema`, `manifestSha256`, `freezeAt`, `evaluatedAt` | Which frozen candidate, and when it was frozen and evaluated. |
| `cases` | `recordsAfterFreeze`, `scored`, `byType`, `notComparable` (the unscorable cases), and `excluded` (counts by exclusion reason, such as a non-user Codex session or a prompt that could not be recovered). |
| `counts` | Per arm and per case type, the number of cases in each status: `hit`, `silentCorrect`, `falseFire`, `wrong`, `miss`, `unscorable` (labeled); `recalled`, `wrong`, `silent` (weak); `fire`, `quiet` (silence). |
| `discordant` | `total`, `candidateWins`, `baselineWins`, and the same split `byType`. |
| `signTest` | `n`, `wins`, `pValue`, `alpha`. |
| `harness` | `{status}`. |
| `blockers`, `verdict` | The unmet conditions and `keep`, `discard`, `insufficient` or `blocked`. |

The file is created 0600 in a 0700 directory. Symlinks are refused (`O_NOFOLLOW` and a private-directory check), the append runs under a lock, and a torn final line from an earlier crash is terminated before the next line is written.

**Report.** The `--out` report is the ledger line plus per-type metrics per arm, the opaque `occurrenceKeys` of the discordant cases (for private debugging only), and the replay isolation flags. It is written 0600.

## Privacy and isolation

- **No prompt text in any output.** The manifest, ledger, report, dev-report and stdout hold counts, hashes, verdicts and skill ids. They never hold prompt text, transcript paths, session ids or skill descriptions. Opaque `occurrenceKeys` (a sha256 of hashes) may appear in the private report only. Every error goes through `contract.safe_reason`, so no exception text can carry a prompt.
- **Prompts recovered in memory only.** For a case, the evaluator finds the session's transcript (`session_paths`), then the turn whose sha256 equals the record's `promptHash`. The text lives in memory for the duration of one replay and is never written to disk.
- **Stdin only.** The text reaches `route_replay.js` through its stdin pipe, never through argv, so it cannot appear in a process listing.
- **Isolated child.** The replay child keeps `HOME` unchanged, so it can read local transcripts, but gets fresh temporary `RHIZE_TYPED_DECISIONS_ROOT`, `XDG_DATA_HOME`, `RHIZE_CONTEXT_MANAGER_DIR` and `RHIZE_SUGGESTION_LOG`, and an allowlisted environment with no credentials. The router can therefore not write to the real stores.
- **No network.** A preloaded tripwire aborts the child (exit 97) on any socket, TLS, UDP, HTTP, `fetch` or name-lookup attempt. Route replay never calls Laya, so any network use is a defect, not a degraded mode.

## What it never does

The evaluator and the automation never:

- push, merge, open a PR, or switch the primary checkout off `main`;
- edit the instrument (`laya-instrument.js`, `typed_decisions/*`), the policy, the registry (`decision-registry.json`, `decision-registry.js`), or the gate;
- run the earned-authority gate or cycle (`decision_registry.py`, `decision_cycle.py`). Running the routing harness is a different thing and is part of every candidate's checks;
- edit router code (`route-core.js`, `skill-router.js`) or the harness. `freeze` refuses a candidate that changes router code, because this evaluator covers index and map changes only;
- write prompt text anywhere, or make a network request.

## Operating notes

- **Freeze preconditions.** Both checkouts must be clean (`freeze` refuses uncommitted changes unless `--allow-dirty`). Use a detached baseline worktree at `main` and a candidate worktree on a local branch with the edit committed. After editing, regenerate the map with `python3 scripts/build_skill_map.py` and commit `generated/` with the edit, so the candidate's arm reflects it. The router code must be identical in both checkouts.
- **Small samples.** Only a fraction of router fires becomes a scorable case, and confirmation needs at least 10 discordant ones. Many candidates will sit at `insufficient` for weeks. That is the intended result when the evidence is thin, not a defect.
- **Weak positives cut both ways.** A weak positive is any prompt the user acted on within the same turn. That includes prompts where they followed the router's own suggestion (`invoked_emitted`), which the candidate loses if it reroutes them. The shown suggestion nudges users toward following it, so on these cases the tilt favors the baseline, which makes the rule conservative. `discordant.byType` in the report shows where each win and loss came from.
- **Codex traffic joins, Codex authority does not.** Codex user sessions feed the evaluator like Claude sessions. Laya's authority on Codex stays capped at `shadow` and Codex evidence stays out of the earned-authority gate (the plan's row F6). This evaluator scores only the router's tags and phrases, so that cap does not change it.
- **A `keep` is not a release.** Shipping a kept patch follows the repo's release rules (plugin README and GUIDE, CHANGELOG, `bump_version.py`). A human or an orchestrator does that. The automation does not.
- **Prerequisite.** Confirmation reads outcomes, so it relies on the daily `outcomes.py join` (part of the 07:30 skill-fit loop) having run. The automation never runs the join itself.
- **Access the automation needs.** Write access to `~/.local/share/rhize/typed-decisions/skill-fit/improvement/` and to the repo's `.git` (worktrees and local branches), and read access to local Claude and Codex session folders and `~/.claude/context-manager/refinement-queue.jsonl`. It needs no network.

## The weekly automation: `skill-fit-weekly-improvement`

A Codex automation, local, Sundays at 18:30, working directory the primary checkout of the Rhize plugins repo on `main`. Its prompt, exactly:

```text
You are running skill-fit-weekly-improvement, Jim's weekly, local-only router improvement loop for the Rhize plugins repo. Run it once, in the order below, then stop.

RULES THAT NEVER BEND
- Never git push, never merge, never open a pull request, and never switch the primary checkout off main.
- Never edit, or invoke directly, anything under rhize-context-manager/scripts/typed_decisions/ (including decision_registry.py and the cycle; real_traffic.py and run.py may import and run these modules internally, which is expected), decision-registry.json, rhize-context-manager/hooks/lib/decision-registry.js, rhize-context-manager/hooks/lib/laya-instrument.js, rhize-context-manager/hooks/lib/route-core.js, rhize-context-manager/hooks/skill-router.js, anything under evals/ except to run the two commands named below, or any CI workflow. Never run the earned-authority gate or its cycle. Running the routing harness (run.py --check) and real_traffic.py is your job and is allowed.
- Never write, print, quote or summarise prompt text, transcript text, session ids or transcript paths. You handle only counts, hashes, skill ids, and the files named below. If any command prints something that looks like prompt text, stop and tell Jim.
- Make no network request. Nothing here needs one.
- Everything you write lives under $OUT (a private folder) or in git worktrees and local branches of this repo.

SETUP
REPO=$(git rev-parse --show-toplevel)
ROOT=$HOME/.local/share/rhize/typed-decisions
IMPROVE=$ROOT/skill-fit/improvement
DATE=$(date +%F)
OUT=$IMPROVE/$DATE
EVAL="python3 $REPO/evals/skill-map-routing/real_traffic.py"
Stop and tell Jim if the primary checkout is not on main or not clean, or if $OUT/summary.json already exists (one run per day). Otherwise: umask 077; mkdir -p "$OUT/worktrees". BASE_SHA=$(git -C "$REPO" rev-parse HEAD).

STEP 1. CONFIRM LAST WEEK'S FROZEN CANDIDATES
List the candidates still waiting for a decision with this command:

python3 - "$IMPROVE" "$DATE" <<'PY'
import datetime, glob, json, os, sys
improve, today = sys.argv[1], datetime.date.fromisoformat(sys.argv[2])
final = set()
try:
    with open(os.path.join(improve, 'ledger.jsonl'), encoding='utf-8') as handle:
        for line in handle:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and row.get('verdict') in ('keep', 'discard'):
                final.add(row.get('manifestSha256'))
except OSError:
    pass
for path in sorted(glob.glob(os.path.join(improve, '*', '*.freeze.out.json'))):
    folder = os.path.basename(os.path.dirname(path))
    try:
        frozen = datetime.date.fromisoformat(folder)
        with open(path, encoding='utf-8') as handle:
            sha = json.load(handle).get('manifestSha256')
    except (ValueError, OSError, AttributeError):
        continue
    age = (today - frozen).days
    if not sha or sha in final or age < 1 or age > 35:
        continue
    print(json.dumps({'state': 'expired' if age > 28 else 'pending', 'folder': folder,
                      'name': os.path.basename(path)[:-len('.freeze.out.json')], 'manifestSha256': sha, 'ageDays': age}))
PY

For each line with state "pending", let F be its folder and N its name (for example c2); the candidate number n is N without the leading c:
- The manifest is $IMPROVE/$F/$N.freeze.json and the candidate worktree is $IMPROVE/$F/worktrees/$N on the local branch skill-fit-weekly/$F-$n. If that worktree is missing, recreate it with: git -C "$REPO" worktree add "$IMPROVE/$F/worktrees/$N" skill-fit-weekly/$F-$n. If it still cannot be used, do not evaluate; list the candidate under "needs attention" in your notification.
- Run: $EVAL evaluate --manifest "$IMPROVE/$F/$N.freeze.json" --root "$ROOT" --run-harness --out "$OUT/confirm-$F-$N.report.json"
- The command prints one JSON line with the verdict (keep, discard, insufficient or blocked), the blockers, the discordant count and the p-value, and appends one line to the ledger. Keep that line for your notification.
- Evaluate each manifest at most once in this run, and never a manifest that already has a keep or discard line in the ledger. A keep or discard verdict is final. After a final verdict, remove that candidate's worktree with git -C "$REPO" worktree remove --force; keep its branch.
For each line with state "expired": report it as expired without a decision (insufficient evidence after 4 weeks), remove its worktree the same way, and keep its branch. Evaluate nothing else.

STEP 2. READ THE INPUTS
- Read ~/.claude/context-manager/refinement-queue.jsonl if it exists. Keep only the lines whose source is skill-fit-decisions, and use only signal_type, subtype, target_skill and the counts. Skip any line you cannot parse.
- Make the baseline worktree and run the dev report:
  git -C "$REPO" worktree add --detach "$OUT/worktrees/baseline" "$BASE_SHA"
  $EVAL dev-report --root "$ROOT" --baseline-checkout "$OUT/worktrees/baseline" --out "$OUT/dev-report.json"
  Read topMisses and topFalseFires in $OUT/dev-report.json. They are skill ids and counts.

STEP 3. PROPOSE AT MOST 3 CANDIDATES
Choose at most 3 changes that the queue signals and the dev report support, each aimed at one skill or one tag. Propose fewer, or none, if the evidence is thin. For each candidate number n (1 to 3), let N be c$n:
- git -C "$REPO" worktree add -b skill-fit-weekly/$DATE-$n "$OUT/worktrees/$N" "$BASE_SHA"
- In that worktree edit only: entries in catalog/tags.json, or the tags and trigger phrases of a SKILL.md that this repo owns (a path of the form <plugin>/skills/<skill>/SKILL.md). Change nothing else: no router code, no scripts, no tests, no docs, no versions.
- In that worktree run: python3 scripts/build_skill_map.py
- Check the scope. Every path printed by git -C "$OUT/worktrees/$N" status --porcelain must be catalog/tags.json, a path under generated/, or an owned <plugin>/skills/<skill>/SKILL.md. If any other path appears, remove the worktree with git -C "$REPO" worktree remove --force, delete the branch with git -C "$REPO" branch -D, and record the candidate as dropped with reason out_of_scope.
- Commit locally: git -C "$OUT/worktrees/$N" add -A, then git -C "$OUT/worktrees/$N" commit -m "skill-fit weekly candidate $n". This is a local commit only.

STEP 4. RUN THE ROUTING HARNESS ON EACH CANDIDATE
python3 "$REPO/evals/skill-map-routing/run.py" --checkout "$OUT/worktrees/$N" --check "$REPO/evals/skill-map-routing/baseline.json" --out "$(mktemp -d)"
A non-zero exit means the candidate failed. Remove its worktree, keep its branch, and record it as dropped with reason harness_failed. Do not freeze it.

STEP 5. FREEZE EACH REMAINING CANDIDATE
$EVAL freeze --baseline-checkout "$OUT/worktrees/baseline" --candidate-checkout "$OUT/worktrees/$N" --root "$ROOT" --out "$OUT/$N.freeze.json" > "$OUT/$N.freeze.out.json"
Exit 0 prints status frozen with manifestSha256 and freezeAt. Exit 3 means the freeze was refused (for example, uncommitted changes or a router-code change): record the candidate as dropped with reason refused and remove its worktree. Freeze before you look at anything else. After a freeze, do not change the candidate's files, branch or worktree. Never edit, move or delete a *.freeze.json file or its .arms folder.
When all candidates are frozen or dropped, remove the baseline worktree: git -C "$REPO" worktree remove --force "$OUT/worktrees/baseline"

STEP 6. WRITE THE RESULTS (all of it under $OUT)
- For each frozen candidate: git -C "$REPO" diff "$BASE_SHA" skill-fit-weekly/$DATE-$n > "$OUT/$N.patch"
- Write "$OUT/summary.json" with this shape, using counts, hashes and skill ids only:
  {"date": "<DATE>", "baselineHead": "<BASE_SHA>",
   "confirmed": [{"folder": "...", "name": "cN", "verdict": "keep|discard|insufficient|blocked|expired", "pValue": 0.0, "discordant": 0, "blockers": []}],
   "frozen": [{"name": "cN", "branch": "skill-fit-weekly/<DATE>-n", "manifestSha256": "...", "freezeAt": "...", "files": ["..."]}],
   "dropped": [{"name": "cN", "reason": "out_of_scope|harness_failed|refused"}],
   "needsAttention": []}
- Leave the ledger alone: evaluate has already appended to it.

STEP 7. NOTIFY JIM
Send Jim one short message: for each confirmed candidate its name, verdict, discordant count, p-value and blockers; for each keep, the branch name and the patch path ("recommended for your review, nothing is applied"); the names of the candidates frozen this week; the dropped candidates with reasons; anything that needs attention; and the path of $OUT. Say nothing about prompts.
You never push, merge or open a PR. Stop after the notification.
```

## Verification

```bash
python3 -m pytest -q -p no:cacheprovider tests/skill-map/test_real_traffic.py tests/skill-map tests/rhize-context-manager
```

`tests/skill-map/test_real_traffic.py` builds tiny git repos and indexes, and synthetic records, labels, outcomes and transcripts with injected prompt strings. It covers acceptance test A3:

- exact per-arm, per-type metrics and discordant counts, and exact sign-test values;
- the prospective filter (before, at and after `freezeAt`) and the Codex `thread_source` exclusion;
- every branch of the keep rule, including a harness failure;
- an append-only 0600 ledger that refuses symlinks, and tamper detection on the manifest and the frozen arms;
- no prompt text, session id, path or skill description in any output (scanned for the injected strings);
- stdin-only replay with the isolated environment and the network tripwire, plus one integration test against the real `route_replay.js`.
