"""Small private-file primitives shared by the registry, cohort and cycle code (lane L3).

Everything here is stdlib only and follows the typed-decision storage rules (plan §4.4): directories
are 0700, files 0600, symlinks are refused, writes that replace content go through a temp file in the
same directory plus fsync plus os.replace, and appended lines are fsynced.
"""
from __future__ import annotations

import contextlib
import fcntl
import json
import os
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path

NOFOLLOW = getattr(os, 'O_NOFOLLOW', 0)
MAX_JSON_BYTES = 1 << 20

# Indirection so tests can simulate a crash between the audit intent and the state replace.
replace_file = os.replace


def utc(value=None) -> datetime:
    """datetime | ISO-8601 string | None -> aware UTC datetime (None means now)."""
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError('timestamp must carry a timezone')
        return value.astimezone(timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            raise ValueError('invalid timestamp') from None
        if parsed.tzinfo is None:
            raise ValueError('timestamp must carry a timezone')
        return parsed.astimezone(timezone.utc)
    raise ValueError('invalid timestamp')


def iso(value=None) -> str:
    """Second-resolution UTC ISO-8601 with a Z suffix (accepted by every contract validator)."""
    return utc(value).strftime('%Y-%m-%dT%H:%M:%SZ')


def private_dir(path, anchor=None) -> Path:
    """Create a 0700 directory chain, refusing symlinked components at or below `anchor`.

    Delegates to the contract rule (records.private_dir) so the store has one symlink policy.
    """
    from typed_decisions import records
    return records.private_dir(path, anchor)


def fsync_dir(path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


@contextlib.contextmanager
def file_lock(path, timeout: float = 10.0):
    """Exclusive advisory lock (fcntl.flock) on a 0600 lock file; TimeoutError when busy for `timeout` s."""
    path = Path(path)
    private_dir(path.parent)
    fd = os.open(path, os.O_CREAT | os.O_RDWR | NOFOLLOW, 0o600)
    deadline = time.monotonic() + timeout
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError('lock_timeout') from None
                time.sleep(0.01)
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def try_lock(path):
    """Non-blocking variant: returns an open fd holding the lock, or None when it is held elsewhere."""
    path = Path(path)
    private_dir(path.parent)
    fd = os.open(path, os.O_CREAT | os.O_RDWR | NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return None
    return fd


def release_lock(fd) -> None:
    if fd is not None:
        with contextlib.suppress(OSError):
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def read_json_file(path):
    """Parsed JSON object from a regular, non-symlink file, or raise ValueError/FileNotFoundError."""
    fd = os.open(path, os.O_RDONLY | NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        raw = stream.read(MAX_JSON_BYTES + 1)
    if len(raw) > MAX_JSON_BYTES:
        raise ValueError('file too large')
    try:
        return json.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError('invalid json') from None


def write_private_atomic(path, data: bytes) -> None:
    """tmp file (0600, O_EXCL) + fsync + os.replace + dir fsync."""
    path = Path(path)
    private_dir(path.parent)
    tmp = path.with_name(f'{path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp')
    fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY | NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        replace_file(tmp, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
    fsync_dir(path.parent)


def write_private_exclusive(path, data: bytes) -> None:
    """Publish a new 0600 file atomically: temp file + fsync + hard link (FileExistsError when `path` exists)."""
    path = Path(path)
    private_dir(path.parent)
    tmp = path.with_name(f'{path.name}.{os.getpid()}.{secrets.token_hex(4)}.new')
    fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY | NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(tmp, path)
    finally:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
    fsync_dir(path.parent)


def append_line(path, obj) -> None:
    """Append one JSON line (fsynced). A torn final line from an earlier crash is terminated first."""
    path = Path(path)
    private_dir(path.parent)
    line = (json.dumps(obj, separators=(',', ':'), ensure_ascii=False, sort_keys=True) + '\n').encode('utf-8')
    fd = os.open(path, os.O_RDWR | os.O_APPEND | os.O_CREAT | NOFOLLOW, 0o600)
    try:
        size = os.fstat(fd).st_size
        if size:
            os.lseek(fd, size - 1, os.SEEK_SET)
            if os.read(fd, 1) != b'\n':
                line = b'\n' + line
        os.write(fd, line)
        os.fsync(fd)
    finally:
        os.close(fd)
