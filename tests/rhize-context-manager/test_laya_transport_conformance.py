"""Conformance: typed_advice.choice and typed_decisions.laya_choice.call_choice must classify the same
loopback server behaviours the same way (plan 2026-10-16 section 11, "Drift from laya_choice.py").

Every server here is a real http.server on an ephemeral 127.0.0.1 port. FakeLaya answers whatever question
shape it is sent, so one server serves both clients.
"""
import json
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / 'rhize-context-manager/scripts'
sys.path.insert(0, str(SCRIPTS))
import typed_advice  # noqa: E402
from typed_decisions import instrument, laya_choice  # noqa: E402

MODEL = 'typed-decisions'


class FakeLaya:
    """Context manager: a loopback server whose /health and POST behaviour are named modes."""

    def __init__(self, health='ok', post='ok', delay=1.0):
        self.health, self.post, self.delay = health, post, delay
        self.hits, self.bodies = [], []

    def __enter__(self):
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def reply(self, status, body, length=True):
                try:
                    self.send_response(status)
                    self.send_header('Content-Type', 'application/json')
                    if length:
                        self.send_header('Content-Length', str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                except OSError:
                    pass  # the client gave up first

            def redirect(self, code):
                self.send_response(code)
                self.send_header('Location', '/elsewhere')
                self.send_header('Content-Length', '0')
                self.end_headers()

            def dribble(self):
                body = json.dumps({'pad': 'x' * 400}).encode()
                try:
                    self.send_response(200)
                    self.send_header('Content-Length', str(len(body)))
                    self.end_headers()
                    for index in range(0, len(body), 8):
                        self.wfile.write(body[index:index + 8])
                        self.wfile.flush()
                        time.sleep(0.12)
                except OSError:
                    pass

            def do_GET(self):
                fake.hits.append(('GET', self.path))
                mode = fake.health
                if mode == 'ok':
                    self.reply(200, json.dumps({'loaded': [MODEL, 'other']}).encode())
                elif mode == 'wrong':
                    self.reply(200, json.dumps({'loaded': ['other-model']}).encode())
                elif mode == 'notjson':
                    self.reply(200, b'<html>not laya</html>')
                elif mode == 'list':
                    self.reply(200, b'["typed-decisions"]')
                elif mode == 'redirect':
                    self.redirect(302)
                elif mode == 'big':
                    self.reply(200, json.dumps({'loaded': [MODEL], 'pad': 'x' * 100000}).encode())
                elif mode == 'slow':
                    time.sleep(fake.delay)
                    self.reply(200, json.dumps({'loaded': [MODEL]}).encode())
                else:
                    self.reply(500, b'{}')

            def do_POST(self):
                raw = self.rfile.read(int(self.headers.get('Content-Length', 0)))
                fake.hits.append(('POST', self.path))
                try:
                    fake.bodies.append(json.loads(raw))
                except ValueError:
                    fake.bodies.append(None)
                mode = fake.post
                if mode in ('ok', 'wrong_model', 'bad_probs', 'bad_choice'):
                    questions = fake.bodies[-1]['questions']
                    qid = next(iter(questions))
                    keys = list(questions[qid]['criteria'])
                    probs = {key: (0.7 if index == 0 else 0.3 / max(1, len(keys) - 1))
                             for index, key in enumerate(keys)}
                    choice = keys[0]
                    if mode == 'bad_probs':
                        probs[keys[0]] = 2
                    if mode == 'bad_choice':
                        choice = 'zz-not-a-key'
                    self.reply(200, json.dumps({
                        'routing': {'model': 'someone-else' if mode == 'wrong_model' else MODEL},
                        'answers': {qid: {'type': 'choice', 'choice': choice, 'probabilities': probs}}}).encode())
                elif mode == 'redirect':
                    self.redirect(302)
                elif mode == 'redirect307':
                    self.redirect(307)
                elif mode == 'big':
                    self.reply(200, json.dumps({'pad': 'x' * 100000}).encode())
                elif mode == 'big_stream':  # no Content-Length: HTTP/1.0 body until close
                    self.reply(200, json.dumps({'pad': 'x' * 100000}).encode(), length=False)
                elif mode == 'slow':
                    time.sleep(fake.delay)
                    self.reply(200, b'{}')
                elif mode == 'trickle':
                    self.dribble()
                elif mode == 'notjson':
                    self.reply(200, b'not json')
                else:
                    self.reply(500, b'{"error": "boom"}')

        self.httpd = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=lambda: self.httpd.serve_forever(poll_interval=0.01), daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.httpd.server_address[1]}'
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(5)


def dead_port_url():
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    sock.close()
    return f'http://127.0.0.1:{port}'


CANDIDATES = [{'id': 'alpha', 'criterion': 'prefer alpha when the task is small'},
              {'id': 'beta', 'criterion': 'prefer beta when the task is large'}]


def ask_advice(endpoint, tmp_path, budget_ms=1500, request='Fix the login page'):
    return typed_advice.choice(request, ['src/app.py'], 'Which one?', CANDIDATES, endpoint=endpoint,
                               budget_ms=budget_ms, store=tmp_path)


def ask_laya(endpoint, budget_ms=1500, request='Fix the login page'):
    built = instrument.build_choice_request(request, [
        {'skillId': 'skill:plug/alpha', 'description': 'alpha skill'},
        {'skillId': 'skill:plug/beta', 'description': 'beta skill'}])
    return laya_choice.call_choice(built['request'], built['keyMap'], endpoint, MODEL, budget_ms)


# (id, health mode, post mode, expected status, budget ms)
CASES = [
    ('ok', 'ok', 'ok', 'ok', 1500),
    ('identity_failed', 'wrong', 'ok', 'identity_failed', 1500),
    ('health_not_json', 'notjson', 'ok', 'identity_failed', 1500),
    ('health_not_object', 'list', 'ok', 'identity_failed', 1500),
    ('health_redirect', 'redirect', 'ok', 'redirect_refused', 1500),
    ('health_oversize', 'big', 'ok', 'invalid', 1500),
    ('health_server_error', 'error', 'ok', 'unavailable', 1500),
    ('post_redirect_302', 'ok', 'redirect', 'redirect_refused', 1500),
    ('post_redirect_307', 'ok', 'redirect307', 'redirect_refused', 1500),
    ('post_oversize', 'ok', 'big', 'invalid', 1500),
    ('post_oversize_no_length', 'ok', 'big_stream', 'invalid', 1500),
    ('post_not_json', 'ok', 'notjson', 'invalid', 1500),
    ('post_wrong_model', 'ok', 'wrong_model', 'invalid', 1500),
    ('post_bad_probabilities', 'ok', 'bad_probs', 'invalid', 1500),
    ('post_unknown_choice', 'ok', 'bad_choice', 'invalid', 1500),
    ('post_server_error', 'ok', 'error', 'unavailable', 1500),
    ('slow_post', 'ok', 'slow', 'timeout', 300),
    ('slow_health', 'slow', 'ok', 'timeout', 300),
]


@pytest.mark.parametrize('health,post,expected,budget', [c[1:] for c in CASES], ids=[c[0] for c in CASES])
def test_both_clients_classify_the_server_behaviour_identically(tmp_path, health, post, expected, budget):
    with FakeLaya(health, post) as fake:
        advice = ask_advice(fake.url, tmp_path, budget)
        advice_hits, fake.hits = list(fake.hits), []
        laya = ask_laya(fake.url, budget)
        laya_hits = list(fake.hits)
    assert (advice['status'], laya['status']) == (expected, expected)
    assert advice_hits == laya_hits  # the same requests, in the same order, reached the server
    if expected == 'ok':
        assert advice['choice'] == 'alpha' and laya['choice'] == 'skill:plug/alpha'
    else:
        assert advice['choice'] is None and laya['choice'] is None
    # Never raises and always reports a latency.
    assert advice['latencyMs'] >= 0 and laya['latencyMs'] >= 0


def _timeout_within_budget(ask):
    started = time.monotonic()
    result = ask()
    assert result['status'] == 'timeout'
    assert time.monotonic() - started < 1.0  # a 0.3 s budget must not be stretched by a slow server


@pytest.mark.parametrize('post', ['slow', 'trickle'])
def test_typed_advice_budget_is_one_deadline_not_a_per_read_timeout(tmp_path, post):
    # 'trickle' sends a 400-byte body in 8-byte pieces 0.12 s apart (about 6 s in total); every piece
    # arrives inside any single socket timeout, so only a deadline re-checked between reads stops it.
    with FakeLaya('ok', post) as fake:
        _timeout_within_budget(lambda: ask_advice(fake.url, tmp_path, 300))


def test_laya_choice_slow_post_stops_at_its_budget():
    with FakeLaya('ok', 'slow') as fake:
        _timeout_within_budget(lambda: ask_laya(fake.url, 300))


def test_laya_choice_trickled_post_stops_at_its_budget():
    with FakeLaya('ok', 'trickle') as fake:
        _timeout_within_budget(lambda: ask_laya(fake.url, 300))


@pytest.mark.parametrize('endpoint', ['http://localhost:{port}', 'http://10.255.255.1:8000', 'https://127.0.0.1:8000',
                                      'http://127.0.0.2:{port}', 'http://0.0.0.0:{port}', 'not a url', None])
def test_non_loopback_endpoints_are_unavailable_with_zero_requests(tmp_path, endpoint):
    with FakeLaya() as fake:
        port = fake.httpd.server_address[1]
        endpoint = endpoint.format(port=port) if isinstance(endpoint, str) else endpoint
        advice, laya = ask_advice(endpoint, tmp_path), ask_laya(endpoint)
        assert fake.hits == []
    assert advice['status'] == laya['status'] == 'unavailable'


def test_connection_refused_is_unavailable_for_both(tmp_path):
    url = dead_port_url()
    assert ask_advice(url, tmp_path)['status'] == ask_laya(url)['status'] == 'unavailable'


@pytest.mark.parametrize('budget', [0, -5])
def test_a_non_positive_budget_is_a_timeout_for_both(tmp_path, budget):
    with FakeLaya() as fake:
        advice, laya = ask_advice(fake.url, tmp_path, budget), ask_laya(fake.url, budget)
        assert fake.hits == []
    assert advice['status'] == laya['status'] == 'timeout'


def test_proxy_environment_never_diverts_either_client(tmp_path, monkeypatch):
    for name in ('HTTP_PROXY', 'http_proxy', 'ALL_PROXY', 'all_proxy'):
        monkeypatch.setenv(name, 'http://127.0.0.1:9')  # nothing listens here
    monkeypatch.delenv('NO_PROXY', raising=False)
    monkeypatch.delenv('no_proxy', raising=False)
    with FakeLaya() as fake:
        advice, laya = ask_advice(fake.url, tmp_path), ask_laya(fake.url)
        assert [h for h in fake.hits if h[0] == 'POST'] == [('POST', '/v1/systemone')] * 2
    assert advice['status'] == laya['status'] == 'ok'


def test_the_identity_probe_precedes_request_text_for_both(tmp_path):
    with FakeLaya('wrong') as fake:
        ask_advice(fake.url, tmp_path, request='private request text')
        ask_laya(fake.url, request='private request text')
        assert fake.hits == [('GET', '/health')] * 2 and fake.bodies == []
