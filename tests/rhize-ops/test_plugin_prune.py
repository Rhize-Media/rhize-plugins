"""Tests for rhize-ops/scripts/plugin_prune.py — the report-first plugin-prune
advisor that reads a skill-forge `audit --claude-plugins`/`routine` JSON
report (schemaVersion 1, a `plugins` array) plus optional skill-monitor
snapshots, cross-references `~/.claude/settings.json`'s `enabledPlugins`, and
only ever disables a plugin via `claude plugin disable <id> --scope user`
behind an explicit `--apply --disable <id>` + typed "yes" confirmation.

No test ever invokes the real `claude` binary: `--apply` tests point
PLUGIN_PRUNE_CLAUDE_BIN at fixtures/plugin_prune/fake_claude.sh, which
records its argv to a file instead of doing anything real.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "rhize-ops" / "scripts" / "plugin_prune.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "plugin_prune"
AUDIT_FIXTURE = FIXTURES / "audit.json"
SETTINGS_FIXTURE = FIXTURES / "settings.json"
FAKE_CLAUDE = FIXTURES / "fake_claude.sh"

SPEC = importlib.util.spec_from_file_location("plugin_prune", SCRIPT)
plugin_prune = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(plugin_prune)


def run(argv: list[str], capsys) -> tuple[int, str, str]:
    code = plugin_prune.main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def write_json(path: Path, data: dict) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def base_audit(plugins: list[dict]) -> dict:
    return {"schemaVersion": 1, "plugins": plugins}


def plugin_entry(plugin_id: str, recommendation: str = "keep", **overrides) -> dict:
    entry = {
        "pluginId": plugin_id,
        "version": "1.0.0",
        "installPath": f"/fake/{plugin_id}",
        "skillCount": 1,
        "findingCounts": {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0},
        "recommendation": recommendation,
        "reasons": [],
    }
    entry.update(overrides)
    return entry


# ---------------------------------------------------------------------------
# Basic report: table, JSON, exit codes
# ---------------------------------------------------------------------------

def test_table_from_fixture_audit_json(capsys):
    code, out, err = run(
        ["--audit", str(AUDIT_FIXTURE), "--settings", str(SETTINGS_FIXTURE)], capsys
    )
    assert err == ""
    assert "code-review@claude-plugins-official" in out
    assert "stale-plugin@claude-plugins-official" in out
    assert "risky-plugin@claude-plugins-official" in out
    assert "keep" in out
    assert "unobserved" in out
    assert "review" in out
    # risky-plugin is "review" -> nonzero exit for cron alerting.
    assert code == 1


def test_exit_code_0_when_every_plugin_is_clean(tmp_path, capsys):
    audit = write_json(
        tmp_path / "audit.json",
        base_audit([plugin_entry("clean@claude-plugins-official", "keep")]),
    )
    settings = write_json(
        tmp_path / "settings.json",
        {"enabledPlugins": {"clean@claude-plugins-official": True}},
    )
    code, out, err = run(["--audit", str(audit), "--settings", str(settings)], capsys)
    assert code == 0
    assert "clean@claude-plugins-official" in out


def test_exit_code_1_when_a_plugin_is_review(tmp_path, capsys):
    audit = write_json(
        tmp_path / "audit.json",
        base_audit([plugin_entry("risky@claude-plugins-official", "review")]),
    )
    settings = write_json(
        tmp_path / "settings.json",
        {"enabledPlugins": {"risky@claude-plugins-official": True}},
    )
    code, _, _ = run(["--audit", str(audit), "--settings", str(settings)], capsys)
    assert code == 1


def test_json_output_is_one_document(capsys):
    code, out, err = run(
        ["--audit", str(AUDIT_FIXTURE), "--settings", str(SETTINGS_FIXTURE), "--json"],
        capsys,
    )
    payload = json.loads(out)
    assert payload["schema"] == "rhize-plugin-prune-v1"
    ids = {row["pluginId"] for row in payload["plugins"]}
    assert ids == {
        "code-review@claude-plugins-official",
        "stale-plugin@claude-plugins-official",
        "risky-plugin@claude-plugins-official",
        "unregistered-plugin@some-marketplace",
    }
    assert code == 1


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

def test_refuses_audit_json_without_plugins_array(tmp_path, capsys):
    audit = write_json(tmp_path / "audit.json", {"schemaVersion": 1})
    code, out, err = run(["--audit", str(audit)], capsys)
    assert code == 2
    assert out == ""
    assert "plugins" in err


def test_refuses_unknown_schema_version(tmp_path, capsys):
    audit = write_json(tmp_path / "audit.json", {"schemaVersion": 2, "plugins": []})
    code, out, err = run(["--audit", str(audit)], capsys)
    assert code == 2
    assert "schemaVersion" in err


def test_refuses_malformed_json(tmp_path, capsys):
    audit = tmp_path / "audit.json"
    audit.write_text("{not json", encoding="utf-8")
    code, out, err = run(["--audit", str(audit)], capsys)
    assert code == 2
    assert out == ""


def test_refuses_missing_audit_file(tmp_path, capsys):
    code, out, err = run(["--audit", str(tmp_path / "missing.json")], capsys)
    assert code == 2
    assert out == ""


def test_a_string_reasons_field_does_not_iterate_into_characters(tmp_path, capsys):
    # A malformed/attacker-influenced audit could put a bare string where
    # "reasons" should be a list — iterating that naively would silently
    # produce one "reason" per character.
    audit = write_json(
        tmp_path / "audit.json",
        base_audit([plugin_entry("odd@claude-plugins-official", "keep", reasons="oops")]),
    )
    settings = write_json(
        tmp_path / "settings.json", {"enabledPlugins": {"odd@claude-plugins-official": True}}
    )
    code, out, err = run(["--audit", str(audit), "--settings", str(settings), "--json"], capsys)
    payload = json.loads(out)
    row = next(r for r in payload["plugins"] if r["pluginId"] == "odd@claude-plugins-official")
    assert row["reasons"] == []


def test_weeks_without_snapshots_still_errors_as_paired_flag(tmp_path, capsys):
    audit = write_json(tmp_path / "audit.json", base_audit([]))
    code, out, err = run(["--audit", str(audit), "--weeks", "4"], capsys)
    assert code == 2
    assert "--snapshots" in err


def test_weeks_zero_is_rejected(tmp_path, capsys):
    audit = write_json(tmp_path / "audit.json", base_audit([]))
    snapshots = tmp_path / "snapshots"
    snapshots.mkdir()
    code, out, err = run(
        ["--audit", str(audit), "--snapshots", str(snapshots), "--weeks", "0"], capsys
    )
    assert code == 2
    assert "--weeks" in err


# ---------------------------------------------------------------------------
# Settings cross-reference
# ---------------------------------------------------------------------------

def test_id_absent_from_enabled_plugins_is_flagged_not_actionable(capsys):
    code, out, err = run(
        ["--audit", str(AUDIT_FIXTURE), "--settings", str(SETTINGS_FIXTURE), "--json"],
        capsys,
    )
    payload = json.loads(out)
    row = next(
        r for r in payload["plugins"] if r["pluginId"] == "unregistered-plugin@some-marketplace"
    )
    assert row["settingsStatus"] == "unknown"
    assert row["settingsStatus"] == "unknown"
    assert any("not actionable" in note for note in row["notes"])
    # This script's own cross-reference note stays out of the audit's own
    # `reasons` (kept a pure passthrough of skill-forge's reasoning).
    assert row["reasons"] == ["no usage telemetry"]

    # Also visible in the default table, not just --json.
    code, out, _ = run(["--audit", str(AUDIT_FIXTURE), "--settings", str(SETTINGS_FIXTURE)], capsys)
    assert "not actionable" in out


def test_enabled_id_is_actionable(capsys):
    code, out, err = run(
        ["--audit", str(AUDIT_FIXTURE), "--settings", str(SETTINGS_FIXTURE), "--json"],
        capsys,
    )
    payload = json.loads(out)
    row = next(r for r in payload["plugins"] if r["pluginId"] == "code-review@claude-plugins-official")
    assert row["settingsStatus"] == "enabled"
    assert row["settingsStatus"] == "enabled"
    assert row["notes"] == []


# ---------------------------------------------------------------------------
# --apply / --disable
# ---------------------------------------------------------------------------

def test_apply_without_disable_exits_2(capsys):
    code, out, err = run(
        ["--audit", str(AUDIT_FIXTURE), "--settings", str(SETTINGS_FIXTURE), "--apply"], capsys
    )
    assert code == 2
    assert "--disable" in err


def test_apply_non_tty_exits_2_and_runs_no_subprocess(monkeypatch, tmp_path, capsys):
    log = tmp_path / "claude-argv.log"
    monkeypatch.setenv("PLUGIN_PRUNE_CLAUDE_BIN", str(FAKE_CLAUDE))
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(log))
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)

    code, out, err = run(
        [
            "--audit", str(AUDIT_FIXTURE), "--settings", str(SETTINGS_FIXTURE),
            "--apply", "--disable", "code-review@claude-plugins-official",
        ],
        capsys,
    )

    assert code == 2
    assert "interactive terminal" in err
    assert not log.exists()


def test_apply_disable_requires_id_present_in_audit(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("PLUGIN_PRUNE_CLAUDE_BIN", str(FAKE_CLAUDE))
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(tmp_path / "claude-argv.log"))
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)

    code, out, err = run(
        [
            "--audit", str(AUDIT_FIXTURE), "--settings", str(SETTINGS_FIXTURE),
            "--apply", "--disable", "not-in-audit@claude-plugins-official",
        ],
        capsys,
    )
    assert code == 2
    assert "not-in-audit@claude-plugins-official" in err


def test_apply_disable_requires_id_enabled_in_settings(monkeypatch, tmp_path, capsys):
    # unregistered-plugin@some-marketplace is in the audit but absent from
    # settings.json's enabledPlugins -> not actionable, so --apply refuses it.
    monkeypatch.setenv("PLUGIN_PRUNE_CLAUDE_BIN", str(FAKE_CLAUDE))
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(tmp_path / "claude-argv.log"))
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)

    code, out, err = run(
        [
            "--audit", str(AUDIT_FIXTURE), "--settings", str(SETTINGS_FIXTURE),
            "--apply", "--disable", "unregistered-plugin@some-marketplace",
        ],
        capsys,
    )
    assert code == 2
    assert "unregistered-plugin@some-marketplace" in err


def test_apply_disable_invokes_claude_once_after_typed_yes(monkeypatch, tmp_path, capsys):
    log = tmp_path / "claude-argv.log"
    monkeypatch.setenv("PLUGIN_PRUNE_CLAUDE_BIN", str(FAKE_CLAUDE))
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(log))
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": "yes")

    code, out, err = run(
        [
            "--audit", str(AUDIT_FIXTURE), "--settings", str(SETTINGS_FIXTURE),
            "--apply", "--disable", "code-review@claude-plugins-official",
        ],
        capsys,
    )

    assert code == 0, err
    assert log.exists()
    lines = log.read_text(encoding="utf-8").splitlines()
    assert lines == ["plugin disable code-review@claude-plugins-official --scope user"]


def test_apply_disable_does_nothing_after_no(monkeypatch, tmp_path, capsys):
    log = tmp_path / "claude-argv.log"
    monkeypatch.setenv("PLUGIN_PRUNE_CLAUDE_BIN", str(FAKE_CLAUDE))
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(log))
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": "no")

    code, out, err = run(
        [
            "--audit", str(AUDIT_FIXTURE), "--settings", str(SETTINGS_FIXTURE),
            "--apply", "--disable", "code-review@claude-plugins-official",
        ],
        capsys,
    )

    assert code == 0, err
    assert not log.exists()


def test_apply_disable_reports_nonzero_subprocess_exit_and_continues(monkeypatch, tmp_path, capsys):
    log = tmp_path / "claude-argv.log"
    monkeypatch.setenv("PLUGIN_PRUNE_CLAUDE_BIN", str(FAKE_CLAUDE))
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(log))
    monkeypatch.setenv("FAKE_CLAUDE_EXIT", "1")
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": "yes")

    code, out, err = run(
        [
            "--audit", str(AUDIT_FIXTURE), "--settings", str(SETTINGS_FIXTURE),
            "--apply",
            "--disable", "code-review@claude-plugins-official",
            "--disable", "risky-plugin@claude-plugins-official",
        ],
        capsys,
    )

    # Both ids still get a confirmation attempt even though the first failed.
    lines = log.read_text(encoding="utf-8").splitlines()
    assert lines == [
        "plugin disable code-review@claude-plugins-official --scope user",
        "plugin disable risky-plugin@claude-plugins-official --scope user",
    ]
    assert "code-review@claude-plugins-official" in err


# ---------------------------------------------------------------------------
# Snapshots / weeks-unobserved
# ---------------------------------------------------------------------------

def _write_snapshot(
    path: Path, generated_at: str, usage_keys: list[str], *, exhaustive: bool = True
) -> None:
    totals = {key: 1 for key in usage_keys}
    report: dict = {
        "generated_at": generated_at,
        "window_days": 7,
        "unique_skills_used": len(usage_keys),
    }
    if exhaustive:
        report["skill_totals"] = totals
        report["top_skills"] = list(totals.items())
    else:
        # Capped top_skills only, shorter than unique_skills_used -> not exhaustive.
        report["top_skills"] = list(totals.items())[:0]
    path.write_text(json.dumps({"report": report}), encoding="utf-8")


def test_weeks_unobserved_counts_only_exhaustive_snapshots_selected_by_generated_at(
    tmp_path, capsys
):
    audit = write_json(
        tmp_path / "audit.json",
        base_audit(
            [
                plugin_entry("observed@claude-plugins-official", "keep"),
                plugin_entry("silent@claude-plugins-official", "unobserved"),
            ]
        ),
    )
    settings = write_json(
        tmp_path / "settings.json",
        {
            "enabledPlugins": {
                "observed@claude-plugins-official": True,
                "silent@claude-plugins-official": True,
            }
        },
    )
    snapshots = tmp_path / "snapshots"
    snapshots.mkdir()

    # Three snapshots, by generated_at newest-first: capped (non-exhaustive),
    # newer (exhaustive, "silent" NOT observed), older (exhaustive, "silent"
    # IS observed). With --weeks 2 the CORRECT selection (by generated_at) is
    # [capped, newer] -> capped skipped as non-exhaustive -> exactly 1
    # exhaustive snapshot considered (newer), where "silent" is unobserved.
    #
    # mtimes are set to the OPPOSITE order (older has the newest mtime, newer
    # has the oldest) so a selection bug that sorted by mtime instead would
    # pick [older, capped] instead -> "silent" WOULD be observed there,
    # flipping weeksUnobserved from 1 to 0. This is the behavioral difference
    # a mtime-based regression would actually change, not just a value that
    # happens to be identical either way.
    older = snapshots / "a-older.json"
    newer = snapshots / "b-newer.json"
    capped = snapshots / "c-capped.json"
    _write_snapshot(older, "2026-08-01T00:00:00Z", ["observed:some-skill", "silent:foo"])
    _write_snapshot(newer, "2026-08-08T00:00:00Z", ["observed:some-skill"])
    _write_snapshot(capped, "2026-08-15T00:00:00Z", ["observed:some-skill"], exhaustive=False)

    now = time.time()
    os.utime(newer, (now - 2000, now - 2000))   # oldest mtime
    os.utime(capped, (now - 1000, now - 1000))  # middle mtime
    os.utime(older, (now, now))                  # newest mtime

    code, out, err = run(
        [
            "--audit", str(audit), "--settings", str(settings),
            "--snapshots", str(snapshots), "--weeks", "2", "--json",
        ],
        capsys,
    )
    payload = json.loads(out)
    assert payload["snapshots"]["selected"] == 2
    assert payload["snapshots"]["skippedNonExhaustive"] == 1
    assert payload["snapshots"]["weeksConsidered"] == 1

    rows = {row["pluginId"]: row for row in payload["plugins"]}
    assert rows["observed@claude-plugins-official"]["weeksTotal"] == 1
    assert rows["observed@claude-plugins-official"]["weeksUnobserved"] == 0
    assert rows["silent@claude-plugins-official"]["weeksTotal"] == 1
    assert rows["silent@claude-plugins-official"]["weeksUnobserved"] == 1



def test_exhaustiveness_inferred_from_top_skills_length_without_skill_totals(tmp_path, capsys):
    # No `skill_totals` key at all — exhaustiveness must be inferred purely
    # from len(top_skills) == unique_skills_used (the pre-skill_totals case).
    audit = write_json(
        tmp_path / "audit.json",
        base_audit([plugin_entry("observed@claude-plugins-official", "keep")]),
    )
    settings = write_json(
        tmp_path / "settings.json",
        {"enabledPlugins": {"observed@claude-plugins-official": True}},
    )
    snapshots = tmp_path / "snapshots"
    snapshots.mkdir()
    report = {
        "generated_at": "2026-08-01T00:00:00Z",
        "unique_skills_used": 1,
        "top_skills": [["observed:some-skill", 3]],
        # deliberately no "skill_totals"
    }
    (snapshots / "only.json").write_text(json.dumps({"report": report}), encoding="utf-8")

    code, out, err = run(
        [
            "--audit", str(audit), "--settings", str(settings),
            "--snapshots", str(snapshots), "--weeks", "1", "--json",
        ],
        capsys,
    )
    payload = json.loads(out)
    assert payload["snapshots"]["skippedNonExhaustive"] == 0
    assert payload["snapshots"]["weeksConsidered"] == 1
    row = next(r for r in payload["plugins"] if r["pluginId"] == "observed@claude-plugins-official")
    assert row["weeksUnobserved"] == 0


def test_mixed_naive_and_aware_generated_at_does_not_crash_selection(tmp_path, capsys):
    audit = write_json(tmp_path / "audit.json", base_audit([plugin_entry("x@y", "keep")]))
    settings = write_json(tmp_path / "settings.json", {"enabledPlugins": {"x@y": True}})
    snapshots = tmp_path / "snapshots"
    snapshots.mkdir()
    # Aware (has a "Z" offset) and naive (no offset) generated_at in the same
    # directory must not raise when compared against each other during sort.
    _write_snapshot(snapshots / "aware.json", "2026-08-08T00:00:00Z", ["x:some-skill"])
    _write_snapshot(snapshots / "naive.json", "2026-08-01T00:00:00", ["x:some-skill"])

    code, out, err = run(
        [
            "--audit", str(audit), "--settings", str(settings),
            "--snapshots", str(snapshots), "--weeks", "2", "--json",
        ],
        capsys,
    )
    assert code in (0, 1), err
    payload = json.loads(out)
    assert payload["snapshots"]["selected"] == 2


def test_non_string_plugin_id_with_snapshots_does_not_crash(tmp_path, capsys):
    # A malformed audit entry (pluginId is a number, not a string) must not
    # crash weeks-unobserved computation, which splits pluginId on "@".
    audit = write_json(tmp_path / "audit.json", base_audit([plugin_entry("x@y", "keep")]))
    audit_data = json.loads(audit.read_text(encoding="utf-8"))
    audit_data["plugins"][0]["pluginId"] = 12345
    write_json(audit, audit_data)
    settings = write_json(tmp_path / "settings.json", {"enabledPlugins": {}})
    snapshots = tmp_path / "snapshots"
    snapshots.mkdir()
    _write_snapshot(snapshots / "only.json", "2026-08-08T00:00:00Z", ["x:some-skill"])

    code, out, err = run(
        [
            "--audit", str(audit), "--settings", str(settings),
            "--snapshots", str(snapshots), "--weeks", "1", "--json",
        ],
        capsys,
    )
    assert code in (0, 1), err
    payload = json.loads(out)
    assert payload["plugins"][0]["pluginId"] == "12345"


def test_no_snapshots_flag_means_weeks_fields_are_null(capsys):
    code, out, err = run(
        ["--audit", str(AUDIT_FIXTURE), "--settings", str(SETTINGS_FIXTURE), "--json"], capsys
    )
    payload = json.loads(out)
    for row in payload["plugins"]:
        assert row["weeksUnobserved"] is None
        assert row["weeksTotal"] is None
    assert "snapshots" not in payload


# ---------------------------------------------------------------------------
# Control-character stripping
# ---------------------------------------------------------------------------

def test_control_characters_are_stripped_from_output(tmp_path, capsys):
    dirty_id = "dirty\x1b[31m@claude-plugins-official"
    audit = write_json(
        tmp_path / "audit.json",
        base_audit(
            [
                plugin_entry(
                    dirty_id,
                    "keep",
                    reasons=["fine\x07 reason"],
                )
            ]
        ),
    )
    settings = write_json(tmp_path / "settings.json", {"enabledPlugins": {dirty_id: True}})

    code, out, err = run(["--audit", str(audit), "--settings", str(settings)], capsys)
    assert "\x1b" not in out
    assert "\x07" not in out
    assert "dirty" in out and "claude-plugins-official" in out


def test_control_characters_stripped_from_nested_finding_counts_too(tmp_path, capsys):
    # sanitize_json_value must recurse into nested dicts (findingCounts), not
    # just the top-level pluginId/version/recommendation/reasons fields.
    audit = write_json(
        tmp_path / "audit.json",
        base_audit(
            [
                plugin_entry(
                    "x@y",
                    "keep",
                    findingCounts={"LOW": 0, "MEDIUM": 0, "HIGH": "0\x1b[31m", "CRITICAL": 0},
                )
            ]
        ),
    )
    settings = write_json(tmp_path / "settings.json", {"enabledPlugins": {"x@y": True}})
    code, out, err = run(["--audit", str(audit), "--settings", str(settings), "--json"], capsys)
    assert "\x1b" not in out


def test_bidi_and_zero_width_characters_are_stripped(tmp_path, capsys):
    # A RIGHT-TO-LEFT OVERRIDE or zero-width space in `reasons` could visually
    # rewrite the table a human reads before typing `yes`.
    audit = write_json(
        tmp_path / "audit.json",
        base_audit([plugin_entry("x@y", "keep", reasons=["safe\u202eknip\u200bfoo"])]),
    )
    settings = write_json(tmp_path / "settings.json", {"enabledPlugins": {"x@y": True}})

    code, out, err = run(["--audit", str(audit), "--settings", str(settings), "--json"], capsys)

    assert code == 0
    assert "\u202e" not in out and "\u200b" not in out
    assert "safeknipfoo" in out


def test_apply_rejects_flag_shaped_id_without_spawning(monkeypatch, tmp_path, capsys):
    log = tmp_path / "claude-argv.log"
    monkeypatch.setenv("PLUGIN_PRUNE_CLAUDE_BIN", str(FAKE_CLAUDE))
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(log))
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)

    code, out, err = run(
        # argparse already refuses a bare `--disable -h`; `--disable=-h` is the form that
        # reaches the script's own validation.
        ["--audit", str(AUDIT_FIXTURE), "--settings", str(SETTINGS_FIXTURE), "--apply", "--disable=-h"],
        capsys,
    )

    assert code == 2
    assert "not a valid plugin id" in err
    assert not log.exists()


def _snapshot(path: Path, generated_at: str, **report) -> Path:
    return write_json(path, {"report": {"generated_at": generated_at, "window_days": 7, **report}})


def test_empty_snapshot_is_not_exhaustive_evidence(tmp_path, capsys):
    snaps = tmp_path / "snaps"
    snaps.mkdir()
    _snapshot(snaps / "a.json", "2026-09-01T00:00:00+00:00", unique_skills_used=1, top_skills=[["realplug:foo", 5]])
    _snapshot(snaps / "b.json", "2026-09-02T00:00:00+00:00", unique_skills_used=0, top_skills=[])
    _snapshot(snaps / "c.json", "2026-09-03T00:00:00+00:00", skill_totals={})
    audit = write_json(tmp_path / "audit.json", base_audit([plugin_entry("realplug@mkt", "keep", skillCount=3)]))
    settings = write_json(tmp_path / "settings.json", {"enabledPlugins": {"realplug@mkt": True}})

    code, out, err = run(
        ["--audit", str(audit), "--settings", str(settings), "--snapshots", str(snaps), "--weeks", "3", "--json"],
        capsys,
    )

    doc = json.loads(out)
    row = doc["rows"][0] if "rows" in doc else doc["plugins"][0]
    assert row["weeksTotal"] == 1 and row["weeksUnobserved"] == 0
    assert doc["snapshots"]["skippedNonExhaustive"] == 2


def test_zero_skill_plugin_and_zero_week_window_report_no_dormancy_number(tmp_path, capsys):
    snaps = tmp_path / "snaps"
    snaps.mkdir()
    _snapshot(snaps / "a.json", "2026-09-01T00:00:00+00:00", unique_skills_used=1, top_skills=[["realplug:foo", 5]])
    audit = write_json(
        tmp_path / "audit.json",
        base_audit([plugin_entry("cmdonly@mkt", "unknown", skillCount=0), plugin_entry("realplug@mkt", "keep", skillCount=3)]),
    )
    settings = write_json(tmp_path / "settings.json", {"enabledPlugins": {"cmdonly@mkt": True, "realplug@mkt": True}})

    code, out, err = run(
        ["--audit", str(audit), "--settings", str(settings), "--snapshots", str(snaps), "--weeks", "1", "--json"],
        capsys,
    )
    doc = json.loads(out)
    rows = {r["pluginId"]: r for r in (doc["rows"] if "rows" in doc else doc["plugins"])}
    assert rows["cmdonly@mkt"]["weeksTotal"] is None and rows["cmdonly@mkt"]["weeksUnobserved"] is None
    assert rows["realplug@mkt"]["weeksTotal"] == 1

    # A window with no exhaustive snapshot at all yields no numbers either.
    _snapshot(snaps / "a.json", "2026-09-01T00:00:00+00:00", unique_skills_used=5, top_skills=[["x:y", 1]])
    code, out, err = run(
        ["--audit", str(audit), "--settings", str(settings), "--snapshots", str(snaps), "--weeks", "1", "--json"],
        capsys,
    )
    doc = json.loads(out)
    rows = {r["pluginId"]: r for r in (doc["rows"] if "rows" in doc else doc["plugins"])}
    assert rows["realplug@mkt"]["weeksTotal"] is None


def test_unrecognized_recommendation_is_marked_and_alerts(tmp_path, capsys):
    audit = write_json(tmp_path / "audit.json", base_audit([plugin_entry("x@y", "quarantine")]))
    settings = write_json(tmp_path / "settings.json", {"enabledPlugins": {"x@y": True}})

    code, out, err = run(["--audit", str(audit), "--settings", str(settings)], capsys)

    assert code == 1
    assert "quarantine (unrecognized)" in out


def test_duplicate_plugin_ids_are_refused(tmp_path, capsys):
    audit = write_json(tmp_path / "audit.json", base_audit([plugin_entry("dup@mkt", "keep"), plugin_entry("dup@mkt", "review")]))
    settings = write_json(tmp_path / "settings.json", {"enabledPlugins": {"dup@mkt": True}})

    code, out, err = run(["--audit", str(audit), "--settings", str(settings)], capsys)

    assert code == 2
    assert "more than once" in err


def test_confirmation_prompt_names_the_exact_command(monkeypatch, tmp_path, capsys):
    log = tmp_path / "claude-argv.log"
    monkeypatch.setenv("PLUGIN_PRUNE_CLAUDE_BIN", str(FAKE_CLAUDE))
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(log))
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    prompts: list[str] = []

    def fake_input(prompt: str) -> str:
        prompts.append(prompt)
        return "no"

    monkeypatch.setattr("builtins.input", fake_input)
    run(
        ["--audit", str(AUDIT_FIXTURE), "--settings", str(SETTINGS_FIXTURE), "--apply", "--disable", "code-review@claude-plugins-official"],
        capsys,
    )
    assert prompts and f"{FAKE_CLAUDE} plugin disable code-review@claude-plugins-official --scope user" in prompts[0]
    assert not log.exists()
