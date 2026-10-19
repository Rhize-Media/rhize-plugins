"""Shared lock for candidate append and atomic Stop updates; no registry access."""
from contextlib import contextmanager
import fcntl
import os
import stat
import sys


@contextmanager
def queue_lock(path):
    os.makedirs(os.path.dirname(path) or '.', mode=0o700, exist_ok=True)
    fd = os.open(path + '.lock', os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode) or os.path.islink(path):
            raise ValueError('unsafe candidate queue')
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def append(path, raw):
    if not raw:
        return
    with queue_lock(path):
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NONBLOCK
                     | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ValueError('unsafe candidate queue')
            os.write(fd, raw)
        finally:
            os.close(fd)


if __name__ == '__main__':
    try:
        append(sys.argv[1], sys.stdin.buffer.read())
    except (OSError, ValueError):
        pass  # advisory capture cannot block the task
