"""Credential GUI regression through the shipped hook manifest; no OS/secret access."""
import json
from pathlib import Path
import re
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "rhize-devflow"
SCRIPT = PLUGIN / "scripts/credential_guard.py"


def run_guard(tool, value):
    return subprocess.run([sys.executable, "-B", str(SCRIPT)], input=json.dumps({
        "hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": value,
    }), text=True, capture_output=True, timeout=5)


def test_shipped_manifest_blocks_native_cua_keychain_selection():
    payload = {"hook_event_name": "PreToolUse", "tool_name": "mcp__cua_repl__js",
               "tool_input": {"code": 'await cua.getApp("Keychain Access");'}}
    results = []
    for group in json.loads((PLUGIN / "hooks/hooks.json").read_text())["hooks"]["PreToolUse"]:
        matcher = group.get("matcher", "")
        if matcher not in ("", "*") and not re.fullmatch(matcher, payload["tool_name"]):
            continue
        for hook in group["hooks"]:
            command = hook["command"].replace("${CLAUDE_PLUGIN_ROOT}", str(PLUGIN))
            results.append(subprocess.run(command, shell=True, input=json.dumps(payload),
                                          text=True, capture_output=True, timeout=10))
    assert any(r.returncode == 2 or '"permissionDecision": "deny"' in r.stdout for r in results)


@pytest.mark.parametrize("tool,value", [
    ("mcp__cua_repl__js", {"code": 'await cua.getApp("Keychain Access");'}),
    ("mcp__cua_repl__js", {"code": 'await cua.getApp("com.apple.keychainaccess");'}),
    ("mcp__cua_repl__js", {"code": 'await cua.getApp("/System/Applications/Utilities/Keychain Access.app");'}),
    ("mcp__cua_repl__js", {"code": 'await cua.getApp("Keychain" + " Access");'}),
    ("mcp__cua_repl__js", {"code": 'await cua.getApp("Keychain\\u0020Access");'}),
    ("Bash", {"command": 'open -a "Keychain Access"'}),
    ("exec_command", {"cmd": "/usr/bin/open -b com.apple.keychainaccess"}),
    ("Bash", {"command": 'osascript -e \'tell application "Keychain Access" to activate\''}),
    ("Bash", {"command": 'open -a Keychain\\ Access'}),
    ("Bash", {"command": 'open /System/Applications/Utilities/Keychain\\ Access.app'}),
    ("Bash", {"command": 'python3 -c \'import subprocess; subprocess.run(["open", "-a", "Keychain Access"])\''}),
    ("Bash", {"command": 'rg fixture .; open -a "Keychain Access"'}),
    ("Bash", {"command": 'rg --pre \'open -a "Keychain Access"\' fixture .'}),
    ("Bash", {"command": 'rg fixture .\nopen -a "Keychain Access"'}),
    ("Bash", {"command": 'rg fixture . # inspect source\nopen -a "Keychain Access"'}),
    ("Bash", {"command": 'osascript -l JavaScript -e \'Application("Keychain Access").activate()\''}),
])
def test_denies_explicit_gui_targets_without_echoing_input(tool, value):
    result = run_guard(tool, value)
    assert result.returncode == 2
    assert "credential-access" in result.stderr and "CLI" in result.stderr
    assert "getApp" not in result.stdout + result.stderr


@pytest.mark.parametrize("tool,value", [
    ("mcp__cua_repl__js", {"code": 'await cua.getApp("Safari");'}),
    ("Bash", {"command": "security find-generic-password -a test -s fixture >/dev/null 2>&1"}),
    ("Bash", {"command": "vercel whoami"}),
    ("Read", {"file_path": "Keychain Access.md"}),
    ("apply_patch", {"input": '+ await cua.getApp("Keychain Access")'}),
    ("Write", {"content": 'await cua.getApp("Keychain Access")'}),
    ("functions.exec", 'await tools.apply_patch(\'+ await cua.getApp("Keychain Access")\');'),
    ("Bash", {"command": 'rg -n \'open -a "Keychain Access"\' README.md'}),
    ("Bash", {"command": "cat <<'EOF'\nIt's a valid heredoc.\nEOF\n"}),
    ("Bash", {"command": "cat <<'EOF'\nIt's a note about Keychain.\nEOF\n"}),
])
def test_allows_cli_other_apps_and_source_edits(tool, value):
    result = run_guard(tool, value)
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")


def test_invalid_execution_envelope_is_denied_privately():
    result = subprocess.run([sys.executable, str(SCRIPT)], input='{"secret":"CANARY_VALUE"}',
                            text=True, capture_output=True, timeout=5)
    assert result.returncode == 2
    assert "CANARY_VALUE" not in result.stdout + result.stderr


def test_code_mode_edit_then_gui_still_denies_the_nested_tool():
    wrapper = run_guard("functions.exec", 'await tools.apply_patch("fixture"); await tools.mcp__cua_repl__js({code: \'await cua.getApp("Keychain Access")\'});')
    nested = run_guard("mcp__cua_repl__js", {"code": 'await cua.getApp("Keychain Access")'})
    assert wrapper.returncode == 0 and nested.returncode == 2
