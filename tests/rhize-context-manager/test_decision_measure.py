"""Actual child-process evidence must not change requested check outcomes."""
import hashlib
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'rhize-context-manager/scripts'))
import decision_measure as measure


def invoke(tmp_path, command, timeout=3):
    return measure.measure(command, 'a' * 64, tmp_path / 'pilot', tmp_path / 'receipts',
                           timeout, io.BytesIO(), io.BytesIO())


def test_exit_status_and_private_output_digest(tmp_path):
    code, row = invoke(tmp_path, [sys.executable, '-c', 'import sys; print("private-data");sys.exit(7)'])
    assert code == row['exitCode'] == 7
    assert row['status'] == 'completed' and row['durationMs'] > 0
    assert row['stdoutSha256'] == hashlib.sha256(b'private-data\n').hexdigest()
    assert row['bindingStatus'] == 'unbound' and row['taskRootId'] is None
    text = next((tmp_path / 'pilot/v2/measurements').glob('*.json')).read_text()
    assert 'private-data' not in text and sys.executable not in text
    assert 'accepted' not in row and 'input_tokens' not in row


def test_capture_failure_does_not_change_check_status(tmp_path, monkeypatch):
    def fail(*a, **k):
        raise PermissionError('private path')
    monkeypatch.setattr(measure, 'locked_update', fail)
    assert invoke(tmp_path, [sys.executable, '-c', 'raise SystemExit(9)'])[0] == 9


def test_source_changes_during_check_hold_binding(tmp_path, monkeypatch):
    calls = iter([({'sessionHash': 'b' * 64}, None), ({'sessionHash': 'c' * 64}, None)])
    monkeypatch.setattr(measure, 'safe_binding', lambda *a: next(calls))
    code, row = invoke(tmp_path, [sys.executable, '-c', 'pass'])
    assert code == 0 and row['bindingStatus'] == 'unbound' and row['reasonCode'] == 'binding_changed'


def test_timeout_terminates_child_group(tmp_path):
    pidfile = tmp_path / 'child-pid'
    command = [sys.executable, '-c',
               'import subprocess,sys,time; p=subprocess.Popen([sys.executable,"-c","import time;time.sleep(30)"]);'
               'open(sys.argv[1],"w").write(str(p.pid));time.sleep(30)', str(pidfile)]
    code, row = invoke(tmp_path, command, timeout=0.5)
    assert code == 124 and row['status'] == 'timeout' and not row['outputComplete']
    assert row['durationMs'] < 3000
    child = int(pidfile.read_text())
    result = subprocess.run(['ps', '-o', 'stat=', '-p', str(child)], capture_output=True, text=True)
    assert not result.stdout.strip() or result.stdout.strip().startswith('Z')


def test_signal_exit_is_observed_without_acceptance(tmp_path):
    code, row = invoke(tmp_path, [sys.executable, '-c', 'import os,signal;os.kill(os.getpid(),signal.SIGTERM)'])
    assert code == 128 + signal.SIGTERM and row['exitCode'] == -signal.SIGTERM
    assert row['status'] == 'completed'


def test_launch_failure_remains_a_failure(tmp_path):
    code, row = invoke(tmp_path, ['/nonexistent-check-program'])
    assert code == 127 and row['status'] == 'launch_failed' and row['exitCode'] is None


def test_interrupted_wrapper_preserves_receipt_and_cleans_up(tmp_path):
    ready = tmp_path / 'ready'
    proc = subprocess.Popen([sys.executable, measure.__file__, '--root', str(tmp_path / 'pilot'),
                             '--receipts', str(tmp_path / 'receipts'), '--id', 'a' * 64,
                             '--', sys.executable, '-c',
                             'import pathlib,sys,time;pathlib.Path(sys.argv[1]).touch();time.sleep(30)',
                             str(ready)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        deadline = time.monotonic() + 5
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert ready.exists()
        proc.terminate()
        proc.communicate(timeout=5)
        assert proc.returncode == 130
        row = json.loads(next((tmp_path / 'pilot/v2/measurements').glob('*.json')).read_text())
        assert row['status'] == 'interrupted' and row['cleanupStatus'] == 'completed'
        assert not row['outputComplete']
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.communicate(timeout=5)


@pytest.mark.parametrize('timeout', [0, -1, float('nan'), float('inf'), 901])
def test_invalid_timeout_never_executes(tmp_path, timeout):
    with pytest.raises(ValueError):
        invoke(tmp_path, [sys.executable, '-c', 'raise SystemExit(99)'], timeout)


def test_bounded_forwarding_still_hashes_full_output(tmp_path, monkeypatch):
    monkeypatch.setattr(measure, 'FORWARD_LIMIT', 16)
    out = io.BytesIO()
    code, row = measure.measure([sys.executable, '-c', 'print("x"*1000)'], 'a' * 64,
                                tmp_path / 'pilot', tmp_path / 'receipts', 3, out, io.BytesIO())
    assert code == 0 and len(out.getvalue()) == 16 and row['forwardTruncated']
    assert row['stdoutSha256'] == hashlib.sha256(b'x' * 1000 + b'\n').hexdigest()


def test_broken_warning_stream_preserves_child_status(tmp_path, monkeypatch):
    class Broken:
        def write(self, value):
            raise BrokenPipeError()
    def fail(*args, **kwargs):
        raise PermissionError()
    monkeypatch.setattr(measure, 'locked_update', fail)
    monkeypatch.setattr(measure.sys, 'stderr', Broken())
    assert invoke(tmp_path, [sys.executable, '-c', 'raise SystemExit(9)'])[0] == 9


def test_backpressured_output_does_not_stall_deadline(tmp_path):
    read_fd, write_fd = os.pipe()
    try:
        with os.fdopen(write_fd, 'wb', buffering=0) as sink:
            code, row = measure.measure([sys.executable, '-c', 'print("x"*1000000)'], 'a' * 64,
                tmp_path / 'pilot', tmp_path / 'receipts', 3, sink, io.BytesIO())
        assert code == 0 and row['status'] == 'completed' and row['forwardTruncated']
        assert row['durationMs'] < 3000
        assert row['stdoutSha256'] == hashlib.sha256(b'x' * 1000000 + b'\n').hexdigest()
    finally:
        os.close(read_fd)


def test_measurement_binds_only_complete_sealed_observation(tmp_path):
    import decision_pilot as pilot
    import workflow_selection as workflow
    import workflow_task_context as context
    receipts, root = tmp_path / 'receipts', tmp_path / 'pilot'
    receipt, _ = workflow.opportunity({'prompt': 'invented task', 'session_id': 'fixture', 'turn_id': '1'},
        'codex', receipts, {'decisionPilot': {'enabled': True, 'mode': 'shadow', 'cohort': 'v2'}})
    identity = receipt['opportunityId']
    evidence = {'schemaVersion': context.SCHEMA, 'opportunityId': identity,
                'promptHash': receipt['promptHash'], 'sessionHash': receipt['sessionHash'],
                'eventKind': 'new_task', 'action': 'implement', 'domain': 'software',
                'exclusions': [], 'parentOpportunityId': None, 'preboundFamily': None}
    context.capture_context(receipts, identity, evidence,
        seal=lambda c, r: pilot.enqueue_v2(c, r, root, spawn=False, receipts=receipts))
    args = ([sys.executable, '-c', 'pass'], identity, root, receipts, 3, io.BytesIO(), io.BytesIO())
    code, row = measure.measure(*args)
    assert code == 0 and row['bindingStatus'] == 'bound'
    assert pilot.report(root, receipts)['v2Coverage']['measurements']['boundRecords'] == 1
    path = root / 'v2/observations' / (identity + '.json')
    value = json.loads(path.read_text())
    path.write_text(json.dumps({k: value[k] for k in ('opportunityId', 'sessionHash', 'sourceSha256')}))
    code, row = measure.measure(*args)
    assert code == 0 and row['bindingStatus'] == 'unbound'
