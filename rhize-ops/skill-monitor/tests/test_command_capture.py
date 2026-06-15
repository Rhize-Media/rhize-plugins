"""Tests for slash-command capture + channel reconciliation in monitor.py.

Run: python3 -m pytest tests/ -q   (from the repo root)
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import monitor  # noqa: E402

FIXTURE = REPO / "tests" / "fixtures" / "commands.jsonl"


def _command_skills():
    return sorted(e["skill"] for e in monitor.extract_command_events(FIXTURE, "main"))


def _all_events():
    evs = list(monitor.extract_command_events(FIXTURE, "main"))
    evs += list(monitor.extract_skill_events(FIXTURE, "main"))
    return evs


def test_extracts_only_live_real_commands():
    # /sc:reflect and /gsd:execute-phase are live, real commands.
    # /model is a builtin (excluded); /simplify is also a live command.
    # The <command-name> inside the hook_success attachment and the assistant
    # prose echo must BOTH be ignored.
    skills = _command_skills()
    assert skills == ["gsd:execute-phase", "sc:reflect", "simplify"], skills


def test_builtin_is_excluded():
    assert "model" not in _command_skills()


def test_embedded_and_echoed_tags_ignored():
    skills = _command_skills()
    assert "should-not-count" not in skills
    assert "also-not-this" not in skills


def test_channel_tagging():
    cmd = list(monitor.extract_command_events(FIXTURE, "main"))
    assert all(e["channel"] == monitor.CHANNEL_SLASH_COMMAND for e in cmd)
    skl = list(monitor.extract_skill_events(FIXTURE, "main"))
    assert all(e["channel"] == monitor.CHANNEL_SKILL_TOOL for e in skl)


def test_args_captured():
    by_name = {e["skill"]: e for e in monitor.extract_command_events(FIXTURE, "main")}
    assert by_name["gsd:execute-phase"]["args"] == "3"
    assert by_name["simplify"]["args"] is None  # empty <command-args> -> None


def test_reconciliation_no_double_count():
    report = monitor.build_report(_all_events(), since_days=None)
    # sess-B has BOTH /simplify (command) and a simplify tool_use -> count once.
    assert report["overlap_deduped"] == 1
    assert report["total_invocations"] == report["total_raw_invocations"] - 1
    # simplify should appear exactly once (the tool_use), on the skill_tool channel.
    top = dict(report["top_skills"])
    assert top["simplify"] == 1
    # Fixture has exactly one skill_tool event (the simplify tool_use); the
    # overlapping /simplify command was deduped out.
    assert report["by_channel"].get(monitor.CHANNEL_SKILL_TOOL) == 1
    # command-only skills survive on the slash_command channel.
    assert report["by_channel"].get(monitor.CHANNEL_SLASH_COMMAND) == 2  # sc:reflect, gsd:execute-phase


def test_command_only_skills_counted():
    report = monitor.build_report(_all_events(), since_days=None)
    top = dict(report["top_skills"])
    assert top["sc:reflect"] == 1
    assert top["gsd:execute-phase"] == 1
