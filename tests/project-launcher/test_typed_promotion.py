"""advise-v1 majority-baseline gate; invented fixtures, no live Laya."""
import hashlib
import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('typed_promotion', ROOT / 'evals/typed-decision/typed_promotion.py')
tp = importlib.util.module_from_spec(spec); spec.loader.exec_module(tp)
from typed_decisions import advise_ledger  # noqa: E402  (typed_promotion put the scripts dir on sys.path)

PRIOR = {'general': 80, 'content': 10, 'none': 10}
P2 = {'general': 80, 'content': 20}
D = 'workflow-fit'
POLICY, INSTRUMENT = 'a' * 64, 'b' * 64


def gate(cases, alpha=0.10, prior=PRIOR, **kwargs):
    return tp.evaluate(cases, baseline='general', alpha=alpha, prior=prior, min_cohort=30, min_coverage=0.9, **kwargs)


def g80(cases, **kwargs):
    return gate(cases, prior=P2, **kwargs)


def make(spec_counts, start=0):
    """spec_counts: [(label, choice, count)] or (label, choice, count, status) -> evaluate() cases, one group each."""
    cases, index = [], start
    for item in spec_counts:
        label, choice, count = item[:3]
        for _ in range(count):
            cases.append({'id': f'case-{index}', 'group': f'group-{index}', 'label': label, 'choice': choice,
                          'status': item[3] if len(item) > 3 else 'ok', 'critical_if_wrong': False})
            index += 1
    return cases


def eighty(correct_minority):
    """30 cases, two classes: the always-general baseline is right on 24 (80%); Laya is right on all of general
    plus `correct_minority` of the 6 content cases and answers general on the rest."""
    return make([('general', 'general', 24), ('content', 'content', correct_minority),
                 ('content', 'general', 6 - correct_minority)])


def test_split_is_a_stable_one_third_promotion_hash_split():
    groups = [f'session:{i}' for i in range(3000)]
    promotion = [g for g in groups if tp.split_of(g) == 'promotion']
    assert 900 < len(promotion) < 1100
    assert all(tp.split_of(g) == ('promotion' if int(hashlib.sha256(('split:' + g).encode()).hexdigest(), 16) % 3 == 2
                                  else 'tuning') for g in groups[:50])


def test_majority_ties_resolve_to_the_smallest_label():
    assert tp.majority(['b', 'a', 'a', 'b']) == 'a' and tp.majority(['z', 'a', 'z']) == 'z' and tp.majority([]) is None


def test_passes_at_28_of_30_and_holds_at_27_against_an_80_percent_baseline():
    # Laya's margin over the baseline is b (minority cases it gets right) since it never errs on the majority class:
    # b=4 (28/30) is the smallest paired margin that clears alpha=.10 at n=30, b=3 (27/30) cannot.
    four = g80(eighty(4))
    assert four['verdict'] == 'pass' and four['reasons'] == []
    assert four['stats']['b'] == 4 and four['stats']['c'] == 0 and four['stats']['baselineAccuracy'] == 0.8
    assert four['stats']['accuracy'] == 28 / 30 and four['stats']['cpLower'] > 0.5
    five = g80(eighty(5))
    assert five['verdict'] == 'pass' and five['stats']['cpLower'] > four['stats']['cpLower']
    three = g80(eighty(3))
    assert three['verdict'] == 'hold' and three['reasons'] == ['sign_test_not_significant']
    assert three['stats']['cpLower'] < 0.5 and three['stats']['accuracy'] == 27 / 30


def test_a_smaller_alpha_needs_a_larger_margin():
    assert g80(eighty(4), alpha=0.10)['verdict'] == 'pass'
    assert g80(eighty(4), alpha=0.05)['verdict'] == 'hold'       # attempt 2 spends alpha/2
    assert g80(eighty(5), alpha=0.05)['verdict'] == 'pass'


def test_a_regression_on_the_baseline_class_counts_against_laya():
    cases = make([('general', 'general', 20), ('general', 'none', 4), ('content', 'content', 3),
                  ('none', 'none', 3)])                              # b=6, c=4
    result = gate(cases)
    assert result['stats']['b'] == 6 and result['stats']['c'] == 4 and result['verdict'] == 'hold'
    assert 'sign_test_not_significant' in result['reasons']


def test_abstention_and_unavailable_count_as_wrong():
    cases = eighty(4)
    cases[24]['choice'] = None                                     # the first content case: abstains
    result = g80(cases)
    assert result['verdict'] == 'hold' and result['stats']['b'] == 3
    cases = eighty(4)
    cases[24]['status'] = 'unavailable'                            # an answer that arrived with a failed status
    assert g80(cases)['stats']['b'] == 3
    cases = make([('general', 'general', 23), ('general', None, 1), ('content', 'content', 3), ('none', 'none', 3)])
    assert gate(cases)['stats']['c'] == 1                          # abstaining on a baseline-right case is a regression


def test_coverage_below_ninety_percent_holds_even_with_a_clear_margin():
    cases = make([('general', 'general', 27), ('general', None, 3), ('content', 'content', 5), ('none', 'none', 5)])
    result = gate(cases)
    assert result['stats']['coverage'] == pytest.approx(37 / 40) and 'coverage_below_minimum' not in result['reasons']
    cases = make([('general', 'general', 26), ('general', None, 5), ('content', 'content', 5), ('none', 'none', 4)])
    result = gate(cases)
    assert 'coverage_below_minimum' in result['reasons'] and result['stats']['coverage'] < 0.9
    assert result['verdict'] == 'hold'
    unavailable = make([('general', 'general', 26), ('general', 'general', 5, 'unavailable'),
                        ('content', 'content', 5), ('none', 'none', 4)])
    assert 'coverage_below_minimum' in gate(unavailable)['reasons']


def test_cohort_needs_thirty_cases_from_thirty_groups():
    assert 'cohort_too_small' in g80(eighty(5)[:29])['reasons']
    cases = eighty(5)
    for case in cases[:5]:
        case['group'] = 'shared'
    assert 'too_few_groups' in g80(cases)['reasons']


def test_class_coverage_and_recall_are_enforced_for_classes_with_prior_share():
    cases = make([('general', 'general', 26), ('content', 'content', 3), ('none', 'none', 2)])
    assert 'class_coverage:none' in gate(cases)['reasons']
    cases = make([('general', 'general', 24), ('content', 'content', 3), ('none', 'none', 1), ('none', 'general', 2)])
    result = gate(cases)
    assert 'class_recall:none' in result['reasons'] and result['stats']['recall']['none'] == pytest.approx(1 / 3)
    # A class under the 10% prior floor is not scored, so its thin coverage is not a blocker.
    cases = make([('general', 'general', 25), ('content', 'content', 4), ('none', 'none', 1)])
    thin = tp.evaluate(cases, baseline='general', alpha=0.10, prior={'general': 90, 'content': 7, 'none': 3},
                       min_cohort=30, min_coverage=0.9)
    assert not [r for r in thin['reasons'] if r.startswith('class_')]


def test_balanced_accuracy_must_beat_the_baselines_and_is_computed():
    lazy = [{**c, 'choice': 'general'} for c in eighty(5)]
    result = g80(lazy)
    assert result['verdict'] == 'hold' and 'balanced_accuracy_not_above_baseline' in result['reasons']
    assert result['stats']['balancedAccuracy'] == pytest.approx(0.5)
    assert result['stats']['baselineBalancedAccuracy'] == pytest.approx(0.5)
    # K is the number of classes actually present in the cohort.
    two = make([('general', 'general', 24), ('content', 'content', 6)])
    assert gate(two)['stats']['baselineBalancedAccuracy'] == pytest.approx(0.5)


def critical_cohort(critical_ids=10):
    cases = make([('general', 'general', 32), ('content', 'content', 4), ('none', 'none', 4)])
    for case in cases[:critical_ids]:
        case['critical_if_wrong'] = True
    return cases


def test_critical_decisions_need_ten_critical_cases_and_no_critical_miss():
    assert gate(critical_cohort(10), critical=True, min_critical=10)['verdict'] == 'pass'
    few = gate(critical_cohort(9), critical=True, min_critical=10)
    assert few['verdict'] == 'hold' and few['reasons'] == ['critical_cases_below_minimum']
    cases = critical_cohort(10)
    cases[0]['choice'] = 'content'                                 # answered, wrong, critical
    miss = gate(cases, critical=True, min_critical=10)
    assert miss['verdict'] == 'hold' and 'critical_miss' in miss['reasons'] and miss['stats']['criticalMisses'] == 1
    # The same data is fine for a decision that is not critical.
    assert gate(cases)['stats']['criticalMisses'] == 1 and 'critical_miss' not in gate(cases)['reasons']


def test_abstaining_or_unavailable_on_a_critical_case_is_a_critical_miss():
    for change in ({'choice': None}, {'status': 'unavailable'}, {'choice': 'content'}):
        cases = critical_cohort(10)
        cases[0].update(change)
        result = gate(cases, critical=True, min_critical=10)
        assert result['verdict'] == 'hold' and 'critical_miss' in result['reasons'] and result['stats']['criticalMisses'] == 1
    assert gate(cases)['stats']['criticalMisses'] == 1                 # counted, but only a critical decision holds on it


def test_ten_unanswered_critical_cases_among_ninety_correct_ones_hold():
    cases = make([('general', 'general', 90), ('general', None, 10)])
    for case in cases[-10:]:
        case['critical_if_wrong'] = True
    result = tp.evaluate(cases, baseline='general', alpha=0.10, prior={'general': 100}, min_cohort=30, min_coverage=0.9,
                         critical=True, min_critical=10)
    assert result['stats']['coverage'] == 0.9 and result['stats']['criticalMisses'] == 10
    assert result['verdict'] == 'hold' and 'critical_miss' in result['reasons']


def test_a_cohort_missing_a_tuning_class_holds_even_when_every_case_is_right():
    # all 40 cohort cases are 'relaxed' and Laya is perfect, but 'full' is 40% of the tuning prior and has no case
    cases = make([('relaxed', 'relaxed', 40)])
    prior = {'relaxed': 60, 'full': 40}
    result = tp.evaluate(cases, baseline='relaxed', alpha=0.10, prior=prior, min_cohort=30, min_coverage=0.9)
    assert result['verdict'] == 'hold' and 'class_coverage:full' in result['reasons']
    two = tp.evaluate(make([('relaxed', 'relaxed', 38), ('full', 'full', 2)]), baseline='relaxed', alpha=0.10,
                      prior=prior, min_cohort=30, min_coverage=0.9)
    assert 'class_coverage:full' in two['reasons']
    # a class under the 10% prior share is not required
    assert not [r for r in tp.evaluate(cases, baseline='relaxed', alpha=0.10, prior={'relaxed': 95, 'full': 5},
                                       min_cohort=30, min_coverage=0.9)['reasons'] if r.startswith('class_')]


def test_a_repeated_group_holds_as_duplicate_groups():
    cases = eighty(5)
    cases[1]['group'] = cases[0]['group']                         # 30 cases, 29 groups
    result = g80(cases)
    assert result['verdict'] == 'hold' and {'duplicate_groups', 'too_few_groups'} <= set(result['reasons'])


def test_empty_cohort_never_passes():
    result = gate([])
    assert result['verdict'] == 'hold' and 'cohort_too_small' in result['reasons']


# ------------------------------------------------------------------ demotion

def live(right, wrong, start=0):
    return make([('general', 'general', right), ('general', 'content', wrong)], start=start)


def test_critical_miss_demotes_immediately_whatever_the_fresh_count():
    cases = live(29, 0)
    cases[3]['critical_if_wrong'] = True
    cases[3]['choice'] = 'content'
    result = tp.demotion(cases, 0, [False], baseline='general', critical=True)
    assert result['demote'] is True and result['reason'] == 'critical_miss' and result['history'] == []
    assert tp.demotion(cases, 0, [], baseline='general', critical=False)['demote'] is False


def test_critical_miss_scans_every_shown_critical_case_not_only_the_window():
    window = live(30, 0, start=100)                                 # a clean window of 30
    old_miss = {'id': 'old', 'group': 'g-old', 'label': 'general', 'choice': 'content', 'status': 'ok', 'critical_if_wrong': True}
    assert tp.demotion(window, 0, [], baseline='general', critical=True)['demote'] is False
    scanned = tp.demotion(window, 0, [], baseline='general', critical=True, scan_cases=[old_miss] + window)
    assert scanned['demote'] is True and scanned['reason'] == 'critical_miss'
    for answer in ({'choice': None}, {'status': 'unavailable', 'choice': None}):
        assert tp.demotion(window, 0, [], baseline='general', critical=True,
                           scan_cases=[{**old_miss, **answer}])['demote'] is True      # not answering is a miss too
    assert tp.demotion(window, 0, [], baseline='general', critical=False, scan_cases=[old_miss])['demote'] is False


def test_nothing_is_scored_until_ten_fresh_labels_exist():
    result = tp.demotion(live(10, 20), 9, [True], baseline='general')
    assert result == {'demote': False, 'reason': None, 'evaluated': False, 'history': [True]}


def test_two_consecutive_evaluations_below_the_baseline_demote():
    below = live(10, 20)                                            # laya .33 vs baseline 1.0 on these cases
    first = tp.demotion(below, 10, [], baseline='general')
    assert first['demote'] is False and first['evaluated'] and first['below'] is True and first['history'] == [True]
    second = tp.demotion(below, 10, first['history'], baseline='general')
    assert second['demote'] is True and second['reason'] == 'below_baseline_consecutive' and second['history'] == []


def test_a_recovered_evaluation_resets_the_streak():
    ok = tp.demotion(live(30, 0), 10, [True], baseline='general')
    assert ok['demote'] is False and ok['below'] is False and ok['history'] == [True, False]
    again = tp.demotion(live(10, 20), 10, ok['history'], baseline='general')
    assert again['demote'] is False and again['history'] == [True, False, True]


def test_only_the_latest_window_is_scored():
    cases = live(0, 30) + live(30, 0, start=100)                    # old failures, then a clean window
    result = tp.demotion(cases, 10, [], baseline='general', window=30)
    assert result['n'] == 30 and result['accuracy'] == 1.0 and result['below'] is False


# ------------------------------------------------------------------ attempts

def pool(count, start=0):
    """`count` promotion-split cases; labels general 80% / content 10% / none 10%."""
    cases, index = [], start
    while len(cases) < count:
        group = f'session-{index}'
        index += 1
        if tp.split_of(group) != 'promotion':
            continue
        position = len(cases) % 10
        label = 'general' if position < 8 else 'content' if position == 8 else 'none'
        cases.append({'id': f'c-{group}', 'group': group, 'label': label, 'critical_if_wrong': False})
    return cases


def attempt(root, cases, predict_one=None, policy=POLICY, revision='rev-1', **kwargs):
    return tp.run_attempt(root, D, cases, policy_sha=policy, instrument_sha=INSTRUMENT, laya_revision=revision,
                          gate_cfg=kwargs.pop('gate_cfg', None), prior=PRIOR, baseline='general',
                          predict_one=predict_one or (lambda case: case['label']), now='2026-10-16T00:00:00Z',
                          **{'probe': lambda: True, **kwargs})


def test_a_clean_attempt_reserves_then_consumes_a_pass_and_verifies(tmp_path):
    cases = pool(40)
    seen = []
    def predict(case):
        seen.append([e['event'] for e in advise_ledger.read(tmp_path, D)])
        return case['label']
    receipt = attempt(tmp_path, cases, predict)
    assert receipt['status'] == 'evaluated' and receipt['verdict'] == 'pass' and receipt['attempt'] == 1
    assert set(map(tuple, seen)) == {('reserve',)}                 # the reservation precedes every Laya call
    events = advise_ledger.read(tmp_path, D)
    assert [e['event'] for e in events] == ['reserve', 'consumed']
    assert events[0]['caseIds'] == sorted(c['id'] for c in cases) and events[0]['baseline'] == 'general'
    assert events[1]['receiptSha256'] == receipt['receiptSha256'] and events[1]['verdict'] == 'pass'
    advise_ledger.verify_pass(tmp_path, D, {'cohortId': receipt['cohortId'], 'policySha256': POLICY,
                                            'instrumentSha256': INSTRUMENT, 'layaRevision': 'rev-1'})
    stored = json.loads((tmp_path / D / 'advise-receipts' / (receipt['cohortId'] + '.json')).read_text())
    assert tp.sha256(stored) == receipt['receiptSha256']


def test_alpha_halves_per_attempt_and_attempts_count_across_policy_changes(tmp_path):
    first = attempt(tmp_path, pool(35))
    second = attempt(tmp_path, pool(35, start=10_000), policy='c' * 64, revision='rev-2')
    third = attempt(tmp_path, pool(35, start=20_000), policy='d' * 64, revision='rev-2')
    assert [first['attempt'], second['attempt'], third['attempt']] == [1, 2, 3]
    assert [first['alpha'], second['alpha'], third['alpha']] == [0.10, 0.05, 0.025]
    assert third['stats']['alpha'] == 0.025 and advise_ledger.next_attempt(tmp_path, D) == 4
    assert advise_ledger.next_attempt(tmp_path, 'procedure-pick') == 1


def test_consumed_case_ids_are_never_reused(tmp_path):
    cases = pool(60)
    first = attempt(tmp_path, cases)
    reserved = set(advise_ledger.consumed_case_ids(tmp_path, D))
    assert first['status'] == 'evaluated' and reserved == {c['id'] for c in cases}
    again = attempt(tmp_path, cases)                                # every case is spent
    assert again == {'status': 'held', 'reason': 'insufficient_promotion_cases', 'available': 0, 'required': 30}
    fresh = pool(35, start=50_000)
    assert attempt(tmp_path, cases + fresh)['status'] == 'evaluated'
    assert len(advise_ledger.consumed_case_ids(tmp_path, D)) == 60 + 35


def test_a_hold_is_consumed_too_and_cannot_be_used_as_a_pass(tmp_path):
    receipt = attempt(tmp_path, pool(40), lambda case: 'general')
    assert receipt['verdict'] == 'hold' and advise_ledger.read(tmp_path, D)[-1]['verdict'] == 'hold'
    with pytest.raises(ValueError, match='did not pass'):
        advise_ledger.verify_pass(tmp_path, D, {'cohortId': receipt['cohortId'], 'policySha256': POLICY,
                                                'instrumentSha256': INSTRUMENT, 'layaRevision': 'rev-1'})


def test_below_the_cohort_floor_touches_nothing(tmp_path):
    held = attempt(tmp_path, pool(29))
    assert held['status'] == 'held' and held['available'] == 29 and held['required'] == 30
    assert advise_ledger.read(tmp_path, D) == [] and not (tmp_path / D).exists()


def test_an_unavailable_laya_holds_before_reserving_so_no_cohort_or_alpha_is_spent(tmp_path):
    def down():
        raise ConnectionRefusedError('laya down')
    calls = []
    held = attempt(tmp_path, pool(40), lambda case: calls.append(case) or case['label'], probe=down)
    assert held == {'status': 'held', 'reason': 'laya_unavailable'} and calls == []
    assert advise_ledger.read(tmp_path, D) == [] and not (tmp_path / D).exists()
    receipt = attempt(tmp_path, pool(40), probe=lambda: True)      # the same cases are still unspent at attempt 1
    assert receipt['status'] == 'evaluated' and receipt['attempt'] == 1 and receipt['alpha'] == 0.10


def test_the_probe_is_mandatory_and_must_return_true(tmp_path):
    assert tp.probe_ok(lambda: True) is True
    for bad in (None, lambda: None, lambda: False, lambda: 'ok', lambda: 1, lambda: (_ for _ in ()).throw(OSError('down'))):
        assert tp.probe_ok(bad) is False
        held = attempt(tmp_path, pool(40), probe=bad)
        assert held == {'status': 'held', 'reason': 'laya_unavailable'}
        assert not (tmp_path / D).exists()
    with pytest.raises(TypeError):                                  # no default: a caller cannot forget it
        tp.run_attempt(tmp_path, D, pool(40), policy_sha=POLICY, instrument_sha=INSTRUMENT, laya_revision='rev-1',
                       gate_cfg=None, prior=PRIOR, baseline='general', predict_one=lambda c: c['label'])


def test_only_promotion_split_groups_are_eligible(tmp_path):
    cases = pool(40)
    tuning, index = [], 0
    while len(tuning) < 20:
        group = f'tuning-{index}'
        index += 1
        if tp.split_of(group) == 'tuning':
            tuning.append({'id': f'c-{group}', 'group': group, 'label': 'general', 'critical_if_wrong': False})
    receipt = attempt(tmp_path, cases + tuning)
    assert receipt['stats']['n'] == 40
    assert not {c['id'] for c in tuning} & advise_ledger.consumed_case_ids(tmp_path, D)


def test_laya_failures_count_as_unavailable_not_as_crashes(tmp_path):
    def flaky(case):
        if case['label'] != 'general':
            raise TimeoutError('laya down')
        return 'general'
    receipt = attempt(tmp_path, pool(40), flaky)
    assert receipt['status'] == 'evaluated' and receipt['verdict'] == 'hold'
    assert receipt['stats']['coverage'] == 0.8 and 'coverage_below_minimum' in receipt['reasons']


def test_dry_run_writes_no_ledger_or_receipt(tmp_path):
    receipt = attempt(tmp_path, pool(40), dry_run=True)
    assert receipt['status'] == 'dry_run' and receipt['verdict'] == 'pass' and receipt['dryRun'] is True
    assert not (tmp_path / D).exists()


def test_critical_attempt_needs_ten_trusted_critical_cases(tmp_path):
    cases = pool(40)
    for case in cases[:9]:
        case['critical_if_wrong'] = True
    cfg = {'minCriticalCases': 10}
    held = attempt(tmp_path, cases, critical=True, gate_cfg=cfg)
    assert held['verdict'] == 'hold' and 'critical_cases_below_minimum' in held['reasons']
    more = pool(40, start=70_000)
    for case in more[:10]:
        case['critical_if_wrong'] = True
    assert attempt(tmp_path, more, critical=True, gate_cfg=cfg)['verdict'] == 'pass'


def test_status_cli_prints_the_ledger(tmp_path):
    attempt(tmp_path, pool(35))
    done = subprocess.run([sys.executable, str(ROOT / 'evals/typed-decision/typed_promotion.py'), 'status',
                           '--root', str(tmp_path), '--decision', D], text=True, capture_output=True, timeout=20)
    assert done.returncode == 0 and [e['event'] for e in json.loads(done.stdout)] == ['reserve', 'consumed']


# ---- shared cycle plumbing (registry writes and the rolling demotion state)

def test_registry_mutate_records_a_refusal_as_a_hold(tmp_path):
    held = tp.registry_mutate(tmp_path, None, 'no-such-decision', 'shadow', 'gate_demote', 0)
    assert held == {'status': 'held', 'to': 'shadow', 'code': 'unknown_decision'}


def test_demotion_state_round_trips_and_a_dry_run_never_writes_it(tmp_path):
    assert tp.read_demotion_state(tmp_path, D) == ([], set())
    outcome = {'demote': False, 'evaluated': True, 'history': [False], 'reason': None}
    dry = tp.demotion_result(tmp_path, None, D, outcome, ['a', 'b'], expected_revision=0, reason='gate_demote', dry_run=True)
    assert dry['registry'] is None and not (tmp_path / D).exists()
    tp.demotion_result(tmp_path, None, D, outcome, ['b', 'a'], expected_revision=0, reason='gate_demote')
    assert tp.read_demotion_state(tmp_path, D) == ([False], {'a', 'b'})
    quiet = {'demote': False, 'evaluated': False, 'history': [False, True], 'reason': None}
    tp.demotion_result(tmp_path, None, D, quiet, ['c'], expected_revision=0, reason='gate_demote')
    assert tp.read_demotion_state(tmp_path, D) == ([False], {'a', 'b'})              # not evaluated: state untouched


# ---- group is the statistical unit (replay)

def test_one_group_with_many_favourable_cases_counts_once(tmp_path):
    cases = pool(35)
    heavy = []
    for i in range(30):                                            # a 'content' group with 30 more cases
        heavy.append({'id': f'zz-{i}', 'group': cases[8]['group'], 'label': 'content', 'critical_if_wrong': False})
    receipt = attempt(tmp_path, cases + heavy)
    assert receipt['stats']['n'] == 35
    reserved = advise_ledger.read(tmp_path, D)[0]
    assert len(reserved['caseIds']) == len(reserved['groups']) == 35


def test_a_cohort_of_a_few_groups_is_too_small_however_many_cases_they_hold(tmp_path):
    groups = pool(10)
    many = [{**g, 'id': f"{g['id']}-{i}"} for g in groups for i in range(10)]     # 100 cases, 10 groups
    held = attempt(tmp_path, many)
    assert held['status'] == 'held' and held['available'] == 10 and advise_ledger.read(tmp_path, D) == []


def test_groups_cannot_be_reused_by_a_later_attempt_even_under_new_case_ids(tmp_path):
    cases = pool(40)
    assert attempt(tmp_path, cases)['status'] == 'evaluated'
    renamed = [{**c, 'id': c['id'] + '-again'} for c in cases]
    held = attempt(tmp_path, renamed + pool(10, start=80_000))
    assert held['status'] == 'held' and held['available'] == 10
    assert len(advise_ledger.used_groups(tmp_path, D)) == 40


# ---- live prospective cohorts

OPENED = '2026-10-16T00:00:00Z'


def rows(count, *, start=0, ts='2026-10-16T01:00:00Z', label=None, unlabelled=False, ambiguous=False, **extra):
    """`count` promotion-split rows, one per group, one second apart from `ts`; labels follow pool()'s 80/10/10 mix
    unless `label` is given; `unlabelled` leaves them pending, `ambiguous` makes the final label ambiguous."""
    base = datetime.strptime(ts, '%Y-%m-%dT%H:%M:%SZ')
    out, index = [], start
    while len(out) < count:
        group = f'live-{index}'
        index += 1
        if tp.split_of(group) != 'promotion':
            continue
        position = len(out) % 10
        mix = 'general' if position < 8 else 'content' if position == 8 else 'none'
        out.append({'id': f'r-{group}', 'group': group, 'ts': (base + timedelta(seconds=len(out))).strftime('%Y-%m-%dT%H:%M:%SZ'),
                    'label': None if unlabelled or ambiguous else label or mix, 'ambiguous': ambiguous,
                    'critical_if_wrong': False, **extra})
    return out


def step(root, data, *, now=OPENED, probe=lambda: True, predict_one=None, baseline='general', **kwargs):
    answers = {r['id']: r['label'] for r in data}
    return tp.run_live(root, D, data, policy_sha=kwargs.pop('policy', POLICY), instrument_sha=INSTRUMENT,
                       laya_revision=kwargs.pop('revision', 'rev-1'), gate_cfg=kwargs.pop('gate_cfg', None),
                       prior=kwargs.pop('prior', PRIOR), baseline=baseline, now=now, predict_one=predict_one or (lambda case: answers[case['id']]),
                       probe=probe, **kwargs)


def kinds(root):
    return [e['event'] for e in advise_ledger.read(root, D)]


def test_the_first_live_step_opens_a_cohort_with_a_frozen_baseline_and_needs_one(tmp_path):
    assert step(tmp_path, [], baseline=None) == {'status': 'held', 'reason': 'no_baseline'} and not (tmp_path / D).exists()
    before = rows(60, ts='2026-10-15T00:00:00Z')                    # the policy's records, all earlier than the open
    opened = step(tmp_path, before)
    assert opened['status'] == 'held' and opened['reason'] == 'cohort_opened' and opened['attempt'] == 1
    event = advise_ledger.read(tmp_path, D)[0]
    assert event['event'] == 'open' and event['openedAt'] == OPENED and event['rule'] == advise_ledger.OPEN_RULE
    assert event['baseline'] == 'general'
    again = step(tmp_path, before, now='2026-10-17T00:00:00Z', baseline='content')   # a perfect history is not eligible
    assert again['reason'] == 'cohort_collecting' and again['available'] == 0
    assert kinds(tmp_path) == ['open']


def test_a_policy_chosen_after_outcomes_cannot_reuse_earlier_recorded_cases(tmp_path):
    history = rows(60, ts='2026-10-10T00:00:00Z')                   # recorded and labelled; Laya matched every label
    step(tmp_path, history)
    rebound = step(tmp_path, history, now='2026-10-17T00:00:00Z', policy='c' * 64)   # binding changed: abandon, reopen
    assert rebound['reason'] == 'cohort_opened'
    assert kinds(tmp_path) == ['open', 'abandoned', 'open']


def test_enrollment_is_label_independent_ordered_by_time_and_immutable(tmp_path):
    step(tmp_path, [])
    data = rows(50, unlabelled=True)                                 # not one label exists yet
    waiting = step(tmp_path, data)
    assert waiting['reason'] == 'cohort_labelling' and waiting['enrolled'] == 38 and waiting['pending'] == 38
    event = advise_ledger.enrollment(tmp_path, D, advise_ledger.open_cohort(tmp_path, D)['cohortId'])
    assert event['caseIds'] == sorted(r['id'] for r in data[:38])    # the 38 earliest groups: ceil(30 / 0.8)
    earlier = rows(5, start=700, ts='2026-10-16T00:30:00Z')          # earlier-timestamped records arriving later
    assert step(tmp_path, data + earlier)['reason'] == 'cohort_labelling'
    assert advise_ledger.enrollment(tmp_path, D, event['cohortId']) == event and kinds(tmp_path) == ['open', 'enrolled']
    labelled = [{**r, 'label': 'general' if i < 30 else 'content'} for i, r in enumerate(data)]   # labels, any value
    assert step(tmp_path, labelled + earlier)['status'] == 'evaluated'
    consumed = advise_ledger.read(tmp_path, D)[-1]
    assert consumed['event'] == 'consumed' and advise_ledger.enrollment(tmp_path, D, event['cohortId']) == event


def test_enrollment_waits_for_enough_groups_without_reading_labels(tmp_path):
    step(tmp_path, [])
    short = rows(37, label=None, unlabelled=True)
    held = step(tmp_path, short)
    assert held['reason'] == 'cohort_collecting' and held['available'] == 37 and held['required'] == 38
    assert kinds(tmp_path) == ['open']
    tuning = {'id': 't1', 'group': next(g for g in (f'tg-{i}' for i in range(99)) if tp.split_of(g) == 'tuning'),
              'ts': '2026-10-16T02:00:00Z', 'label': 'general', 'ambiguous': False, 'critical_if_wrong': False}
    assert step(tmp_path, short + [tuning])['reason'] == 'cohort_collecting'
    assert step(tmp_path, short + rows(1, start=900, ts='2026-10-16T03:00:00Z', unlabelled=True))['reason'] == 'cohort_labelling'


def test_live_evaluates_once_with_the_baseline_frozen_at_open(tmp_path):
    step(tmp_path, [])
    data = rows(45)
    result = step(tmp_path, data, baseline='content')                # today's tuning majority differs; the open one wins
    assert result['status'] == 'evaluated' and result['baseline'] == 'general' and result['verdict'] == 'pass'
    end = advise_ledger.read(tmp_path, D)[-1]
    assert end['event'] == 'consumed' and kinds(tmp_path) == ['open', 'enrolled', 'consumed']
    advise_ledger.verify_pass(tmp_path, D, {'cohortId': result['cohortId'], 'policySha256': POLICY,
                                            'instrumentSha256': INSTRUMENT, 'layaRevision': 'rev-1'})
    assert tp.cohort_baseline(tmp_path, D, result['cohortId']) == 'general'
    after = step(tmp_path, data)                                    # the enrolled groups are spent
    assert after['reason'] == 'cohort_opened' and after['attempt'] == 2 and after['alpha'] == 0.05
    leftover = step(tmp_path, data)                                 # only the 7 groups the first cohort never enrolled
    assert leftover['reason'] == 'cohort_collecting' and leftover['available'] == 45 - 38


def test_ambiguous_labels_are_excluded_and_too_many_consume_a_hold(tmp_path):
    step(tmp_path, [])
    data = rows(45)
    for row in data[:7]:                                             # 7 of 38 enrolled = 18%: excluded, still evaluates
        row.update(label=None, ambiguous=True)
    ok = step(tmp_path, data)
    assert ok['verdict'] == 'pass' and ok['stats']['ambiguous'] == 7 and ok['stats']['n'] == 31
    step(tmp_path, [])                                              # a new attempt
    more = rows(45, start=3000)
    for row in more[:8]:                                             # 8 of 38 = 21%
        row.update(label=None, ambiguous=True)
    held = step(tmp_path, more, now='2026-10-18T00:00:00Z')
    assert held['verdict'] == 'hold' and held['reasons'] == ['ambiguous_share']
    assert advise_ledger.read(tmp_path, D)[-1]['event'] == 'consumed'


def test_probe_runs_immediately_before_the_final_evaluation_and_nothing_is_consumed_when_it_fails(tmp_path):
    step(tmp_path, [])
    data = rows(45)
    calls = []
    held = step(tmp_path, data, probe=lambda: calls.append(1) or False)
    assert held == {'status': 'held', 'reason': 'laya_unavailable'} and calls == [1]
    assert kinds(tmp_path) == ['open', 'enrolled'] and not (tmp_path / D / 'advise-receipts').exists()
    assert step(tmp_path, data)['status'] == 'evaluated' and kinds(tmp_path)[-1] == 'consumed'


def test_a_crash_between_the_receipt_and_consumed_is_recovered_without_re_evaluating(tmp_path, monkeypatch):
    step(tmp_path, [])
    data = rows(45)
    real = advise_ledger.append

    def crash(root, decision, event):
        if event['event'] == 'consumed':
            raise OSError('killed after the receipt was published')
        return real(root, decision, event)
    monkeypatch.setattr(advise_ledger, 'append', crash)
    with pytest.raises(OSError):
        step(tmp_path, data)
    monkeypatch.undo()
    assert kinds(tmp_path) == ['open', 'enrolled']
    [path] = list((tmp_path / D / 'advise-receipts').iterdir())
    stored = path.read_bytes()
    # the world moves on: more labels, a different tuning majority, and a Laya that would now answer everything wrong
    more = data + rows(30, start=5000, ts='2026-10-16T09:00:00Z')
    recovered = step(tmp_path, more, baseline='content', predict_one=lambda case: 'none', prior={'none': 100})
    assert recovered['status'] == 'evaluated' and recovered['verdict'] == 'pass' and recovered['baseline'] == 'general'
    assert recovered['receiptSha256'] == tp.sha256(json.loads(stored)) and path.read_bytes() == stored
    assert kinds(tmp_path) == ['open', 'enrolled', 'consumed']
    again = step(tmp_path, more)                                    # idempotent: no second consumed, a new cohort opens
    assert kinds(tmp_path).count('consumed') == 1 and again['reason'] == 'cohort_opened'


def test_live_open_needs_a_mandatory_probe_and_an_outage_never_opens(tmp_path):
    for bad in (None, lambda: None, lambda: False, lambda: (_ for _ in ()).throw(ConnectionRefusedError('down'))):
        assert step(tmp_path, [], probe=bad) == {'status': 'held', 'reason': 'laya_unavailable'}
        assert not (tmp_path / D).exists()
    assert step(tmp_path, [])['reason'] == 'cohort_opened'


def test_live_dry_run_writes_nothing(tmp_path):
    assert step(tmp_path, [], dry_run=True)['reason'] == 'would_open_cohort' and not (tmp_path / D).exists()
    step(tmp_path, [])
    before = (tmp_path / D / 'advise-cohorts.jsonl').read_bytes()
    assert step(tmp_path, rows(45), dry_run=True)['reason'] == 'would_enroll_cohort'
    assert (tmp_path / D / 'advise-cohorts.jsonl').read_bytes() == before and not (tmp_path / D / 'advise-receipts').exists()


def test_live_critical_cohort_enrolls_enough_critical_cases_and_holds_on_a_miss(tmp_path):
    step(tmp_path, [], critical=True)
    data = rows(60)
    for row in data[:12]:
        row['critical_if_wrong'] = True
    waiting = step(tmp_path, data, critical=True, gate_cfg={'minCriticalCases': 10})
    assert waiting['reason'] == 'cohort_collecting' is not None and waiting['criticalAvailable'] == 12
    assert waiting['criticalRequired'] == 13
    data[12]['critical_if_wrong'] = True
    answers = {r['id']: r['label'] for r in data}
    miss = step(tmp_path, data, critical=True, gate_cfg={'minCriticalCases': 10},
                predict_one=lambda case: None if case['id'] == data[0]['id'] else answers[case['id']])
    assert miss['verdict'] == 'hold' and 'critical_miss' in miss['reasons']


def test_live_cohort_with_a_missing_tuning_class_holds(tmp_path):
    step(tmp_path, [])
    result = step(tmp_path, rows(45, label='general'))               # all one class; 'none' and 'content' are in the prior
    assert result['verdict'] == 'hold' and 'class_coverage:content' in result['reasons']


def test_live_binding_change_abandons_but_the_attempt_stays_spent(tmp_path):
    step(tmp_path, [])
    moved = step(tmp_path, [], revision='rev-2', now='2026-10-17T00:00:00Z')
    assert moved['reason'] == 'cohort_opened' and moved['attempt'] == 2 and moved['alpha'] == 0.05
    assert kinds(tmp_path) == ['open', 'abandoned', 'open']
    assert advise_ledger.open_cohort(tmp_path, D)['layaRevision'] == 'rev-2'
    assert step(tmp_path, [], revision='rev-3', probe=lambda: False)['reason'] == 'laya_unavailable'
    assert len(advise_ledger.read(tmp_path, D)) == 3


# ---- replay: probe before evaluation and crash recovery

def test_replay_crash_between_receipt_and_consumed_is_recovered_identically(tmp_path, monkeypatch):
    cases = pool(40)
    real = advise_ledger.append

    def crash(root, decision, event):
        if event['event'] == 'consumed':
            raise OSError('killed')
        return real(root, decision, event)
    monkeypatch.setattr(advise_ledger, 'append', crash)
    with pytest.raises(OSError):
        attempt(tmp_path, cases)
    monkeypatch.undo()
    assert kinds(tmp_path) == ['reserve']
    [path] = list((tmp_path / D / 'advise-receipts').iterdir())
    stored = path.read_bytes()
    seen = []
    retry = attempt(tmp_path, cases + pool(10, start=90_000), lambda case: seen.append(case) or 'content')
    assert retry['verdict'] == 'pass' and seen == [] and path.read_bytes() == stored      # adopted, never re-evaluated
    assert retry['receiptSha256'] == tp.sha256(json.loads(stored)) and kinds(tmp_path) == ['reserve', 'consumed']
    assert tp.sha256(json.loads(stored)) == retry['receiptSha256']


def reserved_by_hand(root, cases, cohort='9' * 32, attempt=1):
    advise_ledger.append(root, D, {
        'event': 'reserve', 'cohortId': cohort, 'decision': D, 'policySha256': POLICY, 'instrumentSha256': INSTRUMENT,
        'layaRevision': 'rev-1', 'attempt': attempt, 'alpha': 0.1 / 2 ** (attempt - 1), 'baseline': 'general',
        'ts': '2026-10-16T00:00:00Z', 'caseIds': sorted(c['id'] for c in cases),
        'groups': sorted(advise_ledger.group_hash(c['group']) for c in cases)})


def test_replay_resumes_a_reserved_cohort_after_a_probe_failure_instead_of_reserving_another(tmp_path):
    cases = pool(40)
    reserved_by_hand(tmp_path, cases)
    held = attempt(tmp_path, cases, probe=lambda: False)             # the probe right before evaluation fails
    assert held == {'status': 'held', 'reason': 'laya_unavailable'} and kinds(tmp_path) == ['reserve']
    done = attempt(tmp_path, cases)
    assert done['status'] == 'evaluated' and done['cohortId'] == '9' * 32 and done['attempt'] == 1
    assert kinds(tmp_path) == ['reserve', 'consumed']


def test_replay_abandons_a_pending_reserve_whose_cases_vanished_and_starts_fresh(tmp_path):
    reserved_by_hand(tmp_path, pool(35, start=70_000), cohort='8' * 32)
    fresh = attempt(tmp_path, pool(40))
    assert fresh['status'] == 'evaluated' and fresh['attempt'] == 2
    assert kinds(tmp_path) == ['reserve', 'abandoned', 'reserve', 'consumed']
