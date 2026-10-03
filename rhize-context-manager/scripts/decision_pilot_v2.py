"""Versioned, source-bound shadow observations; no execution or label authority."""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime

from workflow_selection import digest, read_json
from pilot_routing import CHOICES, decode_scores

SCHEMA = 'rhize-decision-pilot-v2'
NORMALIZATION = 'workflow-input-v2'
HELD_REASONS = frozenset('''source_changed parent_source_changed context_missing context_held
    context_binding_changed context_binding_mismatch invalid_context_binding context_changed
    invalid_context_schema invalid_context_enum invalid_context_exclusions invalid_prebound_family
    duplicate_context post_decision_context request_seal_failed request_changed ineligible_request
    parent_request_changed parent_reference_changed parent_request_missing parent_context_changed
    missing_parent_context invalid_parent invalid_parent_ancestry invalid_parent_binding
    continuation_intent_conflict unexpected_inherited requires_v2_opportunity symlink_evidence
    observation_missing result_binding_changed result_decoding_changed invalid_result_metrics
    inherited_result_binding_changed inherited_result_decoding_changed label_binding_changed
    outcome_binding_changed label_contract_changed outcome_contract_changed outcome_acceptance_invalid
    invalid_consultation'''.split())
SCORING_REASONS = frozenset({'invalid_usage', 'provider_answer_type_mismatch', 'invalid_latency'})


def failure_reason(exc):
    message = str(exc)
    routing = {'invalid routing scores': 'invalid_routing_scores',
               'invalid routing score': 'invalid_routing_score',
               'invalid abstention threshold': 'invalid_abstention_threshold',
               'invalid routing exclusions': 'invalid_routing_exclusions'}
    if isinstance(exc, ValueError):
        if message in HELD_REASONS | SCORING_REASONS:
            return message
        if message in routing:
            return routing[message]
    return type(exc).__name__



def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def context_digest(context):
    keys = ('schemaVersion', 'opportunityId', 'promptHash', 'sessionHash', 'eventKind',
            'action', 'domain', 'exclusions', 'parentOpportunityId', 'preboundFamily')
    value = {key: context[key] for key in keys}
    value['exclusions'] = sorted(value['exclusions'])
    return digest(canonical(value))


def source_digest():
    scripts = Path(__file__).parent
    paths = [Path(__file__), scripts / 'decision_pilot.py', scripts / 'workflow_selection.py',
             scripts / 'workflow_task_context.py', scripts / 'workflow_context_packet.py',
             scripts / 'pilot_redaction.py', scripts / 'pilot_routing.py',
             scripts / 'context_experiments/typed_relevance.py']
    return digest(b''.join(p.read_bytes() for p in paths))


def request_for(context):
    # No prompt, catalog match, consultation, selected family, or label in features.
    state = {key: context[key] for key in ('eventKind', 'action', 'domain', 'exclusions')}
    state['exclusions'] = sorted(state['exclusions'])
    wording = {
        'content': 'Should this task consult the content workflow family for article creation or revision?',
        'general': 'Should this task consult the general catalog for a repeatable multi-step workflow?',
        'none': 'Should this task proceed without consulting either workflow family?',
    }
    return {'model': 'typed-decisions', 'state': state, 'questions': {
        f'c{i}': {'type': 'noul', 'instructions': wording[name] +
                 ' Use only the structured intent and exclusions. This is consultation relevance, not catalog match, execution, permission or correctness.'}
        for i, name in enumerate(CHOICES)}}


def ensure_root(root):
    if root.is_symlink() or (root / 'v2').is_symlink():
        raise ValueError('symlink pilot root refused')


def enqueue(context, receipt, root, spawn=True, receipts=None):
    from decision_pilot import save_once
    from workflow_task_context import load_context, eligibility
    ensure_root(root)
    receipts = receipts or root.parent / 'receipts'
    identity = receipt['opportunityId']
    verified = load_context(receipts, identity)
    if verified != context or receipt.get('decisionPilot') != 'shadow-v2':
        raise ValueError('invalid_context_binding')
    # Repeated enqueue must preserve the sealed first request and collection source.
    existing = root / 'v2/observations' / (identity + '.json')
    if existing.exists():
        old = read_json(existing)
        if old.get('contextSha256') != context_digest(context):
            raise ValueError('context_changed')
        return old
    disposition = eligibility(context)
    request = request_for(context) if disposition['eligible'] is True else None
    inherited = None
    if context['eventKind'] == 'continuation' and context.get('parentOpportunityId'):
        parent_id = context['parentOpportunityId']
        parent = read_json(root / 'v2/observations' / (parent_id + '.json'))
        parent_context = load_context(receipts, parent_id)
        if parent.get('sourceSha256') != source_digest():
            raise ValueError('parent_source_changed')
        validate_observation(parent, receipts, parent_id, require_current_source=True, root=root)
        if parent.get('contextSha256') != context_digest(parent_context):
            raise ValueError('parent_context_changed')
        inherited = parent.get('inherited') or {
            'opportunityId': parent_id, 'requestSha256': parent.get('requestSha256'),
            'sourceSha256': parent.get('sourceSha256')}
        if not inherited.get('requestSha256'):
            raise ValueError('parent_request_missing')
    value = {'schema': SCHEMA, 'opportunityId': identity, 'host': receipt['host'],
             'sessionHash': receipt['sessionHash'], 'taskHash': receipt['taskHash'],
             'createdAt': time.time(), 'sourceSha256': source_digest(),
             'context': context, 'contextSha256': context_digest(context),
             'disposition': disposition, 'request': request,
             'requestSha256': digest(canonical(request)) if request else None,
             'inherited': inherited, 'basis': 'agent_asserted', 'nativeOrigin': 'unknown'}
    save_once(root / 'v2/observations', identity, value)
    if spawn and disposition['eligible'] is True:
        try:
            subprocess.Popen([sys.executable, str(Path(__file__).with_name('decision_pilot.py')),
                              '--root', str(root), '--receipts', str(receipts), 'drain', '--cohort', 'v2'],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True, close_fds=True)
        except OSError:
            pass  # Pending remains visible; no retry or authority implied.
    return value


def validate_observation(observation, receipts, identity, require_current_source=False, root=None):
    from workflow_task_context import load_context, eligibility
    context = load_context(receipts, identity)
    if not context:
        raise ValueError('context_missing')
    if (observation.get('schema') != SCHEMA or observation.get('opportunityId') != identity
            or observation.get('context') != context
            or observation.get('contextSha256') != context_digest(context)
            or observation.get('disposition') != eligibility(context)):
        raise ValueError('context_binding_changed')
    if require_current_source and observation.get('sourceSha256') != source_digest():
        raise ValueError('source_changed')
    if observation['disposition']['eligible'] is True:
        if (observation.get('request') != request_for(context)
                or observation.get('requestSha256') != digest(canonical(observation['request']))):
            raise ValueError('request_changed')
    elif observation.get('request') is not None or observation.get('requestSha256') is not None:
        raise ValueError('ineligible_request')
    inherited = observation.get('inherited')
    if context['eventKind'] == 'continuation':
        if not isinstance(inherited, dict) or not context.get('parentOpportunityId'):
            raise ValueError('parent_request_missing')
        storage = root or receipts.parent / 'pilot'
        immediate = read_json(storage / 'v2/observations' / (context['parentOpportunityId'] + '.json'))
        expected = immediate.get('inherited') or {
            'opportunityId': context['parentOpportunityId'], 'requestSha256': immediate.get('requestSha256'),
            'sourceSha256': immediate.get('sourceSha256')}
        if inherited != expected:
            raise ValueError('parent_reference_changed')
        parent_id = inherited.get('opportunityId')
        parent_context = load_context(receipts, parent_id)
        parent = read_json((root or receipts.parent / 'pilot') / 'v2/observations' / (parent_id + '.json'))
        if (parent.get('contextSha256') != context_digest(parent_context)
                or parent.get('requestSha256') != inherited.get('requestSha256')
                or parent.get('sourceSha256') != inherited.get('sourceSha256')
                or parent.get('request') != request_for(parent_context)
                or parent.get('requestSha256') != digest(canonical(parent.get('request')))):
            raise ValueError('parent_request_changed')
        if require_current_source and parent.get('sourceSha256') != source_digest():
            raise ValueError('parent_source_changed')
    elif inherited is not None:
        raise ValueError('unexpected_inherited')
    return context


def assess(observation, receipts, call, root=None):
    context = validate_observation(observation, receipts, observation['opportunityId'], True, root=root)
    if observation['disposition']['eligible'] is not True:
        return {'status': 'excluded', 'reasonCode': observation['disposition']['reason'],
                'variant': 'B_shadow_not_run', 'incumbentAltered': False, 'usage': None}
    request = observation['request']
    value, latency = call('http://127.0.0.1:8000', request)
    usage = value.get('usage')
    if (not isinstance(usage, dict) or any(type(usage.get(k)) is not int or usage[k] < 0
                                        for k in ('input_tokens', 'output_tokens'))):
        raise ValueError('invalid_usage')
    if any(not isinstance(value['answers'].get(f'c{i}'), dict)
           or value['answers'][f'c{i}'].get('type') != 'noul' for i in range(len(CHOICES))):
        raise ValueError('provider_answer_type_mismatch')
    scores = {name: value['answers'][f'c{i}']['noul'] for i, name in enumerate(CHOICES)}
    decoded = decode_scores(scores, exclusions=context['exclusions'])
    if type(latency) not in (int, float) or not math.isfinite(latency) or latency < 0:
        raise ValueError('invalid_latency')
    return {'schema': SCHEMA, 'status': 'shadow', 'variant': 'B_local_laya',
            'sourceSha256': observation['sourceSha256'], 'requestSha256': observation['requestSha256'],
            'scores': scores, 'ranking': decoded['ranking'], 'choice': decoded['choice'],
            'reasonCode': decoded['reason'], 'latencyMs': latency, 'usage': usage,
            'model': request['model'], 'routedModel': value['routing']['model'], 'incumbentAltered': False}


def joined(root, receipts):
    from decision_pilot import inventory
    from workflow_task_context import load_context, load_consultation, eligibility
    ensure_root(root)
    collections = {name: dict(inventory(root / 'v2' / name))
                   for name in ('observations', 'results', 'labels', 'outcomes', 'stops')}
    rows = []
    for identity, receipt in inventory(receipts):
        if receipt.get('decisionPilot') != 'shadow-v2':
            continue
        row = {'id': identity, 'receipt': receipt, 'context': None, 'armA': None, 'armB': None,
               'inheritedArmB': None, 'bucket': 'missing', 'reason': 'context_missing',
               **{name[:-1] if name != 'observations' else 'observation': records.get(identity)
                  for name, records in collections.items()}}
        try:
            context = load_context(receipts, identity)
            row['context'] = context
            if context:
                disposition = eligibility(context)
                row['bucket'] = ('eligible' if disposition['eligible'] is True else
                                 'excluded' if disposition['eligible'] is False else 'unknown')
                row['reason'] = disposition['reason']
                observation = row['observation']
                if not observation:
                    raise ValueError('observation_missing')
                validate_observation(observation, receipts, identity, require_current_source=True, root=root)
                consultation = load_consultation(receipts, identity)
                row['armA'] = consultation['kind'] if consultation else None
                result = row['result']
                if result and result.get('status') == 'shadow':
                    if (result.get('requestSha256') != observation['requestSha256']
                            or result.get('sourceSha256') != observation['sourceSha256']):
                        raise ValueError('result_binding_changed')
                    usage = result.get('usage')
                    if (not isinstance(usage, dict) or any(type(usage.get(k)) is not int or usage[k] < 0
                            for k in ('input_tokens', 'output_tokens'))
                            or type(result.get('latencyMs')) not in (int, float)
                            or not math.isfinite(result['latencyMs']) or result['latencyMs'] < 0):
                        raise ValueError('invalid_result_metrics')
                    decoded = decode_scores(result['scores'], exclusions=context['exclusions'])
                    if decoded['choice'] != result.get('choice') or decoded['ranking'] != result.get('ranking'):
                        raise ValueError('result_decoding_changed')
                    row['armB'] = decoded['choice']
                if result and result.get('reasonCode') in HELD_REASONS:
                    raise ValueError(result['reasonCode'])
                if observation.get('inherited'):
                    parent = collections['results'].get(observation['inherited']['opportunityId'])
                    if parent and parent.get('status') == 'shadow':
                        if (parent.get('requestSha256') != observation['inherited']['requestSha256']
                                or parent.get('sourceSha256') != observation['inherited']['sourceSha256']):
                            raise ValueError('inherited_result_binding_changed')
                        decoded = decode_scores(parent['scores'], exclusions=context['exclusions'])
                        if decoded['choice'] != parent.get('choice') or decoded['ranking'] != parent.get('ranking'):
                            raise ValueError('inherited_result_decoding_changed')
                        row['inheritedArmB'] = decoded['choice']
                for kind in ('label', 'outcome'):
                    item = row[kind]
                    if item and (item.get('opportunityId') != identity
                                 or item.get('sourceSha256') != observation['sourceSha256']):
                        raise ValueError(kind + '_binding_changed')
                if row['label'] and (row['label'].get('basis') != 'human_adjudicated'
                        or row['label'].get('choice') not in CHOICES
                        or row['label'].get('stratum') not in {'ordinary', 'critical_safety', 'critical_authorization'}
                        or not isinstance(row['label'].get('evidenceSha256'), str)
                        or not re.fullmatch('[0-9a-f]{64}', row['label']['evidenceSha256'])):
                    raise ValueError('label_contract_changed')
                if row['outcome']:
                    outcome = row['outcome']
                    if outcome.get('outcome') not in {'accepted', 'rejected', 'undetermined'}:
                        raise ValueError('outcome_contract_changed')
                    if outcome['outcome'] == 'accepted' and not (
                            outcome.get('checksPassed') is True and outcome.get('reviewPassed') is True
                            and type(outcome.get('criticalFailureCount')) is int and outcome['criticalFailureCount'] == 0
                            and type(outcome.get('qualityScore')) is int and 0 <= outcome['qualityScore'] <= 100
                            and isinstance(outcome.get('rubricSha256'), str)
                            and re.fullmatch('[0-9a-f]{64}', outcome['rubricSha256'])):
                        raise ValueError('outcome_acceptance_invalid')
        except (OSError, ValueError, KeyError, TypeError) as exc:
            row.update(bucket='held', reason=failure_reason(exc),
                       armA=None, armB=None, inheritedArmB=None)
        rows.append(row)
    return rows


def packet(rows, limit=10):
    if type(limit) is not int or not 1 <= limit <= 10:
        raise ValueError('review packet limit must be 1..10')
    groups = {}
    for row in rows:
        if row['label'] or row['bucket'] == 'excluded':
            continue
        reason = ('context_hold' if row['bucket'] in {'held', 'missing', 'unknown'} else
                  'pending_score' if row['result'] is None else
                  'scoring_unavailable' if row['result'].get('status') != 'shadow' else
                  'abstention' if row['armB'] is None and row['result'].get('reasonCode') == 'below_threshold' else
                  'scoring_unavailable' if row['armB'] is None else
                  'baseline_pending' if row['armA'] is None else
                  'disagreement' if row['armA'] != row['armB'] else 'agreement')
        observation = row['observation'] or {}
        fingerprint = observation.get('requestSha256') or digest(canonical({
            'bucket': row['bucket'], 'reason': row['reason'], 'context': {
                k: (row['context'] or {}).get(k) for k in ('eventKind', 'action', 'domain', 'exclusions')}}))
        key = (reason, fingerprint, observation.get('sourceSha256'))
        groups.setdefault(key, []).append(row)
    strata = {key: [] for key in ('disagreement', 'scoring_unavailable', 'abstention', 'agreement', 'baseline_pending', 'context_hold', 'pending_score')}
    for (reason, fingerprint, source), members in sorted(groups.items(), key=lambda pair: str(pair[0])):
        representative = min(members, key=lambda r: r['id'])
        strata[reason].append({'opportunityId': representative['id'], 'sourceSha256': source,
            'reason': reason, 'holdReason': representative['reason'] if reason == 'context_hold' else None,
            'bucket': representative['bucket'], 'armA': representative['armA'], 'armB': representative['armB'],
            'state': (representative['observation'] or {}).get('request', {}).get('state') if (representative['observation'] or {}).get('request') else None,
            'inputSha256': fingerprint, 'duplicateCount': len(members),
            'opportunityIds': sorted(r['id'] for r in members), 'requires': 'human original-context review',
            'basis': 'assistant_triage_not_human_label'})
    items = []
    while len(items) < limit and any(strata.values()):
        for values in strata.values():
            if values and len(items) < limit:
                items.append(values.pop(0))
    return {'schema': SCHEMA, 'items': items, 'limit': limit,
            'rawUnreviewedCount': sum(not r['label'] for r in rows),
            'candidateRawCount': sum(len(v) for v in groups.values()), 'distinctGroups': len(groups),
            'omittedGroups': len(groups) - len(items),
            'sampling': 'deterministic_stratified_representatives_not_population_estimate'}



def valid_measurement(value):
    required = {'schema', 'opportunityId', 'basis', 'executedVariant', 'observedAt',
                'bindingStatus', 'reasonCode', 'sessionHash', 'sourceSha256',
                'receiptSourceSha256', 'taskRootId', 'status', 'exitCode', 'cleanupStatus',
                'durationMs', 'stdoutSha256', 'stderrSha256', 'outputComplete',
                'forwardTruncated', 'measurementSourceSha256'}
    if (set(value) != required or value.get('schema') != 'rhize-workflow-check-measurement-v2'
            or value.get('basis') != 'automatic_artifact' or value.get('executedVariant') != 'A_incumbent'
            or value.get('bindingStatus') != 'bound' or value.get('reasonCode') is not None):
        return False
    for key in ('opportunityId', 'sessionHash', 'sourceSha256', 'receiptSourceSha256',
                'taskRootId', 'stdoutSha256', 'stderrSha256', 'measurementSourceSha256'):
        if not isinstance(value[key], str) or not re.fullmatch('[0-9a-f]{64}', value[key]):
            return False
    try:
        if not isinstance(value['observedAt'], str) or datetime.fromisoformat(value['observedAt']).tzinfo is None:
            return False
    except ValueError:
        return False
    if (type(value['durationMs']) not in (int, float) or not math.isfinite(value['durationMs'])
            or value['durationMs'] < 0 or type(value['outputComplete']) is not bool
            or type(value['forwardTruncated']) is not bool
            or (value['exitCode'] is not None and type(value['exitCode']) is not int)):
        return False
    status, cleanup, exit_code = value['status'], value['cleanupStatus'], value['exitCode']
    if status == 'completed':
        return cleanup == 'not_required' and exit_code is not None and value['outputComplete']
    if value['outputComplete'] is not False:
        return False
    if status == 'launch_failed':
        return cleanup == 'not_required' and exit_code is None
    if status == 'timeout':
        return cleanup in {'completed', 'failed'} and (cleanup != 'completed' or exit_code is not None)
    if status == 'interrupted':
        return cleanup in {'completed', 'failed', 'not_required'} and (cleanup != 'not_required' or exit_code is None)
    return False

def measurement_summary(root, rows):
    from decision_pilot import inventory
    bound = {r['id']: r for r in rows if r['bucket'] in {'eligible', 'excluded'} and r['observation']}
    records = inventory(root / 'v2/measurements')
    matched, held = [], 0
    for _, value in records:
        row = bound.get(value.get('opportunityId'))
        if (not row or not valid_measurement(value)
                or value['sessionHash'] != row['receipt']['sessionHash']
                or value['sourceSha256'] != row['observation']['sourceSha256']
                or value['taskRootId'] != row['context']['taskRootId']
                or value['receiptSourceSha256'] != row['context']['sourceBindingSha256']):
            held += 1
            continue
        matched.append(value)
    return {'basis': 'automatic_artifact', 'executedVariant': 'A_incumbent', 'records': len(records),
            'boundRecords': len(matched), 'heldOrUnboundRecords': held,
            'taskRootsWithChecks': len({v['taskRootId'] for v in matched}),
            'completedChecks': sum(v.get('status') == 'completed' for v in matched),
            'failedChecks': sum(type(v.get('exitCode')) is int and v['exitCode'] != 0 for v in matched),
            'timeouts': sum(v.get('status') == 'timeout' for v in matched),
            'interrupted': sum(v.get('status') == 'interrupted' for v in matched),
            'launchFailed': sum(v.get('status') == 'launch_failed' for v in matched),
            'measuredCheckDurationMs': sum(v['durationMs'] for v in matched if type(v.get('durationMs')) in (int, float)),
            'acceptanceEstablished': False, 'taskUsageEstablished': False}


def context_diagnostics(receipts, rows):
    """Count source-bound capture failures without exposing payloads or error text."""
    from workflow_task_context import read_evidence, source_binding
    result = {}
    allowed = HELD_REASONS | {'context_input_unavailable', 'invalid_context_input',
                             'request_capture_unavailable', 'request_context_unavailable',
                             'observer_source_unverified', 'context_missing_before_decision', 'native_binding_changed',
                             'OSError', 'ValueError', 'KeyError', 'TypeError'}
    for directory, schema in (('task-context-diagnostics', 'rhize-workflow-context-diagnostic-v2'),
                              ('task-context-holds', 'rhize-workflow-context-hold-v2')):
        summary = {'records': 0, 'events': 0, 'invalidRecords': 0, 'overflowRecords': 0, 'reasons': {}}
        for row in rows:
            path = receipts.parent / directory / (row['id'] + '.json')
            if not path.exists() and not path.is_symlink():
                continue
            try:
                value = json.loads(read_evidence(path, 131072))
                if (not isinstance(value, dict) or value.get('schemaVersion') != schema
                        or value.get('opportunityId') != row['id']
                        or value.get('sourceBindingSha256') != source_binding(row['receipt'])
                        or not isinstance(value.get('events'), list) or not 1 <= len(value['events']) <= 64
                        or set(value) - {'schemaVersion', 'opportunityId', 'sourceBindingSha256', 'events', 'additionalConflicts'}
                        or ('additionalConflicts' in value and type(value['additionalConflicts']) is not bool)):
                    raise ValueError('invalid_diagnostic')
                for event in value['events']:
                    if (not isinstance(event, dict) or set(event) != {'reason', 'attemptSha256', 'recordedAt'}
                            or not isinstance(event['reason'], str)
                            or not isinstance(event['attemptSha256'], str)
                            or not re.fullmatch('[0-9a-f]{64}', event['attemptSha256'])
                            or not isinstance(event['recordedAt'], str)
                            or datetime.fromisoformat(event['recordedAt']).tzinfo is None):
                        raise ValueError('invalid_diagnostic')
            except (OSError, ValueError, KeyError, TypeError, RecursionError):
                summary['invalidRecords'] += 1
                continue
            summary['records'] += 1
            summary['overflowRecords'] += value.get('additionalConflicts') is True
            summary['events'] += len(value['events'])
            for event in value['events']:
                reason = event['reason'] if event['reason'] in allowed else 'other'
                summary['reasons'][reason] = summary['reasons'].get(reason, 0) + 1
        result[directory] = summary
    return result


def collection_funnel(receipts, rows, measurements):
    """Raw receipts are events; only eligible roots are routing-decision tasks."""
    from workflow_task_context import EVENT_KINDS
    current = source_digest()
    def source_for(row):
        value = (row['observation'] or {}).get('sourceSha256')
        if value is None:
            return 'missing'
        return value if isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) else 'invalid'

    def counts(members):
        eligible = [r for r in members if r['bucket'] == 'eligible']
        return {'rawEvents': len(members),
                'contextCapturedEvents': sum(r['context'] is not None for r in members),
                'eligibleDecisionEvents': len(eligible),
                'eligibleTaskRoots': len({r['context']['taskRootId'] for r in eligible}),
                'operationalExcludedEvents': sum(r['bucket'] == 'excluded' and r['reason'] == 'operational_event' for r in members),
                'continuationEvents': sum(r['bucket'] == 'excluded' and r['reason'] == 'continuation_of_existing_task' for r in members),
                'preboundExcludedEvents': sum(r['bucket'] == 'excluded' and r['reason'] == 'prebound_routine' for r in members),
                'missingContextEvents': sum(r['bucket'] == 'missing' for r in members),
                'unknownIntentEvents': sum(r['bucket'] == 'unknown' for r in members),
                'heldEvents': sum(r['bucket'] == 'held' for r in members),
                'sourceChangedEvents': sum(r['reason'] in {'source_changed', 'parent_source_changed'} for r in members),
                'baselineTaskRoots': len({r['context']['taskRootId'] for r in eligible if r['armA'] is not None}),
                'shadowScoredTaskRoots': len({r['context']['taskRootId'] for r in eligible if r['armB'] is not None}),
                'comparableRoutingTaskRoots': len({r['context']['taskRootId'] for r in eligible if r['armA'] is not None and r['armB'] is not None}),
                'outcomeTaskRoots': len({r['context']['taskRootId'] for r in eligible if r['outcome'] is not None})}

    hosts = {host: [] for host in ('claude', 'codex', 'unknown')}
    events = {kind: [] for kind in sorted(EVENT_KINDS)}
    events['missing'] = []
    sources = {}
    hold_reasons = {}
    for row in rows:
        host = row['receipt'].get('host')
        hosts[host if host in hosts else 'unknown'].append(row)
        kind = (row['context'] or {}).get('eventKind')
        events[kind if kind in EVENT_KINDS else 'missing'].append(row)
        sources.setdefault(source_for(row), []).append(row)
        if row['bucket'] == 'held':
            reason = row['reason'] if row['reason'] in HELD_REASONS else 'other'
            hold_reasons[reason] = hold_reasons.get(reason, 0) + 1
    return {'schema': 'rhize-workflow-collection-funnel-v1', **counts(rows),
            'eventDenominator': 'rawEvents', 'taskDenominator': 'eligibleTaskRoots',
            'contextCaptureDefinition': 'validated context binding; a later source hold is separate',
            'byHost': {key: counts(values) for key, values in hosts.items()},
            'byEventKind': {key: counts(values) for key, values in events.items()},
            'bySource': {key: {'sourceStatus': 'current' if key == current else key if key in {'missing', 'invalid'} else 'historical',
                              **counts(values)} for key, values in sorted(sources.items())},
            'heldReasons': hold_reasons, 'captureDiagnostics': context_diagnostics(receipts, rows),
            'allBoundContextRootsWithChecks': measurements['taskRootsWithChecks'],
            'measurementTaskDenominator': 'bound eligible and excluded context roots',
            'measurementReportField': 'measurements', 'nativeOriginVerified': 0, 'nativeOriginUnknown': len(rows),
            'executedVariant': 'A_incumbent', 'shadowVariant': 'B_local_laya',
            'labelReadinessReport': 'separate taxonomy policy report',
            'claimScope': 'current-source eligible decision roots; historical sources remain held; routing comparisons are not causal outcome comparisons'}


def report(root, receipts, rows=None):
    rows = joined(root, receipts) if rows is None else rows
    eligible = [r for r in rows if r['bucket'] == 'eligible']
    scored = [r for r in eligible if r['armB'] is not None]
    compared = [r for r in scored if r['armA'] is not None]
    labeled = [r for r in eligible if r['label']]
    reasons = {}
    for row in rows:
        reasons[row['reason']] = reasons.get(row['reason'], 0) + 1
    outcomes = [r['outcome'] for r in eligible if r['outcome']]
    latencies = sorted(r['result']['latencyMs'] for r in scored)
    unavailable = {}
    for row in eligible:
        if (row['result'] or {}).get('status') == 'unavailable':
            reason = row['result'].get('reasonCode', 'unknown')
            unavailable[reason] = unavailable.get(reason, 0) + 1
    measurements = measurement_summary(root, rows)
    return {'schema': SCHEMA, 'mode': 'shadow', 'rawEvents': len(rows),
            **{bucket: sum(r['bucket'] == bucket for r in rows) for bucket in ('eligible', 'excluded', 'held', 'unknown', 'missing')},
            'reasons': reasons, 'nativeOriginVerified': 0, 'nativeOriginUnknown': len(rows),
            'observations': sum(r['observation'] is not None for r in rows),
            'missingObservations': sum(r['observation'] is None for r in rows),
            'nativeStops': sum(r['stop'] is not None for r in rows),
            'inheritedRecommendations': sum(r['inheritedArmB'] is not None for r in rows),
            'heldLabels': sum(r['label'] is not None and r['bucket'] != 'eligible' for r in rows),
            'byHost': {host: sum(r['receipt']['host'] == host for r in rows) for host in ('claude','codex','unknown')},
            'byDomain': {domain: sum((r['context'] or {}).get('domain') == domain for r in eligible)
                         for domain in ('content','software','operations','general')},
            'sourceCohorts': {source: sum((r['observation'] or {}).get('sourceSha256','missing') == source for r in rows)
                              for source in sorted({(r['observation'] or {}).get('sourceSha256','missing') for r in rows})},
            'contextBasis': 'agent_asserted', 'armABasis': 'operator_reported',
            'labelBasis': 'human_adjudicated', 'executedVariant': 'A_incumbent', 'shadowVariant': 'B_local_laya',
            'scored': len(scored), 'missingScores': len(eligible)-len(scored),
            'pendingScores': sum(r['result'] is None for r in eligible), 'unavailableReasons': unavailable,
            'inferenceLatencyP95Ms': latencies[min(len(latencies)-1, int(len(latencies)*.95))] if latencies else None,
            'localInputTokens': sum(r['result']['usage']['input_tokens'] for r in scored) if scored else None,
            'localOutputTokens': sum(r['result']['usage']['output_tokens'] for r in scored) if scored else None,
            'baselineRecorded': sum(r['armA'] is not None for r in eligible),
            'comparisonCount': len(compared), 'disagreements': sum(r['armA'] != r['armB'] for r in compared),
            'humanLabels': len(labeled), 'labeledScoredCount': sum(r['armB'] is not None for r in labeled),
            'armBCorrectCount': sum(r['armB'] == r['label']['choice'] for r in labeled),
            'accuracyDenominator': 'labeledScoredCount',
            'outcomes': len(outcomes), 'missingOutcomes': len(eligible)-len(outcomes),
            'acceptedTasks': sum(o['outcome'] == 'accepted' for o in outcomes),
            'checksEvidenceRecorded': sum(o.get('checksPassed') is not None for o in outcomes),
            'reviewEvidenceRecorded': sum(o.get('reviewPassed') is not None for o in outcomes),
            'outcomeBasis': 'operator_reported',
            'completeAgentUsage': sum(all(type((o.get('usage') or {}).get(k)) is int for k in ('input_tokens','output_tokens')) for o in outcomes),
            'measurements': measurements, 'collectionFunnel': collection_funnel(receipts, rows, measurements),
            'claimScope': 'separate eligible routing coverage; no causal task benefit or native origin accuracy'}


def export_cases(root, receipts):
    cases = []
    for row in joined(root, receipts):
        if row['bucket'] != 'eligible' or not row['label'] or not row['observation']:
            continue
        label, observation, context = row['label'], row['observation'], row['context']
        if label.get('basis') != 'human_adjudicated':
            continue
        request = observation['request']
        input_sha = digest(canonical({'state': request['state'], 'questions': request['questions']}))
        keys = ['session:' + row['receipt']['sessionHash'], 'task:' + context['taskRootId'],
                'input:' + input_sha, 'prompt:' + row['receipt']['promptHash']]
        cases.append({'case_id': row['id'], 'group_id': input_sha, 'grouping_keys': sorted(keys),
            'normalization_version': NORMALIZATION, 'cohort_version': 'workflow-pilot-v2',
            'collection_source_sha256': observation['sourceSha256'], 'input_sha256': input_sha,
            'task_family': context['domain'], 'host': row['receipt']['host'],
            'decision_type': 'workflow_fit', 'stratum': label['stratum'], 'label_source': label['evidenceSha256'],
            'adjudicated': True, 'state': request['state'], 'questions': request['questions'],
            'candidate_ids': list(CHOICES), 'routing_choice': label['choice'], 'arm_a_choice': row['armA'],
            'labels': {f'c{i}': choice == label['choice'] for i, choice in enumerate(CHOICES)},
            **({'arm_a': {f'c{i}': choice == row['armA'] for i, choice in enumerate(CHOICES)}} if row['armA'] else {})})
    if len({c['collection_source_sha256'] for c in cases}) > 1:
        raise ValueError('mixed_collection_sources')
    return cases
