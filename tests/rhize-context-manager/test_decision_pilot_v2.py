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
import workflow_context_packet as packets
from pilot_routing import decode_choice, decode_scores


def make(tmp_path, turn='task', *, kind='new_task', action='implement', domain='software',
         exclusions=None, parent=None, prebound=None, capture=True, session='session', text=None, snapshot=True):
    receipts, root = tmp_path / 'receipts', tmp_path / 'pilot'
    payload = {'prompt': text or 'invented fixture ' + turn, 'session_id': session, 'turn_id': turn}
    receipt, _ = workflow.opportunity(payload, 'codex', receipts,
        {'decisionPilot': {'enabled': True, 'mode': 'shadow', 'cohort': 'v2'}})
    if snapshot:
        packets.capture_request_snapshot(receipts, receipt, payload)
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
    assert set(request['state']) == {'request', 'eventKind', 'action', 'domain', 'exclusions'}
    assert set(request['questions']) == {'route'}
    return answer({'content': .6, 'general': .3, 'none': .1}), 3.2


def answer(probabilities, **overrides):
    value = {'type': 'choice', 'probabilities': probabilities,
             'choice': max(probabilities, key=probabilities.get)}
    return {'routing': {'model': 'typed-decisions'}, 'answers': {'route': {**value, **overrides}},
            'usage': {'input_tokens': 10, 'output_tokens': 0}}


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
    assert observation['request']['state']['request'] == 'invented fixture task'
    assert observation['requestSha256'] == workflow.digest(v2.canonical(observation['request']))
    assert observation['contextSha256'] == observation['context']['contextSha256']
    consult(tmp_path, receipts, receipt)
    workflow.decide(receipts, SimpleNamespace(id=receipt['opportunityId'], decision='no_match', workflow=None,
                                             variant=None, reason='no_suitable_workflow'))
    pilot.drain(root, call, receipts=receipts, cohort='v2')
    row = v2.joined(root, receipts)[0]
    assert row['armA'] == 'general' and row['armB'] == 'content'
    assert 'invented fixture' not in (root / 'v2/results' / (receipt['opportunityId'] + '.json')).read_text()
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
    root, receipts, _, _ = make(tmp_path, 'a', text='same invented request')
    make(tmp_path, 'b', text='same invented request')
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
    assert case['cohort_version'] == 'workflow-pilot-v3' and case['normalization_version'] == 'workflow-input-v3'
    assert case['labels'] == {'route': 'general'} and case['arm_a'] == {'route': 'general'}
    assert set(case['questions']) == {'route'}
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
    offline, _ = research.decode_route_v3(case, response, 0)
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


def test_collection_funnel_counts_events_and_distinct_eligible_roots(tmp_path):
    root, receipts, parent, _ = make(tmp_path, 'task')
    consult(tmp_path, receipts, parent)
    make(tmp_path, 'followup', kind='continuation', parent=parent['opportunityId'])
    make(tmp_path, 'worker', kind='background_observer')
    make(tmp_path, 'routine', kind='scheduled')
    make(tmp_path, 'unknown', kind='unknown')
    make(tmp_path, 'missing', capture=False)
    _, _, held, data = make(tmp_path, 'conflict')
    data['domain'] = 'content'
    with pytest.raises(ValueError):
        context.capture_context(receipts, held['opportunityId'], data)
    pilot.drain(root, call, receipts=receipts, cohort='v2')
    coverage = pilot.report(root, receipts)['v2Coverage']
    funnel = coverage['collectionFunnel']
    assert funnel['rawEvents'] == 7 and funnel['contextCapturedEvents'] == 5
    assert funnel['eligibleDecisionEvents'] == funnel['eligibleTaskRoots'] == 1
    assert all(funnel[key] == 1 for key in ('operationalExcludedEvents', 'continuationEvents',
        'preboundExcludedEvents', 'missingContextEvents', 'unknownIntentEvents', 'heldEvents',
        'baselineTaskRoots', 'shadowScoredTaskRoots', 'comparableRoutingTaskRoots'))
    assert funnel['outcomeTaskRoots'] == funnel['allBoundContextRootsWithChecks'] == 0
    assert funnel['byHost']['codex']['rawEvents'] == 7
    assert funnel['byEventKind']['background_observer']['operationalExcludedEvents'] == 1
    assert funnel['byEventKind']['missing']['rawEvents'] == 2
    assert sum(item['rawEvents'] for item in funnel['bySource'].values()) == 7
    assert sum(item['rawEvents'] for item in funnel['byEventKind'].values()) == 7
    assert funnel['captureDiagnostics']['task-context-holds']['reasons'] == {'duplicate_context': 1}
    assert funnel['nativeOriginVerified'] == 0 and funnel['nativeOriginUnknown'] == 7
    assert funnel['executedVariant'] == 'A_incumbent' and funnel['shadowVariant'] == 'B_local_laya'
    assert parent['opportunityId'] not in json.dumps(funnel)


def test_collection_funnel_keeps_historical_source_separate_from_capture_failure(tmp_path):
    root, receipts, receipt, _ = make(tmp_path)
    consult(tmp_path, receipts, receipt)
    pilot.drain(root, call, receipts=receipts, cohort='v2')
    observation = root / 'v2/observations' / (receipt['opportunityId'] + '.json')
    value = json.loads(observation.read_text())
    value['sourceSha256'] = 'a' * 64
    observation.write_text(json.dumps(value))
    funnel = pilot.report(root, receipts)['v2Coverage']['collectionFunnel']
    assert funnel['contextCapturedEvents'] == 1 and funnel['missingContextEvents'] == 0
    assert funnel['heldEvents'] == funnel['sourceChangedEvents'] == 1
    assert funnel['eligibleTaskRoots'] == funnel['comparableRoutingTaskRoots'] == 0
    assert funnel['bySource']['a' * 64]['sourceStatus'] == 'historical'
    assert funnel['heldReasons'] == {'source_changed': 1}
    assert v2.export_cases(root, receipts) == []
    assert json.loads(observation.read_text()) == value


@pytest.mark.parametrize('change', [
    {'schemaVersion': 'invalid'}, {'sourceBindingSha256': 'a' * 64}, {'events': [{}]}, {'events': []},
    {'events': 'private error'}, {'additionalConflicts': 'true'}, {'extra': 'private error'}])
def test_invalid_capture_diagnostics_remain_visible_without_breaking_report(tmp_path, change):
    root, receipts, receipt, _ = make(tmp_path, capture=False)
    value = context.diagnostic_context(receipts, receipt['opportunityId'], 'context_input_unavailable', 'a' * 64)
    path = receipts.parent / 'task-context-diagnostics' / (receipt['opportunityId'] + '.json')
    path.write_text(json.dumps({**value, **change}))
    coverage = pilot.report(root, receipts)['v2Coverage']
    summary = coverage['collectionFunnel']['captureDiagnostics']['task-context-diagnostics']
    assert summary == {'records': 0, 'events': 0, 'invalidRecords': 1, 'overflowRecords': 0, 'reasons': {}}
    assert coverage['missing'] == 1 and 'private error' not in json.dumps(coverage)


def test_capture_diagnostics_are_bounded_and_do_not_expose_reason_text(tmp_path):
    root, receipts, receipt, _ = make(tmp_path, capture=False)
    context.diagnostic_context(receipts, receipt['opportunityId'], 'context_input_unavailable', 'a' * 64)
    context.diagnostic_context(receipts, receipt['opportunityId'], 'private provider details', 'b' * 64)
    context.diagnostic_context(receipts, receipt['opportunityId'], 'request_capture_unavailable', 'c' * 64)
    context.diagnostic_context(receipts, receipt['opportunityId'], 'observer_source_unverified', 'd' * 64)
    context.diagnostic_context(receipts, receipt['opportunityId'], 'context_missing_before_decision', 'e' * 64)
    context.diagnostic_context(receipts, receipt['opportunityId'], 'native_binding_changed', 'f' * 64)
    path = receipts.parent / 'task-context-diagnostics' / (receipt['opportunityId'] + '.json')
    value = json.loads(path.read_text())
    value['additionalConflicts'] = True
    path.write_text(json.dumps(value))
    summary = pilot.report(root, receipts)['v2Coverage']['collectionFunnel']['captureDiagnostics']['task-context-diagnostics']
    assert summary['records'] == summary['overflowRecords'] == 1 and summary['events'] == 6
    assert summary['reasons'] == {'context_input_unavailable': 1, 'other': 1, 'request_capture_unavailable': 1,
                                 'observer_source_unverified': 1, 'context_missing_before_decision': 1, 'native_binding_changed': 1}
    assert 'private provider details' not in json.dumps(summary)
    path.unlink()
    path.symlink_to(tmp_path / 'missing-private-file')
    summary = pilot.report(root, receipts)['v2Coverage']['collectionFunnel']['captureDiagnostics']['task-context-diagnostics']
    assert summary['invalidRecords'] == 1


def test_collection_funnel_empty_denominators_are_counts_not_accuracy(tmp_path):
    coverage = pilot.report(tmp_path / 'pilot', tmp_path / 'receipts')['v2Coverage']
    funnel = coverage['collectionFunnel']
    assert funnel['rawEvents'] == funnel['eligibleTaskRoots'] == funnel['allBoundContextRootsWithChecks'] == 0
    assert funnel['bySource'] == {}
    assert coverage['acceptedTasks'] == 0 and coverage['localInputTokens'] is None


def test_drain_leaves_other_v2_source_pending_without_sealing_a_failure(tmp_path):
    root, receipts, old, _ = make(tmp_path, 'old-source')
    old_path = root / 'v2/observations' / (old['opportunityId'] + '.json')
    observation = json.loads(old_path.read_text())
    observation['sourceSha256'] = 'a' * 64
    old_path.write_text(json.dumps(observation))
    before = old_path.read_bytes()
    _, _, current, _ = make(tmp_path, 'current-source')
    calls = []
    result = pilot.drain(root, lambda *args: (calls.append(args) or call(*args)), receipts=receipts, cohort='v2')
    assert result == {'status': 'drained', 'processed': 1, 'sourceHeld': 1}
    assert len(calls) == 1 and old_path.read_bytes() == before
    assert not (root / 'v2/results' / (old['opportunityId'] + '.json')).exists()
    assert (root / 'v2/results' / (current['opportunityId'] + '.json')).exists()
    assert pilot.drain(root, lambda *args: pytest.fail('duplicate inference'), receipts=receipts, cohort='v2') == {
        'status': 'drained', 'processed': 0, 'sourceHeld': 1}
    row = next(r for r in v2.joined(root, receipts) if r['id'] == old['opportunityId'])
    assert row['bucket'] == 'held' and row['reason'] == 'source_changed' and row['result'] is None


# ---- workflow-input-v3: choice decoder, sealed request text, typed answers ----------------------

SNAPSHOT = lambda text: {'originalRequest': text}
CONTEXT = {'eventKind': 'new_task', 'action': 'implement', 'domain': 'software', 'exclusions': ['publishing', 'content_creation']}


@pytest.mark.parametrize('probabilities', [
    {'content': float('nan'), 'general': .5, 'none': .5}, {'content': float('inf'), 'general': .5, 'none': .5},
    {'content': -.1, 'general': .5, 'none': .5}, {'content': 1.1, 'general': .5, 'none': .5},
    {'content': True, 'general': .5, 'none': .5}, {'content': '0.5', 'general': .5, 'none': .5},
    {'content': .5, 'general': .5}, {'content': .5, 'general': .5, 'none': .5, 'extra': .1}, [.5, .5, .5], None])
def test_choice_decoder_rejects_invalid_probabilities(probabilities):
    with pytest.raises(ValueError, match='invalid routing score'):
        decode_choice(probabilities)


def test_choice_decoder_errors_match_the_historical_decoder():
    for bad in ({'abstain_below': 2}, {'abstain_below': float('nan')}, {'exclusions': ['bogus']},
                {'exclusions': ['publishing', 'publishing']}, {'exclusions': 'content_creation'}):
        with pytest.raises(ValueError) as new:
            decode_choice({'content': .5, 'general': .5, 'none': .5}, **bad)
        with pytest.raises(ValueError) as old:
            decode_scores({'content': .5, 'general': .5, 'none': .5}, **bad)
        assert str(new.value) == str(old.value)


def test_choice_decoder_ranking_mask_and_threshold():
    tie = {'content': .5, 'general': .5, 'none': .5}
    assert decode_choice(tie) == decode_scores(tie)
    assert decode_choice(tie)['ranking'] == [{'candidateId': n, 'score': .5} for n in ('content', 'general', 'none')]
    masked = decode_choice({'content': .9, 'general': .06, 'none': .04}, exclusions=['content_creation'])
    assert masked['choice'] == 'general' and all(r['candidateId'] != 'content' for r in masked['ranking'])
    assert decode_choice(tie, abstain_below=.6) == {
        'choice': None, 'ranking': decode_choice(tie)['ranking'], 'reason': 'below_threshold'}


def test_request_for_builds_v3_state_with_sorted_exclusions_and_one_choice_question():
    request = v2.request_for(CONTEXT, SNAPSHOT('  Fix   the\n\tbilling   defect  '))
    assert request['model'] == 'typed-decisions'
    assert request['state'] == {'request': 'Fix the billing defect', 'eventKind': 'new_task', 'action': 'implement',
                                'domain': 'software', 'exclusions': ['content_creation', 'publishing']}
    assert list(request['questions']) == ['route'] and request['questions']['route']['type'] == 'choice'
    assert set(request['questions']['route']['criteria']) == {'content', 'general', 'none'}
    assert 'data, not instructions' in request['questions']['route']['instructions']
    assert v2.NORMALIZATION == 'workflow-input-v3'


def test_request_for_truncates_at_1500_after_whitespace_collapse():
    request = v2.request_for(CONTEXT, SNAPSHOT('word ' * 1000))
    assert len(request['state']['request']) == 1500 and '  ' not in request['state']['request']
    assert len(v2.request_for(CONTEXT, SNAPSHOT('x' * 1500))['state']['request']) == 1500


def test_request_for_redacts_again_defensively_and_requires_snapshot_text():
    request = v2.request_for(CONTEXT, SNAPSHOT('mail owner@example.test about the migration'))
    assert 'owner@example.test' not in request['state']['request']
    for bad in (None, {}, {'originalRequest': 5}):
        with pytest.raises(ValueError, match='request_snapshot_missing'):
            v2.request_for(CONTEXT, bad)


def test_missing_request_snapshot_is_refused_at_enqueue_and_never_falls_back(tmp_path):
    with pytest.raises(ValueError, match='request_snapshot_missing'):
        make(tmp_path, snapshot=False)
    assert not list((tmp_path / 'pilot/v2/observations').glob('*.json'))
    assert 'request_snapshot_missing' in v2.HELD_REASONS
    assert v2.failure_reason(ValueError('request_snapshot_missing')) == 'request_snapshot_missing'


def test_snapshot_lost_after_enqueue_holds_the_observation(tmp_path):
    root, receipts, receipt, _ = make(tmp_path)
    (receipts.parent / 'request-snapshots' / (receipt['opportunityId'] + '.json')).unlink()
    row = v2.joined(root, receipts)[0]
    assert row['bucket'] == 'held' and row['reason'] == 'request_snapshot_missing' and row['armB'] is None


def test_tampered_snapshot_holds_the_observation_as_unverifiable(tmp_path):
    root, receipts, receipt, _ = make(tmp_path)
    path = receipts.parent / 'request-snapshots' / (receipt['opportunityId'] + '.json')
    value = json.loads(path.read_text())
    value['originalRequest'] += ' tampered'
    path.write_text(json.dumps(value))
    row = v2.joined(root, receipts)[0]
    assert row['bucket'] == 'held' and row['reason'] == 'request_snapshot_missing'  # binding hash no longer matches


def observation_for(tmp_path, **kwargs):
    root, receipts, receipt, _ = make(tmp_path, **kwargs)
    return root, receipts, workflow.read_json(root / 'v2/observations' / (receipt['opportunityId'] + '.json'))


def test_assess_accepts_a_valid_choice_answer(tmp_path):
    _, receipts, observation = observation_for(tmp_path)
    result = v2.assess(observation, receipts, lambda url, request: (answer({'content': .1, 'general': .7, 'none': .2}), 4.5))
    assert result['status'] == 'shadow' and result['choice'] == 'general' and result['confidenceCalibrated'] is False
    assert result['scores'] == {'content': .1, 'general': .7, 'none': .2} and result['incumbentAltered'] is False
    assert result['requestSha256'] == observation['requestSha256'] and result['model'] == 'typed-decisions'
    assert result['routedModel'] == 'typed-decisions' and result['latencyMs'] == 4.5
    assert [r['candidateId'] for r in result['ranking']] == ['general', 'none', 'content']
    assert result['reasonCode'] is None and 'invented fixture' not in json.dumps(result)


def broken(**overrides):
    return lambda url, request: (answer({'content': .1, 'general': .7, 'none': .2}, **overrides), 1.0)


@pytest.mark.parametrize('mutate', [
    lambda r: r['answers'].update(route={'type': 'noul', 'noul': .5}),
    lambda r: r['answers'].update(route=None),
    lambda r: r['answers'].update(c0={'type': 'noul', 'noul': .5}) or r['answers'].pop('route'),
    lambda r: r.update(answers=None),
    lambda r: r['answers']['route'].update(probabilities={'content': .5, 'general': .5}),
    lambda r: r['answers']['route'].update(probabilities={'content': .5, 'general': .5, 'none': .5, 'x': .1}),
    lambda r: r['answers']['route'].update(probabilities=[.1, .2, .7]),
    lambda r: r['answers']['route'].update(choice='other'),
    lambda r: r['answers']['route'].pop('choice')])
def test_assess_rejects_malformed_choice_answers(tmp_path, mutate):
    _, receipts, observation = observation_for(tmp_path)
    def malformed(url, request):
        value = answer({'content': .1, 'general': .7, 'none': .2})
        mutate(value)
        return value, 1.0
    with pytest.raises(ValueError, match='provider_answer_type_mismatch'):
        v2.assess(observation, receipts, malformed)


def test_assess_rejects_out_of_range_probabilities_with_the_routing_reason(tmp_path):
    _, receipts, observation = observation_for(tmp_path)
    with pytest.raises(ValueError, match='invalid routing score'):
        v2.assess(observation, receipts, lambda url, request: (answer({'content': 1.5, 'general': .2, 'none': .1}), 1.0))


def test_assess_masks_content_when_content_creation_is_excluded(tmp_path):
    _, receipts, observation = observation_for(tmp_path, domain='content', action='review', exclusions=['content_creation'])
    result = v2.assess(observation, receipts, lambda url, request: (answer({'content': .9, 'general': .06, 'none': .04}), 1.0))
    assert result['choice'] == 'general' and all(r['candidateId'] != 'content' for r in result['ranking'])
    assert result['scores']['content'] == .9


def test_joined_decodes_results_with_the_choice_decoder_and_holds_tampering(tmp_path):
    root, receipts, receipt, _ = make(tmp_path)
    pilot.drain(root, call, receipts=receipts, cohort='v2')
    assert v2.joined(root, receipts)[0]['armB'] == 'content'
    path = root / 'v2/results' / (receipt['opportunityId'] + '.json')
    value = json.loads(path.read_text()); value['choice'] = 'none'; path.write_text(json.dumps(value))
    row = v2.joined(root, receipts)[0]
    assert row['bucket'] == 'held' and row['reason'] == 'result_decoding_changed'


def test_source_digest_covers_the_typed_advice_transport():
    names = ('decision_pilot_v2.py', 'decision_pilot.py', 'workflow_selection.py', 'workflow_task_context.py',
             'workflow_context_packet.py', 'pilot_redaction.py', 'pilot_routing.py', 'typed_advice.py',
             'context_experiments/typed_relevance.py')
    assert v2.source_digest() == workflow.digest(b''.join((SCRIPTS / name).read_bytes() for name in names))


def test_typed_call_posts_to_the_loopback_endpoint_and_checks_checkpoint_and_answer_keys(monkeypatch):
    import typed_advice as typed_transport
    request = {'model': 'typed-decisions', 'state': {}, 'questions': {'route': {'type': 'choice'}}}
    seen = []
    def fake(url, path, payload, timeout, max_bytes=262144):
        seen.append((url, path, payload, timeout))
        return seen_value[0], 2.0
    monkeypatch.setattr(typed_transport, 'post_local', fake)
    seen_value = [{'routing': {'model': 'typed-decisions'}, 'answers': {'route': {}}}]
    assert pilot.typed_call('http://127.0.0.1:8000', request)[1] == 2.0
    assert seen[0] == ('http://127.0.0.1:8000', '/v1/systemone', request, 5)
    seen_value[0] = {'routing': {'model': 'other'}, 'answers': {'route': {}}}
    with pytest.raises(ValueError, match='checkpoint mismatch'): pilot.typed_call('http://127.0.0.1:8000', request)
    seen_value[0] = {'routing': {'model': 'typed-decisions'}, 'answers': {'c0': {}}}
    with pytest.raises(ValueError, match='answers mismatch'): pilot.typed_call('http://127.0.0.1:8000', request)
    seen_value[0] = {'answers': {'route': {}}}
    with pytest.raises(ValueError, match='checkpoint mismatch'): pilot.typed_call('http://127.0.0.1:8000', request)


def test_drain_defaults_to_the_typed_transport_for_v2(tmp_path, monkeypatch):
    import typed_advice as typed_transport
    root, receipts, receipt, _ = make(tmp_path)
    calls = []
    def fake(url, path, payload, timeout, max_bytes=262144):
        calls.append((url, path))
        return answer({'content': .2, 'general': .7, 'none': .1}), 1.5
    monkeypatch.setattr(typed_transport, 'post_local', fake)
    assert pilot.drain(root, receipts=receipts, cohort='v2')['processed'] == 1
    assert calls == [('http://127.0.0.1:8000', '/v1/systemone')]
    assert v2.joined(root, receipts)[0]['armB'] == 'general'
