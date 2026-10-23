"""Native update safety: disposable package metadata and real manifest commands only."""
import json
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest

PLUGIN = Path(__file__).resolve().parents[2] / 'rhize-devflow'
SCRIPT = PLUGIN / 'scripts/plugin_update_guard.py'


def run_guard(tmp_path, event='PreToolUse', command='git status --short', session='session-a'):
    env = dict(os.environ, HOME=str(tmp_path), XDG_DATA_HOME=str(tmp_path / 'data'))
    payload = {'session_id': session, 'hook_event_name': event, 'tool_name': 'exec_command',
               'tool_input': {'cmd': command}, 'cwd': str(tmp_path)}
    if event == 'SessionStart':
        payload['source'] = 'startup'
    return subprocess.run([sys.executable, str(SCRIPT), event], input=json.dumps(payload), env=env,
                          text=True, capture_output=True, timeout=5)


def denied(result):
    assert result.returncode == 0, result.stderr
    value = json.loads(result.stdout)
    assert value['hookSpecificOutput']['permissionDecision'] == 'deny'
    assert 'restart' in value['hookSpecificOutput']['permissionDecisionReason'].lower()


@pytest.mark.parametrize('command', [
    'claude plugin update rhize-devflow',
    'codex plugin add rhize-context-manager@rhize-plugins --json',
    'claude plugin marketplace update rhize-plugins',
    'codex plugin marketplace upgrade rhize-plugins --json',
    'claude plugin update procedural-memory@rhize-plugins',
    'codex plugin remove rhize-devflow@rhize-plugins',
    'env NO_COLOR=1 /usr/local/bin/codex plugin add rhize-devflow@rhize-plugins',
    'git status; claude plugin update rhize-devflow',
    "bash -lc 'codex plugin add rhize-devflow@rhize-plugins'",
    'codex plugin marketplace upgrade',
])
def test_blocks_live_rhize_cache_mutations_without_echoing_input(tmp_path, command):
    result = run_guard(tmp_path, command=command)
    denied(result)
    assert command not in result.stdout + result.stderr


@pytest.mark.parametrize('command', [
    'codex plugin list --json', 'claude plugin update --help',
    'codex plugin add rhize-devflow@rhize-plugins --help',
    'codex plugin add other@unrelated', 'claude plugin marketplace update unrelated',
    "rg 'codex plugin add' README.md", "printf '%s' 'claude plugin update rhize-devflow'",
    'git pull --ff-only', 'python3 -m pytest tests',
])
def test_read_only_commands_source_and_other_marketplaces_stay_quiet(tmp_path, command):
    result = run_guard(tmp_path, command=command)
    assert (result.returncode, result.stdout, result.stderr) == (0, '', '')


def package(tmp_path, version):
    path = tmp_path / '.codex/plugins/cache/rhize-plugins/rhize-devflow' / version / '.claude-plugin/plugin.json'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'name': 'rhize-devflow', 'version': version}))
    return path


def test_each_running_session_gets_one_drift_notice_and_stays_held(tmp_path):
    package(tmp_path, '1.0.0')
    for session in ('session-a', 'session-b'):
        assert run_guard(tmp_path, session=session).stdout == ''
    package(tmp_path, '1.0.1')
    for session in ('session-a', 'session-b'):
        first = run_guard(tmp_path, 'PostToolUse', session=session)
        assert first.returncode == 0 and 'restart' in first.stdout.lower()
        assert json.loads(first.stdout)['continue'] is False
        assert run_guard(tmp_path, 'PostToolUse', session=session).stdout == ''
        denied(run_guard(tmp_path, session=session))
    # A different native session establishes its own baseline without erasing old receipts.
    assert run_guard(tmp_path, session='fresh-native-session').stdout == ''
    states = list((tmp_path / 'data/rhize/plugin-update-safety').glob('*.json'))
    assert len(states) == 3
    assert all('git status' not in p.read_text() and 'session-a' not in p.read_text() for p in states)


def test_native_restart_can_resume_same_chat_without_erasing_old_hold(tmp_path):
    package(tmp_path, '1.0.0')
    assert run_guard(tmp_path).stdout == ''
    package(tmp_path, '1.0.1')
    denied(run_guard(tmp_path))
    assert run_guard(tmp_path, 'SessionStart').stdout == ''
    assert run_guard(tmp_path).stdout == ''
    prior = list((tmp_path / 'data/rhize/plugin-update-safety').glob('*.prior-*.json'))
    assert len(prior) == 1 and json.loads(prior[0].read_text())['restartRequired'] is True


def test_pre_tool_drift_stops_without_waiting_for_an_impossible_reconcile(tmp_path):
    package(tmp_path, '1.0.0')
    assert run_guard(tmp_path).stdout == ''
    package(tmp_path, '1.0.1')
    denied(run_guard(tmp_path))
    stopped = run_guard(tmp_path, 'Stop')
    assert stopped.returncode == 0
    assert json.loads(stopped.stdout)['continue'] is False
    assert json.loads(stopped.stdout).get('decision') != 'block'


def test_large_post_tool_result_does_not_look_like_an_unavailable_plugin(tmp_path):
    assert run_guard(tmp_path).stdout == ''
    payload = {'session_id': 'session-a', 'hook_event_name': 'PostToolUse',
               'tool_name': 'Read', 'tool_response': 'x' * 200000}
    result = subprocess.run([sys.executable, str(SCRIPT), 'PostToolUse'], input=json.dumps(payload),
                            env=dict(os.environ, HOME=str(tmp_path), XDG_DATA_HOME=str(tmp_path / 'data')),
                            capture_output=True, text=True, timeout=5)
    assert (result.returncode, result.stdout, result.stderr) == (0, '', '')


def test_compaction_does_not_clear_restart_hold(tmp_path):
    package(tmp_path, '1.0.0')
    assert run_guard(tmp_path).stdout == ''
    package(tmp_path, '1.0.1')
    denied(run_guard(tmp_path))
    payload = {'session_id': 'session-a', 'hook_event_name': 'SessionStart', 'source': 'compact'}
    result = subprocess.run([sys.executable, str(SCRIPT), 'SessionStart'], input=json.dumps(payload),
                            env=dict(os.environ, HOME=str(tmp_path), XDG_DATA_HOME=str(tmp_path / 'data')),
                            capture_output=True, text=True, timeout=5)
    assert result.returncode == 0 and json.loads(result.stdout)['continue'] is False
    denied(run_guard(tmp_path))


def test_native_uninstall_tool_cannot_remove_the_loaded_guard(tmp_path):
    payload = {'session_id': 'session-a', 'hook_event_name': 'PreToolUse',
               'tool_name': 'mcp__codex_app__uninstall_plugin', 'tool_input': {'plugin': 'Rhize Dev Flow'}}
    result = subprocess.run([sys.executable, str(SCRIPT), 'PreToolUse'], input=json.dumps(payload),
                            env=dict(os.environ, HOME=str(tmp_path), XDG_DATA_HOME=str(tmp_path / 'data')),
                            capture_output=True, text=True, timeout=5)
    denied(result)


def test_parallel_tools_do_not_turn_session_lock_contention_into_a_restart(tmp_path):
    package(tmp_path, '1.0.0')
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: run_guard(tmp_path), range(4)))
    assert all((r.returncode, r.stdout, r.stderr) == (0, '', '') for r in results)
    assert len(list((tmp_path / 'data/rhize/plugin-update-safety').glob('*.json'))) == 1


def test_partial_update_missing_credential_guard_stops_the_surviving_hook(tmp_path):
    scripts = tmp_path / 'plugin/scripts'
    scripts.mkdir(parents=True)
    for name in ('plugin_update_guard.py', 'credential_guard.py', 'refactor_gate.py'):
        shutil.copyfile(PLUGIN / 'scripts' / name, scripts / name)
    env = dict(os.environ, HOME=str(tmp_path), XDG_DATA_HOME=str(tmp_path / 'data'))
    def invoke(event):
        return subprocess.run([sys.executable, str(scripts / 'plugin_update_guard.py'), event],
            input=json.dumps({'session_id': 'partial-update-session', 'hook_event_name': event}),
            env=env, text=True, capture_output=True, timeout=5)
    assert invoke('PreToolUse').stdout == ''
    (scripts / 'credential_guard.py').unlink()
    denied(invoke('PreToolUse'))
    stop = invoke('Stop')
    assert stop.returncode == 0 and json.loads(stop.stdout)['continue'] is False


def test_same_version_metadata_replacement_and_removal_trigger_drift(tmp_path):
    file = package(tmp_path, '1.0.0')
    assert run_guard(tmp_path).stdout == ''
    file.write_text(json.dumps({'name': 'rhize-devflow', 'version': '1.0.0', 'changed': True}))
    denied(run_guard(tmp_path))
    assert run_guard(tmp_path, session='session-b').stdout == ''
    file.unlink()
    denied(run_guard(tmp_path, session='session-b'))


def test_corrupt_state_cannot_clear_a_restart_hold(tmp_path):
    assert run_guard(tmp_path).stdout == ''
    state = next((tmp_path / 'data/rhize/plugin-update-safety').glob('*.json'))
    state.write_text('corrupt')
    denied(run_guard(tmp_path))
    assert state.read_text() == 'corrupt'


def test_symlinked_state_directory_is_not_written(tmp_path):
    outside = tmp_path / 'outside'
    outside.mkdir()
    parent = tmp_path / 'data/rhize'
    parent.mkdir(parents=True)
    (parent / 'plugin-update-safety').symlink_to(outside, target_is_directory=True)
    denied(run_guard(tmp_path))
    assert list(outside.iterdir()) == []


@pytest.mark.parametrize('event', ['SessionStart', 'PreToolUse', 'PostToolUse', 'UserPromptSubmit', 'Stop'])
def test_removed_cache_uses_shell_fallback_without_missing_file_loop(tmp_path, event):
    groups = json.loads((PLUGIN / 'hooks/hooks.json').read_text())['hooks'][event]
    for group in groups:
        for hook in group['hooks']:
            command = hook['command'].replace('${CLAUDE_PLUGIN_ROOT}', str(tmp_path / 'removed cache'))
            result = subprocess.run(command, shell=True, input='{}', text=True, capture_output=True, timeout=5)
            assert result.returncode == 0, result.stderr
            value = json.loads(result.stdout)
            assert 'No such file' not in result.stderr
            if event == 'PreToolUse':
                denied(result)
            else:
                assert 'unavailable' in value['systemMessage'].lower()
                assert value['continue'] is False
                assert value.get('decision') != 'block'


def test_manifest_wires_update_detection_before_and_after_all_tools():
    hooks = json.loads((PLUGIN / 'hooks/hooks.json').read_text())['hooks']
    for event in ('PreToolUse', 'PostToolUse'):
        assert any(group.get('matcher') == '*' and any('plugin_update_guard.py' in h['command']
                   for h in group['hooks']) for group in hooks[event])


def test_actual_manifest_preserves_credential_denial_and_allowed_control(tmp_path):
    env = dict(os.environ, HOME=str(tmp_path), XDG_DATA_HOME=str(tmp_path / 'data'),
               RHIZE_REFACTOR_GATE_STATE_DIR=str(tmp_path / 'gate'))
    groups = json.loads((PLUGIN / 'hooks/hooks.json').read_text())['hooks']['PreToolUse']
    for code, should_deny in [('await cua.getApp("Safari")', False),
                               ('await cua.getApp("Keychain Access")', True)]:
        payload = {'session_id': 'manifest-session', 'hook_event_name': 'PreToolUse',
                   'tool_name': 'mcp__cua_repl__js', 'tool_input': {'code': code}, 'cwd': str(tmp_path)}
        results = {}
        for group in groups:
            if group.get('matcher') != '*' and not re.fullmatch(group.get('matcher', ''), payload['tool_name']):
                continue
            for hook in group['hooks']:
                command = hook['command'].replace('${CLAUDE_PLUGIN_ROOT}', str(PLUGIN))
                results[command] = subprocess.run(command, shell=True, env=env, input=json.dumps(payload),
                                                  text=True, capture_output=True, timeout=5)
        guard = next(v for k, v in results.items() if 'plugin_update_guard.py' in k)
        credential = next(v for k, v in results.items() if 'credential_guard.py' in k)
        assert (guard.returncode, guard.stdout, guard.stderr) == (0, '', '')
        assert credential.returncode == (2 if should_deny else 0)
