"""Loopback-only typed transport; every server is a real http.server on an ephemeral 127.0.0.1 port."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import threading
import urllib.request

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'rhize-context-manager/scripts'))
import typed_advice as transport

M = 'typed-decisions'


class Handler(BaseHTTPRequestHandler):
    hits = []
    loaded = ['typed-decisions']

    def do_GET(self):
        Handler.hits.append(self.path)
        if self.path == '/health':
            self.send(200, json.dumps({'loaded': Handler.loaded}).encode())
        else:
            self.send(404, b'{}')

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
        Handler.hits.append(self.path)
        if self.path == '/ok':
            self.send(200, json.dumps({'echo': json.loads(body), 'path': self.path}).encode())
        elif self.path == '/redirect':
            self.send_response(302)
            self.send_header('Location', '/ok')
            self.send_header('Content-Length', '0')
            self.end_headers()
        elif self.path == '/big':
            self.send(200, json.dumps({'pad': 'x' * 5000}).encode())
        elif self.path == '/notjson':
            self.send(200, b'not json')
        elif self.path == '/list':
            self.send(200, b'[1, 2]')
        else:
            self.send(500, b'{"error": "boom"}')

    def send(self, status, body):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def server():
    Handler.hits = []
    Handler.loaded = ['typed-decisions']
    httpd = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=lambda: httpd.serve_forever(poll_interval=0.01), daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{httpd.server_address[1]}'
    httpd.shutdown()
    httpd.server_close()
    thread.join(5)


def test_posts_json_to_a_literal_loopback_ip_and_reports_latency(server):
    value, latency = transport.post_local(server, '/ok', {'model': M, 'a': 1}, 5)
    assert value == {'echo': {'model': M, 'a': 1}, 'path': '/ok'} and latency >= 0
    assert Handler.hits == ['/health', '/ok']  # identity probe precedes any request text
    assert transport.post_local(server + '/', '/ok', lambda: {'model': M, 'b': 2}, 5)[0]['echo']['b'] == 2


def test_identity_probe_failure_sends_nothing(server):
    Handler.loaded = ['other-model']
    with pytest.raises(ValueError, match='identity_failed'):
        transport.post_local(server, '/ok', {'model': M, 'request': 'text'}, 5)
    assert Handler.hits == ['/health']


def test_check_identity_probes_health_only_and_rejects_a_foreign_server(server):
    transport.check_identity(server)
    assert Handler.hits == ['/health']
    Handler.loaded = ['other-model']
    with pytest.raises(ValueError, match='identity_failed'):
        transport.check_identity(server)
    with pytest.raises(ValueError, match='loopback_ip_url_required'):
        transport.check_identity('http://localhost:8000')


def test_fresh_probe_cache_skips_the_probe(server, tmp_path):
    cache = tmp_path / 'health.json'
    transport.post_local(server, '/ok', {'model': M}, 5, health_cache=cache)
    transport.post_local(server, '/ok', {'model': M}, 5, health_cache=cache)
    assert Handler.hits == ['/health', '/ok', '/ok'] and oct(cache.stat().st_mode & 0o777) == '0o600'


@pytest.mark.parametrize('url', [
    'http://localhost:8000', 'http://10.0.0.1:8000', 'https://127.0.0.1:8000', 'http://127.0.0.1:8000/v1',
    'http://user:secret@127.0.0.1:8000', 'http://127.0.0.1:8000?x=1', 'http://127.0.0.1:8000#frag',
    'http://127.0.0.1', 'http://127.0.0.1:0', 'http://127.0.0.1:99999', 'http://127.0.0.2:8000',
    'http://0.0.0.0:8000', 'http://[::2]:8000', 'http://example.test:8000', 'http://127.0.0.1:8000 ', None, 8000])
def test_destination_must_be_exactly_a_loopback_ip_with_port(url):
    called = []
    with pytest.raises(ValueError, match='loopback_ip_url_required'):
        transport.post_local(url, '/ok', lambda: called.append('built') or {'secret': 'text'}, 5)
    assert called == []  # the payload is never built for a rejected destination


@pytest.mark.parametrize('path', ['', 'ok', '/a?b=1', '/a#b', '/a b', '/a\n', None])
def test_path_must_be_a_plain_absolute_path(server, path):
    called = []
    with pytest.raises(ValueError, match='invalid_path'):
        transport.post_local(server, path, lambda: called.append(1) or {}, 5)
    assert called == [] and Handler.hits == []


def test_ipv6_loopback_literal_is_accepted_by_the_destination_check():
    assert transport._destination('http://[::1]:8000', '/v1/systemone') == 'http://[::1]:8000/v1/systemone'


def test_proxy_environment_is_ignored(server, monkeypatch):
    for name in ('HTTP_PROXY', 'http_proxy', 'ALL_PROXY', 'all_proxy'):
        monkeypatch.setenv(name, 'http://127.0.0.1:9')  # nothing listens here
    monkeypatch.delenv('NO_PROXY', raising=False)
    monkeypatch.delenv('no_proxy', raising=False)
    assert urllib.request.getproxies().get('http') == 'http://127.0.0.1:9'  # the mutation is live
    with pytest.raises(OSError):
        # Control: a fresh default opener honours it (a globally installed opener may not).
        urllib.request.build_opener().open(server + '/ok', data=b'{}', timeout=2)
    assert transport.post_local(server, '/ok', {'model': M, 'x': 1}, 5)[0]['path'] == '/ok'


def test_redirects_are_refused_and_never_followed(server):
    with pytest.raises(ValueError, match='redirect_refused'):
        transport.post_local(server, '/redirect', {'model': M, 'x': 1}, 5)
    assert Handler.hits == ['/health', '/redirect']


def test_oversized_response_is_refused(server):
    with pytest.raises(ValueError, match='response_too_large'):
        transport.post_local(server, '/big', {'model': M}, 5, max_bytes=1024)
    assert transport.post_local(server, '/big', {'model': M}, 5)[0]['pad'] == 'x' * 5000


def test_non_object_or_non_json_responses_and_http_errors_are_refused(server):
    with pytest.raises(ValueError, match='response_not_json'):
        transport.post_local(server, '/notjson', {'model': M}, 5)
    with pytest.raises(ValueError, match='response_not_object'):
        transport.post_local(server, '/list', {'model': M}, 5)
    with pytest.raises(OSError):
        transport.post_local(server, '/other', {'model': M}, 5)


def test_payload_text_never_appears_in_errors(server):
    secret = 'invented-private-request-text'
    for path in ('/notjson', '/redirect', '/other'):
        with pytest.raises((ValueError, OSError)) as caught:
            transport.post_local(server, path, {'model': M, 'request': secret}, 5)
        assert secret not in str(caught.value) and secret not in repr(caught.value)
    with pytest.raises(ValueError) as caught:
        transport.post_local('http://localhost:1', '/x', {'request': secret}, 5)
    assert secret not in str(caught.value)


@pytest.mark.parametrize('payload', [[1], 'text', None, lambda: [1], {'no': 'model'}])
def test_payload_must_be_an_object(server, payload):
    with pytest.raises(ValueError, match='invalid_payload'):
        transport.post_local(server, '/ok', payload, 5)


@pytest.mark.parametrize('timeout', [0, -1, float('nan'), True, None, '5'])
def test_timeout_must_be_a_positive_number(server, timeout):
    with pytest.raises(ValueError, match='invalid_timeout'):
        transport.post_local(server, '/ok', {}, timeout)
