"""Invented fixtures for versioned taxonomy labels; no production prompts or real labels."""
import json
from pathlib import Path
import sys

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / 'rhize-context-manager/scripts'
sys.path.insert(0, str(SCRIPTS))
import decision_pilot as pilot
import decision_pilot_v2 as v2
import pilot_labels as labels
import workflow_selection as workflow
import workflow_task_context as context

DIGEST_FILES = ('decision_pilot_v2.py', 'decision_pilot.py', 'workflow_selection.py', 'workflow_task_context.py',
                'pilot_routing.py', 'context_experiments/typed_relevance.py')


def make(tmp_path, turn='task', *, kind='new_task', action='implement', domain='software', exclusions=None):
    receipts, root = tmp_path / 'receipts', tmp_path / 'pilot'
    receipt, _ = workflow.opportunity({'prompt': 'invented fixture ' + turn, 'session_id': 'session', 'turn_id': turn},
        'codex', receipts, {'decisionPilot': {'enabled': True, 'mode': 'shadow', 'cohort': 'v2'}})
    evidence = {'schemaVersion': context.SCHEMA, 'opportunityId': receipt['opportunityId'],
                'promptHash': receipt['promptHash'], 'sessionHash': receipt['sessionHash'],
                'eventKind': kind, 'action': action, 'domain': domain, 'exclusions': exclusions or [],
                'parentOpportunityId': None, 'preboundFamily': None}
    context.capture_context(receipts, receipt['opportunityId'], evidence,
        seal=lambda c, r: pilot.enqueue_v2(c, r, root, spawn=False, receipts=receipts))
    return root, receipts, receipt


def source(root, receipt):
    return workflow.read_json(root / 'v2/observations' / (receipt['opportunityId'] + '.json'))['sourceSha256']


def value(root, receipt, **overrides):
    base = {'schema': labels.LABEL_SCHEMA, 'opportunityId': receipt['opportunityId'],
            'sourceSha256': source(root, receipt), 'taxonomyVersion': labels.TAXONOMY_VERSION,
            'basis': labels.AI, 'family': 'feature_delivery', 'phase': 'implement', 'areas': ['backend_api'],
            'stratum': 'routine', 'riskFlags': [], 'choice': 'general', 'choiceBasis': 'explicit',
            'reviewer': 'ai-review-fixture', 'reviewEvidenceSha256': 'c' * 64}
    return {**base, **overrides}


def write(tmp_path, data, name='label.json'):
    path = tmp_path / name
    path.write_text(json.dumps(data))
    return path


def annotation(root, receipt, **overrides):
    base = {'schema': labels.BATCH_SCHEMA, 'status': 'labeled', 'opportunityId': receipt['opportunityId'],
            'sourceSha256': source(root, receipt), 'taxonomyVersion': 'rhize-workflow-taxonomy-proposal-2026-09-28-v1',
            'basis': 'ai_generated_model_reviewed', 'humanAdjudicated': False, 'family': 'direct_response',
            'phase': 'not_applicable', 'areas': ['not_applicable'], 'stratum': 'routine', 'riskFlags': [],
            'review': {'verdict': 'accept', 'actuallyRan': True, 'observedModel': 'claude-fable-5-1'}}
    return {**base, **overrides}


def test_module_stays_outside_collection_source_digest():
    before = v2.source_digest()
    joined = b''.join((SCRIPTS / name).read_bytes() for name in DIGEST_FILES)
    assert before == workflow.digest(joined)
    assert b'pilot_labels' not in joined


def test_ai_label_import_is_bound_immutable_and_idempotent(tmp_path):
    root, receipts, receipt = make(tmp_path)
    path = write(tmp_path, value(root, receipt))
    assert labels.import_file(root, receipts, receipt['opportunityId'], path)['status'] == 'recorded'
    assert labels.import_file(root, receipts, receipt['opportunityId'], path)['status'] == 'already_recorded'
    stored = labels.load_labels(root)[0]
    assert stored['basis'] == labels.AI and stored['evidenceSha256'] == workflow.digest(path.read_bytes())
    changed = write(tmp_path, value(root, receipt, family='code_health'), 'changed.json')
    with pytest.raises(ValueError, match='immutable'):
        labels.import_file(root, receipts, receipt['opportunityId'], changed)
    # The legacy human store and its contract are untouched.
    assert not (root / 'v2/labels').exists()
    assert v2.joined(root, receipts)[0]['label'] is None


@pytest.mark.parametrize('overrides, message', [
    ({'basis': 'human_approved'}, 'basis'),
    ({'family': 'backend_feature'}, 'family'),
    ({'family': 'direct_response', 'phase': 'implement'}, 'direct_response'),
    ({'areas': []}, 'areas'),
    ({'areas': ['backend_api', 'not_applicable']}, 'areas'),
    ({'riskFlags': ['financial', 'financial']}, 'risk flags'),
    ({'choiceBasis': labels.FAMILY_MAP, 'choice': 'none'}, 'family map'),
    ({'taxonomyVersion': 'other'}, 'version'),
    ({'reviewer': 'has space'}, 'reviewer'),
])
def test_label_contract_rejects_invalid_values(tmp_path, overrides, message):
    root, receipts, receipt = make(tmp_path)
    with pytest.raises(ValueError, match=message):
        labels.record_label(root, receipts, value(root, receipt, **overrides), 'd' * 64)
    assert not (root / labels.LABEL_DIR).exists()


def test_binding_refuses_ineligible_stale_and_contradicting_labels(tmp_path):
    root, receipts, receipt = make(tmp_path)
    _, _, status = make(tmp_path, 'status', kind='status')
    with pytest.raises(ValueError, match='only eligible'):
        labels.record_label(root, receipts, value(root, status), 'd' * 64)
    _, _, masked = make(tmp_path, 'masked', domain='content', action='review', exclusions=['content_creation'])
    with pytest.raises(ValueError, match='label_contradicts_exclusions'):
        labels.record_label(root, receipts, value(root, masked, family='content_growth', choice='content'), 'd' * 64)
    stale = value(root, receipt, sourceSha256='a' * 64)
    with pytest.raises(ValueError, match='exact collection source'):
        labels.record_label(root, receipts, stale, 'd' * 64)
    path = root / 'v2/observations' / (receipt['opportunityId'] + '.json')
    observation = json.loads(path.read_text()); observation['sourceSha256'] = 'a' * 64
    path.write_text(json.dumps(observation))
    with pytest.raises(ValueError, match='source_changed'):
        labels.record_label(root, receipts, value(root, receipt), 'd' * 64)
    assert not (root / labels.LABEL_DIR).exists()


def test_batch_imports_only_reviewed_labeled_bound_records(tmp_path):
    root, receipts, first = make(tmp_path, 'first')
    _, _, second = make(tmp_path, 'second')
    _, _, status = make(tmp_path, 'status', kind='status')
    batch = [annotation(root, first),
             annotation(root, second, review={'verdict': 'unresolved', 'actuallyRan': True}),
             annotation(root, status),
             annotation(root, second, status='needs_split'),
             annotation(root, second, humanAdjudicated=True),
             {**annotation(root, second), 'opportunityId': 'f' * 64}]
    path = write(tmp_path, batch, 'annotations.json')
    dry = labels.import_batch(root, receipts, path, dry_run=True)
    assert dry['results'] == {'would_record': 1} and not (root / labels.LABEL_DIR).exists()
    result = labels.import_batch(root, receipts, path)
    assert result['results'] == {'recorded': 1}
    assert result['skipped'] == {'basis_mismatch': 1, 'no_v2_observation': 1, 'not_model_reviewed': 1,
                                 'only eligible routing decisions can receive labels': 1, 'status_needs_split': 1}
    stored = labels.load_labels(root)[0]
    assert stored['choice'] == 'none' and stored['choiceBasis'] == labels.FAMILY_MAP
    assert stored['reviewer'] == 'ai-review-claude-fable-5-1' and stored['basis'] == labels.AI
    assert labels.import_batch(root, receipts, path)['results'] == {'already_recorded': 1}


def test_batch_explicit_choice_is_research_usable(tmp_path):
    root, receipts, receipt = make(tmp_path)
    path = write(tmp_path, [annotation(root, receipt, family='feature_delivery', phase='implement',
                                       areas=['backend_api'], choice='none')], 'annotations.json')
    labels.import_batch(root, receipts, path)
    stored = labels.load_labels(root)[0]
    assert stored['choice'] == 'none' and stored['choiceBasis'] == 'explicit'


def test_policy_defaults_human_only_and_records_history(tmp_path):
    root = tmp_path / 'pilot'
    assert labels.load_policy(root)['acceptedBases'] == [labels.HUMAN]
    with pytest.raises(ValueError, match='reason'):
        labels.set_policy(root, True, ' ', 'jim')
    accepted = labels.set_policy(root, True, 'use AI labels until further notice', 'jim')
    assert labels.load_policy(root)['acceptedBases'] == [labels.HUMAN, labels.AI] == accepted['acceptedBases']
    labels.set_policy(root, False, 'revoked', 'jim')
    assert labels.load_policy(root)['acceptedBases'] == [labels.HUMAN]
    history = [json.loads(line) for line in (root / labels.POLICY_HISTORY).read_text().splitlines()]
    assert [entry['next']['acceptedBases'] for entry in history] == [[labels.HUMAN, labels.AI], [labels.HUMAN]]
    assert (root / labels.POLICY_FILE).stat().st_mode & 0o777 == 0o600
    (root / labels.POLICY_FILE).write_text(json.dumps({'schema': labels.POLICY_SCHEMA, 'acceptedBases': [labels.AI]}))
    with pytest.raises(ValueError, match='invalid label policy'):
        labels.load_policy(root)


def test_export_respects_basis_and_choice_basis(tmp_path):
    root, receipts, explicit = make(tmp_path, 'explicit')
    _, _, derived = make(tmp_path, 'derived')
    labels.record_label(root, receipts, value(root, explicit, stratum='elevated', riskFlags=['data_integrity']), 'd' * 64)
    labels.record_label(root, receipts, value(root, derived, choiceBasis=labels.FAMILY_MAP), 'd' * 64)
    assert labels.export_cases(root, receipts, [labels.HUMAN]) == []
    cases = labels.export_cases(root, receipts, [labels.HUMAN, labels.AI])
    assert [case['case_id'] for case in cases] == [explicit['opportunityId']]
    case = cases[0]
    assert case['label_basis'] == labels.AI and case['stratum'] == 'elevated' and case['risk_flags'] == ['data_integrity']
    assert case['routing_choice'] == 'general' and case['labels'] == {'c0': False, 'c1': True, 'c2': False}
    assert set(case) >= {'grouping_keys', 'collection_source_sha256', 'task_family', 'host', 'family', 'phase'}
    both = labels.export_cases(root, receipts, [labels.HUMAN, labels.AI], choice_bases=('explicit', labels.FAMILY_MAP))
    assert len(both) == 2
    out = tmp_path / 'cases.jsonl'
    written = labels.write_cases(root, receipts, out, [labels.HUMAN, labels.AI])
    assert written['count'] == 1 and written['labelBasis'] == {labels.AI: 1}


def test_coverage_gates_name_sparse_slices():
    rows = [{'family': 'feature_delivery', 'routing_choice': 'general', 'stratum': 'routine'}] * 200
    coverage = labels.taxonomy_coverage(rows)
    assert set(coverage['holdReasons']) == {'insufficient_routing_class_coverage', 'insufficient_family_coverage',
                                            'insufficient_risk_coverage'}
    assert coverage['sparseRoutingChoices'] == ['content', 'none'] and coverage['criticalClaimsSupported'] is False
    families = ('feature_delivery', 'defect_resolution', 'code_health', 'research_analysis')
    rows = ([{'family': f, 'routing_choice': 'general', 'stratum': 'elevated'} for f in families for _ in range(15)]
            + [{'family': 'content_growth', 'routing_choice': 'content', 'stratum': 'routine'}] * 15
            + [{'family': 'direct_response', 'routing_choice': 'none', 'stratum': 'routine'}] * 15)
    coverage = labels.taxonomy_coverage(rows)
    assert coverage['holdReasons'] == [] and len(coverage['evaluableFamilies']) == 6
    assert 'coordination' in coverage['sparseFamilies']


def test_report_separates_bases_and_research_usable(tmp_path):
    root, receipts, receipt = make(tmp_path)
    labels.record_label(root, receipts, value(root, receipt), 'd' * 64)
    human_only = labels.report(root)
    assert human_only['labels'] == 1 and human_only['accepted'] == 0 and human_only['byBasis'] == {labels.AI: 1}
    labels.set_policy(root, True, 'fixture', 'jim')
    accepted = labels.report(root)
    assert accepted['accepted'] == 1 and accepted['researchUsable'] == 1 and accepted['byChoice'] == {'general': 1}


def stored_ids(root):
    return {label['opportunityId']: label for label in labels.load_labels(root)}


def test_derived_ai_choice_is_superseded_by_explicit_and_old_record_is_preserved(tmp_path):
    root, receipts, receipt = make(tmp_path)
    identity = receipt['opportunityId']
    derived = value(root, receipt, choiceBasis=labels.FAMILY_MAP, reviewEvidenceSha256='1' * 64)
    assert labels.record_label(root, receipts, derived, 'a' * 64) == 'recorded'
    old = stored_ids(root)[identity]
    explicit = value(root, receipt, choice='none', reviewEvidenceSha256='2' * 64)
    # Without the opt-in the label stays immutable, exactly as before.
    with pytest.raises(ValueError, match='immutable'):
        labels.record_label(root, receipts, explicit, 'b' * 64)
    assert labels.record_label(root, receipts, explicit, 'b' * 64, dry_run=True, supersede=True) == 'would_supersede'
    assert stored_ids(root)[identity] == old and not (root / labels.SUPERSEDED_DIR).exists()
    assert labels.record_label(root, receipts, explicit, 'b' * 64, supersede=True) == 'superseded'
    current = stored_ids(root)[identity]
    assert current['choice'] == 'none' and current['choiceBasis'] == 'explicit' and current['evidenceSha256'] == 'b' * 64
    archived = list((root / labels.SUPERSEDED_DIR).glob('*.json'))
    assert [path.name for path in archived] == [identity + '-' + 'a' * 16 + '.json']
    kept = json.loads(archived[0].read_text())
    assert {k: v for k, v in kept.items() if not k.startswith('superseded')} == old
    assert kept['supersededReason'] == 'derived_to_explicit_choice'
    assert kept['supersededBy']['evidenceSha256'] == 'b' * 64 and kept['supersededBy']['choice'] == 'none'
    assert archived[0].stat().st_mode & 0o777 == 0o600
    # The replacement is itself idempotent, and the archive is invisible to every reader.
    assert labels.record_label(root, receipts, explicit, 'b' * 64, supersede=True) == 'already_recorded'
    assert len(list((root / labels.SUPERSEDED_DIR).glob('*.json'))) == 1
    assert [label['opportunityId'] for label in labels.load_labels(root)] == [identity]
    labels.set_policy(root, True, 'fixture', 'jim')
    report = labels.report(root)
    assert report['labels'] == 1 and report['superseded'] == 1 and report['byChoiceBasis'] == {'explicit': 1}
    assert report['researchUsable'] == 1
    assert not (root / 'v2/labels').exists()


def test_supersession_never_replaces_human_or_directly_judged_ai_labels(tmp_path):
    root, receipts, explicit_ai = make(tmp_path, 'explicit-ai')
    _, _, human = make(tmp_path, 'human')
    labels.record_label(root, receipts, value(root, explicit_ai, choice='general'), 'a' * 64)
    labels.record_label(root, receipts, value(root, human, basis=labels.HUMAN, reviewer='jim',
                                              choiceBasis=labels.FAMILY_MAP), 'a' * 64)
    before = stored_ids(root)
    attempts = [
        (explicit_ai, {'choice': 'none'}),                                      # AI-explicit -> other AI-explicit
        (explicit_ai, {'family': 'code_health'}),                               # same choice, other fields
        (human, {'choice': 'none'}),                                            # human -> explicit AI
        (human, {'basis': labels.HUMAN, 'reviewer': 'jim2', 'choice': 'content'}),  # human -> other human
    ]
    for receipt, overrides in attempts:
        candidate = value(root, receipt, reviewEvidenceSha256='9' * 64, **overrides)
        with pytest.raises(ValueError, match='immutable'):
            labels.record_label(root, receipts, candidate, 'c' * 64, supersede=True)
    assert stored_ids(root) == before and not (root / labels.SUPERSEDED_DIR).exists()


def test_ai_label_may_be_replaced_by_human_label_and_archived(tmp_path):
    root, receipts, receipt = make(tmp_path)
    identity = receipt['opportunityId']
    labels.record_label(root, receipts, value(root, receipt, choice='general'), 'a' * 64)
    human = value(root, receipt, basis=labels.HUMAN, reviewer='jim', choice='none', reviewEvidenceSha256='7' * 64)
    with pytest.raises(ValueError, match='immutable'):
        labels.record_label(root, receipts, human, 'd' * 64)
    assert labels.record_label(root, receipts, human, 'd' * 64, supersede=True) == 'superseded'
    assert stored_ids(root)[identity]['basis'] == labels.HUMAN
    kept = json.loads(next((root / labels.SUPERSEDED_DIR).glob('*.json')).read_text())
    assert kept['basis'] == labels.AI and kept['supersededReason'] == 'ai_to_human'
    # A human label can no longer be replaced, even by another human label.
    other = value(root, receipt, basis=labels.HUMAN, reviewer='jim', choice='content', reviewEvidenceSha256='8' * 64)
    with pytest.raises(ValueError, match='immutable'):
        labels.record_label(root, receipts, other, 'e' * 64, supersede=True)


def test_archive_step_is_repeatable_and_refuses_a_conflicting_archive(tmp_path):
    root, receipts, receipt = make(tmp_path)
    identity = receipt['opportunityId']
    labels.record_label(root, receipts, value(root, receipt, choiceBasis=labels.FAMILY_MAP), 'a' * 64)
    old = stored_ids(root)[identity]
    explicit = value(root, receipt, choice='none', reviewEvidenceSha256='2' * 64)
    # A crash after archiving but before replacing leaves a matching archive; the retry completes.
    path = root / labels.SUPERSEDED_DIR / (identity + '-' + 'a' * 16 + '.json')
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({**old, 'supersededBy': {}, 'supersededReason': 'earlier attempt'}))
    assert labels.record_label(root, receipts, explicit, 'b' * 64, supersede=True) == 'superseded'
    assert json.loads(path.read_text())['supersededReason'] == 'earlier attempt'
    # A different record occupying the archive name is a hard stop and leaves the label untouched.
    root2, receipts2, receipt2 = make(tmp_path / 'second')
    labels.record_label(root2, receipts2, value(root2, receipt2, choiceBasis=labels.FAMILY_MAP), 'a' * 64)
    bad = root2 / labels.SUPERSEDED_DIR / (receipt2['opportunityId'] + '-' + 'a' * 16 + '.json')
    bad.parent.mkdir(parents=True)
    bad.write_text(json.dumps({'unrelated': True}))
    before = stored_ids(root2)
    with pytest.raises(ValueError, match='superseded_archive_conflict'):
        labels.record_label(root2, receipts2, value(root2, receipt2, choice='none', reviewEvidenceSha256='2' * 64),
                            'b' * 64, supersede=True)
    assert stored_ids(root2) == before


def test_batch_supersede_is_opt_in_and_counts_replacements(tmp_path):
    root, receipts, receipt = make(tmp_path)
    labels.record_label(root, receipts, value(root, receipt, choiceBasis=labels.FAMILY_MAP), 'a' * 64)
    path = write(tmp_path, [annotation(root, receipt, family='feature_delivery', phase='implement',
                                       areas=['backend_api'], choice='none')], 'annotations.json')
    plain = labels.import_batch(root, receipts, path)
    assert plain['results'] == {} and plain['skipped'] == {'immutable label already exists': 1}
    dry = labels.import_batch(root, receipts, path, dry_run=True, supersede=True)
    assert dry['results'] == {'would_supersede': 1} and stored_ids(root)[receipt['opportunityId']]['choice'] == 'general'
    done = labels.import_batch(root, receipts, path, supersede=True)
    assert done['results'] == {'superseded': 1} and done['supersede'] is True
    assert stored_ids(root)[receipt['opportunityId']]['choice'] == 'none'
    assert labels.import_batch(root, receipts, path, supersede=True)['results'] == {'already_recorded': 1}


def test_supersede_flag_reaches_the_command_line(tmp_path, capsys, monkeypatch):
    root, receipts, receipt = make(tmp_path)
    labels.record_label(root, receipts, value(root, receipt, choiceBasis=labels.FAMILY_MAP), 'a' * 64)
    path = write(tmp_path, [annotation(root, receipt, family='feature_delivery', phase='implement',
                                       areas=['backend_api'], choice='none')], 'annotations.json')
    argv = ['pilot_labels.py', '--root', str(root), '--receipts', str(receipts), 'import-batch',
            '--annotations', str(path), '--supersede']
    monkeypatch.setattr(sys, 'argv', argv)
    assert labels.main() == 0
    assert json.loads(capsys.readouterr().out)['results'] == {'superseded': 1}
