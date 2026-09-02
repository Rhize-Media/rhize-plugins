#!/usr/bin/env python3
"""
recurrence.py — did the waste pattern a Headroom-learned rule targets
actually stop recurring after the rule landed in CLAUDE.md?

THE QUESTION THIS ANSWERS: NOT "how many tokens did rule X save" — that
number is `headroom learn`'s own self-reported estimate on the
"~N tokens/session saved" byline under each rule, and nobody has ever
checked it. This module never reads or reports that byline. Instead: for
the concrete, countable thing each rule names — a specific file re-read, a
specific command re-run, a specific loop — did per-session occurrences of
that thing go down, stay flat, or go up, comparing sessions before the
rule's text landed in CLAUDE.md to sessions after?

THIS IS OBSERVATIONAL, NOT A CONTROLLED EXPERIMENT. Sessions before and
after a rule's landing date differ in what work they did, not only in
whether the rule existed. A before/after drop is CONSISTENT WITH the rule
having worked; it is not proof of it, and no verdict in this module's
output is ever phrased as "the rule saved X" or "the rule caused Y". Every
rule record carries `observational_caveat` and a `trust` block saying
plainly what was counted (occurrence counts, landing date — both real
events, both MEASURED) versus what was never measured at all (causal
attribution).

DIRECTIONAL VERDICTS ARE SUPPRESSED (as of this revision, following two
independent reviews of this module's own output). `compute_verdict()` used
to compare per-session occurrence rates before vs. after a rule's landing
date and, past a +/-15% relative-change threshold, emit `reduced`,
`unchanged`, or `increased`. That comparison is REMOVED, not adjusted —
`compute_verdict()` no longer computes any directional label at all. Why,
against the module's own real output (26 rule records across the repos in
DEFAULT_REPOS):

  - Signature ROLE was never classified, and it matters: roughly 13-14 of
    the 26 signatures are PRESCRIPTIONS ("always use `grep -n`", "always
    use `.venv/bin/python`") where a DROP in occurrence rate means the
    advice was ABANDONED, not followed — the opposite of what a `reduced`
    verdict implies. Only ~8-9 of 26 are genuine waste-recurrence targets
    (a re-read loop, a repeated command) where a drop is unambiguously
    good. ~4 more are bare identifiers ("rhize-plugins repo path") with no
    waste semantics either way. Grading all three roles by the same
    "occurrences went down = reduced" rule produces answers that are
    right for one role and backwards for another.
  - The identical signature `npx vitest run 2>&1 | tail -25` appeared
    under two OPPOSITE real bullets ("Use..." and "Never run...") and both
    scored `reduced` — direct proof the old logic cannot distinguish a
    followed prescription from an abandoned one.
  - The single loudest `increased` result was `grep -n` — the PRESCRIBED
    replacement working exactly as intended. Labelling that a regression
    is not a subtle miscalibration; it is the sign flipped.
  - `timeout` matched roughly 400 events under the old substring-match
    signature heuristic, and essentially none of them were the CLI-misuse
    pattern the rule targets — most were the Bash tool's own `timeout`
    input FIELD, a naming collision the signature extractor cannot tell
    apart from the shell command.
  - 9 of the 26 signatures failed an exact binomial test at p<0.05 even
    before correcting for running 26 such tests at once (uncorrected
    multiplicity inflates the false-positive count further), and a pooled
    binomial is the wrong test regardless: occurrences cluster WITHIN a
    session (one session re-reading a file 6 times is not 6 independent
    trials), so the correct test is session-level, not pooled.

What must land before a directional verdict is trustworthy again: (1) a
per-signature ROLE classification (prescription vs. waste-target vs. bare
identifier), so "occurrences went down" is interpreted correctly for each;
(2) a session-level significance test in place of the pooled exact
binomial; (3) a multiplicity correction across however many signatures are
compared in one report run; (4) a frozen transcript manifest, so which
transcripts count as "the earliest surviving one" for a given repo (see
`not_evaluable` below) is a fixed, reproducible input rather than whatever
`~/.claude/projects/` happens to contain at run time.

Until all four land, `compute_verdict()` reports only what it can actually
back: real session counts, real occurrence counts, real per-session rates
(all `trust=measured`), and one of three explicit NON-verdicts —
`not_evaluated` (enough data existed for the old logic to have produced a
directional label, but that label is suppressed — see `reason`),
`insufficient_data` (too little data, but more may arrive over time), or
`not_evaluable` (this rule can never be evaluated no matter how much time
passes — the repo has no surviving transcripts, or the rule's landing date
predates the earliest one that does survive). See `compute_verdict()`'s own
docstring for the exact rules, and
test_recurrence.py::test_build_report_end_to_end_emits_zero_directional_verdicts
for the proof.

Sources -> what's measured vs. inferred:
  Rule text                <repo>/CLAUDE.md, under "## Headroom Learned    MEASURED (the text
                            Patterns"                                      exists, verbatim)
  Landing date              `git log -S'<signature>' --format=%aI --       MEASURED (the date a
                            CLAUDE.md`, EARLIEST matching commit           string appeared in a
                                                                            real commit)
  Per-session occurrence    ~/.claude/projects/<repo>/*.jsonl (direct      MEASURED (a real
  counts                    sessions only — see load_repo_sessions)       tool_use count from a
                                                                            real transcript)
  "the rule CAUSED the      not measured anywhere in this module           NEVER tagged measured;
  change" (causal claim)                                                   see observational_caveat

Landing-date command — CORRECTED from the brief's exact text: the brief
specified `git log --diff-filter=A -S'<text>' --format=%aI -- CLAUDE.md`.
Tested against this repo's own CLAUDE.md before writing any loader code:
`--diff-filter=A` restricts to commits where CLAUDE.md itself was newly
*added* as a file — which happens exactly once, at repo init, and never
again on a long-lived tracked file — so that exact command returns nothing
for every real rule tested. Dropping `--diff-filter=A` and taking the
EARLIEST of however many commits `-S` returns (a rule's exact text is
often touched more than once by later consolidation edits) reproducibly
finds real landing dates. See git_landing_date().

Signature extraction — every real rule inspected before writing this
module names its concrete target inside a backtick span (a file path, a
command, a tool name): "`STATE.md` re-read 31x", "`rtk find` shim lacks
-not". Extracting the FIRST backtick span in a bullet is therefore the
signature heuristic here. A bullet with no backtick span, or a bullet
naming several targets in one sentence (only the first is captured), is a
known, reported limitation — see the module's `unparseable_signature`
rules and the miss-rate figures in the summary, never silently dropped.

Trust vocabulary note: this module does NOT import stack_metrics.TrustClass.
That taxonomy is about whether a NUMERIC metric is safe to sum; this module
sums nothing across rules and its measured/inferred split is a different
axis (evidence for "this occurred" vs. inference about "this rule caused
it"). Re-using TrustClass here would overload a vocabulary built for a
different guarantee. Kept self-contained per this project's single-file-
script convention (see stack_metrics.py's own docstring on the same
choice, made for the same reason, against the same sibling file).

Usage:
  python3 recurrence.py                  # human-readable, writes data/recurrence.json
  python3 recurrence.py --json           # JSON to stdout, still writes the file
  python3 recurrence.py --min-sessions 5 # raise the insufficient_data floor
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import paths

HOME = Path.home()
DEFAULT_OUT_PATH = paths.data_dir() / "recurrence.json"

DEFAULT_PROJECTS_DIR = HOME / ".claude" / "projects"

# Each configured repo root (RHIZE_REPO_ROOTS — see paths.py) is a candidate:
# any repo with a CLAUDE.md carrying one or more "## Headroom Learned
# Patterns" sections is measured. [] configured -> {} (nothing measured).
DEFAULT_REPOS: dict[str, Path] = {root.name: root for root in paths.repo_roots()}

MIN_SESSIONS_PER_SIDE_DEFAULT = 3
MIN_SIGNATURE_LEN = 4

# VERDICT_REDUCED / VERDICT_UNCHANGED / VERDICT_INCREASED / VERDICT_THRESHOLD
# (a +/-15% relative-rate-change comparison) are REMOVED, not renamed or
# left dead — see the module docstring's "DIRECTIONAL VERDICTS ARE
# SUPPRESSED" section for why. `compute_verdict()` never emits a
# directional label; do not reintroduce one under a new name.
VERDICT_NOT_EVALUATED = "not_evaluated"
VERDICT_INSUFFICIENT_DATA = "insufficient_data"
VERDICT_NOT_EVALUABLE = "not_evaluable"

VERDICT_SUPPRESSION_REASON = (
    "Directional verdicts (reduced/unchanged/increased) are suppressed: "
    "(1) signature role (prescription vs. waste-target vs. bare identifier) "
    "is not classified, and a drop means opposite things for a prescription "
    "vs. a waste target; (2) statistical support is untested — the correct "
    "test is session-level (occurrences cluster within a session), not the "
    "pooled exact binomial the old threshold logic implicitly relied on; "
    "(3) multiplicity across every signature compared in one report run is "
    "uncorrected. See the module docstring for the full case and what must "
    "land before a directional verdict returns."
)

STATUS_OK = "ok"
STATUS_UNPARSEABLE_SIGNATURE = "unparseable_signature"
STATUS_NO_LANDING_DATE = "no_landing_date"

OBSERVATIONAL_CAVEAT = (
    "Observational, not a controlled experiment: sessions before and after "
    "the landing date differ in what work they did, not only in whether "
    "this rule existed. A before/after change is consistent with the rule "
    "having worked; it is not proof, and this record never claims the rule "
    "caused the change."
)

HEADROOM_HEADING_TEXT = "Headroom Learned Patterns"
_H2_RE = re.compile(r"^## (.+)$")
_H3_RE = re.compile(r"^### (.+)$")
_BULLET_RE = re.compile(r"^- (.+)$")
_BACKTICK_RE = re.compile(r"`([^`]+)`")


def parse_iso(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# ---------------------------------------------------------------------------
# CLAUDE.md parsing -> raw rules
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RawRule:
    section_title: str  # nearest preceding H3 within the H2 block, "" if none
    bullet_text: str


def extract_headroom_rules(text: str) -> list[RawRule]:
    """Every top-level bullet ("- ..." at column 0) found under any
    "## Headroom Learned Patterns" H2 section in `text`, tagged with the
    nearest preceding H3 heading inside that same H2 block (or "" if the
    bullet sits directly under the H2 with no H3 yet). Handles a file with
    the H2 heading repeated multiple times (seo-report-automation has 5,
    one per un-consolidated `headroom learn` run) — each occurrence opens a
    fresh H3 scope. A non-matching H2 (e.g. "## Project Overview") closes
    the section until the next matching H2.
    """
    rules: list[RawRule] = []
    in_section = False
    current_h3 = ""
    for line in text.splitlines():
        h2 = _H2_RE.match(line)
        if h2:
            in_section = h2.group(1).strip() == HEADROOM_HEADING_TEXT
            current_h3 = ""
            continue
        if not in_section:
            continue
        h3 = _H3_RE.match(line)
        if h3:
            current_h3 = h3.group(1).strip()
            continue
        bullet = _BULLET_RE.match(line)
        if bullet:
            rules.append(RawRule(section_title=current_h3, bullet_text=bullet.group(1).strip()))
    return rules


def extract_signature(bullet_text: str) -> str | None:
    """The first backtick-quoted span in the bullet, if any and if long
    enough to be a plausible concrete target rather than a stray fragment.
    A bullet naming multiple targets in one sentence only yields the first
    — a documented limitation, not a silent drop (see module docstring)."""
    matches = _BACKTICK_RE.findall(bullet_text)
    if not matches:
        return None
    sig = matches[0].strip()
    if len(sig) < MIN_SIGNATURE_LEN:
        return None
    return sig


# ---------------------------------------------------------------------------
# Landing date via git
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LandingDate:
    date: datetime | None
    method: str
    matching_commit_dates: tuple[str, ...] = ()


def git_landing_date(
    repo_path: Path,
    signature: str,
    claude_md_rel: str = "CLAUDE.md",
) -> LandingDate:
    """Earliest commit where `git log -S<signature>` reports a change to
    that string's occurrence count in CLAUDE.md — i.e. the earliest point
    this exact text is known to have appeared. See module docstring for why
    `--diff-filter=A` (the brief's exact command) is dropped: it structurally
    cannot match on a file that already existed before the rule was added."""
    if not (repo_path / ".git").exists():
        return LandingDate(None, f"not a git repository: {repo_path}")
    claude_md = repo_path / claude_md_rel
    if not claude_md.exists():
        return LandingDate(None, f"{claude_md_rel} not found in {repo_path}")

    try:
        proc = subprocess.run(
            ["git", "log", "-S", signature, "--format=%aI", "--", claude_md_rel],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return LandingDate(None, f"git invocation failed: {type(e).__name__}: {e}")
    if proc.returncode != 0:
        return LandingDate(
            None, f"git exited {proc.returncode}: {proc.stderr.strip()[:300]}"
        )

    dates_raw = tuple(ln.strip() for ln in proc.stdout.splitlines() if ln.strip())
    if not dates_raw:
        return LandingDate(
            None,
            "git log -S found no commit that changed this signature's occurrence "
            "count in CLAUDE.md — the exact text may have been reworded since it "
            "was written, or added by a hand edit whose commit predates the "
            "signature's current wording.",
        )

    parsed: list[datetime] = []
    for d in dates_raw:
        try:
            parsed.append(parse_iso(d))
        except ValueError:
            continue
    if not parsed:
        return LandingDate(None, "git returned commit dates that failed to parse", dates_raw)

    earliest = min(parsed)
    method = (
        f"git log -S'<signature>' --format=%aI -- {claude_md_rel} (no --diff-filter=A "
        f"— see module docstring); earliest of {len(parsed)} matching commit(s)."
    )
    return LandingDate(earliest, method, dates_raw)


# ---------------------------------------------------------------------------
# Session transcripts -> per-session occurrence counts
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SessionRecord:
    session_id: str
    start_ts: datetime  # earliest timestamp found in the transcript
    haystacks: tuple[str, ...]  # one lowercased "name input_json" string per tool_use event


def encode_project_dir(repo_path: Path) -> str:
    """Mirrors Claude Code's own project-directory encoding: the absolute
    repo path with every "/" replaced by "-"."""
    return str(repo_path.resolve()).replace("/", "-")


def load_repo_sessions(repo_path: Path, projects_dir: Path | None = None) -> dict:
    """Loads every DIRECT session transcript for `repo_path` — top-level
    `<project_dir>/<sessionId>.jsonl` files only. Nested
    `<sessionId>/subagents/*.jsonl` transcripts are out of scope: every rule
    this module measures is phrased "per session" against the main session,
    and a rule's guidance (CLAUDE.md) is loaded once at session start, so a
    session's bucket (before/after landing date) is decided by the EARLIEST
    timestamp found in its transcript, not by individual event times.

    Parses each transcript exactly once regardless of how many rules will be
    measured against it — extracting a lowercased "tool_name input_json"
    haystack string per tool_use event — so per-rule signature counting
    (count_signature, below) is a fast in-memory substring scan, not a
    re-parse of every file per rule.

    Never raises on a missing project directory or an unreadable/malformed
    file — both are recorded as gaps, never silently dropped."""
    root = projects_dir if projects_dir is not None else DEFAULT_PROJECTS_DIR
    project_dir = root / encode_project_dir(repo_path)
    if not project_dir.exists():
        return {
            "available": False,
            "error": f"no transcript directory: {project_dir}",
            "sessions": [],
            "files_scanned": 0,
            "files_unreadable": 0,
            "files_no_timestamp": 0,
        }

    sessions: list[SessionRecord] = []
    files_unreadable = 0
    files_no_timestamp = 0

    try:
        files = sorted(project_dir.glob("*.jsonl"))
    except OSError as e:
        return {
            "available": False,
            "error": str(e),
            "sessions": [],
            "files_scanned": 0,
            "files_unreadable": 0,
            "files_no_timestamp": 0,
        }

    for f in files:
        earliest: datetime | None = None
        haystacks: list[str] = []
        try:
            with f.open("r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    ts_raw = row.get("timestamp")
                    if ts_raw:
                        try:
                            dt = parse_iso(ts_raw)
                            if earliest is None or dt < earliest:
                                earliest = dt
                        except ValueError:
                            pass

                    if row.get("type") != "assistant":
                        continue
                    message = row.get("message")
                    content = message.get("content") if isinstance(message, dict) else None
                    if not isinstance(content, list):
                        continue
                    for item in content:
                        if not isinstance(item, dict) or item.get("type") != "tool_use":
                            continue
                        name = item.get("name", "")
                        try:
                            input_json = json.dumps(item.get("input", {}), ensure_ascii=False)
                        except (TypeError, ValueError):
                            input_json = str(item.get("input"))
                        haystacks.append(f"{name} {input_json}".lower())
        except OSError:
            files_unreadable += 1
            continue

        if earliest is None:
            # No usable timestamp anywhere in the file — can't bucket it
            # before/after a landing date, so it's excluded, but recorded.
            files_no_timestamp += 1
            continue

        sessions.append(
            SessionRecord(session_id=f.stem, start_ts=earliest, haystacks=tuple(haystacks))
        )

    return {
        "available": True,
        "error": None,
        "sessions": sessions,
        "files_scanned": len(files),
        "files_unreadable": files_unreadable,
        "files_no_timestamp": files_no_timestamp,
    }


@dataclass(frozen=True)
class SessionCount:
    session_id: str
    start_ts: datetime
    occurrences: int


def count_signature(sessions: list[SessionRecord], signature: str) -> list[SessionCount]:
    sig_lower = signature.lower()
    return [
        SessionCount(
            session_id=s.session_id,
            start_ts=s.start_ts,
            occurrences=sum(1 for h in s.haystacks if sig_lower in h),
        )
        for s in sessions
    ]


# ---------------------------------------------------------------------------
# Verdict computation
# ---------------------------------------------------------------------------

def _rate(counts: list[SessionCount]) -> float:
    if not counts:
        return 0.0
    return sum(c.occurrences for c in counts) / len(counts)


def compute_verdict(
    before: list[SessionCount],
    after: list[SessionCount],
    min_sessions: int = MIN_SESSIONS_PER_SIDE_DEFAULT,
    before_side_evaluable: bool = True,
    not_evaluable_reason: str | None = None,
) -> dict:
    """Computes real, measured session/occurrence/rate figures for both
    sides, and an explicit NON-verdict — never a directional
    reduced/unchanged/increased claim. See the module docstring's
    "DIRECTIONAL VERDICTS ARE SUPPRESSED" section for why.

    `verdict` is exactly one of:

      not_evaluable     — this rule can never be evaluated, no matter how
                          much more time passes. The caller determines this
                          (per repo, not per rule) from whether the repo has
                          any surviving transcripts at all and whether the
                          landing date is at or before the earliest
                          surviving one — see `before_side_evaluable`. This
                          is checked FIRST and short-circuits everything
                          else: a structurally-blocked side is not made
                          "insufficient" by having fewer sessions than
                          min_sessions: it is unevaluable regardless.
      insufficient_data — too few sessions on a side (below `min_sessions`),
                          or zero occurrences on BOTH sides. Distinct from
                          not_evaluable: this MAY resolve as more sessions
                          accumulate over time.
      not_evaluated     — enough real data exists that the old threshold
                          logic would have emitted a directional verdict.
                          That logic is suppressed; `reason` explains why
                          (see VERDICT_SUPPRESSION_REASON).

    `before_side_evaluable=False` (with `not_evaluable_reason` set) forces
    `not_evaluable` regardless of the actual before/after counts — the
    caller has already determined this rule structurally cannot be
    evaluated before calling this function.
    """
    n_before, n_after = len(before), len(after)
    occ_before = sum(c.occurrences for c in before)
    occ_after = sum(c.occurrences for c in after)
    rate_before = _rate(before)
    rate_after = _rate(after)

    result = {
        "sessions_before": n_before,
        "sessions_after": n_after,
        "occurrences_before": occ_before,
        "occurrences_after": occ_after,
        "rate_before_per_session": rate_before,
        "rate_after_per_session": rate_after,
        "min_sessions_per_side": min_sessions,
        "low_occurrence_signal": (occ_before + occ_after) < 5,
    }

    if not before_side_evaluable:
        result["verdict"] = VERDICT_NOT_EVALUABLE
        result["reason"] = not_evaluable_reason or (
            "this rule can never be evaluated regardless of how much time passes"
        )
        return result

    if n_before < min_sessions or n_after < min_sessions:
        result["verdict"] = VERDICT_INSUFFICIENT_DATA
        result["reason"] = (
            f"fewer than {min_sessions} sessions on at least one side "
            f"(before={n_before}, after={n_after}) — may resolve as more "
            "sessions accumulate"
        )
        return result

    if occ_before == 0 and occ_after == 0:
        result["verdict"] = VERDICT_INSUFFICIENT_DATA
        result["reason"] = (
            "the signature was observed zero times on both sides — we never "
            "observed the pattern at all, which is a different claim from "
            "the rule having eliminated it"
        )
        return result

    result["verdict"] = VERDICT_NOT_EVALUATED
    result["reason"] = VERDICT_SUPPRESSION_REASON
    return result


# ---------------------------------------------------------------------------
# Per-repo / whole-report assembly
# ---------------------------------------------------------------------------

def build_repo_report(
    repo_name: str,
    repo_path: Path,
    projects_dir: Path | None = None,
    min_sessions: int = MIN_SESSIONS_PER_SIDE_DEFAULT,
) -> dict:
    """Runs the full pipeline for one repo: read CLAUDE.md -> extract rules
    -> per rule, extract signature -> git landing date -> session counts ->
    verdict. Never raises: a missing CLAUDE.md, a non-git directory, or a
    missing transcript directory each degrade to recorded gaps rather than
    stopping the whole report."""
    claude_md = repo_path / "CLAUDE.md"
    coverage = {
        "repo": repo_name,
        "repo_path": str(repo_path),
        "claude_md_found": claude_md.exists(),
        "is_git_repo": (repo_path / ".git").exists(),
    }

    if not claude_md.exists():
        coverage["error"] = f"CLAUDE.md not found: {claude_md}"
        return {"coverage": coverage, "rules": []}

    try:
        text = claude_md.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        coverage["error"] = f"could not read {claude_md}: {e}"
        return {"coverage": coverage, "rules": []}

    raw_rules = extract_headroom_rules(text)
    coverage["error"] = None
    coverage["headroom_sections_found"] = text.count(f"## {HEADROOM_HEADING_TEXT}")
    coverage["rules_found"] = len(raw_rules)

    sessions_result = load_repo_sessions(repo_path, projects_dir=projects_dir)
    coverage["transcript_dir_found"] = sessions_result["available"]
    coverage["transcript_error"] = sessions_result.get("error")
    coverage["files_scanned"] = sessions_result.get("files_scanned", 0)
    coverage["files_unreadable"] = sessions_result.get("files_unreadable", 0)
    coverage["files_no_timestamp"] = sessions_result.get("files_no_timestamp", 0)
    sessions: list[SessionRecord] = sessions_result.get("sessions", [])

    # The earliest surviving transcript for this repo, if any. Used below to
    # tell "insufficient_data" (may resolve with time) apart from
    # "not_evaluable" (structurally permanent): if a rule's landing date is
    # at or before the earliest transcript that still exists, no session
    # earlier than that landing date can EVER be found — the past doesn't
    # grow new transcripts. Same conclusion, degenerate case, when the repo
    # has zero surviving transcripts at all.
    earliest_transcript_ts = min((s.start_ts for s in sessions), default=None)

    rule_records = []
    for raw in raw_rules:
        signature = extract_signature(raw.bullet_text)
        record = {
            "repo": repo_name,
            "section_title": raw.section_title,
            "bullet_text": raw.bullet_text,
            "signature": signature,
            "observational_caveat": OBSERVATIONAL_CAVEAT,
            "trust": {
                "occurrence_counts": "measured",
                "landing_date": "measured" if signature else "not_applicable",
                "causal_attribution": "not_measured",
                "directional_verdict": "not_measured",
            },
        }

        if signature is None:
            record["status"] = STATUS_UNPARSEABLE_SIGNATURE
            record["status_detail"] = (
                "no backtick-quoted span found in this bullet's text — no "
                "concrete, matchable target could be extracted"
            )
            rule_records.append(record)
            continue

        landing = git_landing_date(repo_path, signature)
        record["landing_date"] = landing.date.isoformat() if landing.date else None
        record["landing_date_method"] = landing.method
        record["landing_date_matching_commits"] = list(landing.matching_commit_dates)

        if landing.date is None:
            record["status"] = STATUS_NO_LANDING_DATE
            rule_records.append(record)
            continue

        if earliest_transcript_ts is None:
            before_evaluable = False
            not_evaluable_reason = (
                f"{repo_name} has zero surviving session transcripts — this "
                "rule can never be evaluated"
            )
        elif landing.date <= earliest_transcript_ts:
            before_evaluable = False
            not_evaluable_reason = (
                f"rule landed {landing.date.date().isoformat()}, at or "
                f"before the earliest surviving transcript for {repo_name} "
                f"({earliest_transcript_ts.date().isoformat()}) — the "
                "'before' side can never acquire data no matter how much "
                "time passes"
            )
        else:
            before_evaluable = True
            not_evaluable_reason = None

        counts = count_signature(sessions, signature)
        before = [c for c in counts if c.start_ts < landing.date]
        after = [c for c in counts if c.start_ts >= landing.date]
        verdict_detail = compute_verdict(
            before, after, min_sessions=min_sessions,
            before_side_evaluable=before_evaluable,
            not_evaluable_reason=not_evaluable_reason,
        )

        record["status"] = STATUS_OK
        record.update(verdict_detail)
        rule_records.append(record)

    return {"coverage": coverage, "rules": rule_records}


def build_report(
    repos: dict[str, Path] | None = None,
    projects_dir: Path | None = None,
    min_sessions: int = MIN_SESSIONS_PER_SIDE_DEFAULT,
) -> dict:
    repos = repos if repos is not None else DEFAULT_REPOS

    repo_reports = {}
    all_rules: list[dict] = []
    for repo_name, repo_path in repos.items():
        result = build_repo_report(
            repo_name, repo_path, projects_dir=projects_dir, min_sessions=min_sessions
        )
        repo_reports[repo_name] = result["coverage"]
        all_rules.extend(result["rules"])

    total_rules = len(all_rules)
    unparseable = sum(1 for r in all_rules if r["status"] == STATUS_UNPARSEABLE_SIGNATURE)
    no_landing_date = sum(1 for r in all_rules if r["status"] == STATUS_NO_LANDING_DATE)
    measured = sum(1 for r in all_rules if r["status"] == STATUS_OK)
    verdict_counts = {v: 0 for v in (
        VERDICT_NOT_EVALUATED, VERDICT_INSUFFICIENT_DATA, VERDICT_NOT_EVALUABLE
    )}
    for r in all_rules:
        if r["status"] == STATUS_OK:
            verdict_counts[r["verdict"]] += 1

    summary = {
        "total_rules_found": total_rules,
        "signature_extracted_count": total_rules - unparseable,
        "signature_unparseable_count": unparseable,
        "signature_parse_miss_rate": (unparseable / total_rules) if total_rules else None,
        "landing_date_found_count": measured,
        "landing_date_not_found_count": no_landing_date,
        "fully_measured_count": measured,
        "overall_usable_rate": (measured / total_rules) if total_rules else None,
        "verdict_counts": verdict_counts,
    }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "min_sessions_per_side": min_sessions,
        "observational_caveat": OBSERVATIONAL_CAVEAT,
        "repos": repo_reports,
        "summary": summary,
        "rules": all_rules,
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render_text(report: dict) -> str:
    lines: list[str] = []
    lines.append(f"recurrence report — {report['generated_at']}")
    lines.append(f"(min sessions/side: {report['min_sessions_per_side']}; "
                 "directional verdicts are suppressed — see module docstring)")
    lines.append("")
    lines.append("Repo coverage:")
    for repo_name, cov in report["repos"].items():
        if not cov.get("claude_md_found"):
            lines.append(f"  - {repo_name}: CLAUDE.md NOT FOUND ({cov.get('error')})")
            continue
        lines.append(
            f"  - {repo_name}: {cov['rules_found']} rule(s) found across "
            f"{cov['headroom_sections_found']} Headroom section(s); "
            f"transcripts: {'found' if cov['transcript_dir_found'] else 'MISSING'} "
            f"({cov['files_scanned']} scanned, {cov['files_unreadable']} unreadable, "
            f"{cov['files_no_timestamp']} no usable timestamp)"
        )

    s = report["summary"]
    lines.append("")
    lines.append("Summary:")
    lines.append(f"  total rules found: {s['total_rules_found']}")
    if s["signature_parse_miss_rate"] is not None:
        lines.append(
            f"  signature extracted: {s['signature_extracted_count']} "
            f"(miss rate: {s['signature_parse_miss_rate']:.1%})"
        )
    else:
        lines.append("  signature extracted: 0")
    lines.append(f"  landing date found: {s['landing_date_found_count']}")
    lines.append(f"  landing date NOT found: {s['landing_date_not_found_count']}")
    lines.append(f"  fully measured (verdict computed): {s['fully_measured_count']}")
    lines.append("  verdicts:")
    for v, n in s["verdict_counts"].items():
        lines.append(f"    {v}: {n}")

    lines.append("")
    lines.append("Rules:")
    for r in report["rules"]:
        header = f"  [{r['repo']}] {r['section_title'] or '(no subsection)'}"
        if r["status"] == STATUS_UNPARSEABLE_SIGNATURE:
            lines.append(f"{header} — UNPARSEABLE (no backtick signature)")
            continue
        if r["status"] == STATUS_NO_LANDING_DATE:
            lines.append(
                f"{header} — signature=`{r['signature']}` — NO LANDING DATE "
                f"({r['landing_date_method']})"
            )
            continue
        lines.append(
            f"{header} — signature=`{r['signature']}` — landed {r['landing_date']} — "
            f"verdict={r['verdict']} "
            f"(before: {r['sessions_before']} sessions/{r['occurrences_before']} occ, "
            f"rate={r['rate_before_per_session']:.2f}; "
            f"after: {r['sessions_after']} sessions/{r['occurrences_after']} occ, "
            f"rate={r['rate_after_per_session']:.2f})"
            + (" [low occurrence signal]" if r.get("low_occurrence_signal") else "")
        )
        if r.get("reason"):
            lines.append(f"      reason: {r['reason']}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="print the report as JSON to stdout")
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT_PATH,
        help=f"where to write the JSON report (default: {DEFAULT_OUT_PATH})",
    )
    parser.add_argument(
        "--min-sessions",
        type=int,
        default=MIN_SESSIONS_PER_SIDE_DEFAULT,
        help=f"minimum sessions required per side before/after landing date "
             f"(default: {MIN_SESSIONS_PER_SIDE_DEFAULT})",
    )
    args = parser.parse_args(argv)

    report = build_report(min_sessions=args.min_sessions)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(render_text(report))
        print(f"\n(report written to {args.out})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
