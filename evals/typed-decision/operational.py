#!/usr/bin/env python3
"""Development-only deadline replay and grouped menu-order panels; never a promotion gate."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import time
import urllib.error

import research


STATUSES = ('ok', 'late', 'timeout', 'invalid', 'busy', 'unavailable')


def menu_panel(rows, limit=2400):
    """Rotate the same choices; related variants retain their original independent group."""
    variants = []
    for row in rows:
        if row.get('cohort_version') in research.PILOT_COHORTS or len(row['questions']) != 1:
            raise ValueError('order panel requires one generic choice question per case')
        name, question = next(iter(research.questions_for(row, {}).items()))
        if question['type'] != 'choice' or row.get('menu_source_sha256'):
            raise ValueError('order panel requires original choice cases')
        order = list(question['criteria'])
        source = research.digest(row)
        for index in range(len(order)):
            if len(variants) >= limit:
                raise ValueError('menu panel exceeds request ceiling')
            rotated = order[index:] + order[:index]
            variants.append({**row, 'case_id': research.digest([row['case_id'], rotated]),
                             'menu_source_sha256': source, 'candidate_orders': {name: rotated}})
    return variants


def _status(exc):
    if isinstance(exc, urllib.error.HTTPError):
        return 'busy' if exc.code in (429, 503) else 'unavailable'
    if isinstance(exc, TimeoutError) or (isinstance(exc, urllib.error.URLError)
                                       and isinstance(exc.reason, TimeoutError)):
        return 'timeout'
    if isinstance(exc, (ValueError, KeyError, TypeError)):
        return 'timeout' if isinstance(exc, ValueError) and str(exc) == 'timeout' else 'invalid'
    return 'unavailable'


def run(rows, candidate, call, deadline_ms, *, condition='unspecified', runtime_sha256=None):
    if type(deadline_ms) not in (int, float) or not math.isfinite(deadline_ms) or not 0 < deadline_ms <= 20000:
        raise ValueError('deadline must be finite and in (0, 20000] milliseconds')
    if not rows or len(rows) > 2400 or condition not in ('cold', 'warm', 'mixed', 'unspecified'):
        raise ValueError('invalid corpus size or condition')
    research.validate_candidate(candidate, rows)
    cases, successful = [], []
    menus = defaultdict(list)
    for row in rows:
        elapsed, measured, response = None, None, None
        def timed(request):
            nonlocal elapsed, measured, response
            started = time.perf_counter()
            try:
                response, measured = call(request)
                if type(measured) not in (int, float) or not math.isfinite(measured) or measured < 0:
                    raise ValueError('invalid latency')
                return response, measured
            finally:
                elapsed = (time.perf_counter() - started) * 1000
        quality = None
        try:
            quality = research.evaluate([row], candidate, timed)
            latency = max(elapsed, measured)
            status = 'ok' if latency <= deadline_ms else 'late'
        except (OSError, ValueError, KeyError, TypeError) as exc:
            status = _status(exc)
            latency = elapsed
        correct = status == 'ok' and quality['accuracy'] == 1
        item = {'case_sha256': research.digest(row['case_id']), 'group_sha256': research.digest(row['group_id']),
                'status': status, 'elapsed_ms': latency, 'censored': status == 'timeout',
                'critical': row['stratum'].startswith('critical'),
                'correct_before_deadline': correct,
                'abstained': quality['abstention_rate'] > 0 if quality else None}
        if status == 'ok':
            successful.append(latency)
        source = row.get('menu_source_sha256')
        if source and status == 'ok' and not item['abstained']:
            # Panels contain one generic choice. Compare identities only, never persist response text.
            prediction = next(iter(response['answers'].values()))['choice']
            semantics = research.digest({k: row[k] for k in ('state', 'questions', 'labels')})
            menus[(row['group_id'], source, semantics)].append(research.digest(prediction))
        cases.append(item)
    successful.sort()
    comparable = [values for values in menus.values() if len(values) > 1]
    counts = Counter(item['status'] for item in cases)
    return {'schema': 'rhize-operational-decision-v1', 'metrics_schema': research.METRICS_SCHEMA,
            'corpus_sha256': research.digest(rows), 'candidate_sha256': research.digest(candidate),
            'deadline_ms': deadline_ms, 'condition': condition, 'condition_basis': 'operator_declared',
            'runtime_evidence_sha256': runtime_sha256, 'concurrency': 'sequential',
            'timing_scope': 'shared client call including identity probe and response handling; excludes host scheduling and grading',
            'attempts': len(cases), 'independent_groups': len({r['group_id'] for r in rows}),
            'statuses': {name: counts[name] for name in STATUSES},
            'correct_before_deadline': sum(c['correct_before_deadline'] for c in cases),
            'deadline_yield': sum(c['correct_before_deadline'] for c in cases) / len(cases),
            'answer_coverage': sum(c['status'] == 'ok' and not c['abstained'] for c in cases) / len(cases),
            'critical_cases': sum(c['critical'] for c in cases),
            'critical_misses': sum(c['critical'] and not c['correct_before_deadline'] for c in cases),
            'unsafe_actions': None,
            'successful_latency_ms': {'n': len(successful),
                                     'p50': successful[len(successful) // 2] if successful else None,
                                     'p95': successful[min(len(successful) - 1, int(len(successful) * .95))] if successful else None},
            'menu_order': {'comparable_sources': len(comparable),
                           'disagreements': sum(len(set(values)) > 1 for values in comparable)},
            'cases': cases, 'claim_scope': 'development replay; no native-host, causal benefit or promotion claim'}


def _file(path, maximum):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > maximum:
        raise ValueError('input must be a bounded regular file')
    return path.read_bytes()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for command in ('run', 'menu-panel'):
        item = sub.add_parser(command)
        item.add_argument('--cases', type=Path, required=True, help='development cases only; never locked holdout')
        item.add_argument('--output', type=Path, required=True, help='new private output file')
        item.add_argument('--max-requests', type=int, default=2400)
        if command == 'run':
            item.add_argument('--candidate', type=Path, required=True, help='one candidate JSON object')
            item.add_argument('--deadline-ms', type=float, required=True, help='actual caller deadline; no runtime change')
            item.add_argument('--condition', choices=('cold', 'warm', 'mixed', 'unspecified'), required=True)
            item.add_argument('--runtime-evidence', type=Path, required=True, help='pinned checkpoint, source, hardware/dtype/queue evidence')
            item.add_argument('--base-url', default='http://127.0.0.1:8000')
    args = parser.parse_args()
    if not 1 <= args.max_requests <= 2400:
        parser.error('max-requests must be 1..2400')
    if args.output.exists() or args.output.is_symlink():
        parser.error('output must be a new file')
    _file(args.cases, 16 * 1024 * 1024)
    rows = research.read_jsonl(args.cases)
    if len(rows) > args.max_requests:
        parser.error('request ceiling exceeded')
    if args.command == 'menu-panel':
        content = ''.join(json.dumps(row, sort_keys=True) + '\n' for row in menu_panel(rows, args.max_requests))
    else:
        candidate = json.loads(_file(args.candidate, 65536))
        runtime = _file(args.runtime_evidence, 1048576)
        if not isinstance(json.loads(runtime), dict):
            parser.error('runtime evidence must be a JSON object')
        result = run(rows, candidate, lambda request: research.local_call(
            args.base_url, request, timeout=args.deadline_ms / 1000), args.deadline_ms,
            condition=args.condition, runtime_sha256=hashlib.sha256(runtime).hexdigest())
        content = json.dumps(result, indent=2) + '\n'
    args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if args.output.parent.is_symlink():
        parser.error('symlink output parent refused')
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as output:
        output.write(content)
    print(json.dumps({'status': 'written', 'sha256': hashlib.sha256(content.encode()).hexdigest()}))


if __name__ == '__main__':
    main()
