#!/usr/bin/env python3
"""Unit tests for the Dev Flow control-plane observability added to
rhize-ops/skill-monitor/monitor.py (Task 9 of
.claude/plans/rhize-devflow-v3-engineering-control-plane.md).

Scope, deliberately narrow: these tests exercise the new pure functions
(`build_devflow_control_plane_section`, `extract_devflow_doctor_events`)
directly, in isolation from monitor.py's `main()`. They never invoke `main()`
— doing so would scan the real ~/.claude/projects tree and trigger
`git_sync.commit_and_push_snapshots()`, which is out of scope for a unit test
and would violate rhize-ops/skill-monitor/CLAUDE.md's "don't push from an
interactive/agent session" constraint.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[2]
MONITOR_DIR = REPO_ROOT / "rhize-ops" / "skill-monitor"
MONITOR_PATH = MONITOR_DIR / "monitor.py"

# monitor.py does `import git_sync` (a same-directory sibling module) assuming
# it runs as a script with its own directory on sys.path. Loading it here via
# importlib (like tests/test_bump_version.py does for bump_version.py) needs
# that directory on sys.path too, or the sibling import fails at exec time.
sys.path.insert(0, str(MONITOR_DIR))

_spec = importlib.util.spec_from_file_location("skill_monitor", MONITOR_PATH)
monitor = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(monitor)  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# build_devflow_control_plane_section
# ---------------------------------------------------------------------------


def test_deprecated_and_canonical_commands_with_no_telemetry_report_no_data() -> None:
    totals: Counter = Counter()
    section = monitor.build_devflow_control_plane_section(totals, doctor_events=[])

    for old_name in monitor.DEVFLOW_DEPRECATED_TO_CANONICAL:
        assert section["deprecated"][old_name]["invocations"] == "no data", (
            f"{old_name} should report 'no data', not zero, when unobserved"
        )
    for count in section["canonical"].values():
        assert count == "no data"
    assert section["doctor"]["invocations"] == "no data"
    assert section["doctor"]["healthy"] == 0
    assert section["doctor"]["degraded"] == 0
    assert section["doctor"]["unknown_outcome"] == 0


def test_observed_counts_are_reported_verbatim_not_as_no_data() -> None:
    totals: Counter = Counter(
        {
            "rhize-devflow:browser-debug": 3,
            "rhize-devflow:browser-qa": 5,
            "rhize-devflow:mutation-analyze": 0,  # a Counter can hold an explicit 0
        }
    )
    section = monitor.build_devflow_control_plane_section(totals, doctor_events=[])

    assert section["deprecated"]["rhize-devflow:browser-debug"]["invocations"] == 3
    assert section["deprecated"]["rhize-devflow:browser-debug"]["canonical"] == "rhize-devflow:browser-qa"
    assert section["canonical"]["rhize-devflow:browser-qa"] == 5
    # An explicit zero recorded by the Counter is real data, not "no data" —
    # only genuine absence (key never counted) collapses to "no data".
    assert section["deprecated"]["rhize-devflow:mutation-analyze"]["invocations"] == 0


def test_mutation_check_canonical_lookup_strips_the_flag_suffix() -> None:
    """DEVFLOW_DEPRECATED_TO_CANONICAL maps mutation-analyze/-fix to
    'rhize-devflow:mutation-check --all'/'--fix-plan' (the flag distinguishes
    the deprecated adapter's mode) — but invocation counts are keyed by the
    bare command name, so the canonical lookup must strip the suffix before
    consulting `totals`."""
    totals: Counter = Counter({"rhize-devflow:mutation-check": 7})
    section = monitor.build_devflow_control_plane_section(totals, doctor_events=[])

    assert section["canonical"]["rhize-devflow:mutation-check --all"] == 7
    assert section["canonical"]["rhize-devflow:mutation-check --fix-plan"] == 7


def test_doctor_summary_tallies_healthy_degraded_and_unknown() -> None:
    doctor_events = [
        {"healthy": True},
        {"healthy": True},
        {"healthy": False},
        {"healthy": None},
    ]
    section = monitor.build_devflow_control_plane_section(Counter(), doctor_events)

    assert section["doctor"]["invocations"] == 4
    assert section["doctor"]["healthy"] == 2
    assert section["doctor"]["degraded"] == 1
    assert section["doctor"]["unknown_outcome"] == 1


# ---------------------------------------------------------------------------
# extract_devflow_doctor_events
# ---------------------------------------------------------------------------


def _write_jsonl(path: Path, lines: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")


def test_extractor_matches_tool_use_to_its_tool_result_and_reads_healthy_flag() -> None:
    with TemporaryDirectory() as tmp:
        project_dir = Path(tmp) / "-some-project"
        project_dir.mkdir()
        jsonl_path = project_dir / "session.jsonl"
        _write_jsonl(
            jsonl_path,
            [
                {
                    "type": "assistant",
                    "sessionId": "s1",
                    "timestamp": "2026-08-01T00:00:00Z",
                    "message": {
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "toolu_1",
                                "name": "Bash",
                                "input": {"command": "python3 rhize-devflow/scripts/devflow.py doctor --json"},
                            }
                        ]
                    },
                },
                {
                    "type": "user",
                    "sessionId": "s1",
                    "timestamp": "2026-08-01T00:00:01Z",
                    "message": {
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": "toolu_1",
                                "content": [
                                    {"type": "text", "text": '{\n  "healthy": false\n}'}
                                ],
                            }
                        ]
                    },
                },
            ],
        )

        events = list(monitor.extract_devflow_doctor_events(jsonl_path, "main"))

    assert len(events) == 1
    assert events[0]["healthy"] is False
    assert events[0]["channel"] == "devflow_doctor"
    # Redaction: no raw command text, no absolute path beyond what the report
    # already carries via project_dir_decoded (same convention as every other
    # extractor in this file).
    assert "command" not in events[0]
    assert "cwd" not in events[0]


def test_extractor_ignores_bash_calls_that_are_not_devflow_doctor() -> None:
    with TemporaryDirectory() as tmp:
        project_dir = Path(tmp) / "-some-project"
        project_dir.mkdir()
        jsonl_path = project_dir / "session.jsonl"
        _write_jsonl(
            jsonl_path,
            [
                {
                    "type": "assistant",
                    "sessionId": "s1",
                    "timestamp": "2026-08-01T00:00:00Z",
                    "message": {
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "toolu_1",
                                "name": "Bash",
                                "input": {"command": "git status"},
                            }
                        ]
                    },
                },
            ],
        )

        events = list(monitor.extract_devflow_doctor_events(jsonl_path, "main"))

    assert events == []


def test_extractor_reports_unknown_outcome_when_no_tool_result_is_found() -> None:
    with TemporaryDirectory() as tmp:
        project_dir = Path(tmp) / "-some-project"
        project_dir.mkdir()
        jsonl_path = project_dir / "session.jsonl"
        _write_jsonl(
            jsonl_path,
            [
                {
                    "type": "assistant",
                    "sessionId": "s1",
                    "timestamp": "2026-08-01T00:00:00Z",
                    "message": {
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "toolu_1",
                                "name": "Bash",
                                "input": {"command": "python3 devflow.py doctor"},
                            }
                        ]
                    },
                },
            ],
        )

        events = list(monitor.extract_devflow_doctor_events(jsonl_path, "main"))

    assert len(events) == 1
    assert events[0]["healthy"] is None  # unknown outcome, never assumed healthy


if __name__ == "__main__":
    import sys

    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
