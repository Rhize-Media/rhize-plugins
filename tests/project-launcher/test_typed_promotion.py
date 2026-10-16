"""Earned-mode promotion rules for typed decisions; invented fixtures, no live Laya."""
import importlib.util
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('typed_promotion', ROOT / 'evals/typed-decision/typed_promotion.py')
tp = importlib.util.module_from_spec(spec); spec.loader.exec_module(tp)

PRIOR = {'general': 70, 'content': 15, 'none': 15}


def make(spec_counts, start=0, critical=()):
    """spec_counts: [(truth, predicted, how_many)] -> promotion cases plus predictions."""
    cases, predictions, index = [], {}, start
    for truth, predicted, count in spec_counts:
        for _ in range(count):
            case_id = f'case-{index}'
            cases.append({'case_id': case_id, 'routing_choice': truth,
                          'stratum': 'critical_safety' if case_id in critical else 'ordinary'})
            predictions[case_id] = predicted
            index += 1
    return cases, predictions


def good(extra=0):
    # 30 cases, baseline (always general) accuracy .8; 27/30 correct with every class covered.
    return make([('general', 'general', 22), ('general', 'none', 2), ('content', 'content', 3),
                 ('none', 'none', 2), ('none', 'general', 1)], start=extra)


def test_wilson_numbers_against_an_eighty_percent_baseline():
    assert tp.wilson_lower(27, 30) > .8 > tp.wilson_lower(26, 30)
    assert tp.wilson_lower(44, 50) > .8 > tp.wilson_lower(43, 50)
    assert tp.wilson_lower(0, 0) == 0.0
    assert abs(tp.wilson_lower(27, 30) - 0.8078) < 1e-3


def test_27_of_30_promotes_and_26_of_30_does_not():
    cases, predictions = good()
    result = tp.evaluate(cases, predictions, 'general', PRIOR)
    assert result['correct'] == 27 and result['baselineAccuracy'] == .8 and result['promote'] is True
    assert result['scoredClasses'] == ['content', 'general', 'none']
    predictions['case-24'] = 'general'   # flip one correct content case
    result = tp.evaluate(cases, predictions, 'general', PRIOR)
    assert result['correct'] == 26 and result['promote'] is False
    assert 'wilson_lower_not_above_baseline' in result['blockers']


def test_44_of_50_promotes_and_43_of_50_does_not():
    cases, predictions = make([('general', 'general', 37), ('general', 'none', 3), ('content', 'content', 4),
                               ('content', 'general', 1), ('none', 'none', 3), ('none', 'general', 2)])
    result = tp.evaluate(cases, predictions, 'general', PRIOR)
    assert result['n'] == 50 and result['correct'] == 44 and result['baselineAccuracy'] == .8
    assert result['promote'] is True
    predictions['case-0'] = 'none'
    assert tp.evaluate(cases, predictions, 'general', PRIOR)['promote'] is False


def test_class_with_prior_share_but_fewer_than_three_cases_blocks():
    cases, predictions = make([('general', 'general', 26), ('general', 'none', 1), ('content', 'content', 3),
                               ('none', 'none', 2)])
    result = tp.evaluate(cases, predictions, 'general', PRIOR)
    assert result['accuracy'] > .9 and result['promote'] is False
    assert result['blockers'] == ['class_coverage:none']
    # A class below the 10% prior floor is not scored at all.
    assert tp.evaluate(cases, predictions, 'general', {'general': 90, 'content': 7, 'none': 3})['scoredClasses'] == ['general']


def test_recall_below_half_on_a_scored_class_blocks():
    cases, predictions = make([('general', 'general', 25), ('content', 'content', 2), ('content', 'general', 1),
                               ('none', 'none', 1), ('none', 'general', 2)])
    result = tp.evaluate(cases, predictions, 'general', PRIOR)
    assert result['promote'] is False and 'class_recall:none' in result['blockers']
    assert result['classes']['none']['recall'] == pytest.approx(1 / 3)


def test_abstentions_count_as_wrong_and_critical_misses_block():
    cases, predictions = good()
    predictions['case-0'] = None
    result = tp.evaluate(cases, predictions, 'general', PRIOR)
    assert result['abstentions'] == 1 and result['correct'] == 26
    cases, predictions = good()
    cases[0]['stratum'] = 'critical_authorization'
    predictions['case-0'] = None
    result = tp.evaluate(cases, predictions, 'general', PRIOR)
    assert result['criticalMisses'] == 1 and result['promote'] is False
    assert tp.evaluate(*good(), 'general', PRIOR)['criticalMisses'] == 0


def test_balanced_accuracy_must_beat_the_baseline():
    # Accuracy beats baseline but balanced accuracy of the always-general guess (1/3) is also beaten here;
    # force the other direction: a model that only ever predicts the baseline class cannot promote.
    cases, predictions = good()
    lazy = {case['case_id']: 'general' for case in cases}
    result = tp.evaluate(cases, lazy, 'general', PRIOR)
    assert result['promote'] is False and 'balanced_accuracy_not_above_baseline' in result['blockers']
    assert result['balancedAccuracy'] == result['baselineBalancedAccuracy']


def test_empty_promotion_set_never_promotes():
    result = tp.evaluate([], {}, 'general', PRIOR)
    assert result['promote'] is False and 'no_promotion_cases' in result['blockers']


def update(tmp_path, cases, predictions, config='cfg-a', now=1.0):
    return tp.update(cases, predictions, 'general', PRIOR, config, root=str(tmp_path), now=now)


def mode(tmp_path):
    return json.loads((tmp_path / 'modes.json').read_text())['decisionTypes']['workflow_fit']


def test_promotion_state_is_written_atomically_and_privately(tmp_path):
    root = tmp_path / 'state'
    cases, predictions = good()
    result = tp.update(cases, predictions, 'general', PRIOR, 'cfg-a', root=str(root), now=5.0)
    assert result['status'] == 'updated' and result['earnedMode'] == 'advise' and result['promoted'] is True
    path = root / 'modes.json'
    assert stat.S_IMODE(path.stat().st_mode) == 0o600 and stat.S_IMODE(root.stat().st_mode) == 0o700
    assert [p.name for p in root.iterdir()] == ['modes.json']          # no stray temp files
    value = json.loads(path.read_text())
    assert value['schema'] == 'rhize-typed-modes-v1'
    entry = value['decisionTypes']['workflow_fit']
    assert entry['earnedMode'] == 'advise' and entry['configSha256'] == 'cfg-a' and entry['updatedAt'] == 5.0
    assert entry['belowBaselineStreak'] == 0 and entry['lastAttempt']['n'] == 30
    assert len(entry['lastAttempt']['promotionCaseIds']) == 64
    assert 'case-0' not in path.read_text()                              # ids stored hashed, not raw


def test_write_is_atomic_when_the_replace_fails(tmp_path, monkeypatch):
    cases, predictions = good()
    update(tmp_path, cases, predictions)
    before = (tmp_path / 'modes.json').read_bytes()
    def boom(*args): raise OSError('disk full')
    monkeypatch.setattr(tp.os, 'replace', boom)
    with pytest.raises(OSError):
        tp.write_modes({'schema': tp.SCHEMA, 'decisionTypes': {}}, str(tmp_path))
    assert (tmp_path / 'modes.json').read_bytes() == before
    assert [p.name for p in tmp_path.iterdir()] == ['modes.json']


def test_state_root_can_come_from_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv('RHIZE_TYPED_DECISIONS_ROOT', str(tmp_path / 'env'))
    assert tp.modes_path() == tmp_path / 'env' / 'modes.json'
    assert tp.load_modes() == {'schema': 'rhize-typed-modes-v1', 'decisionTypes': {}}


def test_critical_miss_demotes_immediately(tmp_path):
    cases, predictions = good()
    update(tmp_path, cases, predictions)
    assert mode(tmp_path)['earnedMode'] == 'advise'
    cases2, predictions2 = good(extra=100)
    cases2[0]['stratum'] = 'critical_safety'
    predictions2['case-100'] = 'none'
    result = update(tmp_path, cases2, predictions2)
    assert result['demoted'] is True and result['demotionReason'] == 'critical_miss'
    assert mode(tmp_path)['earnedMode'] == 'shadow' and mode(tmp_path)['belowBaselineStreak'] == 0


def test_demotion_needs_two_consecutive_cycles_below_baseline(tmp_path):
    cases, predictions = good()
    update(tmp_path, cases, predictions)
    bad = lambda start: make([('general', 'none', 12), ('general', 'general', 12), ('content', 'general', 3),
                              ('none', 'none', 3)], start=start)   # accuracy .6 < baseline .8
    first = update(tmp_path, *bad(100))
    assert first['earnedMode'] == 'advise' and mode(tmp_path)['belowBaselineStreak'] == 1
    # A cycle that is not below baseline resets the streak.
    update(tmp_path, *good(extra=200))
    assert mode(tmp_path)['belowBaselineStreak'] == 0 and mode(tmp_path)['earnedMode'] == 'advise'
    update(tmp_path, *bad(300))
    assert mode(tmp_path)['earnedMode'] == 'advise' and mode(tmp_path)['belowBaselineStreak'] == 1
    result = update(tmp_path, *bad(400))
    assert result['demoted'] is True and result['demotionReason'] == 'below_baseline_two_cycles'
    assert mode(tmp_path)['earnedMode'] == 'shadow'


def test_a_changed_config_starts_from_shadow(tmp_path):
    cases, predictions = good()
    update(tmp_path, cases, predictions, config='cfg-a')
    assert mode(tmp_path)['earnedMode'] == 'advise'
    weak = make([('general', 'general', 20), ('general', 'none', 4), ('content', 'general', 3), ('none', 'none', 3)])
    result = update(tmp_path, *weak, config='cfg-b')
    assert result['previousMode'] == 'shadow' and result['earnedMode'] == 'shadow'
    assert mode(tmp_path)['configSha256'] == 'cfg-b'
    # Returning to the old config does not resurrect its earned mode either.
    assert update(tmp_path, *good(extra=500), config='cfg-a')['previousMode'] == 'shadow'


def test_reattempt_needs_ten_new_promotion_cases_and_leaves_state_untouched(tmp_path):
    cases, predictions = good()
    update(tmp_path, cases, predictions)
    before = (tmp_path / 'modes.json').read_bytes()
    more, more_predictions = good(extra=1000)
    nine = cases + more[:9]
    result = update(tmp_path, nine, {**predictions, **more_predictions}, now=9.0)
    assert result == {'status': 'held', 'reason': 'insufficient_new_promotion_cases', 'newCases': 9, 'required': 10}
    assert (tmp_path / 'modes.json').read_bytes() == before
    ten = cases + more[:10]
    assert tp.check_novelty([c['case_id'] for c in ten], 'cfg-a', str(tmp_path)) == (True, 10)
    assert update(tmp_path, ten, {**predictions, **more_predictions}, now=9.0)['status'] == 'updated'
    # A different config is never gated by another config's attempt.
    assert tp.check_novelty([c['case_id'] for c in cases], 'cfg-z', str(tmp_path)) == (True, 30)


def test_config_digest_ignores_the_display_id_and_tracks_every_frozen_field():
    base = {'id': 'one', 'model': 'typed-decisions', 'instructions': {'route': 'x'}, 'abstain_below': .6}
    questions = {'route': {'type': 'choice', 'instructions': 'Route it',
                           'criteria': {'content': 'Articles', 'general': 'Engineering', 'none': 'Questions'}}}
    ids = ['content', 'general', 'none']
    digest = tp.config_sha256(base, 'workflow-input-v3', ids, questions)
    assert digest == tp.config_sha256({**base, 'id': 'two'}, 'workflow-input-v3', ids, questions)
    for changed in ({**base, 'model': 'other'}, {**base, 'instructions': {'route': 'y'}}, {**base, 'abstain_below': .8}):
        assert tp.config_sha256(changed, 'workflow-input-v3', ids, questions) != digest
    assert tp.config_sha256(base, 'workflow-input-v4', ids, questions) != digest
    assert tp.config_sha256(base, 'workflow-input-v3', ['content', 'general'], questions) != digest


def test_config_digest_tracks_question_criteria_and_baseline_wording():
    baseline = {'id': 'baseline', 'model': 'typed-decisions', 'instructions': {}, 'abstain_below': 0.0}
    questions = {'route': {'type': 'choice', 'instructions': 'Route it',
                           'criteria': {'content': 'Articles', 'general': 'Engineering', 'none': 'Questions'}}}
    ids = ['content', 'general', 'none']
    digest = tp.config_sha256(baseline, 'workflow-input-v3', ids, questions)
    criteria = {**questions['route']['criteria'], 'general': 'Engineering and operations'}
    edited = {'route': {**questions['route'], 'criteria': criteria}}
    assert tp.config_sha256(baseline, 'workflow-input-v3', ids, edited) != digest
    # The baseline's own instructions are effective wording; a candidate override replaces them.
    reworded = {'route': {**questions['route'], 'instructions': 'Route it differently'}}
    assert tp.config_sha256(baseline, 'workflow-input-v3', ids, reworded) != digest
    override = {**baseline, 'instructions': {'route': 'Override'}}
    assert tp.config_sha256(override, 'workflow-input-v3', ids, questions) == \
        tp.config_sha256(override, 'workflow-input-v3', ids, reworded)


def test_status_cli_prints_modes_json(tmp_path):
    cases, predictions = good()
    update(tmp_path, cases, predictions)
    done = subprocess.run([sys.executable, str(ROOT / 'evals/typed-decision/typed_promotion.py'), 'status',
                           '--root', str(tmp_path)], text=True, capture_output=True, timeout=10)
    assert done.returncode == 0 and json.loads(done.stdout)['decisionTypes']['workflow_fit']['earnedMode'] == 'advise'
    env = {**os.environ, 'RHIZE_TYPED_DECISIONS_ROOT': str(tmp_path / 'empty')}
    done = subprocess.run([sys.executable, str(ROOT / 'evals/typed-decision/typed_promotion.py'), 'status'],
                          text=True, capture_output=True, timeout=10, env=env)
    assert json.loads(done.stdout) == {'decisionTypes': {}, 'schema': 'rhize-typed-modes-v1'}
