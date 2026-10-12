"""laya_keepwarm.py: keep-warm pings, activity gate, backoff, state file and signals (plan §7 F9, §8, A1).

A stub loopback HTTP server stands in for Laya (GET /health, POST /v1/systemone); fake clocks and fake sleeps make
the loop deterministic. Everything lives under tmp_path: HOME, XDG_DATA_HOME and RHIZE_SUGGESTION_LOG are redirected,
so no test touches the real activity sources, the real data root or a real Laya.
"""
from __future__ import annotations

import json
import os
import signal
import socket
import stat
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / 'rhize-context-manager' / 'scripts'
sys.path.insert(0, str(SCRIPTS))

from typed_decisions import instrument, laya_choice, laya_keepwarm, locked_io  # noqa: E402

SCRIPT = SCRIPTS / 'typed_decisions' / 'laya_keepwarm.py'
SENTINEL = 'ZEBRA-SENTINEL-PHRASE'
STATE_FIELDS = {'schema', 'startedAt', 'lastPingAt', 'lastStatus', 'lastLatencyMs', 'consecutiveFailures', 'pings',
                'ok', 'skippedIdle', 'skippedWarm', 'intervalSeconds', 'activeWindowHours', 'lastActivityAt'}
EXPECTED_REQUEST = {
    'model': 'typed-decisions',
    'state': {'request': 'Keep-warm ping. This is a fixed synthetic request; answer with the closest skill or none.'},
    'questions': {'skill': {
        'type': 'choice', 'instructions': 'Which skill, if any, should be loaded to handle `request`?',
        'criteria': {'s0': 'ping-alpha: Synthetic keep-warm candidate A.',
                     's1': 'ping-bravo: Synthetic keep-warm candidate B.',
                     'none': 'none of these skills is needed; answer directly'}}}}


# ---------------------------------------------------------------- stub Laya

class StubLaya:
    def __init__(self, loaded=('typed-decisions',), health_status=200, post_status=200, redirect_on=None):
        self.loaded, self.health_status, self.post_status, self.redirect_on = list(loaded), health_status, post_status, redirect_on
        self.paths, self.posts = [], []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def send(self, status, body=b'', headers=()):
                self.send_response(status)
                for name, value in headers:
                    self.send_header(name, value)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                try:
                    self.wfile.write(body)
                except OSError:
                    pass

            def do_GET(self):
                outer.paths.append(('GET', self.path))
                if self.path != '/health':
                    return self.send(404)
                if outer.redirect_on == 'health':
                    return self.send(302, headers=[('Location', '/elsewhere')])
                self.send(outer.health_status, json.dumps({'status': 'ok', 'loaded': outer.loaded}).encode(),
                          [('Content-Type', 'application/json')])

            def do_POST(self):
                outer.paths.append(('POST', self.path))
                body = json.loads(self.rfile.read(int(self.headers.get('Content-Length') or 0)) or b'{}')
                outer.posts.append(body)
                if outer.redirect_on == 'post':
                    return self.send(307, headers=[('Location', '/v1/elsewhere')])
                if outer.post_status != 200:
                    return self.send(outer.post_status, b'{}')
                criteria = body['questions']['skill']['criteria']
                probs = {key: 0.1 for key in criteria}
                probs['s0'] = round(1 - 0.1 * (len(criteria) - 1), 6)
                answer = {'answers': {'skill': {'type': 'choice', 'choice': 's0', 'confidence': 0.5,
                                                'probabilities': probs}},
                          'routing': {'model': 'typed-decisions'}, 'usage': {'input_tokens': 1, 'output_tokens': 1}}
                self.send(200, json.dumps(answer).encode(), [('Content-Type', 'application/json')])

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=lambda: self.server.serve_forever(poll_interval=0.02), daemon=True).start()

    @property
    def url(self):
        return 'http://127.0.0.1:%d' % self.server.server_address[1]

    def posted(self):
        return len(self.posts)

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def stub():
    made = []

    def make(**kwargs):
        made.append(StubLaya(**kwargs))
        return made[-1]
    yield make
    for server in made:
        server.close()


def closed_port_url():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return 'http://127.0.0.1:%d' % sock.getsockname()[1]


class FakeClock:
    def __init__(self, now=1_790_000_000.0):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    home = tmp_path / 'home'
    home.mkdir()
    monkeypatch.setenv('HOME', str(home))
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path / 'xdg'))
    monkeypatch.setenv('RHIZE_SUGGESTION_LOG', str(tmp_path / 'suggestion-log.jsonl'))
    monkeypatch.delenv('LAYA_KEEPWARM', raising=False)
    monkeypatch.delenv('RHIZE_TYPED_DECISIONS_ROOT', raising=False)


@pytest.fixture
def root(tmp_path):
    return tmp_path / 'store'


def set_mtime(path, when):
    os.utime(path, (when, when), follow_symlinks=False)


def activity(tmp_path, age, now=None, source='log'):
    """Create one activity signal whose newest mtime is `age` seconds before `now` (default: the real time)."""
    now = time.time() if now is None else now
    if source == 'log':
        path = Path(os.environ['RHIZE_SUGGESTION_LOG'])
        path.write_text(f'{{"note":"{SENTINEL}"}}\n')
    elif source == 'receipts':
        path = Path(os.environ['XDG_DATA_HOME']) / 'rhize' / 'workflow-selection' / 'receipts'
        path.mkdir(parents=True, exist_ok=True)
    else:
        directory = tmp_path / 'store' / 'skill-fit' / 'records'
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / '2026-10-11.jsonl'
        path.write_text(SENTINEL + '\n')
    set_mtime(path, now - age)
    return path


def laya_record(tmp_path, age, now=None, basis='live', status='ok', day='2026-10-11', root=None):
    """Append one record-shaped line (only the fields the warm signal reads) dated `age` seconds before `now`."""
    now = time.time() if now is None else now
    directory = (Path(root) if root else tmp_path / 'store') / 'skill-fit' / 'records'
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f'{day}.jsonl'
    line = {'basis': basis, 'ts': locked_io.iso(datetime.fromtimestamp(now - age, timezone.utc)),
            'laya': {'status': status}, 'note': SENTINEL}
    with path.open('a') as handle:
        handle.write(json.dumps(line) + '\n')
    return path


def run_main(args, **kwargs):
    return laya_keepwarm.main(args, **kwargs)


def state_of(root):
    return json.loads((Path(root) / 'laya-keepwarm.json').read_text())


def tree(root):
    return sorted(str(p.relative_to(root)) for p in Path(root).rglob('*')) if Path(root).exists() else []


# ---------------------------------------------------------------- A1: once, the fixed request, the state file

def test_once_sends_exactly_the_fixed_request_and_nothing_else(stub, root, tmp_path, capsys):
    server = stub()
    activity(tmp_path, 300)
    assert run_main(['once', '--root', str(root), '--endpoint', server.url]) == 0
    assert server.posts == [EXPECTED_REQUEST]
    assert json.dumps(server.posts[0], sort_keys=True) == json.dumps(laya_keepwarm.fixed_request()['request'], sort_keys=True)
    assert [method for method, _ in server.paths] == ['GET', 'POST']          # identity probe first, then one ping
    assert server.paths[0] == ('GET', '/health') and server.paths[1] == ('POST', '/v1/systemone')
    assert SENTINEL not in json.dumps(server.posts)                            # activity files are never read
    assert json.loads(capsys.readouterr().out)['action'] == 'ping'


def test_the_fixed_request_is_a_valid_choice_request_with_constant_candidates():
    built = laya_keepwarm.fixed_request()
    assert built['request'] == EXPECTED_REQUEST and built['keyMap'] == {'s0': 'skill:keepwarm/ping-alpha',
                                                                        's1': 'skill:keepwarm/ping-bravo'}
    assert built['instrumentSha256'] == instrument.instrument_sha256()
    assert laya_keepwarm.fixed_request() == built                              # deterministic, no per-call data


def test_state_file_is_private_atomic_and_has_the_exact_fields(stub, root, tmp_path):
    server = stub()
    activity(tmp_path, 300)
    assert run_main(['once', '--root', str(root), '--endpoint', server.url]) == 0
    path = root / 'laya-keepwarm.json'
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600 and stat.S_IMODE(os.stat(root).st_mode) == 0o700
    state = state_of(root)
    assert set(state) == STATE_FIELDS
    assert state['schema'] == 'rhize-laya-keepwarm-v1' and state['lastStatus'] == 'ok'
    assert state['pings'] == 1 and state['ok'] == 1 and state['consecutiveFailures'] == 0
    assert state['skippedIdle'] == 0 and state['skippedWarm'] == 0
    assert state['intervalSeconds'] == 90 and state['activeWindowHours'] == 2
    assert isinstance(state['lastLatencyMs'], float) and state['lastLatencyMs'] >= 0
    for field in ('startedAt', 'lastPingAt', 'lastActivityAt'):
        assert state[field].endswith('Z') and len(state[field]) == 20
    assert [p for p in root.iterdir() if p.name.endswith('.tmp')] == []        # no temp files left behind


def test_second_once_continues_the_counters(stub, root, tmp_path):
    server = stub()
    activity(tmp_path, 300)
    run_main(['once', '--root', str(root), '--endpoint', server.url])
    first = state_of(root)
    run_main(['once', '--root', str(root), '--endpoint', server.url])
    second = state_of(root)
    assert second['pings'] == 2 and second['ok'] == 2 and second['startedAt'] == first['startedAt']


def test_never_writes_decision_records_labels_or_outcomes(stub, root, tmp_path):
    server = stub()
    records_file = activity(tmp_path, 300, source='records')
    before = records_file.read_bytes()
    run_main(['once', '--root', str(root), '--endpoint', server.url])
    run_main(['once', '--root', str(root), '--endpoint', server.url, '--force'])
    for kind in ('records', 'labels', 'outcomes', 'cohorts'):
        files = list((root / 'skill-fit' / kind).glob('*')) if (root / 'skill-fit' / kind).exists() else []
        assert files == ([records_file] if kind == 'records' else [])
    assert records_file.read_bytes() == before
    assert {p.name for p in root.iterdir()} <= {'skill-fit', 'laya-keepwarm.json', 'laya-keepwarm-health.json',
                                                'laya-keepwarm.lock'}


# ---------------------------------------------------------------- activity gate

def test_idle_gate_skips_without_any_network_io(stub, root, tmp_path, capsys):
    server = stub()
    activity(tmp_path, 3 * 3600)                                               # older than the 2 h window
    assert run_main(['once', '--root', str(root), '--endpoint', server.url]) == 0
    assert server.paths == []
    state = state_of(root)
    assert state['skippedIdle'] == 1 and state['skippedWarm'] == 0 and state['pings'] == 0
    assert state['lastPingAt'] is None and state['lastStatus'] is None
    assert json.loads(capsys.readouterr().out) == {'action': 'skipped_idle'}


def test_no_activity_source_at_all_counts_as_idle(stub, root):
    server = stub()
    assert run_main(['once', '--root', str(root), '--endpoint', server.url]) == 0
    assert server.paths == [] and state_of(root)['skippedIdle'] == 1 and state_of(root)['lastActivityAt'] is None


def test_warm_skip_gate_skips_when_live_traffic_is_fresh(stub, root, tmp_path, capsys):
    server = stub()
    laya_record(tmp_path, 10)                                                  # a hook's Laya call answered 10 s ago
    assert run_main(['once', '--root', str(root), '--endpoint', server.url]) == 0
    assert server.paths == []
    assert state_of(root)['skippedWarm'] == 1 and state_of(root)['pings'] == 0
    assert json.loads(capsys.readouterr().out) == {'action': 'skipped_warm'}


def test_force_pings_through_the_gate(stub, root):
    server = stub()
    assert run_main(['once', '--root', str(root), '--endpoint', server.url, '--force']) == 0
    assert server.posted() == 1 and state_of(root)['pings'] == 1


@pytest.mark.parametrize('age,expected', [(None, 'idle'), (7200.0, 'ping'), (7200.5, 'idle'), (60.0, 'ping'),
                                          (59.9, 'warm'), (0.0, 'warm'), (-5.0, 'warm'), (300.0, 'ping')])
def test_gate_boundaries(age, expected):
    now = 1_000_000.0
    newest = None if age is None else now - age
    assert laya_keepwarm.gate(newest, now, 7200, 60, laya=newest) == expected


def test_only_a_real_laya_call_counts_as_warm():
    """Fable final review: a fresh receipt or log row (e.g. a Codex guardian review) proves activity, not warmth."""
    now = 1_000_000.0
    assert laya_keepwarm.gate(now - 5, now, 7200, 60) == 'ping'                       # activity only: ping
    assert laya_keepwarm.gate(now - 5, now, 7200, 60, laya=now - 5) == 'warm'         # a Laya call 5 s ago
    assert laya_keepwarm.gate(now - 5, now, 7200, 60, laya=now - 600) == 'ping'       # last Laya call is stale


@pytest.mark.parametrize('source', ['log', 'receipts', 'records'])
def test_each_activity_source_counts_on_its_own(stub, root, tmp_path, source):
    server = stub()
    activity(tmp_path, 300, source=source)
    assert run_main(['once', '--root', str(root), '--endpoint', server.url]) == 0
    assert server.posted() == 1


def test_newest_activity_is_the_maximum_and_ignores_garbage(root, tmp_path):
    now = 2_000_000_000.0
    assert laya_keepwarm.newest_activity(root, now) is None
    activity(tmp_path, 5000, now=now, source='log')
    activity(tmp_path, 900, now=now, source='receipts')
    older = activity(tmp_path, 4000, now=now, source='records')
    assert laya_keepwarm.newest_activity(root, now) == now - 900
    (older.parent / '2026-10-12.jsonl').write_text('x')
    set_mtime(older.parent / '2026-10-12.jsonl', now - 100)
    assert laya_keepwarm.newest_activity(root, now) == now - 100               # newest file in the records dir
    set_mtime(older.parent / '2026-10-12.jsonl', now + 86400)                  # a far-future mtime is ignored
    assert laya_keepwarm.newest_activity(root, now) == now - 900


def test_symlinked_records_files_and_directory_are_not_activity(root, tmp_path):
    now = 2_000_000_000.0
    target = tmp_path / 'elsewhere.jsonl'
    target.write_text('x')
    set_mtime(target, now - 100)
    directory = root / 'skill-fit' / 'records'
    directory.mkdir(parents=True)
    (directory / 'link.jsonl').symlink_to(target)
    assert laya_keepwarm.newest_activity(root, now) is None                    # a symlinked file is not followed
    real = tmp_path / 'real-records'
    real.mkdir()
    (real / '2026-10-11.jsonl').write_text('x')
    set_mtime(real / '2026-10-11.jsonl', now - 100)
    other = tmp_path / 'other-store'
    (other / 'skill-fit').mkdir(parents=True)
    (other / 'skill-fit' / 'records').symlink_to(real, target_is_directory=True)
    assert laya_keepwarm.newest_activity(other, now) is None                   # nor is a symlinked directory


def test_xdg_data_home_empty_falls_back_to_the_home_default(monkeypatch, tmp_path, root):
    monkeypatch.setenv('XDG_DATA_HOME', '')
    receipts, log, records_dir = laya_keepwarm.activity_sources(root)
    assert receipts == Path.home() / '.local' / 'share' / 'rhize' / 'workflow-selection' / 'receipts'
    assert log == Path(os.environ['RHIZE_SUGGESTION_LOG']) and records_dir == root / 'skill-fit' / 'records'
    monkeypatch.delenv('RHIZE_SUGGESTION_LOG')
    assert laya_keepwarm.activity_sources(root)[1] == Path.home() / '.claude' / 'context-manager' / 'suggestion-log.jsonl'


# ---------------------------------------------------------------- failures, backoff and reset

def make_worker(root, endpoint, clock, **kwargs):
    kwargs.setdefault('wait_for_health', False)
    return laya_keepwarm.KeepWarm(root, endpoint=endpoint, clock=clock, **kwargs)


def drive(worker, clock, ticks):
    """Run `ticks` loop iterations on the fake clock; returns the waits the loop asked for."""
    waits = []

    def sleep(seconds):
        waits.append(seconds)
        clock.advance(seconds)
    laya_keepwarm.run_loop(worker, sleep=sleep, max_iterations=ticks)
    return waits


@pytest.mark.parametrize('interval,cap,expected', [(90, 120, [120, 120, 120, 120]), (30, 120, [60, 120, 120, 120]),
                                                   (10, 25, [20, 25, 25, 25])])
def test_backoff_doubles_to_the_cap_and_resets_on_success(stub, root, tmp_path, interval, cap, expected):
    server = stub(post_status=500)
    clock = FakeClock()
    activity(tmp_path, 400, now=clock.now)
    worker = make_worker(root, server.url, clock, interval=interval, max_backoff=cap)
    assert drive(worker, clock, 5) == expected                                  # 4 sleeps between 5 ticks
    state = state_of(root)
    assert state['pings'] == 5 and state['ok'] == 0 and state['consecutiveFailures'] == 5
    assert state['lastStatus'] == 'unavailable' and state['intervalSeconds'] == interval
    server.post_status = 200                                                    # the server recovers
    assert drive(worker, clock, 2)[0] == interval                               # first success: back to the base
    state = state_of(root)
    assert state['ok'] == 2 and state['consecutiveFailures'] == 0 and state['lastStatus'] == 'ok'
    assert state['pings'] == 5 + 2


def test_idle_and_warm_ticks_do_not_ping_and_keep_the_current_wait(stub, root, tmp_path):
    server = stub()
    clock = FakeClock()
    log = activity(tmp_path, 3 * 3600, now=clock.now)
    worker = make_worker(root, server.url, clock)
    assert drive(worker, clock, 3) == [90, 90]
    assert server.paths == [] and state_of(root)['skippedIdle'] == 3
    set_mtime(log, clock.now - 5)                                               # activity, but no Laya call: ping
    drive(worker, clock, 1)
    assert server.posted() == 1 and state_of(root)['skippedWarm'] == 0
    laya_record(tmp_path, 5, now=clock.now)                                     # a hook's Laya call answered 5 s ago
    drive(worker, clock, 1)
    assert server.posted() == 1 and state_of(root)['skippedWarm'] == 1
    clock.advance(90)                                                           # that call is now 95 s old...
    set_mtime(log, clock.now - 200)                                             # ...and activity is recent: ping
    drive(worker, clock, 1)
    assert server.posted() == 2 and state_of(root)['pings'] == 2


def test_loop_stops_pinging_when_activity_ages_out_of_the_window(stub, root, tmp_path):
    server = stub()
    clock = FakeClock()
    activity(tmp_path, 7200 - 100, now=clock.now)                               # idles out after 100 s
    worker = make_worker(root, server.url, clock)
    drive(worker, clock, 4)                                                     # t = 0, 90 (ping), 180, 270 (idle)
    state = state_of(root)
    assert state['pings'] == 2 and state['skippedIdle'] == 2 and server.posted() == 2


@pytest.mark.parametrize('kind,expected', [('post500', 'unavailable'), ('redirect', 'redirect_refused'),
                                           ('identity', 'identity_failed'), ('health500', 'unavailable')])
def test_failure_statuses_are_recorded_and_counted(stub, root, tmp_path, kind, expected):
    server = stub(post_status=500 if kind == 'post500' else 200, redirect_on='post' if kind == 'redirect' else None,
                  loaded=['other-model'] if kind == 'identity' else ['typed-decisions'],
                  health_status=500 if kind == 'health500' else 200)
    activity(tmp_path, 300)
    assert run_main(['once', '--root', str(root), '--endpoint', server.url]) == 1
    state = state_of(root)
    assert state['lastStatus'] == expected and state['pings'] == 1 and state['ok'] == 0
    assert state['consecutiveFailures'] == 1
    if kind in ('identity', 'health500'):
        assert server.posted() == 0                                             # no ping body before identity passes


def test_a_dead_server_is_reported_quickly_not_hung_on(root, tmp_path):
    activity(tmp_path, 300)
    started = time.monotonic()
    assert run_main(['once', '--root', str(root), '--endpoint', closed_port_url(), '--timeout-ms', '3000']) == 1
    assert time.monotonic() - started < 3
    assert state_of(root)['lastStatus'] in ('unavailable', 'timeout') and state_of(root)['consecutiveFailures'] == 1


# ---------------------------------------------------------------- run: the first ping waits for /health

def test_run_waits_for_health_before_the_first_ping(stub, root, tmp_path):
    server = stub(health_status=503)
    clock = FakeClock()
    activity(tmp_path, 400, now=clock.now)
    worker = make_worker(root, server.url, clock, wait_for_health=True)
    waits = drive(worker, clock, 4)
    assert waits == [5, 5, 5] and server.posted() == 0
    state = state_of(root)
    assert state['pings'] == 0 and state['consecutiveFailures'] == 0 and state['lastStatus'] == 'unavailable'
    assert state['lastPingAt'] is None
    server.health_status = 200
    assert drive(worker, clock, 1) == []
    state = state_of(root)
    assert server.posted() == 1 and state['pings'] == 1 and state['ok'] == 1 and state['lastStatus'] == 'ok'


# ---------------------------------------------------------------- refusals

@pytest.mark.parametrize('endpoint', ['http://localhost:8000', 'http://10.0.0.5:8000', 'https://127.0.0.1:8000',
                                      'http://127.0.0.1:8000/x', 'http://0.0.0.0:8000', 'http://127.0.0.1',
                                      'http://[::ffff:127.0.0.1]:8000', 'http://user@127.0.0.1:8000', ''])
@pytest.mark.parametrize('command', ['once', 'run'])
def test_non_loopback_endpoint_is_rejected_with_no_io(endpoint, command, root, capsys):
    assert run_main([command, '--root', str(root), '--endpoint', endpoint, '--max-iterations', '1']
                    if command == 'run' else [command, '--root', str(root), '--endpoint', endpoint, '--force']) == 2
    assert json.loads(capsys.readouterr().out)['status'] == 'refused'
    assert not root.exists()
    with pytest.raises(ValueError):
        laya_keepwarm.KeepWarm(root, endpoint=endpoint)


def test_a_loopback_endpoint_on_another_port_is_accepted(stub, root, tmp_path):
    server = stub()
    activity(tmp_path, 300)
    assert laya_choice.is_loopback_endpoint(server.url)
    assert run_main(['once', '--root', str(root), '--endpoint', server.url]) == 0


@pytest.mark.parametrize('command', ['once', 'run'])
def test_laya_keepwarm_zero_exits_immediately(command, stub, root, capsys, monkeypatch):
    server = stub()
    monkeypatch.setenv('LAYA_KEEPWARM', '0')
    args = [command, '--root', str(root), '--endpoint', server.url]
    assert run_main(args + (['--force'] if command == 'once' else [])) == 0
    assert json.loads(capsys.readouterr().out) == {'status': 'disabled'}
    assert server.paths == [] and not root.exists()
    monkeypatch.setenv('LAYA_KEEPWARM', '1')                                    # only the literal 0 disables
    assert run_main(['once', '--root', str(root), '--endpoint', server.url, '--force']) == 0
    assert server.posted() == 1


def test_laya_keepwarm_zero_subprocess_exits_zero_fast(stub, root):
    env = {**os.environ, 'LAYA_KEEPWARM': '0', 'PYTHONDONTWRITEBYTECODE': '1'}
    started = time.monotonic()
    for command in ('once', 'run'):
        done = subprocess.run([sys.executable, str(SCRIPT), command, '--root', str(root)], env=env,
                              capture_output=True, text=True, timeout=30)
        assert done.returncode == 0
    assert time.monotonic() - started < 10 and not root.exists()


def test_bad_option_values_are_usage_errors(root, capsys):
    for args in (['once', '--interval', '0'], ['once', '--interval', 'x'], ['once', '--timeout-ms', '-1'],
                 ['once', '--active-window-hours', '0']):
        with pytest.raises(SystemExit) as raised:
            run_main(args + ['--root', str(root)])
        assert raised.value.code == 2
    assert run_main(['once', '--root', str(root), '--interval', '300', '--max-backoff', '120']) == 2
    capsys.readouterr()


def test_symlinked_state_path_is_refused(stub, root, tmp_path):
    server = stub()
    activity(tmp_path, 300)
    root.mkdir(mode=0o700)
    target = tmp_path / 'victim.json'
    target.write_text('untouched')
    (root / 'laya-keepwarm.json').symlink_to(target)
    assert run_main(['once', '--root', str(root), '--endpoint', server.url]) == 1
    assert target.read_text() == 'untouched'
    with pytest.raises(ValueError):
        laya_keepwarm.save_state(root, laya_keepwarm.initial_state(time.time(), 90, 2))
    assert laya_keepwarm.load_state(root) is None


def test_symlinked_root_is_refused(stub, tmp_path):
    server = stub()
    real = tmp_path / 'real'
    real.mkdir()
    link = tmp_path / 'link'
    link.symlink_to(real, target_is_directory=True)
    assert run_main(['once', '--root', str(link), '--endpoint', server.url, '--force']) == 1
    assert server.paths == [] and list(real.iterdir()) == []


# ---------------------------------------------------------------- status

def test_status_prints_the_state_file_as_json(stub, root, tmp_path, capsys):
    assert run_main(['status', '--root', str(root)]) == 1
    assert json.loads(capsys.readouterr().out) == {'status': 'absent'}
    server = stub()
    activity(tmp_path, 300)
    run_main(['once', '--root', str(root), '--endpoint', server.url])
    capsys.readouterr()
    assert run_main(['status', '--root', str(root)]) == 0
    assert json.loads(capsys.readouterr().out) == state_of(root)
    (root / 'laya-keepwarm.json').write_text('{broken')
    assert run_main(['status', '--root', str(root)]) == 1
    assert json.loads(capsys.readouterr().out)['status'] == 'unreadable'


# ---------------------------------------------------------------- single writer

def test_once_does_not_ping_while_a_run_agent_holds_the_lock(stub, root, tmp_path, capsys):
    server = stub()
    activity(tmp_path, 300)
    root.mkdir(mode=0o700)
    held = locked_io.try_lock(root / 'laya-keepwarm.lock')
    try:
        assert run_main(['once', '--root', str(root), '--endpoint', server.url]) == 0
        assert json.loads(capsys.readouterr().out) == {'status': 'busy'}
        assert server.paths == [] and not (root / 'laya-keepwarm.json').exists()
    finally:
        locked_io.release_lock(held)
    assert run_main(['once', '--root', str(root), '--endpoint', server.url]) == 0
    assert server.posted() == 1


# ---------------------------------------------------------------- the CLI loop, in process

def test_run_in_process_with_injected_clock_sleep_and_max_iterations(stub, root, tmp_path, capsys):
    server = stub()
    clock = FakeClock()
    activity(tmp_path, 400, now=clock.now)
    waits = []

    def sleep(seconds):
        waits.append(seconds)
        clock.advance(seconds)
    assert run_main(['run', '--root', str(root), '--endpoint', server.url, '--max-iterations', '3'],
                    clock=clock, sleep=sleep) == 0
    assert waits == [90, 90] and server.posted() == 3
    state = state_of(root)
    assert state['pings'] == 3 and state['ok'] == 3
    assert json.loads(capsys.readouterr().out) == {'status': 'stopped', 'ticks': 3, 'pings': 3, 'ok': 3}


@pytest.mark.parametrize('basis,status', [('backfill', 'skipped'), ('backfill', 'ok'), ('live', 'skipped'),
                                          ('live', 'timeout'), ('live', 'unavailable'), ('live', 'invalid')])
def test_records_that_never_reached_inference_do_not_count_as_warm(stub, root, tmp_path, capsys, basis, status):
    server = stub()
    laya_record(tmp_path, 5, basis=basis, status=status)                      # fresh file mtime, but no live ok call
    assert run_main(['once', '--root', str(root), '--endpoint', server.url]) == 0
    assert server.posted() == 1 and state_of(root)['skippedWarm'] == 0
    assert json.loads(capsys.readouterr().out)['action'] == 'ping'


def test_warm_signal_uses_the_record_ts_not_the_file_mtime(root, tmp_path):
    now = time.time()
    path = laya_record(tmp_path, 600, now=now)                                 # a live ok call 10 minutes ago
    set_mtime(path, now)                                                       # ...in a file touched just now
    assert laya_keepwarm.newest_laya_call(root, now) == pytest.approx(now - 600, abs=1)
    laya_record(tmp_path, 3, now=now, basis='backfill', status='skipped')      # a backfill appended afterwards
    assert laya_keepwarm.newest_laya_call(root, now) == pytest.approx(now - 600, abs=1)
    laya_record(tmp_path, 4, now=now)
    assert laya_keepwarm.newest_laya_call(root, now) == pytest.approx(now - 4, abs=1)


def test_warm_signal_reads_the_two_newest_day_files_and_ignores_junk(root, tmp_path):
    now = time.time()
    laya_record(tmp_path, 20, now=now, day='2026-10-10')                       # just before UTC midnight
    laya_record(tmp_path, 900, now=now, day='2026-10-11')
    directory = root / 'skill-fit' / 'records'
    with (directory / '2026-10-11.jsonl').open('a') as handle:
        handle.write('not json\n[1, 2]\n{"basis": "live", "laya": {"status": "ok"}, "ts": "garbage"}\n')
    assert laya_keepwarm.newest_laya_call(root, now) == pytest.approx(now - 20, abs=1)
    laya_record(tmp_path, 1, now=now, day='2026-10-01')                        # an older day-file is not read
    (directory / 'notes.txt').write_text('{"basis": "live"}\n')
    assert laya_keepwarm.newest_laya_call(root, now) == pytest.approx(now - 20, abs=1)
    laya_record(tmp_path, -3600, now=now, day='2026-10-12')                    # an hour in the future: clock garbage
    assert laya_keepwarm.newest_laya_call(root, now) == pytest.approx(now - 900, abs=1)


def test_warm_signal_refuses_symlinked_day_files_and_directories(root, tmp_path):
    now = time.time()
    real = laya_record(tmp_path, 5, now=now, root=tmp_path / 'elsewhere')
    directory = root / 'skill-fit' / 'records'
    directory.mkdir(parents=True)
    (directory / '2026-10-11.jsonl').symlink_to(real)
    assert laya_keepwarm.newest_laya_call(root, now) is None
    other = tmp_path / 'other-root'
    (other / 'skill-fit').mkdir(parents=True)
    (other / 'skill-fit' / 'records').symlink_to(real.parent, target_is_directory=True)
    assert laya_keepwarm.newest_laya_call(other, now) is None


def test_warm_signal_reads_only_a_bounded_tail(root, tmp_path, monkeypatch):
    now = time.time()
    path = laya_record(tmp_path, 5, now=now)                                   # the ok call is at the file start
    with path.open('a') as handle:
        handle.write(('{"basis": "backfill", "laya": {"status": "skipped"}, "pad": "' + 'x' * 200 + '"}\n') * 50)
    monkeypatch.setattr(laya_keepwarm, 'MAX_RECORD_TAIL_BYTES', 4096)
    assert laya_keepwarm.newest_laya_call(root, now) is None                   # out of the tail: unknown, so ping


def test_run_exits_1_when_the_final_state_write_fails(stub, root, tmp_path, capsys):
    server = stub()
    clock = FakeClock()
    activity(tmp_path, 400, now=clock.now)
    root.mkdir(mode=0o700)
    (root / 'laya-keepwarm.json').symlink_to(tmp_path / 'nowhere')
    assert run_main(['run', '--root', str(root), '--endpoint', server.url, '--max-iterations', '2'],
                    clock=clock, sleep=lambda s: clock.advance(s)) == 1
    out = json.loads(capsys.readouterr().out)
    assert out['status'] == 'failed' and out['reason'] == 'final state write failed' and out['pings'] == 2
    assert server.posted() == 2 and not (tmp_path / 'nowhere').exists()


def test_a_failing_state_write_does_not_end_the_loop(stub, root, tmp_path):
    server = stub()
    clock = FakeClock()
    activity(tmp_path, 400, now=clock.now)
    worker = make_worker(root, server.url, clock)
    errors = []
    root.mkdir(mode=0o700)
    (root / 'laya-keepwarm.json').symlink_to(tmp_path / 'nowhere')
    ticks = laya_keepwarm.run_loop(worker, sleep=lambda s: clock.advance(s), max_iterations=3, on_error=errors.append)
    assert ticks == 3 and server.posted() == 3 and errors and not (tmp_path / 'nowhere').exists()
    assert worker.final_save_ok is False


# ---------------------------------------------------------------- SIGTERM / SIGINT

def wait_for(predicate, seconds=15.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    raise AssertionError('condition not reached in time')


@pytest.mark.parametrize('sig', [signal.SIGTERM, signal.SIGINT])
def test_signals_exit_cleanly_after_writing_state(sig, stub, root, tmp_path):
    server = stub()
    activity(tmp_path, 400)
    env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}
    proc = subprocess.Popen([sys.executable, str(SCRIPT), 'run', '--root', str(root), '--endpoint', server.url,
                             '--interval', '1', '--max-backoff', '2', '--warm-skip-seconds', '0'], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        def pinged():
            try:
                return state_of(root)['pings'] >= 1
            except (OSError, ValueError):
                return False
        wait_for(pinged)
        proc.send_signal(sig)
        out, err = proc.communicate(timeout=15)
    finally:
        if proc.poll() is None:
            proc.kill()
    assert proc.returncode == 0 and err == ''
    assert json.loads(out)['status'] == 'stopped'
    state = state_of(root)
    assert set(state) == STATE_FIELDS and state['pings'] >= 1 and state['lastStatus'] == 'ok'
    assert stat.S_IMODE(os.stat(root / 'laya-keepwarm.json').st_mode) == 0o600


def test_second_run_instance_is_refused_while_one_holds_the_lock(stub, root, tmp_path):
    server = stub()
    activity(tmp_path, 400)
    env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}
    proc = subprocess.Popen([sys.executable, str(SCRIPT), 'run', '--root', str(root), '--endpoint', server.url,
                             '--interval', '1', '--max-backoff', '2', '--warm-skip-seconds', '0'], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        wait_for(lambda: (root / 'laya-keepwarm.json').exists())
        second = subprocess.run([sys.executable, str(SCRIPT), 'run', '--root', str(root), '--endpoint', server.url,
                                 '--max-iterations', '1'], env=env, capture_output=True, text=True, timeout=30)
        assert second.returncode == 0 and json.loads(second.stdout) == {'status': 'busy'}
    finally:
        proc.send_signal(signal.SIGTERM)
        proc.communicate(timeout=15)
    assert proc.returncode == 0
