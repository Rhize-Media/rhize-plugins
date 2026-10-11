"""Python Laya client for the laya-choice-v1 instrument (mirror of the Node client, plan §4.2).

    call_choice(request, key_map, endpoint, model, budget_ms, health_cache_path=None, opener=None)
        -> {'status', 'choice', 'probabilities', 'latencyMs'}

Semantics (shared with hooks/lib/laya-client.js):
- literal loopback endpoints only: http://127.0.0.1:<port> or http://[::1]:<port>. A hostname such as
  'localhost' is refused with no I/O (status 'unavailable');
- redirects are never followed (a 3xx is 'redirect_refused'); the default opener also ignores proxy
  environment variables so loopback traffic can never leave the machine;
- one monotonic deadline (budget_ms) covers GET /health and POST /v1/systemone together; every socket
  timeout is derived from the time that remains, and an expired deadline is 'timeout';
- the identity probe must show `model` in the /health `loaded` list, otherwise 'identity_failed';
  a passed probe is cached for 60 s in a 0600 file keyed by endpoint and model (I/O errors are ignored);
- response bodies are read in bounded chunks and capped at 64 KiB (more is 'invalid');
- the body is decoded with instrument.decode_choice_response (anything else is 'invalid');
- connection errors and non-2xx statuses are 'unavailable'; the function never raises.

The request carries the prompt head. It is sent only to the loopback server and never stored here.
"""
from __future__ import annotations

import http.client
import json
import re
import socket
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from typed_decisions import evidence_fs, instrument  # noqa: E402

STATUSES = ('ok', 'timeout', 'unavailable', 'invalid', 'identity_failed', 'redirect_refused')
MAX_RESPONSE_BYTES = 64 * 1024
PROBE_TTL_SECONDS = 60
CHUNK_BYTES = 8192
_LOOPBACK = re.compile(r'http://(?:127\.0\.0\.1|\[::1\]):([0-9]{1,5})\Z')


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401 - urllib hook
        return None


def default_opener():
    """urllib opener with no redirect handling and no proxy support."""
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())


class _Stop(Exception):
    def __init__(self, status):
        super().__init__(status)
        self.status = status


def is_loopback_endpoint(endpoint) -> bool:
    match = _LOOPBACK.match(endpoint) if isinstance(endpoint, str) else None
    return bool(match) and 1 <= int(match.group(1)) <= 65535


def _remaining(deadline) -> float:
    left = deadline - time.monotonic()
    if left <= 0:
        raise _Stop('timeout')
    return left


def _classify(exc) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        exc.close()
        return 'redirect_refused' if 300 <= exc.code < 400 else 'unavailable'
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return 'timeout'
    if isinstance(exc, urllib.error.URLError):
        return 'timeout' if isinstance(exc.reason, (socket.timeout, TimeoutError)) else 'unavailable'
    return 'unavailable'


def _shrink_timeout(response, seconds) -> None:
    try:
        response.fp.raw._sock.settimeout(max(seconds, 0.001))
    except Exception:  # noqa: BLE001 - best effort; a custom opener may expose no socket
        pass


def _read_body(response, deadline) -> bytes:
    length = getattr(response, 'headers', None) and response.headers.get('Content-Length')
    if length and str(length).isdigit() and int(length) > MAX_RESPONSE_BYTES:
        raise _Stop('invalid')
    chunks, total = [], 0
    while True:
        _shrink_timeout(response, _remaining(deadline))
        chunk = response.read(min(CHUNK_BYTES, MAX_RESPONSE_BYTES + 1 - total))
        if not chunk:
            return b''.join(chunks)
        total += len(chunk)
        if total > MAX_RESPONSE_BYTES:
            raise _Stop('invalid')
        chunks.append(chunk)


def _fetch(opener, request, deadline) -> bytes:
    """One bounded HTTP exchange; raises _Stop with the client status on any failure."""
    try:
        with opener.open(request, timeout=_remaining(deadline)) as response:
            code = getattr(response, 'status', None) or response.getcode()
            final = response.geturl() if hasattr(response, 'geturl') else request.full_url
            if final != request.full_url:
                raise _Stop('redirect_refused')
            if not 200 <= code < 300:
                raise _Stop('redirect_refused' if 300 <= code < 400 else 'unavailable')
            return _read_body(response, deadline)
    except _Stop:
        raise
    except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError) as exc:
        raise _Stop(_classify(exc)) from None


def _model_loaded(document, model) -> bool:
    """The real server answers {"loaded": ["typed-decisions", ...]}; accept exactly that shape (the Node client's rule)."""
    loaded = document.get('loaded') if isinstance(document, dict) else None
    return isinstance(loaded, list) and model in [item for item in loaded if isinstance(item, str)]


def _cache_fresh(path, endpoint, model) -> bool:
    if path is None:
        return False
    try:
        entry = json.loads(evidence_fs.read_regular(path, 4096))
        age = time.time() - entry['checkedAtMs'] / 1000.0
        return (entry['endpoint'] == endpoint and entry['model'] == model and entry['ok'] is True
                and 0 <= age < PROBE_TTL_SECONDS)
    except Exception:  # noqa: BLE001 - a missing, corrupt or foreign cache is simply a miss
        return False


def _cache_store(path, endpoint, model) -> None:
    if path is None:
        return
    try:
        entry = {'endpoint': endpoint, 'model': model, 'ok': True, 'checkedAtMs': int(time.time() * 1000)}
        evidence_fs.write_private_atomic(path, json.dumps(entry, sort_keys=True).encode('utf-8'))
    except Exception:  # noqa: BLE001 - cache write failures never change the call outcome
        pass


def _probe(opener, endpoint, model, deadline, cache_path) -> None:
    if _cache_fresh(cache_path, endpoint, model):
        return
    request = urllib.request.Request(endpoint + '/health', headers={'Accept': 'application/json'}, method='GET')
    body = _fetch(opener, request, deadline)
    try:
        document = json.loads(body.decode('utf-8'))
    except (UnicodeDecodeError, ValueError):
        raise _Stop('identity_failed') from None
    if not _model_loaded(document, model):
        raise _Stop('identity_failed')
    _cache_store(cache_path, endpoint, model)


def call_choice(request, key_map, endpoint, model, budget_ms, health_cache_path=None, opener=None) -> dict:
    """Ask the loopback Laya server one laya-choice-v1 question. Never raises."""
    started = time.monotonic()

    def result(status, choice=None, probabilities=None):
        return {'status': status, 'choice': choice, 'probabilities': probabilities,
                'latencyMs': round((time.monotonic() - started) * 1000.0, 1)}

    try:
        if not is_loopback_endpoint(endpoint):
            return result('unavailable')                      # refused before any I/O
        if isinstance(budget_ms, bool) or not isinstance(budget_ms, (int, float)) or budget_ms <= 0:
            return result('timeout')
        deadline = started + budget_ms / 1000.0
        if not isinstance(request, dict) or not isinstance(key_map, dict) or not isinstance(model, str):
            return result('invalid')
        try:
            payload = json.dumps(request, separators=(',', ':')).encode('utf-8')
        except (TypeError, ValueError):
            return result('invalid')
        opener = opener if opener is not None else default_opener()
        _probe(opener, endpoint, model, deadline, health_cache_path)
        post = urllib.request.Request(
            endpoint + '/v1/systemone', data=payload, method='POST',
            headers={'Content-Type': 'application/json', 'Accept': 'application/json'})
        body = _fetch(opener, post, deadline)
        try:
            decoded = instrument.decode_choice_response(json.loads(body.decode('utf-8')), key_map)
        except (UnicodeDecodeError, ValueError):
            return result('invalid')
        return result('ok', decoded['choice'], decoded['probabilities'])
    except _Stop as stop:
        return result(stop.status)
    except Exception:  # noqa: BLE001 - the contract is "never raises"
        return result('unavailable')


def _main(argv=None) -> int:  # pragma: no cover - tiny manual probe
    import argparse
    parser = argparse.ArgumentParser(description='Probe the loopback Laya server identity (no prompt is sent).')
    parser.add_argument('--endpoint', default='http://127.0.0.1:8000')
    parser.add_argument('--model', default=instrument.MODEL)
    parser.add_argument('--budget-ms', type=int, default=800)
    args = parser.parse_args(argv)
    deadline = time.monotonic() + args.budget_ms / 1000.0
    if not is_loopback_endpoint(args.endpoint):
        print(json.dumps({'status': 'unavailable'}))
        return 1
    try:
        _probe(default_opener(), args.endpoint, args.model, deadline, None)
        print(json.dumps({'status': 'ok'}))
        return 0
    except _Stop as stop:
        print(json.dumps({'status': stop.status}))
        return 1


if __name__ == '__main__':  # pragma: no cover
    raise SystemExit(_main())
