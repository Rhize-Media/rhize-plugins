"""Cohort gate, demotion, report-only alternatives and the recursive cycle (plan §4.6, invariants I5-I8, A6)."""
from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
from fractions import Fraction
from math import comb
from pathlib import Path

import pytest

from typed_decision_testkit import (  # noqa: E402
    ALT1, ALT2, CHOICE_IDS, CHOICE_POLICY, INC, LAYA_REV, REPO, SCRIPTS, disagreements, label_cohort, load_cycle_module,
    make_label, make_record, min_pass_x, passed_cohort, reserve_cohort, small_registry, write_choice, write_choice_label,
    write_labels, write_records)
import typed_advice  # noqa: E402
from typed_decisions import advise_ledger  # noqa: E402
from typed_decisions import cohorts, contract, decision_registry as reg, instrument, locked_io, records  # noqa: E402

SKILL = 'skill-fit'
CYCLE = load_cycle_module()
CYCLE_CLI = REPO / 'evals' / 'typed-decision' / 'decision_cycle.py'
SCRIPTS_DIR = SCRIPTS / 'typed_decisions'
T_RESERVE = '2026-10-11T00:00:00Z'
T_EVAL = '2026-10-11T06:00:00Z'
NOW = '2026-10-12T12:00:00Z'


class Crash(BaseException):
    pass


@pytest.fixture(autouse=True)
def _runtime_pin(monkeypatch):
    """Roots without a laya-runtime.json read as running the fixtures' checkpoint (LAYA_REV); a real pin file wins."""
    real = records.laya_revision

    def pinned(root=None):
        value = real(root)
        base = Path(root) if root is not None else records.default_root()
        return LAYA_REV if value == 'unknown' and not (base / 'laya-runtime.json').exists() else value

    monkeypatch.setattr(records, 'laya_revision', pinned)


@pytest.fixture
def root(tmp_path):
    # The Laya runtime pin the fixtures' records and bindings were produced under (activation writes it).
    path = tmp_path / 'typed-decisions'
    path.mkdir(mode=0o700)
    (path / 'laya-runtime.json').write_text(json.dumps({'revision': LAYA_REV}))
    return path


@pytest.fixture
def registry():
    return small_registry()


def by_key(recs):
    return {r['occurrenceKey']: r for r in recs}


def ledger_events(root):
    events, invalid = records.read(root, SKILL, 'cohorts')
    assert invalid == 0
    return events


def tree_snapshot(path: Path, locks=False):
    """Every file under `path` with mode, size, mtime and content hash (empty lock files are skipped by default)."""
    out = {}
    for item in sorted(path.rglob('*')) if path.exists() else []:
        if item.is_dir() or (item.suffix == '.lock' and not locks):
            continue
        info = item.stat()
        out[str(item.relative_to(path))] = (info.st_mode, info.st_size, info.st_mtime_ns,
                                            hashlib.sha256(item.read_bytes()).hexdigest())
    return out


def cosign_binding(cohort_id=None):
    entry = reg.load_registry()['decisions'][SKILL]
    policy_hash, instrument_hash = cohorts.deployable_hashes(entry)
    return {'policySha256': policy_hash, 'instrumentSha256': instrument_hash, 'layaRevision': LAYA_REV,
            'cohortId': cohort_id}


def go_cosign(root, since='2026-10-01T00:00:00Z', registry=None):
    root = Path(root)
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    (root / 'laya-runtime.json').write_text(json.dumps({'revision': LAYA_REV}))   # the binding's checkpoint
    return reg.mutate(root, SKILL, 'cosign', actor='cli', reason='manual_override', expected_revision=0,
                      binding=cosign_binding(), now=since, registry=registry)


# ================================================================ exact Clopper-Pearson

def exact_upper_tail(x, n, p):
    q = Fraction(p)
    return float(sum(comb(n, k) * q ** k * (1 - q) ** (n - k) for k in range(x, n + 1)))


def exact_lower_tail(x, n, p):
    q = Fraction(p)
    return float(sum(comb(n, k) * q ** k * (1 - q) ** (n - k) for k in range(0, x + 1)))


def test_clopper_pearson_known_values():
    # textbook two-sided 95% intervals are the one-sided bounds at 0.025
    assert cohorts.cp_lower(5, 10, 0.025) == pytest.approx(0.187086, abs=1e-6)
    assert cohorts.cp_upper(5, 10, 0.025) == pytest.approx(0.812914, abs=1e-6)
    assert cohorts.cp_lower(1, 10, 0.025) == pytest.approx(0.002529, abs=1e-6)
    assert cohorts.cp_upper(1, 10, 0.025) == pytest.approx(0.445016, abs=1e-6)
    # closed forms at the edges
    assert cohorts.cp_lower(60, 60, 0.05) == pytest.approx(0.05 ** (1 / 60), abs=1e-9)
    assert cohorts.cp_upper(0, 60, 0.05) == pytest.approx(1 - 0.05 ** (1 / 60), abs=1e-9)
    assert cohorts.cp_lower(0, 60, 0.05) == 0.0 and cohorts.cp_upper(60, 60, 0.05) == 1.0
    assert cohorts.cp_lower(0, 0, 0.05) == 0.0 and cohorts.cp_upper(0, 0, 0.05) == 1.0


def test_plan_gate_n60_alpha05_needs_37():
    assert cohorts.cp_lower(37, 60, 0.05) > 0.5
    assert cohorts.cp_lower(36, 60, 0.05) <= 0.5
    assert min_pass_x(60) == 37


@pytest.mark.parametrize('x,n,alpha', [(3, 10, 0.05), (37, 60, 0.05), (15, 20, 0.0125), (0, 30, 0.1), (29, 30, 0.1),
                                       (45, 90, 0.025), (7, 7, 0.05), (88, 100, 0.00625)])
def test_bounds_solve_the_defining_tail_equation(x, n, alpha):
    lower, upper = cohorts.cp_lower(x, n, alpha), cohorts.cp_upper(x, n, alpha)
    if x > 0:
        assert exact_upper_tail(x, n, lower) == pytest.approx(alpha, abs=1e-9)
    if x < n:
        assert exact_lower_tail(x, n, upper) == pytest.approx(alpha, abs=1e-9)
    assert 0 <= lower <= upper <= 1


def test_bounds_are_accurate_and_fast_for_n_1000():
    import time
    start = time.monotonic()
    lower = cohorts.cp_lower(520, 1000, 0.05)
    upper = cohorts.cp_upper(480, 1000, 0.05)
    assert time.monotonic() - start < 5
    # normal-approximation sanity (loose) plus the exact monotone relation between the two bounds
    assert 0.49 < lower < 0.50 and 0.50 < upper < 0.52
    assert cohorts.cp_lower(520, 1000, 0.05) == cohorts.cp_lower(520, 1000, 0.05)
    # lower(x) and upper(n-x) mirror each other
    assert cohorts.cp_upper(480, 1000, 0.05) == pytest.approx(1 - cohorts.cp_lower(520, 1000, 0.05), abs=1e-9)


def test_bounds_are_monotone():
    n = 40
    lowers = [cohorts.cp_lower(x, n, 0.05) for x in range(n + 1)]
    uppers = [cohorts.cp_upper(x, n, 0.05) for x in range(n + 1)]
    assert lowers == sorted(lowers) and uppers == sorted(uppers)
    assert all(lo <= up for lo, up in zip(lowers, uppers))
    for x in (5, 20, 35):                      # a smaller alpha is more conservative
        assert cohorts.cp_lower(x, n, 0.01) < cohorts.cp_lower(x, n, 0.05) < cohorts.cp_lower(x, n, 0.2)
        assert cohorts.cp_upper(x, n, 0.01) > cohorts.cp_upper(x, n, 0.05) > cohorts.cp_upper(x, n, 0.2)
    assert cohorts.cp_lower(30, 60, 0.05) < cohorts.cp_lower(60, 120, 0.05)    # more data tightens the bound


@pytest.mark.parametrize('args', [(-1, 10, 0.05), (11, 10, 0.05), (1, 10, 0.0), (1, 10, 1.0), (1.5, 10, 0.05),
                                  (True, 10, 0.05)])
def test_bounds_reject_invalid_input(args):
    with pytest.raises(ValueError):
        cohorts.cp_lower(*args)
    with pytest.raises(ValueError):
        cohorts.cp_upper(*args)


def test_alpha_spending_halves_each_attempt_and_stays_below_double_the_base():
    alphas = [cohorts.alpha_for_attempt(0.05, k) for k in range(1, 8)]
    assert alphas[:4] == [0.05, 0.025, 0.0125, 0.00625]
    assert sum(alphas) < 0.1 and sum(cohorts.alpha_for_attempt(0.05, k) for k in range(1, 60)) <= 0.1 + 1e-12
    for bad in (0, -1, 1.5, True):
        with pytest.raises(ValueError):
            cohorts.alpha_for_attempt(0.05, bad)


# ================================================================ reserve

def test_reserve_holds_without_writing_when_there_are_too_few_disagreements(root, registry):
    write_records(root, disagreements(19))
    before = tree_snapshot(root)
    result = cohorts.reserve(root, registry, T_RESERVE, 1)
    assert result['status'] == 'held' and result['reason'] == 'insufficient_disagreements'
    assert result['available'] == 19 and result['target'] == 20
    assert tree_snapshot(root) == before
    assert not (root / SKILL / 'cohorts').exists() and not (root / SKILL / 'cohort-meta').exists()


def test_reserve_takes_at_most_one_case_per_session(tmp_path, registry):
    # 5 chatty sessions own 12 disagreements each (60) plus 20 single-case sessions: without the cap a sample of
    # 20 would almost surely repeat a session; with it 25 sessions can yield at most 25 cases.
    recs = ([make_record(100 * s_ + k, session=f'chatty-{s_}') for s_ in range(5) for k in range(12)]
            + [make_record(1000 + k, session=f'single-{k}') for k in range(20)])
    for seed in range(8):
        root = tmp_path / f'seed-{seed}'
        write_records(root, recs)
        _, event = reserve_cohort(root, registry, seed=seed)
        lookup = by_key(recs)
        sessions = [lookup[k]['sessionHash'] for k in event['occurrenceKeys']]
        assert len(sessions) == 20 and len(set(sessions)) == 20, seed


def test_reserve_holds_when_distinct_sessions_are_short_even_with_many_cases(root, registry):
    recs = [make_record(i, session=i % 15) for i in range(40)]        # 40 disagreements but 15 sessions
    write_records(root, recs)
    result = cohorts.reserve(root, registry, T_RESERVE, 1)
    assert (result['status'], result['available'], result['eligible']) == ('held', 15, 40)


def test_reserve_only_samples_disagreements_of_the_current_key(root, registry):
    old = [make_record(i, laya_revision='old-rev', ts=f'2026-10-01T00:{i:02d}:05.000Z') for i in range(30)]
    new = [make_record(200 + i, laya_revision='new-rev', ts=f'2026-10-05T00:{i:02d}:05.000Z') for i in range(12)]
    noise = ([make_record(300 + i, choice=INC, laya_revision='new-rev') for i in range(10)]            # agreements
             + [make_record(320 + i, status='timeout', laya_revision='new-rev') for i in range(10)]    # Laya failed
             + [make_record(340 + i, instrument_sha='f' * 64) for i in range(30)]                       # other instrument
             + [make_record(380 + i, basis='backfill', incumbent=None, stratum='silent_sample',
                            laya_revision='new-rev') for i in range(10)])                              # router silent
    write_records(root, old + new + noise)
    (root / 'laya-runtime.json').write_text(json.dumps({'revision': 'new-rev'}))    # the checkpoint now running
    held = cohorts.reserve(root, registry, T_RESERVE, 1)
    assert (held['status'], held['available']) == ('held', 12)        # only the newest key counts
    more = [make_record(400 + i, laya_revision='new-rev', ts=f'2026-10-06T00:{i:02d}:05.000Z') for i in range(10)]
    write_records(root, more)
    result, event = reserve_cohort(root, registry)
    assert event['layaRevision'] == 'new-rev'
    lookup = by_key(new + more)
    assert set(event['occurrenceKeys']) <= set(lookup)                 # nothing from old-rev, agreements or noise
    assert all(contract.is_disagreement(lookup[k]) for k in event['occurrenceKeys'])


def test_reserve_ignores_the_instrument_it_does_not_deploy(root, registry):
    write_records(root, [make_record(i, instrument_sha='f' * 64) for i in range(30)])
    assert cohorts.reserve(root, registry, T_RESERVE, 1) == {'status': 'held', 'reason': 'no_records'}


def test_reserve_dedupes_live_and_backfill_copies_of_one_occurrence(root, registry):
    recs = disagreements(19)
    twin = make_record(0, basis='backfill', stratum='fired')           # same session/prompt/ts as record 0
    assert twin['occurrenceKey'] == recs[0]['occurrenceKey']
    write_records(root, recs + [twin])
    result = cohorts.reserve(root, registry, T_RESERVE, 1)
    assert (result['reason'], result['available'], result['eligible']) == ('insufficient_disagreements', 19, 19)


def test_reserved_event_validates_and_freezes_the_policy_hashes_and_registry_numbers(root, registry):
    write_records(root, disagreements(45))
    result, event = reserve_cohort(root, registry, seed=7)
    contract.validate_cohort_event(event)
    assert event['policy'] == 'cosign-v1' and event['policySha256'] == contract.policy_sha256('cosign-v1')
    assert event['instrumentSha256'] == instrument.instrument_sha256() and event['layaRevision'] == LAYA_REV
    assert (event['lambda'], event['alpha'], event['attempt'], event['target'], event['stratum']) == (
        1, 0.05, 1, 20, 'disagreement')
    assert len(set(event['occurrenceKeys'])) == 20


def test_reserve_is_deterministic_for_a_seed_and_independent_of_file_order(tmp_path, registry):
    recs = disagreements(50)
    results = []
    for name, ordered, seed in (('a', recs, 5), ('b', list(reversed(recs)), 5), ('c', recs, 6)):
        root = tmp_path / name
        write_records(root, ordered)
        _, event = reserve_cohort(root, registry, seed=seed)
        results.append(event['occurrenceKeys'])
    assert results[0] == results[1] and results[0] != results[2]


def test_reserve_sidecar_records_the_inclusion_probability(root, registry):
    write_records(root, disagreements(45))
    result, event = reserve_cohort(root, registry)
    assert result['inclusionProbability'] == pytest.approx(20 / 45)
    meta = cohorts.read_cohort_meta(root, event['cohortId'])
    assert meta['inclusionProbability'] == pytest.approx(20 / 45) and meta['eligible'] == 45 and meta['target'] == 20
    path = cohorts.meta_path(root, event['cohortId'])
    assert stat.S_IMODE(path.stat().st_mode) == 0o600 and stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert cohorts.read_cohort_meta(root, 'f' * 32) is None


def test_reserve_dry_run_writes_nothing(root, registry):
    write_records(root, disagreements(45))
    before = tree_snapshot(root)
    result = cohorts.reserve(root, registry, T_RESERVE, 1, dry_run=True)
    assert result['status'] == 'would_reserve' and result['attempt'] == 1
    assert tree_snapshot(root) == before


def test_a_second_cohort_needs_the_first_one_consumed_and_uses_fresh_cases_and_half_alpha(root, registry):
    recs = disagreements(45)
    write_records(root, recs)
    _, first = reserve_cohort(root, registry, seed=1)
    assert cohorts.reserve(root, registry, T_RESERVE, 2) == {'status': 'held', 'reason': 'open_cohort',
                                                              'cohortId': first['cohortId']}
    label_cohort(root, first, by_key(recs), not_hit=min_pass_x(20) - 1)       # one short of passing
    assert cohorts.evaluate(root, registry, first['cohortId'], T_EVAL)['verdict'] == 'fail'
    _, second = reserve_cohort(root, registry, seed=2, now='2026-10-11T07:00:00Z')
    assert second['attempt'] == 2 and second['alpha'] == pytest.approx(0.025)
    assert not set(second['occurrenceKeys']) & set(first['occurrenceKeys'])
    # 45 - 20 = 25 fresh cases remain; after this cohort only 5 are left so a third cannot be formed
    label_cohort(root, second, by_key(recs), not_hit=0)
    assert cohorts.evaluate(root, registry, second['cohortId'], '2026-10-11T08:00:00Z')['verdict'] == 'fail'
    assert cohorts.reserve(root, registry, T_RESERVE, 3)['reason'] == 'insufficient_disagreements'


# ================================================================ evaluate

def cohort_world(root, registry, n=45):
    recs = disagreements(n)
    write_records(root, recs)
    _, event = reserve_cohort(root, registry)
    return recs, event


def test_evaluate_holds_when_a_reserved_case_is_unlabeled_and_writes_nothing(root, registry):
    recs, event = cohort_world(root, registry)
    labels = label_cohort(root, event, by_key(recs), not_hit=15)
    missing = labels[3]
    path = next((root / SKILL / 'labels').glob('*.jsonl'))
    lines = [ln for ln in path.read_text().splitlines() if json.loads(ln)['occurrenceKey'] != missing['occurrenceKey']]
    path.write_text('\n'.join(lines) + '\n')
    before = tree_snapshot(root)
    result = cohorts.evaluate(root, registry, event['cohortId'], T_EVAL)
    assert (result['status'], result['reason'], result['labeled'], result['reserved']) == ('held', 'incomplete', 19, 20)
    assert tree_snapshot(root) == before
    assert [e['event'] for e in ledger_events(root)] == ['reserve']
    assert not cohorts.receipt_path(root, event['cohortId']).exists()
    assert cohorts.cohort_progress(root, event['cohortId']) == {'reserved': 20, 'labeled': 19, 'complete': False}


def test_pass_fail_boundary_at_the_clopper_pearson_threshold(root, registry):
    pass_x = min_pass_x(20)
    assert pass_x == 15
    for x, verdict in ((pass_x, 'pass'), (pass_x - 1, 'fail')):
        scenario = root / f'x{x}'
        recs, event = cohort_world(scenario, registry)
        label_cohort(scenario, event, by_key(recs), not_hit=x)
        result = cohorts.evaluate(scenario, registry, event['cohortId'], T_EVAL)
        stat_ = result['statistic']
        assert result['verdict'] == verdict and (stat_['n'], stat_['x'], stat_['alpha']) == (20, x, 0.05)
        assert stat_['threshold'] == 0.5 and stat_['bound'] == pytest.approx(cohorts.cp_lower(x, 20, 0.05))
        assert (stat_['bound'] > 0.5) == (verdict == 'pass')


def test_false_fires_and_wrong_suggestions_both_count_as_not_hit(root, registry):
    recs, event = cohort_world(root, registry)
    lookup = by_key(recs)
    labels = []
    for index, key in enumerate(sorted(event['occurrenceKeys'])):
        rec = lookup[key]
        acceptable = [ALT1] if index < 8 else ([] if index < 16 else [INC])     # wrong / false fire / hit
        labels.append(make_label(rec, acceptable=acceptable, cohort_id=event['cohortId']))
    write_labels(root, labels)
    result = cohorts.evaluate(root, registry, event['cohortId'], T_EVAL)
    assert result['counts'] == {'labeled': 20, 'ambiguous': 0, 'hit': 4, 'notHit': 16}
    receipt = json.loads(cohorts.receipt_path(root, event['cohortId']).read_text())
    assert (receipt['wrong'], receipt['falseFire']) == (8, 8)


def test_ambiguity_above_the_limit_holds_the_cohort_but_still_spends_it(root, registry):
    recs, event = cohort_world(root, registry)
    label_cohort(root, event, by_key(recs), not_hit=15, ambiguous=5)       # 25% > 20%
    result = cohorts.evaluate(root, registry, event['cohortId'], T_EVAL)
    assert result['status'] == 'consumed' and result['verdict'] == 'held' and result['holdReasons'] == ['ambiguity']
    assert result['statistic']['bound'] is None and result['statistic']['n'] == 20   # ambiguous stay in n
    assert [e['event'] for e in ledger_events(root)] == ['reserve', 'labeled', 'consumed']
    assert cohorts.evaluate(root, registry, event['cohortId'], T_EVAL)['status'] == 'refused'


def test_ambiguity_at_exactly_the_limit_is_tested(root, registry):
    recs, event = cohort_world(root, registry)
    # 20% ambiguity is allowed; ambiguous cases count in n (never in x), so the pass needs the n=20 threshold
    label_cohort(root, event, by_key(recs), not_hit=min_pass_x(20), ambiguous=4)
    result = cohorts.evaluate(root, registry, event['cohortId'], T_EVAL)
    assert result['verdict'] == 'pass' and result['statistic']['n'] == 20 and result['counts']['ambiguous'] == 4


def test_ambiguous_cases_are_conservative_and_cannot_rescue_a_cohort(root, registry):
    recs, event = cohort_world(root, registry)
    # min_pass_x(16) misses among 16 unambiguous cases would pass if ambiguity were dropped from n; it must not
    label_cohort(root, event, by_key(recs), not_hit=min_pass_x(16), ambiguous=4)
    result = cohorts.evaluate(root, registry, event['cohortId'], T_EVAL)
    if min_pass_x(16) < min_pass_x(20):
        assert result['verdict'] == 'fail' and result['statistic']['n'] == 20


def test_unavailable_laya_above_five_percent_holds_the_cohort(tmp_path, registry):
    timeouts_of = lambda k_count: [make_record(100 + k, status='timeout', ts=f'2026-10-10T00:10:{10 + k}.000Z')
                                   for k in range(k_count)]
    # timeouts inside the cohort's own time window: 1/21 = 4.8% passes the limit
    root = tmp_path / 'timeouts-1'
    recs = disagreements(20)
    write_records(root, recs + timeouts_of(1))
    _, event = reserve_cohort(root, registry)
    label_cohort(root, event, by_key(recs), not_hit=18)
    assert cohorts.evaluate(root, registry, event['cohortId'], T_EVAL)['verdict'] == 'pass'
    # 3/23 = 13% is known before labeling: reserve refuses, writes nothing and spends no alpha
    root = tmp_path / 'timeouts-3'
    write_records(root, recs + timeouts_of(3))
    held = cohorts.reserve(root, registry, '2026-10-11T00:00:00Z', 1)
    assert held['status'] == 'held' and held['reason'] == 'laya_unavailable'
    assert held['share'] == pytest.approx(3 / 23) and cohorts.cohort_ledger(root) == {}
    # defense in depth: failures that land in the window after reserve still hold the cohort at evaluation
    root = tmp_path / 'late-timeouts'
    write_records(root, recs)
    _, event = reserve_cohort(root, registry)
    assert event['attempt'] == 1
    write_records(root, timeouts_of(3))
    label_cohort(root, event, by_key(recs), not_hit=18)
    late = cohorts.evaluate(root, registry, event['cohortId'], T_EVAL)
    assert late['verdict'] == 'held' and late['holdReasons'] == ['laya_unavailable']
    receipt = json.loads(cohorts.receipt_path(root, late['cohortId']).read_text())
    assert receipt['unavailable']['unavailable'] == 3 and receipt['unavailable']['total'] == 23


def test_skipped_laya_calls_do_not_count_as_unavailable():
    recs = disagreements(20)
    skipped = make_record(100, basis='backfill', incumbent=None, stratum='silent_sample', status='skipped',
                          shortlist=[], ts='2026-10-10T00:10:30.000Z')
    assert skipped['laya']['status'] == 'skipped'
    window = (locked_io.utc('2026-10-10T00:00:00Z'), locked_io.utc('2026-10-10T23:59:59Z'))
    stats = cohorts.unavailable_stats(recs + [skipped], cohorts.key_of(recs[0]), *window)
    assert stats == {'total': 20, 'unavailable': 0, 'share': 0.0}


def test_evaluation_happens_exactly_once_and_leaves_a_hash_bound_receipt(root, registry):
    recs, event = cohort_world(root, registry)
    label_cohort(root, event, by_key(recs), not_hit=17)
    first = cohorts.evaluate(root, registry, event['cohortId'], T_EVAL)
    assert first['status'] == 'consumed' and first['verdict'] == 'pass'
    events = ledger_events(root)
    assert [e['event'] for e in events] == ['reserve', 'labeled', 'consumed']
    assert events[1]['counts'] == {'labeled': 20, 'ambiguous': 0, 'hit': 3, 'notHit': 17}
    assert events[2]['receiptSha256'] == first['receiptSha256']

    path = cohorts.receipt_path(root, event['cohortId'])
    assert hashlib.sha256(path.read_bytes()).hexdigest() == first['receiptSha256']
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    receipt = json.loads(path.read_text())
    for field in ('policySha256', 'instrumentSha256', 'layaRevision', 'registrySha256', 'routerSourceSha256',
                  'indexSha256', 'criteriaSha256', 'occurrenceKeysSha256', 'labelsSha256', 'statistic', 'counts'):
        assert receipt[field]
    assert receipt['policySha256'] == event['policySha256'] and receipt['statistic'] == events[2]['statistic']

    # a second look is refused, even with different labels, and changes nothing
    before = tree_snapshot(root)
    write_labels(root, [make_label(by_key(recs)[k], acceptable=[ALT1], cohort_id=event['cohortId'])
                        for k in event['occurrenceKeys']])
    again = cohorts.evaluate(root, registry, event['cohortId'], T_EVAL)
    assert again == {'status': 'refused', 'reason': 'already_consumed', 'verdict': 'pass'}
    after = tree_snapshot(root)
    assert {k: v for k, v in after.items() if not k.startswith(f'{SKILL}/labels')} == {
        k: v for k, v in before.items() if not k.startswith(f'{SKILL}/labels')}
    assert cohorts.evaluate(root, registry, 'e' * 32, T_EVAL) == {'status': 'held', 'reason': 'unknown_cohort'}


def test_a_crash_between_receipt_and_consumed_event_resumes_without_a_second_look(root, registry, monkeypatch):
    recs, event = cohort_world(root, registry)
    label_cohort(root, event, by_key(recs), not_hit=16)
    original = records.append

    def crashing(root_arg, decision, kind, obj):
        if obj.get('event') == 'consumed':
            raise Crash()
        return original(root_arg, decision, kind, obj)
    monkeypatch.setattr(records, 'append', crashing)
    with pytest.raises(Crash):
        cohorts.evaluate(root, registry, event['cohortId'], T_EVAL)
    monkeypatch.undo()
    receipt_bytes = cohorts.receipt_path(root, event['cohortId']).read_bytes()
    assert [e['event'] for e in ledger_events(root)] == ['reserve', 'labeled']

    # labels changed after the first look must not change the outcome
    write_labels(root, [make_label(by_key(recs)[k], acceptable=[INC], cohort_id=event['cohortId'])
                        for k in event['occurrenceKeys']])
    result = cohorts.evaluate(root, registry, event['cohortId'], '2026-10-11T09:00:00Z')
    assert result['verdict'] == 'pass' and result['statistic']['x'] == 16
    assert result['receiptSha256'] == hashlib.sha256(receipt_bytes).hexdigest()
    assert cohorts.receipt_path(root, event['cohortId']).read_bytes() == receipt_bytes
    assert [e['event'] for e in ledger_events(root)] == ['reserve', 'labeled', 'consumed']


def test_only_the_first_label_per_reserved_case_in_this_cohort_counts(root, registry):
    recs, event = cohort_world(root, registry)
    lookup = by_key(recs)
    label_cohort(root, event, lookup, not_hit=16)
    keys = sorted(event['occurrenceKeys'])
    extra = [make_label(lookup[keys[0]], acceptable=[INC], cohort_id=event['cohortId'])]        # later duplicate
    outsider = next(r for r in recs if r['occurrenceKey'] not in event['occurrenceKeys'])
    extra.append(make_label(outsider, acceptable=[ALT1], cohort_id=event['cohortId']))        # not a reserved case
    extra.append(make_label(lookup[keys[1]], acceptable=[INC], cohort_id='d' * 32))           # another cohort
    write_labels(root, extra)
    result = cohorts.evaluate(root, registry, event['cohortId'], T_EVAL)
    assert result['statistic']['x'] == 16 and result['counts']['labeled'] == 20


def test_receipts_are_published_atomically_and_never_overwritten(root, registry, tmp_path):
    target = tmp_path / 'out' / 'receipt.json'
    locked_io.write_private_exclusive(target, b'{"a":1}\n')
    with pytest.raises(FileExistsError):
        locked_io.write_private_exclusive(target, b'{"a":2}\n')
    assert target.read_bytes() == b'{"a":1}\n' and stat.S_IMODE(target.stat().st_mode) == 0o600
    assert [p.name for p in target.parent.iterdir()] == ['receipt.json']          # no temp leftovers

    recs, event = cohort_world(root, registry)
    label_cohort(root, event, by_key(recs), not_hit=16)
    cohorts.receipt_path(root, event['cohortId']).parent.mkdir(parents=True)
    cohorts.receipt_path(root, event['cohortId']).write_text('unreadable receipt')
    assert cohorts.evaluate(root, registry, event['cohortId'], T_EVAL) == {'status': 'held', 'reason': 'receipt_conflict'}
    assert [e['event'] for e in ledger_events(root)] == ['reserve']


def test_evaluate_dry_run_writes_nothing(root, registry):
    recs, event = cohort_world(root, registry)
    label_cohort(root, event, by_key(recs), not_hit=16)
    before = tree_snapshot(root)
    result = cohorts.evaluate(root, registry, event['cohortId'], T_EVAL, dry_run=True)
    assert result['status'] == 'would_consume' and result['verdict'] == 'pass'
    assert tree_snapshot(root) == before


# ================================================================ demotion

def live_cosign_disagreements(start, n, **kwargs):
    return [make_record(start + k, mode='cosign', ts=f'2026-10-{5 + k % 6:02d}T10:{k % 60:02d}:05.000Z', **kwargs)
            for k in range(n)]


def label_all(root, recs, *, wrong, ambiguous=0, basis_cohort=None, stratum='disagreement'):
    labels = []
    for index, rec in enumerate(recs):
        if index < ambiguous:
            labels.append(make_label(rec, acceptable=[], ambiguous=True, stratum=stratum, inclusion=0.5))
        elif index < ambiguous + wrong:
            labels.append(make_label(rec, acceptable=[ALT1], stratum=stratum, inclusion=0.5))
        else:
            labels.append(make_label(rec, acceptable=[INC], stratum=stratum, inclusion=0.5))
    write_labels(root, labels)


def test_quality_demotion_needs_minimum_labels_and_a_confident_upper_bound(tmp_path, registry):
    cases = {}
    for name, n, wrong in (('confident', 12, 0), ('too_few', 9, 0), ('unclear', 12, 6), ('wrong_often', 12, 10)):
        scenario = tmp_path / name
        go_cosign(scenario, registry=registry)
        recs = live_cosign_disagreements(0, n)
        write_records(scenario, recs)
        label_all(scenario, recs, wrong=wrong)
        state, _ = reg.read_state(scenario, registry)
        cases[name] = cohorts.demotion_check(scenario, registry, state, NOW)
    assert cases['confident']['demote'] and cases['confident']['reason'] == 'demoted_quality'
    quality = cases['confident']['quality']
    assert quality['n'] == 12 and quality['x'] == 0 and quality['upperBound'] == pytest.approx(cohorts.cp_upper(0, 12, 0.1))
    assert quality['upperBound'] < 0.5
    for other in ('too_few', 'unclear', 'wrong_often'):
        assert not cases[other]['demote'], other
    assert cases['too_few']['quality']['n'] == 9


def test_quality_demotion_only_counts_live_cosign_disagreements_in_the_window(root, registry):
    go_cosign(root, since='2026-08-01T00:00:00Z', registry=registry)
    good = live_cosign_disagreements(0, 12)                                        # in window, incumbent right
    stale = [make_record(50 + k, mode='cosign', ts=f'2026-09-1{k % 9}T10:00:05.000Z') for k in range(15)]   # >14 days
    shadow = [make_record(80 + k, mode='shadow', ts=f'2026-10-{5 + k % 6:02d}T11:{k:02d}:05.000Z') for k in range(15)]
    backfill = [make_record(120 + k, basis='backfill') for k in range(15)]
    agree = [make_record(150 + k, mode='cosign', choice=INC, ts=f'2026-10-{5 + k % 6:02d}T12:{k:02d}:05.000Z')
             for k in range(15)]
    write_records(root, good + stale + shadow + backfill + agree)
    for group in (stale, shadow, backfill, agree):
        label_all(root, group, wrong=len(group))     # all "incumbent wrong": would force a demotion if they counted
    label_all(root, good, wrong=0)
    state, _ = reg.read_state(root, registry)
    check = cohorts.demotion_check(root, registry, state, NOW)
    assert check['demote'] and check['quality']['n'] == 12 and check['quality']['x'] == 0


def test_quality_demotion_ignores_ambiguous_and_pre_promotion_records(root, registry):
    go_cosign(root, since='2026-10-08T00:00:00Z', registry=registry)
    before_promotion = live_cosign_disagreements(0, 12)                            # ts 2026-10-05..10-10, mixed
    before_promotion = [r for r in before_promotion if r['ts'] < '2026-10-08']
    after = [make_record(60 + k, mode='cosign', ts=f'2026-10-09T10:{k:02d}:05.000Z') for k in range(12)]
    write_records(root, before_promotion + after)
    label_all(root, before_promotion, wrong=0)
    label_all(root, after, wrong=0, ambiguous=5)                                    # 7 unambiguous < minLabeled 10
    state, _ = reg.read_state(root, registry)
    check = cohorts.demotion_check(root, registry, state, NOW)
    assert before_promotion and not check['demote']
    assert check['quality']['n'] == 7 and check['quality']['ambiguous'] == 5


def test_harness_labels_never_feed_the_demotion_test(root, registry):
    go_cosign(root, since='2026-10-01T00:00:00Z', registry=registry)
    recs = live_cosign_disagreements(0, 12)
    write_records(root, recs)
    write_labels(root, [contract.validate_label(fixture_harness(rec)) for rec in recs])    # incumbent "wrong" for all
    state, _ = reg.read_state(root, registry)
    assert cohorts.demotion_check(root, registry, state, NOW)['quality']['n'] == 0


def live_ops_records(start, n, status, **kwargs):
    return [make_record(start + k, mode='cosign', status=status, ts=f'2026-10-11T{8 + k % 12:02d}:{k % 60:02d}:05.000Z',
                        choice=INC, **kwargs) for k in range(n)]


def test_operational_demotion_counts_unavailable_invalid_identity_and_redirect_but_not_timeouts(tmp_path, registry):
    scenarios = {
        'outage': live_ops_records(0, 22, 'ok') + live_ops_records(100, 4, 'unavailable') + live_ops_records(200, 1, 'invalid'),
        'mixed_failures': (live_ops_records(0, 22, 'ok') + live_ops_records(100, 1, 'unavailable')
                           + live_ops_records(200, 1, 'invalid') + live_ops_records(300, 1, 'identity_failed')
                           + live_ops_records(400, 1, 'redirect_refused')),
        'timeouts_only': live_ops_records(0, 22, 'ok') + live_ops_records(100, 8, 'timeout'),
        'healthy': live_ops_records(0, 40, 'ok'),
        'tiny_sample': live_ops_records(0, 5, 'ok') + live_ops_records(100, 5, 'unavailable'),
    }
    results = {}
    for name, recs in scenarios.items():
        scenario = tmp_path / name
        go_cosign(scenario, registry=registry)
        write_records(scenario, recs)
        state, _ = reg.read_state(scenario, registry)
        results[name] = cohorts.demotion_check(scenario, registry, state, NOW)
    assert results['outage']['demote'] and results['outage']['reason'] == 'demoted_operational'
    assert results['outage']['operational']['failures'] == 5 and results['outage']['operational']['total'] == 27
    assert results['mixed_failures']['reason'] == 'demoted_operational'      # 4/26 = 15.4%
    assert not results['timeouts_only']['demote']
    assert results['timeouts_only']['operational']['timeouts'] == 8
    assert results['timeouts_only']['operational']['timeoutShare'] == pytest.approx(8 / 30)
    assert results['timeouts_only']['operational']['failures'] == 0
    assert not results['healthy']['demote'] and not results['tiny_sample']['demote']


def test_operational_window_is_three_days_and_starts_at_the_promotion(root, registry):
    go_cosign(root, since='2026-10-11T22:00:00Z', registry=registry)
    old_outage = [make_record(k, mode='cosign', status='unavailable', ts=f'2026-10-0{1 + k % 5}T10:{k:02d}:05.000Z')
                  for k in range(30)]                                              # older than 3 days
    before_promotion = live_ops_records(100, 30, 'unavailable')                    # 10-11 08:00..19:xx < 22:00 since
    write_records(root, old_outage + before_promotion + live_ops_records(300, 30, 'ok', ))
    state, _ = reg.read_state(root, registry)
    check = cohorts.demotion_check(root, registry, state, '2026-10-12T12:00:00Z')
    assert not check['demote'] and check['operational']['total'] == 0


def test_latency_is_report_only_for_the_first_days_then_enforced(tmp_path, registry):
    slow = live_ops_records(0, 25, 'ok', latency=900.0)                            # p90 900 ms > 800 ms budget
    timeouts = live_ops_records(100, 3, 'timeout', latency=800.0)
    fresh, mature = tmp_path / 'fresh', tmp_path / 'mature'
    go_cosign(fresh, since='2026-10-07T00:00:00Z', registry=registry)              # 5.5 days before NOW
    go_cosign(mature, since='2026-09-20T00:00:00Z', registry=registry)             # 22 days before NOW
    for scenario in (fresh, mature):
        write_records(scenario, slow + timeouts)
    fresh_check = cohorts.demotion_check(fresh, registry, reg.read_state(fresh, registry)[0], NOW)
    mature_check = cohorts.demotion_check(mature, registry, reg.read_state(mature, registry)[0], NOW)
    assert fresh_check['latency']['breach'] and fresh_check['latency']['reportOnly'] and not fresh_check['demote']
    assert fresh_check['latency']['p90'] == 900.0 and fresh_check['latency']['n'] == 25     # timeouts excluded
    assert mature_check['latency']['breach'] and not mature_check['latency']['reportOnly']
    assert mature_check['demote'] and mature_check['reason'] == 'demoted_latency'
    assert fresh_check['operational']['timeouts'] == 3


def test_demotion_check_is_a_noop_outside_cosign(root, registry):
    assert cohorts.demotion_check(root, registry, None, NOW) == {'demote': False, 'reason': None, 'skipped': 'not_cosign'}


# ================================================================ HT weights and the report-only alternatives

def pool_label(rec, acceptable, stratum, inclusion):
    return make_label(rec, acceptable=acceptable, stratum=stratum, inclusion=inclusion)


def alt(report, name):
    return next(a for a in report['alternatives'] if a['name'] == name)


def test_horvitz_thompson_weights_and_every_policy_by_hand():
    a = make_record(1, score=5.0, choice=INC)                                      # agreement, router right
    b = make_record(2, score=2.0, choice=ALT1)                                     # disagreement, Laya right
    c = make_record(3, basis='backfill', incumbent=None, stratum='silent_sample', choice=ALT1,
                    shortlist=[ALT1, ALT2])                                        # router silent, Laya picks ALT1 (p 0.7)
    labels = [pool_label(a, [INC], 'agreement', 0.5), pool_label(b, [ALT1], 'disagreement', 0.25),
              pool_label(c, [ALT1], 'silent_laya_pick', 0.1)]
    report = CYCLE.alternatives_report([a, b, c], labels, 1.0, seed=3, instrument_sha256=instrument.instrument_sha256(),
                                       mode='shadow', resamples=50)
    assert report['status'] == 'ok' and report['labels'] == {
        'used': 3, 'ambiguous': 0, 'unmatched': 0, 'sessions': 3, 'layaRevisions': [LAYA_REV]}
    weights = {'a': 2.0, 'b': 4.0, 'c': 10.0 * CYCLE.SILENT_WEIGHT}
    assert weights == {'a': 2.0, 'b': 4.0, 'c': 200.0}
    expected = {                      # (hits, wrong, false fires)
        'incumbent': (2, 4, 0), 'floor@3': (2, 0, 0), 'floor@3.5': (2, 0, 0), 'cosign-v1': (2, 0, 0),
        'cosign@0.3': (2, 0, 0), 'cosign@0.4': (2, 0, 0), 'cosign@0.5': (2, 0, 0),
        'veto-only': (2, 4, 0), 'swap': (6, 0, 0),
        'router-else-laya@0.3': (202, 4, 0), 'router-else-laya@0.4': (202, 4, 0), 'router-else-laya@0.5': (202, 4, 0)}
    assert {x['name'] for x in report['alternatives']} == set(expected)
    for name, (hits, wrong, false_fires) in expected.items():
        item = alt(report, name)
        assert (item['hits'], item['wrong'], item['falseFires']) == (hits, wrong, false_fires), name
        assert item['utility'] == pytest.approx(hits - (wrong + false_fires)), name
        fires = hits + wrong + false_fires
        assert item['precision'] == pytest.approx(hits / fires), name
        assert item['status'] == 'report_only'
    assert alt(report, 'incumbent')['role'] == 'baseline' and alt(report, 'cosign-v1')['role'] == 'deployable'
    assert alt(report, 'swap')['deltaVsIncumbent']['point'] == pytest.approx(8)
    assert alt(report, 'cosign-v1')['deltaVsCosign']['point'] == 0


def test_cosign_probability_threshold_uses_the_incumbents_own_probability():
    rec = make_record(1, choice=INC, probs=[0.45, 0.35, 0.1, 0.1])               # agree, but INC only 0.45
    label = pool_label(rec, [INC], 'agreement', 1.0)
    report = CYCLE.alternatives_report([rec], [label], 1.0, 1, instrument.instrument_sha256(), 'shadow', resamples=10)
    assert alt(report, 'cosign@0.3')['hits'] == 1 and alt(report, 'cosign@0.4')['hits'] == 1
    assert alt(report, 'cosign@0.5')['hits'] == 0 and alt(report, 'cosign-v1')['hits'] == 1


def test_laya_failures_fall_back_to_the_incumbent_in_every_gated_policy():
    rec = make_record(1, status='timeout')
    report = CYCLE.alternatives_report([rec], [pool_label(rec, [ALT1], 'agreement', 1.0)], 1.0, 1,
                                       instrument.instrument_sha256(), 'shadow', resamples=10)
    for name in ('incumbent', 'cosign-v1', 'cosign@0.5', 'veto-only', 'swap'):
        assert alt(report, name)['wrong'] == 1, name


def pool_world(n_each=20):
    """Router-right high-score fires and router-wrong low-score fires that Laya agrees with."""
    recs, labels = [], []
    for i in range(n_each):
        low = make_record(i, score=2.0, choice=INC)
        high = make_record(1000 + i, score=5.0, choice=INC)
        recs += [low, high]
        labels += [pool_label(low, [ALT1], 'agreement', 0.5), pool_label(high, [INC], 'agreement', 0.5)]
    return recs, labels


def test_a_stricter_floor_that_beats_incumbent_and_cosign_is_only_a_recommendation():
    recs, labels = pool_world()
    report = CYCLE.alternatives_report(recs, labels, 1.0, 11, instrument.instrument_sha256(), 'shadow', resamples=200)
    assert alt(report, 'incumbent')['utility'] == 0 and alt(report, 'cosign-v1')['utility'] == 0
    assert alt(report, 'floor@3')['utility'] == 40 and alt(report, 'floor@3.5')['utility'] == 40
    assert len(report['recommendations']) == 2
    assert 'router score floor to 3' in report['recommendations'][0] and 'supported' in report['recommendations'][0]
    assert 'code review' in report['recommendations'][0]
    verdicts = {row['candidate']: row['verdict'] for row in report['ledger']}
    assert verdicts['floor@3'] == 'recommend' and verdicts['incumbent'] == 'baseline'
    assert verdicts['cosign-v1'] == 'pending_gate' and verdicts['veto-only'] == 'discard'
    deployed = CYCLE.alternatives_report(recs, labels, 1.0, 11, instrument.instrument_sha256(), 'cosign', resamples=20)
    assert {r['candidate']: r['verdict'] for r in deployed['ledger']}['cosign-v1'] == 'deployed'
    # too few labels: no recommendation
    few = CYCLE.alternatives_report(recs[:10], labels[:10], 1.0, 11, instrument.instrument_sha256(), 'shadow', 50)
    assert few['recommendations'] == []


def test_report_is_deterministic_for_a_seed_and_the_bootstrap_depends_on_it():
    recs, labels = [], []
    for i in range(40):
        rec = make_record(i, score=2.0 + (i % 4), choice=INC if i % 3 else ALT1)
        recs.append(rec)
        labels.append(pool_label(rec, [INC] if i % 5 else [ALT1], 'agreement' if i % 3 else 'disagreement', 0.5))
    args = (recs, labels, 1.0)
    sha_ = instrument.instrument_sha256()
    first = CYCLE.alternatives_report(*args, 5, sha_, 'shadow', resamples=300)
    again = CYCLE.alternatives_report(*args, 5, sha_, 'shadow', resamples=300)
    other = CYCLE.alternatives_report(*args, 6, sha_, 'shadow', resamples=300)
    assert json.dumps(first, sort_keys=True) == json.dumps(again, sort_keys=True)
    for a, b in zip(first['alternatives'], other['alternatives']):
        assert (a['hits'], a['wrong'], a['utility']) == (b['hits'], b['wrong'], b['utility'])     # point estimates fixed
    assert [a['ci90'] for a in first['alternatives']] != [a['ci90'] for a in other['alternatives']]
    low, high = alt(first, 'incumbent')['ci90']['utility']
    assert low <= alt(first, 'incumbent')['utility'] <= high or low <= high


def test_report_uses_only_scoreboard_pool_labels_of_the_current_instrument():
    good = make_record(1, score=5.0, choice=INC)
    other_instrument = make_record(2, instrument_sha='f' * 64)
    cohort_case = make_record(3)
    harness_case = make_record(4)
    ambiguous_case = make_record(5)
    labels = [pool_label(good, [INC], 'agreement', 1.0),
              pool_label(other_instrument, [INC], 'agreement', 1.0),
              make_label(cohort_case, acceptable=[ALT1], cohort_id='a' * 32),                       # gate cohort label
              contract.validate_label({**fixture_harness(harness_case)}),
              make_label(ambiguous_case, acceptable=[], ambiguous=True, stratum='agreement', inclusion=1.0),
              pool_label(good, [ALT1], 'agreement', 1.0)]                                          # duplicate key
    report = CYCLE.alternatives_report([good, other_instrument, cohort_case, harness_case, ambiguous_case], labels,
                                       1.0, 1, instrument.instrument_sha256(), 'shadow', resamples=10)
    assert report['labels']['used'] == 1 and report['labels']['unmatched'] == 1
    assert alt(report, 'incumbent')['hits'] == 1.0 and alt(report, 'incumbent')['wrong'] == 0
    empty = CYCLE.alternatives_report([], [], 1.0, 1, instrument.instrument_sha256(), 'shadow')
    assert empty['status'] == 'no_labels' and empty['alternatives'] == [] and empty['recommendations'] == []


def fixture_harness(rec):
    from typed_decision_testkit import fixture
    label = dict(fixture('labels.json')['valid']['harness'])
    label.update({'decisionId': rec['decisionId'], 'occurrenceKey': rec['occurrenceKey'],
                  'candidates': rec['shortlist'], 'acceptable': [ALT1], 'bestSkill': ALT1})
    return label


# ================================================================ the cycle

def run(root, registry, now=NOW, **kwargs):
    return CYCLE.run_cycle(root, now, registry=registry, seed=kwargs.pop('seed', 1), **kwargs)


def action_types(result):
    return result['actions']


def test_cycle_reserves_then_promotes_only_through_a_passed_cosign_v1_cohort(root, registry):
    recs = disagreements(45)
    write_records(root, recs)

    first = run(root, registry, now='2026-10-11T00:00:00Z')
    assert action_types(first) == ['reserve'] and first['mode'] == 'shadow'
    assert reg.read_state(root, registry) == (None, 'missing')              # nothing promotes without evidence
    cohort_id = first['cohorts'][0]['cohortId']
    event = cohorts.cohort_ledger(root)[cohort_id]['reserve']

    waiting = run(root, registry, now='2026-10-11T03:00:00Z')               # still unlabeled: nothing happens
    assert action_types(waiting) == ['reserve_held'] and waiting['mode'] == 'shadow'
    assert reg.read_state(root, registry) == (None, 'missing')

    label_cohort(root, event, by_key(recs), not_hit=min_pass_x(20))
    done = run(root, registry, now='2026-10-11T06:00:00Z')
    assert action_types(done) == ['evaluate', 'promote'] and done['mode'] == 'cosign'
    state, status = reg.read_state(root, registry)
    entry = state['decisions'][SKILL]
    assert status == 'ok' and entry['mode'] == 'cosign' and entry['reason'] == 'gate_passed'
    assert entry['cohortId'] == cohort_id and entry['policySha256'] == contract.policy_sha256('cosign-v1')
    assert entry['instrumentSha256'] == instrument.instrument_sha256() and entry['layaRevision'] == LAYA_REV
    lines, _ = reg.read_audit(root)
    assert [(l['phase'], l['actor'], l['reason'], l['toMode']) for l in lines] == [
        ('intent', 'cycle', 'gate_passed', 'cosign'), ('commit', 'cycle', 'gate_passed', 'cosign')]

    steady = run(root, registry, now='2026-10-11T07:00:00Z')                 # cosign: demotion watch, no new cohort
    assert action_types(steady) == ['demotion_check'] and steady['mode'] == 'cosign'
    assert len(cohorts.cohort_table(root)) == 1
    receipts = sorted((root / SKILL / 'cycles').glob('*.json'))
    assert len(receipts) == 4 and all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in receipts)


def test_a_failed_cohort_leaves_shadow_and_the_cycle_reserves_attempt_two_with_half_the_alpha(root, registry):
    recs = disagreements(45)
    write_records(root, recs)
    first = run(root, registry, now='2026-10-11T00:00:00Z')
    event = cohorts.cohort_ledger(root)[first['cohorts'][0]['cohortId']]['reserve']
    label_cohort(root, event, by_key(recs), not_hit=min_pass_x(20) - 1)
    second = run(root, registry, now='2026-10-11T06:00:00Z')
    assert action_types(second) == ['evaluate', 'reserve'] and second['mode'] == 'shadow'
    assert reg.read_state(root, registry) == (None, 'missing')
    rows = cohorts.cohort_table(root)
    assert [(r['attempt'], r['alpha'], r['status']) for r in rows] == [(1, 0.05, 'consumed'), (2, 0.025, 'awaiting_labels')]
    assert rows[0]['verdict'] == 'fail' and not set(cohorts.cohort_ledger(root)[rows[1]['cohortId']]['reserve'][
        'occurrenceKeys']) & set(event['occurrenceKeys'])


def test_a_held_cohort_never_promotes(root, registry):
    recs = disagreements(45)
    write_records(root, recs)
    first = run(root, registry, now='2026-10-11T00:00:00Z')
    event = cohorts.cohort_ledger(root)[first['cohorts'][0]['cohortId']]['reserve']
    label_cohort(root, event, by_key(recs), not_hit=15, ambiguous=5)
    out = run(root, registry, now='2026-10-11T06:00:00Z')
    assert 'promote' not in action_types(out) and out['mode'] == 'shadow'
    assert reg.read_state(root, registry)[1] == 'missing'


def test_a_pinned_decision_is_report_only_even_with_a_passing_cohort(root, registry):
    recs = disagreements(45)
    write_records(root, recs)
    first = run(root, registry, now='2026-10-11T00:00:00Z')
    event = cohorts.cohort_ledger(root)[first['cohorts'][0]['cohortId']]['reserve']
    label_cohort(root, event, by_key(recs), not_hit=18)
    reg.mutate(root, SKILL, 'shadow', actor='cli', reason='manual_pin', expected_revision=0, pinned=True,
               registry=registry, now='2026-10-11T01:00:00Z')
    state_before = (root / reg.STATE_FILE).read_bytes()
    out = run(root, registry, now='2026-10-11T06:00:00Z')
    assert out['pinned'] and out['actions'] == ['skipped'] and out['mode'] == 'shadow'
    assert (root / reg.STATE_FILE).read_bytes() == state_before
    assert cohorts.cohort_table(root)[0]['status'] == 'awaiting_evaluation'     # not even consumed
    assert out['full']['report']['status'] in ('ok', 'no_labels')
    assert out['full']['actions'] == [{'type': 'skipped', 'reason': 'pinned'}]


def test_off_and_corrupt_states_take_no_action(tmp_path, registry):
    for name in ('off', 'corrupt'):
        root = tmp_path / name
        recs = disagreements(45)
        write_records(root, recs)
        if name == 'off':
            reg.mutate(root, SKILL, 'off', actor='cli', reason='manual_off', expected_revision=0, registry=registry)
        else:
            root.mkdir(exist_ok=True)
            (root / reg.STATE_FILE).write_text('garbage')
        out = run(root, registry)
        assert out['actions'] == ['skipped'] and not list((root / SKILL).glob('cohorts'))
        assert out['mode'] == ('off' if name == 'off' else 'shadow')
        assert (root / reg.STATE_FILE).exists()


def test_a_cohort_of_a_different_laya_revision_is_not_promoted(root, registry):
    recs = disagreements(45)
    write_records(root, recs)
    first = run(root, registry, now='2026-10-11T00:00:00Z')
    event = cohorts.cohort_ledger(root)[first['cohorts'][0]['cohortId']]['reserve']
    label_cohort(root, event, by_key(recs), not_hit=18)
    write_records(root, [make_record(500, laya_revision='newer-rev', ts='2026-10-11T05:00:05.000Z')])   # model changed
    out = run(root, registry, now='2026-10-11T06:00:00Z')
    assert out['actions'][0] == 'skip_cohort' and 'promote' not in out['actions'] and out['mode'] == 'shadow'
    assert cohorts.cohort_table(root)[0]['status'] == 'awaiting_evaluation'


def test_a_cycle_demotes_a_failing_cosign_and_a_pin_prevents_it(tmp_path, registry):
    outcomes = {}
    for name, pin in (('free', False), ('pinned', True)):
        root = tmp_path / name
        go_cosign(root, registry=registry)
        if pin:
            reg.mutate(root, SKILL, 'cosign', actor='cli', reason='manual_pin', expected_revision=1, pinned=True,
                       registry=registry)
        recs = live_cosign_disagreements(0, 12)
        write_records(root, recs)
        label_all(root, recs, wrong=0)
        outcomes[name] = (run(root, registry), reg.read_state(root, registry)[0])
    free, free_state = outcomes['free']
    assert free['actions'][:2] == ['demotion_check', 'demote'] and free['mode'] == 'shadow'
    entry = free_state['decisions'][SKILL]
    assert entry['mode'] == 'shadow' and entry['reason'] == 'demoted_quality' and entry['cohortId'] is None
    lines, _ = reg.read_audit(tmp_path / 'free')
    assert lines[-1]['actor'] == 'cycle' and lines[-1]['fromMode'] == 'cosign' and lines[-1]['toMode'] == 'shadow'
    pinned, pinned_state = outcomes['pinned']
    assert pinned['mode'] == 'cosign' and pinned['actions'] == ['skipped']
    assert pinned_state['decisions'][SKILL]['mode'] == 'cosign'
    assert pinned['full']['demotion']['demote'] is True               # reported, never acted on


def test_statistical_cycle_deploys_only_cosign_v1(root, registry):
    entry = dict(registry['decisions'][SKILL], deployablePolicy='router-floor-3')
    with pytest.raises(ValueError, match='unknown deployable policy'):
        cohorts.deployable_hashes(entry)
    assert set(contract.POLICIES) - {contract.POLICY_ADVISE} == {'cosign-v1', 'credential-cli-v1'}  # advise-v1 is gate-earned, never a cosign policy
    recs = disagreements(45)
    write_records(root, recs)
    out = run(root, registry, now='2026-10-11T00:00:00Z')
    event = cohorts.cohort_ledger(root)[out['cohorts'][0]['cohortId']]['reserve']
    assert event['policy'] == 'cosign-v1'
    label_cohort(root, event, by_key(recs), not_hit=19)
    run(root, registry, now='2026-10-11T06:00:00Z')
    state, _ = reg.read_state(root, registry)
    assert state['decisions'][SKILL]['policySha256'] == contract.policy_sha256('cosign-v1')


def test_report_only_recommendations_never_change_the_registry(root, registry):
    recs, labels = pool_world()
    write_records(root, recs)
    write_labels(root, labels)
    out = run(root, registry)
    assert out['recommendations'] and out['mode'] == 'shadow'
    assert reg.read_state(root, registry) == (None, 'missing')
    assert not (root / reg.AUDIT_FILE).exists()


def test_cycle_receipt_binds_every_version_hash_and_is_private(root, registry):
    write_records(root, disagreements(45))
    out = run(root, registry)
    path = Path(out['receipt'])
    assert path.parent == root / SKILL / 'cycles' and path.name == '20261012T120000Z.json'
    assert stat.S_IMODE(path.stat().st_mode) == 0o600 and stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    receipt = json.loads(path.read_text())
    versions = receipt['versions']
    for field in ('policySha256', 'instrumentSha256', 'routerSourceSha256', 'indexSha256', 'registrySha256'):
        assert len(versions[field]) == 64
    assert versions['layaRevision'] == LAYA_REV and set(versions['sources']) == {'decisionCycle', 'cohorts', 'decisionRegistry'}
    assert receipt['registry'] == {'status': 'missing', 'revision': 0, 'mode': 'shadow', 'pinned': False, 'since': None}
    assert receipt['actions'][0]['type'] == 'reserve' and receipt['dryRun'] is False
    assert receipt['stats']['total'] == 45 and receipt['report']['caveat']
    again = run(root, registry)                                           # same second: a distinct name
    assert Path(again['receipt']).name == '20261012T120000Z_1.json'


def test_dry_run_writes_nothing_and_never_calls_the_mutation_path(root, registry, monkeypatch):
    recs = disagreements(45)
    write_records(root, recs)
    first = run(root, registry, now='2026-10-11T00:00:00Z')
    event = cohorts.cohort_ledger(root)[first['cohorts'][0]['cohortId']]['reserve']
    label_cohort(root, event, by_key(recs), not_hit=19)

    def forbidden(*_a, **_k):
        raise AssertionError('mutation called in dry run')
    monkeypatch.setattr(reg, 'mutate', forbidden)
    monkeypatch.setattr(reg, 'recover', forbidden)
    before = tree_snapshot(root)
    out = CYCLE.run_cycle(root, '2026-10-11T06:00:00Z', dry_run=True, seed=1, registry=registry)
    assert out['dryRun'] and out['receipt'] is None
    assert out['actions'] == ['would_evaluate', 'would_promote']
    assert tree_snapshot(root) == before
    assert cohorts.cohort_table(root)[0]['status'] == 'awaiting_evaluation'


def test_dry_run_on_a_missing_root_creates_nothing(tmp_path, registry):
    root = tmp_path / 'never-created'
    out = CYCLE.run_cycle(root, NOW, dry_run=True, registry=registry)
    assert out['actions'] == ['reserve_held'] and not root.exists()


def test_a_second_cycle_in_flight_is_held_not_interleaved(root, registry):
    holder = locked_io.try_lock(root / SKILL / 'cycle.lock')
    try:
        assert CYCLE.run_cycle(root, NOW, registry=registry) == {'status': 'held', 'reason': 'cycle_busy', 'dryRun': False}
    finally:
        locked_io.release_lock(holder)
    assert CYCLE.run_cycle(root, NOW, registry=registry)['status'] == 'ok'


class WriteSpy:
    """Record every path opened for writing, created or made as a directory while active."""

    def __init__(self, monkeypatch):
        self.paths = []
        real_open, real_mkdir = os.open, os.mkdir
        spy = self

        def open_(path, flags, *args, **kwargs):
            if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT):
                spy.paths.append(os.fspath(path))
            return real_open(path, flags, *args, **kwargs)

        def mkdir_(path, *args, **kwargs):
            spy.paths.append(os.fspath(path))
            return real_mkdir(path, *args, **kwargs)
        self.patches = (open_, mkdir_)
        self.monkeypatch = monkeypatch

    def __enter__(self):
        self.ctx = self.monkeypatch.context()
        mp = self.ctx.__enter__()
        mp.setattr(os, 'open', self.patches[0])
        mp.setattr(os, 'mkdir', self.patches[1])
        return self

    def __exit__(self, *exc):
        return self.ctx.__exit__(*exc)


def test_the_cycle_writes_only_under_its_root(tmp_path, registry, monkeypatch):
    fake_home = tmp_path / 'home'
    fake_home.mkdir()
    monkeypatch.setenv('HOME', str(fake_home))
    monkeypatch.delenv('RHIZE_TYPED_DECISIONS_ROOT', raising=False)
    root = tmp_path / 'data' / 'typed-decisions'
    recs = disagreements(45)
    write_records(root, recs)
    with WriteSpy(monkeypatch) as spy:
        first = run(root, registry, now='2026-10-11T00:00:00Z')                       # recover + reserve + receipt
    event = cohorts.cohort_ledger(root)[first['cohorts'][0]['cohortId']]['reserve']
    label_cohort(root, event, by_key(recs), not_hit=19)
    with spy:
        run(root, registry, now='2026-10-11T06:00:00Z')                               # evaluate + promote (registry write)
        run(root, registry, now='2026-10-11T07:00:00Z')                               # demotion watch
        CYCLE.run_cycle(root, '2026-10-11T08:00:00Z', dry_run=True, registry=registry)
    assert any(p.endswith(reg.STATE_FILE) or reg.STATE_FILE in p for p in spy.paths)
    assert any('cycles' in p for p in spy.paths)
    assert all(Path(p).resolve().is_relative_to(root.resolve()) for p in spy.paths), spy.paths
    assert not any('workflow-selection' in p for p in spy.paths)
    assert not (fake_home / '.local' / 'share' / 'rhize' / 'workflow-selection').exists()
    assert list(fake_home.rglob('*')) == []


MODULES = ('decision_registry', 'cohorts', 'scoreboard', 'locked_io')


def string_constants_outside_docstrings(path: Path):
    import ast
    tree = ast.parse(path.read_text(encoding='utf-8'))
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
            first = node.body[0] if node.body else None
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                docstrings.add(id(first.value))
    strings, imports = [], []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
            strings.append(node.value)
        elif isinstance(node, ast.Import):
            imports += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            imports += [node.module or ''] + [alias.name for alias in node.names]
    return strings, imports


def test_no_module_of_the_cycle_references_the_workflow_v2_pilot():
    paths = [REPO / 'evals' / 'typed-decision' / 'decision_cycle.py'] + [
        SCRIPTS_DIR / f'{name}.py' for name in MODULES]
    forbidden = ('workflow-selection', 'workflow_selection', 'decision_pilot', 'pilot_cycle', 'pilot_labels',
                 'pilot_autolabel', 'pilot_routing')
    for path in paths:
        strings, imports = string_constants_outside_docstrings(path)
        for text in strings + imports:
            assert not any(word in text for word in forbidden), (path.name, text)


def test_cli_run_uses_the_env_root_and_prints_a_compact_summary(tmp_path):
    env_root = tmp_path / 'envroot'
    home = tmp_path / 'home'
    home.mkdir()
    write_records(env_root, disagreements(65))
    (env_root / 'laya-runtime.json').write_text(json.dumps({'revision': LAYA_REV}))
    env = {**os.environ, 'HOME': str(home), 'RHIZE_TYPED_DECISIONS_ROOT': str(env_root)}
    dry = subprocess.run([sys.executable, str(CYCLE_CLI), 'run', '--dry-run', '--now', NOW, '--seed', '7'],
                         capture_output=True, text=True, timeout=120, env=env)
    assert dry.returncode == 0, dry.stderr
    summary = json.loads(dry.stdout)
    assert summary['dryRun'] and summary['actions'] == ['would_reserve'] and summary['receipt'] is None
    assert not (env_root / SKILL / 'cohorts').exists()
    live = subprocess.run([sys.executable, str(CYCLE_CLI), 'run', '--now', NOW, '--seed', '7'],
                          capture_output=True, text=True, timeout=120, env=env)
    summary = json.loads(live.stdout)
    assert live.returncode == 0 and summary['actions'] == ['reserve'] and Path(summary['receipt']).is_file()
    assert summary['cohorts'][0]['status'] == 'awaiting_labels'
    assert list(home.rglob('*')) == []
    bad = subprocess.run([sys.executable, str(CYCLE_CLI), 'run', '--now', 'not-a-time'], capture_output=True,
                         text=True, timeout=120, env=env)
    assert bad.returncode == 2 and json.loads(bad.stdout)['status'] == 'error'


# ================================================================ final-review fixes (Fable, 2026-10-11)

def test_effective_mode_reads_a_stale_cosign_binding_as_shadow(root, registry):
    go_cosign(root, registry=registry)
    state, status = reg.read_state(root, registry)
    assert reg.effective_mode(SKILL, registry, state, status, LAYA_REV) == 'cosign'
    assert reg.effective_mode(SKILL, registry, state, status, 'other-rev') == 'shadow'       # new checkpoint
    assert reg.binding_stale(SKILL, registry, state['decisions'][SKILL], 'other-rev') == 'laya_revision_changed'
    stale = json.loads(json.dumps(state))
    stale['decisions'][SKILL]['instrumentSha256'] = 'f' * 64                                 # an update changed it
    assert reg.effective_mode(SKILL, registry, stale, 'ok', LAYA_REV) == 'shadow'
    assert reg.binding_stale(SKILL, registry, stale['decisions'][SKILL], LAYA_REV) == 'binding_stale'


def test_cycle_makes_a_stale_cosign_state_honest_and_resumes_gating(root, registry):
    go_cosign(root, registry=registry)
    (root / 'laya-runtime.json').write_text(json.dumps({'revision': 'new-rev'}))            # checkpoint swapped
    write_records(root, disagreements(45, laya_revision='new-rev'))
    result = run(root, registry)
    assert result['actions'][:2] == ['demote', 'reserve'] and result['mode'] == 'shadow'
    entry = reg.read_state(root, registry)[0]['decisions'][SKILL]
    assert entry['mode'] == 'shadow' and entry['reason'] == 'laya_revision_changed'
    reserve = [e for e in ledger_events(root) if e['event'] == 'reserve'][-1]
    assert reserve['layaRevision'] == 'new-rev'


def test_reserve_holds_when_the_laya_revision_is_unknown(root, registry):
    write_records(root, disagreements(45, laya_revision='unknown'))
    assert cohorts.reserve(root, registry, T_RESERVE, 1) == {'status': 'held', 'reason': 'laya_revision_unknown'}


def test_held_cohorts_spend_alpha(root, registry):
    recs = disagreements(45)
    write_records(root, recs)
    _, first = reserve_cohort(root, registry, seed=1)
    label_cohort(root, first, by_key(recs), not_hit=0, ambiguous=10)                         # 50% ambiguous
    assert cohorts.evaluate(root, registry, first['cohortId'], T_EVAL)['verdict'] == 'held'
    _, second = reserve_cohort(root, registry, seed=2, now='2026-10-11T07:00:00Z')
    assert second['attempt'] == 2 and second['alpha'] == pytest.approx(0.025)


def test_a_passed_cohort_whose_promotion_failed_is_promoted_by_the_next_cycle(root, registry, monkeypatch):
    recs = disagreements(45)
    event, _ = passed_cohort(root, registry, recs)
    real = reg.mutate
    calls = {'n': 0}

    def flaky(*args, **kwargs):
        calls['n'] += 1
        if calls['n'] == 1:
            raise reg.RegistryError('lock_timeout', 'simulated')
        return real(*args, **kwargs)

    monkeypatch.setattr(reg, 'mutate', flaky)
    first = run(root, registry)
    assert reg.effective_mode(SKILL, registry, *reg.read_state(root, registry), LAYA_REV) == 'shadow'
    second = run(root, registry)
    assert 'retry_promotion' in second['actions'] and second['mode'] == 'cosign'
    entry = reg.read_state(root, registry)[0]['decisions'][SKILL]
    assert entry['cohortId'] == event['cohortId'] and entry['reason'] == 'gate_passed'
    # once promoted (and later demoted) the same cohort is never applied again
    assert event['cohortId'] in CYCLE._cohorts_ever_promoted(root)


RUN0 = '0' * 16          # make_record's decisionId f'{i:032x}' starts with this run id for small i


def from_run(recs, run_id):
    """Backfill records answered by run `run_id` (their decisionId carries it as a 16-hex prefix)."""
    for rec in recs:
        rec['decisionId'] = run_id + rec['decisionId'][16:]
    return recs


def write_backfill_runs(root, statuses, *, instrument_sha=None, revision=LAYA_REV, append=False, run_id=RUN0):
    runs = root / 'skill-fit' / 'backfill' / 'runs.jsonl'
    runs.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps({'schema': 'rhize-typed-decision-backfill-run-v1', 'at': '2026-10-11T00:00:00Z', 'runId': run_id,
                       'instrumentSha256': instrument_sha or instrument.instrument_sha256(), 'layaRevision': revision,
                       'layaCalls': sum(statuses.values()), 'layaStatuses': statuses}) + '\n'
    with runs.open('a' if append else 'w', encoding='utf-8') as handle:
        handle.write(line)
    return runs


def test_backfill_run_failures_count_toward_the_unavailability_hold(root, registry):
    recs = disagreements(45, basis='backfill', mode='shadow', arm='none')
    write_records(root, recs)
    write_backfill_runs(root, {'ok': 45, 'timeout': 15})
    held = cohorts.reserve(root, registry, '2026-10-11T00:00:00Z', 1)
    assert held['status'] == 'held' and held['reason'] == 'laya_unavailable' and held['share'] == pytest.approx(0.25)


@pytest.mark.parametrize('logged_ok', [None, 20])
def test_backfill_records_without_covering_run_logs_are_left_out_of_the_pool(root, registry, logged_ok):
    """Missing or partial run logs must not read as a zero failure share (Codex final review, round 2)."""
    recs = disagreements(45, basis='backfill', mode='shadow', arm='none')
    write_records(root, recs)
    if logged_ok is not None:
        write_backfill_runs(root, {'ok': logged_ok})
    held = cohorts.reserve(root, registry, '2026-10-11T00:00:00Z', 1)
    assert held == {'status': 'held', 'reason': 'insufficient_disagreements', 'available': 0, 'eligible': 0,
                    'target': 20, 'backfillExcluded': 45}
    # live disagreements are still eligible on their own; the uncovered backfill rows simply sit out
    live = disagreements(20, start=100)
    write_records(root, live)
    result, event = reserve_cohort(root, registry)
    assert result['backfillExcluded'] == 45 and set(event['occurrenceKeys']) == {r['occurrenceKey'] for r in live}


def test_backfill_coverage_matches_run_logs_on_instrument_and_revision_only(root, registry):
    """Answered calls logged under another revision cannot mask missing logs for this one."""
    recs = disagreements(45, basis='backfill', mode='shadow', arm='none')
    write_records(root, recs)
    key = cohorts.key_of(recs[0])
    write_backfill_runs(root, {'ok': 45}, revision='other-revision')
    assert len(cohorts.backfill_coverage(cohorts.load_records(root)[0], key, root)[0]) == 45
    write_backfill_runs(root, {'ok': 45}, append=True)
    uncovered, runs = cohorts.backfill_coverage(cohorts.load_records(root)[0], key, root)
    assert uncovered == set() and runs['answeredRecords'] == 45 and runs['runsLogged'] == 1


def test_backfill_coverage_is_reconciled_per_run_not_in_aggregate(root, registry):
    """Codex round 3: other runs' answered-call counts cannot vouch for a run whose log is missing."""
    run_a, run_b, run_c = 'a' * 16, 'b' * 16, 'c' * 16
    logged = from_run(disagreements(30, basis='backfill', mode='shadow', arm='none'), run_a)
    unlogged = from_run(disagreements(15, start=30, basis='backfill', mode='shadow', arm='none'), run_c)
    write_records(root, logged + unlogged)
    write_backfill_runs(root, {'ok': 30}, run_id=run_a)
    write_backfill_runs(root, {'ok': 30}, run_id=run_b, append=True)      # 60 logged answers >= 45 records in aggregate
    uncovered, runs = cohorts.backfill_coverage(cohorts.load_records(root)[0], cohorts.key_of(logged[0]), root)
    assert uncovered == {r['occurrenceKey'] for r in unlogged} and runs['uncoveredRecords'] == 15
    result, event = reserve_cohort(root, registry)
    assert result['backfillExcluded'] == 15
    assert set(event['occurrenceKeys']) <= {r['occurrenceKey'] for r in logged}
    # a run log without a run id vouches for nothing
    legacy = root / 'skill-fit' / 'backfill' / 'runs.jsonl'
    legacy.write_text(json.dumps({'instrumentSha256': instrument.instrument_sha256(), 'layaRevision': LAYA_REV,
                                  'layaStatuses': {'ok': 99}}) + '\n')
    assert len(cohorts.backfill_coverage(cohorts.load_records(root)[0], cohorts.key_of(logged[0]), root)[0]) == 45


def test_a_covered_backfill_cohort_passes_and_a_vanished_run_log_still_holds_it(tmp_path, registry):
    for vanish in (False, True):
        root = tmp_path / f'vanish-{vanish}'
        recs = disagreements(45, basis='backfill', mode='shadow', arm='none')
        write_records(root, recs)
        runs = write_backfill_runs(root, {'ok': 45})
        _, event = reserve_cohort(root, registry)
        if vanish:
            runs.unlink()                                   # deleted between reserve and evaluation
        label_cohort(root, event, by_key(recs), not_hit=len(event['occurrenceKeys']))
        result = cohorts.evaluate(root, registry, event['cohortId'], T_EVAL)
        if vanish:
            assert result['verdict'] == 'held' and result['holdReasons'] == ['backfill_runs_missing']
        else:
            assert result['verdict'] == 'pass' and result['holdReasons'] == []


def test_gate_shares_are_frozen_at_reserve(root, registry):
    recs = disagreements(45)
    write_records(root, recs)
    _, event = reserve_cohort(root, registry)
    loosened = json.loads(json.dumps(registry))
    loosened['decisions'][SKILL]['gates']['promote']['maxAmbiguousShare'] = 0.9               # edited after reserve
    label_cohort(root, event, by_key(recs), not_hit=0, ambiguous=10)
    assert cohorts.evaluate(root, loosened, event['cohortId'], T_EVAL)['verdict'] == 'held'


# ================================================================ advise (majority-baseline gate)

ROUTING, CRITICAL_DECISION = 'model-routing', 'devflow-next-action'
OPEN_PROBE = lambda: None  # noqa: E731 - Laya is reachable


def label_of(i):
    return CHOICE_IDS[i % 3]


def fill(root, decision, count=120, *, start=0, critical=False, wrong=(), policy=CHOICE_POLICY, ambiguous=()):
    """`count` labelled choice records; labels cycle over three classes and Laya agrees except at the `wrong` indices."""
    ids = []
    for i in range(start, start + count):
        laya = label_of(i + 1) if i in wrong else label_of(i)
        result = write_choice(root, decision, i, laya=laya, critical=critical, policy=policy)
        write_choice_label(root, decision, result['decisionId'], label_of(i), ambiguous=i in ambiguous)
        ids.append(result['decisionId'])
    return ids


def advise_pass(root, decision=ROUTING, **kwargs):
    kwargs.setdefault('probe', OPEN_PROBE)
    return CYCLE.run_cycle(root, NOW, seed=1, **kwargs)['advise'][decision]


def state_of(root, decision):
    state, _ = reg.read_state(root)
    return ((state or {}).get('decisions') or {}).get(decision)


def backdate(root, decision, decision_id, ts, **changes):
    path = root / decision / 'choice' / f'{decision_id}.json'
    record = {**json.loads(path.read_text()), 'ts': ts, **changes}
    path.write_text(json.dumps(record))


def treatment_index(decision, start):
    return next(i for i in range(start, start + 500) if not typed_advice.holdback(decision, f'key-{i}'))


def test_a_passing_gate_promotes_to_advise_and_the_runtime_reader_honours_it(root):
    fill(root, ROUTING)
    result = advise_pass(root)
    assert result['verdict'] == 'pass' and result['registry']['status'] == 'mutated' and result['earnedMode'] == 'advise'
    entry = state_of(root, ROUTING)
    events = advise_ledger.read(root, ROUTING)
    assert [e['event'] for e in events] == ['reserve', 'consumed'] and events[1]['verdict'] == 'pass'
    policy = typed_advice.policy_sha256(ROUTING, 'Which option fits this request?', CHOICE_POLICY)
    assert entry['mode'] == 'advise' and entry['cohortId'] == events[0]['cohortId']
    assert (entry['policySha256'], entry['instrumentSha256'], entry['layaRevision']) == (
        policy, typed_advice.INSTRUMENT_SHA256, LAYA_REV)
    assert typed_advice.effective_mode(ROUTING, policy, root) == 'advise'          # the surface reader agrees
    assert typed_advice.effective_mode(ROUTING, '0' * 64, root) == 'shadow'        # another policy does not
    again = write_choice(root, ROUTING, 9000, laya='alpha')                          # next record is stamped advise
    assert again['mode'] == 'advise'
    assert 'workflow-fit' not in CYCLE.run_cycle(root, NOW, seed=1, probe=OPEN_PROBE)['advise']


def test_critical_decisions_need_ten_critical_cases_and_zero_critical_misses(root):
    fill(root, CRITICAL_DECISION, critical=True)
    result = advise_pass(root, CRITICAL_DECISION)
    assert result['verdict'] == 'pass' and result['stats']['criticalCases'] >= 10 and result['stats']['criticalMisses'] == 0
    assert state_of(root, CRITICAL_DECISION)['mode'] == 'advise' and state_of(root, CRITICAL_DECISION)['pinned'] is False


def test_a_critical_miss_in_the_cohort_holds(root):
    fill(root, CRITICAL_DECISION, critical=True, wrong=set(range(0, 120, 2)))
    result = advise_pass(root, CRITICAL_DECISION)
    assert result['verdict'] == 'hold' and 'critical_miss' in result['reasons'] and state_of(root, CRITICAL_DECISION) is None
    assert advise_ledger.read(root, CRITICAL_DECISION)[1]['verdict'] == 'hold'


def test_without_enough_critical_cases_a_critical_decision_holds(root):
    fill(root, CRITICAL_DECISION, critical=False)
    result = advise_pass(root, CRITICAL_DECISION)
    assert result['verdict'] == 'hold' and 'critical_cases_below_minimum' in result['reasons']


def test_no_labelled_cases_is_a_hold_that_touches_nothing(root):
    before = tree_snapshot(root)
    result = CYCLE.run_cycle(root, NOW, seed=1, dry_run=True, probe=OPEN_PROBE)['advise']
    assert all(v['status'] == 'held' for v in result.values()) and set(result) == set(
        d for d, e in reg.load_registry()['decisions'].items() if e['advise'] and d != 'workflow-fit')
    assert tree_snapshot(root) == before and not (root / ROUTING).exists()
    fill(root, ROUTING, count=20)
    held = advise_pass(root)
    assert held['status'] == 'held' and held['reason'] == 'insufficient_promotion_cases' and advise_ledger.read(root, ROUTING) == []


def test_a_laya_outage_holds_before_a_cohort_is_reserved(root):
    fill(root, ROUTING)

    def down():
        raise OSError('connection refused')
    result = advise_pass(root, probe=down)
    assert result['status'] == 'held' and result['reason'] == 'laya_unavailable'
    assert advise_ledger.read(root, ROUTING) == [] and state_of(root, ROUTING) is None


def test_pins_off_and_cosign_suppress_the_advise_pass(root):
    fill(root, ROUTING)
    reg.mutate(root, ROUTING, 'off', actor='cli', reason='kill_switch', expected_revision=0)
    assert advise_pass(root)['reason'] == 'mode_off'
    reg.mutate(root, ROUTING, 'shadow', actor='cli', reason='pin_it', expected_revision=1, pinned=True)
    assert advise_pass(root)['reason'] == 'pinned' and advise_ledger.read(root, ROUTING) == []


def test_a_registry_refusal_is_recorded_not_raised(root, monkeypatch):
    fill(root, ROUTING)

    def refuse(*args, **kwargs):
        raise reg.RegistryError('stale_revision', 'raced')
    monkeypatch.setattr(reg, 'mutate', refuse)
    result = advise_pass(root)
    assert result['verdict'] == 'pass' and result['registry'] == {'status': 'held', 'to': 'advise', 'code': 'stale_revision'}
    assert result['earnedMode'] == 'shadow'


def test_a_corrupt_ledger_is_one_recorded_hold_not_a_crash(root):
    fill(root, ROUTING)
    (root / ROUTING).mkdir(exist_ok=True)
    (root / ROUTING / 'advise-cohorts.jsonl').write_text(json.dumps({'event': 'reserve', 'decision': ROUTING}) + '\n')
    result = advise_pass(root)
    assert result['status'] == 'held' and result['reason'] == 'error'


def test_only_the_current_homogeneous_cohort_feeds_the_gate(root):
    old = fill(root, ROUTING, count=90, policy='old|policy', wrong=set(range(90)))      # a retired policy, all wrong
    for decision_id in old:
        backdate(root, ROUTING, decision_id, '2026-10-01T00:00:00Z')
    foreign = fill(root, ROUTING, count=30, start=500)
    for decision_id in foreign:
        backdate(root, ROUTING, decision_id, '2026-10-05T00:00:00Z', instrumentSha256='f' * 64)
    stale_rev = fill(root, ROUTING, count=30, start=700)
    for decision_id in stale_rev:
        backdate(root, ROUTING, decision_id, '2026-10-06T00:00:00Z', layaRevision='older-checkpoint')
    fill(root, ROUTING, count=120, start=1000)
    result = advise_pass(root)
    reserved = advise_ledger.read(root, ROUTING)[0]['caseIds']
    assert result['verdict'] == 'pass' and not set(reserved) & set(old + foreign + stale_rev)
    assert result['stats']['n'] == len(reserved) and result['stats']['accuracy'] == 1.0


def test_ambiguous_labels_are_excluded(root):
    unclear = fill(root, ROUTING, count=90, start=2000, wrong=set(range(2000, 2090)), ambiguous=set(range(2000, 2090)))
    fill(root, ROUTING, count=120)
    result = advise_pass(root)
    reserved = advise_ledger.read(root, ROUTING)[0]['caseIds']
    assert result['verdict'] == 'pass' and result['stats']['accuracy'] == 1.0 and not set(reserved) & set(unclear)


def test_earned_advise_is_demoted_after_two_evaluations_below_baseline(root):
    fill(root, ROUTING)
    assert advise_pass(root)['earnedMode'] == 'advise'
    policy = state_of(root, ROUTING)['policySha256']
    baseline = advise_ledger.read(root, ROUTING)[0]['baseline']
    other = next(c for c in CHOICE_IDS if c != baseline)
    index = [treatment_index(ROUTING, 5000)]

    def batch(n):                                   # advise-arm treatment cases where Laya misses the baseline class
        for _ in range(n):
            i = treatment_index(ROUTING, index[0])
            index[0] = i + 1
            result = write_choice(root, ROUTING, i, laya=other)
            assert result['mode'] == 'advise' and result['recommendation']['id'] == other
            write_choice_label(root, ROUTING, result['decisionId'], baseline)
    batch(5)
    quiet = advise_pass(root)
    assert quiet['branch'] == 'demotion' and quiet['demotion']['evaluated'] is False and quiet['earnedMode'] == 'advise'
    batch(7)
    first = advise_pass(root)
    assert first['demotion']['evaluated'] is True and first['demotion']['below'] is True and first['earnedMode'] == 'advise'
    batch(10)
    second = advise_pass(root)
    assert second['demotion']['demote'] is True and second['registry']['reason'] == 'gate_demote'
    assert state_of(root, ROUTING)['mode'] == 'shadow' and typed_advice.effective_mode(ROUTING, policy, root) == 'shadow'
    assert reg.read_audit(root)[0][-1]['reason'] == 'gate_demote'


def test_a_live_critical_miss_demotes_at_once(root):
    fill(root, CRITICAL_DECISION, critical=True)
    assert advise_pass(root, CRITICAL_DECISION)['earnedMode'] == 'advise'
    i = treatment_index(CRITICAL_DECISION, 7000)
    result = write_choice(root, CRITICAL_DECISION, i, laya='alpha', critical=True)
    write_choice_label(root, CRITICAL_DECISION, result['decisionId'], 'beta')
    outcome = advise_pass(root, CRITICAL_DECISION)
    assert outcome['demotion']['reason'] == 'critical_miss' and outcome['registry']['reason'] == 'critical_miss'
    assert state_of(root, CRITICAL_DECISION)['mode'] == 'shadow'


def test_a_changed_laya_checkpoint_resets_to_shadow_and_forces_a_new_gate(root):
    fill(root, ROUTING)
    advise_pass(root)
    (root / 'laya-runtime.json').write_text(json.dumps({'revision': 'newer-checkpoint'}))
    result = advise_pass(root)
    assert state_of(root, ROUTING)['mode'] == 'shadow' and state_of(root, ROUTING)['reason'] == 'binding_stale'
    assert result['status'] == 'held'                           # the old records belong to the old checkpoint


def test_skill_fit_earns_advise_from_its_own_records_with_the_fixed_policy_hash(root, registry):
    recs = []
    for i in range(120):
        recs.append(make_record(i, choice=[INC, ALT1, ALT2][i % 3], incumbent=INC))
    write_records(root, recs)
    write_labels(root, [make_label(r, acceptable=[r['laya']['choice']], stratum='agreement') for r in recs])
    result = CYCLE.run_cycle(root, NOW, registry=registry, seed=1, probe=OPEN_PROBE)['advise']['skill-fit']
    assert result['verdict'] == 'pass' and result['registry']['status'] == 'mutated', result
    entry = state_of(root, 'skill-fit')
    instrument_hash = reg.advise_instrument_sha256('laya-choice-v1')
    assert entry['mode'] == 'advise' and entry['instrumentSha256'] == instrument_hash
    assert entry['policySha256'] == CYCLE.skill_advise_policy_sha256(instrument_hash)
    assert reg.effective_mode('skill-fit', registry, *reg.read_state(root, registry), LAYA_REV) == 'advise'


def test_the_skill_fit_cosign_path_is_unchanged_by_the_advise_pass(root, registry):
    write_records(root, disagreements(45))
    plain = CYCLE.run_cycle(root, NOW, registry=registry, seed=1, dry_run=True, advise=False)
    with_advise = CYCLE.run_cycle(root, NOW, registry=registry, seed=1, dry_run=True, probe=OPEN_PROBE)
    assert 'advise' not in plain and {k: v for k, v in with_advise.items() if k != 'advise'} == plain
    assert plain['actions'] == ['would_reserve']


# ---- advise and cosign are earned separately (plan §3: gates are per target mode)

def skill_in_advise(root, registry):
    """skill-fit already on the earned advise mode (CLI manual override, like go_cosign)."""
    instrument_hash = reg.advise_instrument_sha256('laya-choice-v1')
    return reg.mutate(root, SKILL, 'advise', actor='cli', reason='manual_override', expected_revision=0, registry=registry,
                      now='2026-10-01T00:00:00Z',
                      binding={'policySha256': CYCLE.skill_advise_policy_sha256(instrument_hash),
                               'instrumentSha256': instrument_hash, 'layaRevision': LAYA_REV, 'cohortId': None})


def test_skill_fit_in_advise_still_reserves_evaluates_and_promotes_a_cosign_cohort(root, registry):
    recs = disagreements(45)
    write_records(root, recs)
    skill_in_advise(root, registry)
    first = run(root, registry, now='2026-10-11T00:00:00Z', advise=False)
    assert action_types(first) == ['reserve'] and first['mode'] == 'advise'
    event = cohorts.cohort_ledger(root)[first['cohorts'][0]['cohortId']]['reserve']
    label_cohort(root, event, by_key(recs), not_hit=min_pass_x(20))
    done = run(root, registry, now='2026-10-11T06:00:00Z', advise=False)
    assert action_types(done) == ['evaluate', 'promote'] and done['mode'] == 'cosign'
    entry = state_of(root, SKILL)
    assert entry['mode'] == 'cosign' and entry['reason'] == 'gate_passed' and entry['cohortId'] == event['cohortId']
    assert entry['policySha256'] == contract.policy_sha256('cosign-v1')


def test_a_failed_cosign_cohort_leaves_an_earned_advise_in_place(root, registry):
    recs = disagreements(45)
    write_records(root, recs)
    skill_in_advise(root, registry)
    first = run(root, registry, now='2026-10-11T00:00:00Z', advise=False)
    event = cohorts.cohort_ledger(root)[first['cohorts'][0]['cohortId']]['reserve']
    label_cohort(root, event, by_key(recs), not_hit=min_pass_x(20) - 1)
    second = run(root, registry, now='2026-10-11T06:00:00Z', advise=False)
    assert action_types(second) == ['evaluate', 'reserve'] and second['mode'] == 'advise'
    assert state_of(root, SKILL)['mode'] == 'advise' and state_of(root, SKILL)['reason'] == 'manual_override'


def test_an_advise_pass_never_yields_cosign_and_a_cosign_never_yields_advise(root, registry):
    recs = [make_record(i, choice=[INC, ALT1, ALT2][i % 3], incumbent=INC) for i in range(120)]
    write_records(root, recs)
    write_labels(root, [make_label(r, acceptable=[r['laya']['choice']], stratum='agreement') for r in recs])
    earned = run(root, registry, now='2026-10-11T00:00:00Z', probe=OPEN_PROBE)
    assert earned['advise'][SKILL]['earnedMode'] == 'advise' and 'promote' not in action_types(earned)
    assert state_of(root, SKILL)['mode'] == 'advise'
    later = run(root, registry, now='2026-10-11T01:00:00Z', probe=OPEN_PROBE)      # the open, unlabeled cosign cohort
    assert 'promote' not in action_types(later) and state_of(root, SKILL)['mode'] == 'advise'


def test_a_promoted_cosign_suppresses_the_skill_fit_advise_pass(root, registry):
    go_cosign(root, registry=registry)
    result = run(root, registry, probe=OPEN_PROBE)['advise'][SKILL]
    assert result == {'status': 'held', 'reason': 'mode_cosign'} and state_of(root, SKILL)['mode'] == 'cosign'
