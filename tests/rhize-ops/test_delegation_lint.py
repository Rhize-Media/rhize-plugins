"""test_delegation_lint.py — delegation_lint.py gate rules (path leaks + jira-description
contract shape) per task-1-brief.md Contract B.
"""
import importlib.util
import io
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "rhize-ops" / "scripts" / "delegation_lint.py"
SPEC = importlib.util.spec_from_file_location("delegation_lint", SCRIPT)
delegation_lint = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(delegation_lint)

VALID_UUID = "11111111-1111-4111-8111-111111111111"


def run(text: str, kind: str, monkeypatch, capsys, *, extra_args: list[str] | None = None):
    monkeypatch.setattr("sys.stdin", io.StringIO(text))
    code = delegation_lint.main(["--kind", kind, *(extra_args or [])])
    captured = capsys.readouterr()
    return code, captured.out


def jira_text_of_length(total_chars: int) -> str:
    prefix = "Paste into Claude: prompt\n"
    suffix = f"\nrhize-delegation:v1:{VALID_UUID}\n"
    filler_len = total_chars - len(prefix) - len(suffix)
    assert filler_len >= 0
    return prefix + ("x" * filler_len) + suffix


def test_clean_jira_brief_passes(monkeypatch, capsys):
    text = (
        "Do the thing.\n"
        "\n"
        "Paste into Claude: some prompt here\n"
        f"rhize-delegation:v1:{VALID_UUID}\n"
    )
    code, out = run(text, "jira-description", monkeypatch, capsys)
    assert code == 0
    assert out == "PASS\n"


def test_absolute_path_fails(monkeypatch, capsys):
    code, out = run("See /Users/jim/report.txt for details.\n", "slack-message", monkeypatch, capsys)
    assert code == 1
    assert "FAIL absolute-path" in out


def test_obsidian_url_fails(monkeypatch, capsys):
    code, out = run("Open obsidian://open?vault=Foo&file=Bar\n", "slack-message", monkeypatch, capsys)
    assert code == 1
    assert "FAIL obsidian-url" in out


def test_vault_note_path_fails(monkeypatch, capsys):
    code, out = run("See Projects/Widgets/spec.md for the plan.\n", "slack-message", monkeypatch, capsys)
    assert code == 1
    assert "FAIL vault-note-path" in out


def test_ask_for_file_fails(monkeypatch, capsys):
    code, out = run("Ask Bob to send report.md before Friday.\n", "slack-message", monkeypatch, capsys)
    assert code == 1
    assert "FAIL ask-for-file" in out


def test_marker_missing_fails(monkeypatch, capsys):
    text = "Do the thing.\nPaste into Claude: prompt\n"
    code, out = run(text, "jira-description", monkeypatch, capsys)
    assert code == 1
    assert "FAIL marker-missing" in out


def test_marker_not_last_when_marker_not_final_line(monkeypatch, capsys):
    text = (
        "Do the thing.\n"
        "Paste into Claude: prompt\n"
        f"rhize-delegation:v1:{VALID_UUID}\n"
        "One more line after the marker.\n"
    )
    code, out = run(text, "jira-description", monkeypatch, capsys)
    assert code == 1
    assert "FAIL marker-not-last" in out


def test_marker_not_last_when_marker_duplicated(monkeypatch, capsys):
    text = (
        "Paste into Claude: prompt\n"
        f"rhize-delegation:v1:{VALID_UUID}\n"
        f"rhize-delegation:v1:{VALID_UUID}\n"
    )
    code, out = run(text, "jira-description", monkeypatch, capsys)
    assert code == 1
    assert "FAIL marker-not-last" in out


def test_marker_in_confluence_fails(monkeypatch, capsys):
    text = f"Body text.\nrhize-delegation:v1:{VALID_UUID}\n"
    code, out = run(text, "confluence-body", monkeypatch, capsys)
    assert code == 1
    assert "FAIL marker-in-confluence" in out


def test_multiple_starter_prompts_fails(monkeypatch, capsys):
    text = (
        "Paste into Claude: first\n"
        "Paste into Claude: second\n"
        f"rhize-delegation:v1:{VALID_UUID}\n"
    )
    code, out = run(text, "jira-description", monkeypatch, capsys)
    assert code == 1
    assert "FAIL multiple-starter-prompts" in out


def test_steps_in_jira_fails(monkeypatch, capsys):
    text = (
        "## Step-by-Step\n"
        "1. Do this\n"
        "Paste into Claude: prompt\n"
        f"rhize-delegation:v1:{VALID_UUID}\n"
    )
    code, out = run(text, "jira-description", monkeypatch, capsys)
    assert code == 1
    assert "FAIL steps-in-jira" in out


def test_bare_note_file_warns_and_does_not_fail(monkeypatch, capsys):
    text = (
        "Paste into Claude: prompt\n"
        "See report.md for background.\n"
        f"rhize-delegation:v1:{VALID_UUID}\n"
    )
    code, out = run(text, "jira-description", monkeypatch, capsys)
    assert code == 0
    assert "WARN bare-note-file" in out
    assert out.strip().splitlines()[-1] == "PASS"


def test_no_starter_prompt_warns_and_does_not_fail(monkeypatch, capsys):
    text = f"Do the thing.\nrhize-delegation:v1:{VALID_UUID}\n"
    code, out = run(text, "jira-description", monkeypatch, capsys)
    assert code == 0
    assert "WARN no-starter-prompt" in out
    assert out.strip().splitlines()[-1] == "PASS"


def test_too_long_warns_over_warn_chars(monkeypatch, capsys):
    text = jira_text_of_length(1501)
    code, out = run(text, "jira-description", monkeypatch, capsys)
    assert code == 0
    assert "WARN too-long" in out


def test_too_long_fails_over_max_chars(monkeypatch, capsys):
    text = jira_text_of_length(3001)
    code, out = run(text, "jira-description", monkeypatch, capsys)
    assert code == 1
    assert "FAIL too-long" in out


def test_url_token_exempt_from_path_rules(monkeypatch, capsys):
    text = "See https://example.atlassian.net/wiki/spaces/RHI/pages/1/Some+Page.md for details.\n"
    code, out = run(text, "slack-message", monkeypatch, capsys)
    assert code == 0
    assert "absolute-path" not in out
    assert "obsidian-url" not in out
    assert "vault-note-path" not in out
    assert "bare-note-file" not in out


def test_json_output_parses_and_mirrors_human_findings(monkeypatch, capsys):
    text = "See /Users/jim/report.txt now.\n"

    monkeypatch.setattr("sys.stdin", io.StringIO(text))
    code = delegation_lint.main(["--kind", "slack-message"])
    human_out = capsys.readouterr().out

    monkeypatch.setattr("sys.stdin", io.StringIO(text))
    code_json = delegation_lint.main(["--kind", "slack-message", "--json"])
    json_out = capsys.readouterr().out

    assert code == code_json
    assert len(json_out.splitlines()) == 1
    payload = json.loads(json_out)
    assert payload["ok"] is (code == 0)
    assert payload["kind"] == "slack-message"
    assert payload["chars"] == len(text)

    human_lines = [line for line in human_out.splitlines() if line not in ("PASS",) and not line.startswith("FAIL (")]
    assert len(payload["findings"]) == len(human_lines)
    for finding, line in zip(payload["findings"], human_lines):
        assert line == f"{finding['severity']} {finding['rule']} line {finding['line']}: {finding['excerpt']}"
