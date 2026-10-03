#!/usr/bin/env python3
"""Private workflow shadow collection. Observations never authorize execution."""
from __future__ import annotations

import argparse
import fcntl
import itertools
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from datetime import datetime

from workflow_selection import DEFAULT_ROOT, digest, locked_update, read_json, detect_host

SCHEMA = 'rhize-decision-pilot-v1'
CHOICES = ('content', 'general', 'none')
SIGNALS = frozenset('article resource documentation software planning workflow publish research review project simple'.split())
MAX_ROWS = 10000


def source_digest():
    paths = [Path(__file__), Path(__file__).with_name('workflow_selection.py'),
             Path(__file__).parent / 'context_experiments/typed_candidates.py',
             Path(__file__).parent / 'context_experiments/typed_relevance.py']
    return digest(b''.join(p.read_bytes() for p in paths))


def state_for(prompt, catalog):
    return {'schema': 'rhize-typed-candidates-v1', 'capability': 'skill_workflow',
            'sourceSha256': digest(json.dumps(catalog, sort_keys=True)),
            'taskSignals': sorted(set(re.findall(r'[a-z]+', prompt.lower())) & SIGNALS)[:8],
            'candidates': [
                {'id': 'content', 'hints': ['resource', 'article', 'content-engine'], 'protected': False},
                {'id': 'general', 'hints': ['repeatable', 'workflow', 'procedural-memory'], 'protected': False},
                {'id': 'none', 'hints': ['simple', 'no-match'], 'protected': False}], 'incumbentIds': []}


def save_once(root, identity, value):
    def update(old):
        if old is not None and old != value:
            raise ValueError('immutable record already exists')
        return (old, False) if old else (value, True)
    return locked_update(root, identity, update)[0]


def inventory(root):
    if root.is_symlink():
        raise ValueError('symlink inventory refused')
    paths = list(itertools.islice(root.glob('*.json'), MAX_ROWS + 1))
    if len(paths) > MAX_ROWS:
        raise ValueError('inventory ceiling exceeded; archive reviewed cohorts')
    rows = []
    for path in sorted(paths):
        if path.is_symlink():
            raise ValueError('symlink record refused')
        value = read_json(path)
        if not re.fullmatch('[0-9a-f]{64}', path.stem):
            raise ValueError('invalid record identity')
        rows.append((path.stem, value))
    return rows


def enqueue(prompt, receipt, root, spawn=True):
    from context_experiments.typed_candidates import build_request
    if root.is_symlink():
        raise ValueError('symlink pilot root refused')
    identity = receipt['opportunityId']
    state = state_for(prompt, receipt['catalog'])
    value = {'schema': SCHEMA, 'opportunityId': identity, 'host': receipt['host'],
             'sessionHash': receipt['sessionHash'], 'taskHash': receipt['taskHash'],
             'identityMode': receipt['identityMode'], 'createdAt': time.time(),
             'sourceSha256': source_digest(), 'state': state, 'request': build_request(state, 'typed-decisions')}
    # Idempotent delivery; preserve the first observation time/source on retries.
    locked_update(root / 'observations', identity, lambda old: (old, False) if old else (value, True))
    if spawn:
        try:
            subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--root', str(root), 'drain'],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True, close_fds=True)
        except OSError:
            pass  # Observation remains pending and is visible to report/heartbeat.


def enqueue_v2(context, receipt, root, spawn=True, receipts=None):
    from decision_pilot_v2 import enqueue
    return enqueue(context, receipt, root, spawn=spawn, receipts=receipts)


def drain(root, call=None, receipts=None, cohort=None):
    from context_experiments.typed_candidates import assess
    from context_experiments.typed_relevance import local_call
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if root.is_symlink():
        raise ValueError('symlink pilot root refused')
    fd = os.open(root / 'worker.lock', os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {'status': 'busy'}
        started, processed, source_held = time.monotonic(), 0, 0
        from decision_pilot_v2 import ensure_root, source_digest as v2_source_digest
        ensure_root(root)
        if cohort not in {None, 'v1', 'v2'}:
            raise ValueError('invalid drain cohort')
        observations = [(False, identity, value) for identity, value in inventory(root / 'observations')] if cohort != 'v2' else []
        if cohort != 'v1':
            observations += [(True, identity, value) for identity, value in inventory(root / 'v2/observations')]
        current_v2_source = v2_source_digest() if cohort != 'v1' else None
        for v2, identity, observation in observations:
            collection = root / 'v2' if v2 else root
            if (collection / 'results' / (identity + '.json')).exists():
                continue
            if v2 and observation.get('sourceSha256') != current_v2_source:
                # Other collection cohorts stay pending; this runtime must not seal their failure.
                source_held += 1
                continue
            if processed >= 20 or time.monotonic() - started > 45:
                break
            request_started = time.monotonic()
            try:
                if v2:
                    from decision_pilot_v2 import assess as assess_v2
                    result = assess_v2(observation, receipts or root.parent / 'receipts',
                                       call or (lambda url, request: local_call(url, request, timeout=5)), root=root)
                elif observation.get('schema') != SCHEMA or observation.get('sourceSha256') != source_digest():
                    raise ValueError('source_changed')
                elif not observation['state']['taskSignals']:
                    raise ValueError('insufficient_task_signals')
                elif not v2:
                    result = assess(observation['state'], 'typed-decisions', 'http://127.0.0.1:8000',
                                    call or (lambda url, request: local_call(url, request, timeout=5)))
            except (OSError, ValueError, KeyError, TypeError) as exc:
                from decision_pilot_v2 import failure_reason
                result = {'status': 'unavailable', 'variant': 'A_incumbent',
                          'reasonCode': failure_reason(exc) if v2 else (str(exc) if isinstance(exc, ValueError) and str(exc) in {'source_changed', 'insufficient_task_signals'} else type(exc).__name__), 'incumbentAltered': False,
                          'latencyMs': round((time.monotonic() - request_started) * 1000, 3), 'usage': None}
            save_once(collection / 'results', identity, {**result, 'opportunityId': identity,
                                                  'observedAt': time.time()})
            processed += 1
        return {'status': 'drained', 'processed': processed, 'sourceHeld': source_held}


def incumbent(receipt):
    selected = receipt.get('selection') or {}
    if selected.get('decision') in {'skip', 'no_match', 'candidate'}:
        return 'none'
    if selected.get('decision') in {'reuse', 'adapt'}:
        return 'content' if selected.get('workflow') in {'rhize-content-engine', 'content-engine', 'content-engine-local'} else 'general'
    return None


def joined(root, receipts):
    observed = dict(inventory(root / 'observations'))
    results = dict(inventory(root / 'results'))
    labels = dict(inventory(root / 'labels'))
    outcomes = dict(inventory(root / 'outcomes'))
    stops = dict(inventory(root / 'stops'))
    # Opportunity is written before enqueue, so failed enqueue remains in denominator.
    rows = []
    for identity, receipt in inventory(receipts):
        if receipt.get('decisionPilot') != 'shadow-v1':
            continue
        observation, result = observed.get(identity), results.get(identity)
        ranking = (result or {}).get('ranking') or []
        rows.append({'id': identity, 'receipt': receipt, 'observation': observation, 'result': result,
                     'armA': incumbent(receipt), 'armB': ranking[0]['candidateId'] if ranking else None,
                     'label': labels.get(identity), 'outcome': outcomes.get(identity), 'stop': stops.get(identity)})
    return rows


def legacy_report(root, receipts):
    rows = joined(root, receipts)
    valid = [r for r in rows if r['armB'] is not None]
    compared = [r for r in valid if r['armA'] is not None]
    labeled = [r for r in valid if r['label']]
    latency = [(r['result'] or {}).get('latencyMs') for r in rows]
    latency = sorted(x for x in latency if isinstance(x, (int, float)))
    outcome_rows = [r['outcome'] for r in rows if r['outcome']]
    metric = lambda key: [r[key] for r in outcome_rows if r[key] is not None]
    mean = lambda values: sum(values) / len(values) if values else None
    sources = {}
    for row in rows:
        source = (row['observation'] or {}).get('sourceSha256', 'missing')
        cohort = sources.setdefault(source, {'opportunities': 0, 'labeledScoredCount': 0, 'armBCorrectCount': 0})
        cohort['opportunities'] += 1
        if row['armB'] and row['label']:
            cohort['labeledScoredCount'] += 1
            cohort['armBCorrectCount'] += row['armB'] == row['label']['choice']
    return {'schema': SCHEMA, 'status': 'available' if receipts.is_dir() else 'unavailable',
            'mode': 'shadow', 'opportunities': len(rows), 'byHost': {host: sum(r['receipt']['host'] == host for r in rows) for host in ('claude', 'codex', 'unknown')},
            'missingObservations': sum(r['observation'] is None for r in rows),
            'pendingResults': sum(r['observation'] is not None and r['result'] is None for r in rows),
            'validResults': len(valid), 'unavailableResults': sum((r['result'] or {}).get('status') == 'unavailable' for r in rows),
            'comparisonCount': len(compared), 'disagreements': sum(r['armA'] != r['armB'] for r in compared),
            'sourceCohorts': sources, 'labelSampling': 'review_queue_enriched_not_population_estimate',
            'criticalReviewedCases': sum(r['label']['stratum'].startswith('critical_') for r in labeled),
            'criticalArmBMismatches': sum(r['label']['stratum'].startswith('critical_') and r['armB'] != r['label']['choice'] for r in labeled),
            'humanLabels': sum(r['label'] is not None for r in rows),
            'labeledScoredCount': len(labeled),
            'armBAccuracy': sum(r['armB'] == r['label']['choice'] for r in labeled) / len(labeled) if labeled else None,
            'armALabeledCount': sum(r['armA'] is not None for r in labeled),
            'armACorrectCount': sum(r['armA'] == r['label']['choice'] for r in labeled if r['armA'] is not None),
            'outcomes': len(outcome_rows),
            'acceptedTasks': sum(r['outcome'] == 'accepted' for r in outcome_rows),
            'rejectedTasks': sum(r['outcome'] == 'rejected' for r in outcome_rows),
            'meanQualityScore': mean(metric('qualityScore')), 'meanTaskWallMs': mean(metric('wallMs')),
            'meanReworkCount': mean(metric('reworkCount')),
            'terminatedWorkflows': sum(r['receipt'].get('terminalStatus') is not None for r in rows),
            'selectionPending': sum(r['receipt'].get('selection') is None for r in rows),
            'stopHealth': dict(inventory(root / 'health')),
            'localInputTokens': sum(r['result']['usage']['input_tokens'] for r in valid) if valid else None,
            'localOutputTokens': sum(r['result']['usage']['output_tokens'] for r in valid) if valid else None,
            'missingOutcomes': sum(r['outcome'] is None for r in rows),
            'nativeStops': sum(r['stop'] is not None for r in rows),
            'completeAgentUsage': sum(all(type(((r['outcome'] or {}).get('usage') or {}).get(k)) is int for k in ('input_tokens', 'output_tokens')) for r in rows),
            'localUsageMissing': sum(not isinstance((r['result'] or {}).get('usage'), dict) for r in rows),
            'latencyP95Ms': latency[min(len(latency) - 1, int(len(latency) * .95))] if latency else None,
            'claimScope': 'observational coverage and reviewed decision accuracy; no causal productivity claim'}


def report(root, receipts):
    from decision_pilot_v2 import joined as joined_v2, report as report_v2, packet
    legacy = legacy_report(root, receipts)
    rows = joined_v2(root, receipts)
    return {**legacy, 'legacyCohort': 'workflow-pilot-v1',
            'totalRawEvents': legacy['opportunities'] + len(rows),
            'v2Coverage': report_v2(root, receipts, rows), 'dailyPacket': packet(rows)}


def queue(root, receipts):
    items = []
    for row in joined(root, receipts):
        if row['label']:
            continue
        reason = ('missing_or_failed_score' if not row['armB'] else
                  'baseline_pending' if not row['armA'] else
                  'disagreement' if row['armA'] != row['armB'] else
                  'sampled_agreement' if int(row['id'][:8], 16) % 5 == 0 else None)
        if reason:
            items.append({'opportunityId': row['id'], 'host': row['receipt']['host'], 'reason': reason,
                          'sessionHash': row['receipt']['sessionHash'], 'taskHash': row['receipt']['taskHash'],
                          'armA': row['armA'], 'armB': row['armB'],
                          'state': (row['observation'] or {}).get('state'),
                          'requires': 'Human must inspect original task context; bounded signals alone may be insufficient.'})
    from decision_pilot_v2 import joined as joined_v2, packet
    return {'schema': SCHEMA, 'items': items, 'dailyPacket': packet(joined_v2(root, receipts))}


def bind_evidence(root, identity, evidence, kind, receipts=None):
    from decision_pilot_v2 import ensure_root
    ensure_root(root)
    v2_path = root / 'v2/observations' / (identity + '.json')
    if v2_path.is_symlink():
        raise ValueError('symlink observation refused')
    if v2_path.exists():
        from decision_pilot_v2 import validate_observation
        observation = read_json(v2_path)
        validate_observation(observation, receipts or root.parent / 'receipts', identity, require_current_source=True, root=root)
        if kind == 'labels' and observation['disposition']['eligible'] is not True:
            raise ValueError('only eligible routing decisions can receive v2 labels')
        root = root / 'v2'
    else:
        observation = read_json(root / 'observations' / (identity + '.json'))
    if evidence.is_symlink():
        raise ValueError('symlink evidence refused')
    value = read_json(evidence)
    if value.get('opportunityId') != identity or value.get('sourceSha256') != observation['sourceSha256']:
        raise ValueError('evidence must bind the exact opportunity and collection source')
    if kind == 'labels':
        required = {'opportunityId', 'sourceSha256', 'choice', 'reviewer', 'basis', 'stratum', 'reviewEvidenceSha256'}
        if set(value) != required or value['choice'] not in CHOICES or value['basis'] != 'human_adjudicated':
            raise ValueError('requires human-adjudicated label contract')
        if not isinstance(value['reviewer'], str) or not re.fullmatch('[A-Za-z0-9_-]{1,64}', value['reviewer']):
            raise ValueError('bounded human reviewer identity required')
        if value['stratum'] not in {'ordinary', 'critical_safety', 'critical_authorization'}:
            raise ValueError('invalid label stratum')
        if not re.fullmatch('[0-9a-f]{64}', value['reviewEvidenceSha256']):
            raise ValueError('review evidence digest required')
    else:
        required = {'opportunityId', 'sourceSha256', 'outcome', 'qualityScore', 'checksPassed', 'reviewPassed',
                    'criticalFailureCount', 'reworkCount', 'wallMs', 'usage', 'rubricSha256'}
        if set(value) != required or value['outcome'] not in {'accepted', 'rejected', 'undetermined'}:
            raise ValueError('invalid task outcome contract')
        for key in ('checksPassed', 'reviewPassed'):
            if value[key] is not None and type(value[key]) is not bool:
                raise ValueError('check/review evidence must be boolean or null')
        for key in ('qualityScore', 'criticalFailureCount', 'reworkCount', 'wallMs'):
            if value[key] is not None and (type(value[key]) is not int or value[key] < 0):
                raise ValueError('metrics must be nonnegative integers or null')
        if value['qualityScore'] is not None and value['qualityScore'] > 100:
            raise ValueError('quality score exceeds 100')
        if not isinstance(value['usage'], dict) or set(value['usage']) != {'input_tokens', 'output_tokens'}:
            raise ValueError('explicit input/output usage required; use null when unavailable')
        for count in value['usage'].values():
            if count is not None and (type(count) is not int or count < 0):
                raise ValueError('invalid usage')
        if value['rubricSha256'] is not None and not re.fullmatch('[0-9a-f]{64}', value['rubricSha256']):
            raise ValueError('invalid rubric digest')
        if value['outcome'] == 'accepted' and not (value['checksPassed'] is True and value['reviewPassed'] is True
                and value['criticalFailureCount'] == 0 and value['qualityScore'] is not None and value['rubricSha256']):
            raise ValueError('accepted requires scored quality, checks, independent review, no critical failures and rubric')
    save_once(root / kind, identity, {**value, 'evidenceSha256': digest(evidence.read_bytes())})
    return {'status': 'recorded', 'opportunityId': identity, 'kind': kind}


def stop(root, receipts, payload, host):
    session = payload.get('session_id') or payload.get('thread_id')
    turn = payload.get('turn_id') or payload.get('turnId') or payload.get('prompt_id') or payload.get('event_id')
    if not isinstance(session, str) or not isinstance(turn, str) or host == 'unknown':
        return {'status': 'unavailable', 'reason': 'exact_native_turn_required'}
    identity = digest(host + ':' + session + ':' + turn)
    path = receipts / (identity + '.json')
    if not path.is_file() or read_json(path).get('decisionPilot') not in {'shadow-v1', 'shadow-v2'}:
        return {'status': 'unavailable', 'reason': 'no_matching_pilot_opportunity'}
    receipt = read_json(path)
    if receipt.get('decisionPilot') == 'shadow-v2':
        root = root / 'v2'
    elapsed = max(0, round((time.time() - datetime.fromisoformat(receipt['observedAt']).timestamp()) * 1000))
    value = {'opportunityId': identity, 'basis': 'native_stop_observed', 'accepted': None, 'elapsedMs': elapsed}
    locked_update(root / 'stops', identity, lambda old: (old, False) if old else (value, True))
    return {'status': 'recorded', 'opportunityId': identity}


def export_cases(root, receipts, output, cohort='v1'):
    if cohort not in {'v1', 'v2'}:
        raise ValueError('invalid export cohort')
    if cohort == 'v2':
        from decision_pilot_v2 import export_cases as export_v2
        cases = export_v2(root, receipts)
    else:
        cases = []
    for row in joined(root, receipts) if cohort == 'v1' else []:
        if not row['label'] or not row['observation']:
            continue
        label = row['label']
        request = row['observation']['request']
        cases.append({'case_id': row['id'], 'group_id': row['receipt']['sessionHash'],
                      'decision_type': 'workflow_fit', 'stratum': label['stratum'],
                      'label_source': label['evidenceSha256'], 'adjudicated': True,
                      'state': request['state'], 'questions': request['questions'],
                      'labels': {f'c{i}': choice == label['choice'] for i, choice in enumerate(CHOICES)},
                      **({'arm_a': {f'c{i}': choice == row['armA'] for i, choice in enumerate(CHOICES)}} if row['armA'] else {})})
    if not cases:
        return {'status': 'held', 'reason': 'no_human_adjudicated_cases', 'count': 0}
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(output, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'w') as stream:
        for case in cases:
            stream.write(json.dumps(case, sort_keys=True) + '\n')
    return {'status': 'exported', 'count': len(cases), 'sha256': digest(output.read_bytes())}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root', type=Path, default=DEFAULT_ROOT / 'pilot')
    ap.add_argument('--receipts', type=Path, default=DEFAULT_ROOT / 'receipts')
    sub = ap.add_subparsers(dest='command', required=True)
    for command in ('report', 'queue', 'stop'):
        sub.add_parser(command)
    sp = sub.add_parser('drain'); sp.add_argument('--cohort', choices=('v1', 'v2'))
    for command in ('adjudicate', 'outcome'):
        sp = sub.add_parser(command); sp.add_argument('--id', required=True); sp.add_argument('--evidence', type=Path, required=True)
    sp = sub.add_parser('export'); sp.add_argument('--out', type=Path, required=True); sp.add_argument('--cohort', choices=('v1', 'v2'), default='v1')
    args = ap.parse_args()
    try:
        if getattr(args, 'id', None) and not re.fullmatch('[0-9a-f]{64}', args.id):
            raise ValueError('invalid opportunity id')
        if args.command == 'drain':
            result = drain(args.root, receipts=args.receipts, cohort=args.cohort)
        elif args.command == 'report':
            result = report(args.root, args.receipts)
        elif args.command == 'queue':
            result = queue(args.root, args.receipts)
        elif args.command in {'adjudicate', 'outcome'}:
            result = bind_evidence(args.root, args.id, args.evidence, 'labels' if args.command == 'adjudicate' else 'outcomes', receipts=args.receipts)
        elif args.command == 'export':
            result = export_cases(args.root, args.receipts, args.out, cohort=args.cohort)
        else:
            config = read_json(DEFAULT_ROOT / 'config.json')
            if config.get('decisionPilot') not in ({'enabled': True, 'mode': 'shadow'}, {'enabled': True, 'mode': 'shadow', 'cohort': 'v2'}):
                return 0
            raw = sys.stdin.buffer.read(65537)
            if len(raw) > 65536:
                raise ValueError('input budget exceeded')
            payload = json.loads(raw)
            result = stop(args.root, args.receipts, payload, detect_host(payload, os.environ))
            locked_update(args.root / 'health', digest('stop:' + detect_host(payload, os.environ)),
                          lambda old: ({**result, 'at': time.time()}, True))
            return 0  # Stop observations never request continuation or emit task text.
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        if args.command == 'stop':
            return 0
        print(json.dumps({'status': 'unavailable', 'reason': type(exc).__name__, 'detail': str(exc)}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
