"""Verify observational collection and research boundaries with private fixtures."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'rhize-context-manager/scripts'))
import decision_pilot as pilot
import workflow_selection as workflow


def observed(tmp_path, turn='t', host='codex', prompt='research workflow secret-customer-44'):
    receipts, root = tmp_path / 'receipts', tmp_path / 'pilot'
    receipt, _ = workflow.opportunity({'prompt': prompt, 'session_id': 'session', 'turn_id': turn}, host, receipts,
                                      {'decisionPilot': {'enabled': True, 'mode': 'shadow'}})
    pilot.enqueue(prompt, receipt, root, spawn=False)
    return root, receipts, receipt


def scored_call(url, request):
    assert url == 'http://127.0.0.1:8000'
    return {'routing': {'model': 'typed-decisions'},
            'answers': {f'c{i}': {'type': 'noul', 'noul': n} for i, n in enumerate((.2, .8, .1))},
            'usage': {'input_tokens': 40, 'output_tokens': 3}}, 5


def choose(receipts, receipt, decision='no_match'):
    return workflow.decide(receipts, SimpleNamespace(id=receipt['opportunityId'], decision=decision,
                           workflow=None, variant=None, reason='no_suitable_workflow'))


def evidence(tmp_path, root, receipt, kind='label'):
    identity = receipt['opportunityId']
    observation = workflow.read_json(root / 'observations' / (identity + '.json'))
    value = {'opportunityId': identity, 'sourceSha256': observation['sourceSha256']}
    if kind == 'label':
        value.update(choice='general', reviewer='human-test-fixture', basis='human_adjudicated',
                     stratum='ordinary', reviewEvidenceSha256='c' * 64)
    else:
        value.update(outcome='undetermined', qualityScore=None, checksPassed=None, reviewPassed=None,
                     criticalFailureCount=None, reworkCount=None, wallMs=None,
                     usage={'input_tokens': None, 'output_tokens': None}, rubricSha256=None)
    path = tmp_path / (kind + '.json'); path.write_text(json.dumps(value))
    return path, value


def test_collection_redacted_deduplicated_and_detached(tmp_path, monkeypatch):
    root, receipts, receipt = observed(tmp_path)
    calls = []
    monkeypatch.setattr(pilot.subprocess, 'Popen', lambda *a, **k: calls.append((a, k)))
    pilot.enqueue('secret-new-text', receipt, root)
    assert len(pilot.inventory(root / 'observations')) == 1
    raw = next((root / 'observations').glob('*.json')).read_text()
    assert 'secret' not in raw and 'customer' not in raw
    assert calls[0][1]['stdin'] == subprocess.DEVNULL
    assert calls[0][1]['stdout'] == subprocess.DEVNULL and calls[0][1]['close_fds']
    assert calls[0][1]['start_new_session']
    assert next((root / 'observations').glob('*.json')).stat().st_mode & 0o777 == 0o600


def test_missing_observation_counts_against_denominator(tmp_path):
    root, receipts, receipt = observed(tmp_path)
    next((root / 'observations').glob('*.json')).unlink()
    result = pilot.report(root, receipts)
    assert result['opportunities'] == 1 and result['missingObservations'] == 1
    assert result['armBAccuracy'] is None


def test_result_join_queue_and_baseline_unchanged(tmp_path):
    root, receipts, receipt = observed(tmp_path)
    choose(receipts, receipt)
    before = next(receipts.glob('*.json')).read_bytes()
    assert pilot.drain(root, scored_call)['processed'] == 1
    assert pilot.drain(root, lambda *args: pytest.fail('duplicate inference'))['processed'] == 0
    result = pilot.report(root, receipts)
    assert result['validResults'] == 1 and result['disagreements'] == 1
    assert result['humanLabels'] == 0 and result['armBAccuracy'] is None
    assert pilot.queue(root, receipts)['items'][0]['reason'] == 'disagreement'
    assert next(receipts.glob('*.json')).read_bytes() == before


def test_failure_is_retained_no_retry_and_no_fake_zero_usage(tmp_path):
    root, receipts, _ = observed(tmp_path)
    def fail(*a): raise TimeoutError('private transport details')
    pilot.drain(root, fail)
    result = pilot.report(root, receipts)
    assert result['unavailableResults'] == 1 and result['localUsageMissing'] == 1
    assert 'private transport details' not in next((root / 'results').glob('*.json')).read_text()
    assert pilot.drain(root, scored_call)['processed'] == 0


def test_changed_collection_source_does_not_run_new_questions(tmp_path, monkeypatch):
    root, receipts, _ = observed(tmp_path)
    monkeypatch.setattr(pilot, 'source_digest', lambda: 'a' * 64)
    pilot.drain(root, lambda *a: pytest.fail('stale observation inferred'))
    assert pilot.report(root, receipts)['unavailableResults'] == 1


def test_human_labels_bind_exact_source_and_export(tmp_path):
    root, receipts, receipt = observed(tmp_path)
    choose(receipts, receipt)
    pilot.drain(root, scored_call)
    path, value = evidence(tmp_path, root, receipt)
    pilot.bind_evidence(root, receipt['opportunityId'], path, 'labels')
    assert pilot.report(root, receipts)['armBAccuracy'] == 1
    output = tmp_path / 'cases.jsonl'
    assert pilot.export_cases(root, receipts, output)['count'] == 1
    case = json.loads(output.read_text())
    assert case['labels'] == {'c0': False, 'c1': True, 'c2': False}
    assert case['arm_a'] == {'c0': False, 'c1': False, 'c2': True}
    assert case['group_id'] == receipt['sessionHash']
    with pytest.raises(FileExistsError): pilot.export_cases(root, receipts, output)
    value['choice'] = 'none'; path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match='immutable'): pilot.bind_evidence(root, receipt['opportunityId'], path, 'labels')


@pytest.mark.parametrize('field,value', [('sourceSha256', 'a'*64), ('basis', 'model_proposed'), ('reviewer', ''), ('choice', 'invented')])
def test_invalid_label_rejected(tmp_path, field, value):
    root, _, receipt = observed(tmp_path)
    path, data = evidence(tmp_path, root, receipt); data[field] = value; path.write_text(json.dumps(data))
    with pytest.raises(ValueError): pilot.bind_evidence(root, receipt['opportunityId'], path, 'labels')


def test_stop_exact_identity_never_accepts(tmp_path):
    root, receipts, receipt = observed(tmp_path)
    assert pilot.stop(root, receipts, {'thread_id': 'session'}, 'codex')['status'] == 'unavailable'
    assert pilot.stop(root, receipts, {'thread_id': 'session', 'turn_id': 'old'}, 'codex')['status'] == 'unavailable'
    assert pilot.stop(root, receipts, {'thread_id': 'session', 'turn_id': 't'}, 'codex')['status'] == 'recorded'
    result = pilot.report(root, receipts)
    assert result['nativeStops'] == 1 and result['outcomes'] == 0
    assert result['completeAgentUsage'] == 0


def test_unknown_outcomes_and_acceptance_checks(tmp_path):
    root, receipts, receipt = observed(tmp_path)
    path, value = evidence(tmp_path, root, receipt, 'outcome')
    value['outcome'] = 'accepted'; path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match='accepted requires'): pilot.bind_evidence(root, receipt['opportunityId'], path, 'outcomes')
    value['outcome'] = 'undetermined'; path.write_text(json.dumps(value))
    pilot.bind_evidence(root, receipt['opportunityId'], path, 'outcomes')
    result = pilot.report(root, receipts)
    assert result['outcomes'] == 1 and result['completeAgentUsage'] == 0


def test_corrupt_and_symlink_inventory_fail_explicitly(tmp_path):
    root, receipts, receipt = observed(tmp_path)
    path = next((root / 'observations').glob('*.json'))
    path.write_text('{}broken')
    with pytest.raises(ValueError): pilot.report(root, receipts)
    path.unlink(); path.symlink_to(next(receipts.glob('*.json')))
    with pytest.raises(ValueError, match='symlink'): pilot.report(root, receipts)


def test_hook_disabled_and_optin_preserve_checkpoint(tmp_path, monkeypatch, capsys):
    import io
    data = tmp_path / 'data'
    config = data / 'config.json'; data.mkdir()
    receipts = data / 'receipts'
    config.write_text(json.dumps({'schemaVersion': 1, 'enabled': True}))
    monkeypatch.setattr(sys, 'argv', ['workflow_selection.py', '--root', str(receipts), 'hook', '--config', str(config)])
    monkeypatch.setattr(pilot.subprocess, 'Popen', lambda *a, **kw: None)
    monkeypatch.setenv('CLAUDE_CODE_ENTRYPOINT', '')
    monkeypatch.setenv('PLUGIN_ROOT', 'codex-fixture')
    def invoke(turn):
        payload = json.dumps({'prompt': 'workflow review', 'thread_id': 'host', 'turn_id': turn}).encode()
        monkeypatch.setattr(sys, 'stdin', io.TextIOWrapper(io.BytesIO(payload)))
        assert workflow.main() == 0
        return capsys.readouterr().out
    assert 'Workflow selection checkpoint' in invoke('one')
    assert not (data / 'pilot').exists()
    config.write_text(json.dumps({'schemaVersion': 1, 'enabled': True, 'decisionPilot': {'enabled': True, 'mode': 'shadow'}}))
    assert 'Laya workflow pilot' in invoke('two')
    assert len(list((data/'pilot/observations').glob('*.json'))) == 1


def load_cycle():
    spec = importlib.util.spec_from_file_location('pilot_cycle', REPO/'evals/typed-decision/pilot_cycle.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def test_research_held_without_labels_and_no_agent_launch(tmp_path):
    module = load_cycle()
    result = module.cycle(tmp_path/'pilot', tmp_path/'receipts', tmp_path/'research', run=lambda *a, **kw: pytest.fail('launched'))
    assert result['status'] == 'held' and result['labels'] == 0
    assert not (tmp_path/'research').exists()
    assert len(module.candidates()) <= 12


def test_stop_entrypoint_always_nonblocking(tmp_path):
    hooks = json.loads((REPO/'rhize-context-manager/hooks/hooks.json').read_text())['hooks']['Stop']
    command = next(h['command'] for group in hooks for h in group['hooks'] if 'decision_pilot.py' in h['command'])
    for plugin in (tmp_path/'missing', REPO/'rhize-context-manager'):
        done = subprocess.run(command, shell=True, input='bad', text=True, capture_output=True,
                              env={**os.environ, 'CLAUDE_PLUGIN_ROOT': str(plugin), 'XDG_DATA_HOME': str(tmp_path)}, timeout=10)
        assert done.returncode == 0 and not done.stdout and not done.stderr


def test_research_search_only_failure_preserved_and_retry_deduplicated(tmp_path):
    module = load_cycle()
    receipts, root = tmp_path/'receipts', tmp_path/'pilot'
    for index in range(24):
        receipt, _ = workflow.opportunity({'prompt': 'workflow software review', 'session_id': f'session-{index}', 'turn_id': 't'},
                                          'codex', receipts, {'decisionPilot': {'enabled': True, 'mode': 'shadow'}})
        pilot.enqueue('workflow software review', receipt, root, spawn=False)
        path, _ = evidence(tmp_path, root, receipt)
        pilot.bind_evidence(root, receipt['opportunityId'], path, 'labels')
    calls = []
    def fail(command, **kwargs):
        calls.append(command)
        assert '--phase' in command and command[command.index('--phase')+1] == 'search'
        assert '--holdout' not in command and kwargs['timeout'] <= 180
        return SimpleNamespace(returncode=1)
    result = module.cycle(root, receipts, tmp_path/'research', minimum=20, run=fail)
    assert result['status'] == 'failed' and len(calls) == 1
    assert module.cycle(root, receipts, tmp_path/'research', minimum=20, run=fail)['status'] == 'unchanged'
    assert len(calls) == 1
    assert next((tmp_path/'research').glob('*/status.json')).stat().st_mode & 0o777 == 0o600


def test_research_freezes_candidate_but_does_not_promote(tmp_path):
    module = load_cycle()
    receipts, root = tmp_path/'receipts', tmp_path/'pilot'
    for index in range(24):
        receipt, _ = workflow.opportunity({'prompt': 'workflow software review', 'session_id': f'session-{index}', 'turn_id': 't'},
                                          'codex', receipts, {'decisionPilot': {'enabled': True, 'mode': 'shadow'}})
        pilot.enqueue('workflow software review', receipt, root, spawn=False)
        path, _ = evidence(tmp_path, root, receipt)
        pilot.bind_evidence(root, receipt['opportunityId'], path, 'labels')
    def run(command, **kwargs):
        options = json.loads(Path(command[command.index('--candidates')+1]).read_text())
        sha = workflow.digest(json.dumps(options[0], sort_keys=True, separators=(',', ':')))
        Path(command[command.index('--ledger')+1]).write_text(json.dumps({'status': 'keep', 'candidate_sha256': sha})+'\n')
        return SimpleNamespace(returncode=0)
    result = module.cycle(root, receipts, tmp_path/'research', minimum=20, run=run)
    assert result['status'] == 'review_required' and result['holdout'] == 'not_run'
    assert result['promotion'] == 'not_performed' and result['releaseEligible'] is False
    assert next((tmp_path/'research').glob('*/frozen-candidate.json')).is_file()


def test_empty_signals_abstain_without_provider_call(tmp_path):
    root, receipts, _ = observed(tmp_path, prompt='Proceed')
    pilot.drain(root, lambda *args: pytest.fail('insufficient input sent to provider'))
    result = json.loads(next((root/'results').glob('*.json')).read_text())
    assert result['reasonCode'] == 'insufficient_task_signals'


def test_export_keeps_original_question_wording_after_source_change(tmp_path, monkeypatch):
    root, receipts, receipt = observed(tmp_path)
    path, _ = evidence(tmp_path, root, receipt)
    pilot.bind_evidence(root, receipt['opportunityId'], path, 'labels')
    import context_experiments.typed_candidates as typed
    monkeypatch.setattr(typed, 'build_request', lambda *args: pytest.fail('reconstructed old question with new source'))
    output = tmp_path/'cases.jsonl'
    pilot.export_cases(root, receipts, output)
    assert 'bounded task signals' in json.loads(output.read_text())['questions']['c0']['instructions']
