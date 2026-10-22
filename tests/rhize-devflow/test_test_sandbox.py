"""Provider-free contracts for isolation, receipt integrity and restored source bytes."""
import json
from pathlib import Path
import stat

import pytest

from test_test_evidence import repository, spec, test_evidence, git

IMAGE = 'sha256:' + 'a' * 64


def test_cleanup_inspection_failure_is_never_clean(monkeypatch, tmp_path):
    adapter = test_evidence.sandbox_adapter()
    sandbox = adapter.DockerSandbox.__new__(adapter.DockerSandbox)
    sandbox.image = IMAGE
    calls = []
    def client(*args, **kwargs):
        calls.append(args)
        if args[0] == 'wait':
            return '0'
        if args[0] in {'rm', 'ps'}:
            raise adapter.SandboxUnavailable('daemon unavailable')
        return 'container-id'
    sandbox.client = client
    with pytest.raises(adapter.CleanupFailed, match='removal could not be verified'):
        sandbox.run(tmp_path, ['python3', 'test.py'], 1)
    run = calls[0]
    assert all(flag in run for flag in ('--network=none', '--read-only', '--cap-drop=ALL', '--no-healthcheck', '--log-driver=none', '--pull=never'))
    assert 'readonly' in run[run.index('--mount') + 1]
    assert '-i' in run and 'HOME=/tmp' in run
    assert any(args[:3] == ('rm', '--force', '--volumes') for args in calls)


def test_snapshot_rejects_same_size_drift_and_excludes_credentials(tmp_path):
    repo = repository(tmp_path)
    (repo / '.envrc').write_text('fake-ambient-secret')
    git(repo, 'add', '.')
    git(repo, 'commit', '-qm', 'credential fixture')
    adapter = test_evidence.sandbox_adapter()
    destination = tmp_path / 'copy'
    destination.mkdir()
    before = adapter.snapshot(repo, destination, test_evidence.run_git)
    assert before == adapter.tree_digest(destination)
    assert not (destination / '.envrc').exists()
    (repo / 'calc.js').write_text((repo / 'calc.js').read_text().replace('a + b', 'a - b'))
    with pytest.raises(adapter.SandboxUnavailable, match='source changed'):
        adapter.snapshot(repo, destination, test_evidence.run_git)


def test_mutation_restores_crlf_bytes_and_executable_mode(tmp_path, monkeypatch):
    repo = repository(tmp_path)
    original = b'exports.add = (a, b) => a + b;\r\n'
    (repo / 'calc.js').write_bytes(original)
    (repo / 'calc.js').chmod(0o755)
    git(repo, 'add', '.')
    git(repo, 'commit', '-qm', 'CRLF fixture')
    adapter = test_evidence.sandbox_adapter()
    seen = []
    class Sandbox:
        def __init__(self, *args):
            pass
        def run(self, root, command, timeout):
            seen.append(((root / 'calc.js').read_bytes(), stat.S_IMODE((root / 'calc.js').stat().st_mode)))
            return 1 if len(seen) == 2 else 0
    monkeypatch.setattr(adapter, 'DockerSandbox', Sandbox)
    result = adapter.execute(repo, spec(repo), IMAGE, test_evidence.run_git)
    assert [r[1] for r in seen] == [0o555] * 3
    assert seen[0][0] == seen[2][0] == original
    assert seen[1][0] == original.replace(b'a + b', b'a - b')
    assert result['before'] != result['after'] and result['mutant'] == 1
    assert (repo / 'calc.js').read_bytes() == original


def test_python_invocation_is_declared_and_digest_bound(tmp_path):
    repo = repository(tmp_path)
    (repo / 'test_calc.py').write_text('import unittest\n')
    git(repo, 'add', '.')
    git(repo, 'commit', '-qm', 'Python fixture')
    value = spec(repo, test_files=['test_calc.py'], test_invocation={'source': 'python_unittest', 'name': 'test_calc.py'})
    validated = test_evidence.validate_spec(value, repo)
    packet = test_evidence.run_evidence(repo, validated, tmp_path / 'packet.json', tmp_path / 'leases')
    assert packet['invocation']['source'] == 'python_unittest'
    assert packet['verdict'] == 'execution_unavailable'
    assert test_evidence.validate_packet(packet, repo)['review_verdict'] == 'unsupported'
    (repo / 'test_calc.py').write_text('changed')
    with pytest.raises(test_evidence.EvidenceError, match='invocation has drifted'):
        test_evidence.validate_packet(packet, repo)
    value['test_files'] = ['test.js']
    with pytest.raises(test_evidence.EvidenceError, match='listed in test_files'):
        test_evidence.validate_spec(value, repo)


def test_python_glob_and_noop_mutation_are_refused(tmp_path):
    repo = repository(tmp_path)
    (repo / 'test_*.py').write_text('import unittest\n')
    value = spec(repo, test_files=['test_*.py'], test_invocation={'source': 'python_unittest', 'name': 'test_*.py'})
    with pytest.raises(test_evidence.EvidenceError, match='canonical'):
        test_evidence.validate_spec(value, repo)
    value = spec(repo)
    value['mutation']['replace'] = value['mutation']['search']
    with pytest.raises(test_evidence.EvidenceError, match='change'):
        test_evidence.validate_spec(value, repo)


def test_policy_hash_covers_producer_and_adapter(tmp_path, monkeypatch):
    adapter = test_evidence.sandbox_adapter()
    module = tmp_path / 'test_sandbox.py'
    producer = tmp_path / 'test_evidence.py'
    module.write_bytes(b'adapter')
    producer.write_bytes(b'producer')
    monkeypatch.setattr(adapter, '__file__', str(module))
    original = adapter.policy_hash()
    producer.write_bytes(b'changed producer')
    assert adapter.policy_hash() != original
    original = adapter.policy_hash()
    module.write_bytes(b'changed adapter')
    assert adapter.policy_hash() != original


@pytest.mark.parametrize('selected_has_test,expected', [(True, 0), (False, 20)])
def test_unittest_harness_runs_only_the_selected_file(tmp_path, selected_has_test, expected):
    import subprocess
    import sys
    adapter = test_evidence.sandbox_adapter()
    tests = tmp_path / 'tests'
    nested = tests / 'nested'
    nested.mkdir(parents=True)
    (nested / '__init__.py').write_text('')
    (nested / 'test_calc.py').write_text('import unittest\nclass Other(unittest.TestCase):\n def test_other(self): self.fail("unselected")\n')
    (tests / 'test_calc.py').write_text('import unittest\n' + ('class Selected(unittest.TestCase):\n def test_selected(self): self.assertTrue(True)\n' if selected_has_test else ''))
    result = subprocess.run([sys.executable, '-I', '-B', '-c', adapter.PYTHON_RUNNER,
                             'python_unittest', 'tests/test_calc.py'], cwd=tmp_path, capture_output=True)
    assert result.returncode == expected, result.stderr


def test_sandbox_receipt_is_bound_to_observed_packet_and_private_store(tmp_path, monkeypatch):
    monkeypatch.setenv('HOME', str(tmp_path / 'home'))
    adapter = test_evidence.sandbox_adapter()
    packet = {'sandbox': None, 'verdict': 'killed', 'baseline': 0}
    packet['sandbox'] = adapter.record(packet, IMAGE)
    adapter.verify(packet)
    packet['baseline'] = 1
    with pytest.raises(adapter.SandboxUnavailable, match='binding mismatch'):
        adapter.verify(packet)


@pytest.mark.parametrize('image', ['python:latest', 'sha256:abc', '', None])
def test_unpinned_image_never_invokes_docker(image, tmp_path):
    adapter = test_evidence.sandbox_adapter()
    with pytest.raises(adapter.SandboxUnavailable, match='explicit local'):
        adapter.DockerSandbox(image, tmp_path / 'config')


def test_remote_context_and_image_volume_are_refused(tmp_path, monkeypatch):
    adapter = test_evidence.sandbox_adapter()
    monkeypatch.setenv('DOCKER_HOST', 'tcp://remote.example.invalid:2375')
    with pytest.raises(adapter.SandboxUnavailable, match='local Unix'):
        adapter.DockerSandbox(IMAGE, tmp_path / 'remote')
    monkeypatch.setenv('DOCKER_HOST', 'unix:///local-fixture.sock')
    monkeypatch.setattr(adapter.DockerSandbox, 'client', lambda *a, **kw: json.dumps({'Id': IMAGE, 'Config': {'Volumes': {'/data': {}}}}))
    with pytest.raises(adapter.SandboxUnavailable, match='identity'):
        adapter.DockerSandbox(IMAGE, tmp_path / 'volume')


@pytest.mark.parametrize('inspection_error', [None, OSError('Git unavailable'), test_evidence.EvidenceError('Git failed')])
def test_cleanup_failure_names_resource_and_cannot_support_claim(tmp_path, monkeypatch, inspection_error):
    repo = repository(tmp_path)
    monkeypatch.setenv('HOME', str(tmp_path / 'home'))
    adapter = test_evidence.sandbox_adapter()
    name = 'rhize-test-evidence-' + 'f' * 32
    def fail(*a):
        raise adapter.CleanupFailed('cannot verify removal: ' + name)
    monkeypatch.setattr(adapter, 'execute', fail)
    monkeypatch.setattr(test_evidence, 'sandbox_adapter', lambda: adapter)
    if inspection_error is not None:
        fingerprint = test_evidence.working_fingerprint
        calls = []
        def inspect(repo):
            calls.append(repo)
            if len(calls) > 1:
                raise inspection_error
            return fingerprint(repo)
        monkeypatch.setattr(test_evidence, 'working_fingerprint', inspect)
    packet = test_evidence.run_evidence(repo, spec(repo), tmp_path / 'packet.json', tmp_path / 'leases', IMAGE)
    assert packet['verdict'] == 'cleanup_failed'
    assert packet['cleanup']['resource'] == name
    if inspection_error is not None:
        assert packet['repository']['final_working_tree_fingerprint'] is None
        monkeypatch.setattr(test_evidence, 'working_fingerprint', fingerprint)
    assert test_evidence.validate_packet(packet, repo)['review_verdict'] == 'FAIL_REQUIRES_HUMAN'


def test_host_client_deadline_terminates_forked_descendants(tmp_path):
    import subprocess
    import sys
    adapter = test_evidence.sandbox_adapter()
    sandbox = adapter.DockerSandbox.__new__(adapter.DockerSandbox)
    pids = tmp_path / 'pids'
    cli = tmp_path / 'fixture-cli'
    cli.write_text('#!' + sys.executable + '\nimport os,time\nos.fork()\nwith open(' + repr(str(pids)) + ',"a") as f: f.write(str(os.getpid())+"\\n")\ntime.sleep(60)\n')
    cli.chmod(0o700)
    sandbox.binary, sandbox.config, sandbox.env = str(cli), tmp_path, {}
    with pytest.raises(adapter.SandboxUnavailable, match='deadline'):
        sandbox.client(timeout=.5)
    children = pids.read_text().splitlines()
    assert len(children) == 2
    for pid in children:
        state = subprocess.run(['/bin/ps', '-o', 'stat=', '-p', pid], capture_output=True, text=True).stdout.strip()
        assert not state or state.startswith('Z'), (pid, state)
