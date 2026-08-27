"""Tests for recurrence.py — the Headroom-learned-rule recurrence measurer.

Run: python3 -m pytest tests/test_recurrence.py -q   (from the repo root)

Covers: the CLAUDE.md rule parser (well-formed, repeated H2, no-H3 bullet,
no-signature bullet), the transcript walker (well-formed, malformed line,
empty file, missing directory, no-timestamp file), git_landing_date against
a real temp git repo (well-formed, not-a-repo, missing CLAUDE.md, signature
never present), and — the module's central requirement — the four-verdict
proof: `compute_verdict` produces `reduced`, `unchanged`, `increased`, and
BOTH `insufficient_data` cases (too few sessions; zero occurrences on both
sides), plus one full `build_report()` end-to-end run proving the whole
pipeline wires those same four outcomes together correctly, not just the
pure function in isolation.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import recurrence  # noqa: E402


def _dt(s: str) -> datetime:
    return recurrence.parse_iso(s)


def _write_jsonl(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _tool_use_row(ts: str, tool_name: str, tool_input: dict) -> str:
    return json.dumps({
        "type": "assistant",
        "timestamp": ts,
        "message": {"content": [{"type": "tool_use", "name": tool_name, "input": tool_input}]},
    })


# ---------------------------------------------------------------------------
# extract_headroom_rules / extract_signature
# ---------------------------------------------------------------------------

def test_extract_rules_well_formed_with_h3_sections():
    text = (
        "# CLAUDE.md\n"
        "\n"
        "## Headroom Learned Patterns\n"
        "*Auto-generated*\n"
        "\n"
        "### Section A\n"
        "*~500 tokens/session saved*\n"
        "- `foo.md` re-read too often; read once.\n"
        "\n"
        "### Section B\n"
        "- `some-cmd --flag` re-run repeatedly.\n"
        "- second bullet with no backtick at all.\n"
    )
    rules = recurrence.extract_headroom_rules(text)
    assert [r.section_title for r in rules] == ["Section A", "Section B", "Section B"]
    assert rules[0].bullet_text == "`foo.md` re-read too often; read once."
    assert rules[2].bullet_text == "second bullet with no backtick at all."


def test_extract_rules_ignores_non_headroom_h2_sections():
    text = (
        "## Project Overview\n"
        "- `not-a-rule.md` should be ignored.\n"
        "\n"
        "## Headroom Learned Patterns\n"
        "### Real Section\n"
        "- `real-signature` counts.\n"
        "\n"
        "## Another Section\n"
        "- `also-ignored` should not count.\n"
    )
    rules = recurrence.extract_headroom_rules(text)
    assert len(rules) == 1
    assert rules[0].bullet_text == "`real-signature` counts."


def test_extract_rules_repeated_h2_heading_mirrors_unconsolidated_file():
    """seo-report-automation's CLAUDE.md has 5 separate '## Headroom Learned
    Patterns' H2 sections (un-consolidated headroom-learn runs) — each must
    open a fresh H3 scope and all their bullets must be captured."""
    text = (
        "## Headroom Learned Patterns\n"
        "### First Run\n"
        "- `alpha` from the first run.\n"
        "\n"
        "## Headroom Learned Patterns\n"
        "### Second Run\n"
        "- `beta` from the second run.\n"
    )
    rules = recurrence.extract_headroom_rules(text)
    assert len(rules) == 2
    assert rules[0].section_title == "First Run"
    assert rules[1].section_title == "Second Run"


def test_extract_rules_bullet_with_no_h3_parent():
    text = "## Headroom Learned Patterns\n- `orphan-bullet` has no H3 parent.\n"
    rules = recurrence.extract_headroom_rules(text)
    assert len(rules) == 1
    assert rules[0].section_title == ""


def test_extract_signature_first_backtick_span():
    assert recurrence.extract_signature("The `rtk find` shim lacks -not/-exec.") == "rtk find"


def test_extract_signature_none_without_backticks():
    assert recurrence.extract_signature("No backticks in this bullet at all.") is None


def test_extract_signature_none_when_too_short():
    assert recurrence.extract_signature("A stray `xy` fragment.") is None


# ---------------------------------------------------------------------------
# load_repo_sessions
# ---------------------------------------------------------------------------

def test_load_repo_sessions_missing_project_dir(tmp_path):
    result = recurrence.load_repo_sessions(tmp_path / "repo", projects_dir=tmp_path / "projects")
    assert result["available"] is False
    assert result["sessions"] == []


def test_load_repo_sessions_empty_project_dir(tmp_path):
    repo = tmp_path / "repo"
    projects_dir = tmp_path / "projects"
    project_dir = projects_dir / recurrence.encode_project_dir(repo)
    project_dir.mkdir(parents=True)
    result = recurrence.load_repo_sessions(repo, projects_dir=projects_dir)
    assert result["available"] is True
    assert result["sessions"] == []
    assert result["files_scanned"] == 0


def test_load_repo_sessions_malformed_line_is_skipped_not_fatal(tmp_path):
    repo = tmp_path / "repo"
    projects_dir = tmp_path / "projects"
    project_dir = projects_dir / recurrence.encode_project_dir(repo)
    _write_jsonl(project_dir / "sess1.jsonl", [
        "{not valid json",
        json.dumps({"type": "user", "timestamp": "2026-01-01T00:00:00Z"}),  # not assistant
        _tool_use_row("2026-01-01T00:01:00Z", "Bash", {"command": "echo hi"}),
    ])
    result = recurrence.load_repo_sessions(repo, projects_dir=projects_dir)
    assert result["available"] is True
    assert len(result["sessions"]) == 1
    assert result["sessions"][0].start_ts == _dt("2026-01-01T00:00:00Z")
    assert len(result["sessions"][0].haystacks) == 1


def test_load_repo_sessions_file_with_no_timestamp_is_a_recorded_gap(tmp_path):
    repo = tmp_path / "repo"
    projects_dir = tmp_path / "projects"
    project_dir = projects_dir / recurrence.encode_project_dir(repo)
    _write_jsonl(project_dir / "sess1.jsonl", [
        json.dumps({"type": "assistant", "message": {"content": []}}),  # no timestamp field
    ])
    result = recurrence.load_repo_sessions(repo, projects_dir=projects_dir)
    assert result["available"] is True
    assert result["sessions"] == []
    assert result["files_no_timestamp"] == 1


def test_load_repo_sessions_well_formed_extracts_haystacks(tmp_path):
    repo = tmp_path / "repo"
    projects_dir = tmp_path / "projects"
    project_dir = projects_dir / recurrence.encode_project_dir(repo)
    _write_jsonl(project_dir / "sess1.jsonl", [
        _tool_use_row("2026-01-05T10:00:00Z", "Read", {"file_path": "STATE.md"}),
        _tool_use_row("2026-01-05T10:01:00Z", "Bash", {"command": "npm test"}),
    ])
    result = recurrence.load_repo_sessions(repo, projects_dir=projects_dir)
    assert result["available"] is True
    sessions = result["sessions"]
    assert len(sessions) == 1
    assert sessions[0].session_id == "sess1"
    assert sessions[0].start_ts == _dt("2026-01-05T10:00:00Z")
    assert any("state.md" in h for h in sessions[0].haystacks)
    assert any("npm test" in h for h in sessions[0].haystacks)


def test_count_signature_counts_case_insensitively(tmp_path):
    repo = tmp_path / "repo"
    projects_dir = tmp_path / "projects"
    project_dir = projects_dir / recurrence.encode_project_dir(repo)
    _write_jsonl(project_dir / "sess1.jsonl", [
        _tool_use_row("2026-01-05T10:00:00Z", "Read", {"file_path": "STATE.md"}),
        _tool_use_row("2026-01-05T10:01:00Z", "Read", {"file_path": "state.md"}),
        _tool_use_row("2026-01-05T10:02:00Z", "Bash", {"command": "npm test"}),
    ])
    sessions = recurrence.load_repo_sessions(repo, projects_dir=projects_dir)["sessions"]
    counts = recurrence.count_signature(sessions, "STATE.md")
    assert len(counts) == 1
    assert counts[0].occurrences == 2


# ---------------------------------------------------------------------------
# git_landing_date — against a real temp git repo
# ---------------------------------------------------------------------------

def _git(repo: Path, *args: str, date: str | None = None) -> None:
    env = None
    if date:
        import os
        env = dict(os.environ, GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
    subprocess.run(["git", *args], cwd=str(repo), check=True, capture_output=True, env=env)


def _init_git_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")


def test_git_landing_date_not_a_git_repo(tmp_path):
    repo = tmp_path / "not-a-repo"
    repo.mkdir()
    (repo / "CLAUDE.md").write_text("no git here")
    result = recurrence.git_landing_date(repo, "some-signature")
    assert result.date is None
    assert "not a git repository" in result.method


def test_git_landing_date_missing_claude_md(tmp_path):
    repo = tmp_path / "repo"
    _init_git_repo(repo)
    result = recurrence.git_landing_date(repo, "some-signature")
    assert result.date is None
    assert "not found" in result.method


def test_git_landing_date_signature_never_present(tmp_path):
    repo = tmp_path / "repo"
    _init_git_repo(repo)
    (repo / "CLAUDE.md").write_text("# CLAUDE.md\nnothing interesting here\n")
    _git(repo, "add", "CLAUDE.md")
    _git(repo, "commit", "-q", "-m", "init", date="2026-01-01T00:00:00")
    result = recurrence.git_landing_date(repo, "never-appears-anywhere")
    assert result.date is None
    assert "no commit" in result.method.lower()


def test_git_landing_date_well_formed_finds_earliest_commit(tmp_path):
    repo = tmp_path / "repo"
    _init_git_repo(repo)
    (repo / "CLAUDE.md").write_text("# CLAUDE.md\nno rules yet\n")
    _git(repo, "add", "CLAUDE.md")
    _git(repo, "commit", "-q", "-m", "init", date="2026-01-01T00:00:00")

    (repo / "CLAUDE.md").write_text(
        "# CLAUDE.md\n## Headroom Learned Patterns\n### Rule\n- `unique-token-xyz` is a thing.\n"
    )
    _git(repo, "add", "CLAUDE.md")
    _git(repo, "commit", "-q", "-m", "add rule", date="2026-02-15T12:00:00")

    result = recurrence.git_landing_date(repo, "unique-token-xyz")
    assert result.date is not None
    assert result.date.date().isoformat() == "2026-02-15"
    assert len(result.matching_commit_dates) == 1


# ---------------------------------------------------------------------------
# DIRECTIONAL VERDICT SUPPRESSION PROOF — compute_verdict in isolation
#
# Every scenario below used to be a clean, textbook case for one of
# reduced/increased/unchanged under the old +/-15%-relative-rate-change
# threshold. Two independent reviews concluded those labels are not
# publishable (role-misclassified prescriptions, an identical signature
# scored 'reduced' under two opposite bullets, an 'increased' result that
# was the rule working as intended, 9/26 signatures failing significance
# uncorrected — see recurrence.py's module docstring). This is not a
# recalibration of the threshold: the threshold logic itself is gone, so
# every one of these scenarios must now land on the same non-directional
# label regardless of how clean the underlying before/after signal is.
# ---------------------------------------------------------------------------

_DIRECTIONAL_LABELS = {"reduced", "increased", "unchanged"}


def _counts(occurrences_list: list[int], start: str = "2026-01-01T00:00:00Z") -> list[recurrence.SessionCount]:
    base = _dt(start)
    return [
        recurrence.SessionCount(session_id=f"s{i}", start_ts=base, occurrences=n)
        for i, n in enumerate(occurrences_list)
    ]


def test_verdict_large_drop_does_not_emit_reduced():
    """Occurrences 3->0 across the landing date — a 100% drop, a clean
    'reduced' under the old logic. Must now be not_evaluated."""
    before = _counts([3, 3, 3, 3])
    after = _counts([0, 0, 0, 0])
    result = recurrence.compute_verdict(before, after, min_sessions=3)
    assert result["verdict"] == recurrence.VERDICT_NOT_EVALUATED
    assert result["verdict"] not in _DIRECTIONAL_LABELS
    assert result["reason"] == recurrence.VERDICT_SUPPRESSION_REASON


def test_verdict_large_increase_does_not_emit_increased():
    """Occurrences 1->3 off a nonzero baseline — a clean 'increased' under
    the old logic. This is exactly the shape of the real grep -n case in
    the module docstring: an 'increased' result off a nonzero baseline can
    be the prescribed replacement working as intended, not a regression —
    the old logic could not tell the two apart, so the label is gone."""
    before = _counts([1, 1, 1, 1])
    after = _counts([3, 3, 3, 3])
    result = recurrence.compute_verdict(before, after, min_sessions=3)
    assert result["verdict"] == recurrence.VERDICT_NOT_EVALUATED
    assert result["verdict"] not in _DIRECTIONAL_LABELS


def test_verdict_zero_baseline_appearance_does_not_emit_increased():
    """occ_before == 0 but occ_after > 0 (not both zero) used to bypass the
    relative-change threshold entirely via a special-cased branch and force
    INCREASED. That branch is removed along with the rest of the
    directional logic: this is not_evaluated (real data exists on the
    'after' side), not insufficient_data (the signature WAS observed, just
    only on one side) and not a directional label."""
    before = _counts([0, 0, 0, 0])
    after = _counts([2, 2, 2, 2])
    result = recurrence.compute_verdict(before, after, min_sessions=3)
    assert result["verdict"] == recurrence.VERDICT_NOT_EVALUATED
    assert result["verdict"] not in _DIRECTIONAL_LABELS


def test_verdict_flat_rate_does_not_emit_unchanged():
    before = _counts([2, 2, 2, 2])
    after = _counts([2, 2, 2, 2])
    result = recurrence.compute_verdict(before, after, min_sessions=3)
    assert result["verdict"] == recurrence.VERDICT_NOT_EVALUATED
    assert result["verdict"] not in _DIRECTIONAL_LABELS


def test_verdict_small_change_does_not_emit_directional_label():
    """The +/-15% threshold comparison is removed entirely, not just its
    default value — even a sub-threshold change (which used to map to
    'unchanged', itself still a directional claim) must not appear."""
    before = _counts([10, 10, 10, 10])
    after = _counts([9, 9, 9, 9])  # was -10% relative change, old threshold was 15%
    result = recurrence.compute_verdict(before, after, min_sessions=3)
    assert result["verdict"] == recurrence.VERDICT_NOT_EVALUATED
    assert result["verdict"] not in _DIRECTIONAL_LABELS


def test_verdict_insufficient_data_too_few_sessions():
    before = _counts([5])
    after = _counts([0])
    result = recurrence.compute_verdict(before, after, min_sessions=3)
    assert result["verdict"] == recurrence.VERDICT_INSUFFICIENT_DATA
    assert result["sessions_before"] == 1
    assert result["sessions_after"] == 1


def test_verdict_insufficient_data_zero_occurrences_both_sides_not_reduced():
    """The critical distinction the brief calls out explicitly: a signature
    that appears zero times on BOTH sides, even with plenty of sessions on
    both sides, is insufficient_data — NOT reduced, nor any other
    directional label (those don't exist any more). We never observed the
    pattern; that's a different claim from "the rule eliminated it"."""
    before = _counts([0, 0, 0, 0, 0])
    after = _counts([0, 0, 0, 0, 0])
    result = recurrence.compute_verdict(before, after, min_sessions=3)
    assert result["verdict"] == recurrence.VERDICT_INSUFFICIENT_DATA
    assert result["sessions_before"] == 5
    assert result["sessions_after"] == 5


def test_verdict_not_evaluable_when_before_side_flagged_unevaluable():
    """The before_side_evaluable escape hatch: when the caller has already
    determined a rule can never be evaluated (e.g. the landing date
    predates the earliest surviving transcript for that repo), the verdict
    must be not_evaluable regardless of what the raw counts look like —
    even counts shaped exactly like the 'large drop' scenario above."""
    before = _counts([3, 3, 3, 3])
    after = _counts([0, 0, 0, 0])
    result = recurrence.compute_verdict(
        before, after, min_sessions=3,
        before_side_evaluable=False,
        not_evaluable_reason="test reason: landed before earliest transcript",
    )
    assert result["verdict"] == recurrence.VERDICT_NOT_EVALUABLE
    assert result["verdict"] not in _DIRECTIONAL_LABELS
    assert result["reason"] == "test reason: landed before earliest transcript"


def test_module_defines_no_directional_verdict_constants():
    """Structural refusal check, not just a behavioral one: the directional
    verdict constants themselves must be gone, so nothing can reintroduce a
    directional label just by referencing an old name that still exists."""
    for name in ("VERDICT_REDUCED", "VERDICT_UNCHANGED", "VERDICT_INCREASED", "VERDICT_THRESHOLD"):
        assert not hasattr(recurrence, name), (
            f"{name} must not exist — directional verdicts are suppressed"
        )


# ---------------------------------------------------------------------------
# DIRECTIONAL VERDICT SUPPRESSION PROOF — build_repo_report's not_evaluable
# determination (repo has zero transcripts, or landing predates the
# earliest surviving one)
# ---------------------------------------------------------------------------

def test_build_repo_report_not_evaluable_when_repo_has_zero_transcripts(tmp_path):
    repo = tmp_path / "repo"
    _init_git_repo(repo)
    (repo / "CLAUDE.md").write_text("# CLAUDE.md\nno rules yet\n")
    _git(repo, "add", "CLAUDE.md")
    _git(repo, "commit", "-q", "-m", "init", date="2026-01-01T00:00:00")

    (repo / "CLAUDE.md").write_text(
        "# CLAUDE.md\n## Headroom Learned Patterns\n### Rule\n"
        "- `zero-transcript-signature` never appears anywhere.\n"
    )
    _git(repo, "add", "CLAUDE.md")
    _git(repo, "commit", "-q", "-m", "add rule", date="2026-02-01T00:00:00")

    # No project directory at all for this repo under projects_dir -> zero
    # surviving transcripts.
    result = recurrence.build_repo_report(
        "notranscripts", repo, projects_dir=tmp_path / "projects", min_sessions=3
    )
    rule = result["rules"][0]
    assert rule["status"] == recurrence.STATUS_OK
    assert rule["verdict"] == recurrence.VERDICT_NOT_EVALUABLE
    assert "zero surviving session transcripts" in rule["reason"]


def test_build_repo_report_not_evaluable_when_landing_predates_earliest_transcript(tmp_path):
    """The 'before' side is permanently, not just currently, empty: the
    only surviving transcript starts AFTER the rule's landing date, so no
    session earlier than the landing date can ever be found — this must be
    not_evaluable, not insufficient_data (which implies more time might
    help)."""
    repo = tmp_path / "repo"
    _init_git_repo(repo)
    (repo / "CLAUDE.md").write_text("# CLAUDE.md\nno rules yet\n")
    _git(repo, "add", "CLAUDE.md")
    _git(repo, "commit", "-q", "-m", "init", date="2026-01-01T00:00:00")

    (repo / "CLAUDE.md").write_text(
        "# CLAUDE.md\n## Headroom Learned Patterns\n### Rule\n"
        "- `old-signature` landed long before any surviving transcript.\n"
    )
    _git(repo, "add", "CLAUDE.md")
    _git(repo, "commit", "-q", "-m", "add rule", date="2026-01-15T00:00:00")

    projects_dir = tmp_path / "projects"
    project_dir = projects_dir / recurrence.encode_project_dir(repo)
    _write_jsonl(project_dir / "sess1.jsonl", [
        _tool_use_row("2026-03-01T00:00:00Z", "Bash", {"command": "run old-signature now"}),
    ])

    result = recurrence.build_repo_report(
        "latetranscripts", repo, projects_dir=projects_dir, min_sessions=1
    )
    rule = result["rules"][0]
    assert rule["status"] == recurrence.STATUS_OK
    assert rule["verdict"] == recurrence.VERDICT_NOT_EVALUABLE
    assert "before the earliest surviving transcript" in rule["reason"]


# ---------------------------------------------------------------------------
# THE CENTRAL REFUSAL PROOF — full build_report() pipeline, end to end
# ---------------------------------------------------------------------------

def test_build_report_end_to_end_emits_zero_directional_verdicts(tmp_path):
    """Same synthetic repo/git/session fixture that used to prove all four
    directional verdicts were reachable end-to-end (renamed rule titles to
    match: each one is exactly the scenario that used to produce
    reduced/increased/unchanged). Now proves the opposite: the full
    pipeline (parse CLAUDE.md -> extract signature -> git landing date ->
    session counts -> verdict) never wires a directional label into its
    output, no matter how clean the underlying before/after signal is —
    not just the isolated compute_verdict function in the tests above."""
    repo = tmp_path / "repo"
    _init_git_repo(repo)

    (repo / "CLAUDE.md").write_text("# CLAUDE.md\nno rules yet\n")
    _git(repo, "add", "CLAUDE.md")
    _git(repo, "commit", "-q", "-m", "init", date="2025-12-01T00:00:00")

    # Commit A: 3 rules land together on 2026-02-01.
    (repo / "CLAUDE.md").write_text(
        "# CLAUDE.md\n"
        "## Headroom Learned Patterns\n"
        "### Rule Would Have Been Reduced\n"
        "- `alpha-cmd` re-run repeatedly; read once.\n"
        "\n"
        "### Rule Would Have Been Increased\n"
        "- `beta-file.md` should be checked less.\n"
        "\n"
        "### Rule Would Have Been Unchanged\n"
        "- `gamma-path` re-read too often.\n"
    )
    _git(repo, "add", "CLAUDE.md")
    _git(repo, "commit", "-q", "-m", "add 3 rules", date="2026-02-01T00:00:00")

    # Commit B: a 4th rule lands very late (2026-03-20), leaving it with no
    # "after" population in the shared session pool below — still
    # insufficient_data, unaffected by verdict suppression.
    (repo / "CLAUDE.md").write_text(
        (repo / "CLAUDE.md").read_text()
        + "\n### Rule Thin\n- `delta-thing` wasteful pattern.\n"
    )
    _git(repo, "add", "CLAUDE.md")
    _git(repo, "commit", "-q", "-m", "add thin rule", date="2026-03-20T00:00:00")

    # Shared session pool: 8 sessions, 2026-01-05 .. 2026-03-15. The
    # earliest of these (2026-01-05) predates every rule's landing date, so
    # none of these rules hit the not_evaluable path — only insufficient_data
    # (Rule Thin, zero "after" sessions) and not_evaluated (the other three).
    projects_dir = tmp_path / "projects"
    project_dir = projects_dir / recurrence.encode_project_dir(repo)
    session_dates = [
        "2026-01-05T00:00:00Z", "2026-01-15T00:00:00Z", "2026-01-25T00:00:00Z",  # before 02-01
        "2026-02-05T00:00:00Z", "2026-02-15T00:00:00Z", "2026-02-25T00:00:00Z",
        "2026-03-05T00:00:00Z", "2026-03-15T00:00:00Z",                          # after 02-01, before 03-20
    ]
    before_dates = session_dates[:3]
    after_dates = session_dates[3:]

    for i, ts in enumerate(before_dates):
        rows = [_tool_use_row(ts, "Bash", {"command": "run alpha-cmd now"})] * 3
        rows += [_tool_use_row(ts, "Read", {"file_path": "gamma-path/x.md"})] * 2
        _write_jsonl(project_dir / f"before{i}.jsonl", rows)

    for i, ts in enumerate(after_dates):
        rows = [_tool_use_row(ts, "Read", {"file_path": "beta-file.md"})] * 2
        rows += [_tool_use_row(ts, "Read", {"file_path": "gamma-path/x.md"})] * 2
        _write_jsonl(project_dir / f"after{i}.jsonl", rows)

    report = recurrence.build_report(
        repos={"synthetic": repo}, projects_dir=projects_dir, min_sessions=3
    )

    by_section = {r["section_title"]: r for r in report["rules"]}
    for title in (
        "Rule Would Have Been Reduced",
        "Rule Would Have Been Increased",
        "Rule Would Have Been Unchanged",
    ):
        rule = by_section[title]
        assert rule["status"] == recurrence.STATUS_OK, title
        assert rule["verdict"] == recurrence.VERDICT_NOT_EVALUATED, title
        assert rule["verdict"] not in _DIRECTIONAL_LABELS, title
        assert rule["reason"] == recurrence.VERDICT_SUPPRESSION_REASON, title

    assert by_section["Rule Thin"]["status"] == recurrence.STATUS_OK
    assert by_section["Rule Thin"]["verdict"] == recurrence.VERDICT_INSUFFICIENT_DATA
    assert by_section["Rule Thin"]["sessions_after"] == 0

    verdict_counts = report["summary"]["verdict_counts"]
    assert verdict_counts[recurrence.VERDICT_NOT_EVALUATED] == 3
    assert verdict_counts[recurrence.VERDICT_INSUFFICIENT_DATA] == 1
    assert verdict_counts[recurrence.VERDICT_NOT_EVALUABLE] == 0
    assert set(verdict_counts) == {
        recurrence.VERDICT_NOT_EVALUATED,
        recurrence.VERDICT_INSUFFICIENT_DATA,
        recurrence.VERDICT_NOT_EVALUABLE,
    }
    assert not _DIRECTIONAL_LABELS & set(verdict_counts)

    # Every rule record carries the observational caveat and trust block,
    # regardless of status — and the trust block now explicitly disclaims
    # BOTH the causal claim and the merely-directional claim as separate,
    # equally not_measured things.
    for r in report["rules"]:
        assert r["observational_caveat"] == recurrence.OBSERVATIONAL_CAVEAT
        assert r["trust"]["causal_attribution"] == "not_measured"
        assert r["trust"]["directional_verdict"] == "not_measured"

    # No rule record anywhere in this report carries a directional verdict.
    assert all(r.get("verdict") not in _DIRECTIONAL_LABELS for r in report["rules"])


# ---------------------------------------------------------------------------
# build_repo_report — gap handling never crashes
# ---------------------------------------------------------------------------

def test_build_repo_report_missing_claude_md_is_a_gap_not_a_crash(tmp_path):
    repo = tmp_path / "no-claude-md-repo"
    repo.mkdir()
    result = recurrence.build_repo_report("ghost", repo, projects_dir=tmp_path / "projects")
    assert result["coverage"]["claude_md_found"] is False
    assert result["rules"] == []


def test_build_repo_report_unparseable_and_no_landing_date_are_reported_not_dropped(tmp_path):
    repo = tmp_path / "repo"
    _init_git_repo(repo)
    (repo / "CLAUDE.md").write_text(
        "# CLAUDE.md\n"
        "## Headroom Learned Patterns\n"
        "### No Signature\n"
        "- this bullet has no backtick span at all.\n"
        "\n"
        "### Never Committed\n"
        "- `phantom-signature-not-in-history` is a thing.\n"
    )
    # Deliberately do NOT commit — so git log finds no history at all for
    # the second rule's signature, exercising STATUS_NO_LANDING_DATE.
    result = recurrence.build_repo_report(
        "gaptest", repo, projects_dir=tmp_path / "projects"
    )
    statuses = {r["section_title"]: r["status"] for r in result["rules"]}
    assert statuses["No Signature"] == recurrence.STATUS_UNPARSEABLE_SIGNATURE
    assert statuses["Never Committed"] == recurrence.STATUS_NO_LANDING_DATE
    # Both rules are present in the output — never silently dropped.
    assert len(result["rules"]) == 2
