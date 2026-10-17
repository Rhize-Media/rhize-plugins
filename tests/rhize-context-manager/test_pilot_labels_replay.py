"""v3 replay corpus: accepted explicit taxonomy labels rebuilt through the current request envelope."""
import importlib.util
import json
from pathlib import Path
import sys

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / 'rhize-context-manager/scripts'
sys.path.insert(0, str(SCRIPTS))
import decision_pilot as pilot
import decision_pilot_v2 as v2
import pilot_labels as labels
import workflow_context_packet as packets
import workflow_selection as workflow
import workflow_task_context as context

spec = importlib.util.spec_from_file_location('typed_research', REPO / 'evals/typed-decision/research.py')
research = importlib.util.module_from_spec(spec); spec.loader.exec_module(research)
POLICY = {'schema': labels.POLICY_SCHEMA, 'acceptedBases': [labels.HUMAN, labels.AI]}


def make(tmp_path, turn='task', *, kind='new_task', action='implement', domain='software', exclusions=None):
    receipts, root = tmp_path / 'receipts', tmp_path / 'pilot'
    payload = {'prompt': 'invented fixture ' + turn, 'session_id': 'session-' + turn, 'turn_id': turn}
    receipt, _ = workflow.opportunity(payload, 'codex', receipts,
        {'decisionPilot': {'enabled': True, 'mode': 'shadow', 'cohort': 'v2'}})
    packets.capture_request_snapshot(receipts, receipt, payload)
    evidence = {'schemaVersion': context.SCHEMA, 'opportunityId': receipt['opportunityId'],
                'promptHash': receipt['promptHash'], 'sessionHash': receipt['sessionHash'],
                'eventKind': kind, 'action': action, 'domain': domain, 'exclusions': exclusions or [],
                'parentOpportunityId': None, 'preboundFamily': None}
    context.capture_context(receipts, receipt['opportunityId'], evidence,
        seal=lambda c, r: pilot.enqueue_v2(c, r, root, spawn=False, receipts=receipts))
    return root, receipts, receipt


def label(root, receipt, **overrides):
    source = workflow.read_json(root / 'v2/observations' / (receipt['opportunityId'] + '.json'))['sourceSha256']
    base = {'schema': labels.LABEL_SCHEMA, 'opportunityId': receipt['opportunityId'], 'sourceSha256': source,
            'taxonomyVersion': labels.TAXONOMY_VERSION, 'basis': labels.AI, 'family': 'feature_delivery',
            'phase': 'implement', 'areas': ['backend_api'], 'stratum': 'routine', 'riskFlags': [],
            'choice': 'general', 'choiceBasis': 'explicit', 'reviewer': 'ai-review-fixture',
            'reviewEvidenceSha256': 'c' * 64}
    return {**base, **overrides}


def stored(root, receipt):
    return root / labels.LABEL_DIR / (receipt['opportunityId'] + '.json')


def test_replay_builds_a_research_valid_v3_case_from_the_sealed_snapshot(tmp_path):
    root, receipts, receipt = make(tmp_path)
    labels.record_label(root, receipts, label(root, receipt, stratum='elevated', riskFlags=['data_integrity']), 'd' * 64)
    result = labels.replay_cases(receipts, root, POLICY)
    assert len(result['cases']) == 1
    case = result['cases'][0]
    assert case['case_id'] == receipt['opportunityId'] and case['replayed'] is True
    assert case['cohort_version'] == 'workflow-pilot-v3' and case['normalization_version'] == 'workflow-input-v3'
    assert case['decision_type'] == 'workflow_fit' and case['stratum'] == 'ordinary' and case['taxonomy_stratum'] == 'elevated'
    assert case['risk_flags'] == ['data_integrity'] and case['labels'] == {'route': 'general'}
    assert case['routing_choice'] == 'general' and case['candidate_ids'] == ['content', 'general', 'none']
    assert set(case['questions']) == {'route'} and case['questions']['route']['type'] == 'choice'
    assert 'invented fixture task' in case['state']['request']
    assert case['collection_source_sha256'] == label(root, receipt)['sourceSha256']
    assert case['label_source'] == 'c' * 64 and case['adjudicated'] is True
    assert {k.split(':')[0] for k in case['grouping_keys']} == {'session', 'task', 'input', 'prompt'}
    path = tmp_path / 'cases.jsonl'
    path.write_text(json.dumps(case) + '\n')
    assert research.read_jsonl(path)[0]['case_id'] == case['case_id']
    provenance = result['provenance']
    assert provenance['labels'] == 1 and provenance['cases'] == 1 and provenance['skipped'] == {}
    assert provenance['replayed'] is True and provenance['pooledAcrossSources'] is False


def test_critical_stratum_maps_to_critical_safety_and_routine_to_ordinary(tmp_path):
    root, receipts, critical = make(tmp_path, 'critical')
    _, _, routine = make(tmp_path, 'routine')
    labels.record_label(root, receipts, label(root, critical, stratum='critical', riskFlags=['security_privacy']), 'd' * 64)
    labels.record_label(root, receipts, label(root, routine), 'd' * 64)
    cases = {c['case_id']: c for c in labels.replay_cases(receipts, root, POLICY)['cases']}
    assert cases[critical['opportunityId']]['stratum'] == 'critical_safety'
    assert cases[routine['opportunityId']]['stratum'] == 'ordinary'


def test_unusable_labels_are_skipped_and_counted_by_reason(tmp_path):
    root, receipts, good = make(tmp_path, 'good')
    _, _, derived = make(tmp_path, 'derived')
    _, _, no_snapshot = make(tmp_path, 'nosnapshot')
    _, _, broken = make(tmp_path, 'broken')
    _, _, masked = make(tmp_path, 'masked', domain='content', action='review', exclusions=['content_creation'])
    _, _, human_only = make(tmp_path, 'humanonly')
    for item, extra in ((good, {}), (derived, {'choiceBasis': labels.FAMILY_MAP}), (no_snapshot, {}), (broken, {}),
                        (masked, {'choice': 'general'}), (human_only, {})):
        labels.record_label(root, receipts, label(root, item, **extra), 'd' * 64)
    # A choice that contradicts the mask can only arrive through a tampered store; replay still refuses it.
    record = json.loads(stored(root, masked).read_text())
    stored(root, masked).write_text(json.dumps({**record, 'choice': 'content'}))
    (receipts.parent / 'request-snapshots' / (no_snapshot['opportunityId'] + '.json')).unlink()
    (receipts.parent / 'request-snapshots' / (broken['opportunityId'] + '.json')).write_text('{"not": "a snapshot"}')
    result = labels.replay_cases(receipts, root, POLICY)
    assert {c['case_id'] for c in result['cases']} == {good['opportunityId'], human_only['opportunityId']}
    assert result['provenance']['skipped'] == {
        'choice_not_explicit': 1, 'snapshot_missing': 1, 'context_or_snapshot_invalid': 1,
        'label_contradicts_exclusions': 1}
    # Policy decides which bases count: with human-only acceptance every AI label is skipped.
    strict = labels.replay_cases(receipts, root, {'schema': labels.POLICY_SCHEMA, 'acceptedBases': [labels.HUMAN]})
    assert strict['cases'] == [] and strict['provenance']['skipped'] == {'basis_not_accepted': 6}


def test_missing_context_is_counted(tmp_path):
    root, receipts, item = make(tmp_path)
    labels.record_label(root, receipts, label(root, item), 'd' * 64)
    (receipts.parent / 'task-context' / (item['opportunityId'] + '.json')).unlink()
    result = labels.replay_cases(receipts, root, POLICY)
    assert result['cases'] == [] and result['provenance']['skipped'] == {'context_missing': 1}


def test_superseded_labels_replay_only_their_replacement(tmp_path):
    root, receipts, item = make(tmp_path)
    labels.record_label(root, receipts, label(root, item, choiceBasis=labels.FAMILY_MAP), 'd' * 64)
    assert labels.replay_cases(receipts, root, POLICY)['cases'] == []
    labels.record_label(root, receipts, label(root, item, reviewEvidenceSha256='e' * 64), 'e' * 64, supersede=True)
    result = labels.replay_cases(receipts, root, POLICY)
    assert [c['label_source'] for c in result['cases']] == ['e' * 64]
    assert result['provenance']['supersededArchived'] == 1


def test_pooling_across_collection_sources_is_recorded(tmp_path):
    root, receipts, first = make(tmp_path, 'first')
    _, _, second = make(tmp_path, 'second')
    labels.record_label(root, receipts, label(root, first), 'd' * 64)
    labels.record_label(root, receipts, label(root, second), 'd' * 64)
    record = json.loads(stored(root, second).read_text())
    stored(root, second).write_text(json.dumps({**record, 'sourceSha256': 'f' * 64}))   # collected under an older source
    result = labels.replay_cases(receipts, root, POLICY)
    provenance = result['provenance']
    assert provenance['pooledAcrossSources'] is True and len(provenance['collectionSources']) == 2
    assert {c['normalization_version'] for c in result['cases']} == {'workflow-input-v3'}
    assert 'envelope' in provenance['poolingBasis']
