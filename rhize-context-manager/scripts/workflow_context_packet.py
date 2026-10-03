"""Private, redacted native requests; never model scoring input or authority."""
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import uuid

from workflow_selection import digest, locked_update
from workflow_task_context import load_context, read_evidence, receipt_for, source_binding

SCHEMA = 'rhize-workflow-request-snapshot-v1'
LINK_SCHEMA = 'rhize-workflow-request-context-v1'
MAX_PACKET = 131072
SNAPSHOT_FIELDS = {'schemaVersion', 'opportunityId', 'sourceBindingSha256', 'sessionHash',
                   'promptHash', 'selectorDigest', 'receiptObservedAt', 'capturedAt',
                   'originalRequest', 'requestTruncated', 'sanitizedRequestSha256',
                   'transcriptPath', 'captureOrigin', 'operationalKind', 'snapshotSha256'}


def _sha(value, field):
    return digest(json.dumps({k: v for k, v in value.items() if k != field},
                            sort_keys=True, separators=(',', ':')))


def _read(path):
    _safe_parent(path.parent)
    value = json.loads(read_evidence(path, MAX_PACKET))
    if not isinstance(value, dict):
        raise ValueError('request_snapshot_invalid')
    return value


def _safe_parent(path):
    if path.resolve() != path.absolute():
        raise ValueError('request_snapshot_source_invalid')


def _time(value):
    if not isinstance(value, str):
        raise ValueError('request_snapshot_time_invalid')
    stamp = datetime.fromisoformat(value)
    if stamp.tzinfo is None:
        raise ValueError('request_snapshot_time_invalid')
    return stamp.timestamp()


def _before_context(receipts, identity, captured_at):
    for directory, field in (('task-context', 'recordedAt'), ('pilot/v2/observations', 'createdAt')):
        path = Path(receipts).parent / directory / (identity + '.json')
        if path.exists():
            recorded = _read(path)[field]
            stamp = _time(recorded) if field == 'recordedAt' else recorded
            if type(stamp) not in (int, float) or not math.isfinite(stamp) or captured_at > stamp:
                raise ValueError('request_snapshot_post_decision')


def load_request_snapshot(receipts, identity):
    from pilot_redaction import PROMPT_LIMIT
    receipt = receipt_for(receipts, identity)
    path = Path(receipts).parent / 'request-snapshots' / (identity + '.json')
    if not path.exists() and not path.is_symlink():
        return None
    value = _read(path)
    if (set(value) != SNAPSHOT_FIELDS or value['schemaVersion'] != SCHEMA or
            value['snapshotSha256'] != _sha(value, 'snapshotSha256') or
            value['opportunityId'] != identity or value['sourceBindingSha256'] != source_binding(receipt) or
            any(value[k] != receipt[k] for k in ('sessionHash', 'promptHash', 'selectorDigest')) or
            value['receiptObservedAt'] != receipt['observedAt'] or
            value['captureOrigin'] != 'native_hook' or
            value['operationalKind'] not in (None, 'background_observer') or
            not isinstance(value['originalRequest'], str) or
            len(value['originalRequest']) > PROMPT_LIMIT + len('\n[TRUNCATED: more source context exists]') or
            type(value['requestTruncated']) is not bool or
            value['sanitizedRequestSha256'] != digest(value['originalRequest']) or
            (value['transcriptPath'] is not None and
             (not isinstance(value['transcriptPath'], str) or len(value['transcriptPath']) > 4096))):
        raise ValueError('request_snapshot_binding_mismatch')
    captured = _time(value['capturedAt'])
    if captured < _time(receipt['observedAt']):
        raise ValueError('request_snapshot_time_invalid')
    _before_context(receipts, identity, captured)
    return value


def native_observer(payload, host, env=None):
    """Require the existing ECC launcher contract AND its dedicated native source."""
    env = os.environ if env is None else env
    if host != 'claude' or env.get('ECC_SKIP_OBSERVE') != '1' or env.get('ECC_HOOK_PROFILE') != 'minimal':
        return False
    home = Path.home()
    observer_root = home / '.local/share/ecc-homunculus'
    session = payload.get('session_id')
    try:
        cwd = Path(payload['cwd'])
        allowed_cwd = cwd == observer_root or (cwd.parent == observer_root / 'projects' and
                                              re.fullmatch(r'[0-9a-f]{12}', cwd.name))
        if str(uuid.UUID(session)) != session or not allowed_cwd or not cwd.is_dir() or cwd.resolve() != cwd:
            return False
        transcript = Path(payload['transcript_path'])
        project = home / '.claude/projects' / re.sub(r'[^a-zA-Z0-9]', '-', str(cwd))
        if transcript != project / (session + '.jsonl') or transcript.resolve() != transcript:
            return False
        raw = read_evidence(transcript, 1024 * 1024)
        for line in raw.splitlines():
            row = json.loads(line)
            content = row.get('message', {}).get('content')
            if isinstance(content, list):
                content = '\n'.join(b['text'] for b in content if isinstance(b, dict) and b.get('type') == 'text')
            if (row.get('type') == 'user' and row.get('isSidechain') is False and row.get('isMeta') is not True and
                    row.get('sessionId') == session and row.get('cwd') == str(cwd) and
                    isinstance(content, str) and digest(content) == digest(payload['prompt'])):
                return True
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False
    return False


def capture_request_snapshot(receipts, receipt, payload):
    """Called only for a fresh native hook opportunity; never reconstruct old turns."""
    from pilot_redaction import sanitize, PROMPT_LIMIT
    identity = receipt['opportunityId']
    _safe_parent(Path(receipts).parent / 'request-snapshots')
    if (digest(payload['prompt']) != receipt['promptHash'] or
            digest(payload.get('session_id') or payload.get('thread_id')) != receipt['sessionHash']):
        raise ValueError('request_snapshot_binding_mismatch')
    text, truncated = sanitize(payload['prompt'], PROMPT_LIMIT)
    transcript = payload.get('transcript_path')
    if transcript is not None and (not isinstance(transcript, str) or len(transcript) > 4096):
        raise ValueError('request_snapshot_source_invalid')
    value = {'schemaVersion': SCHEMA, 'opportunityId': identity,
             'sourceBindingSha256': source_binding(receipt),
             **{k: receipt[k] for k in ('sessionHash', 'promptHash', 'selectorDigest')},
             'receiptObservedAt': receipt['observedAt'], 'capturedAt': datetime.now(timezone.utc).isoformat(),
             'originalRequest': text, 'requestTruncated': truncated, 'sanitizedRequestSha256': digest(text),
             'transcriptPath': transcript, 'captureOrigin': 'native_hook',
             'operationalKind': 'background_observer' if native_observer(payload, receipt['host']) else None}
    value['snapshotSha256'] = _sha(value, 'snapshotSha256')
    result = None
    def seal(current):
        nonlocal result
        prior = load_request_snapshot(receipts, identity)
        if prior is not None:
            if any(prior[k] != value[k] for k in SNAPSHOT_FIELDS - {'capturedAt', 'snapshotSha256'}):
                raise ValueError('request_snapshot_conflict')
            result = prior
            return current, False
        if (current.get('selection') is not None or current.get('terminalStatus') is not None or
                any((Path(receipts).parent / d / (identity + '.json')).exists()
                    for d in ('task-context', 'consultations', 'pilot/v2/observations'))):
            raise ValueError('request_snapshot_post_decision')
        if current != receipt:
            raise ValueError('request_snapshot_binding_mismatch')
        result = locked_update(Path(receipts).parent / 'request-snapshots', identity,
                               lambda old: (old, False) if old is not None else (value, True))[0]
        return current, False
    locked_update(Path(receipts), identity, seal)
    return result


def _linked_snapshot(receipts, receipt, identity):
    linked = load_request_snapshot(receipts, identity)
    context = load_context(receipts, identity)
    if (linked is None or context is None or linked['sessionHash'] != receipt['sessionHash'] or
            receipt_for(receipts, identity)['host'] != receipt['host'] or
            _time(linked['receiptObservedAt']) >= _time(receipt['observedAt'])):
        raise ValueError('request_context_binding_mismatch')
    return linked


def capture_request_context(receipts, identity, context_ids):
    if not context_ids:
        return
    if len(context_ids) > 4 or len(set(context_ids)) != len(context_ids):
        raise ValueError('request_context_invalid_links')
    _safe_parent(Path(receipts).parent / 'request-context')
    def seal(receipt):
        current = load_request_snapshot(receipts, identity)
        if current is None:
            raise ValueError('request_snapshot_missing')
        preceding = sorted((_linked_snapshot(receipts, receipt, i) for i in context_ids),
                           key=lambda v: v['receiptObservedAt'])
        links = [{k: v[k] for k in ('opportunityId', 'snapshotSha256', 'sourceBindingSha256')} for v in preceding]
        path = Path(receipts).parent / 'request-context' / (identity + '.json')
        if path.exists() or path.is_symlink():
            prior = load_request_context(receipts, identity)
            if [v['opportunityId'] for v in prior['preceding']] != [v['opportunityId'] for v in preceding]:
                raise ValueError('request_context_conflict')
            return receipt, False
        if receipt.get('selection') is not None or receipt.get('terminalStatus') is not None or any(
                (Path(receipts).parent / d / (identity + '.json')).exists()
                for d in ('task-context', 'consultations', 'pilot/v2/observations')):
            raise ValueError('request_snapshot_post_decision')
        value = {'schemaVersion': LINK_SCHEMA, 'opportunityId': identity,
                 'snapshotSha256': current['snapshotSha256'], 'links': links,
                 'capturedAt': datetime.now(timezone.utc).isoformat()}
        value['contextSha256'] = _sha(value, 'contextSha256')
        locked_update(path.parent, identity, lambda old: (old, False) if old else (value, True))
        return receipt, False
    locked_update(Path(receipts), identity, seal)


def load_request_context(receipts, identity):
    current = load_request_snapshot(receipts, identity)
    path = Path(receipts).parent / 'request-context' / (identity + '.json')
    if not path.exists() and not path.is_symlink():
        return {'current': current, 'preceding': [], 'contextSha256': None}
    value = _read(path)
    if (current is None or set(value) != {'schemaVersion', 'opportunityId', 'snapshotSha256', 'links', 'capturedAt', 'contextSha256'} or
            value['schemaVersion'] != LINK_SCHEMA or value['opportunityId'] != identity or
            value['snapshotSha256'] != current['snapshotSha256'] or
            value['contextSha256'] != _sha(value, 'contextSha256') or
            not isinstance(value['links'], list) or not 1 <= len(value['links']) <= 4):
        raise ValueError('request_context_binding_mismatch')
    captured = _time(value['capturedAt'])
    if captured < _time(current['capturedAt']):
        raise ValueError('request_snapshot_time_invalid')
    _before_context(receipts, identity, captured)
    receipt = receipt_for(receipts, identity)
    preceding = []
    for link in value['links']:
        if not isinstance(link, dict) or set(link) != {'opportunityId', 'snapshotSha256', 'sourceBindingSha256'}:
            raise ValueError('request_context_binding_mismatch')
        linked = _linked_snapshot(receipts, receipt, link['opportunityId'])
        if any(link[k] != linked[k] for k in link):
            raise ValueError('request_context_binding_mismatch')
        preceding.append(linked)
    if len({v['opportunityId'] for v in preceding}) != len(preceding):
        raise ValueError('request_context_invalid_links')
    return {'current': current, 'preceding': preceding, 'contextSha256': value['contextSha256']}
