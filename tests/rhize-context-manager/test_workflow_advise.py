"""Advisory Laya surfaces in workflow_selection: workflow-fit on `context`, `recommend-procedure`, hook text."""
import io
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / 'rhize-context-manager/scripts'
sys.path.insert(0, str(SCRIPTS))
import decision_pilot_v2 as pilot  # noqa: E402
import typed_advice as ta  # noqa: E402
import workflow_selection as ws  # noqa: E402

FAMILY_ANSWER = {'status': 'ok', 'choice': 'general', 'probabilities': {'content': 0.1, 'general': 0.8, 'none': 0.1},
                 'latencyMs': 1.0}


class FakeLaya:
    def __init__(self, answer):
        self.answer, self.calls = answer, []

    def __call__(self, request, files, question, candidates, **kwargs):
        self.calls.append({'request': request, 'question': question, 'ids': [c['id'] for c in candidates]})
        return dict(self.answer)


@pytest.fixture
def store(tmp_path, monkeypatch):
    path = tmp_path / 'typed'
    path.mkdir()
    monkeypatch.setenv('RHIZE_TYPED_DECISIONS_ROOT', str(path))
    return path


def write_state(store, decision, policy_sha, mode='advise'):
    (store / 'registry-state.json').write_text(json.dumps({'decisions': {decision: {
        'mode': mode, 'policySha256': policy_sha, 'instrumentSha256': ta.INSTRUMENT_SHA256, 'layaRevision': None}}}))


def workflow_sha():
    return ta.policy_sha256('workflow-fit', pilot.ADVICE_QUESTION, pilot.ADVICE_POLICY)


def procedure_sha():
    return ta.policy_sha256('procedure-pick', ws.PROCEDURE_QUESTION, ws.PROCEDURE_POLICY)


def seal_opportunity(tmp_path, turn='one', prompt='Migrate the billing job to the new queue'):
    """A real hook run: receipt plus the sealed, redacted request snapshot."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    cfg = tmp_path / 'config.json'
    cfg.write_text(json.dumps({'schemaVersion': 1, 'enabled': True,
                               'decisionPilot': {'enabled': True, 'mode': 'shadow', 'cohort': 'v2'}}))
    root = tmp_path / 'wf/receipts'
    result = subprocess.run([sys.executable, str(SCRIPTS / 'workflow_selection.py'), '--root', str(root), 'hook',
                             '--host', 'claude', '--config', str(cfg)],
                            input=json.dumps({'prompt': prompt, 'session_id': 'fx', 'turn_id': turn}), text=True,
                            capture_output=True, timeout=10, env=dict(os.environ))
    assert result.returncode == 0, result.stderr
    receipt = next(p for p in root.glob('*.json') if json.loads(p.read_text()).get('opportunityId'))
    return root, json.loads(receipt.read_text())['opportunityId']


def force_holdback(monkeypatch, held):
    monkeypatch.setattr(ta, 'holdback', lambda decision, key: held)


def outcome(store, decision, decision_id):
    return ta.load(decision, decision_id, kind='outcome', store=store)


# ------------------------------------------------------------------ workflow-fit on `context`

def test_workflow_advice_matrix(tmp_path, store, monkeypatch):
    force_holdback(monkeypatch, False)
    laya = FakeLaya(FAMILY_ANSWER)
    monkeypatch.setattr(ta, 'choice', laya)
    root, identity = seal_opportunity(tmp_path / 'a')

    assert ws.workflow_advice(root, identity) is None  # no registry state -> shadow
    write_state(store, 'workflow-fit', workflow_sha(), mode='shadow')
    assert ws.workflow_advice(root, identity) is None
    (store / 'registry-state.json').unlink()  # the shadow runs left write-once records; fresh opportunity below

    root, identity = seal_opportunity(tmp_path / 'b')
    write_state(store, 'workflow-fit', workflow_sha())
    advice = ws.workflow_advice(root, identity)
    decision_id = ta.sha256('workflow-fit:' + identity)[:32]
    assert advice == {'decisionType': 'workflow-fit', 'decisionId': decision_id, 'recommendedFamily': 'general',
                      'confidence': 0.8, 'calibrated': False, 'holdback': False, 'basis': 'laya-advise',
                      'note': ws.ADVICE_NOTE}
    assert laya.calls[-1]['question'] == pilot.ADVICE_QUESTION
    assert laya.calls[-1]['ids'] == ['content', 'general', 'none']
    assert 'Migrate the billing job' in laya.calls[-1]['request']

    # a stale binding reads as shadow
    write_state(store, 'workflow-fit', '0' * 64)
    root, identity = seal_opportunity(tmp_path / 'c')
    assert ws.workflow_advice(root, identity) is None


def test_workflow_advice_holdback_snapshot_missing_and_exception(tmp_path, store, monkeypatch):
    laya = FakeLaya(FAMILY_ANSWER)
    monkeypatch.setattr(ta, 'choice', laya)
    write_state(store, 'workflow-fit', workflow_sha())

    force_holdback(monkeypatch, True)
    root, identity = seal_opportunity(tmp_path / 'h')
    assert ws.workflow_advice(root, identity) is None
    assert laya.calls, 'holdback still asks Laya for shadow evidence'
    assert ta.load('workflow-fit', ta.sha256('workflow-fit:' + identity)[:32], store=store)['arm'] == 'holdback'

    force_holdback(monkeypatch, False)
    root, identity = seal_opportunity(tmp_path / 'm')
    (root.parent / 'request-snapshots' / (identity + '.json')).unlink()
    calls = len(laya.calls)
    assert ws.workflow_advice(root, identity) is None and len(laya.calls) == calls

    root, identity = seal_opportunity(tmp_path / 'x')
    monkeypatch.setattr(ta, 'advise', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('boom')))
    assert ws.workflow_advice(root, identity) is None


def test_non_ok_laya_gives_no_recommendation(tmp_path, store, monkeypatch):
    force_holdback(monkeypatch, False)
    monkeypatch.setattr(ta, 'choice', FakeLaya({'status': 'timeout', 'choice': None, 'probabilities': None,
                                                'latencyMs': 3000.0}))
    write_state(store, 'workflow-fit', workflow_sha())
    root, identity = seal_opportunity(tmp_path)
    assert ws.workflow_advice(root, identity) is None


def test_consult_records_the_family_as_the_outcome(tmp_path, store, monkeypatch):
    force_holdback(monkeypatch, False)
    monkeypatch.setattr(ta, 'choice', FakeLaya(FAMILY_ANSWER))
    write_state(store, 'workflow-fit', workflow_sha())
    root, identity = seal_opportunity(tmp_path)
    ws.workflow_advice(root, identity)
    decision_id = ta.sha256('workflow-fit:' + identity)[:32]
    assert outcome(store, 'workflow-fit', decision_id) is None
    ws.record_advice_outcome('workflow-fit', identity, 'content')
    ws.record_advice_outcome('workflow-fit', identity, 'general')  # first write wins
    recorded = outcome(store, 'workflow-fit', decision_id)
    assert recorded['chosen'] == 'content' and recorded['followed'] is False
    ws.record_advice_outcome('workflow-fit', 'f' * 64, 'content')  # no record: silently ignored


def test_consult_command_survives_and_records(tmp_path, store, monkeypatch, capsys):
    force_holdback(monkeypatch, False)
    monkeypatch.setattr(ta, 'choice', FakeLaya(FAMILY_ANSWER))
    write_state(store, 'workflow-fit', workflow_sha())
    root, identity = seal_opportunity(tmp_path)
    ws.workflow_advice(root, identity)
    import workflow_task_context
    monkeypatch.setattr(workflow_task_context, 'capture_consultation', lambda *a: {'kind': 'general'})
    evidence = tmp_path / 'evidence.txt'
    evidence.write_text('consulted')
    monkeypatch.setattr(sys, 'argv', ['ws', '--root', str(root), 'consult', '--id', identity, '--family', 'general',
                                      '--evidence', str(evidence)])
    assert ws.main() == 0
    assert json.loads(capsys.readouterr().out) == {'kind': 'general'}
    assert outcome(store, 'workflow-fit', ta.sha256('workflow-fit:' + identity)[:32])['chosen'] == 'general'


# ------------------------------------------------------------------ hook text

def test_hook_text_is_mode_aware(store):
    receipt = {'decisionPilot': 'shadow-v2', 'opportunityId': 'a' * 64}
    shadow = ws.hook_message(receipt)
    assert 'keeps Arm A authoritative and Laya in shadow' in shadow
    assert 'credential CLI procedure selection' in shadow and 'recommend-procedure --id ' + 'a' * 64 in shadow
    write_state(store, 'workflow-fit', workflow_sha())
    advise = ws.hook_message(receipt)
    assert 'in shadow' not in advise.split('Opportunity ID')[0]
    assert 'may print an advisory Laya recommendation (layaAdvice)' in advise
    assert 'credential CLI procedure selection' in advise
    write_state(store, 'workflow-fit', '1' * 64)  # stale binding
    assert 'Laya in shadow' in ws.hook_message(receipt)


# ------------------------------------------------------------------ recommend-procedure

def hits(n=3):
    return [{'id': f'proc-{i}', 'title': f'Procedure {i}', 'summary': 'does thing ' + 'x' * 400} for i in range(n)]


def procedure_answer(choice='proc-1'):
    ids = ['proc-0', 'proc-1', 'proc-2', 'none']
    return {'status': 'ok', 'choice': choice, 'probabilities': {i: 0.1 for i in ids} | {choice: 0.7}, 'latencyMs': 2.0}


def advised_procedure_opportunity(tmp_path, store, monkeypatch, hit_ids=None):
    """An opportunity whose procedure-pick advice is shown (holdback forced off)."""
    laya = FakeLaya(procedure_answer())
    monkeypatch.setattr(ta, 'choice', laya)
    write_state(store, 'procedure-pick', procedure_sha())
    force_holdback(monkeypatch, False)
    root, identity = seal_opportunity(tmp_path)
    return root, identity, laya


def test_recommend_procedure_builds_candidates_and_advises(tmp_path, store, monkeypatch):
    root, identity, laya = advised_procedure_opportunity(tmp_path, store, monkeypatch)
    document = [{'id': 'bad id!', 'title': 'x'}, {'id': '../escape'}, {'id': 'none', 'title': 'shadow'}, 'junk',
                {'id': 'proc-0', 'title': 'Procedure 0', 'summary': 'does thing ' + 'x' * 400},
                {'id': 'proc-0', 'title': 'duplicate'}] + hits(8)[1:]
    out = ws.recommend_procedure(root, identity, document)
    assert laya.calls[-1]['ids'] == ['proc-0', 'proc-1', 'proc-2', 'proc-3', 'proc-4', 'none']
    assert laya.calls[-1]['question'] == ws.PROCEDURE_QUESTION
    assert out['mode'] == 'advise' and out['decisionId']
    assert out['layaAdvice']['recommendedProcedure'] == 'proc-1'
    assert out['layaAdvice']['decisionType'] == 'procedure-pick' and out['layaAdvice']['calibrated'] is False
    record = ta.load('procedure-pick', out['decisionId'], store=store)
    assert record['candidates'] == ['proc-0', 'proc-1', 'proc-2', 'proc-3', 'proc-4', 'none']
    snapshot = ta.load('procedure-pick', out['decisionId'], kind='snapshot', store=store)
    criteria = {c['id']: c['criterion'] for c in snapshot['candidates']}
    assert len(criteria['proc-0']) == 160 and criteria['proc-0'].startswith('Procedure 0: does thing')
    assert criteria['none'] == 'none of these procedures fits; work without one'


def test_recommend_procedure_idempotent_and_decide_records_outcome(tmp_path, store, monkeypatch):
    hit_list = hits(3)
    root, identity, laya = advised_procedure_opportunity(tmp_path, store, monkeypatch)
    first = ws.recommend_procedure(root, identity, hit_list)
    assert first['layaAdvice']['recommendedProcedure'] == 'proc-1'
    again = ws.recommend_procedure(root, identity, list(reversed(hit_list)))
    assert again['decisionId'] == first['decisionId'] and len(laya.calls) == 1
    assert ws.recommend_procedure(root, identity, hits(2))['decisionId'] != first['decisionId']
    # the second call moved the pointer; ask again so decide targets the full hit set
    ws.recommend_procedure(root, identity, hit_list)

    args = SimpleNamespace(id=identity, decision='reuse', workflow='proc-1', procedure=None)
    ws.record_procedure_outcome(root, args)
    recorded = outcome(store, 'procedure-pick', first['decisionId'])
    assert recorded['chosen'] == 'proc-1' and recorded['followed'] is True


def test_decide_no_match_records_none_and_skip_records_nothing(tmp_path, store, monkeypatch):
    hit_list = hits(3)
    root, identity, _ = advised_procedure_opportunity(tmp_path, store, monkeypatch)
    first = ws.recommend_procedure(root, identity, hit_list)
    ws.record_procedure_outcome(root, SimpleNamespace(id=identity, decision='skip', workflow=None, procedure=None))
    assert outcome(store, 'procedure-pick', first['decisionId']) is None
    ws.record_procedure_outcome(root, SimpleNamespace(id=identity, decision='no_match', workflow=None, procedure=None))
    assert outcome(store, 'procedure-pick', first['decisionId'])['chosen'] == 'none'


def test_recommend_procedure_shadow_gives_no_advice(tmp_path, store, monkeypatch):
    monkeypatch.setattr(ta, 'choice', FakeLaya(procedure_answer()))
    root, identity = seal_opportunity(tmp_path)
    out = ws.recommend_procedure(root, identity, hits(2))
    assert out['mode'] == 'shadow' and out['layaAdvice'] is None


def test_recommend_procedure_errors_and_missing_snapshot(tmp_path, store, monkeypatch, capsys):
    monkeypatch.setattr(ta, 'choice', FakeLaya(procedure_answer()))
    root, identity = seal_opportunity(tmp_path)
    for bad in ([], None, [{'id': 'bad id'}, {'id': 'none'}, 'x']):
        with pytest.raises(ValueError, match='at least one valid hit'):
            ws.recommend_procedure(root, identity, bad)
    monkeypatch.setattr(sys, 'argv', ['ws', '--root', str(root), 'recommend-procedure', '--id', identity])
    monkeypatch.setattr(sys, 'stdin', SimpleNamespace(buffer=io.BytesIO(b'{"hits": []}')))
    assert ws.main() == 1 and 'at least one valid hit' in capsys.readouterr().err
    monkeypatch.setattr(sys, 'stdin', SimpleNamespace(buffer=io.BytesIO(json.dumps({'hits': hits(2)}).encode())))
    assert ws.main() == 0
    assert json.loads(capsys.readouterr().out)['mode'] == 'shadow'

    (root.parent / 'request-snapshots' / (identity + '.json')).unlink()
    assert ws.recommend_procedure(root, identity, hits(2)) == {'layaAdvice': None, 'reason': 'request_snapshot_missing'}


# ------------------------------------------------------------------ skill-fit records in advise mode

def test_skill_fit_record_accepts_advise_mode_and_keeps_the_incumbent_emitted():
    from typed_decision_testkit import ALT1, make_record
    from typed_decisions import contract
    record = make_record(1, mode='advise', choice=ALT1)  # Laya disagrees; the incumbent is still the shown payload
    assert record['mode'] == 'advise' and record['emitted'] == record['incumbent']['skillId']
    assert contract.validate_record(record) is record
    record['emitted'] = None if record['emitted'] else record['emitted']
    record['mode'] = 'unknown-mode'
    with pytest.raises(ValueError):
        contract.validate_record(record)
    schema = json.loads((ROOT / 'rhize-context-manager/schemas/typed-decision-record-v1.schema.json').read_text())
    assert schema['properties']['mode']['enum'] == ['shadow', 'advise', 'cosign']
