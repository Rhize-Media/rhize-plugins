#!/usr/bin/env python3
"""Opt-in local invocation metrics. No content, host hooks, network or raw-event export."""
import argparse
from contextlib import contextmanager
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time
import uuid

SCHEMA = 1
MAX_EVENTS = 2000
MAX_BYTES = 2 * 1024 * 1024
HOSTS = ('claude', 'codex', 'unknown')
OPERATIONS = ('public-setup', 'web-search', 'reddit-search', 'exa-read', 'jina-read',
              'github-search', 'github-read', 'v2ex-hot', 'v2ex-read', 'meta-setup',
              'meta-doctor', 'meta-provider-check', 'meta-list', 'meta-plan', 'meta-collect',
              'meta-resume', 'meta-status', 'meta-export', 'brief-json', 'brief-csv', 'brief-markdown')
PROVIDERS = ('public-adapter', 'meta-response-journal', 'offline-renderer')
STATUSES = ('completed', 'retrieved', 'empty', 'unavailable', 'planned', 'checked',
            'awaiting_response', 'held', 'already_terminal', 'imported', 'exported',
            'rendered', 'failed', 'interrupted', 'output_failed')
ERRORS = ('none', 'rate_limit', 'timeout', 'setup', 'provider', 'validation', 'io',
          'broken_pipe', 'interrupted', 'unclassified')
DURATIONS = ('lt1s', '1to5s', '5to30s', '30to120s', 'gte120s')
EVENT_FIELDS = set('id day version declared_host operation provider status error duration returned dropped tokens cost'.split())
WARNING = 'Rhize usage capture unavailable; research outcome unchanged.'


def require(ok):
    if not ok:
        raise ValueError('invalid_telemetry_store')


def today():
    return dt.datetime.now(dt.timezone.utc).date()


def root():
    return Path.home().resolve() / 'Library/Application Support/Rhize Ad Research/usage-telemetry'


def valid_id(value):
    return isinstance(value, str) and re.fullmatch(r'[0-9a-f]{32}', value) is not None


def validate_event(event):
    require(isinstance(event, dict) and set(event) == EVENT_FIELDS)
    require(valid_id(event['id']))
    day = dt.date.fromisoformat(event['day'])
    require(day.isoformat() == event['day'])
    require(isinstance(event['version'], str) and re.fullmatch(r'[0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,4}', event['version']))
    for field, choices in (('declared_host', HOSTS), ('operation', OPERATIONS), ('provider', PROVIDERS),
                           ('status', STATUSES), ('error', ERRORS), ('duration', DURATIONS)):
        require(event[field] in choices)
    for field in ('returned', 'dropped'):
        require(event[field] is None or type(event[field]) is int and 0 <= event[field] <= 100)
    require(event['tokens'] is None and event['cost'] is None)


def validate(state):
    require(isinstance(state, dict) and set(state) == {'schema', 'enabled', 'generation', 'events'})
    require(type(state['schema']) is int and state['schema'] == SCHEMA)
    require(type(state['enabled']) is bool and valid_id(state['generation']))
    require(isinstance(state['events'], list) and len(state['events']) <= MAX_EVENTS)
    ids = set()
    for event in state['events']:
        validate_event(event)
        require(event['id'] not in ids)
        ids.add(event['id'])
    return state


def unique(pairs):
    out = {}
    for key, value in pairs:
        require(key not in out)
        out[key] = value
    return out


@contextmanager
def directory(create=False):
    """Anchor operations to an opened directory, refusing symlinks along the path."""
    path = root().absolute()
    fd = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            try:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            except FileNotFoundError:
                if not create:
                    raise
                try:
                    os.mkdir(part, 0o700, dir_fd=fd)
                except FileExistsError:
                    pass
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        info = os.fstat(fd)
        require(info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o700)
        yield fd
    finally:
        os.close(fd)


def checked_file(fd, cap=MAX_BYTES):
    info = os.fstat(fd)
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid() and info.st_nlink == 1
            and stat.S_IMODE(info.st_mode) == 0o600 and info.st_size <= cap)


def read(fd):
    handle = os.open('state.json', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    try:
        checked_file(handle)
        with os.fdopen(handle, 'rb', closefd=False) as stream:
            raw = stream.read(MAX_BYTES + 1)
        require(len(raw) <= MAX_BYTES)
        return validate(json.loads(raw, object_pairs_hook=unique))
    finally:
        os.close(handle)


def write(fd, state):
    data = json.dumps(validate(state), separators=(',', ':'), sort_keys=True).encode()
    require(len(data) <= MAX_BYTES)
    temporary = '.write-' + uuid.uuid4().hex
    handle = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600, dir_fd=fd)
    try:
        with os.fdopen(handle, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, 'state.json', src_dir_fd=fd, dst_dir_fd=fd)
        os.fsync(fd)
    finally:
        try:
            os.unlink(temporary, dir_fd=fd)
        except FileNotFoundError:
            pass


@contextmanager
def locked(fd, timeout=.25):
    # The private directory inode is stable; corrupt state/lock entries cannot block purge.
    until = time.monotonic() + timeout
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            if time.monotonic() >= until:
                raise TimeoutError('telemetry_busy') from None
            time.sleep(.005)
    try:
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)


def cleanup(fd):
    # Only our fixed-pattern atomic-write remnants; never traverse directories or links.
    for name in os.listdir(fd):
        if re.fullmatch(r'\.write-[0-9a-f]{32}', name):
            os.unlink(name, dir_fd=fd)


def fresh(enabled=False):
    return {'schema': SCHEMA, 'enabled': enabled, 'generation': uuid.uuid4().hex, 'events': []}


def retained(events):
    cutoff = (today() - dt.timedelta(days=30)).isoformat()
    return [event for event in events if cutoff < event['day'] <= today().isoformat()]


def classify(exc):
    """Return constants only; never serialize exception text or class names."""
    if isinstance(exc, BrokenPipeError):
        return 'broken_pipe'
    if isinstance(exc, (TimeoutError, subprocess.TimeoutExpired)):
        return 'timeout'
    if isinstance(exc, subprocess.CalledProcessError):
        return 'setup'
    if isinstance(exc, OSError):
        return 'io'
    # Exact known codes; arbitrary provider/interpreter text always becomes unclassified.
    code = str(exc) if isinstance(exc, ValueError) else None
    return {'rate_limited': 'rate_limit', 'worker_timeout': 'timeout',
            'docker_required': 'setup', 'run_setup_first': 'setup', 'image_changed': 'setup',
            'provider_error': 'provider', 'provider_parse_error': 'provider',
            'platform_blocked': 'provider', 'not_found': 'provider',
            'broker_failed': 'provider', 'invalid_input': 'validation',
            'invalid_url': 'validation', 'private_target': 'validation'}.get(code, 'unclassified')


def duration_bucket(seconds):
    return DURATIONS[sum(seconds >= limit for limit in (1, 5, 30, 120))]


def count(value):
    return min(value, 100) if type(value) is int and value >= 0 else None


@contextmanager
def measure(host, operation, provider):
    started = time.monotonic()
    state = None
    try:
        with directory() as fd:
            state = read(fd)
        if not state['enabled']:
            state = None
    except Exception:
        state = None
    outcome = {'status': 'failed', 'error': 'unclassified', 'returned': None, 'dropped': None}
    def set_outcome(status, error='none', returned=None, dropped=None):
        outcome.update(status=status, error=error, returned=count(returned), dropped=count(dropped))
    try:
        yield set_outcome
    except KeyboardInterrupt:
        set_outcome('interrupted', 'interrupted')
        raise
    finally:
        elapsed = time.monotonic() - started
        if state is not None:
            try:
                version = json.loads((Path(__file__).resolve().parents[1] / '.claude-plugin/plugin.json').read_text())['version']
                event = {'id': uuid.uuid4().hex, 'day': today().isoformat(), 'version': version,
                         'declared_host': host, 'operation': operation, 'provider': provider,
                         'duration': duration_bucket(elapsed), **outcome, 'tokens': None, 'cost': None}
                append(event, state['generation'])
            except Exception:
                # A diagnostic must not turn a completed research operation into a failure.
                try:
                    print(WARNING, file=sys.stderr)
                except Exception:
                    pass


def append(event, generation):
    validate_event(event)
    require(event['day'] <= today().isoformat())
    with directory() as fd, locked(fd):
        current = read(fd)
        if not current['enabled'] or current['generation'] != generation:
            return
        rows = retained(current['events'])
        if any(row['id'] == event['id'] for row in rows):
            return
        current['events'] = (rows + [event])[-MAX_EVENTS:]
        cleanup(fd)
        write(fd, current)


def report(state):
    groups = {}
    for event in retained(state['events']):
        keys = ('version', 'declared_host', 'operation', 'provider', 'status', 'error', 'duration')
        key = tuple(event[k] for k in keys)
        row = groups.setdefault(key, dict(zip(keys, key), invocations=0, returned_total=0,
                                         returned_known=0, returned_unknown=0, dropped_total=0,
                                         dropped_known=0, dropped_unknown=0))
        row['invocations'] += 1
        for field in ('returned', 'dropped'):
            row[field + ('_unknown' if event[field] is None else '_known')] += 1
            if event[field] is not None:
                row[field + '_total'] += event[field]
    return {'schema': SCHEMA, 'unit': 'CLI invocation; not a unique research job or native Meta call',
            'limits': 'Local declared hosts; no human acceptance. Verify capture permissions in both hosts before comparisons. Missing writes and abrupt termination are unobserved. Aggregates are not anonymous.',
            'retention_days': 30, 'capacity_events': MAX_EVENTS, 'capacity_policy': 'drop_oldest',
            'count_limits': 'Per-invocation counts capped at 100; totals are lower bounds.',
            'tokens': None, 'cost': None, 'groups': [groups[key] for key in sorted(groups)]}


def control(command):
    try:
        with directory(create=command == 'enable') as fd, locked(fd, timeout=2):
            if command == 'purge':
                # Replace a corrupt/symlink/FIFO state entry without reading or following it.
                state = fresh()
                try:
                    os.rmdir('state.json', dir_fd=fd)  # Empty directory corruption only; never recursive.
                except (FileNotFoundError, NotADirectoryError):
                    pass
            else:
                try:
                    state = read(fd)
                except FileNotFoundError:
                    state = fresh()
                state['events'] = retained(state['events'])
            if command in ('enable', 'disable'):
                state.update(enabled=command == 'enable', generation=uuid.uuid4().hex)
            cleanup(fd)
            write(fd, state)
            if command == 'report':
                return report(state)
            return {'enabled': state['enabled'], 'events': len(state['events']), 'writable': True,
                    'retention_days': 30, 'deletion': 'purge disables and removes events; disable retains rows until next control/pruning access'}
    except FileNotFoundError:
        if command == 'enable':
            raise
        return report(fresh()) if command == 'report' else {'enabled': False, 'events': 0, 'writable': None}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('enable', 'disable', 'status', 'report', 'purge'))
    args = parser.parse_args(argv)
    if args.command == 'enable':
        if not sys.stdin.isatty():
            print('Enable requires the operator in an interactive terminal.', file=sys.stderr)
            return 2
        print('Record local operational counts for 30 days (pruned on access), no research content or uploads. Type ENABLE:', file=sys.stderr)
        try:
            if input().strip() != 'ENABLE':
                return 2
        except (EOFError, KeyboardInterrupt):
            return 2
    try:
        print(json.dumps(control(args.command), sort_keys=True))
        return 0
    except TimeoutError:
        print('Telemetry store busy; retry the control command later.', file=sys.stderr)
        return 2
    except Exception:
        print('Telemetry store unavailable or invalid; no report produced. Inspect permissions or purge the local store.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
