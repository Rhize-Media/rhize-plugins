import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("package", ROOT / "scripts/build_perplexity_plugin.py")
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


def test_complete_snapshot_without_credential_content(tmp_path):
    reference = tmp_path / "authorization.txt"
    reference.write_text("private authorization text stays outside the package")
    reference.chmod(0o600)
    destination = tmp_path / "snapshot"
    result = package.build(destination, reference)
    plugin = destination / "plugins/perplexity-research"
    assert result["plugin"] == "perplexity-research@perplexity-local"
    catalog = json.loads((destination / ".agents/plugins/marketplace.json").read_text())
    assert catalog["plugins"][0]["source"]["path"] == "./plugins/perplexity-research"
    manifest = json.loads((plugin / ".codex-plugin/plugin.json").read_text())
    server = manifest["mcpServers"]["perplexity_research"]
    assert server["cwd"] == "." and Path(server["command"]).is_absolute()
    assert server["args"][-1] == str(reference)
    for name in package.RUNTIME:
        assert (plugin / "scripts" / name).read_bytes() == (ROOT / "perplexity-research/scripts" / name).read_bytes()
    hashes = json.loads((plugin / "snapshot.json").read_text())
    for path, digest in hashes.items():
        data = (plugin / path).read_bytes()
        assert package.hashlib.sha256(data).hexdigest() == digest
        assert reference.read_bytes() not in data
    with pytest.raises(FileExistsError):
        package.build(destination, reference)
    assert (plugin / "snapshot.json").exists()


@pytest.mark.parametrize("kind", ["shared", "symlink", "hardlink"])
def test_reject_unsafe_reference_before_writing(tmp_path, kind):
    reference = tmp_path / "reference"
    reference.write_text("authorization")
    reference.chmod(0o600)
    if kind == "shared":
        reference.chmod(0o644)
    elif kind == "symlink":
        link = tmp_path / "link"
        link.symlink_to(reference)
        reference = link
    else:
        (tmp_path / "link").hardlink_to(reference)
    with pytest.raises(ValueError):
        package.build(tmp_path / "snapshot", reference)
    assert not (tmp_path / "snapshot").exists()


@pytest.mark.parametrize("stage", ["dependency", "copy"])
def test_failure_leaves_no_partial_snapshot(tmp_path, monkeypatch, stage):
    reference = tmp_path / "reference"
    reference.write_text("authorization")
    reference.chmod(0o600)
    def fail(*args, **kwargs):
        raise OSError("fixture failure")
    if stage == "dependency":
        monkeypatch.setattr(package.subprocess, "run", fail)
    else:
        monkeypatch.setattr(package.shutil, "copyfile", fail)
    with pytest.raises(OSError):
        package.build(tmp_path / "snapshot", reference)
    assert not (tmp_path / "snapshot").exists()
    assert reference.read_text() == "authorization"


def test_marketplace_launcher_is_portable_and_uses_existing_state(tmp_path):
    import os
    import shutil
    import subprocess
    import sys
    # Copy only the published island into a path with spaces, outside the checkout.
    plugin = tmp_path / 'installed plugin'
    shutil.copytree(ROOT / 'perplexity-research', plugin)
    home = tmp_path / 'home'
    state = home / 'existing reports'
    state.mkdir(parents=True, mode=0o700)
    write_config(home, {'pythonExecutable': str(Path(sys.executable).absolute()), 'stateDir': str(state), 'keychainService': 'existing:session'})
    job_id = '00000000-0000-4000-8000-000000000001'
    record = state / (job_id + '.json')
    record.write_text(json.dumps({'job_id': job_id, 'status': 'failed', 'submitted': False}))
    record.chmod(0o600)
    env = {**os.environ, 'HOME': str(home)}
    wire = '\n'.join(json.dumps(x) for x in [
        {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {}},
        {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list', 'params': {}},
        {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call',
         'params': {'name': 'research_jobs', 'arguments': {}}},
    ]) + '\n'
    run = subprocess.run([str(plugin / 'scripts/launch-mcp.sh')], input=wire,
                         text=True, capture_output=True, timeout=10, env=env, cwd=tmp_path)
    assert run.returncode == 0, run.stderr
    replies = [json.loads(line) for line in run.stdout.splitlines()]
    manifest = json.loads((plugin / '.claude-plugin/plugin.json').read_text())
    assert replies[0]['result']['serverInfo']['version'] == manifest['version']
    assert len(replies[1]['result']['tools']) == 11
    assert not replies[2]['result']['isError']
    assert not (state / 'mcp-authorization.txt').exists()
    jobs = json.loads(replies[2]['result']['content'][0]['text'])['jobs']
    assert [job['job_id'] for job in jobs] == [job_id]
    assert sorted(p.name for p in state.glob('*.json')) == [record.name]


@pytest.mark.parametrize('selection', [None, 'relative-python\n', '/missing/python\n'])
def test_launcher_refuses_missing_or_invalid_runtime_without_stdout(tmp_path, selection):
    import os
    import subprocess
    state = tmp_path / '.config/perplexity-research'
    state.mkdir(parents=True)
    if selection is not None:
        write_config(tmp_path, {'pythonExecutable': selection.strip()})
    run = subprocess.run([str(ROOT / 'perplexity-research/scripts/launch-mcp.sh')],
                         text=True, capture_output=True, timeout=5,
                         env={**os.environ, 'HOME': str(tmp_path)})
    assert run.returncode == 78 and not run.stdout
    assert 'Perplexity' in run.stderr
    assert sorted(p.name for p in state.iterdir()) == ([] if selection is None else ['config.json'])


def test_launcher_missing_crypto_has_no_install_or_state_side_effect(tmp_path):
    import os
    import shlex
    import subprocess
    import sys
    state = tmp_path / '.config/perplexity-research'
    state.mkdir(parents=True)
    runtime = tmp_path / 'python without site'
    runtime.write_text('#!/bin/sh\nexec ' + shlex.quote(sys.executable) + ' -S "$@"\n')
    runtime.chmod(0o700)
    write_config(tmp_path, {'pythonExecutable': str(runtime)})
    run = subprocess.run([str(ROOT / 'perplexity-research/scripts/launch-mcp.sh')],
                         text=True, capture_output=True, timeout=5,
                         env={**os.environ, 'HOME': str(tmp_path)})
    assert run.returncode == 78 and not run.stdout
    assert 'cryptography' in run.stderr
    assert [p.name for p in state.iterdir()] == ['config.json']


def test_snapshot_excludes_unlisted_local_files(tmp_path, monkeypatch):
    import shutil
    source = tmp_path / 'source'
    shutil.copytree(ROOT / 'perplexity-research', source / 'perplexity-research')
    (source / 'perplexity-research/private-local.txt').write_text('fixture-not-for-distribution')
    monkeypatch.setattr(package, 'ROOT', source)
    reference = tmp_path / 'authorization'
    reference.write_text('user authorization fixture')
    reference.chmod(0o600)
    package.build(tmp_path / 'snapshot', reference)
    installed = tmp_path / 'snapshot/plugins/perplexity-research'
    assert not (installed / 'private-local.txt').exists()
    assert all(b'fixture-not-for-distribution' not in f.read_bytes()
               for f in installed.rglob('*') if f.is_file())


def write_config(home, values):
    path = home / '.config/perplexity-research/config.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(values))
    path.chmod(0o600)
    return path


@pytest.mark.parametrize('values', [[], {'unknown': True}, {'stateDir': 'relative'},
    {'keychainService': 'name\nquit'}, {'keychainService': '-s'}, {'keychainService': 42},
    {'authorizationReference': False}, {'pythonExecutable': '/bad\npath'}])
def test_config_rejects_unsafe_values(tmp_path, monkeypatch, values):
    import runpy
    monkeypatch.setenv('HOME', str(tmp_path))
    write_config(tmp_path, values)
    load = runpy.run_path(str(ROOT / 'perplexity-research/scripts/perplexity_config.py'))['load_config']
    with pytest.raises(ValueError):
        load()


@pytest.mark.parametrize('kind', ['shared', 'symlink', 'hardlink', 'oversize', 'malformed'])
def test_config_rejects_unsafe_files(tmp_path, monkeypatch, kind):
    import runpy
    monkeypatch.setenv('HOME', str(tmp_path))
    path = write_config(tmp_path, {})
    if kind == 'shared':
        path.chmod(0o644)
    elif kind == 'symlink':
        target = path.with_suffix('.target')
        path.rename(target)
        path.symlink_to(target)
    elif kind == 'hardlink':
        path.with_suffix('.link').hardlink_to(path)
    else:
        path.write_text(' ' * 8193 if kind == 'oversize' else '{')
    load = runpy.run_path(str(ROOT / 'perplexity-research/scripts/perplexity_config.py'))['load_config']
    with pytest.raises((ValueError, OSError)):
        load()


def test_snapshot_keeps_selected_interpreter_symlink(tmp_path, monkeypatch):
    import sys
    runtime = tmp_path / 'venv-python'
    runtime.symlink_to(sys.executable)
    monkeypatch.setattr(package.sys, 'executable', str(runtime))
    reference = tmp_path / 'reference'
    reference.write_text('authorization')
    reference.chmod(0o600)
    package.build(tmp_path / 'snapshot', reference)
    manifest = json.loads((tmp_path / 'snapshot/plugins/perplexity-research/.codex-plugin/plugin.json').read_text())
    assert manifest['mcpServers']['perplexity_research']['command'] == str(runtime)


def test_launcher_home_resolution_error_is_controlled(monkeypatch, capsys):
    import runpy
    module = runpy.run_path(str(ROOT / 'perplexity-research/scripts/perplexity_config.py'))
    def unavailable():
        raise RuntimeError('HOME unavailable fixture')
    monkeypatch.setattr(Path, 'home', unavailable)
    assert module['launch']() == 78
    captured = capsys.readouterr()
    assert not captured.out and 'Perplexity setup invalid' in captured.err
    assert 'HOME unavailable fixture' not in captured.err
