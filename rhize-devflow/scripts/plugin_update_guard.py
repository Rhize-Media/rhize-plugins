#!/usr/bin/env python3
"""Hold native sessions across Rhize package changes; never update packages or host trust."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import stat
import sys
import tempfile
import time

MAX_BYTES = 65536
MAX_INPUT = 16 * 1024 * 1024
RESTART = ('Rhize plugin restart required. Save the task checkpoint and stop tools. Close all Claude/Codex '
           'sessions before updating installed plugins from a separate terminal, then restart the hosts. '
           'Never retry missing-hook errors or disable required guards.')


def rhize_target(value):
    value = value.lower().replace(' ', '-')
    return (value == 'rhize-plugins' or value.endswith('@rhize-plugins') or value.startswith('rhize-')
            or value in {'procedural-memory', 'project-launcher', 'seo-aeo-geo', 'obsidian-second-brain'})


def mutates_plugins(command, depth=0):
    """Recognize native CLI mutations, not arbitrary programs that could execute them."""
    if depth > 2 or len(command) > MAX_BYTES:
        return False
    lexer = shlex.shlex(command, posix=True, punctuation_chars=';&|()\n')
    lexer.whitespace = ' \t\r'
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError:
        return False
    segments, current = [], []
    for token in tokens + [';']:
        if token and all(c in ';&|()\n' for c in token):
            segments.append(current)
            current = []
        else:
            current.append(token)
    for args in segments:
        while args and (args[0] in {'env', 'command', 'rtk', 'proxy'} or '=' in args[0]
                        or args[0].startswith('-')):
            args = args[1:]
        if not args:
            continue
        name = Path(args[0]).name
        if name in {'bash', 'sh', 'zsh'}:
            for index, arg in enumerate(args[1:-1], 1):
                if arg.startswith('-') and 'c' in arg and mutates_plugins(args[index + 1], depth + 1):
                    return True
        if name not in {'claude', 'codex'} or '--help' in args or '-h' in args:
            continue
        if 'plugin' not in args:
            continue
        rest = args[args.index('plugin') + 1:]
        if rest and rest[0] == 'marketplace':
            rest = rest[1:]
            verbs = {'update', 'upgrade', 'remove', 'add'}
        else:
            verbs = {'update', 'upgrade', 'install', 'add', 'uninstall', 'remove'}
        if rest and rest[0] in verbs:
            targets = [x for x in rest[1:] if not x.startswith('-')]
            if not targets or any(rhize_target(x) for x in targets):
                return True
    return False


def fingerprint(home):
    """Version/content metadata only; never inspect prompts, credentials or host approvals."""
    files = []
    for host in ('.claude', '.codex'):
        files.extend((home / host / 'plugins/cache/rhize-plugins').glob('*/*/.claude-plugin/plugin.json'))
    if len(files) > 256:
        raise ValueError('package_inventory_limit')
    values = []
    for path in sorted(files):
        info = path.stat()
        if any(p.is_symlink() for p in (path, *path.parents)) or info.st_size > MAX_BYTES:
            raise ValueError('package_metadata_unavailable')
        values.append((str(path.relative_to(home)), info.st_ino, info.st_mtime_ns,
                       hashlib.sha256(path.read_bytes()).hexdigest()))
    return hashlib.sha256(json.dumps(values).encode()).hexdigest()


def drift(payload):
    identity = payload.get('session_id')
    if not isinstance(identity, str) or not identity.strip():
        raise ValueError('native_session_missing')
    home = Path.home()
    root = Path(os.environ.get('XDG_DATA_HOME', str(home / '.local/share'))) / 'rhize/plugin-update-safety'
    if not root.is_absolute() or any(p.is_symlink() for p in (root, *root.parents)):
        raise ValueError('unsafe_state_path')
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Including the loaded package path separates a genuinely reloaded install from its old session.
    key = hashlib.sha256((identity + '\0' + str(Path(__file__).resolve().parent)).encode()).hexdigest()
    path = root / (key + '.json')
    fd = os.open(root / (key + '.lock'), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'r+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        current = fingerprint(home)
        old = None
        if path.exists() or path.is_symlink():
            handle = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(handle, 'r') as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
                    raise ValueError('invalid_session_state')
                old = json.loads(stream.read(MAX_BYTES + 1))
            if (not isinstance(old, dict) or old.get('schema') != 'rhize-plugin-session-v1'
                    or not re.fullmatch('[0-9a-f]{64}', old.get('fingerprint', ''))
                    or type(old.get('restartRequired')) is not bool):
                raise ValueError('invalid_session_state')
        if (payload.get('hook_event_name') == 'SessionStart'
                and payload.get('source') in {'startup', 'resume'} and old is not None):
            # A native reload may resume the same chat with the same Dev Flow version.
            os.rename(path, root / (key + '.prior-' + str(time.time_ns()) + '.json'))
            old = None
        held = old is not None and (old['restartRequired'] or old['fingerprint'] != current)
        first = held and not old['restartRequired']
        if old is None or first:
            value = {'schema': 'rhize-plugin-session-v1', 'fingerprint': old['fingerprint'] if old else current,
                     'restartRequired': held}
            temp_fd, temporary = tempfile.mkstemp(prefix='.session-', dir=root)
            try:
                with os.fdopen(temp_fd, 'w') as stream:
                    json.dump(value, stream)
                os.replace(temporary, path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        return held, first


def deny():
    return {'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'deny',
                                  'permissionDecisionReason': RESTART}}


def main():
    event = sys.argv[1]
    try:
        raw = sys.stdin.buffer.read(MAX_INPUT + 1)
        if len(raw) > MAX_INPUT:
            raise ValueError('input_limit')
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError('invalid_envelope')
        if payload.get('hook_event_name') != event:
            raise ValueError('hook_event_mismatch')
        value = payload.get('tool_input') or {}
        command = (value.get('command') or value.get('cmd') or '') if isinstance(value, dict) else value
        # Code Mode's nested execution tools are guarded separately; edits and prose are not commands.
        tool = payload.get('tool_name', '')
        if not isinstance(tool, str):
            raise ValueError('invalid_tool_name')
        tool = tool.split('.')[-1]
        if event == 'PreToolUse' and tool.endswith('uninstall_plugin') and isinstance(value, dict) \
                and isinstance(value.get('plugin'), str) and rhize_target(value['plugin']):
            print(json.dumps(deny()))
            return 0
        if event == 'PreToolUse' and tool in {'Bash', 'exec_command'} and isinstance(command, str) \
                and mutates_plugins(command):
            print(json.dumps(deny()))
            return 0
        held, first = drift(payload)
        if event == 'PreToolUse' and held:
            print(json.dumps(deny()))
        elif event == 'PostToolUse' and first:
            print(json.dumps({'continue': False, 'stopReason': RESTART, 'systemMessage': RESTART}))
        elif event in {'Stop', 'SessionStart'} and held:
            print(json.dumps({'continue': False, 'stopReason': RESTART}))
    except (OSError, ValueError, TypeError, RecursionError):
        if event == 'PreToolUse':
            print(json.dumps(deny()))
        else:
            print(json.dumps({'continue': False, 'stopReason': RESTART,
                              'systemMessage': 'Plugin session metadata unavailable. ' + RESTART}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
