"""Explicit, bounded pre-decision context; never native origin or authority.

Sidecars leave legacy receipts untouched. A conflicting/late assertion is retained
as a durable hold, not silently repaired or used to change the authoritative task.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import stat

SCHEMA = 'rhize-workflow-task-context-v2'
CONSULT_SCHEMA = 'rhize-workflow-consultation-v2'
EVENT_KINDS = {'new_task', 'changed_intent', 'continuation', 'status', 'approval',
               'context_update', 'background_observer', 'summarizer', 'tool_callback',
               'worker_handback', 'scheduled', 'unknown'}
ACTIONS = {'create', 'revise', 'investigate', 'implement', 'review', 'validate',
           'research', 'explain', 'handoff', 'unknown'}
DOMAINS = {'content', 'software', 'operations', 'general', 'unknown'}
EXCLUSIONS = {'content_creation', 'publishing', 'deployment', 'external_messages'}
FIELDS = {'schemaVersion', 'opportunityId', 'promptHash', 'sessionHash', 'eventKind',
          'action', 'domain', 'exclusions', 'parentOpportunityId', 'preboundFamily'}
DERIVED = {'basis', 'nativeOrigin', 'recordedAt', 'sourceBindingSha256', 'contextSha256',
           'taskRootId', 'taskRootSourceBindingSha256'}
MAX_DEPTH = 32


def _tools():
    from workflow_selection import digest, read_json, locked_update
    return digest, read_json, locked_update


def _hash(value):
    return _tools()[0](json.dumps(value, sort_keys=True, separators=(',', ':')))


def context_digest(value):
    """Canonical input identity; never timestamps, A decisions or derived fields."""
    canonical = {key: value[key] for key in FIELDS}
    canonical['exclusions'] = sorted(set(canonical['exclusions']))
    return _hash(canonical)


def _id(value):
    return isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value) is not None


def _load(path):
    value = json.loads(read_evidence(path, 131072))
    if not isinstance(value, dict):
        raise ValueError('expected_object')
    return value


def read_evidence(path, maximum):
    """A FIFO/device/symlink must never block capture while a receipt is locked."""
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise OSError('evidence_must_be_regular')
        if info.st_size > maximum:
            raise ValueError('evidence_too_large')
        raw = stream.read(maximum + 1)
    if len(raw) > maximum:
        raise ValueError('evidence_too_large')
    return raw


def receipt_for(receipts, identity):
    if not _id(identity):
        raise ValueError('invalid_opportunity_id')
    receipt = _load(Path(receipts) / (identity + '.json'))
    if receipt.get('opportunityId') != identity or receipt.get('decisionPilot') != 'shadow-v2':
        raise ValueError('requires_v2_opportunity')
    return receipt


def source_binding(receipt):
    return _hash({k: receipt[k] for k in ('schemaVersion', 'opportunityId', 'host',
                  'sessionHash', 'taskHash', 'promptHash', 'observedAt', 'selectorDigest')})


def _path(receipts, directory, identity):
    return Path(receipts).parent / directory / (identity + '.json')


def _context_event(receipts, identity, reason, attempted_hash, directory):
    """Retain bounded hashes only; malformed user input is never copied to storage."""
    receipt = receipt_for(receipts, identity)
    event = {'reason': reason, 'attemptSha256': attempted_hash}
    def update(old):
        old = old or {'schemaVersion': ('rhize-workflow-context-hold-v2' if directory == 'task-context-holds'
                                        else 'rhize-workflow-context-diagnostic-v2'),
                      'opportunityId': identity, 'sourceBindingSha256': source_binding(receipt),
                      'events': []}
        if event in [{k: e[k] for k in event} for e in old['events']]:
            return old, False
        if len(old['events']) < 64:
            old['events'].append({**event, 'recordedAt': datetime.now(timezone.utc).isoformat()})
        else:
            if old.get('additionalConflicts') is True:
                return old, False
            old['additionalConflicts'] = True
        return old, True
    return _tools()[2](Path(receipts).parent / directory, identity, update)[0]


def hold_context(receipts, identity, reason, attempted_hash):
    return _context_event(receipts, identity, reason, attempted_hash, 'task-context-holds')


def diagnostic_context(receipts, identity, reason, attempted_hash):
    """I/O before an assertion arrives is diagnostic, not a semantic hold."""
    return _context_event(receipts, identity, reason, attempted_hash, 'task-context-diagnostics')


def read_context_evidence(receipts, identity, path):
    try:
        raw = read_evidence(path, 8192)
    except OSError:
        diagnostic_context(receipts, identity, 'context_input_unavailable', _hash('context_input_unavailable'))
        raise
    except ValueError:
        hold_context(receipts, identity, 'invalid_context_input', _hash('invalid_context_input'))
        raise
    try:
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError('expected_object')
        return value
    except ValueError:
        hold_context(receipts, identity, 'invalid_context_input', _tools()[0](raw))
        raise


def _check_hold(receipts, identity):
    path = _path(receipts, 'task-context-holds', identity)
    if path.exists():
        hold = _load(path)
        reasons = [e.get('reason') for e in hold.get('events', [])]
        raise ValueError('duplicate_context' if 'duplicate_context' in reasons else 'context_held')


def canonical_context(value, receipt):
    if not isinstance(value, dict) or set(value) != FIELDS:
        raise ValueError('invalid_context_schema')
    if value['schemaVersion'] != SCHEMA:
        raise ValueError('invalid_context_schema')
    for key in ('opportunityId', 'promptHash', 'sessionHash'):
        if value[key] != receipt[key]:
            raise ValueError('context_binding_mismatch')
    for key, allowed in (('eventKind', EVENT_KINDS), ('action', ACTIONS), ('domain', DOMAINS)):
        if not isinstance(value[key], str) or value[key] not in allowed:
            raise ValueError('invalid_context_enum')
    exclusions = value['exclusions']
    if not isinstance(exclusions, list) or len(exclusions) > len(EXCLUSIONS) or any(
            not isinstance(item, str) or item not in EXCLUSIONS for item in exclusions):
        raise ValueError('invalid_context_exclusions')
    if value['preboundFamily'] is not None and value['preboundFamily'] not in ('content', 'general'):
        raise ValueError('invalid_prebound_family')
    if value['parentOpportunityId'] is not None and not _id(value['parentOpportunityId']):
        raise ValueError('invalid_parent')
    if value['parentOpportunityId'] is not None and value['eventKind'] != 'continuation':
        raise ValueError('parent_requires_continuation')
    return {**value, 'exclusions': sorted(set(exclusions))}


def _parent(receipts, receipt, context, seen):
    identity = receipt['opportunityId']
    parent_id = context['parentOpportunityId']
    if not parent_id:
        if context['eventKind'] == 'continuation':
            raise ValueError('missing_parent_context')
        return identity, source_binding(receipt)
    if len(seen) >= MAX_DEPTH or parent_id in seen:
        raise ValueError('invalid_parent_ancestry')
    try:
        parent = receipt_for(receipts, parent_id)
    except FileNotFoundError as exc:
        raise ValueError('missing_parent_context') from exc
    if (parent['host'] != receipt['host'] or parent['sessionHash'] != receipt['sessionHash'] or
            datetime.fromisoformat(parent['observedAt']) >= datetime.fromisoformat(receipt['observedAt'])):
        raise ValueError('invalid_parent_binding')
    # An ancestor hold invalidates dependent contexts intentionally: there is no
    # longer a trustworthy sealed parent to inherit. Arm A can still proceed.
    parent_context = load_context(receipts, parent_id, _seen=seen)
    if parent_context is None:
        raise ValueError('missing_parent_context')
    if context['eventKind'] == 'continuation' and any(
            context[key] != parent_context[key] for key in ('action', 'domain', 'exclusions', 'preboundFamily')):
        raise ValueError('continuation_intent_conflict')
    return parent_context['taskRootId'], parent_context['taskRootSourceBindingSha256']


def load_context(receipts, identity, _seen=()):
    receipt = receipt_for(receipts, identity)
    _check_hold(receipts, identity)
    path = _path(receipts, 'task-context', identity)
    if not path.exists():
        return None
    if identity in _seen or len(_seen) >= MAX_DEPTH:
        raise ValueError('invalid_parent_ancestry')
    value = _load(path)
    if set(value) != FIELDS | DERIVED:
        raise ValueError('invalid_context_schema')
    canonical = canonical_context({k: value[k] for k in FIELDS}, receipt)
    root_id, root_binding = _parent(receipts, receipt, canonical, (*_seen, identity))
    if (value['sourceBindingSha256'] != source_binding(receipt) or value['contextSha256'] != _hash(canonical) or
            value['basis'] != 'agent_asserted' or value['nativeOrigin'] != 'unknown' or
            value['taskRootId'] != root_id or value['taskRootSourceBindingSha256'] != root_binding):
        raise ValueError('context_binding_mismatch')
    return value


def task_root(receipts, identity, context=None):
    verified = load_context(receipts, identity)
    if verified is None or (context is not None and context != verified):
        raise ValueError('missing_or_invalid_context')
    return verified['taskRootId']


def eligibility(context):
    if context['eventKind'] == 'unknown':
        return {'eligible': None, 'reason': 'unknown_event_kind'}
    if context['preboundFamily'] is not None or context['eventKind'] == 'scheduled':
        return {'eligible': False, 'reason': 'prebound_routine'}
    if context['eventKind'] == 'continuation':
        return {'eligible': False, 'reason': 'continuation_of_existing_task'}
    if context['eventKind'] not in {'new_task', 'changed_intent'}:
        return {'eligible': False, 'reason': 'operational_event'}
    if context['action'] == 'unknown' or context['domain'] == 'unknown':
        return {'eligible': None, 'reason': 'insufficient_structured_intent'}
    return {'eligible': True, 'reason': 'new_routing_decision'}


def _capture_context(receipts, identity, value):
    receipt = receipt_for(receipts, identity)
    attempted_hash = _hash(value)
    try:
        canonical = canonical_context(value, receipt)
        _check_hold(receipts, identity)
        path = _path(receipts, 'task-context', identity)
        # Replay canonical equality before checking later A activity.
        if path.exists():
            prior = load_context(receipts, identity)
            if prior['contextSha256'] == _hash(canonical):
                return prior
            raise ValueError('duplicate_context')
        if receipt.get('selection') is not None or receipt.get('terminalStatus') is not None or _path(receipts, 'consultations', identity).exists():
            raise ValueError('post_decision_context')
        root_id, root_binding = _parent(receipts, receipt, canonical, (identity,))
        result = {**canonical, 'contextSha256': _hash(canonical), 'sourceBindingSha256': source_binding(receipt),
                  'taskRootId': root_id, 'taskRootSourceBindingSha256': root_binding,
                  'basis': 'agent_asserted', 'nativeOrigin': 'unknown',
                  'recordedAt': datetime.now(timezone.utc).isoformat()}
        def update(old):
            if old is not None and old.get('contextSha256') != result['contextSha256']:
                raise ValueError('duplicate_context')
            return (old, False) if old is not None else (result, True)
        return _tools()[2](Path(receipts).parent / 'task-context', identity, update)[0]
    except OSError:
        diagnostic_context(receipts, identity, 'context_storage_unavailable', attempted_hash)
        raise
    except (ValueError, KeyError, TypeError) as exc:
        reason = str(exc) if isinstance(exc, ValueError) else 'invalid_context'
        allowed = {'invalid_context_schema', 'context_binding_mismatch', 'invalid_context_enum',
                   'invalid_context_exclusions', 'invalid_prebound_family', 'invalid_parent',
                   'duplicate_context', 'post_decision_context', 'missing_parent_context',
                   'invalid_parent_ancestry', 'invalid_parent_binding', 'continuation_intent_conflict',
                   'context_held', 'requires_v2_opportunity', 'parent_requires_continuation'}
        hold_context(receipts, identity, reason if reason in allowed else 'invalid_context', attempted_hash)
        raise


def capture_context(receipts, identity, value, seal=None):
    """Serialize context/request sealing with the authoritative receipt's writes."""
    result = None
    def update(receipt):
        nonlocal result
        result = _capture_context(receipts, identity, value)
        if seal is not None:
            try:
                seal(result, receipt)
            except Exception:
                # Request construction may have partially executed. Preserve the
                # failed attempt permanently; only a genuinely new opportunity
                # can be scored, never a retrospective retry of this identity.
                hold_context(receipts, identity, 'request_seal_failed', result['contextSha256'])
                raise
        return receipt, False
    _tools()[2](Path(receipts), identity, update)
    return result


def load_consultation(receipts, identity):
    receipt = receipt_for(receipts, identity)
    path = _path(receipts, 'consultations', identity)
    if not path.exists():
        return None
    value = _load(path)
    context = load_context(receipts, identity)
    if (set(value) != {'schemaVersion', 'opportunityId', 'kind', 'sourceBindingSha256', 'contextSha256',
                      'evidenceSha256', 'basis', 'recordedAt'} or value.get('schemaVersion') != CONSULT_SCHEMA or
            value.get('opportunityId') != identity or value.get('kind') not in ('content', 'general', 'none') or
            value.get('sourceBindingSha256') != source_binding(receipt) or context is None or
            value.get('contextSha256') != context['contextSha256'] or not _id(value.get('evidenceSha256')) or
            value.get('basis') != 'operator_reported'):
        raise ValueError('invalid_consultation')
    return value


def _capture_consultation(receipts, identity, kind, evidence):
    receipt = receipt_for(receipts, identity)
    context = load_context(receipts, identity)
    if context is None:
        raise ValueError('context_must_precede_consultation')
    if kind not in ('content', 'general', 'none'):
        raise ValueError('invalid_consultation_kind')
    raw = read_evidence(evidence, 16 * 1024 * 1024)
    result = {'schemaVersion': CONSULT_SCHEMA, 'opportunityId': identity, 'kind': kind,
              'sourceBindingSha256': source_binding(receipt), 'contextSha256': context['contextSha256'],
              'evidenceSha256': _tools()[0](raw), 'basis': 'operator_reported',
              'recordedAt': datetime.now(timezone.utc).isoformat()}
    def update(old):
        if old is not None:
            if {k: v for k, v in old.items() if k != 'recordedAt'} != {k: v for k, v in result.items() if k != 'recordedAt'}:
                raise ValueError('consultation_is_immutable')
            return old, False
        if receipt.get('selection') is not None or receipt.get('terminalStatus') is not None:
            raise ValueError('consultation_must_precede_selection')
        return result, True
    return _tools()[2](Path(receipts).parent / 'consultations', identity, update)[0]


def capture_consultation(receipts, identity, kind, evidence):
    result = None
    def update(receipt):
        nonlocal result
        result = _capture_consultation(receipts, identity, kind, evidence)
        return receipt, False
    _tools()[2](Path(receipts), identity, update)
    return result
