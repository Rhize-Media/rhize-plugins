"""Shared Laya advice client for advise-v1 decisions (stdlib only, Python 3.9).

Copied byte-identical into rhize-context-manager, rhize-devflow, rhize-ops and project-launcher
`scripts/` (plugins are islands; tests/config-lint/test_shared_shims.py checks drift). Spec:
docs/superpowers/specs/2026-10-16-laya-advise-everywhere-plan.md.

- Transport: literal loopback IPs only, no redirects, no proxies, a /health identity probe before any
  request text is sent, bounded responses, one monotonic deadline. Same rules as typed_decisions/laya_choice.py.
- Mode: read-only view of registry-state.json (written only by Context Manager's decision_registry.py).
  Missing, corrupt, unbound or stale state reads as 'shadow'; advice is shown only in an earned 'advise'.
- Records: write-once JSON files, directories 0700, files 0600, symlinks refused. A record holds hashes,
  candidate ids and Laya's answer. The scrubbed request snapshot is a separate file used for blinded labels.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

MODEL = 'typed-decisions'
ENDPOINT = 'http://127.0.0.1:8000'
INSTRUMENT = 'typed-advice-v1'
RECORD_SCHEMA = 'rhize-typed-choice-record-v1'
OUTCOME_SCHEMA = 'rhize-typed-choice-outcome-v1'
SCRUB_VERSION = 'scrub-v1'
MODES = ('off', 'shadow', 'advise', 'cosign')
REQUEST_CHARS = 1500
MAX_FILES = 20
MAX_CANDIDATES = 16
MAX_RESPONSE_BYTES = 64 * 1024
CHUNK_BYTES = 8192
PROBE_TTL_SECONDS = 60
HOLDBACK = {'advisory': 0.10, 'workflow': 0.10, 'critical': 0.15}

_BASE = re.compile(r'http://(127\.0\.0\.1|\[::1\]):([0-9]{1,5})/?')
_PATH = re.compile(r'/[A-Za-z0-9._~/-]*')
_DECISION = re.compile(r'[a-z][a-z0-9-]{1,40}')
_CANDIDATE = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}')
_DECISION_ID = re.compile(r'[0-9a-f]{32}')
_REVISION = re.compile(r'[A-Za-z0-9._-]{1,80}')
_SECRET_ASSIGN = re.compile(
    r'(?i)\b([A-Za-z0-9_]*(?:pass(?:word|wd)?|secret|token|api[_-]?key|auth[A-Za-z_]*|bearer|credential|private[_-]?key)'
    r'[A-Za-z0-9_]*)(?:["\']?\s*[:=]\s*|\s+)(?:(?:bearer|basic)\s+)?'
    r'("[^"]*"|\'[^\']*\'|["\']?[^\s"\']+)')
_SECRET_RUN = re.compile(r'[A-Za-z0-9+/_=-]{32,}')
_SECRET_FILE = re.compile(r'(?i)(^|/)(\.env[^/]*|.*\.(pem|key|p12|pfx|keystore)|id_[a-z0-9]+|.*credential[^/]*|.*secret[^/]*)$')
_WS = re.compile(r'\s+')

# shortcut: decision-to-tier map duplicated from catalog/decision-registry.json so islands need no catalog;
# a test asserts they agree.
TIERS = {
    'skill-fit': 'advisory', 'workflow-fit': 'workflow', 'procedure-pick': 'advisory',
    'devflow-next-action': 'critical', 'browser-qa-selection': 'advisory', 'model-routing': 'advisory',
    'gsd-directive': 'critical', 'check-relaxation': 'critical',
}


def root() -> Path:
    override = os.environ.get('RHIZE_TYPED_DECISIONS_ROOT')
    return Path(override) if override else Path.home() / '.local' / 'share' / 'rhize' / 'typed-decisions'


def sha256(value) -> str:
    text = value if isinstance(value, str) else json.dumps(value, sort_keys=True, separators=(',', ':'),
                                                          ensure_ascii=False)
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


INSTRUMENT_SHA256 = sha256({'instrument': INSTRUMENT, 'model': MODEL, 'requestChars': REQUEST_CHARS,
                            'maxFiles': MAX_FILES, 'scrub': SCRUB_VERSION})


# ------------------------------------------------------------------ input hygiene

def scrub(text) -> str:
    """Collapse whitespace, mask credential-shaped assignments and long opaque runs, cap at REQUEST_CHARS."""
    if not isinstance(text, str):
        return ''
    text = _WS.sub(' ', text).strip()[:REQUEST_CHARS * 2]
    text = _SECRET_ASSIGN.sub(lambda m: m.group(1) + '=<redacted>', text)
    text = _SECRET_RUN.sub('<redacted>', text)
    return text[:REQUEST_CHARS]


def clean_files(paths) -> list:
    """Up to MAX_FILES repo-relative hints; absolute, parent-relative and secret-shaped names are dropped."""
    kept = []
    for item in paths or ():
        if not isinstance(item, str):
            continue
        path = item.strip().replace('\\', '/')
        if (not path or len(path) > 200 or path.startswith(('/', '~')) or re.match(r'[A-Za-z]:', path)
                or '..' in path.split('/') or _SECRET_FILE.search(path) or any(ord(c) < 32 for c in path)):
            continue
        if path not in kept:
            kept.append(path)
        if len(kept) == MAX_FILES:
            break
    return kept


# ------------------------------------------------------------------ transport

class _RefuseRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('redirect_refused')


def _opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), _RefuseRedirect)


def _destination(base_url, path) -> str:
    match = _BASE.fullmatch(base_url) if isinstance(base_url, str) else None
    if not match or not 1 <= int(match.group(2)) <= 65535:
        raise ValueError('loopback_ip_url_required')
    if not isinstance(path, str) or not _PATH.fullmatch(path):
        raise ValueError('invalid_path')
    return f'http://{match.group(1)}:{match.group(2)}{path}'


def _remaining(deadline) -> float:
    left = deadline - time.monotonic()
    if left <= 0:
        raise ValueError('timeout')
    return left


def _read_bounded(response, deadline, max_bytes) -> bytes:
    """Read at most max_bytes, re-arming the socket timeout from the shared deadline before every chunk."""
    length = getattr(response, 'headers', None) and response.headers.get('Content-Length')
    if length and str(length).isdigit() and int(length) > max_bytes:
        raise ValueError('response_too_large')
    chunks, total = [], 0
    while True:
        try:
            response.fp.raw._sock.settimeout(max(_remaining(deadline), 0.001))
        except AttributeError:  # a custom response may expose no socket; the per-open timeout still applies
            _remaining(deadline)
        # read1 returns whatever one socket read yields, so a slow trickle re-checks the deadline between
        # chunks; read(n) would block until n bytes arrive and ignore it.
        chunk = getattr(response, 'read1', response.read)(min(CHUNK_BYTES, max_bytes + 1 - total))
        if not chunk:
            return b''.join(chunks)
        total += len(chunk)
        if total > max_bytes:
            raise ValueError('response_too_large')
        chunks.append(chunk)


def _get_json(opener, request, deadline, max_bytes):
    try:
        with opener.open(request, timeout=_remaining(deadline)) as response:
            raw = _read_bounded(response, deadline, max_bytes)
    except urllib.error.HTTPError as exc:
        exc.close()
        if 300 <= exc.code < 400:  # e.g. a 307/308 on POST, which urllib does not route through redirect_request
            raise ValueError('redirect_refused') from None
        raise
    _remaining(deadline)
    try:
        value = json.loads(raw)
    except ValueError:
        raise ValueError('response_not_json') from None
    if not isinstance(value, dict):
        raise ValueError('response_not_object')
    return value


def _probe_fresh(cache, url, model) -> bool:
    try:
        entry = json.loads(_read_regular(cache, 4096))
        age = time.time() - entry['checkedAt']
        return entry['url'] == url and entry['model'] == model and 0 <= age < PROBE_TTL_SECONDS
    except Exception:  # noqa: BLE001 - a missing or foreign cache is a miss
        return False


def _probe(opener, health, model, deadline):
    try:
        document = _get_json(opener, urllib.request.Request(health, method='GET'), deadline, 16384)
    except ValueError as exc:
        if str(exc) in ('response_not_json', 'response_not_object'):
            raise ValueError('identity_failed') from None  # not a Laya /health document
        raise
    loaded = document.get('loaded')
    if not isinstance(loaded, list) or model not in loaded:
        raise ValueError('identity_failed')


def check_identity(base_url, model=MODEL, timeout=2.0):
    """Uncached /health identity probe on the same loopback rules as post_local; no request text is sent.
    Raises ValueError (post_local's short codes) or an OSError when Laya is not the expected model server."""
    _probe(_opener(), _destination(base_url, '/health'), model, time.monotonic() + timeout)


def post_local(base_url, path, payload, timeout, max_bytes=MAX_RESPONSE_BYTES, health_cache=None):
    """POST JSON to a literal loopback IP after a /health identity probe; return (response dict, latency ms).

    The destination is validated before the payload is built. The probe must list payload['model'] in
    `loaded`; probe and POST share one deadline of `timeout` seconds. Proxies are ignored, redirects
    refused, responses bounded. Raises ValueError with a short code; payload text never enters an error.
    """
    url = _destination(base_url, path)
    health = _destination(base_url, '/health')
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('invalid_timeout')
    started = time.monotonic()
    deadline = started + timeout
    body = payload() if callable(payload) else payload
    if not isinstance(body, dict) or not isinstance(body.get('model'), str):
        raise ValueError('invalid_payload')
    model = body['model']
    opener = _opener()
    if not (health_cache and _probe_fresh(health_cache, health, model)):
        _probe(opener, health, model, deadline)
        if health_cache:
            try:
                _write_atomic(Path(health_cache), {'url': health, 'model': model, 'checkedAt': time.time()})
            except (OSError, ValueError):
                pass
    request = urllib.request.Request(url, data=json.dumps(body).encode(), method='POST',
                                     headers={'Content-Type': 'application/json'})
    value = _get_json(opener, request, deadline, max_bytes)
    return value, round((time.monotonic() - started) * 1000, 3)


def build_request(request, files, question, candidates) -> tuple:
    """Laya /v1/systemone payload for one choice question; returns (payload, key->candidate id map)."""
    key_map = {f'c{i}': item['id'] for i, item in enumerate(candidates)}
    criteria = {f'c{i}': item['criterion'] for i, item in enumerate(candidates)}
    state = {'request': scrub(request), 'files': clean_files(files)}
    return ({'model': MODEL, 'state': state,
             'questions': {'pick': {'type': 'choice', 'instructions': question, 'criteria': criteria}}}, key_map)


def decode(response, key_map) -> dict:
    """{'choice': candidate id, 'probabilities': {id: p}}; ValueError('invalid_response') otherwise."""
    try:
        if response['routing']['model'] != MODEL:
            raise ValueError
        answers = response['answers']
        if set(answers) != {'pick'} or answers['pick']['type'] != 'choice':
            raise ValueError
        answer = answers['pick']
        if answer['choice'] not in key_map or set(answer['probabilities']) != set(key_map):
            raise ValueError
        probabilities = {}
        for key, p in answer['probabilities'].items():
            if isinstance(p, bool) or not isinstance(p, (int, float)) or not math.isfinite(p) or not 0 <= p <= 1:
                raise ValueError
            probabilities[key_map[key]] = float(p)
    except (ValueError, KeyError, TypeError, AttributeError):
        raise ValueError('invalid_response') from None
    return {'choice': key_map[answer['choice']], 'probabilities': probabilities}


def choice(request, files, question, candidates, *, endpoint=ENDPOINT, budget_ms=1500, store=None) -> dict:
    """Ask one choice question; never raises. {'status', 'choice', 'probabilities', 'latencyMs'}."""
    started = time.monotonic()
    status, decoded = 'unavailable', None
    try:
        payload, key_map = build_request(request, files, question, candidates)
        cache = Path(store if store is not None else root()) / 'laya-health-advice.json'
        response, _ = post_local(endpoint, '/v1/systemone', payload, budget_ms / 1000.0, health_cache=cache)
        decoded, status = decode(response, key_map), 'ok'
    except ValueError as exc:
        code = str(exc)
        status = ('timeout' if code == 'invalid_timeout' else code
                  if code in ('timeout', 'identity_failed', 'redirect_refused') else
                  'invalid' if code.startswith(('invalid', 'response')) else 'unavailable')
    except Exception as exc:  # noqa: BLE001 - the contract is "never raises"
        status = 'timeout' if 'timed out' in str(exc).lower() else 'unavailable'
    return {'status': status, 'choice': decoded and decoded['choice'],
            'probabilities': decoded and decoded['probabilities'],
            'latencyMs': round((time.monotonic() - started) * 1000, 1)}


# ------------------------------------------------------------------ mode

def laya_revision(store=None) -> str:
    try:
        value = json.loads(_read_regular(Path(store or root()) / 'laya-runtime.json', 16384)).get('revision')
    except Exception:  # noqa: BLE001
        return 'unknown'
    return value if isinstance(value, str) and _REVISION.fullmatch(value) else 'unknown'


def policy_sha256(decision, question, policy) -> str:
    """Binding for an advise-v1 decision: the question plus the caller's fixed policy description
    (candidate ids or, for dynamic shortlists, their construction rule)."""
    return sha256({'decision': decision, 'question': question, 'policy': policy, 'instrument': INSTRUMENT_SHA256})


def effective_mode(decision, policy_sha, store=None) -> str:
    """'off' | 'shadow' | 'advise'. Only an entry whose earned binding matches what runs now may advise."""
    try:
        state = json.loads(_read_regular(Path(store or root()) / 'registry-state.json', 1 << 20))
        entry = state['decisions'].get(decision)
    except Exception:  # noqa: BLE001 - missing or corrupt state reads as shadow
        return 'shadow'
    if not isinstance(entry, dict) or entry.get('mode') not in MODES:
        return 'shadow'
    if entry['mode'] == 'off':
        return 'off'
    if entry['mode'] != 'advise':
        return 'shadow'
    revision = entry.get('layaRevision')
    if (entry.get('policySha256') != policy_sha or entry.get('instrumentSha256') != INSTRUMENT_SHA256
            or (revision is not None and revision != laya_revision(store))):
        return 'shadow'
    return 'advise'


def holdback(decision, key) -> bool:
    share = HOLDBACK[TIERS[decision]]
    return int(sha256('holdback:' + decision + ':' + key)[:8], 16) / 0x100000000 < share


# ------------------------------------------------------------------ records

def _read_regular(path, max_bytes) -> bytes:
    fd = os.open(str(path), os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > max_bytes:
            raise ValueError('not a regular file within the size limit')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            return stream.read(max_bytes)
    finally:
        os.close(fd)


def _private_dir(path: Path, anchor: Path) -> Path:
    path.relative_to(anchor)
    for component in [path, *path.parents]:
        if component == anchor.parent:
            break
        if component.is_symlink():
            raise ValueError('symlinked typed-decision path refused')
    missing, probe = [], path
    while not probe.exists() and probe != probe.parent:
        missing.append(probe)
        probe = probe.parent
    for directory in reversed(missing):
        try:
            directory.mkdir(mode=0o700)
        except FileExistsError:
            pass
    if path.is_symlink() or not path.is_dir():
        raise ValueError('typed-decision path is not a directory')
    return path


def _write_atomic(path: Path, value) -> None:
    handle, temporary = tempfile.mkstemp(prefix='.tmp-', dir=str(path.parent))
    try:
        with os.fdopen(handle, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, sort_keys=True)
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _write_once(store: Path, decision, kind, decision_id, value) -> bool:
    """Publish `value` at <store>/<decision>/<kind>/<id>.json unless it exists. True when this call wrote it."""
    if not _DECISION.fullmatch(decision) or not _DECISION_ID.fullmatch(decision_id):
        raise ValueError('invalid record path component')
    directory = _private_dir(store / decision / kind, store)
    target = directory / f'{decision_id}.json'
    handle, temporary = tempfile.mkstemp(prefix='.tmp-', dir=str(directory))
    try:
        with os.fdopen(handle, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        try:
            os.link(temporary, target)
        except FileExistsError:
            return False
        return True
    finally:
        os.unlink(temporary)


def load(decision, decision_id, kind='choice', store=None):
    """A stored record (dict) or None."""
    try:
        if not _DECISION.fullmatch(decision) or not _DECISION_ID.fullmatch(decision_id):
            return None
        return json.loads(_read_regular(Path(store or root()) / decision / kind / f'{decision_id}.json', 1 << 20))
    except Exception:  # noqa: BLE001
        return None


def _validate_candidates(candidates) -> list:
    if not isinstance(candidates, list) or not 2 <= len(candidates) <= MAX_CANDIDATES:
        raise ValueError('candidate count out of range')
    ids = []
    for item in candidates:
        if (not isinstance(item, dict) or set(item) != {'id', 'criterion'} or not isinstance(item['id'], str)
                or not _CANDIDATE.fullmatch(item['id']) or not isinstance(item['criterion'], str)
                or not item['criterion'].strip()):
            raise ValueError('invalid candidate')
        ids.append(item['id'])
    if len(set(ids)) != len(ids):
        raise ValueError('duplicate candidate')
    return ids


def advise(decision, request, candidates, key, *, critical_if_wrong, question, policy, files=(),
           endpoint=ENDPOINT, budget_ms=1500, store=None, call=None, snapshot=True) -> dict:
    """Ask Laya for an advise-v1 recommendation and record it before anything is shown.

    `key` identifies the decision occurrence (idempotent: a repeat returns the stored record's answer).
    `critical_if_wrong` must come from trusted caller state (hard gates), never from request text.
    Returns {'decisionId', 'mode', 'holdback', 'recommendation': {'id', 'confidence'} | None, 'policySha256'}.
    """
    if decision not in TIERS:
        raise ValueError('unknown decision')
    if not isinstance(key, str) or not key:
        raise ValueError('decision key required')
    ids = _validate_candidates(candidates)
    store = Path(store or root())
    policy_sha = policy_sha256(decision, question, policy)
    decision_id = sha256(decision + ':' + key)[:32]
    mode = effective_mode(decision, policy_sha, store)
    held = holdback(decision, key)
    result = {'decisionId': decision_id, 'mode': mode, 'holdback': held, 'recommendation': None,
              'policySha256': policy_sha}
    if mode == 'off':
        return result
    existing = load(decision, decision_id, store=store)
    if existing is None:
        answer = (call or choice)(request, files, question, candidates, endpoint=endpoint, budget_ms=budget_ms,
                                  store=store)
        record = {'schema': RECORD_SCHEMA, 'decision': decision, 'decisionId': decision_id,
                  'ts': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'mode': mode,
                  'arm': 'holdback' if held else 'treatment', 'tier': TIERS[decision],
                  'policySha256': policy_sha, 'instrumentSha256': INSTRUMENT_SHA256,
                  'layaRevision': laya_revision(store), 'candidates': ids,
                  'criticalIfWrong': bool(critical_if_wrong), 'requestSha256': sha256(scrub(request)),
                  'files': len(clean_files(files)),
                  'laya': {k: answer.get(k) for k in ('status', 'choice', 'probabilities', 'latencyMs')}}
        try:
            if snapshot:
                _write_once(store, decision, 'snapshot', decision_id,
                            {'request': scrub(request), 'files': clean_files(files), 'question': question,
                             'candidates': candidates, 'scrub': SCRUB_VERSION})
            _write_once(store, decision, 'choice', decision_id, record)
        except (OSError, ValueError):
            return result  # no durable record, no advice
        existing = load(decision, decision_id, store=store)
        if existing is None:
            return result
    laya = existing.get('laya') or {}
    if (mode == 'advise' and not held and existing.get('policySha256') == policy_sha
            and laya.get('status') == 'ok' and laya.get('choice') in ids):
        confidence = (laya.get('probabilities') or {}).get(laya['choice'])
        result['recommendation'] = {'id': laya['choice'],
                                    'confidence': round(confidence, 3) if isinstance(confidence, float) else None}
    return result


def record_outcome(decision, decision_id, chosen, store=None) -> bool:
    """What the agent actually did. First write wins; False for a duplicate or an unknown choice."""
    store = Path(store or root())
    record = load(decision, decision_id, store=store)
    if record is None or chosen not in record.get('candidates', ()):
        return False
    try:
        return _write_once(store, decision, 'outcome', decision_id,
                           {'schema': OUTCOME_SCHEMA, 'decision': decision, 'decisionId': decision_id,
                            'chosen': chosen, 'followed': chosen == (record.get('laya') or {}).get('choice'),
                            'ts': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())})
    except (OSError, ValueError):
        return False


def advice_line(decision, result, label) -> str:
    """One agent-facing sentence for an earned recommendation ('' otherwise). Never includes model text."""
    rec = result.get('recommendation')
    if not rec:
        return ''
    confidence = '' if rec['confidence'] is None else f", confidence {rec['confidence']:.2f}, uncalibrated"
    return (f"Laya advises {label} `{rec['id']}` (advisory{confidence}; decision {result['decisionId']}). "
            "You may override it; the incumbent checks still apply.")
