#!/usr/bin/env python3
"""Keep the loopback Laya server warm so the skill-fit co-sign does not time out on a cold start (plan §7 F9, §8).

    laya_keepwarm.py once   [--root DIR] [--endpoint URL] [--force] ...   one gated ping, then exit
    laya_keepwarm.py run    [--root DIR] [--endpoint URL] ...             loop until SIGTERM / SIGINT
    laya_keepwarm.py status [--root DIR]                                   print <root>/laya-keepwarm.json

Options (once / run): --interval 90, --max-backoff 120, --active-window-hours 2, --warm-skip-seconds 60,
--timeout-ms 10000. `LAYA_KEEPWARM=0` makes once and run exit 0 immediately (no I/O at all).

Each ping is ONE fixed synthetic laya-choice-v1 request (constant text, two constant candidate skills; no user
data) sent with laya_choice.call_choice, so it has the hook's exact transport rules: literal loopback endpoint
only, no proxy, redirects refused, a /health identity probe first (cached in <root>/laya-keepwarm-health.json),
one monotonic deadline. A dead server is reported, never waited on past --timeout-ms.

Activity gate (newest mtime of): the workflow-selection `receipts` directory under
${XDG_DATA_HOME:-~/.local/share}/rhize, $RHIZE_SUGGESTION_LOG (default ~/.claude/context-manager/suggestion-log.jsonl)
and the newest file under <root>/skill-fit/records/.
  * older than --active-window-hours       -> skip, skippedIdle++   (nobody is working; let Laya idle)
  * a real Laya call younger than --warm-skip-seconds: the newest `ts` of a LIVE skill-fit record whose Laya
    status is 'ok' (read from the tails of the two newest record day-files; backfill replays, skipped calls,
    failed calls and bare file mtimes prove nothing about warmth)
                                           -> skip, skippedWarm++   (live traffic is already keeping Laya warm)
  * otherwise                              -> ping

Failure backoff: after a failed ping the next wait doubles (interval -> 2 x interval ...) up to --max-backoff and
resets to --interval on the first success. `run` also waits for /health to answer before its first ping, so a
server that is still loading at boot is not scored as a failing ping.

State: <root>/laya-keepwarm.json (0600, atomic, symlinks refused), schema rhize-laya-keepwarm-v1. This script
never writes decision records, labels, outcomes or cohort events, and never reads prompt text.
`intervalSeconds` is the configured base interval; the current backoff is visible through `consecutiveFailures`.

Exit codes: 0 done / skipped / disabled, 1 the ping or the state write failed (for `run`: the final state write on
the way out; a failing write mid-run is reported once on stderr and the loop keeps pinging), 2 bad arguments (for
example a non-loopback endpoint).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import signal
import stat
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from typed_decisions import contract, instrument, laya_choice, locked_io, records  # noqa: E402

SCHEMA = 'rhize-laya-keepwarm-v1'
DECISION = 'skill-fit'
STATE_NAME = 'laya-keepwarm.json'
HEALTH_CACHE_NAME = 'laya-keepwarm-health.json'
LOCK_NAME = 'laya-keepwarm.lock'
DEFAULT_ENDPOINT = 'http://127.0.0.1:8000'
STATE_KEYS = ('schema', 'startedAt', 'lastPingAt', 'lastStatus', 'lastLatencyMs', 'consecutiveFailures', 'pings',
              'ok', 'skippedIdle', 'skippedWarm', 'intervalSeconds', 'activeWindowHours', 'lastActivityAt')
# Seconds between /health polls while `run` waits for the server to come up before its first ping.
HEALTH_POLL_SECONDS = 5
# An activity mtime this far in the future is clock garbage and must not suppress pings forever.
MAX_FUTURE_SKEW_SECONDS = 60
SLEEP_SLICE_SECONDS = 0.5
# Bytes read from the end of each record day-file when looking for the newest live Laya call.
MAX_RECORD_TAIL_BYTES = 256 * 1024
DAY_FILE = re.compile(r'\d{4}-\d{2}-\d{2}\.jsonl\Z')

EXIT_OK, EXIT_FAILED, EXIT_USAGE = 0, 1, 2

# The one request this module ever sends: constant text and two constant candidates. No user data.
PING_PROMPT = 'Keep-warm ping. This is a fixed synthetic request; answer with the closest skill or none.'
PING_CANDIDATES = (
    {'skillId': 'skill:keepwarm/ping-alpha', 'description': 'Synthetic keep-warm candidate A.'},
    {'skillId': 'skill:keepwarm/ping-bravo', 'description': 'Synthetic keep-warm candidate B.'},
)


def fixed_request() -> dict:
    """The constant laya-choice-v1 request ({'request', 'keyMap', ...} from instrument.build_choice_request)."""
    return instrument.build_choice_request(PING_PROMPT, [dict(item) for item in PING_CANDIDATES])


def _iso(epoch) -> str:
    return locked_io.iso(datetime.fromtimestamp(epoch, timezone.utc))


# ------------------------------------------------------------------ activity gate

def activity_sources(root) -> tuple:
    """(workflow-selection receipts dir, suggestion log file, skill-fit records dir)."""
    xdg = os.environ.get('XDG_DATA_HOME') or str(Path.home() / '.local' / 'share')
    receipts = Path(xdg) / 'rhize' / 'workflow-selection' / 'receipts'
    log = Path(os.environ.get('RHIZE_SUGGESTION_LOG')
               or Path.home() / '.claude' / 'context-manager' / 'suggestion-log.jsonl')
    return receipts, log, Path(root) / DECISION / 'records'


def _mtime(path):
    try:
        return os.stat(path).st_mtime
    except OSError:
        return None


def _newest_file_mtime(directory):
    """Newest mtime among regular, non-symlink files directly inside `directory`; None when there is none."""
    if os.path.islink(directory):
        return None
    newest = None
    try:
        with os.scandir(directory) as entries:
            for entry in entries:
                try:
                    if entry.is_symlink() or not entry.is_file(follow_symlinks=False):
                        continue
                    mtime = entry.stat(follow_symlinks=False).st_mtime
                except OSError:
                    continue
                if newest is None or mtime > newest:
                    newest = mtime
    except OSError:
        return None
    return newest


def newest_activity(root, now):
    """Newest mtime (epoch seconds) of the three activity signals, or None when none of them exists."""
    receipts, log, records_dir = activity_sources(root)
    candidates = [_mtime(receipts), _mtime(log), _newest_file_mtime(records_dir)]
    usable = [value for value in candidates if value is not None and value <= now + MAX_FUTURE_SKEW_SECONDS]
    return max(usable) if usable else None


def _tail_lines(path, limit):
    """Complete lines in the last `limit` bytes of a regular, non-symlink file ([] when it cannot be read)."""
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    except OSError:
        return []
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            return []
        start = max(0, info.st_size - limit)
        os.lseek(fd, start, os.SEEK_SET)
        chunks, left = [], info.st_size - start
        while left > 0:
            chunk = os.read(fd, min(left, 65536))
            if not chunk:
                break
            chunks.append(chunk)
            left -= len(chunk)
    except OSError:
        return []
    finally:
        os.close(fd)
    lines = b''.join(chunks).split(b'\n')
    return lines[1:] if start > 0 else lines            # the first line of a mid-file tail may be partial


def _record_epoch(value):
    """Epoch seconds of a record's ISO `ts`, or None. Only a string counts: locked_io.utc(None) means "now", so a
    missing or null ts must never become fresh warmth evidence (Codex final review)."""
    if not isinstance(value, str):
        return None
    try:
        return locked_io.utc(value).timestamp()
    except ValueError:
        return None


def newest_laya_call(root, now):
    """Epoch of the newest LIVE skill-fit record whose Laya call returned 'ok' — the last time a hook's request
    actually reached inference (None when unknown). Only this signal may skip a ping as 'warm'.

    Workflow receipts and suggestion-log rows also come from prompts that never reach Laya (Codex guardian reviews,
    subagents, silent prompts), and the records directory itself also receives backfill replays and skipped or
    failed calls (Codex final review), so none of those, nor a file mtime, proves the server is warm.
    """
    directory = activity_sources(root)[2]
    if os.path.islink(directory):
        return None
    try:
        names = sorted(name for name in os.listdir(directory) if DAY_FILE.match(name))[-2:]
    except OSError:
        return None
    newest = None
    for name in names:
        for line in _tail_lines(directory / name, MAX_RECORD_TAIL_BYTES):
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if not isinstance(rec, dict):
                continue
            laya = rec.get('laya')
            if rec.get('basis') != 'live' or not isinstance(laya, dict) or laya.get('status') != 'ok':
                continue
            epoch = _record_epoch(rec.get('ts'))
            if epoch is None or epoch > now + MAX_FUTURE_SKEW_SECONDS:
                continue
            if newest is None or epoch > newest:
                newest = epoch
    return newest


def gate(newest, now, window_seconds, warm_seconds, laya=None) -> str:
    """'idle' | 'warm' | 'ping'. `newest` is the newest activity of any kind; `laya` the newest real Laya call."""
    if newest is None:
        return 'idle'
    if now - newest > window_seconds:
        return 'idle'
    if laya is not None and now - laya < warm_seconds:
        return 'warm'
    return 'ping'


# ------------------------------------------------------------------ state

def state_path(root) -> Path:
    return Path(root) / STATE_NAME


def initial_state(now, interval, active_window_hours) -> dict:
    return {'schema': SCHEMA, 'startedAt': _iso(now), 'lastPingAt': None, 'lastStatus': None,
            'lastLatencyMs': None, 'consecutiveFailures': 0, 'pings': 0, 'ok': 0, 'skippedIdle': 0,
            'skippedWarm': 0, 'intervalSeconds': interval, 'activeWindowHours': active_window_hours,
            'lastActivityAt': None}


def load_state(root):
    """The saved state when it is a valid current-schema file, else None (missing, symlinked or foreign)."""
    try:
        state = locked_io.read_json_file(state_path(root))
    except (OSError, ValueError):
        return None
    if not isinstance(state, dict) or state.get('schema') != SCHEMA or set(state) != set(STATE_KEYS):
        return None
    return state


def save_state(root, state) -> None:
    path = state_path(root)
    if os.path.islink(path):
        raise ValueError('symlinked state path refused')
    if set(state) != set(STATE_KEYS):
        raise ValueError('state keys mismatch')
    locked_io.write_private_atomic(path, (json.dumps(state, sort_keys=True) + '\n').encode('utf-8'))


# ------------------------------------------------------------------ keep-warm engine

class KeepWarm:
    """One keep-warm worker: gate decision, ping, counters and backoff. All time goes through `clock`."""

    def __init__(self, root, endpoint=DEFAULT_ENDPOINT, interval=90, max_backoff=120, active_window_hours=2,
                 warm_skip_seconds=60, timeout_ms=10000, clock=time.time, opener=None, state=None,
                 wait_for_health=True):
        if not laya_choice.is_loopback_endpoint(endpoint):
            raise ValueError('endpoint must be a literal loopback http address')
        if interval <= 0 or max_backoff < interval or active_window_hours <= 0 or warm_skip_seconds < 0 \
                or timeout_ms <= 0:
            raise ValueError('invalid keep-warm option')
        self.root = Path(root)
        self.endpoint = endpoint
        self.interval = interval
        self.max_backoff = max_backoff
        self.window_seconds = active_window_hours * 3600
        self.warm_seconds = warm_skip_seconds
        self.timeout_ms = timeout_ms
        self.clock = clock
        self.opener = opener
        self.health_cache = self.root / HEALTH_CACHE_NAME
        self.health_ready = not wait_for_health
        self.current_interval = interval
        self.final_save_ok = None                   # set by run_loop: did the last state write succeed?
        self.state = state if state is not None else initial_state(clock(), interval, active_window_hours)
        self.state['intervalSeconds'] = interval
        self.state['activeWindowHours'] = active_window_hours

    def health_status(self) -> str:
        """Identity probe only (GET /health); 'ok' or the laya_choice status of the failure."""
        deadline = time.monotonic() + self.timeout_ms / 1000.0
        try:
            laya_choice._probe(self.opener if self.opener is not None else laya_choice.default_opener(),  # noqa: SLF001
                               self.endpoint, instrument.MODEL, deadline, self.health_cache)
            return 'ok'
        except laya_choice._Stop as stop:  # noqa: SLF001
            return stop.status
        except Exception:  # noqa: BLE001 - the probe must never take the worker down
            return 'unavailable'

    def ping(self) -> dict:
        built = fixed_request()
        return laya_choice.call_choice(built['request'], built['keyMap'], self.endpoint, instrument.MODEL,
                                       self.timeout_ms, health_cache_path=self.health_cache, opener=self.opener)

    def tick(self, force=False) -> tuple:
        """One gate decision (and maybe one ping). Returns (seconds to wait before the next tick, info dict)."""
        now = self.clock()
        state = self.state
        newest = newest_activity(self.root, now)
        if newest is not None:
            state['lastActivityAt'] = _iso(newest)
        decision = 'ping' if force else gate(newest, now, self.window_seconds, self.warm_seconds,
                                             laya=newest_laya_call(self.root, now))
        if decision == 'idle':
            state['skippedIdle'] += 1
            return self.current_interval, {'action': 'skipped_idle'}
        if decision == 'warm':
            state['skippedWarm'] += 1
            return self.current_interval, {'action': 'skipped_warm'}
        if not self.health_ready:
            status = self.health_status()
            if status != 'ok':
                state['lastStatus'] = status
                return min(HEALTH_POLL_SECONDS, self.interval), {'action': 'waiting_health', 'status': status}
            self.health_ready = True
        result = self.ping()
        state['pings'] += 1
        state['lastPingAt'] = _iso(now)
        state['lastStatus'] = result['status']
        state['lastLatencyMs'] = result['latencyMs']
        if result['status'] == 'ok':
            state['ok'] += 1
            state['consecutiveFailures'] = 0
            self.current_interval = self.interval
        else:
            state['consecutiveFailures'] += 1
            self.current_interval = min(self.current_interval * 2, self.max_backoff)
        return self.current_interval, {'action': 'ping', 'status': result['status'],
                                       'latencyMs': result['latencyMs']}

    def save(self) -> None:
        save_state(self.root, self.state)


def _interruptible_sleep(seconds, should_stop) -> None:
    deadline = time.monotonic() + seconds
    while not should_stop():
        left = deadline - time.monotonic()
        if left <= 0:
            return
        time.sleep(min(SLEEP_SLICE_SECONDS, left))


def run_loop(worker, sleep=None, max_iterations=None, should_stop=lambda: False, on_error=None) -> int:
    """tick / save / sleep until `should_stop()` or `max_iterations` ticks. Returns the number of ticks run.

    `sleep(seconds)` is injectable (the default sleeps in short slices so a stop request is honored promptly).
    A failing state write is reported through `on_error(exc)` and never ends the loop; the final state write
    happens on the way out so SIGTERM leaves a current file behind. `worker.final_save_ok` records whether that
    last write succeeded, so the caller can exit non-zero when it did not (Codex final review).
    """
    if sleep is None:
        def sleep(seconds):
            _interruptible_sleep(seconds, should_stop)
    ticks = 0
    while not should_stop() and (max_iterations is None or ticks < max_iterations):
        wait, _info = worker.tick()
        ticks += 1
        try:
            worker.save()
        except Exception as exc:  # noqa: BLE001 - a read-only disk must not end the keep-warm loop
            if on_error:
                on_error(exc)
        if max_iterations is not None and ticks >= max_iterations:
            break
        sleep(wait)
    worker.final_save_ok = False
    try:
        worker.save()
        worker.final_save_ok = True
    except Exception as exc:  # noqa: BLE001
        if on_error:
            on_error(exc)
    return ticks


# ------------------------------------------------------------------ CLI

def _number(text):
    try:
        value = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError('must be a number') from None
    if value != value or value in (float('inf'), float('-inf')):
        raise argparse.ArgumentTypeError('must be finite')
    return int(value) if value.is_integer() else value


def _positive(text):
    value = _number(text)
    if value <= 0:
        raise argparse.ArgumentTypeError('must be positive')
    return value


def _non_negative(text):
    value = _number(text)
    if value < 0:
        raise argparse.ArgumentTypeError('must not be negative')
    return value


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    sub = parser.add_subparsers(dest='command', required=True)
    for name, help_text in (('once', 'one gated ping, then exit'), ('run', 'loop until SIGTERM or SIGINT')):
        cmd = sub.add_parser(name, help=help_text)
        cmd.add_argument('--root', default=None, help='typed-decisions root (default: records.default_root())')
        cmd.add_argument('--endpoint', default=DEFAULT_ENDPOINT, help='literal loopback Laya endpoint')
        cmd.add_argument('--interval', type=_positive, default=90, help='seconds between pings (default 90)')
        cmd.add_argument('--max-backoff', type=_positive, default=120, help='backoff cap in seconds (default 120)')
        cmd.add_argument('--active-window-hours', type=_positive, default=2)
        cmd.add_argument('--warm-skip-seconds', type=_non_negative, default=60)
        cmd.add_argument('--timeout-ms', type=_positive, default=10000)
        if name == 'once':
            cmd.add_argument('--force', action='store_true', help='ping even when the activity gate says skip')
        else:
            cmd.add_argument('--max-iterations', type=int, default=None, help=argparse.SUPPRESS)
    status = sub.add_parser('status', help='print the keep-warm state file as JSON')
    status.add_argument('--root', default=None)
    return parser


def _emit(payload) -> None:
    print(json.dumps(payload, sort_keys=True))


def _worker_from(args, clock, opener, state, wait_for_health):
    return KeepWarm(args.root, endpoint=args.endpoint, interval=args.interval, max_backoff=args.max_backoff,
                    active_window_hours=args.active_window_hours, warm_skip_seconds=args.warm_skip_seconds,
                    timeout_ms=args.timeout_ms, clock=clock, opener=opener, state=state,
                    wait_for_health=wait_for_health)


def _command_status(root) -> int:
    path = state_path(root)
    try:
        state = locked_io.read_json_file(path)
    except FileNotFoundError:
        _emit({'status': 'absent'})
        return EXIT_FAILED
    except (OSError, ValueError) as exc:
        _emit({'status': 'unreadable', 'reason': contract.safe_reason(exc)})
        return EXIT_FAILED
    print(json.dumps(state, sort_keys=True))
    return EXIT_OK


def main(argv=None, *, clock=time.time, sleep=None, opener=None) -> int:
    args = build_parser().parse_args(argv)
    args.root = Path(args.root) if args.root else records.default_root()
    if args.command == 'status':
        return _command_status(args.root)
    if os.environ.get('LAYA_KEEPWARM') == '0':
        _emit({'status': 'disabled'})
        return EXIT_OK
    if not laya_choice.is_loopback_endpoint(args.endpoint):
        _emit({'status': 'refused', 'reason': 'endpoint must be a literal loopback http address'})
        return EXIT_USAGE
    if args.max_backoff < args.interval:
        _emit({'status': 'refused', 'reason': '--max-backoff must not be below --interval'})
        return EXIT_USAGE
    try:
        records.private_dir(args.root)
        lock = locked_io.try_lock(args.root / LOCK_NAME)
    except (OSError, ValueError) as exc:
        _emit({'status': 'failed', 'reason': contract.safe_reason(exc)})
        return EXIT_FAILED
    if lock is None:
        _emit({'status': 'busy'})                     # a keep-warm agent already owns the state file
        return EXIT_OK
    try:
        if args.command == 'once':
            return _command_once(args, clock, opener)
        return _command_run(args, clock, sleep, opener)
    finally:
        locked_io.release_lock(lock)


def _command_once(args, clock, opener) -> int:
    state = load_state(args.root)
    try:
        worker = _worker_from(args, clock, opener, state, wait_for_health=False)
        _wait, info = worker.tick(force=args.force)
        worker.save()
    except (OSError, ValueError) as exc:
        _emit({'status': 'failed', 'reason': contract.safe_reason(exc)})
        return EXIT_FAILED
    _emit(info)
    return EXIT_FAILED if info['action'] == 'ping' and info['status'] != 'ok' else EXIT_OK


def _command_run(args, clock, sleep, opener) -> int:
    stopping = {'flag': False}

    def request_stop(_signum, _frame):
        stopping['flag'] = True

    previous = {sig: signal.signal(sig, request_stop) for sig in (signal.SIGTERM, signal.SIGINT)}
    reported = {'done': False}

    def on_error(exc):
        if not reported['done']:                      # one line, not one per tick
            reported['done'] = True
            print(f'laya-keepwarm: state write failed ({type(exc).__name__})', file=sys.stderr, flush=True)

    try:
        worker = _worker_from(args, clock, opener, None, wait_for_health=True)
        ticks = run_loop(worker, sleep=sleep, max_iterations=args.max_iterations,
                         should_stop=lambda: stopping['flag'], on_error=on_error)
    except (OSError, ValueError) as exc:
        _emit({'status': 'failed', 'reason': contract.safe_reason(exc)})
        return EXIT_FAILED
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    if not worker.final_save_ok:
        _emit({'status': 'failed', 'reason': 'final state write failed', 'ticks': ticks,
               'pings': worker.state['pings'], 'ok': worker.state['ok']})
        return EXIT_FAILED
    _emit({'status': 'stopped', 'ticks': ticks, 'pings': worker.state['pings'], 'ok': worker.state['ok']})
    return EXIT_OK


if __name__ == '__main__':
    raise SystemExit(main())
