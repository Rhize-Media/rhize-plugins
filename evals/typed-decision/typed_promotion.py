#!/usr/bin/env python3
"""advise-v1 promotion gate: Laya must beat the frozen majority-class baseline (plan §3, §11).

Pure functions generic over decisions (stdlib only, Python 3.9 compatible). `evaluate` is the paired sign test
on a reserved promotion cohort, `demotion` the rolling live check, `run_attempt` the ledger-bound attempt flow
(reserve before evaluating, one consumed verdict per cohort, alpha spent per decision). The gate never writes
the registry; the caller does, through decision_registry.mutate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_SCRIPTS = str(Path(__file__).resolve().parents[2] / 'rhize-context-manager/scripts')
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)
from typed_decisions import advise_ledger, locked_io  # noqa: E402
from typed_decisions.cohorts import alpha_for_attempt, cp_lower  # noqa: E402

RECEIPT_SCHEMA = 'rhize-advise-baseline-receipt-v1'
PRIOR_SHARE_FLOOR = 0.10      # classes below this share of the tuning split are not scored
MIN_CLASS_CASES = 3
MIN_CLASS_RECALL = 0.5
DEFAULT_GATE = {'minCohort': 30, 'alphaBase': 0.10, 'minCoverage': 0.9, 'minCriticalCases': 0,
                'demote': {'freshLabels': 10, 'window': 30, 'consecutive': 2}}
CRITICAL_MIN_CASES = 10


def sha256(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def split_of(group):
    """Stable session-group split: promotion 1/3, tuning 2/3 (plan §3.1)."""
    return 'promotion' if int(hashlib.sha256(('split:' + str(group)).encode()).hexdigest(), 16) % 3 == 2 else 'tuning'


def majority(labels):
    """Most common label; ties resolve to the lexicographically smallest."""
    counts = {}
    for label in labels:
        counts[label] = counts.get(label, 0) + 1
    return sorted(counts, key=lambda name: (-counts[name], name))[0] if counts else None


def _answered(case):
    return case.get('status') == 'ok' and case.get('choice') is not None


def _laya_right(case):
    return _answered(case) and case['choice'] == case['label']


def evaluate(cases, *, baseline, alpha, prior, min_cohort, min_coverage, critical=False, min_critical=CRITICAL_MIN_CASES):
    """Gate one reserved promotion cohort. case = {id, group, label, choice, status, critical_if_wrong}.

    Laya is wrong on a non-ok status, an abstention (choice None) or a different choice. Returns
    {verdict, reasons, stats}; verdict is 'pass' only when every condition holds.
    """
    n = len(cases)
    right = sum(_laya_right(c) for c in cases)
    base_right = sum(baseline == c['label'] for c in cases)
    b = sum(_laya_right(c) and baseline != c['label'] for c in cases)
    c_ = sum(not _laya_right(c) and baseline == c['label'] for c in cases)
    coverage = sum(_answered(c) for c in cases) / n if n else 0.0
    lower = cp_lower(b, b + c_, alpha) if b + c_ > 0 else 0.0
    classes = sorted({c['label'] for c in cases})
    counts = {k: sum(c['label'] == k for c in cases) for k in classes}
    recall = {k: sum(_laya_right(c) for c in cases if c['label'] == k) / counts[k] for k in classes}
    balanced = sum(recall.values()) / len(classes) if classes else 0.0
    base_balanced = sum(float(k == baseline) for k in classes) / len(classes) if classes else 0.0
    critical_cases = sum(bool(c.get('critical_if_wrong')) for c in cases)
    critical_misses = sum(bool(c.get('critical_if_wrong')) and _answered(c) and c['choice'] != c['label'] for c in cases)
    total = float(sum(prior.values())) or 1.0
    scored = sorted(k for k, v in prior.items() if v / total >= PRIOR_SHARE_FLOOR)
    reasons = []
    if n < min_cohort:
        reasons.append('cohort_too_small')
    if len({c['group'] for c in cases}) < min_cohort:
        reasons.append('too_few_groups')
    if coverage < min_coverage:
        reasons.append('coverage_below_minimum')
    if b + c_ == 0:
        reasons.append('no_discordant_cases')
    elif not lower > 0.5:
        reasons.append('sign_test_not_significant')
    if not balanced > base_balanced:
        reasons.append('balanced_accuracy_not_above_baseline')
    for k in scored:
        if counts.get(k, 0) < MIN_CLASS_CASES:
            reasons.append('class_coverage:' + k)
        elif recall[k] < MIN_CLASS_RECALL:
            reasons.append('class_recall:' + k)
    if critical:
        if critical_cases < min_critical:
            reasons.append('critical_cases_below_minimum')
        if critical_misses:
            reasons.append('critical_miss')
    return {'verdict': 'hold' if reasons else 'pass', 'reasons': reasons,
            'stats': {'n': n, 'b': b, 'c': c_, 'cpLower': lower, 'alpha': alpha, 'coverage': coverage,
                      'accuracy': right / n if n else 0.0, 'baselineAccuracy': base_right / n if n else 0.0,
                      'balancedAccuracy': balanced, 'baselineBalancedAccuracy': base_balanced,
                      'recall': recall, 'criticalCases': critical_cases, 'criticalMisses': critical_misses}}


def demotion(window_cases, fresh_count, history, *, baseline=None, critical=False, window=30, fresh_labels=10, consecutive=2):
    """Live demotion (plan §3.7). `window_cases` are labelled advise-arm cases, oldest first; `fresh_count` the labels
    accrued since the last evaluation; `history` the prior evaluations' below-baseline flags (oldest first).

    A critical miss demotes at once. Otherwise nothing is evaluated until `fresh_labels` new labels exist; then the
    latest `window` cases are scored and `consecutive` evaluations in a row below the baseline demote. Callers
    should pass the frozen `baseline`; without one the window's own majority label stands in.
    """
    history = list(history)
    if critical and any(c.get('critical_if_wrong') and _answered(c) and c['choice'] != c['label'] for c in window_cases):
        return {'demote': True, 'reason': 'critical_miss', 'evaluated': False, 'history': []}
    latest = list(window_cases)[-window:]
    if fresh_count < fresh_labels or not latest:
        return {'demote': False, 'reason': None, 'evaluated': False, 'history': history}
    baseline = baseline if baseline is not None else majority([c['label'] for c in latest])
    accuracy = sum(_laya_right(c) for c in latest) / len(latest)
    base_accuracy = sum(baseline == c['label'] for c in latest) / len(latest)
    history.append(accuracy < base_accuracy)
    demote = len(history) >= consecutive and all(history[-consecutive:])
    return {'demote': demote, 'reason': 'below_baseline_consecutive' if demote else None, 'evaluated': True,
            'below': history[-1], 'accuracy': accuracy, 'baselineAccuracy': base_accuracy, 'n': len(latest),
            'history': [] if demote else history}


def _iso(now):
    if isinstance(now, (int, float)) and not isinstance(now, bool):
        now = datetime.fromtimestamp(now, timezone.utc)
    return locked_io.iso(now)


def run_attempt(root, decision, candidate_cases, *, policy_sha, instrument_sha, laya_revision, gate_cfg, prior,
                baseline, critical=False, now=None, dry_run=False, predict_one, probe=None):
    """One ledger-bound attempt. `candidate_cases` carry id, group, label, critical_if_wrong; `predict_one(case)`
    returns Laya's choice (None to abstain) and may raise, which counts as an unavailable answer (Laya wrong).

    Picks promotion-split cases never reserved before; holds without touching the ledger below minCohort or when
    `probe()` (Laya availability; raises when down) fails, so an outage never consumes a cohort or spends alpha.
    Otherwise appends `reserve` (case ids, frozen baseline) BEFORE predicting, evaluates at alpha_for_attempt(alphaBase,
    next_attempt), stores the receipt and appends the single `consumed` event. dry_run evaluates without any ledger
    or receipt write.
    """
    cfg = {**DEFAULT_GATE, **(gate_cfg or {})}
    used = advise_ledger.consumed_case_ids(root, decision)
    selected = sorted((c for c in candidate_cases if split_of(c['group']) == 'promotion' and c['id'] not in used),
                      key=lambda c: c['id'])
    if len(selected) < cfg['minCohort']:
        return {'status': 'held', 'reason': 'insufficient_promotion_cases', 'available': len(selected),
                'required': cfg['minCohort']}
    if probe is not None:
        try:
            probe()
        except Exception:  # noqa: BLE001 - any failure means Laya is unavailable
            return {'status': 'held', 'reason': 'laya_unavailable'}
    attempt = advise_ledger.next_attempt(root, decision)
    alpha = alpha_for_attempt(cfg['alphaBase'], attempt)
    ids = [c['id'] for c in selected]
    cohort = sha256({'decision': decision, 'policy': policy_sha, 'instrument': instrument_sha,
                     'attempt': attempt, 'caseIds': ids})[:32]
    base = {'cohortId': cohort, 'decision': decision, 'policySha256': policy_sha, 'instrumentSha256': instrument_sha,
            'layaRevision': laya_revision, 'attempt': attempt, 'alpha': alpha}
    if not dry_run:
        advise_ledger.append(root, decision, {**base, 'event': 'reserve', 'caseIds': ids, 'baseline': baseline,
                                              'ts': _iso(now)})
    scored = []
    for case in selected:
        try:
            choice, status = predict_one(case), 'ok'
        except Exception:  # noqa: BLE001 - any failure is an unavailable answer, counted wrong
            choice, status = None, 'unavailable'
        scored.append({**case, 'choice': choice, 'status': status})
    result = evaluate(scored, baseline=baseline, alpha=alpha, prior=prior, min_cohort=cfg['minCohort'],
                      min_coverage=cfg['minCoverage'], critical=critical,
                      min_critical=cfg.get('minCriticalCases') or CRITICAL_MIN_CASES)
    receipt = {'schema': RECEIPT_SCHEMA, **base, 'baseline': baseline, 'critical': critical, 'gate': cfg,
               'caseIdsSha256': sha256(ids), **result, 'dryRun': dry_run}
    receipt_sha = sha256(receipt)
    if not dry_run:
        directory = locked_io.private_dir(Path(root) / decision / 'advise-receipts', anchor=Path(root))
        locked_io.write_private_exclusive(directory / (cohort + '.json'),
                                          (json.dumps(receipt, sort_keys=True, indent=2) + '\n').encode())
        advise_ledger.append(root, decision, {**base, 'event': 'consumed', 'verdict': result['verdict'],
                                              'receiptSha256': receipt_sha, 'ts': _iso(now)})
    return {'status': 'dry_run' if dry_run else 'evaluated', **receipt, 'receiptSha256': receipt_sha}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    status = sub.add_parser('status', help='print the advise cohort ledger of a decision')
    status.add_argument('--root', required=True, help='typed-decisions state directory')
    status.add_argument('--decision', default='workflow-fit')
    args = parser.parse_args()
    print(json.dumps(advise_ledger.read(args.root, args.decision), sort_keys=True, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
