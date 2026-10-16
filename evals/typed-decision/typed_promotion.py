#!/usr/bin/env python3
"""advise-v1 promotion gate: Laya must beat the frozen majority-class baseline (plan §3, §11).

Pure functions generic over decisions (stdlib only, Python 3.9 compatible). The statistical unit is the group
(session): `evaluate`, the paired sign test, receives at most one case per group, and the ledger refuses a group
that any earlier cohort of the decision used. `run_attempt` is the replay flow (reserve before predicting, one
case per group); `run_live` the prospective one (a cohort is `open`ed before any eligible record exists, its cases
are the earliest record per promotion group created after it, evaluated once). `demotion` is the live check.
The gate itself never writes the registry; its callers (decision_cycle, pilot_cycle) do, through the shared
`registry_mutate`, `earned_result` and `demotion_result` below, which wrap decision_registry.mutate.
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
from typed_decisions import advise_ledger, decision_registry, locked_io  # noqa: E402
from typed_decisions.cohorts import alpha_for_attempt, cp_lower  # noqa: E402

RECEIPT_SCHEMA = 'rhize-advise-baseline-receipt-v1'
PRIOR_SHARE_FLOOR = 0.10      # classes below this share of the tuning split are not scored
MIN_CLASS_CASES = 3
MIN_CLASS_RECALL = 0.5
DEFAULT_GATE = {'minCohort': 30, 'alphaBase': 0.10, 'minCoverage': 0.9, 'minCriticalCases': 0,
                'demote': {'freshLabels': 10, 'window': 30, 'consecutive': 2}}
CRITICAL_MIN_CASES = 10
DEMOTION_FILE = 'advise-demotion.json'   # <root>/<decision>/: the rolling check's history and seen case ids


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
    """Gate one promotion cohort. case = {id, group, label, choice, status, critical_if_wrong}, at most one per group
    (a repeated group holds as 'duplicate_groups').

    Laya is wrong on a non-ok status, an abstention (choice None) or a different choice; a critical_if_wrong case it
    is wrong on is a critical miss. Every class with >= 10% of the tuning prior must have >= 3 cohort cases (a class
    missing from the cohort fails 'class_coverage:<class>'). Returns {verdict, reasons, stats}; verdict is 'pass'
    only when every condition holds.
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
    critical_misses = sum(bool(c.get('critical_if_wrong')) and not _laya_right(c) for c in cases)
    total = float(sum(prior.values())) or 1.0
    scored = sorted(k for k, v in prior.items() if v / total >= PRIOR_SHARE_FLOOR)
    reasons = []
    if n < min_cohort:
        reasons.append('cohort_too_small')
    groups = len({c['group'] for c in cases})
    if groups < n:
        reasons.append('duplicate_groups')
    if groups < min_cohort:
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


def demotion(window_cases, fresh_count, history, *, baseline=None, critical=False, window=30, fresh_labels=10,
             consecutive=2, scan_cases=None):
    """Live demotion (plan §3.7). `window_cases` are labelled advise-arm cases, oldest first; `fresh_count` the labels
    accrued since the last evaluation; `history` the prior evaluations' below-baseline flags (oldest first).

    A critical miss demotes at once: on a critical decision, any critical_if_wrong case Laya did not get right
    (including an abstention or an unavailable answer) among `scan_cases` - every shown critical case since the last
    demotion, not only the window (default: the window). Otherwise nothing is evaluated until `fresh_labels` new
    labels exist; then the latest `window` cases are scored and `consecutive` evaluations in a row below the
    baseline demote. Callers should pass the frozen `baseline`; without one the window's own majority stands in.
    """
    history = list(history)
    scan = window_cases if scan_cases is None else scan_cases
    if critical and any(c.get('critical_if_wrong') and not _laya_right(c) for c in scan):
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


def probe_ok(probe) -> bool:
    """Laya availability, fail closed: `probe()` must return exactly True. A raise, False, None or anything else
    (including no probe at all) is unavailable."""
    try:
        return probe is not None and probe() is True
    except Exception:  # noqa: BLE001 - any failure means Laya is unavailable
        return False


def _score(cases, predict_one):
    scored = []
    for case in cases:
        try:
            choice, status = predict_one(case), 'ok'
        except Exception:  # noqa: BLE001 - any failure is an unavailable answer, counted wrong
            choice, status = None, 'unavailable'
        scored.append({**case, 'choice': choice, 'status': status})
    return scored


def _settle(root, decision, base, cases, *, baseline, prior, critical, cfg, predict_one, now, dry_run, ended=None):
    """Predict, evaluate, store the receipt and append the single `consumed` event (`ended` = extra consumed fields)."""
    ids = [c['id'] for c in cases]
    result = evaluate(_score(cases, predict_one), baseline=baseline, alpha=base['alpha'], prior=prior,
                      min_cohort=cfg['minCohort'], min_coverage=cfg['minCoverage'], critical=critical,
                      min_critical=cfg.get('minCriticalCases') or CRITICAL_MIN_CASES)
    receipt = {'schema': RECEIPT_SCHEMA, **base, 'baseline': baseline, 'critical': critical, 'gate': cfg,
               'caseIdsSha256': sha256(ids), **result, 'dryRun': dry_run}
    receipt_sha = sha256(receipt)
    if not dry_run:
        directory = locked_io.private_dir(Path(root) / decision / 'advise-receipts', anchor=Path(root))
        locked_io.write_private_exclusive(directory / (base['cohortId'] + '.json'),
                                          (json.dumps(receipt, sort_keys=True, indent=2) + '\n').encode())
        advise_ledger.append(root, decision, {**base, 'event': 'consumed', 'verdict': result['verdict'],
                                              'receiptSha256': receipt_sha, 'ts': _iso(now), **(ended or {})})
    return {'status': 'dry_run' if dry_run else 'evaluated', **receipt, 'receiptSha256': receipt_sha}


def _one_per_group(cases, used_groups, used_ids=frozenset()):
    """Promotion-split cases on groups no earlier cohort used, the smallest case id per group (deterministic and
    outcome independent), sorted by id."""
    best = {}
    for case in sorted(cases, key=lambda c: c['id']):
        if (split_of(case['group']) == 'promotion' and case['id'] not in used_ids
                and advise_ledger.group_hash(case['group']) not in used_groups):
            best.setdefault(case['group'], case)
    return sorted(best.values(), key=lambda c: c['id'])


def run_attempt(root, decision, candidate_cases, *, policy_sha, instrument_sha, laya_revision, gate_cfg, prior,
                baseline, critical=False, now=None, dry_run=False, predict_one, probe):
    """One replay attempt (workflow-fit corpus), ledger-bound. `candidate_cases` carry id, group, label,
    critical_if_wrong; `predict_one(case)` returns Laya's choice (None to abstain) and may raise, which counts as an
    unavailable answer (Laya wrong).

    Picks one promotion-split case per group, on groups no earlier cohort used; holds without touching the ledger
    below minCohort or when `probe()` (mandatory; must return True, see `probe_ok`) says Laya is down, so an outage
    never consumes a cohort or spends alpha. Otherwise appends `reserve` (case ids, group hashes, frozen baseline)
    BEFORE predicting, evaluates at alpha_for_attempt(alphaBase, next_attempt), stores the receipt and appends the
    single `consumed` event. dry_run evaluates without any ledger or receipt write.
    """
    cfg = {**DEFAULT_GATE, **(gate_cfg or {})}
    selected = _one_per_group(candidate_cases, advise_ledger.used_groups(root, decision),
                              advise_ledger.consumed_case_ids(root, decision))
    if len(selected) < cfg['minCohort']:
        return {'status': 'held', 'reason': 'insufficient_promotion_cases', 'available': len(selected),
                'required': cfg['minCohort']}
    if not probe_ok(probe):
        return {'status': 'held', 'reason': 'laya_unavailable'}
    attempt = advise_ledger.next_attempt(root, decision)
    ids = [c['id'] for c in selected]
    base = _base(decision, policy_sha, instrument_sha, laya_revision, attempt, cfg,
                 sha256({'decision': decision, 'policy': policy_sha, 'instrument': instrument_sha,
                         'attempt': attempt, 'caseIds': ids})[:32])
    if not dry_run:
        advise_ledger.append(root, decision, {**base, 'event': 'reserve', 'caseIds': ids, 'baseline': baseline,
                                              'groups': sorted(advise_ledger.group_hash(c['group']) for c in selected),
                                              'ts': _iso(now)})
    return _settle(root, decision, base, selected, baseline=baseline, prior=prior, critical=critical, cfg=cfg,
                   predict_one=predict_one, now=now, dry_run=dry_run)


def _base(decision, policy_sha, instrument_sha, laya_revision, attempt, cfg, cohort):
    return {'cohortId': cohort, 'decision': decision, 'policySha256': policy_sha, 'instrumentSha256': instrument_sha,
            'layaRevision': laya_revision, 'attempt': attempt, 'alpha': alpha_for_attempt(cfg['alphaBase'], attempt)}


def collect_cohort(rows, opened_at, used_groups):
    """The live cohort's cases: the earliest record (by ts, then id) of each promotion-split group created after
    `opened_at` on a group no earlier cohort used; only groups whose earliest record is labelled (label not None)
    count. Selection never looks at an outcome, a recommendation or Laya's answer. rows carry id, group, ts, label
    (None when unlabelled or ambiguous) and critical_if_wrong."""
    opened = locked_io.utc(opened_at)
    first = {}
    for row in sorted(rows, key=lambda r: (locked_io.utc(r['ts']), r['id'])):
        if (split_of(row['group']) == 'promotion' and advise_ledger.group_hash(row['group']) not in used_groups
                and locked_io.utc(row['ts']) > opened):
            first.setdefault(row['group'], row)
    return sorted((r for r in first.values() if r['label'] is not None), key=lambda r: r['id'])


def run_live(root, decision, rows, *, policy_sha, instrument_sha, laya_revision, gate_cfg, prior, baseline,
             critical=False, now=None, dry_run=False, predict_one, probe):
    """One prospective-cohort step for a live decision. `rows` are every record of the decision on the current
    binding (see collect_cohort). In order:
      - no open cohort: probe (mandatory, `probe_ok`), then append `open` and hold as 'cohort_opened'. Nothing
        recorded before this moment is ever a case;
      - an open cohort on another binding is `abandoned` (its attempt and alpha stay spent) and a fresh one opens;
      - an open cohort with fewer than minCohort labelled groups (and, when critical, minCriticalCases critical
        cases) holds as 'cohort_collecting'; otherwise it is evaluated once and `consumed`.
    dry_run writes nothing."""
    cfg = {**DEFAULT_GATE, **(gate_cfg or {})}
    active = advise_ledger.open_cohort(root, decision)
    binding = (policy_sha, instrument_sha, laya_revision)
    if active is not None and (active['policySha256'], active['instrumentSha256'], active['layaRevision']) != binding:
        if not probe_ok(probe):
            return {'status': 'held', 'reason': 'laya_unavailable'}
        if dry_run:
            return {'status': 'held', 'reason': 'would_abandon_stale_cohort', 'cohortId': active['cohortId']}
        advise_ledger.append(root, decision, {
            'event': 'abandoned', **{k: active[k] for k in ('cohortId', 'decision', 'policySha256', 'instrumentSha256',
                                                              'layaRevision', 'attempt', 'alpha')},
            'reason': 'binding_changed', 'ts': _iso(now)})
        active = None
    if active is None:
        if not probe_ok(probe):
            return {'status': 'held', 'reason': 'laya_unavailable'}
        if dry_run:
            return {'status': 'held', 'reason': 'would_open_cohort'}
        attempt = advise_ledger.next_attempt(root, decision)
        opened_at = _iso(now)
        base = _base(decision, policy_sha, instrument_sha, laya_revision, attempt, cfg,
                     sha256({'decision': decision, 'policy': policy_sha, 'instrument': instrument_sha,
                             'attempt': attempt, 'openedAt': opened_at})[:32])
        advise_ledger.append(root, decision, {**base, 'event': 'open', 'openedAt': opened_at,
                                              'rule': advise_ledger.OPEN_RULE, 'ts': opened_at})
        return {'status': 'held', 'reason': 'cohort_opened', 'cohortId': base['cohortId'], 'attempt': attempt,
                'openedAt': opened_at}
    cases = collect_cohort(rows, active['openedAt'], advise_ledger.used_groups(root, decision))
    need_critical = (cfg.get('minCriticalCases') or CRITICAL_MIN_CASES) if critical else 0
    if len(cases) < cfg['minCohort'] or sum(bool(c['critical_if_wrong']) for c in cases) < need_critical:
        return {'status': 'held', 'reason': 'cohort_collecting', 'cohortId': active['cohortId'],
                'available': len(cases), 'required': cfg['minCohort'],
                'criticalAvailable': sum(bool(c['critical_if_wrong']) for c in cases), 'criticalRequired': need_critical}
    base = {k: active[k] for k in ('cohortId', 'decision', 'policySha256', 'instrumentSha256', 'layaRevision',
                                   'attempt', 'alpha')}
    trimmed = [{k: c[k] for k in ('id', 'group', 'label', 'critical_if_wrong')} for c in cases]
    ended = {'caseIds': [c['id'] for c in trimmed],
             'groups': sorted(advise_ledger.group_hash(c['group']) for c in trimmed)}
    return _settle(root, decision, base, trimmed, baseline=baseline, prior=prior, critical=critical, cfg=cfg,
                   predict_one=predict_one, now=now, dry_run=dry_run, ended=ended)


# ---------------------------------------------------------------- shared cycle plumbing (registry writes)

def registry_mutate(root, registry, decision, to_mode, reason, expected_revision, binding=None, now=None):
    """The cycles' single registry write; a refusal is a recorded hold, never a crash."""
    try:
        state = decision_registry.mutate(root, decision, to_mode, actor='cycle', reason=reason,
                                         expected_revision=expected_revision, binding=binding, now=now, registry=registry)
    except decision_registry.RegistryError as err:
        return {'status': 'held', 'to': to_mode, 'code': err.code}
    return {'status': 'mutated', 'to': to_mode, 'reason': reason, 'revision': state['revision']}


def earned_result(root, registry, decision, receipt, *, policy_sha, instrument_sha, laya_revision, expected_revision,
                  now=None, dry_run=False):
    """Fold a finished `run_attempt` receipt into the cycle's result: a 'pass' moves the decision to advise through
    the registry (only planned on a dry run), bound to the cohort that earned it."""
    result = {'status': receipt['status'], 'earnedMode': 'shadow', 'registry': None,
              **{key: receipt[key] for key in ('verdict', 'reasons', 'stats', 'cohortId', 'attempt', 'alpha',
                                               'receiptSha256', 'baseline')}}
    if receipt['verdict'] == 'pass':
        if dry_run:
            result['registry'] = {'status': 'would_mutate', 'to': 'advise', 'reason': 'gate_pass'}
        else:
            binding = {'policySha256': policy_sha, 'instrumentSha256': instrument_sha, 'layaRevision': laya_revision,
                       'cohortId': receipt['cohortId']}
            result['registry'] = registry_mutate(root, registry, decision, 'advise', 'gate_pass', expected_revision,
                                                 binding, now)
            if result['registry']['status'] == 'mutated':
                result['earnedMode'] = 'advise'
    return result


def cohort_baseline(root, decision, cohort_id):
    """The baseline frozen into a consumed cohort's receipt (replay and live alike); None when unreadable."""
    try:
        return locked_io.read_json_file(Path(root) / decision / 'advise-receipts' / (cohort_id + '.json'))['baseline']
    except (OSError, ValueError, KeyError, TypeError):
        return None


def read_demotion_state(root, decision):
    """(history, seen ids) of the rolling demotion check; empty when never written or unreadable."""
    try:
        value = locked_io.read_json_file(Path(root) / decision / DEMOTION_FILE)
        return list(value['history']), set(value['seen'])
    except (OSError, ValueError, KeyError, TypeError):
        return [], set()


def demotion_result(root, registry, decision, outcome, seen, *, expected_revision, reason, now=None, dry_run=False,
                    guard=None):
    """Persist a `demotion()` outcome's history (never on a dry run) and, when it demotes, move the decision to
    shadow with `reason`. `guard()` runs just before that write (it may raise to refuse it)."""
    result = {'status': 'evaluated', 'branch': 'demotion', 'earnedMode': 'advise', 'registry': None,
              'demotion': {key: value for key, value in outcome.items() if key != 'history'}}
    if not dry_run and (outcome['evaluated'] or outcome['demote']):
        locked_io.write_private_atomic(Path(root) / decision / DEMOTION_FILE,
                                       json.dumps({'history': outcome['history'], 'seen': sorted(seen)}).encode())
    if outcome['demote']:
        if dry_run:
            result['registry'] = {'status': 'would_mutate', 'to': 'shadow', 'reason': reason}
        else:
            if guard:
                guard()
            result['registry'] = registry_mutate(root, registry, decision, 'shadow', reason, expected_revision, None, now)
            if result['registry']['status'] == 'mutated':
                result['earnedMode'] = 'shadow'
    return result


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
