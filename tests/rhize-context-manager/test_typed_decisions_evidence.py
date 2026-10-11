"""Typed-decision evidence pipeline (lane L2): Laya client, transcript scanner, router replay, backfill, outcomes.

Invented fixtures, a fake loopback Laya server and temp directories only. No test starts a model, reaches the
network beyond 127.0.0.1 ports it opens itself, or writes outside tmp_path.
"""
from __future__ import annotations

import copy
import hashlib
import json
import shutil
import socket
import stat
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / 'rhize-context-manager' / 'scripts'
FIX = REPO / 'tests' / 'rhize-context-manager' / 'fixtures' / 'typed-decisions'
sys.path.insert(0, str(SCRIPTS))

from typed_decisions import (backfill, contract, instrument, laya_choice, outcomes, records,  # noqa: E402
                             transcripts)

NODE = shutil.which('node')
needs_node = pytest.mark.skipif(NODE is None, reason='node is required for the router replay')
SENTINEL = 'ZEBRA-SENTINEL-PHRASE'
S1 = '11111111-1111-4111-8111-111111111111'
S2 = '22222222-2222-4222-8222-222222222222'
S3 = '33333333-3333-4333-8333-333333333333'
SEO = 'skill:seo-aeo-geo/seo-site-audit'
GEO = 'skill:seo-aeo-geo/aeo-geo-optimization'
SHIP = 'skill:rhize-devflow/ship'


def sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


# ---------------------------------------------------------------- fake loopback Laya

def default_chooser(req):
    head = req['state']['request']
    criteria = req['questions']['skill']['criteria']
    keys = [k for k in criteria if k != 'none']
    choice = 'none' if 'PICKNONE' in head else keys[-1] if 'PICKLAST' in head else keys[0]
    rest = 0.1 * (len(criteria) - 1)
    probs = {k: 0.1 for k in criteria}
    probs[choice] = round(1 - rest, 6)
    return {'answers': {'skill': {'type': 'choice', 'choice': choice, 'confidence': 0.5, 'probabilities': probs}},
            'routing': {'model': 'typed-decisions'}, 'usage': {'input_tokens': 1, 'output_tokens': 1}}


class FakeLaya:
    """Loopback server with knobs: loaded models, delays, redirects, oversize and non-2xx replies."""

    def __init__(self, loaded=('typed-decisions',), health_delay=0.0, post_delay=0.0, redirect_to=None,
                 redirect_on='post', post_bytes=None, post_status=200, health_status=200, health_bytes=None):
        self.loaded, self.health_delay, self.post_delay = list(loaded), health_delay, post_delay
        self.redirect_to, self.redirect_on = redirect_to, redirect_on
        self.post_bytes, self.post_status = post_bytes, post_status
        self.health_status, self.health_bytes = health_status, health_bytes
        self.health_hits, self.posts, self.paths = 0, [], []
        self.release = threading.Event()
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
                if self.command != 'HEAD':
                    try:
                        self.wfile.write(body)
                    except OSError:
                        pass

            def do_GET(self):
                outer.paths.append(('GET', self.path))
                if self.path != '/health':
                    return self.send(404)
                outer.health_hits += 1
                if outer.health_delay:
                    outer.release.wait(outer.health_delay)
                if outer.redirect_to and outer.redirect_on == 'health':
                    return self.send(302, headers=[('Location', outer.redirect_to + '/health')])
                body = outer.health_bytes if outer.health_bytes is not None else json.dumps(
                    {'status': 'ok', 'loaded': outer.loaded}).encode()
                self.send(outer.health_status, body, [('Content-Type', 'application/json')])

            def do_POST(self):
                outer.paths.append(('POST', self.path))
                length = int(self.headers.get('Content-Length') or 0)
                body = json.loads(self.rfile.read(length) or b'{}')
                outer.posts.append(body)
                if outer.post_delay:
                    outer.release.wait(outer.post_delay)
                if outer.redirect_to and outer.redirect_on == 'post':
                    return self.send(307, headers=[('Location', outer.redirect_to + '/v1/systemone')])
                if outer.post_bytes is not None:
                    return self.send(outer.post_status, outer.post_bytes, [('Content-Type', 'application/json')])
                self.send(outer.post_status, json.dumps(default_chooser(body)).encode(),
                          [('Content-Type', 'application/json')])

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self):
        return 'http://127.0.0.1:%d' % self.server.server_address[1]

    def close(self):
        self.release.set()
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def make_laya():
    made = []

    def make(**kwargs):
        made.append(FakeLaya(**kwargs))
        return made[-1]
    yield make
    for server in made:
        server.close()


def closed_port_url():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return 'http://127.0.0.1:%d' % sock.getsockname()[1]


def built(prompt='Audit the SEO of the site'):
    return instrument.build_choice_request(prompt, [{'skillId': SEO, 'description': 'Audit a site for SEO.'},
                                                    {'skillId': GEO, 'description': 'Optimize for answer engines.'}])


def ask(server_url, prompt='Audit the SEO of the site', budget_ms=2000, **kwargs):
    item = built(prompt)
    return laya_choice.call_choice(item['request'], item['keyMap'], server_url, 'typed-decisions', budget_ms, **kwargs)


# ---------------------------------------------------------------- A2: Laya client

def test_ok_answer_is_decoded_and_aligned(make_laya):
    server = make_laya()
    result = ask(server.url)
    assert result['status'] == 'ok' and result['choice'] == SEO
    assert len(result['probabilities']) == 3 and abs(sum(result['probabilities']) - 1) < 1e-6
    assert isinstance(result['latencyMs'], float) and result['latencyMs'] >= 0
    assert [p[0] for p in server.paths] == ['GET', 'POST'] and server.paths[0][1] == '/health'
    assert server.posts[0]['model'] == 'typed-decisions'


def test_none_answer_and_last_candidate(make_laya):
    server = make_laya()
    assert ask(server.url, 'PICKNONE please')['choice'] == 'none'
    assert ask(server.url, 'PICKLAST please')['choice'] == GEO


@pytest.mark.parametrize('endpoint', ['http://localhost:%d', 'http://127.0.0.1.evil.test:%d', 'https://127.0.0.1:%d',
                                      'http://user@127.0.0.1:%d', 'http://0.0.0.0:%d', 'http://127.0.0.2:%d',
                                      'http://[::ffff:127.0.0.1]:%d', 'http://127.0.0.1:%d/', 'http://127.0.0.1',
                                      'http://127.0.0.1:99999'])
def test_only_literal_loopback_endpoints_and_no_io_otherwise(endpoint, make_laya):
    server = make_laya()
    port = server.server.server_address[1]
    endpoint = endpoint % port if '%d' in endpoint else endpoint

    class Forbidden:
        def open(self, *args, **kwargs):
            raise AssertionError('no I/O may happen for a refused endpoint')
    item = built()
    result = laya_choice.call_choice(item['request'], item['keyMap'], endpoint, 'typed-decisions', 500,
                                     opener=Forbidden())
    assert result['status'] == 'unavailable' and server.paths == []


def test_ipv6_loopback_literal_is_accepted():
    assert laya_choice.is_loopback_endpoint('http://[::1]:8000')
    assert laya_choice.is_loopback_endpoint('http://127.0.0.1:8000')
    assert not laya_choice.is_loopback_endpoint('http://localhost:8000')


@pytest.mark.parametrize('on', ['health', 'post'])
def test_redirects_are_refused_and_never_followed(on, make_laya):
    target = make_laya()
    server = make_laya(redirect_to=target.url, redirect_on=on)
    result = ask(server.url)
    assert result['status'] == 'redirect_refused' and result['choice'] is None
    assert target.paths == []                                   # the redirect target saw nothing


def test_external_redirect_location_is_refused(make_laya):
    server = make_laya(redirect_to='http://203.0.113.9:80', redirect_on='health')
    assert ask(server.url)['status'] == 'redirect_refused'


def test_proxy_environment_is_ignored(make_laya, monkeypatch):
    for name in ('http_proxy', 'HTTP_PROXY', 'all_proxy', 'ALL_PROXY'):
        monkeypatch.setenv(name, 'http://127.0.0.1:9')
    monkeypatch.delenv('no_proxy', raising=False)
    monkeypatch.delenv('NO_PROXY', raising=False)
    assert ask(make_laya().url)['status'] == 'ok'


def test_identity_probe_must_list_the_model(make_laya):
    server = make_laya(loaded=['some-other-model'])
    result = ask(server.url)
    assert result['status'] == 'identity_failed' and server.posts == []        # no prompt was ever sent


@pytest.mark.parametrize('body', [b'not json', b'[]', b'{"loaded": "typed-decisions"}', b'{}'])
def test_unusable_probe_bodies_fail_identity(body, make_laya):
    server = make_laya(health_bytes=body)
    assert ask(server.url)['status'] == 'identity_failed' and server.posts == []


def test_loaded_must_be_a_list_of_model_names(make_laya):
    # Same rule as the Node client: the real server answers {"loaded": ["typed-decisions"]}.
    assert ask(make_laya(loaded=['other', 'typed-decisions']).url)['status'] == 'ok'
    assert ask(make_laya(loaded=[{'name': 'typed-decisions'}]).url)['status'] == 'identity_failed'


def test_oversize_responses_are_invalid(make_laya):
    server = make_laya(post_bytes=b'{"pad":"' + b'x' * (laya_choice.MAX_RESPONSE_BYTES + 10) + b'"}')
    assert ask(server.url)['status'] == 'invalid'
    big_health = make_laya(health_bytes=b'{"loaded":["typed-decisions"],"pad":"' + b'x' * 70000 + b'"}')
    assert ask(big_health.url)['status'] == 'invalid' and big_health.posts == []


@pytest.mark.parametrize('payload', [b'garbage', b'{"answers":{}}', b'[]',
                                     json.dumps({'answers': {'skill': {'type': 'choice', 'choice': 's9',
                                                                       'probabilities': {}}},
                                                 'routing': {'model': 'typed-decisions'}}).encode()])
def test_malformed_choice_bodies_are_invalid(payload, make_laya):
    assert ask(make_laya(post_bytes=payload).url)['status'] == 'invalid'


def test_non_2xx_and_refused_connections_are_unavailable(make_laya):
    assert ask(make_laya(post_status=500, post_bytes=b'{}').url)['status'] == 'unavailable'
    assert ask(make_laya(health_status=503, health_bytes=b'{}').url)['status'] == 'unavailable'
    assert ask(closed_port_url())['status'] == 'unavailable'


def test_hanging_probe_times_out_inside_the_budget(make_laya):
    server = make_laya(health_delay=30)
    began = time.monotonic()
    result = ask(server.url, budget_ms=300)
    assert result['status'] == 'timeout' and time.monotonic() - began < 2 and result['latencyMs'] < 1500
    assert server.posts == []


def test_hanging_post_times_out_inside_the_budget(make_laya):
    server = make_laya(post_delay=30)
    began = time.monotonic()
    assert ask(server.url, budget_ms=300)['status'] == 'timeout'
    assert time.monotonic() - began < 2


def test_one_deadline_covers_probe_and_post(make_laya):
    server = make_laya(health_delay=0.4, post_delay=0.4)       # each fits alone; together they do not
    began = time.monotonic()
    assert ask(server.url, budget_ms=600)['status'] == 'timeout'
    assert time.monotonic() - began < 1.5
    assert ask(server.url, budget_ms=3000)['status'] == 'ok'


def test_non_positive_budget_never_touches_the_network(make_laya):
    server = make_laya()
    assert ask(server.url, budget_ms=0)['status'] == 'timeout' and server.paths == []


def test_probe_is_cached_for_a_minute_and_files_are_private(make_laya, tmp_path):
    cache = tmp_path / 'state' / 'laya-health.json'
    server = make_laya()
    assert ask(server.url, health_cache_path=cache)['status'] == 'ok'
    assert ask(server.url, health_cache_path=cache)['status'] == 'ok'
    assert server.health_hits == 1 and len(server.posts) == 2
    assert stat.S_IMODE(cache.stat().st_mode) == 0o600 and stat.S_IMODE(cache.parent.stat().st_mode) == 0o700
    entry = json.loads(cache.read_text())
    assert entry['endpoint'] == server.url and entry['model'] == 'typed-decisions' and entry['ok'] is True
    entry['checkedAtMs'] -= 61_000                             # expired
    cache.write_text(json.dumps(entry))
    assert ask(server.url, health_cache_path=cache)['status'] == 'ok' and server.health_hits == 2


def test_changing_endpoint_or_model_invalidates_the_probe_cache(make_laya, tmp_path):
    cache = tmp_path / 'laya-health.json'
    first, second = make_laya(), make_laya()
    assert ask(first.url, health_cache_path=cache)['status'] == 'ok'
    assert ask(second.url, health_cache_path=cache)['status'] == 'ok'
    assert (first.health_hits, second.health_hits) == (1, 1)
    # a cached pass for another model must not vouch for this one
    item = built()
    result = laya_choice.call_choice(item['request'], item['keyMap'], second.url, 'other-model', 2000,
                                     health_cache_path=cache)
    assert result['status'] == 'identity_failed' and second.health_hits == 2


def test_failed_probes_are_not_cached_and_cache_errors_are_ignored(make_laya, tmp_path):
    server = make_laya(loaded=['nope'])
    cache = tmp_path / 'laya-health.json'
    assert ask(server.url, health_cache_path=cache)['status'] == 'identity_failed' and not cache.exists()
    bad_dir = tmp_path / 'file-not-dir'
    bad_dir.write_text('x')
    good = make_laya()
    assert ask(good.url, health_cache_path=bad_dir / 'laya-health.json')['status'] == 'ok'   # write fails, call fine
    cache.write_text('{corrupt')
    assert ask(good.url, health_cache_path=cache)['status'] == 'ok'
    link = tmp_path / 'link.json'
    link.symlink_to(tmp_path / 'target.json')
    assert ask(good.url, health_cache_path=link)['status'] == 'ok' and not (tmp_path / 'target.json').exists()


def test_call_choice_never_raises():
    class Exploding:
        def open(self, *args, **kwargs):
            raise RuntimeError('boom')
    item = built()
    for request, key_map, endpoint in ((None, None, None), (item['request'], item['keyMap'], 5),
                                       ({'bad': float('nan')}, item['keyMap'], 'http://127.0.0.1:8000'),
                                       (item['request'], item['keyMap'], 'http://127.0.0.1:8000')):
        result = laya_choice.call_choice(request, key_map, endpoint, 'typed-decisions', 100, opener=Exploding())
        assert result['status'] in laya_choice.STATUSES and result['choice'] is None


# ---------------------------------------------------------------- transcript fixtures

def row(role, text, when, **extra):
    return {'type': role, 'timestamp': when, 'message': {'role': role, 'content': text}, **extra}


def user(text, when, **extra):
    return row('user', text, when, **extra)


def assistant(text, when):
    return row('assistant', text, when)


def skill_use(skill, when, **extra):
    return {'type': 'assistant', 'timestamp': when, **extra,
            'message': {'role': 'assistant', 'content': [{'type': 'tool_use', 'id': 'toolu_' + uuid.uuid4().hex[:8],
                                                          'name': 'Skill', 'input': {'skill': skill}}]}}


def slash(command, when):
    return user(f'<command-message>{command.lstrip("/")}</command-message>\n<command-name>/{command.lstrip("/")}'
                '</command-name>', when)


def tool_result(when):
    return {'type': 'user', 'timestamp': when, 'message': {'role': 'user', 'content': [
        {'type': 'tool_result', 'tool_use_id': 'toolu_x', 'content': 'output text'}]}}


def write_transcript(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(json.dumps(r) for r in rows) + '\n')
    return path


@pytest.fixture
def roots(tmp_path):
    return [tmp_path / 'transcripts']


def claude_file(tmp_path, session):
    return tmp_path / 'transcripts' / '-proj' / f'{session}.jsonl'


# ---------------------------------------------------------------- transcripts

def test_find_turn_by_prefix_returns_text_context_and_path(tmp_path, roots):
    path = write_transcript(claude_file(tmp_path, S1), [
        user('first context turn', '2026-10-05T11:00:00.000Z'), assistant('reply', '2026-10-05T11:00:05.000Z'),
        user(f'Audit our SEO {SENTINEL}', '2026-10-05T12:00:05.000Z')])
    prompt = f'Audit our SEO {SENTINEL}'
    match, reason = transcripts.find_turn(S1, sha(prompt)[:16], '2026-10-05T12:00:04.900Z', roots)
    assert reason is None and match['text'] == prompt and match['timestamp'] == '2026-10-05T12:00:05.000Z'
    assert match['path'] == str(path) and match['line'] == 3
    assert [t['text'] for t in match['prior']] == ['first context turn']      # assistant prose is never context
    assert transcripts.find_turn(S2, sha(prompt)[:16], None, roots) == (None, 'transcript_unavailable')
    assert transcripts.find_turn(S1, '0' * 16, None, roots) == (None, 'context_missing')
    assert transcripts.find_turn('', sha(prompt)[:16], None, roots) == (None, 'transcript_unavailable')
    assert transcripts.find_turn(S1, 'zz', None, roots) == (None, 'context_missing')


def test_repeated_identical_prompts_are_resolved_by_timestamp(tmp_path, roots):
    write_transcript(claude_file(tmp_path, S1), [
        user('context one', '2026-10-05T14:00:00.000Z'), user('ship it', '2026-10-05T14:00:10.000Z'),
        user('context two', '2026-10-05T14:10:00.000Z'), user('ship it', '2026-10-05T14:20:00.000Z')])
    prefix = sha('ship it')[:16]
    scanner = transcripts.TranscriptScanner(roots)
    first, _ = scanner.find_turn(S1, prefix, '2026-10-05T14:00:09.000Z')
    second, _ = scanner.find_turn(S1, prefix, '2026-10-05T14:20:01.000Z')
    assert first['line'] == 2 and [t['text'] for t in first['prior']] == ['context one']
    assert second['line'] == 4 and [t['text'] for t in second['prior']][-1] == 'context two'
    assert scanner.find_turn(S1, prefix, '2026-10-05T14:40:00.000Z') == (None, 'context_ambiguous')
    assert scanner.find_turn(S1, prefix, None) == (None, 'context_ambiguous')


def test_identical_prompt_with_identical_context_is_not_ambiguous(tmp_path, roots):
    write_transcript(claude_file(tmp_path, S1), [user('ship it', '2026-10-05T14:00:10.000Z'),
                                                 user('ship it', '2026-10-05T14:20:00.000Z')])
    match, reason = transcripts.find_turn(S1, sha('ship it')[:16], '2026-10-05T14:20:00.000Z', roots)
    assert reason is None and match['text'] == 'ship it'


def test_lookup_by_stored_hashes_matches_the_prefix_lookup(tmp_path, roots):
    write_transcript(claude_file(tmp_path, S1), [user('Audit our SEO', '2026-10-05T12:00:05.000Z')])
    scanner = transcripts.TranscriptScanner(roots)
    by_hash, reason = scanner.find_turn_by_hash(sha(S1), sha('Audit our SEO'), '2026-10-05T12:00:05.000Z')
    assert reason is None and by_hash['text'] == 'Audit our SEO'
    assert scanner.find_turn_by_hash(sha(S1), sha('other'), None) == (None, 'context_missing')
    assert scanner.find_turn_by_hash(sha(S2), sha('Audit our SEO'), None) == (None, 'transcript_unavailable')


def test_codex_layout_is_searchable_but_has_no_invocation_parser(tmp_path, roots):
    path = tmp_path / 'transcripts' / '2026' / '10' / f'rollout-2026-10-05T10-00-00-{S2}.jsonl'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'type': 'response_item', 'timestamp': '2026-10-05T10:00:01.000Z', 'payload': {
        'type': 'message', 'role': 'user', 'content': [{'type': 'input_text', 'text': 'codex prompt'}]}}) + '\n')
    match, reason = transcripts.find_turn(S2, sha('codex prompt')[:16], '2026-10-05T10:00:01.000Z', roots)
    assert reason is None and match['text'] == 'codex prompt'
    with pytest.raises(transcripts.TranscriptError) as caught:
        transcripts.skill_invocations(path, 0)
    assert caught.value.reason == 'transcript_unavailable'


def test_session_index_maps_hashes_to_paths_and_skips_symlinks_and_subagents(tmp_path, roots):
    real = write_transcript(claude_file(tmp_path, S1), [user('x', '2026-10-05T12:00:00.000Z')])
    write_transcript(tmp_path / 'transcripts' / '-proj' / 'subagents' / 'agent-a1b2c3d4e5f6.jsonl',
                     [user('y', '2026-10-05T12:00:00.000Z')])
    (tmp_path / 'transcripts' / '-proj' / f'{S3}.jsonl').symlink_to(real)
    (tmp_path / 'elsewhere').mkdir()
    (tmp_path / 'elsewhere' / f'{S2}.jsonl').write_text('{}\n')
    linked_root = tmp_path / 'linked-root'
    linked_root.symlink_to(tmp_path / 'elsewhere')
    index = transcripts.session_index([*roots, linked_root])
    assert index == {sha(S1): real}


def test_oversized_transcripts_and_lines_are_bounded(tmp_path, roots, monkeypatch):
    path = write_transcript(claude_file(tmp_path, S1), [user('Audit our SEO', '2026-10-05T12:00:05.000Z')])
    monkeypatch.setattr(transcripts, 'MAX_TRANSCRIPT_BYTES', 10)
    assert transcripts.find_turn(S1, sha('Audit our SEO')[:16], None, roots) == (None, 'transcript_unavailable')
    monkeypatch.setattr(transcripts, 'MAX_TRANSCRIPT_BYTES', 1 << 20)
    monkeypatch.setattr(transcripts, 'MAX_LINE_BYTES', 400)
    huge = user('x' * 5000, '2026-10-05T12:00:01.000Z')
    write_transcript(path, [huge, user('Audit our SEO', '2026-10-05T12:00:05.000Z')])
    match, reason = transcripts.find_turn(S1, sha('Audit our SEO')[:16], '2026-10-05T12:00:05.000Z', roots)
    assert reason is None and match['prior'] == []                  # the oversize line was skipped, not read
    assert transcripts.parse_transcript(path).sha256 == hashlib.sha256(path.read_bytes()).hexdigest()


def test_skill_invocations_report_tool_and_slash_forms(tmp_path):
    path = write_transcript(claude_file(tmp_path, S1), [
        skill_use('earlier:skill', '2026-10-05T11:00:00.000Z'),
        user('Audit our SEO', '2026-10-05T12:00:00.000Z'),
        skill_use('seo-aeo-geo:seo-site-audit', '2026-10-05T12:00:05.000Z'),
        tool_result('2026-10-05T12:00:06.000Z'),
        user('now ship it', '2026-10-05T12:01:00.000Z'),
        slash('rhize-devflow:ship', '2026-10-05T12:02:00.000Z'),
        slash('clear', '2026-10-05T12:03:00.000Z'),
        user('<system-reminder>injected</system-reminder>', '2026-10-05T12:03:30.000Z'),
        skill_use('late:one', '2026-10-05T12:04:00.000Z', isSidechain=True),
        skill_use('/obsidian-second-brain:defuddle', '2026-10-05T12:05:00.000Z')])
    found = transcripts.skill_invocations(path, '2026-10-05T12:00:00.000Z')
    assert [(i['skillRef'], i['via'], i['userTurnsAfter']) for i in found] == [
        ('seo-aeo-geo:seo-site-audit', 'skill_tool', 0),
        ('rhize-devflow:ship', 'slash_command', 2),
        ('obsidian-second-brain:defuddle', 'skill_tool', 3)]
    assert found[0]['ts'] == '2026-10-05T12:00:05.000Z'
    anchored = transcripts.skill_invocations(path, None, after_line=2)
    assert [i['skillRef'] for i in anchored] == [i['skillRef'] for i in found]
    assert anchored[0]['userTurnsAfter'] == 0 and anchored[1]['userTurnsAfter'] == 2
    assert [i['skillRef'] for i in transcripts.skill_invocations(path, '2026-10-05T12:00:00.000Z',
                                                                 max_user_turns=1)] == ['seo-aeo-geo:seo-site-audit']
    assert [i['skillRef'] for i in transcripts.skill_invocations(
        path, 0, until_ts='2026-10-05T11:30:00.000Z')] == ['earlier:skill']


# ---------------------------------------------------------------- router replay

SIGNALS = {
    SEO: [{'kind': 'tag', 'facet': 'topic', 'label': 'seo', 'weight': 2},
          {'kind': 'tag', 'facet': 'topic', 'label': 'audit', 'weight': 2},
          {'kind': 'tag-inferred', 'label': 'site health', 'weight': 0.5},
          {'kind': 'name', 'label': 'seo-site-audit', 'weight': 1}],
    GEO: [{'kind': 'tag', 'facet': 'topic', 'label': 'seo', 'weight': 2},
          {'kind': 'tag', 'facet': 'topic', 'label': 'geo', 'weight': 2},
          {'kind': 'name', 'label': 'aeo-geo-optimization', 'weight': 1}],
    SHIP: [{'kind': 'tag', 'facet': 'topic', 'label': 'ship', 'weight': 2},
           {'kind': 'tag', 'facet': 'topic', 'label': 'release', 'weight': 2},
           {'kind': 'name', 'label': 'ship', 'weight': 1}],
}
DESCRIPTIONS = {SEO: 'Audit a website for SEO health.   Uses\nDataForSEO.', GEO: 'Optimize for answer engines.'}


def write_index(path, wrapped=True, signals=None):
    router = {'signals': signals or SIGNALS, 'extendsBases': {}}
    path.write_text(json.dumps({'router': router, 'schemaVersion': 1} if wrapped else router))
    return router


def write_map(path):
    nodes = [{'kind': 'skill', 'id': sid, 'name': sid.rsplit('/', 1)[-1], 'description': text}
             for sid, text in DESCRIPTIONS.items()]
    nodes.append({'kind': 'skill', 'id': SHIP, 'name': 'ship'})                       # no description
    path.write_text(json.dumps({'nodes': nodes, 'edges': [], 'schemaVersion': 1}))


def replay_lines(index, map_path, prompts, *extra):
    lines = ''.join(json.dumps({'id': i, 'prompt': p}) + '\n' for i, p in enumerate(prompts))
    done = subprocess.run([NODE, str(SCRIPTS / 'typed_decisions' / 'route_replay.js'), str(index), str(map_path), *extra],
                          input=lines, capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    return [json.loads(line) for line in done.stdout.splitlines()]


@needs_node
def test_route_replay_reports_incumbent_shortlist_descriptions_and_hashes(tmp_path):
    index, map_path = tmp_path / 'index.json', tmp_path / 'map.json'
    router = write_index(index)
    write_map(map_path)
    out = replay_lines(index, map_path, ['Audit the SEO of our site', 'what about seo today', 'hello there friend',
                                         'use ship for this', 'get ready to ship this release'])
    audit, silent, nothing, explicit, shipping = out
    assert audit['incumbent'] == {'skillId': SEO, 'score': 5} and audit['explicit'] is False
    assert audit['shortlist'] == [SEO, GEO] and audit['descriptions'][SEO] == DESCRIPTIONS[SEO]
    assert silent['incumbent'] is None and silent['shortlist'] == [GEO, SEO]          # tie broken by id
    assert nothing['incumbent'] is None and nothing['shortlist'] == [] and nothing['descriptions'] == {}
    assert explicit['incumbent']['skillId'] == SHIP and explicit['explicit'] is True
    assert shipping['shortlist'] == [SHIP] and shipping['descriptions'] == {SHIP: None}
    expected_index = hashlib.sha256(json.dumps(router, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
    hooks = REPO / 'rhize-context-manager' / 'hooks'
    source = b''.join((hooks / name).read_bytes() for name in ('lib/route-core.js', 'skill-router.js',
                                                                'lib/laya-instrument.js'))
    for item in out:
        assert item['indexSha256'] == expected_index and item['routerSourceSha256'] == hashlib.sha256(source).hexdigest()
    assert [item['id'] for item in out] == [0, 1, 2, 3, 4]


@needs_node
def test_route_replay_accepts_wrapped_and_bare_indexes_and_hash_only_mode(tmp_path):
    wrapped, bare, map_path = tmp_path / 'wrapped.json', tmp_path / 'bare.json', tmp_path / 'map.json'
    write_index(wrapped, wrapped=True)
    write_index(bare, wrapped=False)
    write_map(map_path)
    hashes = [replay_lines(path, map_path, [], '--hashes')[0] for path in (wrapped, bare)]
    assert hashes[0] == hashes[1] and set(hashes[0]) == {'indexSha256', 'routerSourceSha256'}
    first = replay_lines(wrapped, map_path, ['Audit the SEO of our site'])[0]
    assert first['indexSha256'] == hashes[0]['indexSha256']


@needs_node
def test_route_replay_survives_bad_lines_and_rejects_bad_inputs(tmp_path):
    index, map_path = tmp_path / 'index.json', tmp_path / 'map.json'
    write_index(index)
    write_map(map_path)
    done = subprocess.run([NODE, str(SCRIPTS / 'typed_decisions' / 'route_replay.js'), str(index), str(map_path)],
                          input='garbage\n{"id":7}\n{"id":8,"prompt":""}\n\n{"id":9,"prompt":"Audit the SEO"}\n',
                          capture_output=True, text=True, timeout=60)
    out = [json.loads(line) for line in done.stdout.splitlines()]
    assert [o.get('error') for o in out] == ['invalid_request'] * 3 + [None] and out[1]['id'] == 7
    assert out[3]['id'] == 9
    for argv in ([str(index)], [str(index), str(tmp_path / 'missing.json')], [str(tmp_path / 'missing.json'), str(map_path)]):
        bad = subprocess.run([NODE, str(SCRIPTS / 'typed_decisions' / 'route_replay.js'), *argv],
                             input='', capture_output=True, text=True, timeout=60)
        assert bad.returncode == 2 and bad.stderr.startswith('route_replay:')


# ---------------------------------------------------------------- backfill world

P_A = f'Audit the SEO of our site {SENTINEL}'
P_B = 'get ready to ship this release PICKNONE'
P_EXPLICIT = 'use ship for this'
P_SILENT = f'what about seo today {SENTINEL}'
P_NONE = 'hello there friend'
P_GHOST = 'this prompt is in no transcript'
CUTOVER = '2026-10-11T00:00:00Z'


def log_row(session, prompt, when, suggested=None, hook='router'):
    return {'ts': when, 'session_id': session, 'hook': hook, 'suggested': suggested, 'context_hash': sha(prompt)[:16],
            'typed_status': None, 'typed_candidate_count': None}


class World:
    def __init__(self, tmp_path, extra=0):
        self.tmp = tmp_path
        self.root = tmp_path / 'root'
        self.index, self.map = tmp_path / 'index.json', tmp_path / 'map.json'
        self.log = tmp_path / 'suggestion-log.jsonl'
        self.transcripts = tmp_path / 'transcripts'
        self.router = write_index(self.index)
        write_map(self.map)
        write_transcript(claude_file(tmp_path, S1), [
            user('some earlier context', '2026-10-05T11:59:00.000Z'), user(P_A, '2026-10-05T12:00:05.000Z'),
            assistant('ok', '2026-10-05T12:00:20.000Z'), user(P_B, '2026-10-05T12:05:05.000Z'),
            user(P_EXPLICIT, '2026-10-05T12:06:05.000Z')])
        write_transcript(claude_file(tmp_path, S2), [
            user(P_SILENT, '2026-10-05T13:00:05.000Z'), user(P_NONE, '2026-10-05T13:01:05.000Z')])
        rows = [
            log_row(S1, P_A, '2026-10-05T12:00:04.900Z', SEO), log_row(S1, P_B, '2026-10-05T12:05:04.900Z', SHIP),
            log_row(S1, P_EXPLICIT, '2026-10-05T12:06:04.900Z', SHIP), log_row(S2, P_SILENT, '2026-10-05T13:00:04.900Z'),
            log_row(S2, P_NONE, '2026-10-05T13:01:04.900Z'), log_row(S2, P_GHOST, '2026-10-05T13:02:04.900Z'),
            log_row(None, P_A, '2026-10-05T13:03:04.900Z'), log_row(S1, P_A, '2026-09-20T12:00:04.900Z', SEO),
            log_row(S1, P_A, '2026-10-12T12:00:04.900Z', SEO), log_row(S1, P_A, '2026-10-05T12:00:06.000Z', SEO, hook='agent-brief'),
            log_row(S1, P_A, '2026-10-05T12:00:30.000Z', SEO)]
        lines = [json.dumps(r) for r in rows]
        if extra:
            variants = [f'Audit the SEO of the site variant {i}' for i in range(extra)]
            write_transcript(claude_file(tmp_path, S3), [user(v, f'2026-10-06T10:{i:02d}:05.000Z')
                                                         for i, v in enumerate(variants)])
            lines += [json.dumps(log_row(S3, v, f'2026-10-06T10:{i:02d}:04.900Z', SEO)) for i, v in enumerate(variants)]
        lines.insert(3, 'this line is not json')
        self.log.write_text('\n'.join(lines) + '\n')

    def run(self, server, **overrides):
        args = dict(root=self.root, since=backfill.parse_instant('2026-10-01', 'since'),
                    cutover=backfill.parse_instant(CUTOVER, 'cutover'), log=self.log, index=self.index,
                    map_path=self.map, transcripts_roots=[self.transcripts], endpoint=server if isinstance(server, str)
                    else server.url, budget_ms=3000, node=NODE)
        args.update(overrides)
        return backfill.run_backfill(**args)

    def stored(self):
        return records.read(self.root, 'skill-fit', 'records')[0]


@pytest.fixture
def world(tmp_path):
    return World(tmp_path)


def by_prompt(world, recs):
    keys = {sha(p): p for p in (P_A, P_B, P_SILENT, P_NONE)}
    return {keys[r['promptHash']]: r for r in recs}


@needs_node
def test_backfill_end_to_end_writes_valid_records_from_real_turns(world, make_laya, capsys):
    server = make_laya()
    summary, code = world.run(server)
    assert code == 0 and summary['status'] == 'completed' and summary['manifest'] == 'created'
    assert summary['logRows'] == 11 and summary['routerRows'] == 10 and summary['inWindow'] == 7 + 1
    assert summary['matched'] == 6 and summary['recordsWritten'] == 4
    assert summary['unmatched'] == {'context_missing': 1, 'no_session_id': 1} and summary['unmatchedTotal'] == 2
    assert summary['explicitRequestsSkipped'] == 1 and summary['alreadyRecorded'] == 1
    assert summary['layaStatuses'] == {'ok': 3, 'skipped': 1} and summary['layaCalls'] == 3
    recs = world.stored()
    assert len(recs) == 4
    for record in recs:
        contract.validate_record(record)
        assert (record['basis'], record['mode'], record['arm'], record['propensity'], record['emitted']) == (
            'backfill', 'shadow', 'none', None, None)
        assert (record['host'], record['policy'], record['registryRevision'], record['layaRevision']) == (
            'claude', 'cosign-v1', 0, 'unknown')
        assert record['instrumentSha256'] == instrument.instrument_sha256()
    got = by_prompt(world, recs)
    agree = got[P_A]
    assert agree['sourceStratum'] == 'fired' and agree['incumbent'] == {'skillId': SEO, 'score': 5}
    assert agree['shortlist'] == [SEO, GEO] and agree['laya']['choice'] == SEO and len(agree['laya']['probabilities']) == 3
    assert agree['sessionHash'] == sha(S1) and agree['promptHash'] == sha(P_A) and agree['promptLengthBucket'] == 'lt200'
    assert agree['ts'] == '2026-10-05T12:00:04.900Z'
    assert agree['occurrenceKey'] == contract.occurrence_key(sha(S1), sha(P_A), '2026-10-05T12:00:04.900Z')
    assert agree['laya']['truncated'] is False and agree['criteriaSha256'] == built_criteria(world, P_A)
    disagree = got[P_B]
    assert contract.is_disagreement(disagree) and disagree['laya']['choice'] == 'none'
    silent = got[P_SILENT]
    assert silent['sourceStratum'] == 'silent_sample' and silent['incumbent'] is None
    assert silent['shortlist'] == [GEO, SEO] and silent['laya']['choice'] == GEO
    skipped = got[P_NONE]
    assert skipped['laya']['status'] == 'skipped' and skipped['shortlist'] == [] and skipped['criteriaSha256'] is None
    # one replay frame for everything: the manifest hashes ride on every record
    manifest = json.loads((world.root / 'skill-fit' / 'backfill' / 'backfill-manifest.json').read_text())
    assert {r['indexSha256'] for r in recs} == {manifest['indexSha256']}
    assert {r['routerSourceSha256'] for r in recs} == {manifest['routerSourceSha256']}
    assert manifest['indexSha256'] == hashlib.sha256(
        json.dumps(world.router, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
    assert manifest['mapSha256'] == hashlib.sha256(world.map.read_bytes()).hexdigest()
    assert manifest['instrumentSha256'] == instrument.instrument_sha256()
    assert manifest['since'] == '2026-10-01T00:00:00.000Z' and manifest['cutover'] == '2026-10-11T00:00:00.000Z'
    # the criteria that reached Laya carried the collapsed, capped descriptions
    criteria = server.posts[0]['questions']['skill']['criteria']
    assert criteria['s0'] == 'seo-site-audit: Audit a website for SEO health. Uses DataForSEO.'
    assert server.health_hits == 1                                     # probe cached across the run


def built_criteria(world, prompt):
    item = instrument.build_choice_request(prompt, [{'skillId': SEO, 'description': DESCRIPTIONS[SEO]},
                                                    {'skillId': GEO, 'description': DESCRIPTIONS[GEO]}])
    return item['criteriaSha256']


@needs_node
def test_backfill_persists_no_prompt_text_and_keeps_files_private(world, make_laya, capsys):
    server = make_laya()
    summary, _ = world.run(server)
    blob = json.dumps(summary)
    assert SENTINEL not in blob and S1 not in blob and str(world.tmp) not in blob
    seen_files = 0
    for path in [world.root, *world.root.rglob('*')]:
        mode = stat.S_IMODE(path.stat().st_mode)
        if path.is_dir():
            assert mode == 0o700, path
        else:
            seen_files += 1
            assert mode == 0o600, path
            data = path.read_bytes()
            for needle in (SENTINEL.encode(), b'Audit the SEO', b'what about seo', b'ship this release', S1.encode()):
                assert needle not in data, path
    assert seen_files >= 5                                             # records, manifest, copies, lock, health cache
    code = backfill.main(['run', '--since', '2026-10-01', '--cutover', CUTOVER, '--root', str(world.root),
                          '--log', str(world.log), '--transcripts', str(world.transcripts),
                          '--endpoint', server.url])
    out = capsys.readouterr().out
    assert code == 0 and SENTINEL not in out and json.loads(out)['recordsWritten'] == 0


@needs_node
def test_backfill_resumes_without_repeating_work(world, make_laya):
    server = make_laya()
    world.run(server)
    posts_before = len(server.posts)
    again, code = world.run(server)
    assert code == 0 and again['manifest'] == 'reused' and again['recordsWritten'] == 0
    assert again['alreadyRecorded'] == 5 and len(server.posts) == posts_before
    assert len(world.stored()) == 4


@needs_node
def test_backfill_dedupes_by_occurrence_key_across_log_repeats(world, make_laya):
    summary, _ = world.run(make_laya())
    keys = [r['occurrenceKey'] for r in world.stored()]
    assert len(keys) == len(set(keys)) == 4 and summary['alreadyRecorded'] == 1   # the 12:00:30 repeat of row one


@needs_node
def test_backfill_only_reads_rows_before_the_cutover(world, make_laya):
    summary, _ = world.run(make_laya(), cutover=backfill.parse_instant('2026-10-05T12:30:00Z', 'cutover'))
    assert summary['recordsWritten'] == 2                              # P_A and P_B only; S2 rows are at or after 13:00
    assert {r['promptHash'] for r in world.stored()} == {sha(P_A), sha(P_B)}
    assert all(r['ts'] < '2026-10-05T12:30:00' for r in world.stored())


@needs_node
def test_backfill_budget_limits_laya_calls_and_leaves_the_rest_for_next_run(world, make_laya):
    server = make_laya()
    summary, code = world.run(server, budget=1)
    assert code == 0 and summary['layaCalls'] == 1 and len(server.posts) == 1
    assert summary['deferredBudget'] == 2 and summary['recordsWritten'] == 2    # the one call plus the Laya-free skip
    assert {r['promptHash'] for r in world.stored()} == {sha(P_A), sha(P_NONE)}
    more, _ = world.run(server)
    assert more['layaCalls'] == 2 and more['recordsWritten'] == 2 and len(world.stored()) == 4
    zero, _ = world.run(server, budget=0)
    assert zero['layaCalls'] == 0 and len(server.posts) == 3


@needs_node
def test_frozen_manifest_is_reused_even_when_the_live_index_changes(world, make_laya):
    server = make_laya()
    world.run(server, budget=0)
    frozen = world.root / 'skill-fit' / 'backfill'
    manifest_text = (frozen / 'backfill-manifest.json').read_text()
    original_index = (frozen / 'index.json').read_bytes()
    changed = {**SIGNALS, SHIP: SIGNALS[SHIP] + [{'kind': 'tag', 'facet': 'topic', 'label': 'audit', 'weight': 2}]}
    write_index(world.index, signals=changed)
    summary, code = world.run(server)
    assert code == 0 and summary['manifest'] == 'reused' and summary['recordsWritten'] == 3   # the skipped row was free
    assert (frozen / 'backfill-manifest.json').read_text() == manifest_text
    assert (frozen / 'index.json').read_bytes() == original_index
    assert {r['indexSha256'] for r in world.stored()} == {json.loads(manifest_text)['indexSha256']}


@needs_node
def test_resume_refuses_a_changed_instrument_hash_unless_a_new_manifest_is_requested(world, make_laya, monkeypatch):
    server = make_laya()
    world.run(server, budget=0)
    monkeypatch.setattr(instrument, 'QUESTION', 'Which skill, if any, is best for `request`?')
    with pytest.raises(backfill.BackfillError) as refused:
        world.run(server)
    assert refused.value.code == backfill.EXIT_MANIFEST and 'instrumentSha256 changed' in str(refused.value)
    assert '--new-manifest' in str(refused.value)
    summary, code = world.run(server, new_manifest=True)
    assert code == 0 and summary['manifest'] == 'created'
    frozen = world.root / 'skill-fit' / 'backfill'
    assert json.loads((frozen / 'backfill-manifest.json').read_text())['instrumentSha256'] == instrument.instrument_sha256()
    assert len(list(frozen.glob('backfill-manifest.*.json'))) == 1       # the previous frame was archived


@needs_node
def test_resume_refuses_changed_router_sources_laya_revision_window_and_tampering(world, make_laya, monkeypatch):
    server = make_laya()
    world.run(server, budget=0)
    real = backfill.node_hashes
    monkeypatch.setattr(backfill, 'node_hashes', lambda *a: {**real(*a), 'routerSourceSha256': 'f' * 64})
    with pytest.raises(backfill.BackfillError, match='routerSourceSha256 changed') as refused:
        world.run(server)
    assert refused.value.code == backfill.EXIT_MANIFEST
    monkeypatch.setattr(backfill, 'node_hashes', real)
    (world.root / 'laya-runtime.json').write_text(json.dumps({'revision': '55cf4c4ebb4e'}))
    with pytest.raises(backfill.BackfillError, match='Laya revision changed'):
        world.run(server)
    (world.root / 'laya-runtime.json').unlink()
    with pytest.raises(backfill.BackfillError, match='--since/--cutover differ'):
        world.run(server, cutover=backfill.parse_instant('2026-10-12', 'cutover'))
    frozen = world.root / 'skill-fit' / 'backfill'
    (frozen / 'index.json').write_text(json.dumps({'router': {'signals': {}}}))
    with pytest.raises(backfill.BackfillError, match='frozen index or map copy was modified'):
        world.run(server)
    assert len(world.stored()) == 1                    # only the budget-free skipped row from the first run


@needs_node
def test_backfill_uses_the_laya_runtime_revision_and_registry_state(world, make_laya):
    (world.root).mkdir(parents=True)
    (world.root / 'laya-runtime.json').write_text(json.dumps({'revision': '55cf4c4ebb4e'}))
    registry = json.loads((REPO / 'rhize-context-manager' / 'catalog' / 'decision-registry.json').read_text())
    state = {'schemaVersion': 1, 'revision': 7, 'updatedAt': '2026-10-04T00:00:00Z', 'decisions': {
        'skill-fit': {'mode': 'shadow', 'pinned': False, 'since': '2026-10-04T00:00:00Z', 'reason': 'default',
                      'policySha256': None, 'instrumentSha256': None, 'layaRevision': None, 'cohortId': None}}}
    contract.validate_state(state, registry)
    (world.root / 'registry-state.json').write_text(json.dumps(state))
    world.run(make_laya())
    assert {(r['layaRevision'], r['registryRevision']) for r in world.stored()} == {('55cf4c4ebb4e', 7)}
    (world.root / 'registry-state.json').write_text('{corrupt')
    assert backfill.read_registry_revision(world.root) == 0


@needs_node
def test_laya_failures_are_retried_later_not_recorded_and_five_in_a_row_abort(tmp_path):
    world = World(tmp_path, extra=6)
    summary, code = world.run(closed_port_url())
    assert code == backfill.EXIT_ABORTED and summary['status'] == 'aborted:laya_unavailable'
    assert summary['layaStatuses']['unavailable'] == 5 and summary['notRecordedRetryLater'] == 5
    assert all(r['laya']['status'] == 'skipped' for r in world.stored())      # nothing says "unavailable" forever


@needs_node
def test_failed_laya_rows_succeed_on_the_next_run(tmp_path, make_laya):
    world = World(tmp_path)
    broken = make_laya(loaded=['wrong'])
    first, code = world.run(broken)
    assert code == 0 and first['layaStatuses'] == {'identity_failed': 4, 'skipped': 1} and first['recordsWritten'] == 1
    assert broken.posts == []
    second, _ = world.run(make_laya())
    assert second['recordsWritten'] == 3 and len(world.stored()) == 4


@needs_node
def test_repeated_identical_prompts_become_separate_occurrences(tmp_path, make_laya):
    world = World(tmp_path)
    write_transcript(claude_file(tmp_path, S3), [
        user('context one', '2026-10-06T09:00:00.000Z'), user('Audit the SEO today', '2026-10-06T09:00:10.000Z'),
        user('context two', '2026-10-06T09:30:00.000Z'), user('Audit the SEO today', '2026-10-06T09:40:00.000Z')])
    rows = [log_row(S3, 'Audit the SEO today', '2026-10-06T09:00:09.900Z', SEO),
            log_row(S3, 'Audit the SEO today', '2026-10-06T09:39:59.900Z', SEO)]
    world.log.write_text('\n'.join(json.dumps(r) for r in rows) + '\n')
    summary, _ = world.run(make_laya())
    assert summary['recordsWritten'] == 2 and summary['matched'] == 2
    recs = world.stored()
    assert len({r['occurrenceKey'] for r in recs}) == 2 and {r['promptHash'] for r in recs} == {sha('Audit the SEO today')}


@needs_node
def test_unreadable_inputs_are_reported_without_a_traceback(world, make_laya, tmp_path):
    server = make_laya()
    with pytest.raises(backfill.BackfillError, match='cannot read the suggestion log'):
        world.run(server, log=tmp_path / 'missing.jsonl')
    with pytest.raises(backfill.BackfillError, match='literal loopback'):
        world.run('http://localhost:8000')
    with pytest.raises(backfill.BackfillError, match='earlier than'):
        world.run(server, since=backfill.parse_instant(CUTOVER, 'since'))
    with pytest.raises(backfill.BackfillError, match='missing or not JSON'):
        world.run(server, index=tmp_path / 'nope.json', root=tmp_path / 'fresh-root')
    for bad in ('yesterday', '2026-10-05T12:00:00'):
        with pytest.raises(backfill.BackfillError):
            backfill.parse_instant(bad, 'since')
    assert backfill.main(['run', '--since', '2026-10-01', '--cutover', CUTOVER, '--root', str(world.root),
                          '--endpoint', 'http://localhost:1']) == backfill.EXIT_USAGE


@needs_node
def test_a_busy_backfill_exits_quietly(world, make_laya):
    from typed_decisions import evidence_fs
    workdir = world.root / 'skill-fit' / 'backfill'
    with evidence_fs.exclusive_lock(workdir / 'run.lock') as held:
        assert held
        summary, code = world.run(make_laya())
    assert (summary, code) == ({'status': 'busy'}, 0) and world.stored() == []


# ---------------------------------------------------------------- outcomes

T0 = '2026-10-05T12:00:00.000Z'


def live_record(session, prompt, *, shortlist=(SEO, GEO), emitted=SEO, ts=T0, decision_id=None):
    record = copy.deepcopy(json.loads((FIX / 'records.json').read_text())['valid']['live-shadow-agree'])
    record.update(decisionId=decision_id or uuid.uuid4().hex, sessionHash=sha(session), promptHash=sha(prompt),
                  ts=ts, shortlist=list(shortlist), emitted=emitted)
    record['incumbent'] = {'skillId': shortlist[0], 'score': 5}
    record['laya'] = {'status': 'ok', 'choice': shortlist[0], 'latencyMs': 40, 'truncated': False,
                      'probabilities': [0.5] + [0.5 / len(shortlist)] * len(shortlist)}
    record['occurrenceKey'] = contract.occurrence_key(record['sessionHash'], record['promptHash'], ts)
    return contract.validate_record(record)


NOW = outcomes.datetime.fromisoformat('2026-10-05T14:00:00+00:00')


def run_join(tmp_path, root, **kwargs):
    return outcomes.join(root=root, transcripts_roots=[tmp_path / 'transcripts'], now=kwargs.pop('now', NOW), **kwargs)


def outcome_map(root):
    items, invalid = records.read(root, 'skill-fit', 'outcomes')
    assert invalid == 0
    return {o['decisionId']: o for o in items}


def sessions(n):
    return [f'aaaaaaaa-0000-4000-8000-{i:012d}' for i in range(n)]


def test_outcomes_classify_emitted_other_unlisted_none_and_unavailable(tmp_path):
    root = tmp_path / 'root'
    a, b, c, d, e, f, g, h = sessions(8)
    cases = {}

    def add(name, session, prompt, rows, **kwargs):
        if rows is not None:
            write_transcript(claude_file(tmp_path, session), rows)
        record = live_record(session, prompt, **kwargs)
        records.append(root, 'skill-fit', 'records', record)
        cases[name] = record['decisionId']

    add('emitted', a, 'p-emitted', [user('p-emitted', T0), skill_use('seo-aeo-geo:seo-site-audit', '2026-10-05T12:00:08.000Z')])
    add('other', b, 'p-other', [user('p-other', T0), assistant('hm', '2026-10-05T12:00:05.000Z'),
                                user('/ship', '2026-10-05T12:01:00.000Z'), slash('rhize-devflow:ship', '2026-10-05T12:01:01.000Z')],
        shortlist=(SEO, SHIP))
    add('unlisted', c, 'p-unlisted', [user('p-unlisted', T0), skill_use('obsidian-second-brain:defuddle', '2026-10-05T12:00:30.000Z')])
    add('none', d, 'p-none', [user('p-none', T0), assistant('done', '2026-10-05T12:00:30.000Z')])
    add('missing-transcript', e, 'p-missing', None)
    add('late', f, 'p-late', [user('p-late', T0), skill_use('seo-aeo-geo:seo-site-audit', '2026-10-05T12:31:00.000Z')])
    add('turns', g, 'p-turns', [user('p-turns', T0), user('t1', '2026-10-05T12:01:00.000Z'), user('t2', '2026-10-05T12:02:00.000Z'),
                                user('t3', '2026-10-05T12:03:00.000Z'), user('t4', '2026-10-05T12:04:00.000Z'),
                                skill_use('seo-aeo-geo:seo-site-audit', '2026-10-05T12:05:00.000Z')])
    add('before-and-builtin', h, 'p-builtin', [skill_use('seo-aeo-geo:seo-site-audit', '2026-10-05T11:59:00.000Z'),
                                               user('p-builtin', T0), slash('clear', '2026-10-05T12:00:30.000Z')])
    summary, code = run_join(tmp_path, root)
    assert code == 0 and summary['written'] == 8 and summary['pendingWindow'] == 0
    got = outcome_map(root)
    for name, expected in (('emitted', 'invoked_emitted'), ('other', 'invoked_other_shortlisted'),
                           ('unlisted', 'invoked_unlisted'), ('none', 'none_invoked'),
                           ('missing-transcript', 'transcript_unavailable'), ('late', 'none_invoked'),
                           ('turns', 'none_invoked'), ('before-and-builtin', 'none_invoked')):
        assert got[cases[name]]['outcome'] == expected, name
    emitted = got[cases['emitted']]
    assert (emitted['skillInvoked'], emitted['via'], emitted['latencyTurns']) == ('seo-aeo-geo:seo-site-audit', 'skill_tool', 0)
    other = got[cases['other']]
    assert (other['skillInvoked'], other['via'], other['latencyTurns']) == ('rhize-devflow:ship', 'slash_command', 2)
    unlisted = got[cases['unlisted']]
    assert unlisted['skillInvoked'] == 'obsidian-second-brain:defuddle' and unlisted['latencyTurns'] == 0
    assert emitted['transcriptSha256'] == hashlib.sha256(claude_file(tmp_path, a).read_bytes()).hexdigest()
    assert got[cases['missing-transcript']]['transcriptSha256'] is None
    assert got[cases['none']]['skillInvoked'] is None and got[cases['none']]['via'] is None


def test_outcomes_normalize_bare_names_and_prefer_the_emitted_skill(tmp_path):
    root = tmp_path / 'root'
    a, b = sessions(2)
    write_transcript(claude_file(tmp_path, a), [user('pa', T0), skill_use('ship', '2026-10-05T12:00:05.000Z'),
                                                skill_use('seo-aeo-geo:seo-site-audit', '2026-10-05T12:00:09.000Z')])
    write_transcript(claude_file(tmp_path, b), [user('pb', T0), slash('/Rhize-Devflow:Ship', '2026-10-05T12:00:05.000Z')])
    one = live_record(a, 'pa', shortlist=(SEO, SHIP), emitted=SEO)
    two = live_record(b, 'pb', shortlist=(SEO, SHIP), emitted=None)       # a backfill-like record never "emitted"
    for record in (one, two):
        records.append(root, 'skill-fit', 'records', record)
    run_join(tmp_path, root)
    got = outcome_map(root)
    assert got[one['decisionId']]['outcome'] == 'invoked_emitted' and got[one['decisionId']]['latencyTurns'] == 0
    assert got[two['decisionId']]['outcome'] == 'invoked_other_shortlisted'
    assert got[two['decisionId']]['skillInvoked'] == 'rhize-devflow:ship' and got[two['decisionId']]['via'] == 'slash_command'


def test_outcomes_wait_for_open_windows_and_are_idempotent(tmp_path):
    root = tmp_path / 'root'
    a, b = sessions(2)
    write_transcript(claude_file(tmp_path, a), [user('pa', T0)])
    write_transcript(claude_file(tmp_path, b), [user('pb', '2026-10-05T13:50:00.000Z')])
    old = live_record(a, 'pa')
    fresh = live_record(b, 'pb', ts='2026-10-05T13:50:00.000Z')
    for record in (old, fresh):
        records.append(root, 'skill-fit', 'records', record)
    first, _ = run_join(tmp_path, root)
    assert first['written'] == 1 and first['pendingWindow'] == 1 and list(outcome_map(root)) == [old['decisionId']]
    before = sorted(p.read_bytes() for p in (root / 'skill-fit' / 'outcomes').glob('*.jsonl'))
    again, _ = run_join(tmp_path, root)
    assert again['written'] == 0 and again['alreadyJoined'] == 1 and again['pendingWindow'] == 1
    assert sorted(p.read_bytes() for p in (root / 'skill-fit' / 'outcomes').glob('*.jsonl')) == before
    later, _ = run_join(tmp_path, root, now=outcomes.datetime.fromisoformat('2026-10-05T15:00:00+00:00'))
    assert later['written'] == 1 and len(outcome_map(root)) == 2
    final, _ = run_join(tmp_path, root, now=outcomes.datetime.fromisoformat('2026-10-06T15:00:00+00:00'))
    assert final['written'] == 0


def test_outcomes_window_and_turn_limits_are_parameters(tmp_path):
    root = tmp_path / 'root'
    (a,) = sessions(1)
    write_transcript(claude_file(tmp_path, a), [user('pa', T0), user('t1', '2026-10-05T12:01:00.000Z'),
                                                skill_use('seo-aeo-geo:seo-site-audit', '2026-10-05T12:20:00.000Z')])
    record = live_record(a, 'pa')
    records.append(root, 'skill-fit', 'records', record)
    run_join(tmp_path, root, window_minutes=10)
    assert outcome_map(root)[record['decisionId']]['outcome'] == 'none_invoked'
    other_root = tmp_path / 'root2'
    records.append(other_root, 'skill-fit', 'records', record)
    run_join(tmp_path, other_root, window_minutes=30, turns=1)
    assert outcome_map(other_root)[record['decisionId']]['outcome'] == 'invoked_emitted'
    third = tmp_path / 'root3'
    records.append(third, 'skill-fit', 'records', record)
    run_join(tmp_path, third, window_minutes=30, turns=0)
    assert outcome_map(third)[record['decisionId']]['outcome'] == 'none_invoked'


def test_outcomes_refuse_to_write_when_no_transcripts_exist_under_the_roots(tmp_path, capsys):
    root = tmp_path / 'root'
    records.append(root, 'skill-fit', 'records', live_record(sessions(1)[0], 'pa'))
    with pytest.raises(outcomes.OutcomesError, match='no transcripts found'):
        outcomes.join(root=root, transcripts_roots=[tmp_path / 'empty'], now=NOW)
    assert not (root / 'skill-fit' / 'outcomes').exists()
    code = outcomes.main(['join', '--root', str(root), '--transcripts', str(tmp_path / 'empty')])
    assert code == outcomes.EXIT_USAGE and 'refused' in capsys.readouterr().out


def test_outcomes_cli_prints_counts_only(tmp_path, capsys):
    root = tmp_path / 'root'
    (a,) = sessions(1)
    write_transcript(claude_file(tmp_path, a), [user(f'pa {SENTINEL}', T0)])
    records.append(root, 'skill-fit', 'records', live_record(a, f'pa {SENTINEL}'))
    code = outcomes.main(['join', '--root', str(root), '--transcripts', str(tmp_path / 'transcripts')])
    out = capsys.readouterr().out
    assert code == 0 and json.loads(out)['written'] == 1 and SENTINEL not in out
    for path in (root / 'skill-fit' / 'outcomes').glob('*.jsonl'):
        assert SENTINEL not in path.read_text() and stat.S_IMODE(path.stat().st_mode) == 0o600


def test_skill_ref_mirrors_the_router_display_form():
    assert outcomes.skill_ref('skill:rhize-devflow/ship') == 'rhize-devflow:ship'
    assert outcomes.skill_ref('skill:market/plugin/name') == 'plugin:name'
    assert outcomes.skill_ref('skill:flat') is None and outcomes.skill_ref('nope') is None


def test_backfill_recognizes_background_observer_transcripts():
    from typed_decisions import backfill as bf
    home = '/Users/someone'
    assert bf.is_background_observer_transcript(
        '/Users/someone/.claude/projects/-Users-someone--local-share-ecc-homunculus/s.jsonl', home=home)
    assert bf.is_background_observer_transcript(
        '/Users/someone/.claude/projects/-Users-someone--local-share-ecc-homunculus-projects-0123456789ab/s.jsonl', home=home)
    assert not bf.is_background_observer_transcript(
        '/Users/someone/.claude/projects/-Users-someone--local-share-ecc-homunculus-projects-notes/s.jsonl', home=home)
    assert not bf.is_background_observer_transcript(
        '/Users/someone/.claude/projects/-Users-someone-dev-local-app/s.jsonl', home=home)


@needs_node
def test_the_run_log_is_written_even_when_a_backfill_run_crashes(world, make_laya, monkeypatch):
    """Every answered call is already a record, so its run-log count must survive a crash (Fable final review)."""
    real = backfill.Replayer.replay
    calls = {'n': 0}

    def crash_on_third(self, text):
        calls['n'] += 1
        if calls['n'] == 3:
            raise RuntimeError('simulated crash')
        return real(self, text)

    monkeypatch.setattr(backfill.Replayer, 'replay', crash_on_third)
    with pytest.raises(RuntimeError):
        world.run(make_laya())
    lines = (world.root / 'skill-fit' / 'backfill' / 'runs.jsonl').read_text().splitlines()
    assert len(lines) == 1
    run = json.loads(lines[0])
    stored_ok = [r for r in world.stored() if r['laya']['status'] == 'ok']
    assert stored_ok and run['layaStatuses'].get('ok', 0) == len(stored_ok)
    # every record carries its run's id, so the gate can reconcile coverage per run (cohorts.backfill_coverage)
    assert len(run['runId']) == 16 and {r['decisionId'][:16] for r in world.stored()} == {run['runId']}
