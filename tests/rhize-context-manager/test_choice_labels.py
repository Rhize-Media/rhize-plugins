"""choice_labels: blinded AI labels for the generic advise decisions, and critical-miss demotion (plan §8, §3.7).

Fake runner in place of the two model CLIs, temp roots only; no model, network or real data root is touched.
"""
from __future__ import annotations

import fcntl
import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / 'rhize-context-manager' / 'scripts'
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pilot_autolabel as auto  # noqa: E402
import typed_advice  # noqa: E402
from typed_decision_testkit import (CHOICE_IDS, CHOICE_POLICY, CHOICE_QUESTION, write_choice,  # noqa: E402
                                    write_choice_label)
from typed_decisions import choice_labels as cl, decision_registry as reg, skillfit_labels as sl  # noqa: E402

REV = 'rev-labels-1'
MODEL, ADVISORY = 'devflow-next-action', 'model-routing'          # critical tier / advisory tier
EMAIL = 'jane.doe@example.com'
FORBIDDEN = re.compile(r'(?i)\b(laya|probabilit\w*|recommend\w*|mode|arm|outcome|followed|critical\w*|holdback|'
                       r'treatment|advise|policy)\b')


class FakeRunner:
    """Stands in for the CLIs. Marker WANT-<id> in the request picks that candidate; SPLIT makes the annotators differ."""

    def __init__(self, review=None, fail=None):
        self.calls, self.review_fn, self.fail = [], review, fail

    def preflight(self, host):
        return {'host': host}

    def _pick(self, case, id_):
        key = {c['id']: c['key'] for c in case['candidates']}
        return 'ambiguous' if id_ == 'AMBIG' else key[id_]

    def call(self, host, model, system, prompt, schema, timeout):
        self.calls.append({'host': host, 'prompt': prompt, 'system': system, 'schema': schema})
        if self.fail:
            raise auto.LabelerError(self.fail)
        cases = json.loads(prompt.split('# Cases\n\n', 1)[1])
        reviewing = 'reviews' in schema['properties']
        if reviewing:
            reviews = []
            for case in cases:
                want = re.search(r'WANT-(\w+)', case['request']).group(1)
                verdict = (self.review_fn or (lambda c, w: ('resolved', w)))(case, want)
                reviews.append({'caseId': case['caseId'], 'verdict': verdict[0], 'reason': 'fixture',
                                'final': {'choice': self._pick(case, verdict[1])}})
            answer = {'reviews': reviews}
        else:
            answers = []
            for case in cases:
                want = re.search(r'WANT-(\w+)', case['request']).group(1)
                if 'SPLIT' in case['request']:
                    want = 'alpha' if host == 'claude' else 'gamma'
                answers.append({'caseId': case['caseId'], 'choice': self._pick(case, want), 'rationale': 'fixture'})
            answer = {'answers': answers}
        return {'answer': answer, 'raw': '', 'requestedModel': model, 'observedModel': model,
                'identitySource': 'native_model_usage', 'usage': {}}

    def prompts(self):
        return '\n'.join(c['prompt'] for c in self.calls)


@pytest.fixture
def root(tmp_path):
    path = tmp_path / 'typed-decisions'
    path.mkdir(mode=0o700)
    (path / 'laya-runtime.json').write_text(json.dumps({'revision': REV}))
    return path


@pytest.fixture
def cfg(tmp_path):
    return {'state': tmp_path / 'autolabel'}


def go_advise(root, decision):
    policy = typed_advice.policy_sha256(decision, CHOICE_QUESTION, CHOICE_POLICY)
    reg.mutate(root, decision, 'advise', actor='cli', reason='manual_override', expected_revision=0,
               binding={'policySha256': policy, 'instrumentSha256': typed_advice.INSTRUMENT_SHA256,
                        'layaRevision': REV, 'cohortId': None})


def mode_of(root, decision):
    state, _ = reg.read_state(root)
    return ((state or {}).get('decisions') or {}).get(decision, {}).get('mode')


def run(root, cfg, runner, **kwargs):
    return cl.run(root, runner=runner, config=cfg, **kwargs)


def seed(root, decision, count, want='beta', laya='alpha', start=0, **kwargs):
    return [write_choice(root, decision, start + i, laya=laya, text=f'please WANT-{want} item {start + i}', **kwargs)
            for i in range(count)]


# ---------------------------------------------------------------- blinding and storage

def test_packet_is_blinded_redacted_and_the_label_is_stored(root, cfg):
    go_advise(root, ADVISORY)
    results = [write_choice(root, ADVISORY, i, laya='alpha', text=f'WANT-beta mail {EMAIL} item {i}')
               for i in range(4)]
    typed_advice.record_outcome(ADVISORY, results[0]['decisionId'], 'gamma', store=root)
    runner = FakeRunner()
    summary, code = run(root, cfg, runner)
    assert code == 0 and summary['labelsWritten'] == 4 and summary['modelCalls'] == 2
    prompts = runner.prompts()
    assert not FORBIDDEN.search(prompts + runner.calls[0]['system']), FORBIDDEN.search(prompts)
    assert EMAIL not in prompts and '0.7' not in prompts and 'followed' not in prompts
    packet = json.loads(runner.calls[0]['prompt'].split('# Cases\n\n', 1)[1])[0]
    assert set(packet) == {'caseId', 'request', 'files', 'question', 'candidates'}
    assert all(set(c) == {'key', 'id', 'criterion'} and re.fullmatch(r'c\d', c['key']) for c in packet['candidates'])
    labels = cl.read_labels(root, ADVISORY)
    assert len(labels) == 4
    label = labels[results[0]['decisionId']]
    assert label['label'] == 'beta' and label['ambiguous'] is False and label['basis'] == 'ai_model_reviewed'
    assert label['rubricVersion'] == cl.RUBRIC_VERSION and label['reviewer'] is None
    assert label['annotators'] == ['claude-sonnet-5-5', 'gpt-5.6-sol'] and label['redactor'] == cl.redactor_sha256()
    assert len(label['evidenceSha256']) == 64
    path = root / ADVISORY / 'label' / f"{results[0]['decisionId']}.json"
    assert path.stat().st_mode & 0o777 == 0o600


def test_candidate_order_is_shuffled_per_case_but_stable(root, cfg):
    results = seed(root, ADVISORY, 8)
    record, snap = cl.pending(root, ADVISORY)[0][0]
    orders = {tuple(c['id'] for c in cl.build_case(ADVISORY, r, s, 'C1')['entry']['candidates'])
              for r, s in cl.pending(root, ADVISORY)[0]}
    assert len(orders) > 1 and set(map(len, orders)) == {3}
    first = cl.build_case(ADVISORY, record, snap, 'C1')
    assert first['entry'] == cl.build_case(ADVISORY, record, snap, 'C1')['entry'] and len(results) == 8


def test_labels_are_write_once_and_labelled_records_are_not_pending(root, cfg):
    results = seed(root, ADVISORY, 3)
    write_choice_label(root, ADVISORY, results[0]['decisionId'], 'gamma')
    runner = FakeRunner()
    summary, _ = run(root, cfg, runner)
    assert summary['labelsWritten'] == 2 and cl.read_labels(root, ADVISORY)[results[0]['decisionId']]['label'] == 'gamma'
    assert run(root, cfg, runner)[0]['status'] == 'nothing_to_do'
    # a racing writer cannot overwrite either
    assert write_choice_label(root, ADVISORY, results[1]['decisionId'], 'alpha') is False
    assert cl.read_labels(root, ADVISORY)[results[1]['decisionId']]['label'] == 'beta'


def test_split_goes_to_the_reviewer_and_unresolved_is_ambiguous(root, cfg):
    a = write_choice(root, ADVISORY, 1, laya='alpha', text='SPLIT WANT-beta one')
    b = write_choice(root, ADVISORY, 2, laya='alpha', text='SPLIT WANT-AMBIG two')
    runner = FakeRunner(review=lambda case, want: ('unresolved', 'AMBIG') if want == 'AMBIG' else ('resolved', want))
    summary, code = run(root, cfg, runner)
    assert code == 0 and summary['reviewed'] == 2 and summary['reviewUnresolved'] == 1
    labels = cl.read_labels(root, ADVISORY)
    assert labels[a['decisionId']]['label'] == 'beta' and labels[a['decisionId']]['reviewer'] == 'claude-fable-5-1'
    assert labels[b['decisionId']]['label'] is None and labels[b['decisionId']]['ambiguous'] is True


def test_an_agreed_ambiguous_answer_is_stored_ambiguous(root, cfg):
    record = write_choice(root, ADVISORY, 1, laya='alpha', text='WANT-AMBIG')
    run(root, cfg, FakeRunner())
    assert cl.read_labels(root, ADVISORY)[record['decisionId']]['ambiguous'] is True


def test_a_reviewer_that_is_an_annotator_labels_nothing(root, cfg):
    write_choice(root, ADVISORY, 1, laya='alpha', text='SPLIT WANT-beta')
    runner = FakeRunner()
    original = runner.call

    def call(host, model, *rest):
        result = original(host, model, *rest)
        if 'reviews' in rest[2]['properties']:
            result['observedModel'] = 'claude-sonnet-5-5'
        return result
    runner.call = call
    summary, code = run(root, cfg, runner)
    assert summary['labelsWritten'] == 0 and code == 3 and cl.read_labels(root, ADVISORY) == {}


# ---------------------------------------------------------------- budget, lock, dry run, scope

def test_budget_is_total_and_shared_fairly_across_decisions(root, cfg):
    seed(root, ADVISORY, 3)
    seed(root, 'browser-qa-selection', 3)
    runner = FakeRunner()
    summary, _ = run(root, cfg, runner, max_cases=2)
    assert summary['labelsWritten'] == 2 and summary['pending'] == 6 and summary['maxCases'] == 2
    assert len(cl.read_labels(root, ADVISORY)) == 1 and len(cl.read_labels(root, 'browser-qa-selection')) == 1


def test_default_budget_is_fifty(root, cfg):
    seed(root, ADVISORY, 2)
    assert run(root, cfg, FakeRunner(), dry_run=True)[0]['maxCases'] == 50


def test_a_held_run_lock_means_busy_and_no_model_calls(root, cfg):
    seed(root, ADVISORY, 2)
    state = auto.ensure_private(cfg['state'])
    runner = FakeRunner()
    with open(state / 'run.lock', 'w') as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        summary, code = run(root, cfg, runner)
    assert summary == {'status': 'busy', 'modelCalls': 0} and code == 0 and runner.calls == []
    assert cl.read_labels(root, ADVISORY) == {}


def test_dry_run_prepares_without_calls_or_writes(root, cfg):
    seed(root, ADVISORY, 2)
    runner = FakeRunner()
    summary, code = run(root, cfg, runner, dry_run=True)
    assert code == 0 and summary['status'] == 'prepared' and summary['ready'] == 2 and runner.calls == []
    assert not (root / ADVISORY / 'label').exists() and not (root / 'choice-labels').exists()


def test_records_without_a_snapshot_are_skipped_and_other_labelers_are_refused(root, cfg):
    write_choice(root, ADVISORY, 1, laya='alpha', text='WANT-beta', snapshot=False)
    summary, _ = run(root, cfg, FakeRunner())
    assert summary['noSnapshot'] == 1 and summary['status'] == 'nothing_to_do'
    for own in ('skill-fit', 'workflow-fit'):
        assert own not in cl.labelable(reg.load_registry())
        with pytest.raises(sl.LabelError):
            cl.run(root, decision=own, config=cfg, runner=FakeRunner())


def test_failures_leave_no_label_and_the_next_run_retries(root, cfg):
    seed(root, ADVISORY, 2)
    summary, code = run(root, cfg, FakeRunner(fail='codex_exit_1'))
    assert code == 3 and summary['labelsWritten'] == 0 and cl.read_labels(root, ADVISORY) == {}
    assert run(root, cfg, FakeRunner())[0]['labelsWritten'] == 2


# ---------------------------------------------------------------- critical-miss demotion

def scenario(tmp_path, cfg, *, decision=MODEL, laya='alpha', want='beta', critical=True, treatment=True, mode='advise',
             status='ok'):
    root = tmp_path / f'root-{abs(hash((decision, laya, want, critical, treatment, mode, status)))}'
    root.mkdir(mode=0o700)
    (root / 'laya-runtime.json').write_text(json.dumps({'revision': REV}))
    if mode == 'shadow_then_advise':
        index = next(i for i in range(200) if typed_advice.holdback(decision, f'key-{i}') == (not treatment))
        write_choice(root, decision, index, laya=laya, critical=critical, status=status, text=f'WANT-{want}')
        go_advise(root, decision)
    else:
        go_advise(root, decision)
        index = next(i for i in range(200) if typed_advice.holdback(decision, f'key-{i}') == (not treatment))
        write_choice(root, decision, index, laya=laya, critical=critical, status=status, text=f'WANT-{want}')
    summary, _ = run(root, cfg, FakeRunner())
    return root, summary


def test_the_full_conjunction_demotes_a_critical_decision_to_shadow(tmp_path, cfg):
    root, summary = scenario(tmp_path, cfg)
    assert mode_of(root, MODEL) == 'shadow'
    assert summary['criticalDemotions'] == [{'decision': MODEL, 'misses': 1, 'status': 'demoted', 'revision': 2}]
    audit = reg.read_audit(root)[0][-1]
    assert audit['reason'] == 'critical_miss' and audit['actor'] == 'cycle' and audit['toMode'] == 'shadow'
    receipts = list((root / 'choice-labels' / 'receipts').glob('*.json'))
    assert len(receipts) == 1 and json.loads(receipts[0].read_text())['criticalDemotions']


@pytest.mark.parametrize('change', [
    {'laya': 'beta'},                       # Laya was right
    {'critical': False},                    # not critical if wrong
    {'treatment': False},                   # holdback arm: advice was never shown
    {'mode': 'shadow_then_advise'},         # the record was written in shadow
    {'want': 'AMBIG'},                      # ambiguous label
    {'status': 'timeout'},                  # Laya did not answer
    {'decision': ADVISORY},                 # advisory tier: no immediate demotion
], ids=['laya-right', 'not-critical', 'holdback', 'shadow-record', 'ambiguous', 'laya-unavailable', 'advisory-tier'])
def test_each_single_clause_negation_leaves_the_mode_alone(tmp_path, cfg, change):
    root, summary = scenario(tmp_path, cfg, **change)
    assert summary['labelsWritten'] == 1 and summary['criticalDemotions'] == []
    assert mode_of(root, change.get('decision', MODEL)) == 'advise'


def test_a_pin_or_an_unchanged_mode_is_recorded_not_raised(tmp_path, cfg):
    root = tmp_path / 'pinned'
    root.mkdir(mode=0o700)
    (root / 'laya-runtime.json').write_text(json.dumps({'revision': REV}))
    go_advise(root, MODEL)
    reg.mutate(root, MODEL, 'advise', actor='cli', reason='pin_it', expected_revision=1, pinned=True)
    index = next(i for i in range(200) if not typed_advice.holdback(MODEL, f'key-{i}'))
    write_choice(root, MODEL, index, laya='alpha', critical=True, text='WANT-beta')
    summary, _ = run(root, cfg, FakeRunner())
    assert summary['criticalDemotions'][0]['status'] == 'held' and summary['criticalDemotions'][0]['code'] == 'pinned'
    assert mode_of(root, MODEL) == 'advise'
    assert CHOICE_IDS  # fixture sanity
