import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
import uuid

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "rhize-ops/scripts/agent_bridge.py"
spec = importlib.util.spec_from_file_location("agent_bridge", SCRIPT)
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)


def request(**extra):
    return dict(request_id=str(uuid.uuid4()), target="codex", model="gpt-5.6-terra",
                prompt="Fix the addition function", authority="User authorized this fixture", **extra)


@pytest.fixture
def repo(tmp_path):
    path = tmp_path.resolve() / "repo"
    path.mkdir()
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    (path / "math.py").write_text("def add(a, b): return a - b\n")
    subprocess.run(["git", "-C", str(path), "add", "math.py"], check=True)
    subprocess.run(["git", "-C", str(path), "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                    "commit", "-qm", "fixture"], check=True)
    return path


def task_request(repo):
    return request(repository=str(repo), expected_head=subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip(),
        context_files=["math.py"], editable_paths=["math.py", "new.py"])


def answer(changes=None):
    return dict(status="completed", summary="Changed addition", findings=[], changes=changes or [])


def wait(bridge, job):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        value = bridge.status(job["job_id"])
        if value["status"] in b.TERMINAL:
            return value
        time.sleep(.01)
    pytest.fail("job did not finish")


@pytest.mark.parametrize("name", [".", "../a", "/a", "a//b", "a/./b", ".env", ".github/workflows/x.yml",
                                  "foo/.config", "payment.py", "secrets/key", "a\\b"])
def test_protected_paths(name):
    with pytest.raises(b.BridgeError):
        b.relative_path(name)


def test_snapshot_head_symlinks_and_limits(repo):
    args = b.validate_request("task", task_request(repo), "claude")
    assert b.snapshot("task", args)["files"]["new.py"] is None
    with pytest.raises(b.BridgeError, match="HEAD"):
        b.snapshot("task", {**args, "expected_head": "wrong"})
    (repo / "math.py").unlink()
    (repo / "math.py").symlink_to("new.py")
    with pytest.raises(b.BridgeError, match="symlink"):
        b.snapshot("task", args)


@pytest.mark.parametrize("before,after", [("old", "new"), ("old\n", "new"), (None, "new"), (None, ""), ("old", "")])
def test_patch_applies_and_source_unchanged(tmp_path, before, after):
    root = tmp_path.resolve()
    source = root / "source"
    source.mkdir()
    if before is not None:
        (source / "file.txt").write_text(before)
    result = b.materialize(root, {"files": {"file.txt": before}}, answer([{"path": "file.txt", "content": after}]))
    assert (source / "file.txt").read_text() == before if before is not None else not (source / "file.txt").exists()
    subprocess.run(["git", "apply", result["patch"]], cwd=source, check=True, capture_output=True)
    assert (source / "file.txt").read_text() == after


def test_scope_and_review_reject_changes():
    change = answer([{"path": "other.py", "content": "x"}])
    with pytest.raises(b.BridgeError, match="out-of-scope"):
        b.validate_answer(change, "task", {"editable_paths": ["math.py"]})
    with pytest.raises(b.BridgeError, match="forbidden"):
        b.validate_answer(change, "review", {})


def test_environment_and_commands(monkeypatch, tmp_path):
    for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_BASE_URL", "OPENAI_BASE_URL", "N8N_EXECUTOR_TOKEN"):
        monkeypatch.setenv(key, "must-not-inherit")
        assert key not in b.worker_env()
    assert b.worker_env()["RHIZE_BRIDGE_CHILD"] == "1"
    for host, model in [("claude", "claude-sonnet-5"), ("codex", "gpt-5.6-terra")]:
        command = b.worker_command(host, host, model, "medium", tmp_path)
        assert "--dangerously-skip-permissions" not in command
        assert "--dangerously-bypass-approvals-and-sandbox" not in command
        assert model in command
    assert "features.shell_tool=false" in command


def test_native_failure_identity_and_tools():
    with pytest.raises(b.BridgeError, match="mismatched"):
        b.parse_native("claude", json.dumps(dict(subtype="success", modelUsage={"different": {}}, structured_output=answer())), "claude-sonnet-5")
    for event in [{"type": "turn.failed"}, {"type": "item.started", "item": {"type": "command_execution"}}]:
        with pytest.raises(b.BridgeError):
            b.parse_native("codex", json.dumps(event), "gpt-5.6-terra")


def test_jobs_idempotence_and_isolated_results(monkeypatch, tmp_path, repo):
    calls = []
    monkeypatch.setattr(b, "authenticated", lambda *a: True)
    def run(*args):
        calls.append(args)
        return 0, "\n".join(map(json.dumps, [
            {"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(answer([{"path": "math.py", "content": "def add(a, b): return a + b\n"}]))}},
            {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 20}}])), ""
    monkeypatch.setattr(b, "run_process", run)
    bridge = b.Bridge(tmp_path.resolve() / "state", "claude", {"codex": "codex"})
    other = b.Bridge(tmp_path.resolve() / "state", "claude")
    try:
        args = task_request(repo)
        first = bridge.submit("task", args)
        result = wait(bridge, first)
        assert result["status"] == "completed"
        assert other.submit("task", args) == result
        assert len(calls) == 1
        assert result["observed_model"] is None
        assert result["source"]["file_hashes"]["math.py"] == b.digest((repo / "math.py").read_bytes())
        assert "a - b" in (repo / "math.py").read_text()
        scope = {}
        exec((Path(result["workspace"]) / "math.py").read_text(), scope)
        assert scope["add"](2, 4) == 6
        with pytest.raises(b.BridgeError, match="different input"):
            bridge.submit("task", {**args, "prompt": "different"})
    finally:
        other.close()
        bridge.close()


def test_restart_detects_interruption(tmp_path):
    bridge = b.Bridge(tmp_path.resolve() / "state", "claude")
    job = str(uuid.uuid4())
    bridge.db.execute("INSERT INTO jobs VALUES (?,?,?,?,?)", (job, "claude", str(uuid.uuid4()), "x", json.dumps({"status": "running"})))
    assert bridge.status(job)["status"] == "interrupted"
    bridge.close()


@pytest.mark.parametrize("mode", ["timeout", "cancel", "output"])
def test_process_deadline_cancel_output_and_cleanup(tmp_path, mode):
    event = threading.Event()
    code = "import os,time; print(os.getpid(),flush=True); time.sleep(20)"
    if mode == "cancel":
        timer = threading.Timer(.15, event.set)
        timer.start()
    if mode == "output":
        code = "print('x' * 3000000)"
    start = time.monotonic()
    with pytest.raises(b.BridgeError, match={"timeout": "timed_out", "cancel": "cancelled", "output": "limit"}[mode]):
        b.run_process([sys.executable, "-c", code], b"", tmp_path, .3 if mode == "timeout" else 5, event)
    assert time.monotonic() - start < 3


def test_stdio_protocol(tmp_path):
    messages = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26"}},
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "request_review", "arguments": {}}}]
    run = subprocess.run([sys.executable, str(SCRIPT), "--origin", "codex", "--state-dir", str(tmp_path.resolve() / "state")],
                         input="\n".join(map(json.dumps, messages)) + "\n", text=True, capture_output=True, timeout=10)
    assert run.returncode == 0, run.stderr
    rows = [json.loads(line) for line in run.stdout.splitlines()]
    assert len(rows) == 3
    assert len(rows[1]["result"]["tools"]) == 4
    assert rows[1]["result"]["tools"][0]["inputSchema"]["properties"]["target"]["enum"] == ["claude"]
    assert rows[2]["result"]["isError"] is True


def test_kills_descendant_process_group(tmp_path):
    pidfile = tmp_path / 'pids'
    code = "import os,time; child=os.fork(); open(%r,'a').write(str(os.getpid())+'\\n'); time.sleep(30)" % str(pidfile)
    with pytest.raises(b.BridgeError, match="timed_out"):
        b.run_process([sys.executable, "-c", code], b"", tmp_path, .5, threading.Event())
    pids = pidfile.read_text().splitlines()
    assert len(pids) == 2
    for pid in pids:
        state = subprocess.run(["ps", "-o", "stat=", "-p", pid], capture_output=True, text=True).stdout.strip()
        assert not state or state.startswith("Z")


def test_backpressure_duplicate_pending_and_close(monkeypatch, tmp_path):
    calls = []
    def auth(host, binary, directory, cancel):
        calls.append(host)
        cancel.wait(5)
        raise b.BridgeError("cancelled")
    monkeypatch.setattr(b, "authenticated", auth)
    bridge = b.Bridge(tmp_path.resolve() / "state", "claude", {"codex": "codex"})
    try:
        args = request()
        first = bridge.submit("review", args)
        assert bridge.submit("review", args)["job_id"] == first["job_id"]
        second = bridge.submit("review", request())
        with pytest.raises(b.BridgeError, match="busy"):
            bridge.submit("review", request())
        assert bridge.cancel(first["job_id"])["cancellation_requested"]
        assert wait(bridge, first)["status"] == "cancelled"
    finally:
        bridge.close()
    reopened = b.Bridge(tmp_path.resolve() / "state", "claude")
    try:
        assert reopened.status(second["job_id"])["status"] == "cancelled"
        assert len(calls) == 2
    finally:
        reopened.close()


@pytest.mark.parametrize("failure", ["auth", "exit", "json", "scope"])
@pytest.mark.parametrize("origin,target,model", [("claude", "codex", "gpt-5.6-terra"), ("codex", "claude", "claude-sonnet-5")])
def test_job_failures_never_become_success(monkeypatch, tmp_path, failure, origin, target, model):
    monkeypatch.setattr(b, "authenticated", lambda *args: failure != "auth")
    result = answer([{"path": "math.py", "content": "bad"}])
    out = json.dumps(dict(subtype="success", modelUsage={model: {}}, structured_output=result)) if target == "claude" else '\n'.join(map(json.dumps, [
        {"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(result)}}, {"type": "turn.completed"}]))
    monkeypatch.setattr(b, "run_process", lambda *a: (1 if failure == "exit" else 0, "broken" if failure == "json" else out, ""))
    bridge = b.Bridge(tmp_path.resolve() / "state", origin, {target: target})
    try:
        args = request()
        args.update(target=target, model=model)
        value = wait(bridge, bridge.submit("review", args))
        assert value["status"] == "failed"
        assert "workspace" not in value
        assert value["actually_ran"] is (failure != "auth")
    finally:
        bridge.close()


@pytest.mark.parametrize("error", [subprocess.TimeoutExpired("git", 10), b.sqlite3.OperationalError("database is locked")])
def test_submission_operational_failure_keeps_connection_alive(monkeypatch, tmp_path, capsys, error):
    import io
    bridge = b.Bridge(tmp_path.resolve() / "state", "claude")
    def fail(*args):
        raise error
    monkeypatch.setattr(bridge, "submit", fail)
    messages = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "request_review", "arguments": {}}},
                {"jsonrpc": "2.0", "id": 3, "method": "ping"}]
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(("\n".join(map(json.dumps, messages)) + "\n").encode())))
    b.serve(bridge)
    rows = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert rows[1]["result"]["isError"] is True
    assert rows[2]["result"] == {}
