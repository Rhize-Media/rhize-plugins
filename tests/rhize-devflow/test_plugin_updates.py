"""Exercise safety decisions with disposable state; no real installed cache is mutated."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / 'rhize-devflow/scripts/plugin_updates.py'
spec = importlib.util.spec_from_file_location('plugin_updates', SCRIPT)
updates = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updates)
COMMIT = 'a' * 40


@pytest.fixture
def worker(tmp_path, monkeypatch):
    monkeypatch.setattr(updates, 'root', lambda: tmp_path)
    monkeypatch.setattr(updates, 'notice', lambda *args: None)
    monkeypatch.setattr(updates, 'owners', lambda host: [])
    updates.write(tmp_path / 'config.json', {'cli': {'codex': '/bin/codex', 'claude': '/bin/claude'}, 'python': sys.executable})
    before = {'rhize-devflow': {'version': '1.0.0', 'enabled': True, 'path': '/fake/old'}}
    after = {'rhize-devflow': {'version': '1.1.0', 'enabled': True, 'path': '/fake/new'}}
    state = {'schema': updates.SCHEMA, 'host': 'codex', 'phase': 'pending', 'targets': {'rhize-devflow': '1.1.0'},
             'commit': COMMIT, 'before': before, 'queuedAt': 1, 'quietSince': 1,
             'generation': 0, 'attempts': 0, 'after': None, 'mutationStarted': False}
    updates.write(tmp_path / 'codex/status.json', state)
    updates.write(tmp_path / 'catalog/.claude-plugin/marketplace.json', {'plugins': [{'name': 'rhize-devflow', 'version': '1.1.0'}]})
    calls = []
    def run(args, timeout=120):
        calls.append(args)
        if 'rev-parse' in args:
            return COMMIT
        if 'doctor' in args:
            return '{"healthy":true}'
        return '{}'
    monkeypatch.setattr(updates, 'run', run)
    monkeypatch.setattr(updates, 'marketplace', lambda *args: tmp_path / 'catalog')
    monkeypatch.setattr(updates, 'inventory', lambda *args: after if any('add' in a or 'update' in a for a in calls) else before)
    return tmp_path, calls, state, before, after


def status(root, host='codex'):
    return updates.read(root / host / 'status.json')


def test_success_is_verified_and_idempotent(worker):
    root, calls, *_ = worker
    updates.worker('codex')
    assert status(root)['phase'] == 'complete'
    assert status(root)['nativeSessionVerified'] is False
    assert status(root)['resolvedCommit'] == COMMIT
    assert updates.read(root / 'codex/doctor.json')['healthy'] is True
    previous = list(calls)
    updates.worker('codex')
    assert calls == previous


def test_active_host_blocks_only_itself(worker, monkeypatch):
    root, calls, *_ = worker
    monkeypatch.setattr(updates, 'owners', lambda host: [45] if host == 'codex' else [])
    updates.worker('codex')
    assert status(root)['phase'] == 'waiting_for_host'
    assert status(root)['ownerCount'] == 1
    assert not calls
    state = status(root)
    state.update(host='claude', phase='pending', quietSince=1)
    updates.write(root / 'claude/status.json', state)
    updates.worker('claude')
    assert status(root, 'claude')['phase'] == 'complete'


def test_process_starts_before_mutation(worker, monkeypatch):
    root, calls, *_ = worker
    checks = iter([[], [10]])
    monkeypatch.setattr(updates, 'owners', lambda _: next(checks))
    updates.worker('codex')
    assert status(root)['phase'] == 'waiting_for_host'
    assert not calls


def test_process_starts_after_marketplace_refresh(worker, monkeypatch):
    root, calls, *_ = worker
    checks = iter([[], [], [10]])
    monkeypatch.setattr(updates, 'owners', lambda _: next(checks))
    updates.worker('codex')
    assert status(root)['phase'] == 'held'
    assert status(root)['mutationStarted'] is False
    assert not any('add' in a for a in calls)


def test_quiet_period_is_required(worker):
    root, calls, state, *_ = worker
    state.pop('quietSince')
    updates.write(root / 'codex/status.json', state)
    updates.worker('codex')
    updates.worker('codex')
    assert status(root)['phase'] == 'settling'
    assert not calls


def test_interrupted_mutation_holds_without_replaying(worker):
    root, calls, state, *_ = worker
    state.update(phase='updating', mutationStarted=True)
    updates.write(root / 'codex/status.json', state)
    updates.worker('codex')
    updates.worker('codex')
    assert status(root)['phase'] == 'held'
    assert not calls


@pytest.mark.parametrize('kind', ['version', 'commit', 'enabled', 'doctor', 'timeout'])
def test_verification_failure_never_claims_success(worker, monkeypatch, kind):
    root, calls, state, before, after = worker
    original_run = updates.run
    if kind == 'version':
        updates.write(root / 'catalog/.claude-plugin/marketplace.json', {'plugins': []})
    elif kind == 'enabled':
        after['rhize-devflow']['enabled'] = False
    def run(args, timeout=120):
        result = original_run(args, timeout)
        if kind == 'commit' and 'rev-parse' in args:
            return 'b' * 40
        if kind == 'doctor' and 'doctor' in args:
            return '{"healthy":false}'
        if kind == 'timeout' and 'add' in args:
            raise subprocess.TimeoutExpired(args, timeout)
        return result
    monkeypatch.setattr(updates, 'run', run)
    updates.worker('codex')
    assert status(root)['phase'] == 'held'
    if kind in {'version', 'commit'}:
        assert not any('add' in a for a in calls)


def test_worker_lock_excludes_duplicate(worker):
    root, calls, *_ = worker
    with updates.locked('codex'):
        with pytest.raises(BlockingIOError):
            updates.worker('codex')
    assert not calls


def test_dependency_can_complete_then_other_host_reopens(worker, monkeypatch):
    root, calls, state, *_ = worker
    state.update(host='claude', after='codex')
    updates.write(root / 'claude/status.json', state)
    updates.worker('claude')
    assert status(root, 'claude')['phase'] == 'waiting_for_dependency'
    assert not calls
    updates.worker('codex')
    monkeypatch.setattr(updates, 'owners', lambda host: [999] if host == 'codex' else [])
    # Separate host native inventory remains at its own original version.
    before = state['before']
    after = {'rhize-devflow': {'version': '1.1.0', 'enabled': True, 'path': '/fake/new'}}
    calls.clear()
    monkeypatch.setattr(updates, 'inventory', lambda *args: after if any('update' in a and 'marketplace' not in a for a in calls) else before)
    updates.worker('claude')
    assert status(root, 'claude')['phase'] == 'complete'


@pytest.mark.parametrize('command,argv,expected', [
    ('/Applications/Claude.app/Contents/MacOS/Claude', ['Claude'], 'claude'),
    ('/app/claude.app/Contents/MacOS/claude', ['claude'], 'claude'),
    ('/bin/codex', ['codex', 'app-server'], 'codex'),
    ('/bin/codex', ['codex', 'mcp-server'], None),
    ('/bin/codex-aarch64-apple-darwin', ['codex', 'exec'], 'codex'),
    ('/bin/node', ['node', '/npm/@anthropic-ai/claude-code/cli.js', '-p'], 'claude'),
    ('/bin/node', ['node', '/npm/@openai/codex/bin/codex.js'], 'codex'),
    ('/bin/node', ['node', '/some/unrelated.js'], None),
    ('/app/Claude Helper', ['helper'], None),
])
def test_owner_classifier(command, argv, expected):
    assert updates.classify(command, argv) == expected


def test_unknown_process_state_holds(worker, monkeypatch):
    root, calls, *_ = worker
    def unavailable(_):
        raise OSError('ps_unavailable')
    monkeypatch.setattr(updates, 'owners', unavailable)
    updates.worker('codex')
    assert status(root)['phase'] == 'held'
    assert not calls


def test_guard_latches_startup_race_and_allows_real_restart(worker):
    root, _, state, *_ = worker
    payload = {'session_id': 'one', 'source': 'startup'}
    assert updates.hook('codex', 'SessionStart', payload) is None
    state.update(phase='updating', generation=42)
    updates.write(root / 'codex/status.json', state)
    assert updates.hook('codex', 'PreToolUse', payload)
    second = {'session_id': 'two', 'source': 'startup'}
    assert updates.hook('codex', 'SessionStart', second)
    state.update(phase='complete')
    updates.write(root / 'codex/status.json', state)
    assert updates.hook('codex', 'PreToolUse', payload)
    assert updates.hook('codex', 'PreToolUse', second)
    assert updates.hook('codex', 'SessionStart', payload) is None
    assert updates.hook('codex', 'PreToolUse', payload) is None


def test_failed_partial_update_holds_new_sessions(worker):
    root, _, state, *_ = worker
    state.update(phase='held', mutationStarted=True)
    updates.write(root / 'codex/status.json', state)
    assert updates.hook('codex', 'UserPromptSubmit', {'session_id': 'fresh'})
    output = updates.hook_output('PreToolUse', 'message')
    assert output['hookSpecificOutput']['permissionDecision'] == 'deny'
    assert 'continue' not in output


def test_no_worker_state_is_not_a_global_lockout(tmp_path, monkeypatch):
    monkeypatch.setattr(updates, 'root', lambda: tmp_path)
    assert updates.hook('codex', 'PreToolUse', {}) is None


def test_state_symlink_rejected(tmp_path):
    target = tmp_path / 'target'
    target.write_text('{}')
    link = tmp_path / 'link'
    link.symlink_to(target)
    with pytest.raises(ValueError):
        updates.write(link, {'clobbered': True})
    assert target.read_text() == '{}'


def test_queue_cannot_overwrite_pending_or_change_generation(worker):
    root, _, state, *_ = worker
    with pytest.raises(ValueError, match='already_pending'):
        updates.queue('codex', state['targets'], COMMIT)
    state.update(phase='complete', generation=22)
    updates.write(root / 'codex/status.json', state)
    queued = updates.queue('codex', state['targets'], COMMIT)
    assert queued['generation'] == 22


def test_invalid_targets_rejected():
    for invalid in ({}, {'../escape': '1.0.0'}, {'rhize-devflow': 'latest'}, ['rhize-devflow']):
        with pytest.raises(ValueError):
            updates.validate_targets(invalid)


def test_signed_system_uid_and_mcp_workers_do_not_block(monkeypatch):
    uid = os.getuid()
    monkeypatch.setattr(updates, 'run', lambda _: f'-2 804 /usr/sbin/distnoted\n{uid} 101 /bin/codex\n{uid} 102 /bin/claude\n')
    monkeypatch.setattr(updates, 'arguments', lambda pid: ['codex', 'mcp-server'] if pid == 101 else ['claude'])
    assert updates.owners('codex') == []
    assert updates.owners('claude') == [102]


def test_codex_disabled_state_is_never_changed_by_queue(worker):
    _, _, state, before, _ = worker
    before['rhize-devflow']['enabled'] = False
    state.update(phase='complete')
    updates.write(updates.root() / 'codex/status.json', state)
    with pytest.raises(ValueError, match='disabled_codex'):
        updates.queue('codex', state['targets'], COMMIT)


def test_installer_preserves_unrelated_hooks_and_missing_helper_denies(tmp_path, monkeypatch):
    monkeypatch.setattr(updates.sys, 'platform', 'darwin')
    monkeypatch.setattr(updates.Path, 'home', lambda: tmp_path)
    monkeypatch.setattr(updates.shutil, 'which', lambda name: '/usr/bin/' + name)
    monkeypatch.setattr(updates, 'run', lambda *args, **kwargs: '')
    monkeypatch.setattr(updates.subprocess, 'run', lambda *args, **kwargs: subprocess.CompletedProcess(args, 1, '', ''))
    unrelated = {'hooks': [{'type': 'command', 'command': 'existing-hook'}]}
    updates.write(tmp_path / '.claude/settings.json', {'custom': True, 'hooks': {'PreToolUse': [unrelated]}})
    updates.write(tmp_path / '.claude/codex/hooks.json', {'hooks': {'Stop': [unrelated]}})
    (tmp_path / '.codex').mkdir()
    (tmp_path / '.codex/hooks.json').symlink_to('../.claude/codex/hooks.json')
    updates.install()
    updates.install()
    claude = updates.read(tmp_path / '.claude/settings.json')
    assert claude['custom'] is True
    assert claude['hooks']['PreToolUse'][-1] == unrelated
    assert len(claude['hooks']['PreToolUse']) == 2
    assert (tmp_path / '.codex/hooks.json').is_symlink()
    import plistlib
    plist = plistlib.loads((tmp_path / 'Library/LaunchAgents/media.rhize.plugin-updates.codex.plist').read_bytes())
    assert plist['StartInterval'] == 15 and plist['RunAtLoad'] is True
    assert '/plugins/cache/' not in plist['ProgramArguments'][1]
    command = claude['hooks']['PreToolUse'][0]['hooks'][0]['command']
    # Restore subprocess only for the actual shell-resident missing-helper check.
    monkeypatch.undo()
    (tmp_path / '.local/share/rhize/plugin-updates/plugin_updates.py').unlink()
    result = subprocess.run(['/bin/sh', '-c', command], capture_output=True, text=True)
    assert json.loads(result.stdout)['hookSpecificOutput']['permissionDecision'] == 'deny'


def test_timeout_kills_the_worker_owned_command_group():
    with pytest.raises(subprocess.TimeoutExpired):
        updates.run([sys.executable, '-c', 'import time; time.sleep(20)'], timeout=0.05)


def test_malformed_native_envelope_still_denies():
    result = subprocess.run([sys.executable, str(SCRIPT), 'hook', 'codex', 'PreToolUse'],
                            input='[]', text=True, capture_output=True)
    assert result.returncode == 0
    assert json.loads(result.stdout)['hookSpecificOutput']['permissionDecision'] == 'deny'


def test_dependency_requires_same_reviewed_release(worker):
    root, calls, state, *_ = worker
    dependency = dict(state, host='claude', phase='complete', commit='b' * 40)
    updates.write(root / 'claude/status.json', dependency)
    state.update(after='claude')
    updates.write(root / 'codex/status.json', state)
    updates.worker('codex')
    assert status(root)['phase'] == 'waiting_for_dependency'
    assert not calls
    (root / 'claude/status.json').unlink()
    updates.worker('codex')
    assert status(root)['phase'] == 'waiting_for_dependency'


def test_repair_requires_explicit_acknowledgment_and_stays_guarded(worker):
    root, _, state, *_ = worker
    state.update(phase='held', mutationStarted=True)
    updates.write(root / 'codex/status.json', state)
    with pytest.raises(ValueError, match='requires_reconcile'):
        updates.queue('codex', state['targets'], COMMIT)
    repaired = updates.queue('codex', state['targets'], COMMIT, reconcile=True)
    assert repaired['reconciledFrom']
    assert repaired['repairRequired'] is True
    assert updates.hook('codex', 'PreToolUse', {'session_id': 'during-repair'})


def test_non_object_status_emits_native_denial(tmp_path):
    folder = tmp_path / '.local/share/rhize/plugin-updates/codex'
    folder.mkdir(parents=True)
    (folder / 'status.json').write_text('[]')
    result = subprocess.run([sys.executable, str(SCRIPT), 'hook', 'codex', 'PreToolUse'],
        input=json.dumps({'hook_event_name': 'PreToolUse', 'session_id': 'one'}),
        env=dict(os.environ, HOME=str(tmp_path)), text=True, capture_output=True)
    assert json.loads(result.stdout)['hookSpecificOutput']['permissionDecision'] == 'deny'


def test_missing_interpreter_denies_even_when_helper_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(updates.sys, 'platform', 'darwin')
    monkeypatch.setattr(updates.Path, 'home', lambda: tmp_path)
    monkeypatch.setattr(updates.shutil, 'which', lambda name: str(tmp_path / 'removed-python') if name == 'python3' else '/usr/bin/' + name)
    monkeypatch.setattr(updates, 'run', lambda *args, **kwargs: '')
    monkeypatch.setattr(updates.subprocess, 'run', lambda *args, **kwargs: subprocess.CompletedProcess(args, 1, '', ''))
    updates.install()
    command = updates.read(tmp_path / '.codex/hooks.json')['hooks']['PreToolUse'][0]['hooks'][0]['command']
    assert (tmp_path / '.local/share/rhize/plugin-updates/plugin_updates.py').exists()
    monkeypatch.undo()
    result = subprocess.run(['/bin/sh', '-c', command], capture_output=True, text=True)
    assert json.loads(result.stdout)['hookSpecificOutput']['permissionDecision'] == 'deny'
