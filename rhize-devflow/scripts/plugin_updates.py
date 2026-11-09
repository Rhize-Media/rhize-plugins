#!/usr/bin/env python3
"""Approved Rhize package maintenance after each macOS host's native owners exit."""
from __future__ import annotations

import argparse
import ctypes
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time

SOURCE = 'https://github.com/Rhize-Media/rhize-plugins.git'
SCHEMA = 'rhize-plugin-updates-v1'
HOSTS = ('codex', 'claude')
EVENTS = ('SessionStart', 'UserPromptSubmit', 'PreToolUse', 'Stop', 'SessionEnd')
LIMIT = 1024 * 1024


def root():
    return Path.home() / '.local/share/rhize/plugin-updates'


def safe(path):
    if not path.is_absolute() or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('unsafe_state_path')
    if path.exists() and path.stat().st_uid != os.getuid():
        raise ValueError('foreign_state_owner')
    return path


def read(path):
    safe(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd) as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > LIMIT:
            raise ValueError('invalid_state_file')
        return json.load(stream)


def write(path, value):
    safe(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


@contextmanager
def locked(host):
    folder = safe(root() / host)
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(folder / 'worker.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield folder


def run(args, timeout=120):
    process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                               stdin=subprocess.DEVNULL, start_new_session=True)
    try:
        output, _ = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        # Kill only our native command group; git children must not outlive the maintenance lock.
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate()
        raise
    if process.returncode:
        # Native output may contain private configuration; keep only the failing command category.
        raise RuntimeError(f'native_command_failed:{Path(args[0]).name}:{process.returncode}')
    if len(output) > 16 * LIMIT:
        raise ValueError('native_output_limit')
    return output


def arguments(pid):
    """macOS argv, in memory only; ps rendering loses argument boundaries."""
    libc = ctypes.CDLL(None, use_errno=True)
    mib = (ctypes.c_int * 3)(1, 49, pid)  # CTL_KERN, KERN_PROCARGS2
    size = ctypes.c_size_t(1024 * 1024)
    buffer = ctypes.create_string_buffer(size.value)
    if libc.sysctl(mib, 3, buffer, ctypes.byref(size), None, 0):
        raise OSError(ctypes.get_errno(), 'process_arguments_unavailable')
    raw = buffer.raw[:size.value]
    argc = ctypes.c_int.from_buffer_copy(raw[:4]).value
    pos = raw.index(b'\0', 4) + 1
    while pos < len(raw) and raw[pos] == 0:
        pos += 1
    if not 0 < argc < 65536:
        raise ValueError('process_arguments_invalid')
    return [part.decode('utf-8', 'replace') for part in raw[pos:].split(b'\0', argc)[:argc]]


def classify(command, argv):
    name = Path(command).name
    if name in {'Claude', 'Codex'}:
        return name.lower()
    host = next((h for h in HOSTS if name == h or name.startswith(h + '-aarch64-')
                 or name.startswith(h + '-x86_64-')), None)
    if name in {'node', 'bun', 'nodejs'} and len(argv) > 1:
        script = argv[1]
        if '/@anthropic-ai/claude-code/' in script:
            host = 'claude'
        elif '/@openai/codex/' in script:
            host = 'codex'
        argv = argv[1:]
    # These workers expose tools, not native plugin sessions; no broad ancestor exclusion.
    if host == 'codex' and len(argv) > 1 and argv[1] == 'mcp-server':
        return None
    return host


def owners(host):
    rows = run(['/bin/ps', '-axo', 'uid=,pid=,comm=']).splitlines()
    found = []
    for line in rows:
        parts = line.strip().split(None, 2)
        if len(parts) != 3 or not parts[0].lstrip('-').isdigit() or not parts[1].isdigit():
            raise ValueError('process_inventory_invalid')
        uid, pid, command = int(parts[0]), int(parts[1]), parts[2]
        if uid != os.getuid():
            continue
        name = Path(command).name
        if name not in {'Claude', 'Codex', 'claude', 'codex', 'node', 'nodejs', 'bun'} and not re.match(r'(claude|codex)-(aarch64|x86_64)-', name):
            continue
        try:
            argv = arguments(pid)
        except OSError:
            # A process may exit between ps and sysctl. Only proven exit is harmless.
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                continue
            raise
        if classify(command, argv) == host:
            found.append(pid)
    return found


def inventory(host, cli, targets):
    argv = [cli, 'plugin', 'list', '--json']
    if host == 'codex':
        argv += ['--marketplace', 'rhize-plugins']
    data = json.loads(run(argv))
    rows = data['installed'] if host == 'codex' else data
    selected = {}
    for name in targets:
        matches = [p for p in rows if p.get('pluginId', p.get('id')) == name + '@rhize-plugins'
                   and (host == 'codex' or p.get('scope') == 'user')]
        if len(matches) != 1 or type(matches[0].get('enabled')) is not bool:
            raise ValueError('expected_existing_install:' + name)
        p = matches[0]
        path = (Path.home() / '.codex/plugins/cache/rhize-plugins' / name / p['version']
                if host == 'codex' else Path(p['installPath']))
        manifest = read(path / '.claude-plugin/plugin.json')
        if manifest.get('name') != name or manifest.get('version') != p['version']:
            raise ValueError('installed_manifest_mismatch:' + name)
        selected[name] = {'version': p['version'], 'enabled': p['enabled'], 'path': str(path)}
    return selected


def marketplace(host, cli):
    if host == 'codex':
        matches = [p for p in json.loads(run([cli, 'plugin', 'marketplace', 'list', '--json']))['marketplaces']
                   if p['name'] == 'rhize-plugins']
        if len(matches) != 1 or matches[0]['marketplaceSource'] != {'sourceType': 'git', 'source': SOURCE}:
            raise ValueError('marketplace_source_changed')
        return Path(matches[0]['root'])
    item = read(Path.home() / '.claude/plugins/known_marketplaces.json')['rhize-plugins']
    if item['source'] != {'source': 'git', 'url': SOURCE}:
        raise ValueError('marketplace_source_changed')
    return Path(item['installLocation'])


def validate_targets(targets):
    if not isinstance(targets, dict) or not 1 <= len(targets) <= 20:
        raise ValueError('invalid_targets')
    for name, version in targets.items():
        if not re.fullmatch('[a-z][a-z0-9-]{1,60}', name) or not isinstance(version, str) or not re.fullmatch(r'\d+\.\d+\.\d+', version):
            raise ValueError('invalid_target')



def approved_packages(commit, targets):
    # Read committed objects from the coordinator checkout, never refresh a live host catalog.
    catalog = json.loads(run(['/usr/bin/git', '--no-replace-objects', 'show', commit + ':.claude-plugin/marketplace.json']))
    result = {}
    for name, version in targets.items():
        entries = [p for p in catalog['plugins'] if p.get('name') == name]
        if len(entries) != 1 or entries[0].get('version') != version or entries[0].get('source') != './' + name:
            raise ValueError('reviewed_package_mismatch:' + name)
        tree = run(['/usr/bin/git', '--no-replace-objects', 'rev-parse', commit + ':' + name]).strip()
        if (not re.fullmatch('[0-9a-f]{40}', tree)
                or run(['/usr/bin/git', '--no-replace-objects', 'cat-file', '-t', commit + ':' + name]).strip() != 'tree'):
            raise ValueError('reviewed_tree_unavailable:' + name)
        result[name] = {'entry': entries[0], 'tree': tree}
    return result


def queue(host, targets, commit, after=None, reconcile=False):
    validate_targets(targets)
    if not re.fullmatch('[0-9a-f]{40}', commit):
        raise ValueError('reviewed_commit_required')
    config = read(root() / 'config.json')
    cli = config['cli'][host]
    with locked(host) as folder:
        path = folder / 'status.json'
        if path.exists() and read(path)['phase'] not in {'complete', 'held'}:
            raise ValueError('queue_already_pending')
        if path.exists():
            previous = read(path)
            if previous.get('mutationStarted') and previous['phase'] == 'held' and not reconcile:
                raise ValueError('held_partial_mutation_requires_reconcile')
            digest = hashlib.sha256(json.dumps(previous, sort_keys=True).encode()).hexdigest()
            write(folder / 'history' / (digest + '.json'), previous)
        before = inventory(host, cli, targets)
        if host == 'codex' and any(not row['enabled'] for row in before.values()):
            raise ValueError('disabled_codex_plugin_requires_native_preservation_support')
        marketplace(host, cli)
        approved = approved_packages(commit, targets)
        value = {'schema': SCHEMA, 'host': host, 'phase': 'pending', 'targets': targets,
                 'commit': commit, 'approvedPackages': approved, 'before': before, 'queuedAt': time.time(),
                 'generation': read(path)['generation'] if path.exists() else 0,
                 'after': after, 'mutationStarted': False,
                 'repairRequired': bool(reconcile and path.exists() and previous.get('mutationStarted')),
                 'reconciledFrom': digest if reconcile and path.exists() else None}
        write(path, value)
        return value


def notice(host, phase):
    message = f'Rhize {host} plugin updates: {phase}. Details in ~/.local/share/rhize/plugin-updates/{host}/status.json'
    try:
        subprocess.run(['/usr/bin/osascript', '-e', 'display notification ' + json.dumps(message)
                        + ' with title "Rhize plugin updates"'], capture_output=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        pass  # Notification delivery never changes the verified update result.


def cache_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location('plugin_update_cache', Path(__file__).with_name('plugin_update_cache.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def admission(host):
    folder = safe(root() / host)
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(folder / 'admission.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as stream:
        deadline = time.monotonic() + 2
        while True:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise ValueError('publication_busy_try_after_completion')
                time.sleep(0.05)
        yield


def process_tokens(host, ancestors=False):
    """PID plus kernel start time prevents a reused PID inheriting an idle lease."""
    active = owners(host)
    rows = run(['/bin/ps', '-axo', 'pid=,ppid=,lstart=']).splitlines()
    parsed = {}
    for line in rows:
        fields = line.strip().split(None, 2)
        if len(fields) != 3 or not fields[0].isdigit() or not fields[1].isdigit():
            raise ValueError('process_identity_unavailable')
        parsed[int(fields[0])] = (int(fields[1]), fields[2])
    if ancestors:
        lineage, pid = set(), os.getppid()
        while pid in parsed and pid not in lineage:
            lineage.add(pid)
            pid = parsed[pid][0]
        active = [pid for pid in active if pid in lineage]
    return {str(pid): parsed[pid][1] for pid in active if pid in parsed}


def idle_guard_ready(host, config):
    guard = Path(inventory(host, config['cli'][host], ['rhize-devflow'])['rhize-devflow']['path']) / 'scripts/plugin_update_guard.py'
    return hashlib.sha256(guard.read_bytes()).hexdigest() == config.get('idleGuardSha256')


def idle(host, active, config):
    if not active:
        return True
    if host != 'codex' or config.get('idleProtocol') != 1:
        return False
    if not idle_guard_ready(host, config):
        return False
    tokens = process_tokens(host)
    if (set(tokens) != {str(pid) for pid in active}
            or any(config.get('bootstrapOwners', {}).get(host, {}).get(pid) == token
                   for pid, token in tokens.items())):
        return False
    seen = {}
    paths = list((root() / host / 'sessions').glob('*.json'))
    if len(paths) > 10000:
        raise ValueError('session_inventory_limit')
    for path in paths:
        session = read(path)
        matching = {pid: token for pid, token in session.get('owners', {}).items() if tokens.get(pid) == token}
        if matching:
            if session.get('active') is not False or session.get('protocol') != 1:
                return False
            seen.update(matching)
    # Unknown owners and legacy hook generations retain the closed-host fallback.
    return seen == tokens



def worker(host):
    with locked(host) as folder:
        path = folder / 'status.json'
        if not path.exists():
            return
        state = read(path)
        if not isinstance(state, dict) or state.get('schema') != SCHEMA or state.get('host') != host:
            raise ValueError('invalid_queue')
        if state['phase'] in {'complete', 'held'}:
            return
        if state['phase'] == 'updating':
            state.update(phase='held', error='interrupted_update_requires_reconciliation')
            write(path, state)
            notice(host, 'held after an interrupted update')
            return
        try:
            validate_targets(state['targets'])
            approved = state.get('approvedPackages')
            if not isinstance(approved, dict) or approved.keys() != state['targets'].keys():
                raise ValueError('invalid_package_approval')
            for name, version in state['targets'].items():
                item = approved[name]
                entry = item.get('entry', {}) if isinstance(item, dict) else {}
                if (not isinstance(entry, dict) or entry.get('name') != name or entry.get('version') != version
                        or entry.get('source') != './' + name
                        or not isinstance(item.get('tree'), str)
                        or not re.fullmatch('[0-9a-f]{40}', item['tree'])):
                    raise ValueError('invalid_package_approval:' + name)
            config = read(root() / 'config.json')
            cli = config['cli'][host]
            active = owners(host)
            state['ownerCount'] = len(active)
            if not idle(host, active, config):
                state.update(phase='waiting_for_idle', quietSince=None)
                write(path, state)
                return
            if state.get('after'):
                dependency_path = root() / state['after'] / 'status.json'
                dependency = read(dependency_path) if dependency_path.exists() else {}
                if dependency.get('phase') != 'complete' or dependency.get('commit') != state['commit']:
                    state.update(phase='waiting_for_dependency')
                    write(path, state)
                    return
            now = time.time()
            activity_path = folder / 'activity.json'
            activity = read(activity_path)['sequence'] if activity_path.exists() else 0
            if activity != state.get('activityMark', 0):
                state.update(quietSince=None, activityMark=activity)
            if not state.get('quietSince'):
                state.update(phase='settling', quietSince=now)
                write(path, state)
                return
            if now - state['quietSince'] < 15:
                return
            validate_targets(state['targets'])
            current = inventory(host, cli, state['targets'])
            if current != state['before']:
                raise ValueError('installed_state_changed_since_approval')
            catalog_root = marketplace(host, cli)
            if not idle(host, owners(host), config):
                state.update(phase='waiting_for_idle', quietSince=None)
                write(path, state)
                return
            # Publish maintenance before any native mutation, including marketplace refresh.
            state.update(phase='staging')
            write(path, state)
            refresh = 'upgrade' if host == 'codex' else 'update'
            run([cli, 'plugin', 'marketplace', refresh, 'rhize-plugins'], timeout=300)
            resolved = run(['/usr/bin/git', '--no-replace-objects', '-C', str(catalog_root), 'rev-parse', 'HEAD']).strip()
            state['resolvedCommit'] = resolved
            catalog = json.loads(run(['/usr/bin/git', '--no-replace-objects', '-C', str(catalog_root),
                                      'show', resolved + ':.claude-plugin/marketplace.json']))
            versions = {p['name']: p.get('version') for p in catalog['plugins']}
            if any(versions.get(n) != v for n, v in state['targets'].items()):
                raise ValueError('reviewed_release_changed')
            for name in state['targets']:
                expected = state['approvedPackages'][name]
                entries = [p for p in catalog['plugins'] if p.get('name') == name]
                tree = run(['/usr/bin/git', '--no-replace-objects', '-C', str(catalog_root), 'rev-parse', resolved + ':' + name]).strip()
                if entries != [expected['entry']] or tree != expected['tree']:
                    raise ValueError('reviewed_package_changed:' + name)
            if run(['/usr/bin/git', '--no-replace-objects', '-C', str(catalog_root), 'status', '--porcelain', '--untracked-files=all', '--ignored=matching', '--',
                    '.claude-plugin/marketplace.json', *state['targets']]).strip():
                raise ValueError('catalog_worktree_changed')
            cache = cache_module()
            staged = state.get('staged')
            if host == 'codex' and staged is None:
                staged = cache.prepare(host, cli, catalog_root, state['targets'], folder, resolved)
                state['staged'] = staged
                write(path, state)
            with admission(host):
                activity = read(activity_path)['sequence'] if activity_path.exists() else 0
                if activity != state.get('activityMark', 0):
                    state.update(phase='settling', quietSince=None, activityMark=activity)
                    write(path, state)
                    return
                if not idle(host, owners(host), config):
                    state.update(phase='waiting_for_idle', quietSince=None)
                    write(path, state)
                    return
                if inventory(host, cli, state['targets']) != state['before']:
                    raise ValueError('installed_state_changed_before_publication')
                state.update(phase='updating', generation=time.time_ns(), mutationStarted=True,
                             cachePolicy='immutable-v1' if host == 'codex' else 'native-closed-host')
                write(path, state)
                if host == 'codex':
                    cache.publish(host, state['targets'], current, staged, read, write)
                else:
                    for name, version in state['targets'].items():
                        if owners(host):
                            raise ValueError('host_started_during_maintenance')
                        if current[name]['version'] != version:
                            run([cli, 'plugin', 'update', name + '@rhize-plugins', '--scope', 'user'], timeout=300)
            after = inventory(host, cli, state['targets'])
            state['installed'] = after
            if any(after[n]['version'] != v or after[n]['enabled'] != state['before'][n]['enabled']
                   for n, v in state['targets'].items()):
                raise ValueError('post_update_state_mismatch')
            devflow = inventory(host, cli, ['rhize-devflow'])['rhize-devflow']['path']
            doctor = json.loads(run([config['python'], str(Path(devflow) / 'scripts/devflow.py'), 'doctor', '--json']))
            write(folder / 'doctor.json', doctor)
            if doctor.get('healthy') is not True:
                raise ValueError('installed_doctor_unhealthy')
            state.update(phase='complete', completedAt=time.time(), nativeSessionVerified=False)
            write(path, state)
            notice(host, 'installed and verified; next session loads the new release')
        except Exception as error:
            state.update(phase='held', error=str(error)[:160], failedAt=time.time())
            write(path, state)
            notice(host, 'held; verification needs attention')


def hook(host, event, payload):
    with admission(host):
        path = root() / host / 'status.json'
        state = read(path) if path.exists() else None
        if state is not None and (not isinstance(state, dict) or state.get('schema') != SCHEMA or state.get('host') != host):
            raise ValueError('invalid_queue')
        identity = payload.get('session_id')
        if not isinstance(identity, str) or not identity:
            if state is None:
                return None
            raise ValueError('native_session_missing')
        key = hashlib.sha256(identity.encode()).hexdigest()
        session_path = root() / host / 'sessions' / (key + '.json')
        reset = event == 'SessionStart' and payload.get('source') in {'startup', 'resume'}
        old = read(session_path) if session_path.exists() and not reset else None
        busy = bool(state and (state['phase'] == 'updating' or
                    (state['phase'] == 'held' and state['mutationStarted']) or
                    (state.get('repairRequired', False) and state['phase'] != 'complete')))
        if old is None:
            old = {'generation': state['generation'] if state else 0, 'restartRequired': busy and state.get('cachePolicy') != 'immutable-v1',
                   'protocol': 1, 'active': True, 'owners': process_tokens(host, ancestors=True)}
        turn = payload.get('turn_id') or payload.get('turnId')
        if event in {'SessionStart', 'UserPromptSubmit', 'PreToolUse'}:
            old.update(active=True, owners=process_tokens(host, ancestors=True))
            if event in {'SessionStart', 'UserPromptSubmit'} or turn is not None:
                old['turn'] = turn
            activity_path = root() / host / 'activity.json'
            activity = read(activity_path)['sequence'] if activity_path.exists() else 0
            write(activity_path, {'sequence': activity + 1})
        elif event in {'Stop', 'SessionEnd'} and isinstance(turn, str) and turn and old.get('turn') == turn:
            old['active'] = False
        write(session_path, old)
        changed = state and old['generation'] != state['generation']
        if busy and state.get('cachePolicy') == 'immutable-v1':
            return 'Rhize plugin publication is being verified; wait for its completion receipt before another tool. Existing versions are retained.'
        if busy or old['restartRequired'] or (changed and state.get('cachePolicy') != 'immutable-v1'):
            return 'Rhize plugin maintenance is incomplete or this session crossed a legacy update. Preserve the checkpoint; reconcile the saved receipt before reopening. Required guards remain enabled.'
        return None


def hook_output(event, message):
    if event == 'PreToolUse':
        return {'hookSpecificOutput': {'hookEventName': event, 'permissionDecision': 'deny',
                                       'permissionDecisionReason': message}}
    return {'continue': False, 'stopReason': message}


def install():
    if sys.platform != 'darwin':
        raise ValueError('macOS_required')
    folder = safe(root())
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    cli = {host: shutil.which(host) for host in HOSTS}
    python = shutil.which('python3')
    if not all(cli.values()) or not python:
        raise ValueError('both_native_CLIs_required')
    destination = safe(folder / 'plugin_updates.py')
    # One stable runtime, outside caches; don't overwrite it while either worker owns its lock.
    with locked('codex'), locked('claude'):
        content = Path(__file__).read_bytes()
        fd, name = tempfile.mkstemp(dir=folder)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
        os.replace(name, destination)
        helper = Path(__file__).with_name('plugin_update_cache.py')
        shutil.copyfile(helper, folder / helper.name)
        config = {'schema': SCHEMA, 'cli': cli, 'python': python, 'path': os.environ['PATH'],
                  'runtimeSha256': hashlib.sha256(content).hexdigest(), 'idleProtocol': 1,
                  'bootstrapOwners': {host: process_tokens(host) for host in HOSTS},
                  'idleGuardSha256': hashlib.sha256(Path(__file__).with_name('plugin_update_guard.py').read_bytes()).hexdigest()}
        write(folder / 'config.json', config)
        for host in HOSTS:
            config_path = Path.home() / ('.claude/settings.json' if host == 'claude' else '.codex/hooks.json')
            # Codex global hooks may intentionally link into tracked claude-config.
            config_path = config_path.resolve()
            allowed = {Path.home() / '.claude/settings.json', Path.home() / '.codex/hooks.json',
                       Path.home() / '.claude/codex/hooks.json'}
            if config_path not in allowed:
                raise ValueError('unexpected_global_hook_target')
            data = read(config_path) if config_path.exists() else {}
            for event in EVENTS:
                invocation = shlex.join([python, '-I', str(destination), 'hook', host, event])
                missing = json.dumps(hook_output(event, 'Rhize update helper is unavailable; required maintenance guard did not run. Restart and repair the helper before continuing.'))
                command = f"if [ -f {shlex.quote(str(destination))} ] && [ -x {shlex.quote(python)} ]; then {invocation} || printf '%s\\n' {shlex.quote(missing)}; else printf '%s\\n' {shlex.quote(missing)}; fi"
                entries = data.setdefault('hooks', {}).setdefault(event, [])
                entries[:] = [e for e in entries if not any(str(destination) in h.get('command', '') for h in e.get('hooks', []))]
                entry = {'hooks': [{'type': 'command', 'command': command, 'timeout': 5}]}
                if event == 'PreToolUse':
                    entry['matcher'] = '*'
                entries.insert(0, entry)
            write(config_path, data)
            label = 'media.rhize.plugin-updates.' + host
            plist = Path.home() / 'Library/LaunchAgents' / (label + '.plist')
            safe(plist)
            plist.parent.mkdir(parents=True, exist_ok=True)
            value = {'Label': label, 'ProgramArguments': [python, '-I', str(destination), 'worker', host],
                     'RunAtLoad': True, 'StartInterval': 15, 'ProcessType': 'Background',
                     'EnvironmentVariables': {'HOME': str(Path.home()), 'PATH': os.environ['PATH']},
                     'StandardErrorPath': str(folder / host / 'launchd.stderr'),
                     'StandardOutPath': str(folder / host / 'launchd.stdout')}
            fd, temporary = tempfile.mkstemp(dir=plist.parent)
            with os.fdopen(fd, 'wb') as stream:
                plistlib.dump(value, stream)
            os.replace(temporary, plist)
            domain = 'gui/' + str(os.getuid())
            existing = subprocess.run(['/bin/launchctl', 'print', domain + '/' + label], capture_output=True)
            if existing.returncode == 0:
                run(['/bin/launchctl', 'bootout', domain + '/' + label])
            for attempt in range(5):
                try:
                    run(['/bin/launchctl', 'bootstrap', domain, str(plist)])
                    break
                except RuntimeError:
                    if attempt == 4:
                        raise
                    time.sleep(1)
    return {'installed': True, 'guardTrust': 'verify through native host before queueing', 'root': str(folder)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('install')
    for name in ('queue', 'worker', 'status', 'hook'):
        sub = commands.add_parser(name)
        sub.add_argument('host', choices=HOSTS)
        if name == 'queue':
            sub.add_argument('--targets', type=Path, required=True)
            sub.add_argument('--commit', required=True)
            sub.add_argument('--after', choices=HOSTS)
            sub.add_argument('--reconcile', action='store_true', help='Acknowledge a held partial update; keep guards held until repair verifies')
        if name == 'hook':
            sub.add_argument('event', choices=EVENTS)
    args = parser.parse_args()
    try:
        if args.command == 'install':
            value = install()
        elif args.command == 'queue':
            if args.after == args.host:
                raise ValueError('self_dependency')
            value = queue(args.host, read(args.targets.resolve()), args.commit, args.after, args.reconcile)
        elif args.command == 'worker':
            worker(args.host)
            return 0
        elif args.command == 'status':
            value = read(root() / args.host / 'status.json')
        else:
            raw = sys.stdin.buffer.read(16 * LIMIT + 1)
            if len(raw) > 16 * LIMIT:
                raise ValueError('hook_input_limit')
            payload = json.loads(raw)
            if not isinstance(payload, dict) or payload.get('hook_event_name') != args.event:
                raise ValueError('hook_event_mismatch')
            message = hook(args.host, args.event, payload)
            if not message:
                return 0
            value = hook_output(args.event, message)
        print(json.dumps(value))
        return 0
    except BlockingIOError:
        return 0 if args.command == 'worker' else 1
    except Exception as error:
        if args.command == 'hook':
            message = ('Rhize plugin publication is busy; wait for its completion receipt before another tool. Existing versions are retained.'
                       if str(error) == 'publication_busy_try_after_completion' else
                       'Rhize update metadata unavailable; stop this session and inspect the automatic updater status.')
            print(json.dumps(hook_output(args.event, message)))
            return 0
        print(str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
