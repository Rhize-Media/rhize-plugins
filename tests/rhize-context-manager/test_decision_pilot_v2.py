"""Invented intent fixtures; no production prompts, provider or human labels."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / 'rhize-context-manager/scripts'
sys.path.insert(0, str(SCRIPTS))
import decision_pilot as pilot
import decision_pilot_v2 as v2
import workflow_selection as workflow
import workflow_task_context as context
from pilot_routing import decode_scores


def make(tmp_path, turn='task', *, kind='new_task', action='implement', domain='software',
         exclusions=None, parent=None, prebound=None, capture=True, session='session'):
    receipts, root = tmp_path / 'receipts', tmp_path / 'pilot'
    receipt, _ = workflow.opportunity({'prompt': 'invented fixture ' + turn, 'session_id': session, 'turn_id': turn},
        'codex', receipts, {'decisionPilot': {'enabled': True, 'mode': 'shadow', 'cohort': 'v2'}})
    evidence = {'schemaVersion': context.SCHEMA, 'opportunityId': receipt['opportunityId'],
                'promptHash': receipt['promptHash'], 'sessionHash': receipt['sessionHash'],
                'eventKind': kind, 'action': action, 'domain': domain, 'exclusions': exclusions or [],
                'parentOpportunityId': parent, 'preboundFamily': prebound}
    if capture:
        context.capture_context(receipts, receipt['opportunityId'], evidence,
            seal=lambda c, r: pilot.enqueue_v2(c, r, root, spawn=False, receipts=receipts))
    return root, receipts, receipt, evidence


def call(url, request):
    assert url == 'http://127.0.0.1:8000'
    assert set(request['state']) == {'eventKind', 'action', 'domain', 'exclusions'}
    return {'routing': {'model': 'typed-decisions'},
            'answers': {f'c{i}': {'type': 'noul', 'noul': n} for i, n in enumerate((.9, .8, .2))},
            'usage': {'input_tokens': 10, 'output_tokens': 0}}, 3.2


def consult(tmp_path, receipts, receipt, kind='general'):
    path = tmp_path / 'consult-evidence'; path.write_text('invented lookup result')
    return context.capture_consultation(receipts, receipt['opportunityId'], kind, path)


def label(tmp_path, root, receipt):
    observation = workflow.read_json(root / 'v2/observations' / (receipt['opportunityId'] + '.json'))
    path = tmp_path / 'label.json'
    path.write_text(json.dumps({'opportunityId': receipt['opportunityId'], 'sourceSha256': observation['sourceSha256'],
        'choice': 'general', 'reviewer': 'human-fixture', 'basis': 'human_adjudicated',
        'stratum': 'ordinary', 'reviewEvidenceSha256': 'c' * 64}))
    pilot.bind_evidence(root, receipt['opportunityId'], path, 'labels')


def test_v2_context_seals_private_request_before_consultation(tmp_path):
    root, receipts, receipt, _ = make(tmp_path)
    path = root / 'v2/observations' / (receipt['opportunityId'] + '.json')
    before = path.read_bytes()
    observation = json.loads(before)
    assert 'invented fixture' not in before.decode()
    assert observation['requestSha256'] == workflow.digest(v2.canonical(observation['request']))
    assert observation['contextSha256'] == observation['context']['contextSha256']
    consult(tmp_path, receipts, receipt)
    workflow.decide(receipts, SimpleNamespace(id=receipt['opportunityId'], decision='no_match', workflow=None,
                                             variant=None, reason='no_suitable_workflow'))
    pilot.drain(root, call, receipts=receipts, cohort='v2')
    row = v2.joined(root, receipts)[0]
    assert row['armA'] == 'general' and row['armB'] == 'content'
    assert path.read_bytes() == before
    assert not (root / 'observations').exists()


def test_intent_pairs_distinct_and_exclusion_mask_shared(tmp_path):
    root, receipts, _, _ = make(tmp_path, 'defer', domain='content', action='review', exclusions=['content_creation'])
    make(tmp_path, 'create', domain='content', action='create')
    make(tmp_path, 'handoff', domain='content', action='handoff')
    make(tmp_path, 'revise', domain='content', action='revise')
    pilot.drain(root, call, receipts=receipts, cohort='v2')
    rows = v2.joined(root, receipts)
    assert len({r['observation']['requestSha256'] for r in rows}) == 4
    masked = next(r for r in rows if r['context']['exclusions'])
    assert masked['armB'] == 'general'
    assert all(p['candidateId'] != 'content' for p in masked['result']['ranking'])


def test_five_denominators_reconcile_and_operational_calls_never_run(tmp_path):
    root, receipts, _, _ = make(tmp_path, 'eligible')
    make(tmp_path, 'observer', kind='background_observer')
    make(tmp_path, 'unknown', kind='unknown')
    make(tmp_path, 'missing', capture=False)
    _, _, held, data = make(tmp_path, 'held')
    data['action'] = 'review'
    with pytest.raises(ValueError): context.capture_context(receipts, held['opportunityId'], data)
    calls = []
    pilot.drain(root, lambda *a: (calls.append(a) or call(*a)), receipts=receipts, cohort='v2')
    summary = pilot.report(root, receipts)
    assert summary['opportunities'] == 0 and summary['totalRawEvents'] == 5
    coverage = summary['v2Coverage']
    assert all(coverage[k] == 1 for k in ('eligible','excluded','held','unknown','missing'))
    assert coverage['rawEvents'] == sum(coverage[k] for k in ('eligible','excluded','held','unknown','missing'))
    assert len(calls) == 1
    assert coverage['nativeOriginVerified'] == 0


def test_request_tamper_and_later_context_conflict_hold_old_score(tmp_path):
    root, receipts, receipt, data = make(tmp_path)
    pilot.drain(root, call, receipts=receipts, cohort='v2')
    data['domain'] = 'content'
    with pytest.raises(ValueError): context.capture_context(receipts, receipt['opportunityId'], data)
    row = v2.joined(root, receipts)[0]
    assert row['bucket'] == 'held' and row['armB'] is None
    assert pilot.drain(root, lambda *a: pytest.fail('retried'), receipts=receipts, cohort='v2')['processed'] == 0


def test_continuation_inherits_sealed_choice_without_rescoring(tmp_path):
    root, receipts, parent, _ = make(tmp_path, 'parent')
    pilot.drain(root, call, receipts=receipts, cohort='v2')
    _, _, child, _ = make(tmp_path, 'child', kind='continuation', parent=parent['opportunityId'])
    pilot.drain(root, lambda *a: pytest.fail('rescored continuation'), receipts=receipts, cohort='v2')
    row = next(r for r in v2.joined(root, receipts) if r['id'] == child['opportunityId'])
    assert row['bucket'] == 'excluded' and row['armB'] is None and row['inheritedArmB'] == 'content'
    assert row['observation']['request'] is None


def test_packet_deduplicates_with_counts_and_strata(tmp_path):
    root, receipts, _, _ = make(tmp_path, 'a')
    make(tmp_path, 'b')
    _, _, agreement, _ = make(tmp_path, 'agreement', action='review')
    consult(tmp_path, receipts, agreement, 'content')
    make(tmp_path, 'abstention', action='validate')
    make(tmp_path, 'missing', capture=False)
    pilot.drain(root, call, receipts=receipts, cohort='v2')
    # Preserve an immutable failed result fixture as an actual unavailable stratum.
    row = next(r for r in v2.joined(root, receipts) if (r['context'] or {}).get('action') == 'validate')
    (root / 'v2/results' / (row['id'] + '.json')).write_text(json.dumps({'status':'unavailable','usage':None}))
    result = pilot.queue(root, receipts)['dailyPacket']
    assert len(result['items']) <= 10 and result['candidateRawCount'] == 5
    assert {'agreement','scoring_unavailable','context_hold','baseline_pending'} <= {i['reason'] for i in result['items']}
    assert any(i['duplicateCount'] == 2 for i in result['items'])
    assert all(i['basis'] == 'assistant_triage_not_human_label' for i in result['items'])


def test_v2_export_only_eligible_bound_human_labels(tmp_path):
    root, receipts, receipt, _ = make(tmp_path)
    consult(tmp_path, receipts, receipt)
    label(tmp_path, root, receipt)
    out = tmp_path / 'cases.jsonl'
    assert pilot.export_cases(root, receipts, out, cohort='v2')['count'] == 1
    case = json.loads(out.read_text())
    assert case['routing_choice'] == 'general' and case['arm_a_choice'] == 'general'
    assert case['candidate_ids'] == ['content','general','none']
    assert set(k.split(':')[0] for k in case['grouping_keys']) == {'session','task','input','prompt'}
    assert case['cohort_version'] == 'workflow-pilot-v2'
    _, _, excluded, _ = make(tmp_path, 'excluded', kind='status')
    with pytest.raises(ValueError, match='only eligible'): label(tmp_path, root, excluded)


def test_measurement_facts_never_establish_acceptance(tmp_path):
    root, receipts, receipt, _ = make(tmp_path)
    row = v2.joined(root, receipts)[0]
    fact = {'opportunityId': row['id'], 'sourceSha256':row['observation']['sourceSha256'],
            'receiptSourceSha256':row['context']['sourceBindingSha256'], 'taskRootId':row['context']['taskRootId'],
            'sessionHash': receipt['sessionHash'], 'basis':'automatic_artifact','executedVariant':'A_incumbent',
            'status':'completed','exitCode':2,'durationMs':25, 'bindingStatus':'bound',
            'schema':'rhize-workflow-check-measurement-v2','reasonCode':None,
            'observedAt':'2026-09-28T13:00:00+00:00', 'cleanupStatus':'not_required',
            'stdoutSha256':'d'*64, 'stderrSha256':'e'*64, 'measurementSourceSha256':'f'*64,
            'outputComplete':True, 'forwardTruncated':False}
    pilot.save_once(root/'v2/measurements', 'a'*64, fact)
    bad = {**fact,'opportunityId':'b'*64}
    pilot.save_once(root/'v2/measurements', 'b'*64, bad)
    coverage = pilot.report(root, receipts)['v2Coverage']
    metrics = coverage['measurements']
    assert metrics['boundRecords'] == 1 and metrics['failedChecks'] == 1
    assert metrics['heldOrUnboundRecords'] == 1 and metrics['measuredCheckDurationMs'] == 25
    assert coverage['acceptedTasks'] == 0 and coverage['completeAgentUsage'] == 0


@pytest.mark.parametrize('score', [float('nan'), float('inf'), -.1, 1.1, True, '0.5'])
def test_decoder_rejects_invalid_scores(score):
    with pytest.raises(ValueError): decode_scores({'content':score,'general':.5,'none':.5})


def test_decoder_tie_mask_and_threshold():
    scores = {'content':.5,'general':.5,'none':.5}
    assert decode_scores(scores)['choice'] == 'content'
    assert decode_scores(scores, exclusions=['content_creation'])['choice'] == 'general'
    assert decode_scores(scores, abstain_below=.6)['choice'] is None


def test_cohort_scoped_drain_does_not_touch_old_observations(tmp_path):
    root, receipts, _, _ = make(tmp_path)
    old, _ = workflow.opportunity({'prompt':'workflow','session_id':'old','turn_id':'old'}, 'codex', receipts,
                                  {'decisionPilot':{'enabled':True,'mode':'shadow'}})
    pilot.enqueue('workflow', old, root, spawn=False)
    pilot.drain(root, call, receipts=receipts, cohort='v2')
    assert not (root/'results').exists()
    assert len(list((root/'v2/results').glob('*.json'))) == 1


def test_source_and_result_metric_mismatches_hold_without_breaking_report(tmp_path):
    root, receipts, receipt, _ = make(tmp_path)
    pilot.drain(root, call, receipts=receipts, cohort='v2')
    path = root/'v2/results'/(receipt['opportunityId']+'.json')
    value = json.loads(path.read_text()); value['latencyMs'] = float('nan'); path.write_text(json.dumps(value))
    assert pilot.report(root, receipts)['v2Coverage']['held'] == 1
    path.unlink()
    observation = root/'v2/observations'/(receipt['opportunityId']+'.json')
    value = json.loads(observation.read_text()); value['sourceSha256'] = 'a'*64; observation.write_text(json.dumps(value))
    assert v2.joined(root, receipts)[0]['reason'] == 'source_changed'


def test_operational_v2_events_do_not_create_labels_or_provider_usage(tmp_path):
    root, receipts, receipt, _ = make(tmp_path, kind='background_observer')
    pilot.drain(root, lambda *a: pytest.fail('background scored'), receipts=receipts, cohort='v2')
    report = pilot.report(root, receipts)['v2Coverage']
    assert report['excluded'] == 1 and report['scored'] == 0 and report['localInputTokens'] is None
    assert report['humanLabels'] == 0 and report['acceptedTasks'] == 0


def test_continuation_cannot_reference_an_unrelated_parent_result(tmp_path):
    root, receipts, parent, _ = make(tmp_path, 'parent')
    _, _, other, _ = make(tmp_path, 'other', session='another-session')
    _, _, child, _ = make(tmp_path, 'child', kind='continuation', parent=parent['opportunityId'])
    path = root/'v2/observations'/(child['opportunityId']+'.json')
    value = json.loads(path.read_text())
    other_observation = workflow.read_json(root/'v2/observations'/(other['opportunityId']+'.json'))
    value['inherited'] = {'opportunityId':other['opportunityId'], 'requestSha256':other_observation['requestSha256'],
                          'sourceSha256':other_observation['sourceSha256']}
    path.write_text(json.dumps(value))
    row = next(r for r in v2.joined(root,receipts) if r['id']==child['opportunityId'])
    assert row['bucket'] == 'held' and row['reason'] == 'parent_reference_changed'


def test_export_and_research_share_route_decoder(tmp_path):
    import importlib.util
    source = SCRIPTS.parents[1]/'evals/typed-decision/research.py'
    spec = importlib.util.spec_from_file_location('pilot_v2_research_integration', source)
    research = importlib.util.module_from_spec(spec); spec.loader.exec_module(research)
    root, receipts, receipt, _ = make(tmp_path, exclusions=['content_creation'])
    label(tmp_path, root, receipt)
    out = tmp_path/'cases.jsonl'
    pilot.export_cases(root, receipts, out, cohort='v2')
    case = research.read_jsonl(out)[0]
    observation = workflow.read_json(root/'v2/observations'/(receipt['opportunityId']+'.json'))
    response, _ = call('http://127.0.0.1:8000', observation['request'])
    live = v2.assess(observation, receipts, call)
    offline = research.decode_route(case, response, 0)
    assert live['choice'] == offline['choice'] == 'general'
    assert live['ranking'] == offline['ranking']


def test_continuation_cannot_add_or_remove_parent_exclusions(tmp_path):
    root, receipts, parent, _ = make(tmp_path, 'parent', exclusions=['content_creation'])
    pilot.drain(root, call, receipts=receipts, cohort='v2')
    with pytest.raises(ValueError, match='continuation_intent_conflict'):
        make(tmp_path, 'changed-child', kind='continuation', parent=parent['opportunityId'], exclusions=[])
    _, _, child, _ = make(tmp_path, 'same-child', kind='continuation', parent=parent['opportunityId'], exclusions=['content_creation'])
    pilot.drain(root, lambda *a: pytest.fail('continuation rescored'), receipts=receipts, cohort='v2')
    row = next(r for r in v2.joined(root, receipts) if r['id']==child['opportunityId'])
    assert row['bucket']=='excluded' and row['inheritedArmB']=='general'
    assert pilot.report(root, receipts)['v2Coverage']['inheritedRecommendations']==1


def test_missing_consultation_is_missing_and_explicit_none_is_recordable(tmp_path):
    root, receipts, receipt, _ = make(tmp_path)
    assert v2.joined(root, receipts)[0]['armA'] is None
    consult(tmp_path, receipts, receipt, 'none')
    assert v2.joined(root, receipts)[0]['armA'] == 'none'
    path = receipts.parent/'consultations'/(receipt['opportunityId']+'.json')
    value=json.loads(path.read_text()); value['kind']='invented'; path.write_text(json.dumps(value))
    row=v2.joined(root, receipts)[0]
    assert row['bucket']=='held' and row['reason']=='invalid_consultation'


def test_provider_failure_packet_is_not_a_model_abstention(tmp_path):
    root, receipts, _, _ = make(tmp_path)
    def fail(*args): raise TimeoutError('private transport text')
    pilot.drain(root, fail, receipts=receipts, cohort='v2')
    items=pilot.queue(root, receipts)['dailyPacket']['items']
    assert len(items)==1 and items[0]['reason']=='scoring_unavailable'
    assert 'private transport' not in json.dumps(items)


def test_stale_source_label_refused_before_write(tmp_path):
    root, receipts, receipt, _=make(tmp_path)
    path=root/'v2/observations'/(receipt['opportunityId']+'.json')
    value=json.loads(path.read_text()); value['sourceSha256']='a'*64; path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match='source_changed'): label(tmp_path, root, receipt)
    assert not (root/'v2/labels').exists()


def test_parent_source_policy_and_enqueue_hold_are_explicit(tmp_path):
    root, receipts, parent, _=make(tmp_path,'parent')
    _, _, child, _=make(tmp_path,'child',kind='continuation',parent=parent['opportunityId'])
    parent_path=root/'v2/observations'/(parent['opportunityId']+'.json')
    value=json.loads(parent_path.read_text()); value['sourceSha256']='a'*64; parent_path.write_text(json.dumps(value))
    child_path=root/'v2/observations'/(child['opportunityId']+'.json')
    child_value=json.loads(child_path.read_text()); child_value['inherited']['sourceSha256']='a'*64
    v2.validate_observation(child_value,receipts,child['opportunityId'],require_current_source=False,root=root)
    with pytest.raises(ValueError,match='parent_source_changed'):
        v2.validate_observation(child_value,receipts,child['opportunityId'],require_current_source=True,root=root)
    with pytest.raises(ValueError,match='parent_source_changed'):
        make(tmp_path,'late-child',kind='continuation',parent=parent['opportunityId'])
    assert len(list((root/'v2/observations').glob('*.json')))==2


def test_noncontinuation_rejects_inherited_metadata(tmp_path):
    root, receipts, receipt, _=make(tmp_path)
    path=root/'v2/observations'/(receipt['opportunityId']+'.json')
    value=json.loads(path.read_text()); value['inherited']={'opportunityId':'a'*64}
    path.write_text(json.dumps(value))
    row=v2.joined(root,receipts)[0]
    assert row['bucket']=='held' and row['reason']=='unexpected_inherited'


@pytest.mark.parametrize('reason', ['parent_request_changed','parent_reference_changed','parent_request_missing',
                                   'ineligible_request','invalid_usage','provider_answer_type_mismatch','invalid_latency'])
def test_drain_preserves_bounded_v2_failure_reason(tmp_path, reason):
    root, receipts, receipt, _=make(tmp_path)
    def fail(*args): raise ValueError(reason)
    pilot.drain(root,fail,receipts=receipts,cohort='v2')
    result=workflow.read_json(root/'v2/results'/(receipt['opportunityId']+'.json'))
    assert result['reasonCode']==reason
    if reason in v2.HELD_REASONS:
        assert v2.joined(root,receipts)[0]['bucket']=='held'


@pytest.mark.parametrize('change', [
    {'schema':'unknown'}, {'stdoutSha256':'not-a-digest'}, {'measurementSourceSha256':None},
    {'outputComplete':'true'}, {'forwardTruncated':0}, {'status':'completed','exitCode':None},
    {'status':'completed','cleanupStatus':'failed'}, {'status':'timeout','outputComplete':True},
    {'status':'launch_failed','exitCode':1}, {'status':'interrupted','cleanupStatus':'not_required','exitCode':-9},
    {'durationMs':float('nan')}, {'observedAt':'2026-09-28'}, {'extra':True}])
def test_measurement_reader_rejects_malformed_or_incoherent_facts(change):
    value={'schema':'rhize-workflow-check-measurement-v2','opportunityId':'a'*64,
           'sessionHash':'b'*64,'sourceSha256':'c'*64,'receiptSourceSha256':'d'*64,'taskRootId':'e'*64,
           'basis':'automatic_artifact','executedVariant':'A_incumbent','bindingStatus':'bound','reasonCode':None,
           'status':'completed','exitCode':0,'cleanupStatus':'not_required','durationMs':10,
           'stdoutSha256':'f'*64,'stderrSha256':'a'*64,'measurementSourceSha256':'b'*64,
           'observedAt':'2026-09-28T13:00:00+00:00','outputComplete':True,'forwardTruncated':False}
    assert v2.valid_measurement(value)
    assert not v2.valid_measurement({**value,**change})
