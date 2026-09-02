"""test_suggestion_report.py — tests for the relocated
rhize-context-manager/scripts/suggestion_log_report.py (moved from repo-root
scripts/ 2026-09-02, R3 task 8 of the portability-readiness plan) and its
root-level compatibility shim.

Covers:
  1. The plugin copy runs standalone against a tmp suggestion-log fixture and
     produces the expected per-hook counts and agent-dispatch stats.
  2. The root shim (`scripts/suggestion_log_report.py`) produces byte-identical
     stdout to the plugin copy for the same arguments — both in `--json` mode
     and in the default human-readable table — proving the shim forwards
     correctly rather than reimplementing or drifting from the moved script.

Uses pytest (matches this directory's other test, test_skill_evals.py), unlike
the plain-script style used under tests/skill-map/.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_SCRIPT = REPO_ROOT / "rhize-context-manager" / "scripts" / "suggestion_log_report.py"
SHIM_SCRIPT = REPO_ROOT / "scripts" / "suggestion_log_report.py"

FIXTURE_ROWS = [
    {
        "ts": "2026-09-02T00:00:00Z",
        "session_id": "sessA",
        "hook": "router",
        "suggested": "skill:rhize-context-manager/graphify",
        "context_hash": "aaaa1111",
    },
    {
        "ts": "2026-09-02T00:01:00Z",
        "session_id": None,
        "hook": "router",
        "suggested": None,
        "context_hash": "bbbb2222",
    },
    {
        "ts": "2026-09-02T00:02:00Z",
        "source": "agent-dispatch",
        "agentType": "executor",
        "briefHash": "c1c1c1c1c1c1c1c1",
        "briefLength": 100,
        "namedSkills": ["skill:rhize-context-manager/graphify"],
        "suggestedSkills": ["skill:rhize-context-manager/graphify"],
        "advisoryEmitted": False,
    },
]


def _write_fixture(path: Path) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for row in FIXTURE_ROWS:
            fh.write(json.dumps(row) + "\n")


def _run(script: Path, log_path: Path, usage_path: Path, *extra_args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            str(script),
            "--log-path",
            str(log_path),
            "--usage-path",
            str(usage_path),
            *extra_args,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def test_plugin_copy_reports_expected_counts(tmp_path: Path) -> None:
    log_path = tmp_path / "suggestion-log.jsonl"
    usage_path = tmp_path / "no-skill-usage.json"  # missing on purpose — degrades cleanly
    _write_fixture(log_path)

    result = _run(PLUGIN_SCRIPT, log_path, usage_path, "--json")
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"

    report = json.loads(result.stdout)
    router_stats = report["per_hook"]["router"]
    assert router_stats["suggestions"] == 1
    assert router_stats["accepted"] == 0  # no skill-usage data to join against
    assert router_stats["ignored"] == 1
    assert report["router_silence_samples"] == 1  # the suggested:null row

    ad = report["agent_dispatch"]
    assert ad["total"] == 1
    assert ad["named_rate"] == 1.0
    assert ad["candidate_present"] == 1
    assert ad["candidate_miss_rate"] == 0.0  # named skill matches the suggested one


def test_root_shim_forwards_to_plugin_copy_identically(tmp_path: Path) -> None:
    log_path = tmp_path / "suggestion-log.jsonl"
    usage_path = tmp_path / "no-skill-usage.json"
    _write_fixture(log_path)

    plugin_json = _run(PLUGIN_SCRIPT, log_path, usage_path, "--json")
    shim_json = _run(SHIM_SCRIPT, log_path, usage_path, "--json")
    assert shim_json.returncode == plugin_json.returncode == 0
    assert shim_json.stdout == plugin_json.stdout

    plugin_table = _run(PLUGIN_SCRIPT, log_path, usage_path)
    shim_table = _run(SHIM_SCRIPT, log_path, usage_path)
    assert shim_table.returncode == plugin_table.returncode == 0
    assert shim_table.stdout == plugin_table.stdout
    assert shim_table.stdout != ""
