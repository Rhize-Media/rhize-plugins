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


def _receipt_path(root, decision, cohort_id):
    return Path(root) / decision / 'advise-receipts' / (cohort_id + '.json')


def _recover(root, decision, cohort_id):
    """The stored receipt of a cohort whose evaluation already finished, or None. A receipt for another cohort or
    decision is an error, never a recovery."""
    try:
        receipt = locked_io.read_json_file(_receipt_path(root, decision, cohort_id))
    except FileNotFoundError:
        return None
    if (not isinstance(receipt, dict) or receipt.get('cohortId') != cohort_id or receipt.get('decision') != decision
            or receipt.get('verdict') not in ('pass', 'hold')):
        raise ValueError('advise receipt does not match its cohort')
    return receipt


def _consume(root, decision, receipt, now):
    """Append the `consumed` event for a finished receipt, once (a retry after a crash finds it already there)."""
    if receipt['cohortId'] not in advise_ledger.consumed_cohorts(root, decision):
        advise_ledger.append(root, decision, {
            'event': 'consumed', **{k: receipt[k] for k in ('cohortId', 'decision', 'policySha256', 'instrumentSha256',
                                                              'layaRevision', 'attempt', 'alpha')},
            'verdict': receipt['verdict'], 'receiptSha256': sha256(receipt), 'ts': _iso(now)})
    return _adopt(receipt)


def _adopt(receipt):
    return {'status': 'evaluated', **receipt, 'receiptSha256': sha256(receipt)}


def _finish(root, decision, base, ids, result, *, baseline, critical, cfg, now, dry_run):
    """Publish the receipt exclusively per cohort, then append `consumed`. Crash safe: whoever finds the receipt
    already published (a retry) adopts it unchanged and only appends the missing `consumed`."""
    receipt = {'schema': RECEIPT_SCHEMA, **base, 'baseline': baseline, 'critical': critical, 'gate': cfg,
               'caseIdsSha256': sha256(ids), **result, 'dryRun': dry_run}
    if dry_run:
        return {'status': 'dry_run', **receipt, 'receiptSha256': sha256(receipt)}
    directory = locked_io.private_dir(Path(root) / decision / 'advise-receipts', anchor=Path(root))
    try:
        locked_io.write_private_exclusive(directory / (base['cohortId'] + '.json'),
                                          (json.dumps(receipt, sort_keys=True, indent=2) + '\n').encode())
    except FileExistsError:
        receipt = _recover(root, decision, base['cohortId'])
    return _consume(root, decision, receipt, now)


def _evaluate(cases, predict_one, *, baseline, alpha, prior, cfg, critical):
    return evaluate(_score(cases, predict_one), baseline=baseline, alpha=alpha, prior=prior,
                    min_cohort=cfg['minCohort'], min_coverage=cfg['minCoverage'], critical=critical,
                    min_critical=cfg.get('minCriticalCases') or CRITICAL_MIN_CASES)


def _one_per_group(cases, used_groups, used_ids=frozenset()):
    """Promotion-split cases on groups no earlier cohort used, the smallest case id per group (deterministic and
    outcome independent), sorted by id."""
    best = {}
    for case in sorted(cases, key=lambda c: c['id']):
        if (split_of(case['group']) == 'promotion' and case['id'] not in used_ids
                and advise_ledger.group_hash(case['group']) not in used_groups):
            best.setdefault(case['group'], case)
    return sorted(best.values(), key=lambda c: c['id'])


def _base(decision, policy_sha, instrument_sha, laya_revision, attempt, cfg, cohort):
    return {'cohortId': cohort, 'decision': decision, 'policySha256': policy_sha, 'instrumentSha256': instrument_sha,
            'layaRevision': laya_revision, 'attempt': attempt, 'alpha': alpha_for_attempt(cfg['alphaBase'], attempt)}


def _abandon(root, decision, cohort, reason, now):
    advise_ledger.append(root, decision, {
        'event': 'abandoned', **{k: cohort[k] for k in ('cohortId', 'decision', 'policySha256', 'instrumentSha256',
                                                         'layaRevision', 'attempt', 'alpha')},
        'reason': reason, 'ts': _iso(now)})


def run_attempt(root, decision, candidate_cases, *, policy_sha, instrument_sha, laya_revision, gate_cfg, prior,
                baseline, critical=False, now=None, dry_run=False, predict_one, probe):
    """One replay attempt (workflow-fit corpus), ledger-bound. `candidate_cases` carry id, group, label,
    critical_if_wrong; `predict_one(case)` returns Laya's choice (None to abstain) and may raise, which counts as an
    unavailable answer (Laya wrong).

    Picks one promotion-split case per group, on groups no earlier cohort used; holds without touching the ledger
    below minCohort or when `probe()` (mandatory; must return True, see `probe_ok`) says Laya is down, so an outage
    never consumes a cohort or spends alpha. Otherwise appends `reserve` (case ids, group hashes, frozen baseline)
    BEFORE predicting, evaluates at alpha_for_attempt(alphaBase, next_attempt), publishes the receipt exclusively and
    appends the single `consumed` event. A reserved cohort left without a verdict (a crash, or a probe failure
    right before evaluation) is resumed - its stored receipt adopted unchanged if it exists - not replaced.
    dry_run evaluates without any ledger or receipt write.
    """
    cfg = {**DEFAULT_GATE, **(gate_cfg or {})}
    pending = advise_ledger.pending_reserve(root, decision)
    if pending is not None:
        finished = _recover(root, decision, pending['cohortId'])
        if finished is not None:
            return _adopt(finished) if dry_run else _consume(root, decision, finished, now)
        wanted = set(pending['caseIds'])
        resumed = sorted((c for c in candidate_cases if c['id'] in wanted), key=lambda c: c['id'])
        same = (pending['policySha256'], pending['instrumentSha256'], pending['layaRevision']) == (
            policy_sha, instrument_sha, laya_revision)
        if same and len(resumed) == len(wanted):
            if not probe_ok(probe):
                return {'status': 'held', 'reason': 'laya_unavailable'}
            base = {k: pending[k] for k in ('cohortId', 'decision', 'policySha256', 'instrumentSha256', 'layaRevision',
                                            'attempt', 'alpha')}
            frozen = pending.get('baseline', baseline)
            result = _evaluate(resumed, predict_one, baseline=frozen, alpha=base['alpha'], prior=prior, cfg=cfg,
                               critical=critical)
            return _finish(root, decision, base, [c['id'] for c in resumed], result, baseline=frozen,
                           critical=critical, cfg=cfg, now=now, dry_run=dry_run)
        if not dry_run:       # another binding, or its cases are gone: the attempt stays spent, a fresh cohort follows
            _abandon(root, decision, pending, 'binding_changed' if not same else 'cases_missing', now)
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
    result = _evaluate(selected, predict_one, baseline=baseline, alpha=base['alpha'], prior=prior, cfg=cfg,
                       critical=critical)
    return _finish(root, decision, base, ids, result, baseline=baseline, critical=critical, cfg=cfg, now=now,
                   dry_run=dry_run)


AMBIGUOUS_MAX = 0.2       # more ambiguous labels than this share of an enrolled cohort consume it as a hold


def _enroll_target(minimum):
    return -(-int(minimum) * 10 // 8) if minimum else 0     # ceil(minimum / 0.8)


def enrollment_cases(rows, opened_at, used_groups, minimum, minimum_critical):
    """Label-independent enrollment: the earliest record (by ts, then id) of each promotion-split group created after
    `opened_at` on groups no earlier cohort used, taken in that order until there are enough of them and enough
    critical_if_wrong ones. Looks only at id, group, ts and the pre-decision critical flag - never a label, an
    outcome, a recommendation or Laya's answer. Returns (chosen rows, all candidate rows); chosen is [] while short.
    `minimum` counts cases that survive up to 20% ambiguous labels, so the target is ceil(minimum / 0.8)."""
    opened = locked_io.utc(opened_at)
    first = {}
    for row in sorted(rows, key=lambda r: (locked_io.utc(r['ts']), r['id'])):
        if (split_of(row['group']) == 'promotion' and advise_ledger.group_hash(row['group']) not in used_groups
                and locked_io.utc(row['ts']) > opened):
            first.setdefault(row['group'], row)
    ordered = list(first.values())
    want, want_critical, chosen, critical = _enroll_target(minimum), _enroll_target(minimum_critical), [], 0
    for row in ordered:
        chosen.append(row)
        critical += bool(row['critical_if_wrong'])
        if len(chosen) >= want and critical >= want_critical:
            return chosen, ordered
    return [], ordered


def run_live(root, decision, rows, *, policy_sha, instrument_sha, laya_revision, gate_cfg, prior, baseline,
             critical=False, now=None, dry_run=False, predict_one, probe):
    """One prospective-cohort step for a live decision. `rows` are every record of the decision on the current
    binding: id, group, ts, critical_if_wrong, label (None while unlabelled or ambiguous) and ambiguous (True when
    the final label is ambiguous). `baseline` is the tuning majority NOW; it is frozen into the cohort only when
    one opens. In order:
      - an open cohort on another binding is `abandoned` (its attempt and alpha stay spent);
      - no open cohort: needs a baseline and a passing probe (mandatory, `probe_ok`), then appends `open` (with the
        frozen baseline) and holds as 'cohort_opened'. Nothing recorded before that moment is ever a case;
      - an open cohort not yet enrolled enrolls (see enrollment_cases) as soon as enough groups exist, appending the
        immutable `enrolled` event, else holds as 'cohort_collecting';
      - an enrolled cohort whose receipt is already published is finished from that receipt (crash recovery);
      - otherwise it waits ('cohort_labelling') until every enrolled case has a final label, then probes Laya
        immediately before evaluating and settles once with the open-frozen baseline: ambiguous labels are
        excluded and more than 20% of them consume the cohort as a hold ('ambiguous_share').
    dry_run writes nothing."""
    cfg = {**DEFAULT_GATE, **(gate_cfg or {})}
    active = advise_ledger.open_cohort(root, decision)
    binding = (policy_sha, instrument_sha, laya_revision)
    if active is not None and (active['policySha256'], active['instrumentSha256'], active['layaRevision']) != binding:
        if not probe_ok(probe):
            return {'status': 'held', 'reason': 'laya_unavailable'}
        if dry_run:
            return {'status': 'held', 'reason': 'would_abandon_stale_cohort', 'cohortId': active['cohortId']}
        _abandon(root, decision, active, 'binding_changed', now)
        active = None
    if active is None:
        if not baseline:
            return {'status': 'held', 'reason': 'no_baseline'}
        if not probe_ok(probe):
            return {'status': 'held', 'reason': 'laya_unavailable'}
        if dry_run:
            return {'status': 'held', 'reason': 'would_open_cohort'}
        attempt = advise_ledger.next_attempt(root, decision)
        opened_at = _iso(now)
        base = _base(decision, policy_sha, instrument_sha, laya_revision, attempt, cfg,
                     sha256({'decision': decision, 'policy': policy_sha, 'instrument': instrument_sha,
                             'attempt': attempt, 'openedAt': opened_at})[:32])
        advise_ledger.append(root, decision, {**base, 'event': 'open', 'openedAt': opened_at, 'baseline': baseline,
                                              'rule': advise_ledger.OPEN_RULE, 'ts': opened_at})
        return {'status': 'held', 'reason': 'cohort_opened', 'cohortId': base['cohortId'], 'attempt': attempt,
                'alpha': base['alpha'], 'openedAt': opened_at, 'baseline': baseline}
    base = {k: active[k] for k in ('cohortId', 'decision', 'policySha256', 'instrumentSha256', 'layaRevision',
                                   'attempt', 'alpha')}
    enrolled = advise_ledger.enrollment(root, decision, active['cohortId'])
    if enrolled is None:
        need_critical = (cfg.get('minCriticalCases') or CRITICAL_MIN_CASES) if critical else 0
        chosen, ordered = enrollment_cases(rows, active['openedAt'], advise_ledger.used_groups(root, decision),
                                           cfg['minCohort'], need_critical)
        if not chosen:
            return {'status': 'held', 'reason': 'cohort_collecting', 'cohortId': active['cohortId'],
                    'available': len(ordered), 'required': _enroll_target(cfg['minCohort']),
                    'criticalAvailable': sum(bool(r['critical_if_wrong']) for r in ordered),
                    'criticalRequired': _enroll_target(need_critical)}
        if dry_run:
            return {'status': 'held', 'reason': 'would_enroll_cohort', 'cohortId': active['cohortId'],
                    'enrolled': len(chosen)}
        enrolled = advise_ledger.append(root, decision, {
            **base, 'event': 'enrolled', 'caseIds': sorted(r['id'] for r in chosen),
            'groups': sorted(advise_ledger.group_hash(r['group']) for r in chosen), 'ts': _iso(now)})
    finished = _recover(root, decision, active['cohortId'])
    if finished is not None:
        return _adopt(finished) if dry_run else _consume(root, decision, finished, now)
    by_id = {r['id']: r for r in rows}
    final = [by_id.get(i) for i in enrolled['caseIds']]
    pending = sum(r is None or (r['label'] is None and not r.get('ambiguous')) for r in final)
    if pending:
        return {'status': 'held', 'reason': 'cohort_labelling', 'cohortId': active['cohortId'],
                'enrolled': len(final), 'pending': pending}
    if not probe_ok(probe):          # Laya is queried (or relied on) only while it is verifiably the one we gated
        return {'status': 'held', 'reason': 'laya_unavailable'}
    frozen = active['baseline']
    ids = list(enrolled['caseIds'])
    ambiguous = sum(r['label'] is None for r in final)
    if ambiguous / len(final) > AMBIGUOUS_MAX:
        result = {'verdict': 'hold', 'reasons': ['ambiguous_share'],
                  'stats': {'n': len(final) - ambiguous, 'enrolled': len(final), 'ambiguous': ambiguous}}
    else:
        usable = [{k: r[k] for k in ('id', 'group', 'label', 'critical_if_wrong')} for r in final
                  if r['label'] is not None]
        result = _evaluate(usable, predict_one, baseline=frozen, alpha=base['alpha'], prior=prior, cfg=cfg,
                           critical=critical)
        result['stats']['enrolled'] = len(final)
        result['stats']['ambiguous'] = ambiguous
    return _finish(root, decision, base, ids, result, baseline=frozen, critical=critical, cfg=cfg, now=now,
                   dry_run=dry_run)


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
