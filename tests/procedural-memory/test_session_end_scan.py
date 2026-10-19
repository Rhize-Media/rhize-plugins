"""Native completion evidence and lossless candidate-queue updates."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import threading

import pytest

HOOKS = Path(__file__).resolve().parents[2] / 'procedural-memory/hooks'
SCAN = HOOKS / 'session-end-scan.py'


def candidate(identity='exec-pass', session='native-session', **extra):
    return {'id': identity, 'session_id': session, 'status': 'pending', 'command': 'pytest', **extra}


def completed(identity='exec-pass', status='completed', code=0, session='native-session'):
    return {'type': 'event_msg', 'payload': {'type': 'item_completed', 'thread_id': session,
            'item': {'type': 'CommandExecution', 'id': identity, 'status': status, 'exit_code': code}}}


def native(*records, session='native-session'):
    return [{'type': 'session_meta', 'payload': {'id': session}}, *records]


def run_scan(tmp_path, records, entries=None, raw=None):
    transcript = tmp_path / 'rollout.jsonl'
    transcript.write_text('\n'.join(json.dumps(x) for x in records) + '\n')
    queue = tmp_path / 'queue.jsonl'
    if raw is not None:
        queue.write_bytes(raw)
    elif not queue.exists():
        queue.write_text(''.join(json.dumps(x) + '\n' for x in (entries or [candidate()])))
    payload = {'session_id': 'native-session', 'transcript_path': str(transcript)}
    result = subprocess.run([sys.executable, str(SCAN)], input=json.dumps(payload), text=True,
                            capture_output=True, env={**os.environ, 'PROCEDURAL_MEMORY_CANDIDATE_QUEUE': str(queue)})
    assert result.returncode == 0, result.stderr
    return queue, result


@pytest.mark.parametrize(('status', 'code', 'expected'), [
    ('completed', 0, 'surfaced'), ('failed', 1, 'rejected'), ('completed', 7, 'rejected'),
    ('failed', 0, 'rejected'), ('in_progress', 0, 'pending'), ('completed', None, 'pending'),
    ('completed', False, 'pending'), ('completed', '0', 'pending'),
])
def test_codex_requires_terminal_status_and_explicit_integer_exit(tmp_path, status, code, expected):
    queue, result = run_scan(tmp_path, native(completed(status=status, code=code)))
    assert json.loads(queue.read_text())['status'] == expected
    assert ('promotion candidates' in result.stdout) == (expected == 'surfaced')


def test_success_failure_missing_and_replay(tmp_path):
    records = native(completed(), completed('exec-fail', 'failed', 1))
    queue, _ = run_scan(tmp_path, records, [candidate(), candidate('exec-fail'), candidate('exec-missing')])
    assert [json.loads(l)['status'] for l in queue.read_text().splitlines()] == ['surfaced', 'rejected', 'pending']
    before = queue.read_bytes()
    _, replay = run_scan(tmp_path, records)
    assert queue.read_bytes() == before and replay.stdout == ''


@pytest.mark.parametrize('records', [
    native(completed(session='other-session')), native(completed(), session='other-session'),
    [completed()], native({'type': 'response_item', 'payload': {'text': 'exec-pass completed exit_code 0'}}),
    native(completed(), completed(code=1)),
])
def test_foreign_unbound_quoted_conflicting_evidence_stays_pending(tmp_path, records):
    queue, result = run_scan(tmp_path, records)
    assert json.loads(queue.read_text())['status'] == 'pending' and result.stdout == ''


def test_claude_result_and_edited_files_still_work(tmp_path):
    records = [{'message': {'content': [
        {'type': 'tool_use', 'name': 'Write', 'input': {'file_path': '/workspace/example.py'}},
        {'type': 'tool_result', 'tool_use_id': 'exec-pass', 'is_error': False}]}}]
    queue, result = run_scan(tmp_path, records)
    assert json.loads(queue.read_text())['status'] == 'surfaced'
    assert '/workspace/example.py' in result.stdout


def test_opaque_and_unrelated_bytes_survive(tmp_path):
    opaque = b'{broken json\n\n42\n[1,2]\n'
    unrelated = b'{ "id": "other", "session_id": "other", "status": "pending" }\n'
    raw = opaque + json.dumps(candidate()).encode() + b'\n' + unrelated
    queue, _ = run_scan(tmp_path, native(completed()), raw=raw)
    assert queue.read_bytes().startswith(opaque) and queue.read_bytes().endswith(unrelated)
    assert json.loads(queue.read_bytes().splitlines()[4])['status'] == 'surfaced'


def test_duplicate_queue_identity_is_held(tmp_path):
    entries = [candidate(command='pytest one'), candidate(command='pytest two')]
    queue, result = run_scan(tmp_path, native(completed()), entries)
    assert all(json.loads(l)['status'] == 'pending' for l in queue.read_text().splitlines())
    assert result.stdout == ''


def test_symlinked_queue_is_never_replaced(tmp_path):
    target = tmp_path / 'real.jsonl'
    raw = json.dumps(candidate()) + '\n'
    target.write_text(raw)
    (tmp_path / 'queue.jsonl').symlink_to(target)
    _, result = run_scan(tmp_path, native(completed()))
    assert target.read_text() == raw and result.stdout == ''


def test_append_waits_for_atomic_update_without_losing_data(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(HOOKS))
    spec = importlib.util.spec_from_file_location('scan_test', SCAN)
    scan = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scan)
    import candidate_queue
    queue = tmp_path / 'queue.jsonl'
    queue.write_text(json.dumps(candidate()) + '\n{malformed preserved\n')
    entered, release, appended = threading.Event(), threading.Event(), threading.Event()
    replace = os.replace

    def paused_replace(src, dest):
        entered.set()
        assert release.wait(3)
        replace(src, dest)

    monkeypatch.setattr(scan.os, 'replace', paused_replace)
    updater = threading.Thread(target=scan.write_queue_atomic, args=(str(queue), [candidate(status='surfaced')]))
    updater.start()
    assert entered.wait(3)

    def append():
        candidate_queue.append(str(queue), (json.dumps(candidate('new')) + '\n').encode())
        appended.set()

    writer = threading.Thread(target=append)
    writer.start()
    assert not appended.wait(0.1)
    release.set()
    updater.join(3)
    writer.join(3)
    assert not updater.is_alive() and not writer.is_alive() and appended.is_set()
    lines = queue.read_bytes().splitlines()
    assert json.loads(lines[0])['status'] == 'surfaced'
    assert lines[1] == b'{malformed preserved' and json.loads(lines[2])['id'] == 'new'
