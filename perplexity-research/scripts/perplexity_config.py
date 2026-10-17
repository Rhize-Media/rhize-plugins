#!/usr/bin/env python3
"""Load private JSON settings; launch MCP without evaluating shell configuration."""
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def load_config():
    settings = json.loads((ROOT / 'config/defaults.json').read_text())
    path = Path.home() / '.config/perplexity-research/config.json'
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        pass
    else:
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or info.st_mode & 0o077 or info.st_nlink != 1):
                raise ValueError('configuration must be an owned private regular file')
            raw = stream.read(8193)
        if len(raw) > 8192:
            raise ValueError('configuration exceeds 8192 bytes')
        overrides = json.loads(raw)
        if not isinstance(overrides, dict) or set(overrides) - settings.keys():
            raise ValueError('unknown configuration fields')
        settings.update(overrides)
    for key in ('pythonExecutable', 'stateDir', 'authorizationReference'):
        value = settings[key]
        if key == 'pythonExecutable' and value is None:
            continue
        if (not isinstance(value, str) or not value.startswith(('/', '~/'))
                or any(ord(c) < 32 for c in value)):
            raise ValueError('invalid configuration path')
        path = Path(value).expanduser()
        if not path.is_absolute():
            raise ValueError('configuration paths must be absolute or start with ~/')
        settings[key] = str(path)
    if not isinstance(settings['keychainService'], str) or not re.fullmatch(
            r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', settings['keychainService']):
        raise ValueError('invalid Keychain service name')
    return settings


def launch():
    try:
        settings = load_config()
        runtime = settings['pythonExecutable']
        if runtime is None or not os.access(runtime, os.X_OK) or not Path(runtime).is_file():
            raise ValueError('select an absolute Python executable in ~/.config/perplexity-research/config.json')
        check = subprocess.run([runtime, '-I', '-c',
                                'import sys; assert sys.version_info >= (3, 10); import cryptography'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        if check.returncode:
            raise ValueError('Python 3.10+ with cryptography is required')
        os.execv(runtime, [runtime, '-I', str(ROOT / 'scripts/perplexity_research_mcp.py')])
    except (OSError, ValueError, subprocess.TimeoutExpired):
        # Do not echo configuration values or parser excerpts into host logs.
        print('Perplexity setup invalid: check private config.json and Python 3.10+ with cryptography; see README.', file=sys.stderr)
        return 78


if __name__ == '__main__':
    sys.exit(launch())
