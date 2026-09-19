"""Health cannot manufacture capture success, leak content, or hide worker death."""
import concurrent.futures
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from unittest.mock import patch

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "rhize-context-manager/scripts"
sys.path.insert(0, str(SCRIPTS))
from memory_context import hook_health, hook_runtime
from memory_context.core import default_memory_root
from memory_context.hook_health import Health


@pytest.fixture
def health(tmp_path):
    return Health(tmp_path / "plugin", tmp_path / "health")


def test_root_parity_and_unknown_is_not_success(monkeypatch, tmp_path, health):
    for name in ("RHIZE_CONTEXT_HOME", "XDG_DATA_HOME"):
        monkeypatch.delenv(name, raising=False)
    assert hook_health.memory_root() == default_memory_root()
    for name in ("XDG_DATA_HOME", "RHIZE_CONTEXT_HOME"):
        monkeypatch.setenv(name, str(tmp_path / name))
        assert hook_health.memory_root() == default_memory_root()
    assert health.status()["status"] == "not_run"


def test_atomic_concurrent_dedup_recovery_and_permissions(health, monkeypatch):
    transaction = health.transaction
    monkeypatch.setattr(health, "transaction", lambda action, wait=2: transaction(action, wait=2))
    def failure(_):
        health.outcome("codex", "Stop", error="child_failed", exit_code=2)
        return health.warnings("codex")
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(failure, range(12))) == 1
    record = health.status()["records"][0]
    assert record["failures"] == 12
    assert record["exitCode"] == 2
    health.outcome("codex", "Stop", "observed")
    assert health.status()["status"] == "operational"
    health.outcome("codex", "Stop", error="child_failed")
    assert health.warnings("codex")
    assert health.root.stat().st_mode & 0o777 == 0o700
    assert (health.root / "state.json").stat().st_mode & 0o777 == 0o600


def test_old_installation_failures_are_evictable_and_do_not_warn(health, tmp_path):
    for i in range(40):
        Health(tmp_path / str(i), health.root).outcome("codex", "Stop", error="entrypoint_missing")
    assert not health.warnings("codex")
    health.outcome("codex", "Stop", "disabled")
    assert health.status()["status"] == "operational"
    state = json.loads((health.root / "state.json").read_text())
    assert len(state["records"]) == 32


def test_old_installation_live_worker_is_not_evicted(health, tmp_path):
    def running(rows):
        r = health.record(rows, "codex", "worker")
        r.update(workerState="running", launchId="a" * 32, updated=1)
    health.transaction(running)
    for i in range(40):
        Health(tmp_path / str(i), health.root).outcome("codex", "Stop", "disabled")
    health.outcome("codex", "worker", error="worker_failed", launch_id="a" * 32)
    assert health.status()["status"] == "degraded"


@pytest.mark.parametrize("kind", ["json", "oversize", "fields", "symlink", "parent", "fifo"])
def test_invalid_or_unsafe_storage_reports_unavailable(health, tmp_path, kind):
    health.status()
    target = health.root / "state.json"
    if kind == "json":
        target.write_text("broken PRIVATE_SECRET")
    elif kind == "oversize":
        target.write_text("x" * 65537)
    elif kind == "fields":
        target.write_text('{"version":1,"records":{},"secret":"PRIVATE_SECRET"}')
    elif kind == "parent":
        link = tmp_path / "link"
        link.symlink_to(health.root, target_is_directory=True)
        health = Health(tmp_path / "plugin", link / "child")
    else:
        target.unlink()
        if kind == "fifo":
            os.mkfifo(target)
        else:
            outside = tmp_path / "outside"
            outside.write_text("PRIVATE_SECRET")
            target.symlink_to(outside)
    result = health.status()
    assert result["status"] == "unavailable"
    assert "PRIVATE_SECRET" not in json.dumps(result)


def test_busy_worker_and_stale_completion_cannot_resolve_failure(health):
    health.outcome("codex", "worker", error="worker_failed")
    health.outcome("codex", "worker", "busy")
    assert health.status()["status"] == "degraded"
    health.outcome("codex", "worker", "drained", launch_id="a" * 32)
    assert health.status()["status"] == "degraded"
    health.outcome("codex", "Stop", "observed")
    assert health.status()["status"] == "degraded"


def test_worker_lock_is_liveness_authority_even_when_old(health):
    def running(rows):
        r = health.record(rows, "codex", "worker")
        r.update(workerState="running", launchId="a" * 32, updated=1)
    health.transaction(running)
    with health.lock("worker.lock", wait=0):
        assert health.status()["status"] == "operational"
        assert health.status()["records"][0]["longRunning"] is True
    assert health.status()["status"] == "degraded"
    assert health.status()["records"][0]["error"] == "worker_died"


def test_spawn_failure_and_fd_identity(health):
    with patch.object(hook_runtime.subprocess, "Popen", side_effect=OSError("PRIVATE_SECRET")):
        hook_runtime.launch_worker(health, "codex")
    assert health.status()["records"][0]["error"] == "worker_spawn_failed"
    with open(os.devnull) as wrong_fd:
        with pytest.raises(ValueError, match="descriptor"):
            hook_runtime.worker(health, "codex", "a" * 32, wrong_fd.fileno())


def test_foreground_timeout_and_overflow_kill_promptly(tmp_path, monkeypatch):
    (tmp_path / "hooks").mkdir()
    script = tmp_path / "hooks/memory-opportunity-stop.py"
    monkeypatch.setattr(hook_runtime, "PLUGIN", tmp_path)
    with open(os.devnull) as stdin, patch.object(hook_runtime.sys, "stdin", stdin):
        script.write_text("import time\ntime.sleep(30)\n")
        start = time.monotonic()
        assert hook_runtime.capture("Stop", start + .8)[1] == "child_timeout"
        assert time.monotonic() - start < 2
        script.write_text("import sys\nsys.stdout.write('PRIVATE_SECRET'*100000)\nsys.stdout.flush()\n")
        start = time.monotonic()
        assert hook_runtime.capture("Stop", start + 5)[1] == "protocol_error"
        assert time.monotonic() - start < 2


def test_recursive_child_touches_no_health(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("RHIZE_MEMORY_EVAL_CHILD", "1")
    monkeypatch.setenv("RHIZE_CONTEXT_HOME", str(tmp_path / "absent"))
    assert hook_runtime.main(["Stop"]) == 0
    assert not (tmp_path / "absent").exists()
    assert capsys.readouterr().out == ""


def test_diagnostic_contention_alone_is_quiet(health, monkeypatch, capsys):
    monkeypatch.setattr(hook_runtime, "Health", lambda _: health)
    monkeypatch.setattr(hook_runtime, "capture", lambda *_: ("disabled", None, None))
    with health.lock():
        assert hook_runtime.main(["Stop"]) == 0
        assert capsys.readouterr().out == ""
        assert health.status()["status"] == "unavailable"


def test_unavailable_storage_warns_at_start_or_capture_failure_only(health, monkeypatch, capsys):
    monkeypatch.setattr(hook_runtime, "Health", lambda _: health)
    monkeypatch.setattr(hook_runtime, "capture", lambda *_: ("disabled", None, None))
    health.status()
    (health.root / "state.json").write_text("PRIVATE_SECRET broken JSON")
    hook_runtime.main(["PostToolUse"])
    assert capsys.readouterr().out == ""
    hook_runtime.main(["SessionStart"])
    assert set(json.loads(capsys.readouterr().out)) == {"systemMessage"}
    monkeypatch.setattr(hook_runtime, "capture", lambda *_: (None, "child_failed", 2))
    hook_runtime.main(["Stop"])
    assert set(json.loads(capsys.readouterr().out)) == {"systemMessage"}
    assert health.status()["status"] == "unavailable"


def test_detached_worker_retains_lock_and_releases_it_on_death(tmp_path):
    import shutil
    plugin = tmp_path / "plugin"
    shutil.copytree(SCRIPTS.parent, plugin)
    pidfile = tmp_path / "pid"
    (plugin / "scripts/memory_context/runner.py").write_text(
        "import os,time\nfrom pathlib import Path\n"
        f"def main(args):\n    Path({str(pidfile)!r}).write_text(str(os.getpid()))\n"
        "    time.sleep(30)\n    print('{}')\n    return 0\n")
    (plugin / "hooks/memory-opportunity-session.py").write_text("print('{\"outcome\":\"observed\"}')\n")
    env = {**os.environ, "RHIZE_CONTEXT_HOME": str(tmp_path / "context"), "PLUGIN_ROOT": str(plugin)}
    env.pop("RHIZE_MEMORY_EVAL_CHILD", None)
    runtime = plugin / "scripts/memory_context/hook_runtime.py"
    proc = subprocess.run([sys.executable, str(runtime), "SessionStart"], input="{}", text=True,
                          capture_output=True, env=env, timeout=3)
    assert (proc.returncode, proc.stdout, proc.stderr) == (0, "", "")
    for _ in range(100):
        if pidfile.exists():
            break
        time.sleep(.02)
    assert pidfile.exists()
    pid = int(pidfile.read_text())
    health = Health(plugin, tmp_path / "context/memory-context/hook-health-v1")
    try:
        with pytest.raises(TimeoutError):
            with health.lock("worker.lock", wait=0):
                pass
        assert health.status()["status"] == "operational"
    finally:
        os.kill(pid, signal.SIGKILL)
    for _ in range(100):
        if health.status()["status"] == "degraded":
            break
        time.sleep(.02)
    assert health.status()["records"][-1]["error"] == "worker_died"
