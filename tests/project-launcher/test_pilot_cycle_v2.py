"""Invented local fixtures for bounded, versioned development research."""
import importlib.util
import json
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


def key(kind, value):
    return kind + ':' + cycle.digest(str(value))


def case(index):
    choice = 'content' if index % 2 else 'general'
    return {'case_id': str(index), 'group_id': str(index), 'decision_type': 'workflow_fit',
            'stratum': 'ordinary', 'label_source': cycle.digest(str(index)), 'adjudicated': True,
            'state': {'action': 'create', 'domain': 'content' if index % 2 else 'software', 'exclusions': []},
            'questions': {f'c{i}': {'type': 'noul', 'instructions': 'Consider ' + c}
                          for i, c in enumerate(('content', 'general', 'none'))},
            'labels': {f'c{i}': c == choice for i, c in enumerate(('content', 'general', 'none'))},
            'candidate_ids': ['content', 'general', 'none'], 'routing_choice': choice, 'arm_a_choice': 'general',
            'cohort_version': cycle.COHORT, 'collection_source_sha256': 'a' * 64,
            'normalization_version': cycle.NORMALIZATION,
            'grouping_keys': [key('session', index), key('input', index), key('prompt', index)],
            'task_family': 'content' if index % 2 else 'software', 'host': 'codex'}


def corpus(monkeypatch, root, rows):
    labels = root / 'v2/labels'; labels.mkdir(parents=True)
    for i in range(200):
        (labels / (cycle.digest(str(i)) + '.json')).write_text('{}')
    def export(_root, _receipts, output, cohort):
        assert cohort == 'v2'
        output.write_text(''.join(json.dumps(row) + '\n' for row in rows))
        return {'status': 'exported', 'count': len(rows), 'sha256': cycle.digest(output.read_bytes())}
    monkeypatch.setattr(cycle, 'export_cases', export)


def test_automatic_floor_and_durable_label_hold(tmp_path):
    with pytest.raises(ValueError, match='200'):
        cycle.cycle(tmp_path/'pilot', tmp_path/'receipts', tmp_path/'research', minimum=199)
    result = cycle.cycle(tmp_path/'pilot', tmp_path/'receipts', tmp_path/'research')
    assert result['status'] == 'held' and result['labels'] == 0
    artifacts = list((tmp_path/'research'/cycle.COHORT/'holds').glob('*.json'))
    assert len(artifacts) == 1
    assert json.loads(artifacts[0].read_text()) == result
    assert artifacts[0].stat().st_mode & 0o777 == 0o600


def test_duplicate_templates_and_sessions_connect_without_sentinel(tmp_path):
    rows = [case(i) for i in range(3)]
    rows[1]['grouping_keys'][1] = rows[0]['grouping_keys'][1]
    rows[2]['grouping_keys'][0] = rows[1]['grouping_keys'][0]
    grouped, assignments, records = cycle.grouping(rows, [])
    assert len({row['group_id'] for row in grouped}) == 1
    rows[0]['grouping_keys'].append('input:' + '0' * 64)
    with pytest.raises(ValueError, match='invalid_grouping_keys'):
        cycle.grouping(rows, [])


def test_append_only_assignments_preserve_old_holdout_and_hold_bridges():
    a, b = case(1), case(2)
    old = [{'cohort': cycle.COHORT, 'normalization': cycle.NORMALIZATION,
            'keys': a['grouping_keys'], 'split': 'holdout'},
           {'cohort': cycle.COHORT, 'normalization': cycle.NORMALIZATION,
            'keys': b['grouping_keys'], 'split': 'train'}]
    grouped, assignments, _ = cycle.grouping([a, b], old)
    assert assignments[grouped[0]['group_id']] == 'holdout'
    a['grouping_keys'].append(b['grouping_keys'][0])
    with pytest.raises(ValueError, match='cross_split_bridge'):
        cycle.grouping([a, b], old)


def test_diversity_holds_without_dropping_rows():
    rows = [case(i) for i in range(200)]
    for row in rows[:181]: row['group_id'] = 'same'
    result = cycle.diversity(rows)
    assert result['labels'] == 200 and result['largestGroupShare'] == 181/200
    assert 'group_concentration' in result['holdReasons']


def test_legacy_membership_does_not_open_holdout_cases(tmp_path):
    split = tmp_path/'legacy/split'; split.mkdir(parents=True)
    (split/'manifest.json').write_text('{}')
    (split/'holdout.jsonl').write_text('must not parse this')
    with pytest.raises(ValueError, match='legacy_holdout_membership_unavailable'):
        cycle.legacy_holdout_keys(tmp_path)


def test_v2_search_failure_preserved_without_retry(tmp_path, monkeypatch):
    root = tmp_path/'pilot'; research_root = tmp_path/'research'
    corpus(monkeypatch, root, [case(i) for i in range(200)])
    calls = []
    def run(command, **kwargs):
        assert command[command.index('--phase')+1] == 'search'
        assert '--holdout' not in command
        calls.append(command)
        return SimpleNamespace(returncode=9)
    first = cycle.cycle(root, tmp_path/'receipts', research_root, run=run)
    assert first['status'] == 'failed' and first['exitCode'] == 9
    second = cycle.cycle(root, tmp_path/'receipts', research_root, run=run)
    assert second['status'] == 'unchanged' and len(calls) == 1
    directory = research_root/cycle.COHORT/first['runId']
    assert (directory/'started.json').exists() and (directory/'status.json').exists()
    assert list((research_root/cycle.COHORT/'assignments').glob('*.json'))


def test_interrupted_attempt_never_replayed(tmp_path, monkeypatch):
    root = tmp_path/'pilot'; research_root = tmp_path/'research'
    corpus(monkeypatch, root, [case(i) for i in range(200)])
    def interrupted(*args, **kwargs): raise KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        cycle.cycle(root, tmp_path/'receipts', research_root, run=interrupted)
    result = cycle.cycle(root, tmp_path/'receipts', research_root,
                         run=lambda *a, **kw: pytest.fail('replayed'))
    assert result['status'] == 'unchanged' and result['previous']['status'] == 'interrupted'


def test_v2_uses_shared_argmax_mask_and_abstention():
    row = case(1)
    def provider(_):
        return {'answers': {f'c{i}': {'type': 'noul', 'noul': score}
                            for i, score in enumerate((.49, .48, .47))}}, 1
    value = research.evaluate([row], {'id': 'base', 'model': 'fixture'}, provider)
    assert value['count'] == 1 and value['accuracy'] == 1 and value['brier_mean'] is None
    value = research.evaluate([row], {'id': 'base', 'model': 'fixture', 'abstain_below': .65}, provider)
    assert value['abstention_rate'] == 1
    row['state']['exclusions'] = ['content_creation']; row['routing_choice'] = 'general'
    value = research.evaluate([row], {'id': 'base', 'model': 'fixture'}, provider)
    assert value['accuracy'] == 1
    assert research.arm_a_metrics([row])['accuracy'] == 1
    row['arm_a_choice'] = None
    assert research.arm_a_metrics([row]) == 'unavailable'


def test_mixed_source_holds_before_search(tmp_path, monkeypatch):
    root = tmp_path/'pilot'; rows = [case(i) for i in range(200)]
    rows[0]['collection_source_sha256'] = 'b' * 64
    corpus(monkeypatch, root, rows)
    result = cycle.cycle(root, tmp_path/'receipts', tmp_path/'research',
                         run=lambda *a, **kw: pytest.fail('launched'))
    assert result['status'] == 'held' and result['reason'] == 'mixed_collection_source'


def test_malformed_export_failure_preserved(tmp_path, monkeypatch):
    root = tmp_path/'pilot'
    corpus(monkeypatch, root, [case(i) for i in range(200)])
    calls = []
    def invalid(*args, **kwargs):
        calls.append(True)
        raise ValueError('private detail')
    monkeypatch.setattr(cycle, 'export_cases', invalid)
    first = cycle.cycle(root, tmp_path/'receipts', tmp_path/'research')
    assert first['status'] == 'failed' and 'private detail' not in json.dumps(first)
    second = cycle.cycle(root, tmp_path/'receipts', tmp_path/'research')
    assert second['status'] == 'unchanged' and len(calls) == 1


def test_review_candidate_never_grants_release_or_promotion(tmp_path, monkeypatch):
    root = tmp_path/'pilot'
    corpus(monkeypatch, root, [case(i) for i in range(200)])
    def run(command, **kwargs):
        options = json.loads(Path(command[command.index('--candidates')+1]).read_text())
        ledger = Path(command[command.index('--ledger')+1])
        ledger.write_text(json.dumps({'status': 'keep', 'candidate_sha256': research.digest(options[0])}) + '\n')
        return SimpleNamespace(returncode=0)
    result = cycle.cycle(root, tmp_path/'receipts', tmp_path/'research', run=run)
    assert result['status'] == 'review_required'
    assert result['releaseEligible'] is False and result['holdout'] == 'not_run'
    assert result['promotion'] == 'not_performed'


def test_cross_split_identity_rejected_when_materializing(tmp_path):
    a, b, c = case(1), case(2), case(3)
    b['grouping_keys'].append(a['grouping_keys'][0])
    with pytest.raises(ValueError, match='duplicate identity'):
        research.prepare_corpus([a,b,c], 'fixture', tmp_path/'split',
                                split_assignments={'1':'train','2':'validation','3':'holdout'})


def test_export_mixed_collection_source_is_durable_hold(tmp_path, monkeypatch):
    root = tmp_path/'pilot'
    corpus(monkeypatch, root, [case(i) for i in range(200)])
    def mixed(*args, **kwargs):
        raise ValueError('mixed_collection_sources')
    monkeypatch.setattr(cycle, 'export_cases', mixed)
    result = cycle.cycle(root, tmp_path/'receipts', tmp_path/'research',
                         run=lambda *a, **kw: pytest.fail('launched'))
    assert result['status'] == 'held' and result['reason'] == 'mixed_collection_source'
    holds = list((tmp_path/'research'/cycle.COHORT/'holds').glob('*.json'))
    assert any(json.loads(p.read_text()) == result for p in holds)
    assert not (tmp_path/'research'/cycle.COHORT/'preflight-failures').exists()


def test_stored_assignment_sentinel_is_rejected():
    record = {'cohort': cycle.COHORT, 'normalization': cycle.NORMALIZATION,
              'keys': ['input:' + '0' * 64], 'split': 'train'}
    with pytest.raises(ValueError, match='invalid_grouping_keys'):
        cycle.grouping([case(1)], [record])


def test_preflight_identity_changes_after_bound_input_repair(tmp_path, monkeypatch):
    root, receipts = tmp_path/'pilot', tmp_path/'receipts'
    corpus(monkeypatch, root, [case(i) for i in range(200)])
    receipts.mkdir(); receipt = receipts/(cycle.digest('bound') + '.json')
    receipt.write_text('malformed')
    def invalid(*a, **kw): raise ValueError('invalid fixture')
    monkeypatch.setattr(cycle, 'export_cases', invalid)
    first = cycle.cycle(root, receipts, tmp_path/'research')
    assert cycle.cycle(root, receipts, tmp_path/'research')['status'] == 'unchanged'
    receipt.write_text('{"repaired":true}')
    second = cycle.cycle(root, receipts, tmp_path/'research')
    assert first['status'] == second['status'] == 'failed'
    assert first['runId'] != second['runId']
    assert len(list((tmp_path/'research'/cycle.COHORT/'preflight-failures').glob('*.json'))) == 2


def test_legacy_metadata_correction_creates_new_attempt_preserving_hold(tmp_path, monkeypatch):
    root, research_root = tmp_path/'pilot', tmp_path/'research'
    corpus(monkeypatch, root, [case(i) for i in range(200)])
    split = research_root/'legacy/split'; split.mkdir(parents=True)
    manifest = split/'manifest.json'; manifest.write_text('{}')
    first = cycle.cycle(root, tmp_path/'receipts', research_root,
                        run=lambda *a, **k: pytest.fail('legacy metadata unavailable'))
    assert first['reason'] == 'legacy_holdout_membership_unavailable'
    old = (research_root/cycle.COHORT/first['runId']/'status.json').read_bytes()
    manifest.write_text(json.dumps({'holdout_grouping_keys': [key('session', 'unseen')]}))
    second = cycle.cycle(root, tmp_path/'receipts', research_root,
                         run=lambda *a, **k: SimpleNamespace(returncode=7))
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
    rows = [case(i) for i in range(200)]
    rows[1]['state']['exclusions'] = ['content_creation']
    root = tmp_path/'pilot'; corpus(monkeypatch, root, rows)
    result = cycle.cycle(root, tmp_path/'receipts', tmp_path/'research',
                         run=lambda *a, **kw: pytest.fail('launched contradictory corpus'))
    assert result['status'] == 'held' and result['reason'] == 'label_contradicts_exclusions'
    assert result['labels'] == 200 and rows[1]['routing_choice'] == 'content'


def test_critical_abstention_cannot_reduce_critical_misses():
    row = case(1); row['stratum'] = 'critical_safety'
    def provider(_):
        return {'answers': {f'c{i}': {'type': 'noul', 'noul': score}
                            for i, score in enumerate((.49, .48, .47))}}, 1
    result = research.evaluate([row], {'id': 'abstain', 'model': 'fixture', 'abstain_below': .8}, provider)
    assert result['abstention_rate'] == 1 and result['critical_misses'] == 1
    baseline = research.evaluate([row], {'id': 'base', 'model': 'fixture'}, provider)
    assert baseline['accuracy'] == 1 and baseline['critical_misses'] == 0


def test_export_hold_reports_actual_label_inventory(tmp_path, monkeypatch):
    root = tmp_path/'pilot'; corpus(monkeypatch, root, [case(i) for i in range(200)])
    monkeypatch.setattr(cycle, 'export_cases', lambda *a, **k: {'status': 'held', 'reason': 'no_eligible_cases'})
    result = cycle.cycle(root, tmp_path/'receipts', tmp_path/'research')
    assert result['labels'] == 200 and result['reason'] == 'no_eligible_cases'


def test_preflight_failure_receipt_write_failure_is_structured(tmp_path, monkeypatch):
    root = tmp_path/'pilot'; corpus(monkeypatch, root, [case(i) for i in range(200)])
    def invalid(*a, **kw): raise ValueError('invalid')
    def denied(*a, **kw): raise PermissionError('private path')
    monkeypatch.setattr(cycle, 'export_cases', invalid)
    monkeypatch.setattr(cycle, 'private_write', denied)
    result = cycle.cycle(root, tmp_path/'receipts', tmp_path/'research')
    assert result['status'] == 'failed' and result['persistence'] == 'unavailable'
    assert 'private path' not in json.dumps(result)


def test_cli_invalid_bounds_is_structured_json(tmp_path):
    import subprocess, sys
    for args in (['--minimum-labels', '199'], ['--deadline-seconds', '0']):
        done = subprocess.run([sys.executable, str(ROOT/'evals/typed-decision/pilot_cycle.py'),
                               '--research-root', str(tmp_path/'research'), *args],
                              text=True, capture_output=True, timeout=10)
        assert done.returncode == 1 and not done.stderr
        assert json.loads(done.stdout)['reason'] == 'invalid_research_bounds'


def taxonomy_case(index):
    row = case(index)
    choice = ('content', 'general', 'none')[index % 3]
    family = {'content': 'content_growth', 'none': 'direct_response'}.get(
        choice, ('feature_delivery', 'defect_resolution', 'code_health', 'research_analysis')[index % 4])
    return {**row, 'routing_choice': choice, 'labels': {f'c{i}': c == choice for i, c in enumerate(('content', 'general', 'none'))},
            'stratum': 'elevated' if index % 4 == 0 else 'routine', 'label_basis': 'ai_model_reviewed',
            'family': family, 'choice_basis': 'explicit'}


def taxonomy_corpus(monkeypatch, rows, count=200, bases=('human_adjudicated', 'ai_model_reviewed'), choice_basis='explicit'):
    stored = [{'basis': 'ai_model_reviewed', 'choiceBasis': choice_basis, 'opportunityId': cycle.digest(str(i))}
              for i in range(count)]
    monkeypatch.setattr(cycle.pilot_labels, 'load_labels', lambda root: stored)
    monkeypatch.setattr(cycle.pilot_labels, 'load_policy', lambda root: {
        'schema': 'rhize-pilot-label-policy-v1', 'acceptedBases': list(bases), 'reason': 'fixture', 'setBy': 'jim'})
    def write(_root, _receipts, output, accepted):
        assert accepted == list(bases)
        output.write_text(''.join(json.dumps(row) + '\n' for row in rows))
        return {'status': 'exported', 'count': len(rows), 'sha256': cycle.digest(output.read_bytes())}
    monkeypatch.setattr(cycle.pilot_labels, 'write_cases', write)


def keep_first(command, **kwargs):
    options = json.loads(Path(command[command.index('--candidates')+1]).read_text())
    Path(command[command.index('--ledger')+1]).write_text(
        json.dumps({'status': 'keep', 'candidate_sha256': research.digest(options[0])}) + '\n')
    return SimpleNamespace(returncode=0)


def test_taxonomy_labels_below_floor_hold_with_basis_facts(tmp_path, monkeypatch):
    taxonomy_corpus(monkeypatch, [], count=8, choice_basis='derived:family-map-v1')
    result = cycle.cycle(tmp_path/'pilot', tmp_path/'receipts', tmp_path/'research')
    assert result['reason'] == 'insufficient_accepted_labels' and result['labels'] == 0
    assert result['taxonomyLabels'] == 8 and result['derivedChoiceLabels'] == 8
    taxonomy_corpus(monkeypatch, [], count=8, bases=('human_adjudicated',))
    result = cycle.cycle(tmp_path/'pilot', tmp_path/'receipts', tmp_path/'research')
    assert result['labels'] == 0 and result['acceptedBases'] == ['human_adjudicated']


def test_legacy_and_taxonomy_answer_keys_never_merge(tmp_path, monkeypatch):
    root = tmp_path/'pilot'
    corpus(monkeypatch, root, [case(i) for i in range(200)])
    taxonomy_corpus(monkeypatch, [], count=200)
    result = cycle.cycle(root, tmp_path/'receipts', tmp_path/'research')
    assert result['reason'] == 'mixed_label_schemas' and result['labels'] == 200


def test_taxonomy_path_names_sparse_slices(tmp_path, monkeypatch):
    rows = [{**taxonomy_case(i), 'routing_choice': 'general', 'family': 'feature_delivery', 'stratum': 'routine',
             'labels': {'c0': False, 'c1': True, 'c2': False}} for i in range(200)]
    taxonomy_corpus(monkeypatch, rows)
    result = cycle.cycle(tmp_path/'pilot', tmp_path/'receipts', tmp_path/'research', run=keep_first)
    assert result['reason'] == 'insufficient_diversity'
    assert set(result['coverage']['taxonomy']['holdReasons']) == {
        'insufficient_routing_class_coverage', 'insufficient_family_coverage', 'insufficient_risk_coverage'}
    assert result['labelBasis'] == {'ai_model_reviewed': 200} and 'exploratory' in result['claimScope']


def test_taxonomy_search_records_policy_and_never_releases(tmp_path, monkeypatch):
    taxonomy_corpus(monkeypatch, [taxonomy_case(i) for i in range(200)])
    result = cycle.cycle(tmp_path/'pilot', tmp_path/'receipts', tmp_path/'research', run=keep_first)
    assert result['status'] == 'review_required' and result['releaseEligible'] is False
    assert result['coverage']['taxonomy']['holdReasons'] == []
    assert result['coverage']['taxonomy']['criticalClaimsSupported'] is False
    assert result['config']['acceptedBases'] == ['human_adjudicated', 'ai_model_reviewed']
    assert len(result['config']['labelPolicySha256']) == 64 and result['labelBasis'] == {'ai_model_reviewed': 200}


def test_legacy_config_has_no_taxonomy_keys(tmp_path, monkeypatch):
    root = tmp_path/'pilot'
    corpus(monkeypatch, root, [case(i) for i in range(200)])
    result = cycle.cycle(root, tmp_path/'receipts', tmp_path/'research', run=keep_first)
    assert result['status'] == 'review_required' and 'claimScope' not in result
    assert set(result['config']) == {'minimum', 'deadline', 'minimumGroups', 'minimumDomains',
                                     'minimumDomainLabels', 'maximumGroupShare', 'normalization'}


def test_research_rows_accept_only_known_label_bases(tmp_path):
    path = tmp_path/'cases.jsonl'
    path.write_text(json.dumps(taxonomy_case(1)) + '\n')
    assert research.read_jsonl(path)[0]['label_basis'] == 'ai_model_reviewed'
    path.write_text(json.dumps({**taxonomy_case(1), 'label_basis': 'crowd'}) + '\n')
    with pytest.raises(ValueError, match='label basis'):
        research.read_jsonl(path)
