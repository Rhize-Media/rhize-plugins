"""Atomic repository/capability leases for concurrent agent sessions."""

from __future__ import annotations

import hashlib
import json
import os
import time
import fcntl
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Lease:
    path: Path
    key: str
    owner: str


class LeaseStore:
    def __init__(self, directory: Path, ttl_seconds: int, now=time.time) -> None:
        self.directory = directory
        self.ttl_seconds = ttl_seconds
        self._now = now

    def claim(self, key: str, owner: str) -> Lease | None:
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = self.directory / f"{hashlib.sha256(key.encode()).hexdigest()}.lease"
        gate = self._gate(path)
        with gate:
            self._remove_if_stale(path)
            payload = json.dumps(
                {"keyHash": hashlib.sha256(key.encode()).hexdigest(), "owner": owner},
                sort_keys=True,
            ).encode()
            try:
                descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                return None
            try:
                os.write(descriptor, payload)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        return Lease(path=path, key=key, owner=owner)

    def release(self, lease: Lease) -> None:
        with self._gate(lease.path):
            try:
                payload = json.loads(lease.path.read_text(encoding="utf-8"))
            except (FileNotFoundError, OSError, json.JSONDecodeError):
                return
            if payload.get("owner") == lease.owner:
                lease.path.unlink(missing_ok=True)

    def _remove_if_stale(self, path: Path) -> None:
        try:
            age = self._now() - path.stat().st_mtime
        except FileNotFoundError:
            return
        if age > self.ttl_seconds:
            path.unlink(missing_ok=True)

    def _gate(self, lease_path: Path):
        return _FileGate(lease_path.with_suffix(".lock"))


class _FileGate:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.descriptor = -1

    def __enter__(self) -> "_FileGate":
        self.descriptor = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        fcntl.flock(self.descriptor, fcntl.LOCK_EX)
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        fcntl.flock(self.descriptor, fcntl.LOCK_UN)
        os.close(self.descriptor)
        self.descriptor = -1
