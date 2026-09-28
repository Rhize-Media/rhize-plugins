"""Invented enum fixtures; not human labels or measured task benefit."""
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / 'rhize-context-manager/scripts'
sys.path.insert(0, str(SCRIPTS))
from workflow_selection import opportunity, decide, hook_message, digest
from workflow_task_context import (SCHEMA, capture_context, capture_consultation, load_context,
                                   load_consultation, eligibility, source_binding, task_root,
                                   read_context_evidence, hold_context)


def make(tmp_path, turn='one', session='fixture', host='codex', **changes):
    receipts = tmp_path / 'receipts'
    receipt, _ = opportunity({'prompt': '<task-notification> private.example/article </task-notification>',
                             'session_id': session, 'turn_id': turn, 'event_kind': 'trusted_observer'},
                            host, receipts, {'decisionPilot': {'enabled': True, 'mode': 'shadow', 'cohort': 'v2'}})
    data = {'schemaVersion': SCHEMA, 'opportunityId': receipt['opportunityId'],
            'promptHash': receipt['promptHash'], 'sessionHash': receipt['sessionHash'],
            'eventKind': 'new_task', 'action': 'implement', 'domain': 'software',
            'exclusions': [], 'parentOpportunityId': None, 'preboundFamily': None, **changes}
    return receipts, receipt, data


def choose(receipts, receipt):
    return decide(receipts, SimpleNamespace(id=receipt['opportunityId'], decision='no_match', workflow=None,
                                           variant=None, reason='no_suitable_workflow'))


def test_explicit_context_preserves_identity_and_unknown_native_origin(tmp_path):
    receipts, receipt, data = make(tmp_path)
    path = receipts / (receipt['opportunityId'] + '.json')
    before = path.read_bytes()
    assert load_context(receipts, receipt['opportunityId']) is None
    captured = capture_context(receipts, receipt['opportunityId'], data)
    assert captured['basis'] == 'agent_asserted' and captured['nativeOrigin'] == 'unknown'
    assert eligibility(captured) == {'eligible': True, 'reason': 'new_routing_decision'}
    assert path.read_bytes() == before
    assert 'private.example' not in json.dumps(captured) and 'trusted_observer' not in json.dumps(captured)
    assert load_context(receipts, receipt['opportunityId']) == captured
    assert (tmp_path / 'task-context' / path.name).stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize('patch', [
    {'freeText': 'private.example'}, {'action': ['create']}, {'domain': 'https://private.example'},
    {'exclusions': ['unknown']}, {'parentOpportunityId': '../../private'},
    {'promptHash': '0' * 64}, {'sessionHash': '0' * 64}, {'nativeOrigin': 'trusted'},
])
def test_invalid_context_retained_as_hold_without_private_input(tmp_path, patch):
    receipts, receipt, data = make(tmp_path)
    with pytest.raises(ValueError):
        capture_context(receipts, receipt['opportunityId'], {**data, **patch})
    hold = tmp_path / 'task-context-holds' / (receipt['opportunityId'] + '.json')
    assert hold.exists() and 'private.example' not in hold.read_text()
    assert choose(receipts, receipt)['selection']['decision'] == 'no_match'


def test_retry_after_decision_is_idempotent_but_conflicting_retry_holds(tmp_path):
    receipts, receipt, data = make(tmp_path, exclusions=['deployment', 'publishing'])
    original = capture_context(receipts, receipt['opportunityId'], data)
    choose(receipts, receipt)
    reordered = {**data, 'exclusions': ['publishing', 'deployment', 'deployment']}
    assert capture_context(receipts, receipt['opportunityId'], reordered) == original
    with pytest.raises(ValueError, match='duplicate_context'):
        capture_context(receipts, receipt['opportunityId'], {**data, 'action': 'review'})
    with pytest.raises(ValueError, match='duplicate_context'):
        load_context(receipts, receipt['opportunityId'])
    saved = json.loads((tmp_path / 'task-context' / (receipt['opportunityId'] + '.json')).read_text())
    assert saved == original


def test_context_after_selection_is_held_and_missing_never_blocks_arm_a(tmp_path):
    receipts, receipt, data = make(tmp_path)
    assert choose(receipts, receipt)['contextCaptureStatus'] == 'missing'
    with pytest.raises(ValueError, match='post_decision_context'):
        capture_context(receipts, receipt['opportunityId'], data)


def test_context_after_existing_consultation_is_held(tmp_path):
    receipts, receipt, data = make(tmp_path)
    consultation = tmp_path / 'consultations' / (receipt['opportunityId'] + '.json')
    consultation.parent.mkdir(); consultation.write_text('{}')
    with pytest.raises(ValueError, match='post_decision_context'):
        capture_context(receipts, receipt['opportunityId'], data)


def test_consultation_distinct_from_no_match_and_not_in_context(tmp_path):
    receipts, receipt, data = make(tmp_path)
    evidence = tmp_path / 'recall.json'; evidence.write_text('{"references": []}')
    with pytest.raises(ValueError, match='context_must_precede'):
        capture_consultation(receipts, receipt['opportunityId'], 'general', evidence)
    original = capture_context(receipts, receipt['opportunityId'], data)
    consulted = capture_consultation(receipts, receipt['opportunityId'], 'general', evidence)
    assert consulted['basis'] == 'operator_reported'
    choose(receipts, receipt)
    assert load_consultation(receipts, receipt['opportunityId'])['kind'] == 'general'
    assert load_context(receipts, receipt['opportunityId']) == original
    assert capture_consultation(receipts, receipt['opportunityId'], 'general', evidence) == consulted
    with pytest.raises(ValueError, match='immutable'):
        capture_consultation(receipts, receipt['opportunityId'], 'none', evidence)


def test_source_revalidation_detects_mutated_prompt_binding(tmp_path):
    receipts, receipt, data = make(tmp_path)
    capture_context(receipts, receipt['opportunityId'], data)
    receipt['promptHash'] = '1' * 64
    (receipts / (receipt['opportunityId'] + '.json')).write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match='binding_mismatch'):
        load_context(receipts, receipt['opportunityId'])


def test_continuation_references_parent_without_new_routing(tmp_path):
    receipts, parent, parent_data = make(tmp_path, action='revise', domain='content', exclusions=['publishing'])
    parent_context = capture_context(receipts, parent['opportunityId'], parent_data)
    _, child, child_data = make(tmp_path, turn='two', eventKind='continuation', action='revise', domain='content',
                               exclusions=['publishing'], parentOpportunityId=parent['opportunityId'])
    child_context = capture_context(receipts, child['opportunityId'], child_data)
    assert eligibility(child_context)['eligible'] is False
    assert task_root(receipts, child['opportunityId']) == parent['opportunityId']
    assert child_context['taskRootSourceBindingSha256'] == source_binding(parent)
    assert child_context['action'] == parent_context['action']


@pytest.mark.parametrize('case', ['different_session', 'different_host', 'future', 'missing_context', 'conflict', 'self'])
def test_parent_invalid_links_are_held(tmp_path, case):
    receipts, parent, data = make(tmp_path)
    if case != 'missing_context':
        capture_context(receipts, parent['opportunityId'], data)
    _, child, child_data = make(tmp_path, turn='two', session='other' if case == 'different_session' else 'fixture',
                               host='claude' if case == 'different_host' else 'codex', eventKind='continuation',
                               parentOpportunityId=parent['opportunityId'])
    if case == 'future':
        parent['observedAt'] = '2099-01-01T00:00:00+00:00'
        (receipts / (parent['opportunityId'] + '.json')).write_text(json.dumps(parent))
    elif case == 'conflict':
        child_data['action'] = 'review'
    elif case == 'self':
        child_data['parentOpportunityId'] = child['opportunityId']
    with pytest.raises(ValueError):
        capture_context(receipts, child['opportunityId'], child_data)
    assert (tmp_path / 'task-context-holds' / (child['opportunityId'] + '.json')).exists()


def test_depth_budget_and_missing_parent(tmp_path):
    receipts, parent, data = make(tmp_path)
    capture_context(receipts, parent['opportunityId'], data)
    for number in range(1, 32):
        _, child, context = make(tmp_path, turn=str(number), eventKind='continuation', parentOpportunityId=parent['opportunityId'])
        capture_context(receipts, child['opportunityId'], context)
        parent = child
    _, child, context = make(tmp_path, turn='too-deep', eventKind='continuation', parentOpportunityId=parent['opportunityId'])
    with pytest.raises(ValueError, match='ancestry'):
        capture_context(receipts, child['opportunityId'], context)
    _, child, context = make(tmp_path, turn='missing', eventKind='continuation')
    with pytest.raises(ValueError, match='missing_parent'):
        capture_context(receipts, child['opportunityId'], context)


def test_intent_pairs_and_exclusions_are_distinct(tmp_path):
    cases = [('implement', 'software', ['content_creation']), ('create', 'content', []),
             ('handoff', 'general', []), ('revise', 'content', [])]
    contexts = []
    for n, (action, domain, exclusions) in enumerate(cases):
        receipts, receipt, data = make(tmp_path, turn=str(n), action=action, domain=domain, exclusions=exclusions)
        contexts.append(capture_context(receipts, receipt['opportunityId'], data))
    assert len({c['contextSha256'] for c in contexts}) == 4


@pytest.mark.parametrize('kind,expected', [('new_task', True), ('changed_intent', True), ('unknown', None),
                                        ('status', False), ('approval', False), ('scheduled', False),
                                        ('background_observer', False), ('summarizer', False), ('worker_handback', False)])
def test_eligibility_is_explicit_not_prompt_classification(tmp_path, kind, expected):
    receipts, receipt, data = make(tmp_path, eventKind=kind)
    result = capture_context(receipts, receipt['opportunityId'], data)
    assert eligibility(result)['eligible'] is expected


def test_v1_cannot_be_retroactively_recoded(tmp_path):
    receipt, _ = opportunity({'prompt': 'review fixture', 'session_id': 's'}, 'codex', tmp_path / 'receipts', {})
    before = (tmp_path / 'receipts' / (receipt['opportunityId'] + '.json')).read_bytes()
    with pytest.raises(ValueError, match='requires_v2'):
        capture_context(tmp_path / 'receipts', receipt['opportunityId'], {})
    assert (tmp_path / 'receipts' / (receipt['opportunityId'] + '.json')).read_bytes() == before


def test_seal_callback_precedes_selection_and_failures_hold(tmp_path):
    receipts, receipt, data = make(tmp_path)
    def seal(context, original):
        assert original['selection'] is None
        with pytest.raises(BlockingIOError):
            choose(receipts, receipt)
        raise RuntimeError('fixture seal failure')
    with pytest.raises(RuntimeError):
        capture_context(receipts, receipt['opportunityId'], data, seal=seal)
    assert choose(receipts, receipt)['contextCaptureStatus'] == 'held'
    def must_not_retry(*args):
        pytest.fail('failed request construction must never be retried')
    with pytest.raises(ValueError, match='held'):
        capture_context(receipts, receipt['opportunityId'], data, seal=must_not_retry)


def test_missing_context_file_is_diagnostic_and_correctable(tmp_path):
    receipts, receipt, data = make(tmp_path)
    missing = tmp_path / 'wrong-path.json'
    with pytest.raises(FileNotFoundError):
        read_context_evidence(receipts, receipt['opportunityId'], missing)
    assert not (tmp_path / 'task-context-holds').exists()
    diagnostic = json.loads((tmp_path / 'task-context-diagnostics' / (receipt['opportunityId'] + '.json')).read_text())
    assert diagnostic['sourceBindingSha256'] == source_binding(receipt)
    assert str(missing) not in json.dumps(diagnostic)
    missing.write_text(json.dumps(data))
    value = read_context_evidence(receipts, receipt['opportunityId'], missing)
    assert capture_context(receipts, receipt['opportunityId'], value)['action'] == 'implement'


def test_malformed_assertion_remains_held(tmp_path):
    receipts, receipt, data = make(tmp_path)
    malformed = tmp_path / 'bad.json'; malformed.write_text('{malformed')
    with pytest.raises(ValueError):
        read_context_evidence(receipts, receipt['opportunityId'], malformed)
    with pytest.raises(ValueError, match='held'):
        capture_context(receipts, receipt['opportunityId'], data)


def test_context_storage_failure_is_diagnostic_until_request_sealing(tmp_path, monkeypatch):
    import workflow_task_context as context_module
    receipts, receipt, data = make(tmp_path)
    digest_fn, read_fn, lock_fn = context_module._tools()
    failed = False
    def temporarily_unavailable(root, *args):
        nonlocal failed
        if Path(root).name == 'task-context' and not failed:
            failed = True
            raise PermissionError('fixture unavailable')
        return lock_fn(root, *args)
    monkeypatch.setattr(context_module, '_tools', lambda: (digest_fn, read_fn, temporarily_unavailable))
    with pytest.raises(PermissionError):
        capture_context(receipts, receipt['opportunityId'], data)
    assert not (tmp_path / 'task-context-holds').exists()
    assert capture_context(receipts, receipt['opportunityId'], data)['action'] == 'implement'


@pytest.mark.parametrize('kind', ['fifo', 'symlink', 'device'])
def test_consult_rejects_nonregular_evidence_without_blocking(tmp_path, kind):
    import time
    receipts, receipt, data = make(tmp_path)
    capture_context(receipts, receipt['opportunityId'], data)
    evidence = tmp_path / 'invalid-evidence'
    if kind == 'fifo':
        os.mkfifo(evidence)
    elif kind == 'symlink':
        target = tmp_path / 'target'; target.write_text('fixture')
        evidence.symlink_to(target)
    else:
        evidence = Path('/dev/null')
    start = time.monotonic()
    with pytest.raises(OSError):
        capture_consultation(receipts, receipt['opportunityId'], 'general', evidence)
    assert time.monotonic() - start < 0.5
    good = tmp_path / 'regular'; good.write_text('fixture recall')
    assert capture_consultation(receipts, receipt['opportunityId'], 'general', good)['kind'] == 'general'


def test_changed_intent_starts_fresh_root_and_rejects_parent(tmp_path):
    receipts, parent, data = make(tmp_path)
    capture_context(receipts, parent['opportunityId'], data)
    _, child, changed = make(tmp_path, turn='changed', eventKind='changed_intent', action='review')
    assert capture_context(receipts, child['opportunityId'], changed)['taskRootId'] == child['opportunityId']
    _, child, changed = make(tmp_path, turn='bad-change', eventKind='changed_intent',
                            parentOpportunityId=parent['opportunityId'])
    with pytest.raises(ValueError, match='parent_requires_continuation'):
        capture_context(receipts, child['opportunityId'], changed)


def test_ancestor_hold_invalidates_inherited_context_but_not_arm_a(tmp_path):
    receipts, parent, data = make(tmp_path)
    capture_context(receipts, parent['opportunityId'], data)
    _, child, continuation = make(tmp_path, turn='child', eventKind='continuation',
                                 parentOpportunityId=parent['opportunityId'])
    capture_context(receipts, child['opportunityId'], continuation)
    with pytest.raises(ValueError, match='duplicate_context'):
        capture_context(receipts, parent['opportunityId'], {**data, 'action': 'review'})
    with pytest.raises(ValueError, match='duplicate_context'):
        load_context(receipts, child['opportunityId'])
    assert choose(receipts, child)['selection']['decision'] == 'no_match'


def test_hold_saturation_stops_rewriting(tmp_path):
    receipts, receipt, _ = make(tmp_path)
    for number in range(65):
        hold_context(receipts, receipt['opportunityId'], 'duplicate_context', digest(str(number)))
    path = tmp_path / 'task-context-holds' / (receipt['opportunityId'] + '.json')
    before = path.stat().st_mtime_ns
    hold_context(receipts, receipt['opportunityId'], 'duplicate_context', digest('another'))
    assert path.stat().st_mtime_ns == before


def test_v2_checkpoint_orders_context_before_recall(tmp_path):
    _, receipt, _ = make(tmp_path)
    message = hook_message(receipt)
    assert message.index(' context --id ') < message.index('procedural-memory:procedural-memory recall')
    assert 'decision_measure.py' in message and 'native origin unknown' in message


def test_v2_hook_never_falls_back_to_keyword_shadow(tmp_path):
    import os
    import subprocess
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'schemaVersion': 1, 'enabled': True,
                                 'decisionPilot': {'enabled': True, 'mode': 'shadow', 'cohort': 'v2'}}))
    result = subprocess.run([sys.executable, str(SCRIPTS / 'workflow_selection.py'), '--root',
                             str(tmp_path / 'receipts'), 'hook', '--host', 'codex', '--config', str(config)],
                            input=json.dumps({'prompt': 'article project workflow', 'session_id': 'fixture', 'turn_id': 'one'}),
                            capture_output=True, text=True, timeout=10,
                            env={**os.environ, 'RHIZE_LAYA_WORKFLOW_SHADOW': '1'})
    assert result.returncode == 0
    assert ' context --id ' in result.stdout
    assert len(list((tmp_path / 'receipts').glob('*.json'))) == 1
    assert not (tmp_path / 'pilot').exists() and not (tmp_path / 'typed-shadow').exists()
