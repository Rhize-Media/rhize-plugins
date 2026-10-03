"""Prospective private request capture: bindings, redaction and no authority."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import uuid

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / 'rhize-context-manager/scripts'
sys.path.insert(0, str(SCRIPTS))
from workflow_selection import opportunity, decide, digest
from workflow_task_context import capture_context, SCHEMA as CONTEXT_SCHEMA
from workflow_context_packet import (capture_request_snapshot, capture_request_context,
                                     load_request_snapshot, load_request_context, native_observer)


def make(tmp_path, text='Implement a database fix', session='one', turn='one'):
    root = tmp_path / 'receipts'
    payload = {'prompt': text, 'session_id': session, 'turn_id': turn}
    receipt, fresh = opportunity(payload, 'claude', root,
                                 {'decisionPilot': {'enabled': True, 'mode': 'shadow', 'cohort': 'v2'}})
    assert fresh
    return root, payload, receipt


def context(root, receipt):
    return capture_context(root, receipt['opportunityId'], {
        'schemaVersion': CONTEXT_SCHEMA, 'opportunityId': receipt['opportunityId'],
        'sessionHash': receipt['sessionHash'], 'promptHash': receipt['promptHash'],
        'eventKind': 'new_task', 'action': 'implement', 'domain': 'software',
        'exclusions': [], 'parentOpportunityId': None, 'preboundFamily': None})


def test_snapshot_redacts_before_storage_and_is_immutable(tmp_path):
    root, payload, receipt = make(tmp_path, 'Implement a fix\npassword: secret-super-sensitive')
    first = capture_request_snapshot(root, receipt, payload)
    assert 'secret-super-sensitive' not in first['originalRequest']
    assert first['promptHash'] == digest(payload['prompt'])
    assert first['sanitizedRequestSha256'] == digest(first['originalRequest'])
    path = root.parent / 'request-snapshots' / (receipt['opportunityId'] + '.json')
    assert 'secret-super-sensitive' not in path.read_text()
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700
    assert capture_request_snapshot(root, receipt, payload) == first
    assert load_request_snapshot(root, receipt['opportunityId']) == first
    context(root, receipt)
    assert capture_request_snapshot(root, receipt, payload) == first
    assert receipt['selection'] is None and receipt['classification']['eligible'] is None


def test_capture_cannot_backfill_context_or_decision(tmp_path):
    root, payload, receipt = make(tmp_path)
    context(root, receipt)
    with pytest.raises(ValueError, match='post_decision'):
        capture_request_snapshot(root, receipt, payload)
    root, payload, receipt = make(tmp_path, turn='two')
    decide(root, SimpleNamespace(id=receipt['opportunityId'], decision='no_match', workflow=None,
                                variant=None, reason='no_suitable_workflow'))
    with pytest.raises(ValueError, match='post_decision'):
        capture_request_snapshot(root, receipt, payload)


def test_corrupt_symlink_and_binding_changes_never_become_missing(tmp_path):
    root, payload, receipt = make(tmp_path)
    assert load_request_snapshot(root, receipt['opportunityId']) is None
    capture_request_snapshot(root, receipt, payload)
    path = root.parent / 'request-snapshots' / (receipt['opportunityId'] + '.json')
    value = json.loads(path.read_text()); value['originalRequest'] = 'tampered'
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match='binding_mismatch'):
        load_request_snapshot(root, receipt['opportunityId'])
    with pytest.raises(ValueError):
        capture_request_snapshot(root, receipt, payload)
    path.unlink(); path.symlink_to(tmp_path / 'nonexistent')
    with pytest.raises(OSError):
        load_request_snapshot(root, receipt['opportunityId'])


def test_explicit_prior_requests_bind_without_changing_task_root(tmp_path):
    root, payload, prior = make(tmp_path, 'Repair auth bug; keep database schema unchanged')
    capture_request_snapshot(root, prior, payload); context(root, prior)
    root, payload, current = make(tmp_path, 'Proceed with implementation', turn='two')
    capture_request_snapshot(root, current, payload)
    capture_request_context(root, current['opportunityId'], [prior['opportunityId']])
    captured = context(root, current)
    assert captured['taskRootId'] == current['opportunityId']
    loaded = load_request_context(root, current['opportunityId'])
    assert loaded['preceding'][0]['originalRequest'] == 'Repair auth bug; keep database schema unchanged'
    assert loaded['contextSha256'] and loaded['current']['promptHash'] == current['promptHash']
    capture_request_context(root, current['opportunityId'], [prior['opportunityId']])
    with pytest.raises(ValueError):
        capture_request_context(root, current['opportunityId'], [prior['opportunityId']] * 2)


def test_links_reject_unbound_other_session_and_post_context(tmp_path):
    root, payload, prior = make(tmp_path)
    capture_request_snapshot(root, prior, payload); context(root, prior)
    root, payload, current = make(tmp_path, turn='two', session='other')
    capture_request_snapshot(root, current, payload)
    with pytest.raises(ValueError, match='binding_mismatch'):
        capture_request_context(root, current['opportunityId'], [prior['opportunityId']])
    root, payload, current = make(tmp_path, turn='three')
    capture_request_snapshot(root, current, payload); context(root, current)
    with pytest.raises(ValueError, match='post_decision'):
        capture_request_context(root, current['opportunityId'], [prior['opportunityId']])


def test_native_observer_requires_launcher_and_verified_native_source(tmp_path, monkeypatch):
    monkeypatch.setenv('HOME', str(tmp_path))
    cwd = tmp_path / '.local/share/ecc-homunculus'; cwd.mkdir(parents=True)
    import re
    project = tmp_path / '.claude/projects' / re.sub(r'[^a-zA-Z0-9]', '-', str(cwd))
    project.mkdir(parents=True)
    session = str(uuid.uuid4()); path = project / (session + '.jsonl')
    payload = {'session_id': session, 'cwd': str(cwd), 'transcript_path': str(path), 'prompt': 'Read observations'}
    path.write_text(json.dumps({'type': 'user', 'sessionId': session, 'cwd': str(cwd),
                               'isSidechain': False, 'message': {'content': payload['prompt']}}) + '\n')
    env = {'ECC_SKIP_OBSERVE': '1', 'ECC_HOOK_PROFILE': 'minimal'}
    assert native_observer(payload, 'claude', env)
    assert not native_observer(payload, 'codex', env)
    assert not native_observer(payload, 'claude', {})
    assert not native_observer({**payload, 'prompt': 'A user quoting the observer request'}, 'claude', env)
    assert not native_observer({**payload, 'transcript_path': str(tmp_path / path.name)}, 'claude', env)
    source = tmp_path / 'actual'; path.rename(source); path.symlink_to(source)
    assert not native_observer(payload, 'claude', env)


def test_request_budget_truncates_after_redaction(tmp_path):
    root, payload, receipt = make(tmp_path, 'Investigate ' * 700 + '\npassword: super-secret-tail')
    value = capture_request_snapshot(root, receipt, payload)
    assert value['requestTruncated'] and len(value['originalRequest']) < 6600
    assert 'super-secret-tail' not in json.dumps(value)


def test_snapshot_seal_rejects_post_observation_and_context_time(tmp_path):
    root, payload, receipt = make(tmp_path)
    snapshot = capture_request_snapshot(root, receipt, payload)
    captured = datetime.fromisoformat(snapshot['capturedAt']).timestamp()
    observations = root.parent / 'pilot/v2/observations'; observations.mkdir(parents=True)
    (observations / (receipt['opportunityId'] + '.json')).write_text(json.dumps({'createdAt': captured - 1}))
    with pytest.raises(ValueError, match='post_decision'):
        load_request_snapshot(root, receipt['opportunityId'])


def test_mutated_context_link_cannot_fallback_to_current_request(tmp_path):
    root, payload, prior = make(tmp_path)
    capture_request_snapshot(root, prior, payload); context(root, prior)
    root, payload, current = make(tmp_path, turn='two')
    capture_request_snapshot(root, current, payload)
    capture_request_context(root, current['opportunityId'], [prior['opportunityId']])
    path = root.parent / 'request-context' / (current['opportunityId'] + '.json')
    value = json.loads(path.read_text()); value['links'][0]['snapshotSha256'] = '0' * 64
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match='binding_mismatch'):
        load_request_context(root, current['opportunityId'])


@pytest.mark.parametrize('suffix,accepted', [('projects/0123456789ab', True),
                                           ('projects/not-a-fingerprint', False),
                                           ('arbitrary/0123456789ab', False)])
def test_observer_project_scope_is_exact(tmp_path, monkeypatch, suffix, accepted):
    import re
    monkeypatch.setenv('HOME', str(tmp_path))
    cwd = tmp_path / '.local/share/ecc-homunculus' / suffix; cwd.mkdir(parents=True)
    project = tmp_path / '.claude/projects' / re.sub(r'[^a-zA-Z0-9]', '-', str(cwd)); project.mkdir(parents=True)
    session = str(uuid.uuid4()); path = project / (session + '.jsonl')
    payload = {'session_id': session, 'cwd': str(cwd), 'transcript_path': str(path), 'prompt': 'Read observations'}
    path.write_text(json.dumps({'type': 'user', 'sessionId': session, 'cwd': str(cwd),
                               'isSidechain': False, 'message': {'content': payload['prompt']}}) + '\n')
    assert native_observer(payload, 'claude', {'ECC_SKIP_OBSERVE': '1', 'ECC_HOOK_PROFILE': 'minimal'}) is accepted


def test_snapshot_parent_symlink_is_refused(tmp_path):
    root, payload, receipt = make(tmp_path)
    capture_request_snapshot(root, receipt, payload)
    original = root.parent / 'request-snapshots'
    moved = tmp_path / 'moved'; original.rename(moved); original.symlink_to(moved, target_is_directory=True)
    with pytest.raises(ValueError, match='source_invalid'):
        load_request_snapshot(root, receipt['opportunityId'])


@pytest.mark.parametrize('flags', [{'isSidechain': True}, {'isMeta': True}])
def test_observer_source_rejects_sidechain_or_meta_record(tmp_path, monkeypatch, flags):
    import re
    monkeypatch.setenv('HOME', str(tmp_path))
    cwd = tmp_path / '.local/share/ecc-homunculus'; cwd.mkdir(parents=True)
    project = tmp_path / '.claude/projects' / re.sub(r'[^a-zA-Z0-9]', '-', str(cwd)); project.mkdir(parents=True)
    session = str(uuid.uuid4()); path = project / (session + '.jsonl')
    payload = {'session_id': session, 'cwd': str(cwd), 'transcript_path': str(path), 'prompt': 'Read observations'}
    path.write_text(json.dumps({'type': 'user', 'sessionId': session, 'cwd': str(cwd), 'isSidechain': False,
                               'message': {'content': payload['prompt']}, **flags}) + '\n')
    assert not native_observer(payload, 'claude', {'ECC_SKIP_OBSERVE': '1', 'ECC_HOOK_PROFILE': 'minimal'})
