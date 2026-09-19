"""Bounded, content-free diagnostics, independent of measurement-engine imports."""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import time
import uuid

EVENTS = {
    "SessionStart": "memory-opportunity-session.py",
    "UserPromptSubmit": "memory-opportunity.py",
    "PostToolUse": "memory-opportunity-tool.py",
    "Stop": "memory-opportunity-stop.py",
}
OUTCOMES = {"child_ignored", "disabled", "invalid_event", "scope_denied", "stale_turn_ignored",
            "observed", "no_pending_pair", "pending", "ineligible", "sensitive_input_skipped",
            "unavailable", "duplicate", "complete", "incomplete", "payload_too_large",
            "drained", "busy", "starting", "running"}
ERRORS = {"entrypoint_missing", "child_failed", "child_timeout", "protocol_error",
          "invalid_event", "incomplete", "worker_spawn_failed", "worker_failed", "worker_died"}
MAX_STATE = 65536
MAX_RECORDS = 32


def memory_root() -> Path:
    override = os.environ.get("RHIZE_CONTEXT_HOME")
    if override:
        return Path(override).expanduser() / "memory-context"
    base = Path(os.environ["XDG_DATA_HOME"]).expanduser() if os.environ.get("XDG_DATA_HOME") else Path.home() / ".local/share"
    return base / "rhize/context-manager/memory-context"


def installation(root: Path) -> str:
    return hashlib.sha256(str(root.absolute()).encode()).hexdigest()[:24]


class Health:
    def __init__(self, plugin: Path, root: Path | None = None):
        self.install = installation(plugin)
        self.deadline = None
        self.root = (root if root is not None else memory_root() / "hook-health-v1").absolute()

    @contextmanager
    def directory(self):
        # Walk using directory descriptors: no symlink-parent check/open race.
        fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
        try:
            for part in self.root.parts[1:]:
                if part in {".", ".."}:
                    raise ValueError("unsafe diagnostic root")
                try:
                    os.mkdir(part, 0o700, dir_fd=fd)
                except FileExistsError:
                    pass
                next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = next_fd
            os.fchmod(fd, 0o700)
            yield fd
        finally:
            os.close(fd)

    @staticmethod
    def open_file(directory: int, name: str, flags: int) -> int:
        flags |= os.O_NOFOLLOW | os.O_NONBLOCK
        # Separate exclusive creation from reopening: concurrent O_CREAT|O_NOFOLLOW
        # on macOS can report ENOENT while the other caller creates the same file.
        if flags & os.O_CREAT and not flags & os.O_EXCL:
            try:
                fd = os.open(name, flags | os.O_EXCL, 0o600, dir_fd=directory)
            except FileExistsError:
                fd = os.open(name, flags & ~os.O_CREAT, dir_fd=directory)
        else:
            fd = os.open(name, flags, 0o600, dir_fd=directory)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid():
            os.close(fd)
            raise ValueError("unsafe diagnostic file")
        os.fchmod(fd, 0o600)
        return fd

    @contextmanager
    def lock(self, name: str = ".lock", wait: float = 0.2):
        if self.deadline is not None:
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("diagnostic deadline")
            wait = min(wait, remaining)
        with self.directory() as directory:
            fd = self.open_file(directory, name, os.O_CREAT | os.O_RDWR)
            try:
                deadline = time.monotonic() + wait
                while True:
                    try:
                        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except BlockingIOError:
                        if time.monotonic() >= deadline:
                            raise TimeoutError("diagnostic lock busy") from None
                        time.sleep(0.01)
                yield fd
            finally:
                # close only: LOCK_UN would also unlock an inherited worker fd.
                os.close(fd)

    @staticmethod
    def validate(state: dict) -> None:
        if not isinstance(state, dict) or set(state) != {"version", "records"} or state["version"] != 1:
            raise ValueError("invalid diagnostic state")
        rows = state["records"]
        fields = {"installation", "host", "lane", "outcome", "error", "reported", "failures",
                  "updated", "firstFailure", "exitCode", "launchId", "workerState"}
        if not isinstance(rows, dict) or len(rows) > MAX_RECORDS:
            raise ValueError("invalid diagnostic records")
        for key, r in rows.items():
            if not isinstance(r, dict) or set(r) != fields:
                raise ValueError("invalid diagnostic record")
            if (not isinstance(r["installation"], str) or not re.fullmatch(r"[a-f0-9]{24}", r["installation"])
                    or r["host"] not in {"claude", "codex"} or r["lane"] not in {*EVENTS, "worker"}
                    or key != f'{r["installation"]}:{r["host"]}:{r["lane"]}'
                    or r["outcome"] not in OUTCOMES | {None} or r["error"] not in ERRORS | {None}
                    or type(r["reported"]) is not bool or type(r["failures"]) is not int
                    or not 0 <= r["failures"] <= 1000000000
                    or r["workerState"] not in {"idle", "starting", "running"}
                    or (r["launchId"] is not None and (not isinstance(r["launchId"], str)
                        or not re.fullmatch(r"[a-f0-9]{32}", r["launchId"])))
                    or (r["exitCode"] is not None and (type(r["exitCode"]) is not int or not -255 <= r["exitCode"] <= 255))):
                raise ValueError("invalid diagnostic fields")
            for field in ("updated", "firstFailure"):
                if type(r[field]) not in (float, int) or not math.isfinite(r[field]) or r[field] < 0:
                    raise ValueError("invalid diagnostic timestamp")

    def transaction(self, action, wait: float = 0.2):
        with self.lock(wait=wait), self.directory() as directory:
            try:
                fd = self.open_file(directory, "state.json", os.O_RDONLY)
            except FileNotFoundError:
                state = {"version": 1, "records": {}}
            else:
                with os.fdopen(fd, "rb") as stream:
                    raw = stream.read(MAX_STATE + 1)
                if len(raw) > MAX_STATE:
                    raise ValueError("diagnostic state too large")
                state = json.loads(raw)
            self.validate(state)
            result = action(state["records"])
            self.validate(state)
            raw = json.dumps(state, sort_keys=True).encode()
            if len(raw) > MAX_STATE:
                raise ValueError("diagnostic state too large")
            name = ".state-" + uuid.uuid4().hex
            try:
                fd = self.open_file(directory, name, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                with os.fdopen(fd, "wb") as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(name, "state.json", src_dir_fd=directory, dst_dir_fd=directory)
            finally:
                try:
                    os.unlink(name, dir_fd=directory)
                except FileNotFoundError:
                    pass
            return result

    def record(self, rows: dict, host: str, lane: str) -> dict:
        key = f"{self.install}:{host}:{lane}"
        if key not in rows:
            if len(rows) >= MAX_RECORDS:
                old = [k for k, r in rows.items() if r["installation"] != self.install
                       and r["workerState"] == "idle"]
                if not old:
                    raise ValueError("diagnostic capacity unavailable")
                del rows[min(old, key=lambda k: rows[k]["updated"])]
            rows[key] = {"installation": self.install, "host": host, "lane": lane,
                         "outcome": None, "error": None, "reported": False, "failures": 0,
                         "updated": 0, "firstFailure": 0, "exitCode": None,
                         "launchId": None, "workerState": "idle"}
        return rows[key]

    @staticmethod
    def fail(record: dict, code: str, exit_code: int | None = None):
        now = time.time()
        if record["error"] is None:
            record.update(firstFailure=now, reported=False)
        record.update(error=code, exitCode=exit_code, updated=now,
                      failures=min(1000000000, record["failures"] + 1))

    def outcome(self, host: str, lane: str, outcome: str | None = None, error: str | None = None,
                exit_code: int | None = None, launch_id: str | None = None):
        def update(rows):
            r = self.record(rows, host, lane)
            if launch_id is not None and r["launchId"] != launch_id:
                return
            if error:
                self.fail(r, error, exit_code)
            elif outcome != "busy":
                r.update(error=None, reported=False, exitCode=None)
            r.update(outcome=outcome, updated=time.time())
            if lane == "worker":
                r["workerState"] = "idle"
        self.transaction(update)

    def inspect_worker(self):
        try:
            with self.lock("worker.lock", wait=0):
                def update(rows):
                    for r in rows.values():
                        if r["lane"] == "worker" and r["workerState"] != "idle":
                            self.fail(r, "worker_died")
                            r["workerState"] = "idle"
                self.transaction(update)
        except TimeoutError:
            pass  # Held launch lock is the authoritative live-worker signal.

    def warnings(self, host: str) -> bool:
        def update(rows):
            active = [r for r in rows.values() if r["installation"] == self.install
                      and r["host"] == host and r["error"] and not r["reported"]]
            for r in active:
                r["reported"] = True
            return bool(active)
        return self.transaction(update)

    def status(self) -> dict:
        try:
            self.inspect_worker()
            rows = self.transaction(lambda rows: [dict(r) for r in rows.values() if r["installation"] == self.install])
            for r in rows:
                r["longRunning"] = r["workerState"] != "idle" and time.time() - r["updated"] > 900
            return {"status": "degraded" if any(r["error"] for r in rows) else "operational" if rows else "not_run",
                    "records": rows, "measurementCompleteness": "see_pair_receipts"}
        except (OSError, ValueError, TypeError):
            return {"status": "unavailable", "records": [], "measurementCompleteness": "unknown"}
