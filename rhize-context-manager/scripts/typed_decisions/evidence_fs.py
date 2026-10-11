"""Private-file helpers shared by the evidence scripts (stdlib only).

Directories are 0700, files 0600, symlinks are refused, writes are atomic. These helpers never see
prompt or transcript text: callers pass hashes, counts and manifests only.
"""
from __future__ import annotations

import contextlib
import fcntl
import os
import stat
import tempfile
from pathlib import Path


def private_dir(path, anchor=None) -> Path:
    """Create `path` (and missing parents) as 0700 directories; refuse symlinked components at or below `anchor`.

    Delegates to the contract rule (records.private_dir) so the store has one symlink policy.
    """
    from typed_decisions import records
    return records.private_dir(path, anchor)


def tighten(path) -> None:
    """chmod 0700 an existing real directory we own. records.append() creates the intermediate directories of a
    new store with the umask (only the leaf is 0700), so the scripts that own a store tighten it before use."""
    path = Path(path)
    try:
        info = path.lstat()
    except OSError:
        return
    if stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) != 0o700:
        try:
            os.chmod(path, 0o700)
        except OSError:
            pass


def write_private_atomic(path, data: bytes) -> None:
    """Write `data` to `path` through a 0600 temp file in the same directory, fsync, then os.replace."""
    path = Path(path)
    if path.is_symlink():
        raise ValueError('symlinked path refused')
    private_dir(path.parent)
    handle, temporary = tempfile.mkstemp(prefix='.tmp-', dir=str(path.parent))
    try:
        with os.fdopen(handle, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_regular(path, max_bytes: int) -> bytes:
    """Bytes of a regular, non-symlink file no larger than `max_bytes`; OSError/ValueError otherwise."""
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > max_bytes:
            raise ValueError('not a regular file within the size limit')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            data = stream.read(max_bytes + 1)
    finally:
        os.close(fd)
    if len(data) > max_bytes:
        raise ValueError('file exceeds the size limit')
    return data


@contextlib.contextmanager
def exclusive_lock(path):
    """Non-blocking exclusive flock on `path` (created 0600). Yields True when held, False when busy."""
    private_dir(Path(path).parent)
    fd = os.open(path, os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    held = False
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            held = True
        except OSError:
            held = False
        yield held
    finally:
        if held:
            with contextlib.suppress(OSError):
                fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
