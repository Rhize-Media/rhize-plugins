"""Native encrypted transfer contracts: synthetic cookies, no real browser or Keychain."""
import base64
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
from unittest.mock import Mock

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / 'perplexity-research/scripts/perplexity_research.py'
ADAPTER = SCRIPT.with_name('perplexity_session_transfer.mjs')
spec = importlib.util.spec_from_file_location('auth_bridge', SCRIPT)
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)
SECRET = 'synthetic-cookie-value'


def worker(tmp_path, store, lifetime=3):
    root = b.private_root(tmp_path.resolve() / 'auth')
    fd = b.private_open(root / 'session.lock', os.O_RDWR | os.O_CREAT)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    thread = threading.Thread(target=b.auth_worker, args=(root, fd), kwargs={'store': store, 'lifetime': lifetime})
    thread.start()
    for _ in range(100):
        if (root / 'session.json').exists():
            return root, thread, b.auth_status(root)
        time.sleep(.01)
    raise AssertionError('worker did not start')


def browser(descriptor, cookies):
    source = "import {transferSession} from " + json.dumps(ADAPTER.as_uri()) + ";\n" + '''
let text = ''; for await (const chunk of process.stdin) text += chunk;
const {descriptor, cookies} = JSON.parse(text);
try {
  const result = await transferSession(descriptor, async (method, args) => {
    if (method !== 'Network.getCookies' || JSON.stringify(args) !== JSON.stringify({urls:['https://www.perplexity.ai/']})) throw Error();
    return {cookies};
  });
  console.log(JSON.stringify(result));
} catch (error) { console.log(error.message); process.exitCode = 2; }
'''
    return subprocess.run([shutil.which('node'), '--input-type=module', '-e', source],
                          input=json.dumps({'descriptor': descriptor, 'cookies': cookies}),
                          text=True, capture_output=True, timeout=5)


def cookie(name, value=SECRET, **fields):
    return {'name': name, 'value': value, 'domain': 'www.perplexity.ai', 'path': '/', 'secure': True, 'expires': -1, **fields}


def test_browser_to_worker_round_trip_scopes_and_erases(tmp_path):
    store = Mock()
    root, thread, descriptor = worker(tmp_path, store)
    result = browser(descriptor, [cookie('__Host-pplx-last-active-account', 'active'),
        cookie('__Secure-pplx.session.active'), cookie('__Secure-pplx.session.other'), cookie('analytics'),
        cookie('__Secure-next-auth.session-token', domain='evil.example')])
    thread.join(5)
    assert not thread.is_alive() and result.returncode == 0, result.stdout + result.stderr
    store.assert_called_once_with({'__Host-pplx-last-active-account': 'active', '__Secure-pplx.session.active': SECRET})
    assert b.auth_status(root)['status'] == 'stored'
    assert SECRET not in result.stdout + result.stderr
    assert not (root / 'payload.json').exists()
    assert all(SECRET.encode() not in p.read_bytes() for p in root.iterdir())
    assert 'public_key' not in b.auth_status(root)
    assert browser(descriptor, [cookie('__Secure-pplx.session.active')]).returncode == 2
    assert not (root / 'payload.json').exists()


def encrypt(descriptor, cookies):
    hashes, serialization, padding, rsa, AESGCM = b.auth_crypto()
    key, iv = os.urandom(32), os.urandom(12)
    public = serialization.load_pem_public_key(descriptor['public_key'].encode())
    encode = lambda value: base64.b64encode(value).decode()
    return {'transfer_id': descriptor['transfer_id'], 'key': encode(public.encrypt(key,
        padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))),
        'iv': encode(iv), 'ciphertext': encode(AESGCM(key).encrypt(iv, json.dumps(cookies).encode(), descriptor['transfer_id'].encode()))}


@pytest.mark.parametrize('failure', ['tamper', 'identity', 'cookies', 'permissions'])
def test_invalid_payload_never_reaches_keychain(tmp_path, failure):
    store = Mock()
    root, thread, descriptor = worker(tmp_path, store)
    payload = encrypt(descriptor, {'analytics' if failure == 'cookies' else '__Secure-next-auth.session-token': SECRET})
    if failure == 'tamper': payload['ciphertext'] = base64.b64encode(b'invalid').decode()
    if failure == 'identity': payload['transfer_id'] = 'other'
    temporary = root / 'fixture'
    temporary.write_text(json.dumps(payload))
    temporary.chmod(0o644 if failure == 'permissions' else 0o600)
    temporary.rename(root / 'payload.json')
    thread.join(5)
    assert not thread.is_alive()
    store.assert_not_called()
    assert b.auth_status(root)['status'] == 'failed'
    assert SECRET not in json.dumps(b.auth_status(root))
    assert not (root / 'payload.json').exists()


def test_expired_transfer_and_browser_error_are_safe(tmp_path):
    store = Mock()
    root, thread, descriptor = worker(tmp_path, store, lifetime=.1)
    thread.join(2)
    result = browser(descriptor, [cookie('__Secure-next-auth.session-token')])
    assert result.returncode == 2 and SECRET not in result.stdout + result.stderr
    assert b.auth_status(root)['error'] == 'auth_transfer_expired'
    store.assert_not_called()


def test_keychain_secret_only_on_stdin_and_verified(monkeypatch):
    cookies = {'__Secure-next-auth.session-token': SECRET}
    run = Mock(return_value=Mock(returncode=0))
    monkeypatch.setattr(b.subprocess, 'run', run)
    monkeypatch.setattr(b, 'cookies_from_keychain', lambda: cookies)
    b.store_cookies(cookies)
    assert run.call_args.args == (['/usr/bin/security', '-i'],)
    assert SECRET not in repr(run.call_args.args)
    assert b.encoded(cookies).hex().encode() in run.call_args.kwargs['input']
    assert run.call_args.kwargs['stdout'] == subprocess.DEVNULL
    assert run.call_args.kwargs['stderr'] == subprocess.DEVNULL
    monkeypatch.setattr(b, 'cookies_from_keychain', lambda: {})
    with pytest.raises(b.BridgeError, match='verification_failed'): b.store_cookies(cookies)


@pytest.mark.parametrize('cookies', [
    [cookie('__Secure-next-auth.session-token', domain='evil.example')],
    [cookie('__Secure-next-auth.session-token', secure=False)],
    [cookie('__Secure-next-auth.session-token'), cookie('__Secure-next-auth.session-token')],
])
def test_browser_refuses_wrong_scope_and_ambiguous_sessions(tmp_path, cookies):
    store = Mock()
    root, thread, descriptor = worker(tmp_path, store, lifetime=.5)
    result = browser(descriptor, cookies)
    thread.join(2)
    assert result.returncode == 2
    store.assert_not_called()
    assert not (root / 'payload.json').exists()


def test_auth_launch_failure_is_durable_and_safe(tmp_path, monkeypatch):
    root = b.private_root(tmp_path.resolve() / 'auth')
    monkeypatch.setattr(b.subprocess, 'Popen', Mock(side_effect=OSError(SECRET)))
    with pytest.raises(b.BridgeError, match='auth_worker_launch_failed'): b.auth_start(root)
    assert b.auth_status(root)['error'] == 'auth_worker_launch_failed'
    assert SECRET not in json.dumps(b.auth_status(root))


def test_real_cli_worker_fails_closed_and_duplicate_start_reuses_descriptor(tmp_path):
    root = tmp_path.resolve() / 'jobs'
    def cli(command):
        result = subprocess.run([sys.executable, '-I', str(SCRIPT), '--state-dir', str(root), command], capture_output=True, text=True, timeout=5)
        assert not result.stderr
        return json.loads(result.stdout)
    assert cli('auth-status')['status'] == 'not_started'
    assert cli('auth-start')['status'] == 'starting'
    for _ in range(100):
        descriptor = cli('auth-status')
        if descriptor['status'] == 'waiting': break
        time.sleep(.01)
    assert descriptor['status'] == 'waiting'
    assert cli('auth-start') == descriptor
    path = Path(descriptor['payload_path'])
    path.write_text('{}'); path.chmod(0o600)
    for _ in range(100):
        state = cli('auth-status')
        if state['status'] == 'failed': break
        time.sleep(.01)
    assert state['status'] == 'failed'
    assert not path.exists()
    assert Path(descriptor['payload_path']).parent == b.auth_root(root)
    assert not root.is_relative_to(Path(descriptor['payload_path']).parent)
    shutil.rmtree(path.parent)


def test_auth_temporary_directory_is_private_and_bound_to_job_state(tmp_path, monkeypatch):
    first = b.auth_root(tmp_path / 'one')
    second = b.auth_root(tmp_path / 'two')
    try:
        assert first != second and first == b.auth_root(tmp_path / 'one')
        assert first.parent == Path('/tmp').resolve()
        monkeypatch.setenv('TMPDIR', str(tmp_path))
        assert first == b.auth_root(tmp_path / 'one')
        assert first.stat().st_uid == os.getuid() and first.stat().st_mode & 0o077 == 0
    finally:
        first.rmdir(); second.rmdir()


def test_auth_worker_inherits_configured_service(tmp_path, monkeypatch):
    root = b.private_root(tmp_path.resolve() / 'auth')
    popen = Mock()
    monkeypatch.setattr(b.subprocess, 'Popen', popen)
    monkeypatch.setattr(b, 'KEYCHAIN_SERVICE', 'custom:session')
    b.auth_start(root)
    argv = popen.call_args.args[0]
    assert argv[argv.index('--keychain-service') + 1] == 'custom:session'
    assert popen.call_args.kwargs['start_new_session']
