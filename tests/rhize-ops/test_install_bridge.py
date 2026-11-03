import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "rhize-ops/scripts/install_bridge.py"
BRIDGE = ROOT / "rhize-ops/scripts/agent_bridge.py"
spec = importlib.util.spec_from_file_location("install_bridge", SCRIPT)
ib = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ib)

FAKE_CLAUDE = """\
import json, os, sys
from pathlib import Path
a = sys.argv[1:]
p = Path(os.environ["HOME"]) / ".claude.json"
if a == ["--version"]:
    print("9.0.0 (Claude Code)")
elif a[:2] == ["auth", "status"]:
    print(json.dumps({"loggedIn": True, "authMethod": "claude.ai"}))
elif a[:2] == ["mcp", "remove"]:
    d = json.loads(p.read_text()); d["mcpServers"].pop(a[2]); p.write_text(json.dumps(d))
elif a[:2] == ["mcp", "add-json"]:
    if os.environ.get("FAKE_FAIL") and os.environ["FAKE_FAIL"] in a[-1]:
        sys.exit("add-json refused")
    d = json.loads(p.read_text()); d["mcpServers"][a[2]] = json.loads(a[-1]); p.write_text(json.dumps(d))
"""
FAKE_CODEX = """\
import sys
print("Logged in using ChatGPT" if sys.argv[1:] == ["login", "status"] else "codex-cli 9.0.0")
"""


@pytest.fixture
def env(tmp_path):
    home = tmp_path.resolve() / "home"
    old = home / ".rhize/agent-bridge-releases/1.0.0/agent_bridge.py"
    old.parent.mkdir(parents=True)
    old.write_bytes(BRIDGE.read_bytes())
    (old.parent / "installation.json").write_text(json.dumps(
        {"script_sha256": hashlib.sha256(old.read_bytes()).hexdigest(), "previous_release": None}))
    (home / ".claude.json").write_text(json.dumps({
        "mcpServers": {"rhize-bridge": {"type": "stdio", "command": sys.executable, "env": {},
                                        "args": [str(old), "--origin", "claude", "--claude-bin", "/c"]},
                       "other": {"command": "x"}},
        "projects": {"/p": {"mcpServers": {"local": {"command": "y"}}}}, "oauth": "keep"}))
    (home / ".codex").mkdir()
    (home / ".codex/config.toml").write_text(
        'model = "m"\n\n[mcp_servers.rhize-bridge]\n'
        f'command = "{sys.executable}"\nargs = ["{old}", "--origin", "codex", "--claude-bin", "/l"]\n\n'
        '[mcp_servers.rhize-bridge.tools.job_status]\napproval_mode = "approve"\n\n'
        '[mcp_servers.other]\ncommand = "z"\n')
    bins = tmp_path.resolve() / "bin"
    bins.mkdir()
    for name, body in (("claude", FAKE_CLAUDE), ("codex", FAKE_CODEX)):
        (bins / name).write_text(f"#!{sys.executable}\n{body}")
        (bins / name).chmod(0o755)
    repo = tmp_path.resolve() / "repo"
    (repo / "rhize-ops/scripts").mkdir(parents=True)
    (repo / "rhize-ops/.claude-plugin").mkdir()
    (repo / "rhize-ops/.claude-plugin/plugin.json").write_text('{"version": "2.0.0"}')
    (repo / "rhize-ops/scripts/agent_bridge.py").write_bytes(BRIDGE.read_bytes() + b"# 2.0.0\n")
    git = ["git", "-C", str(repo), "-c", "core.excludesFile=/dev/null", "-c", "user.name=T",
           "-c", "user.email=t@example.invalid"]
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run([*git, "commit", "-qm", "release"], check=True)
    subprocess.run([*git, "tag", "v9.9.9"], check=True)
    return {"home": home, "repo": repo, "old": str(old),
            "new": str(home / ".rhize/agent-bridge-releases/2.0.0/agent_bridge.py"),
            "env": {**os.environ, "HOME": str(home), "PATH": f"{bins}:{os.environ['PATH']}"}}


def run(env, *args, **extra):
    return subprocess.run([sys.executable, str(SCRIPT), *args, "--repo", str(env["repo"]), "--ref", "HEAD"],
                          env={**env["env"], **extra}, capture_output=True, text=True, timeout=120)


def state(env):
    claude = json.loads((env["home"] / ".claude.json").read_text())
    return claude, (env["home"] / ".codex/config.toml").read_text()


def test_swap_codex_text_guards():
    text = '[mcp_servers.rhize-bridge]\nargs = ["/a/agent_bridge.py", "--origin", "codex"]\n'
    assert '"/b/agent_bridge.py"' in ib.swap_codex_text(text, "/a/agent_bridge.py", "/b/agent_bridge.py")
    with pytest.raises(ib.InstallError, match="found 0"):
        ib.swap_codex_text(text, "/missing.py", "/b.py")
    with pytest.raises(ib.InstallError, match="found 2"):
        ib.swap_codex_text(text + 'note = "/a/agent_bridge.py"\n', "/a/agent_bridge.py", "/b.py")
    with pytest.raises(ib.InstallError, match="outside"):
        ib.swap_codex_text('note = "/a.py"\n' + text.replace("/a/agent_bridge.py", "/x.py"), "/a.py", "/b.py")


def test_check_claude_entries_flags_unrelated_change():
    before = {"mcpServers": {"rhize-bridge": {"args": ["/a"]}}, "projects": {"/p": {"mcpServers": {"k": 1}}}}
    after = {"mcpServers": {"rhize-bridge": {"args": ["/b"]}}, "projects": {"/p": {"mcpServers": {"k": 2}}}}
    with pytest.raises(ib.InstallError, match="'/p', 'k'"):
        ib.check_claude_entries(before, after, {"args": ["/b"]})


def test_dry_run_writes_nothing(env):
    before = state(env)
    r = run(env, "2.0.0", "--dry-run")
    assert r.returncode == 0, r.stderr
    assert "dry run" in r.stdout and state(env) == before
    assert not Path(env["new"]).parent.exists()


def test_install_rollback_and_reactivate(env):
    claude0, codex0 = state(env)
    r = run(env, "2.0.0")
    assert r.returncode == 0, r.stderr
    claude, codex = state(env)
    assert claude["mcpServers"]["rhize-bridge"]["args"] == [env["new"], *claude0["mcpServers"]["rhize-bridge"]["args"][1:]]
    assert {k: v for k, v in claude.items() if k != "mcpServers"} == {k: v for k, v in claude0.items() if k != "mcpServers"}
    assert claude["mcpServers"]["other"] == claude0["mcpServers"]["other"]
    assert codex == codex0.replace(env["old"], env["new"])
    manifest = json.loads((Path(env["new"]).parent / "installation.json").read_text())
    assert manifest["previous_release"] == "1.0.0" and manifest["release_tags"] == ["v9.9.9"]
    assert manifest["script_sha256"] == hashlib.sha256(Path(env["new"]).read_bytes()).hexdigest()
    assert manifest["validation"]["stdio_probe"]["codex"] == {"handshake": "initialize 2025-06-18; 4 tools"}
    assert oct(Path(env["new"]).stat().st_mode & 0o777) == "0o600"

    r = run(env, "--rollback")
    assert r.returncode == 0, r.stderr
    assert state(env) == (claude0, codex0)

    r = run(env, "2.0.0")
    assert r.returncode == 0 and "installed copy verified" in r.stdout, r.stderr
    assert state(env)[1] == codex
    assert "nothing to change" in run(env, "2.0.0").stdout


def test_failed_claude_registration_restores_both_hosts(env):
    before = state(env)
    r = run(env, "2.0.0", FAKE_FAIL="2.0.0")
    assert r.returncode == 1 and "add-json" in r.stderr
    assert state(env) == before


def test_refuses_wrong_version_and_disagreeing_hosts(env):
    r = run(env, "3.0.0")
    assert r.returncode == 1 and "is rhize-ops 2.0.0, not 3.0.0" in r.stderr
    toml = env["home"] / ".codex/config.toml"
    toml.write_text(toml.read_text().replace(env["old"], "/elsewhere/agent_bridge.py"))
    r = run(env, "2.0.0", "--dry-run")
    assert r.returncode == 1 and "hosts disagree" in r.stderr
