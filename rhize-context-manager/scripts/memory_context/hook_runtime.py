#!/usr/bin/env python3
"""Nonblocking hook boundary and independently observable detached drain."""
from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import runpy
import selectors
import signal
import subprocess
import sys
import time
import uuid

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from hook_health import EVENTS, OUTCOMES, Health
else:
    from .hook_health import EVENTS, OUTCOMES, Health

PLUGIN = Path(__file__).resolve().parents[2]
WARNING = "Rhize passive measurement is degraded; your task can continue. Run hook_runtime.py status from this plugin for private diagnostic status."
UNAVAILABLE = "Rhize passive measurement diagnostics are unavailable; capture health is unknown. Your task can continue."


def emit(message: str):
    try:
        print(json.dumps({"systemMessage": message}), flush=True)
    except (OSError, ValueError):
        pass  # Host may already have closed its output pipe.


def capture(event: str, deadline: float) -> tuple[str | None, str | None, int | None]:
    entrypoint = PLUGIN / "hooks" / EVENTS[event]
    if not entrypoint.is_file():
        return None, "entrypoint_missing", None
    proc = subprocess.Popen([sys.executable, str(entrypoint), "--supervised", event],
                            stdin=sys.stdin, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            start_new_session=True)
    output = bytearray()
    error = None
    end = min(deadline - 0.6, time.monotonic() + 8)
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(proc.stdout, selectors.EVENT_READ)
            while True:
                remaining = end - time.monotonic()
                if remaining <= 0:
                    error = "child_timeout"
                    break
                if not selector.select(remaining):
                    continue
                chunk = os.read(proc.stdout.fileno(), 4097 - len(output))
                if not chunk:
                    break
                output.extend(chunk)
                if len(output) > 4096:
                    error = "protocol_error"
                    break
        if error:
            return None, error, None
        try:
            code = proc.wait(timeout=max(0.001, end - time.monotonic()))
        except subprocess.TimeoutExpired:
            return None, "child_timeout", None
        if code:
            return None, "child_failed", code
        try:
            value = json.loads(output)
            if (not isinstance(value, dict) or set(value) != {"outcome"}
                    or value["outcome"] not in OUTCOMES - {"drained", "busy", "starting", "running"}):
                raise ValueError("invalid result")
        except (ValueError, TypeError):
            return None, "protocol_error", None
        outcome = value["outcome"]
        return outcome, outcome if outcome in {"invalid_event", "incomplete"} else None, None
    finally:
        if proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait()
        proc.stdout.close()


def launch_worker(health: Health, host: str):
    try:
        with health.lock("worker.lock", wait=0) as fd:
            launch_id = uuid.uuid4().hex
            def starting(rows):
                r = health.record(rows, host, "worker")
                r.update(workerState="starting", launchId=launch_id, updated=time.time())
            health.transaction(starting)
            try:
                subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "worker", host, launch_id, str(fd)],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 start_new_session=True, close_fds=True, pass_fds=(fd,))
            except OSError:
                health.outcome(host, "worker", error="worker_spawn_failed", launch_id=launch_id)
    except TimeoutError:
        pass  # Another worker or a transient diagnostic writer owns the lock.


class BoundedOutput(io.StringIO):
    def write(self, value):
        if self.tell() + len(value) > 4096:
            raise ValueError("worker protocol overflow")
        return super().write(value)


def worker(health: Health, host: str, launch_id: str, fd: int):
    # Validate the exact descriptor and prevent native drivers from inheriting it.
    with health.directory() as directory:
        expected = os.stat("worker.lock", dir_fd=directory, follow_symlinks=False)
        actual = os.fstat(fd)
        if (expected.st_dev, expected.st_ino) != (actual.st_dev, actual.st_ino):
            raise ValueError("invalid launch descriptor")
    os.set_inheritable(fd, False)
    def running(rows):
        r = health.record(rows, host, "worker")
        if r["launchId"] != launch_id:
            raise ValueError("superseded launch")
        r.update(workerState="running", updated=time.time())
    try:
        health.transaction(running)
        output = BoundedOutput()
        with open(os.devnull, "w") as sink, contextlib.redirect_stderr(sink), contextlib.redirect_stdout(output):
            module = runpy.run_path(str(PLUGIN / "scripts/memory_context/runner.py"))
            code = module["main"](["opportunity-drain", "--limit", "2"])
        if code != 0:
            raise ValueError("worker failed")
        result = json.loads(output.getvalue())
        if not isinstance(result, dict):
            raise ValueError("invalid worker result")
        health.outcome(host, "worker", "busy" if result.get("workerAlreadyRunning") else "drained", launch_id=launch_id)
    except (Exception, SystemExit):
        health.outcome(host, "worker", error="worker_failed", launch_id=launch_id)
    finally:
        os.close(fd)


def main(argv=None):
    if os.environ.get("RHIZE_MEMORY_EVAL_CHILD") == "1":
        return 0
    args = sys.argv[1:] if argv is None else argv
    health = Health(PLUGIN)
    if args == ["status"]:
        result = health.status()
        print(json.dumps(result, sort_keys=True))
        return int(result["status"] in {"degraded", "unavailable"})
    if args and args[0] == "worker":
        worker(health, args[1], args[2], int(args[3]))
        return 0
    deadline = time.monotonic() + 9
    health.deadline = deadline
    host = "codex" if os.environ.get("PLUGIN_ROOT") else "claude"
    warning = None
    try:
        if len(args) != 1 or args[0] not in EVENTS:
            raise ValueError("invalid native event")
        outcome, error, code = capture(args[0], deadline)
        try:
            health.outcome(host, args[0], outcome, error, code)
            health.inspect_worker()
            if health.warnings(host):
                warning = WARNING
            if outcome in {"complete", "observed"} and time.monotonic() < deadline - 0.4:
                launch_worker(health, host)
                if health.warnings(host):
                    warning = WARNING
        except TimeoutError:
            # Contention alone is normal; an actual capture failure still warns.
            if error:
                warning = UNAVAILABLE
        except Exception:
            # Broken diagnostics cannot deduplicate. Announce on session start,
            # or actual capture failure, rather than on every successful tool.
            if error or args[0] == "SessionStart":
                warning = UNAVAILABLE
    except Exception:
        warning = UNAVAILABLE
    if warning:
        emit(warning)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        # The manifest has a static fallback if even imports/bootstrap fail.
        emit(UNAVAILABLE)
