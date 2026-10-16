"""Invented local fixtures for bounded, versioned development research."""
import importlib.util
import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f'evals/typed-decision/{name}.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


cycle = load('pilot_cycle')
research = load('research')
CHOICES = ('content', 'general', 'none')


@pytest.fixture(autouse=True)
def private_modes_root(tmp_path, monkeypatch):
    """The typed-decisions state root (registry, advise ledger) with a pinned Laya checkpoint."""
    state = tmp_path / 'typed-decisions'
    state.mkdir()
    (state / 'laya-runtime.json').write_text(json.dumps({'revision': 'rev-test'}))
    monkeypatch.setenv('RHIZE_TYPED_DECISIONS_ROOT', str(state))
    return state


def registry_state(tmp_path):
    path = tmp_path / 'typed-decisions/registry-state.json'
    return json.loads(path.read_text()) if path.exists() else None


def ledger_events(tmp_path):
    path = tmp_path / 'typed-decisions/workflow-fit/advise-cohorts.jsonl'
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def key(kind, value):
    return kind + ':' + cycle.digest(str(value))


def expected(index):
    return CHOICES[index % 3]


def case(index):
    choice = expected(index)
    return {'case_id': str(index), 'group_id': str(index), 'decision_type': 'workflow_fit',
            'stratum': 'ordinary', 'label_source': cycle.digest(str(index)), 'adjudicated': True,
            'state': {'request': f'request {index}', 'eventKind': 'new_task', 'action': 'create',
                      'domain': 'content' if index % 2 else 'software', 'exclusions': []},
            'questions': {'route': {'type': 'choice', 'instructions': 'Route it',
                                    'criteria': {name: 'Choose ' + name for name in CHOICES}}},
            'labels': {'route': choice}, 'candidate_ids': list(CHOICES), 'routing_choice': choice,
            'arm_a_choice': 'general', 'cohort_version': cycle.COHORT, 'replayed': True,
            'collection_source_sha256': 'a' * 64, 'normalization_version': cycle.NORMALIZATION,
            'grouping_keys': [key('session', index), key('input', index), key('prompt', index)],
            'task_family': 'content' if index % 2 else 'software', 'host': 'codex', 'label_basis': 'ai_model_reviewed'}


def corpus(monkeypatch, rows, count=None, bases=('human_adjudicated', 'ai_model_reviewed'), choice_basis='explicit'):
    stored = [{'basis': 'ai_model_reviewed', 'choiceBasis': choice_basis, 'opportunityId': cycle.digest(str(i))}
              for i in range(len(rows) if count is None else count)]
    monkeypatch.setattr(cycle.pilot_labels, 'load_labels', lambda root: stored)
    monkeypatch.setattr(cycle.pilot_labels, 'load_policy', lambda root: {
        'schema': 'rhize-pilot-label-policy-v1', 'acceptedBases': list(bases), 'reason': 'fixture', 'setBy': 'jim'})
    def replay(receipts, root, policy):
        assert policy['acceptedBases'] == list(bases)
        return {'cases': rows, 'provenance': {'labels': len(stored), 'cases': len(rows), 'skipped': {},
                                              'replayed': True, 'pooledAcrossSources': False}}
    monkeypatch.setattr(cycle.pilot_labels, 'replay_cases', replay)


def answer(choice, confidence=.9):
    rest = (1 - confidence) / 2
    return {'type': 'choice', 'choice': choice, 'confidence': confidence,
            'probabilities': {name: confidence if name == choice else rest for name in CHOICES}}


def laya(request, right=True):
    index = int(request['state']['request'].split()[1])
    return {'answers': {'route': answer(expected(index) if right else 'none')}}, 1.0


def shifted_laya(request):
    index = int(request['state']['request'].split()[1])
    return {'answers': {'route': answer(expected(index + 1))}}, 1.0


def wrong_laya(request):
    return laya(request, right=False)


def keep_first(command, **kwargs):
    options = json.loads(Path(command[command.index('--candidates')+1]).read_text())
    Path(command[command.index('--ledger')+1]).write_text(
        json.dumps({'status': 'keep', 'candidate_sha256': research.digest(options[0])}) + '\n')
    return SimpleNamespace(returncode=0)


def run_cycle(tmp_path, **kwargs):
    kwargs.setdefault('run', keep_first)
    kwargs.setdefault('call', laya)
    return cycle.cycle(tmp_path/'pilot', tmp_path/'receipts', tmp_path/'research', **kwargs)


def test_automatic_floor_is_twenty_and_default_thirty(tmp_path):
    with pytest.raises(ValueError, match='at least 20 labels'):
        cycle.cycle(tmp_path/'pilot', tmp_path/'receipts', tmp_path/'research', minimum=19)
    with pytest.raises(ValueError, match='at least 20 labels'):
        cycle.cycle(tmp_path/'pilot', tmp_path/'receipts', tmp_path/'research', minimum=10001)
    assert cycle.DEFAULT_MINIMUM == 30
    for minimum in (20, 30, 10000):
        cycle.check_bounds(minimum, 180)
    result = cycle.cycle(tmp_path/'pilot', tmp_path/'receipts', tmp_path/'research')
    assert result['status'] == 'held' and result['reason'] == 'insufficient_accepted_labels'
    assert result['labels'] == 0 and result['required'] == 30
    artifacts = list((tmp_path/'research'/cycle.COHORT/'holds').glob('*.json'))
    assert len(artifacts) == 1
    assert json.loads(artifacts[0].read_text()) == result
    assert artifacts[0].stat().st_mode & 0o777 == 0o600


def test_cycle_accepts_thirty_labels_and_holds_below_the_requested_minimum(tmp_path, monkeypatch):
    corpus(monkeypatch, [case(i) for i in range(30)])
    result = run_cycle(tmp_path)
    assert result['config']['minimum'] == 30 and result['status'] in {'held', 'review_required'}
    corpus(monkeypatch, [case(i) for i in range(29)])
    result = run_cycle(tmp_path / 'other')
    assert result['reason'] == 'insufficient_accepted_labels' and result['labels'] == 29 and result['required'] == 30


def test_legacy_cycle_accepts_new_bounds(tmp_path):
    result = cycle.legacy_cycle(tmp_path/'pilot', tmp_path/'receipts', tmp_path/'research', minimum=20)
    assert result['reason'] == 'insufficient_human_labels' and result['required'] == 20
    with pytest.raises(ValueError, match='invalid research bounds'):
        cycle.legacy_cycle(tmp_path/'pilot', tmp_path/'receipts', tmp_path/'research', minimum=19)


def test_candidate_set_is_bounded_and_overrides_the_route_question():
    options = cycle.candidates()
    assert options[0] == {'id': 'baseline', 'model': 'typed-decisions', 'instructions': {}, 'abstain_below': 0.0}
    assert len(options) <= 12 and len({research.digest(o) for o in options}) == len(options)
    research.validate_candidate(options[-1], [case(1)])
    for option in options:
        research.validate_candidate(option, [case(1)])


def test_duplicate_templates_and_sessions_connect_without_sentinel(tmp_path):
    rows = [case(i) for i in range(3)]
    rows[1]['grouping_keys'][1] = rows[0]['grouping_keys'][1]
    rows[2]['grouping_keys'][0] = rows[1]['grouping_keys'][0]
    grouped, assignments, records = cycle.grouping(rows, [])
    assert len({row['group_id'] for row in grouped}) == 1
    rows[0]['grouping_keys'].append('input:' + '0' * 64)
    with pytest.raises(ValueError, match='invalid_grouping_keys'):
        cycle.grouping(rows, [])


def test_append_only_assignments_preserve_old_promotion_and_hold_bridges():
    a, b = case(1), case(2)
    old = [{'cohort': cycle.COHORT, 'normalization': cycle.NORMALIZATION,
            'keys': a['grouping_keys'], 'split': 'promotion'},
           {'cohort': cycle.COHORT, 'normalization': cycle.NORMALIZATION,
            'keys': b['grouping_keys'], 'split': 'train'}]
    grouped, assignments, _ = cycle.grouping([a, b], old)
    assert assignments[grouped[0]['group_id']] == 'promotion'
    a['grouping_keys'].append(b['grouping_keys'][0])
    with pytest.raises(ValueError, match='cross_split_bridge'):
        cycle.grouping([a, b], old)


def test_split_is_roughly_one_third_promotion_and_stable_as_the_corpus_grows():
    rows = [case(i) for i in range(120)]
    grouped, assignments, records = cycle.grouping(rows, [])
    shares = {name: sum(v == name for v in assignments.values()) / len(assignments) for name in cycle.SPLITS}
    assert .2 < shares['promotion'] < .5 and set(shares) == set(cycle.SPLITS)
    more, assignments_more, _ = cycle.grouping(rows + [case(i) for i in range(120, 160)], records)
    assert all(assignments_more[g] == split for g, split in assignments.items())


def test_diversity_holds_without_dropping_rows():
    rows = [case(i) for i in range(40)]
    for row in rows[:31]: row['group_id'] = 'same'
    result = cycle.diversity(rows)
    assert result['labels'] == 40 and result['largestGroupShare'] == 31/40
    assert 'group_concentration' in result['holdReasons']
    few = [case(i) for i in range(30)]
    for i, row in enumerate(few): row['group_id'] = str(i % 5)
    assert 'insufficient_independent_groups' in cycle.diversity(few)['holdReasons']
    assert cycle.diversity([case(i) for i in range(30)])['holdReasons'] == []


def test_legacy_membership_does_not_open_holdout_cases(tmp_path):
    split = tmp_path/'legacy/split'; split.mkdir(parents=True)
    (split/'manifest.json').write_text('{}')
    (split/'holdout.jsonl').write_text('must not parse this')
    with pytest.raises(ValueError, match='legacy_holdout_membership_unavailable'):
        cycle.legacy_holdout_keys(tmp_path)


def test_v2_search_failure_preserved_without_retry(tmp_path, monkeypatch):
    research_root = tmp_path/'research'
    corpus(monkeypatch, [case(i) for i in range(40)])
    calls = []
    def run(command, **kwargs):
        assert command[command.index('--phase')+1] == 'search'
        assert '--holdout' not in command
        calls.append(command)
        return SimpleNamespace(returncode=9)
    first = run_cycle(tmp_path, run=run)
    assert first['status'] == 'failed' and first['exitCode'] == 9
    second = run_cycle(tmp_path, run=run)
    assert second['status'] == 'unchanged' and len(calls) == 1
    directory = research_root/cycle.COHORT/first['runId']
    assert (directory/'started.json').exists() and (directory/'status.json').exists()
    assert list((research_root/cycle.COHORT/'assignments').glob('*.json'))


def test_interrupted_attempt_never_replayed(tmp_path, monkeypatch):
    corpus(monkeypatch, [case(i) for i in range(40)])
    def interrupted(*args, **kwargs): raise KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        run_cycle(tmp_path, run=interrupted)
    result = run_cycle(tmp_path, run=lambda *a, **kw: pytest.fail('replayed'))
    assert result['status'] == 'unchanged' and result['previous']['status'] == 'interrupted'


def test_v3_uses_shared_choice_decoder_mask_and_abstention():
    row = case(0)
    def provider(_):
        return {'answers': {'route': answer('content', .5)}}, 1
    value = research.evaluate([row], {'id': 'base', 'model': 'fixture'}, provider)
    assert value['count'] == 1 and value['accuracy'] == 1 and value['brier_mean'] is not None
    value = research.evaluate([row], {'id': 'base', 'model': 'fixture', 'abstain_below': .65}, provider)
    assert value['abstention_rate'] == 1
    row['state']['exclusions'] = ['content_creation']; row['routing_choice'] = 'general'
    row['labels'] = {'route': 'general'}
    value = research.evaluate([row], {'id': 'base', 'model': 'fixture'}, provider)
    assert value['accuracy'] == 1   # content is masked; the general/none tie resolves to general
    row['routing_choice'] = 'none'; row['labels'] = {'route': 'none'}
    assert research.evaluate([row], {'id': 'base', 'model': 'fixture'}, provider)['accuracy'] == 0
    row['routing_choice'] = 'general'; row['labels'] = {'route': 'general'}
    assert research.predict([row], {'id': 'base', 'model': 'fixture'}, provider) == {row['case_id']: 'general'}
    assert research.arm_a_metrics([row])['accuracy'] == 1
    row['arm_a_choice'] = None
    assert research.arm_a_metrics([row]) == 'unavailable'


def test_pooled_collection_sources_proceed_and_are_recorded(tmp_path, monkeypatch):
    rows = [case(i) for i in range(40)]
    rows[0]['collection_source_sha256'] = 'b' * 64
    corpus(monkeypatch, rows)
    result = run_cycle(tmp_path)
    assert result['status'] in {'held', 'review_required'} and len(result['sourcesSha256']) == 64
    assert 'provenance' in result


def test_malformed_replay_failure_preserved(tmp_path, monkeypatch):
    corpus(monkeypatch, [case(i) for i in range(40)])
    calls = []
    def invalid(*args, **kwargs):
        calls.append(True)
        raise ValueError('private detail')
    monkeypatch.setattr(cycle.pilot_labels, 'replay_cases', invalid)
    first = run_cycle(tmp_path)
    assert first['status'] == 'failed' and 'private detail' not in json.dumps(first)
    second = run_cycle(tmp_path)
    assert second['status'] == 'unchanged' and len(calls) == 1


def test_review_candidate_reports_promotion_without_holdout(tmp_path, monkeypatch):
    corpus(monkeypatch, [case(i) for i in range(150)])
    result = run_cycle(tmp_path, call=wrong_laya)
    assert result['status'] == 'review_required' and result['holdout'] == 'not_run'
    assert result['releaseEligible'] is False and result['promotion']['earnedMode'] == 'shadow'
    assert result['promotion']['verdict'] == 'hold' and result['promotion']['stats']['n'] > 0
    assert registry_state(tmp_path) is None and [e['event'] for e in ledger_events(tmp_path)] == ['reserve', 'consumed']


def test_too_few_promotion_cases_hold_without_spending_an_attempt(tmp_path, monkeypatch):
    corpus(monkeypatch, [case(i) for i in range(40)])
    result = run_cycle(tmp_path, call=lambda r: pytest.fail('no cohort, no Laya call'))
    assert result['status'] == 'held' and result['reason'] == 'insufficient_promotion_cases'
    assert result['promotion']['required'] == 30 and ledger_events(tmp_path) == []


def test_a_laya_outage_holds_before_reserving_a_cohort(tmp_path, monkeypatch):
    corpus(monkeypatch, [case(i) for i in range(150)])
    with socket.socket() as closed:                                 # a loopback port nothing listens on
        closed.bind(('127.0.0.1', 0))
        monkeypatch.setattr(cycle, 'LAYA_URL', f'http://127.0.0.1:{closed.getsockname()[1]}')
    result = run_cycle(tmp_path, call=None)
    assert result['status'] == 'held' and result['reason'] == 'laya_unavailable'
    assert ledger_events(tmp_path) == [] and registry_state(tmp_path) is None


def test_a_laya_outage_hold_does_not_mark_the_corpus_processed(tmp_path, monkeypatch):
    corpus(monkeypatch, [case(i) for i in range(150)])
    live_url = cycle.LAYA_URL
    with socket.socket() as closed:
        closed.bind(('127.0.0.1', 0))
        monkeypatch.setattr(cycle, 'LAYA_URL', f'http://127.0.0.1:{closed.getsockname()[1]}')
    assert run_cycle(tmp_path, call=None)['reason'] == 'laya_unavailable'
    monkeypatch.setattr(cycle, 'LAYA_URL', live_url)
    retry = run_cycle(tmp_path)                                       # Laya is back: the same corpus is attempted again
    assert retry['status'] == 'review_required' and retry['promotion']['verdict'] == 'pass'
    assert run_cycle(tmp_path)['status'] == 'unchanged'               # a real verdict still marks it processed
    assert list((tmp_path / 'research').rglob('*.laya-unavailable-*'))   # the outage receipt is kept aside


def test_accurate_default_wording_earns_advise_through_the_registry(tmp_path, monkeypatch):
    corpus(monkeypatch, [case(i) for i in range(150)])
    result = run_cycle(tmp_path)
    assert result['status'] == 'review_required' and result['promotion']['verdict'] == 'pass'
    assert result['promotion']['earnedMode'] == 'advise' and result['releaseEligible'] is True
    assert result['promotion']['registry']['status'] == 'mutated'
    entry = registry_state(tmp_path)['decisions']['workflow-fit']
    events = ledger_events(tmp_path)
    assert entry['mode'] == 'advise' and entry['cohortId'] == events[0]['cohortId'] == events[1]['cohortId']
    assert [e['event'] for e in events] == ['reserve', 'consumed'] and events[1]['verdict'] == 'pass'
    assert entry['policySha256'] == events[0]['policySha256'] and entry['layaRevision'] == 'rev-test'
    assert not (tmp_path / 'typed-decisions/modes.json').exists()
    assert run_cycle(tmp_path)['status'] == 'unchanged'


def test_pass_calls_mutate_with_the_gate_binding(tmp_path, monkeypatch):
    corpus(monkeypatch, [case(i) for i in range(150)])
    calls = []
    def mutate(root, decision, to_mode, **kwargs):
        calls.append((decision, to_mode, kwargs))
        return {'revision': 1}
    monkeypatch.setattr(cycle.decision_registry, 'mutate', mutate)
    result = run_cycle(tmp_path)
    (decision, to_mode, kwargs), = calls
    assert (decision, to_mode) == ('workflow-fit', 'advise')
    assert kwargs['actor'] == 'cycle' and kwargs['reason'] == 'gate_pass' and kwargs['expected_revision'] == 0
    event = ledger_events(tmp_path)[0]
    assert kwargs['binding'] == {
        'policySha256': cycle.typed_advice.policy_sha256('workflow-fit', cycle.ADVICE_QUESTION, cycle.ADVICE_POLICY),
        'instrumentSha256': cycle.typed_advice.INSTRUMENT_SHA256, 'layaRevision': 'rev-test',
        'cohortId': event['cohortId']}
    assert kwargs['binding']['policySha256'] == event['policySha256']
    assert result['promotion']['earnedMode'] == 'advise'


def test_registry_refusal_is_recorded_as_held_not_raised(tmp_path, monkeypatch):
    corpus(monkeypatch, [case(i) for i in range(150)])
    def refuse(*args, **kwargs):
        raise cycle.decision_registry.RegistryError('pinned', 'operator pin')
    monkeypatch.setattr(cycle.decision_registry, 'mutate', refuse)
    result = run_cycle(tmp_path)
    assert result['status'] == 'review_required' and result['promotion']['verdict'] == 'pass'
    assert result['promotion']['registry'] == {'status': 'held', 'to': 'advise', 'code': 'pinned'}
    assert result['promotion']['earnedMode'] == 'shadow' and result['releaseEligible'] is False


def test_a_pass_cohort_is_never_reused_by_the_next_attempt(tmp_path, monkeypatch):
    corpus(monkeypatch, [case(i) for i in range(130)])
    monkeypatch.setattr(cycle.decision_registry, 'mutate', lambda *a, **k: {'revision': 1})
    run_cycle(tmp_path)
    first = {i for e in ledger_events(tmp_path) if e['event'] == 'reserve' for i in e['caseIds']}
    corpus(monkeypatch, [case(i) for i in range(240)])
    run_cycle(tmp_path)
    reserves = [e for e in ledger_events(tmp_path) if e['event'] == 'reserve']
    assert [e['attempt'] for e in reserves] == [1, 2] and reserves[1]['alpha'] == reserves[0]['alpha'] / 2
    assert not first & set(reserves[1]['caseIds'])


def test_earned_advise_is_demoted_after_two_evaluations_below_baseline(tmp_path, monkeypatch):
    corpus(monkeypatch, [case(i) for i in range(150)])
    assert run_cycle(tmp_path)['promotion']['earnedMode'] == 'advise'
    corpus(monkeypatch, [case(i) for i in range(165)])
    first = run_cycle(tmp_path, call=shifted_laya)
    assert first['promotion']['branch'] == 'demotion' and first['promotion']['demotion']['below'] is True
    assert first['promotion']['earnedMode'] == 'advise' and len(ledger_events(tmp_path)) == 2   # no new attempt
    corpus(monkeypatch, [case(i) for i in range(180)])
    second = run_cycle(tmp_path, call=shifted_laya)
    assert second['promotion']['demotion']['demote'] is True and second['promotion']['earnedMode'] == 'shadow'
    assert second['promotion']['registry']['status'] == 'mutated'
    state = registry_state(tmp_path)
    assert state['decisions']['workflow-fit']['mode'] == 'shadow'
    audit = (tmp_path / 'typed-decisions/registry-audit.jsonl').read_text()
    assert 'gate_demote' in audit and 'gate_pass' in audit


def test_a_stale_policy_binding_is_reset_to_shadow_before_a_new_attempt(tmp_path, monkeypatch):
    corpus(monkeypatch, [case(i) for i in range(150)])
    run_cycle(tmp_path)
    monkeypatch.setattr(cycle, 'ADVICE_QUESTION', cycle.ADVICE_QUESTION + ' Pick one.')
    corpus(monkeypatch, [case(i) for i in range(260)])
    result = run_cycle(tmp_path)
    assert result['promotion']['verdict'] == 'pass' and result['promotion']['attempt'] == 2
    entry = registry_state(tmp_path)['decisions']['workflow-fit']
    assert entry['mode'] == 'advise' and entry['cohortId'] == result['promotion']['cohortId']
    audit = (tmp_path / 'typed-decisions/registry-audit.jsonl').read_text()
    assert 'binding_stale' in audit


def test_promotion_split_is_never_handed_to_search(tmp_path, monkeypatch):
    rows = [case(i) for i in range(150)]
    corpus(monkeypatch, rows)
    seen = {}
    def run(command, **kwargs):
        run_dir = Path(command[command.index('--manifest')+1]).parents[1]
        seen['dir'] = run_dir
        seen['search'] = {name: [json.loads(l)['case_id'] for l in (run_dir/'split'/f'{name}.jsonl').read_text().splitlines()]
                          for name in ('train', 'validation')}
        seen['candidates'] = (run_dir/'candidates.json').read_text()
        assert not (run_dir/'split/holdout.jsonl').exists() and '--holdout' not in command
        return keep_first(command, **kwargs)
    result = run_cycle(tmp_path, run=run)
    promotion = [json.loads(l)['case_id'] for l in (seen['dir']/'promotion.jsonl').read_text().splitlines()]
    searched = set(seen['search']['train']) | set(seen['search']['validation'])
    assert promotion and searched and not searched & set(promotion)
    assert searched | set(promotion) == {row['case_id'] for row in rows}
    manifest = json.loads((seen['dir']/'split/manifest.json').read_text())
    assert set(manifest['split_counts']) == {'train', 'validation'} and manifest['release_eligible'] is False
    assert (seen['dir']/'promotion.jsonl').stat().st_mode & 0o777 == 0o600
    assert result['promotion']['stats']['n'] == len(promotion)
    reserved = ledger_events(tmp_path)[0]['caseIds']
    assert set(reserved) == set(promotion)
    # The gate's own split rule governs: every promotion group hashes to the promotion side.
    assert all(cycle.typed_promotion.split_of(json.loads(l)['group_id']) == 'promotion'
               for l in (seen['dir']/'promotion.jsonl').read_text().splitlines())


def test_only_the_default_wording_is_evaluated_for_promotion(tmp_path, monkeypatch):
    corpus(monkeypatch, [case(i) for i in range(150)])
    requests = []
    def call(request):
        requests.append(request)
        return laya(request)
    def run(command, **kwargs):               # the search "keeps" a non-default candidate
        options = json.loads(Path(command[command.index('--candidates')+1]).read_text())
        Path(command[command.index('--ledger')+1]).write_text(
            json.dumps({'status': 'keep', 'candidate_sha256': research.digest(options[-1])}) + '\n')
        return SimpleNamespace(returncode=0)
    result = run_cycle(tmp_path, run=run, call=call)
    assert result['candidateId'] != 'baseline' and result['promotion']['earnedMode'] == 'advise'
    assert len(requests) == result['promotion']['stats']['n']
    assert all(r['questions']['route']['instructions'] == 'Route it' for r in requests)   # no override applied
    assert all(set(r['questions']) == {'route'} and r['model'] == 'typed-decisions' for r in requests)


def test_promotion_deadline_counts_unanswered_cases_wrong_and_never_promotes(tmp_path, monkeypatch):
    corpus(monkeypatch, [case(i) for i in range(150)])
    monkeypatch.setattr(cycle.time, 'monotonic', iter(range(0, 10**6, 1000)).__next__)
    result = run_cycle(tmp_path)
    assert result['promotion']['verdict'] == 'hold' and 'coverage_below_minimum' in result['promotion']['reasons']
    assert registry_state(tmp_path) is None and ledger_events(tmp_path)[-1]['verdict'] == 'hold'


def test_cross_split_identity_rejected_when_materializing(tmp_path):
    a, b, c = case(1), case(2), case(3)
    b['grouping_keys'].append(a['grouping_keys'][0])
    with pytest.raises(ValueError, match='duplicate identity'):
        research.prepare_corpus([a,b,c], 'fixture', tmp_path/'split',
                                split_assignments={'1':'train','2':'validation','3':'holdout'})


def test_stored_assignment_sentinel_is_rejected():
    record = {'cohort': cycle.COHORT, 'normalization': cycle.NORMALIZATION,
              'keys': ['input:' + '0' * 64], 'split': 'train'}
    with pytest.raises(ValueError, match='invalid_grouping_keys'):
        cycle.grouping([case(1)], [record])


def test_preflight_identity_changes_after_bound_input_repair(tmp_path, monkeypatch):
    receipts = tmp_path/'receipts'
    corpus(monkeypatch, [case(i) for i in range(40)])
    receipts.mkdir(); receipt = receipts/(cycle.digest('bound') + '.json')
    receipt.write_text('malformed')
    def invalid(*a, **kw): raise ValueError('invalid fixture')
    monkeypatch.setattr(cycle.pilot_labels, 'replay_cases', invalid)
    first = run_cycle(tmp_path)
    assert run_cycle(tmp_path)['status'] == 'unchanged'
    receipt.write_text('{"repaired":true}')
    second = run_cycle(tmp_path)
    assert first['status'] == second['status'] == 'failed'
    assert first['runId'] != second['runId']
    assert len(list((tmp_path/'research'/cycle.COHORT/'preflight-failures').glob('*.json'))) == 2


def test_request_snapshot_repair_changes_preflight_identity(tmp_path, monkeypatch):
    corpus(monkeypatch, [case(i) for i in range(40)])
    def invalid(*a, **kw): raise ValueError('invalid fixture')
    monkeypatch.setattr(cycle.pilot_labels, 'replay_cases', invalid)
    first = run_cycle(tmp_path)
    snapshots = tmp_path/'request-snapshots'; snapshots.mkdir()
    (snapshots/(cycle.digest('x') + '.json')).write_text('{}')
    assert run_cycle(tmp_path)['runId'] != first['runId']


def test_legacy_metadata_correction_creates_new_attempt_preserving_hold(tmp_path, monkeypatch):
    research_root = tmp_path/'research'
    corpus(monkeypatch, [case(i) for i in range(40)])
    split = research_root/'legacy/split'; split.mkdir(parents=True)
    manifest = split/'manifest.json'; manifest.write_text('{}')
    first = run_cycle(tmp_path, run=lambda *a, **k: pytest.fail('legacy metadata unavailable'))
    assert first['reason'] == 'legacy_holdout_membership_unavailable'
    old = (research_root/cycle.COHORT/first['runId']/'status.json').read_bytes()
    manifest.write_text(json.dumps({'holdout_grouping_keys': [key('session', 'unseen')]}))
    second = run_cycle(tmp_path, run=lambda *a, **k: SimpleNamespace(returncode=7))
    assert second['status'] == 'failed' and second['exitCode'] == 7
    assert first['runId'] != second['runId']
    assert (research_root/cycle.COHORT/first['runId']/'status.json').read_bytes() == old


def test_legacy_input_keys_are_not_claimed_cross_version_comparable(tmp_path):
    split = tmp_path/'legacy/split'; split.mkdir(parents=True)
    manifest = split/'manifest.json'
    manifest.write_text(json.dumps({'holdout_grouping_keys': [key('input', 'opaque')]}))
    with pytest.raises(ValueError, match='legacy_holdout_membership_unavailable'):
        cycle.legacy_holdout_keys(tmp_path)
    manifest.write_text(json.dumps({'holdout_grouping_keys': [key('session', 1), key('input', 'opaque')]}))
    assert cycle.legacy_holdout_keys(tmp_path) == {key('session', 1)}


def test_mask_label_conflict_holds_whole_corpus_without_changing_label(tmp_path, monkeypatch):
    rows = [case(i) for i in range(40)]
    rows[1]['state']['exclusions'] = ['content_creation']
    rows[1]['routing_choice'] = 'content'; rows[1]['labels'] = {'route': 'content'}
    corpus(monkeypatch, rows)
    result = run_cycle(tmp_path, run=lambda *a, **kw: pytest.fail('launched contradictory corpus'))
    assert result['status'] == 'held' and result['reason'] == 'label_contradicts_exclusions'
    assert result['labels'] == 40 and rows[1]['routing_choice'] == 'content'


def test_critical_abstention_cannot_reduce_critical_misses():
    row = case(0); row['stratum'] = 'critical_safety'
    def provider(_):
        return {'answers': {'route': answer('content', .5)}}, 1
    result = research.evaluate([row], {'id': 'abstain', 'model': 'fixture', 'abstain_below': .8}, provider)
    assert result['abstention_rate'] == 1 and result['critical_misses'] == 1
    baseline = research.evaluate([row], {'id': 'base', 'model': 'fixture'}, provider)
    assert baseline['accuracy'] == 1 and baseline['critical_misses'] == 0


def test_replay_without_cases_holds_with_actual_label_inventory(tmp_path, monkeypatch):
    corpus(monkeypatch, [], count=40)
    result = run_cycle(tmp_path)
    assert result['labels'] == 40 and result['reason'] == 'no_replayable_labels'


def test_preflight_failure_receipt_write_failure_is_structured(tmp_path, monkeypatch):
    corpus(monkeypatch, [case(i) for i in range(40)])
    def invalid(*a, **kw): raise ValueError('invalid')
    def denied(*a, **kw): raise PermissionError('private path')
    monkeypatch.setattr(cycle.pilot_labels, 'replay_cases', invalid)
    monkeypatch.setattr(cycle, 'private_write', denied)
    result = run_cycle(tmp_path)
    assert result['status'] == 'failed' and result['persistence'] == 'unavailable'
    assert 'private path' not in json.dumps(result)


def test_cli_invalid_bounds_is_structured_json(tmp_path):
    import subprocess, sys
    for args in (['--minimum-labels', '19'], ['--deadline-seconds', '0']):
        done = subprocess.run([sys.executable, str(ROOT/'evals/typed-decision/pilot_cycle.py'),
                               '--research-root', str(tmp_path/'research'), *args],
                              text=True, capture_output=True, timeout=10)
        assert done.returncode == 1 and not done.stderr
        assert json.loads(done.stdout)['reason'] == 'invalid_research_bounds'


def taxonomy_case(index):
    row = case(index)
    return {**row, 'stratum': 'ordinary', 'label_basis': 'ai_model_reviewed', 'family': 'feature_delivery',
            'choice_basis': 'explicit'}


def test_taxonomy_labels_below_floor_hold_with_basis_facts(tmp_path, monkeypatch):
    corpus(monkeypatch, [], count=8, choice_basis='derived:family-map-v1')
    result = cycle.cycle(tmp_path/'pilot', tmp_path/'receipts', tmp_path/'research')
    assert result['reason'] == 'insufficient_accepted_labels' and result['labels'] == 0
    assert result['taxonomyLabels'] == 8 and result['derivedChoiceLabels'] == 8
    corpus(monkeypatch, [], count=8, bases=('human_adjudicated',))
    result = cycle.cycle(tmp_path/'pilot', tmp_path/'receipts', tmp_path/'research')
    assert result['labels'] == 0 and result['acceptedBases'] == ['human_adjudicated']


def test_search_records_policy_provenance_and_exploratory_scope(tmp_path, monkeypatch):
    corpus(monkeypatch, [taxonomy_case(i) for i in range(150)])
    result = run_cycle(tmp_path)
    assert result['status'] == 'review_required' and result['coverage']['holdReasons'] == []
    assert result['config']['acceptedBases'] == ['human_adjudicated', 'ai_model_reviewed']
    assert len(result['config']['labelPolicySha256']) == 64 and result['labelBasis'] == {'ai_model_reviewed': 150}
    assert 'exploratory' in result['claimScope'] and result['provenance']['replayed'] is True
    assert set(result['coverage']['routingChoices']) == set(CHOICES)


def test_research_rows_accept_only_known_label_bases(tmp_path):
    path = tmp_path/'cases.jsonl'
    path.write_text(json.dumps(taxonomy_case(1)) + '\n')
    assert research.read_jsonl(path)[0]['label_basis'] == 'ai_model_reviewed'
    path.write_text(json.dumps({**taxonomy_case(1), 'label_basis': 'crowd'}) + '\n')
    with pytest.raises(ValueError, match='label basis'):
        research.read_jsonl(path)


def test_missing_split_holds_before_any_search(tmp_path, monkeypatch):
    corpus(monkeypatch, [case(i) for i in range(40)])
    real = cycle.grouping
    def without_promotion(rows, assignments):
        rows, split_map, records = real(rows, assignments)
        return rows, {group: ('train' if split == 'promotion' else split) for group, split in split_map.items()}, records
    monkeypatch.setattr(cycle, 'grouping', without_promotion)
    result = run_cycle(tmp_path, run=lambda *a, **kw: pytest.fail('searched with a missing split'))
    assert result['status'] == 'held' and result['reason'] == 'insufficient_split_groups'
    assert registry_state(tmp_path) is None and ledger_events(tmp_path) == []


@pytest.mark.parametrize('guarded', ['evaluator', 'decoder', 'promoter'])
def test_changed_guarded_source_during_promotion_never_mutates_the_registry(tmp_path, monkeypatch, guarded):
    corpus(monkeypatch, [case(i) for i in range(150)])
    path = {'evaluator': ROOT/'evals/typed-decision/research.py',
            'decoder': ROOT/'rhize-context-manager/scripts/pilot_routing.py',
            'promoter': ROOT/'evals/typed-decision/typed_promotion.py'}[guarded]
    source, real, state = path.read_bytes(), cycle.digest, {'changed': False}
    monkeypatch.setattr(cycle, 'digest', lambda value: 'f' * 64 if state['changed'] and value == source else real(value))
    def call(request):
        state['changed'] = True
        return laya(request)
    result = run_cycle(tmp_path, call=call)
    assert state['changed'] and result['status'] == 'failed' and result['reason'] == 'ValueError'
    assert registry_state(tmp_path) is None


class Recorder(BaseHTTPRequestHandler):
    """Fake Laya (or proxy/redirect target); behaviour and hits live on the server object."""
    def do_GET(self):
        self.server.hits.append(self.path)
        payload = json.dumps({'loaded': ['typed-decisions']}).encode()
        self.send_response(200); self.send_header('Content-Length', str(len(payload))); self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
        self.server.hits.append(self.path)
        if self.server.mode == 'redirect':
            self.send_response(302); self.send_header('Location', self.server.target + '/v1/systemone')
            self.send_header('Content-Length', '0'); self.end_headers()
            return
        request = json.loads(body)
        model = 'other-checkpoint' if self.server.mode == 'wrong_model' else request['model']
        answers = {'wrong': {}} if self.server.mode == 'wrong_answers' else {'route': answer('content')}
        payload = json.dumps({'routing': {'model': model}, 'answers': answers}).encode()
        self.send_response(200); self.send_header('Content-Length', str(len(payload))); self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


@pytest.fixture
def servers():
    started = []
    def start(mode='ok', target=None):
        httpd = ThreadingHTTPServer(('127.0.0.1', 0), Recorder)
        httpd.hits, httpd.mode, httpd.target = [], mode, target
        threading.Thread(target=lambda: httpd.serve_forever(poll_interval=0.01), daemon=True).start()
        started.append(httpd)
        return httpd, f'http://127.0.0.1:{httpd.server_address[1]}'
    yield start
    for httpd in started:
        httpd.shutdown(); httpd.server_close()


LAYA_REQUEST = {'model': 'typed-decisions', 'state': {'request': 'request 1'}, 'questions': {'route': {}}}


def test_research_laya_call_ignores_proxy_environment(servers, monkeypatch):
    proxy, proxy_url = servers()
    laya_server, url = servers()
    for name in ('http_proxy', 'HTTP_PROXY', 'all_proxy', 'ALL_PROXY'):
        monkeypatch.setenv(name, proxy_url)
    monkeypatch.delenv('NO_PROXY', raising=False); monkeypatch.delenv('no_proxy', raising=False)
    result, latency = research.local_call(url, LAYA_REQUEST)
    assert result['answers']['route']['choice'] == 'content' and latency >= 0
    assert laya_server.hits == ['/health', '/v1/systemone'] and proxy.hits == []


def test_research_laya_call_refuses_redirects_and_localhost(servers):
    target, target_url = servers()
    redirecting, url = servers('redirect', target_url)
    with pytest.raises(ValueError, match='redirect_refused'):
        research.local_call(url, LAYA_REQUEST)
    assert redirecting.hits == ['/health', '/v1/systemone'] and target.hits == []
    port = url.rsplit(':', 1)[1]
    with pytest.raises(ValueError, match='loopback_ip_url_required'):
        research.local_call(f'http://localhost:{port}', LAYA_REQUEST)
    assert redirecting.hits == ['/health', '/v1/systemone']


@pytest.mark.parametrize('mode, message', [('wrong_model', 'different checkpoint'), ('wrong_answers', 'answers do not match')])
def test_research_laya_call_keeps_response_validation(servers, mode, message):
    _, url = servers(mode)
    with pytest.raises(ValueError, match=message):
        research.local_call(url, LAYA_REQUEST)
