#!/usr/bin/env python3
"""Public Agent Reach adapters in an ephemeral, network-disabled container."""
import argparse
import datetime as dt
import hashlib
import http.client
import ipaddress
import json
import os
from pathlib import Path
import re
import selectors
import select
import shutil
import socket
import ssl
import subprocess
import sys
import time
import tempfile
import signal
from urllib.parse import urlencode, urlsplit
import uuid

ROOT = Path(__file__).resolve().parents[1]
CONTEXT = ROOT / 'reach'
MAX_BODY = 1024 * 1024
MAX_OUTPUT = 262144
DEADLINE = 45
OPERATIONS = ('web-search', 'reddit-search', 'exa-read', 'jina-read', 'github-search', 'github-read', 'v2ex-hot', 'v2ex-read')
DOCKER_CONFIG = None


def require(ok, message):
    if not ok:
        raise ValueError(message)


def clean_text(value):
    require(isinstance(value, str) and 0 < len(value) <= 500, 'invalid_input')
    require(not any(ord(c) < 32 or ord(c) == 127 for c in value), 'invalid_input')
    return value


def public_url(value):
    clean_text(value)
    u = urlsplit(value)
    require(value.isascii() and not re.search(r'[\s\\?#]', value), 'invalid_url')
    require(u.scheme == 'https' and u.hostname and u.netloc == u.hostname and not u.port, 'invalid_url')
    host = u.hostname
    require(bool(re.fullmatch(r'[a-z0-9.-]+\.[a-z]{2,63}', host)), 'invalid_host')
    require(not host.endswith(('.local', '.internal', '.localhost', '.lan', '.test', '.home.arpa', '.corp', '.intranet')), 'private_target')
    return value


def result_url(value):
    require(isinstance(value, str) and 0 < len(value) <= 2048 and value.isascii(), 'invalid_result_url')
    require(not any(c.isspace() or ord(c) < 32 or c in '\\<>"`' for c in value), 'invalid_result_url')
    parsed = urlsplit(value)
    # Preserve meaningful queries/anchors in evidence; they are never automatically fetched.
    public_url('https://' + parsed.netloc)
    require(parsed.scheme == 'https', 'invalid_result_url')
    return value


def select_items(rows, operation):
    accepted = []
    for item in rows:
        require(isinstance(item, dict) and set(item) == {'title', 'url', 'published_at', 'text'}, 'invalid_item')
        require(all(v is None or isinstance(v, str) for v in item.values()), 'invalid_item')
        try:
            result_url(item['url'])
            if operation == 'reddit-search':
                url = urlsplit(item['url'])
                require(url.hostname in ('reddit.com', 'www.reddit.com', 'old.reddit.com') and url.path.startswith('/r/'), 'off_domain_result')
        except ValueError:
            continue
        accepted.append(item)
    require(not rows or accepted, 'no_usable_results')
    return {'items': accepted, 'dropped_items': len(rows) - len(accepted)}


def plan(task):
    require(set(task) == {'host', 'operation', 'query', 'target', 'limit'}, 'invalid_fields')
    require(task['host'] in ('claude', 'codex'), 'invalid_host')
    op = task['operation']
    require(op in OPERATIONS and type(task['limit']) is int and 1 <= task['limit'] <= 5, 'invalid_operation_or_limit')
    query, target, limit = task['query'], task['target'], task['limit']
    require(isinstance(query, str) and isinstance(target, str), 'invalid_input')
    require(not (query and target), 'ambiguous_input')
    if op.endswith('search'):
        clean_text(query)
        require(not target, 'unexpected_target')
    elif op.endswith('read'):
        clean_text(target)
        require(not query, 'unexpected_query')
    else:
        require(not query and not target, 'unexpected_input')
    def get(url, accept='application/json'):
        return {'url': url, 'body': None, 'accept': accept}
    if op in ('web-search', 'reddit-search', 'exa-read'):
        args = {'query': query, 'objective': query, 'numResults': limit}
        name = 'web_search_exa'
        if op == 'reddit-search':
            args['query'] = args['objective'] = 'site:reddit.com/r/ ' + query
        if op == 'exa-read':
            name, args = 'web_fetch_exa', {'urls': [public_url(target)], 'maxCharacters': 20000}
        body = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': name, 'arguments': args}}).encode()
        return [{'url': 'https://mcp.exa.ai/mcp', 'body': body, 'accept': 'application/json, text/event-stream'}]
    if op == 'jina-read':
        return [get('https://r.jina.ai/' + public_url(target), 'text/plain')]
    if op == 'github-search':
        return [get('https://api.github.com/search/repositories?' + urlencode({'q': query, 'per_page': limit}))]
    if op == 'github-read':
        m = re.fullmatch(r'https://github\.com/([A-Za-z0-9_-]+)/([A-Za-z0-9_.-]+)(?:/(?:issues|pull)/([1-9][0-9]*))?/?', target)
        require(m is not None and m[2] not in ('.', '..'), 'invalid_github_target')
        base = 'https://api.github.com/repos/' + m[1] + '/' + m[2]
        if m[3]:
            base += '/issues/' + m[3]
            return [get(base), get(base + '/comments?per_page=50')]
        return [get(base), get(base + '/readme', 'application/vnd.github.raw')]
    if op == 'v2ex-hot':
        return [get('https://www.v2ex.com/api/topics/hot.json')]
    m = re.fullmatch(r'https://www\.v2ex\.com/t/([1-9][0-9]*)', target)
    require(m is not None, 'invalid_v2ex_target')
    return [get('https://www.v2ex.com/api/topics/show.json?id=' + m[1]),
            get('https://www.v2ex.com/api/replies/show.json?topic_id=' + m[1] + '&page=1')]


def request(call, timeout):
    """Connect to a validated public IP, retaining TLS hostname verification. No redirects/proxy."""
    u = urlsplit(call['url'])
    require(u.hostname in ('api.github.com', 'www.v2ex.com', 'mcp.exa.ai', 'r.jina.ai') and u.scheme == 'https', 'broker_endpoint')
    if u.hostname == 'r.jina.ai':
        target_host = urlsplit(u.path[1:]).hostname
        public_addresses(target_host)
    elif u.hostname == 'mcp.exa.ai':
        args = json.loads(call['body'])['params']['arguments']
        for target in args.get('urls', []):
            public_addresses(urlsplit(target).hostname)
    addresses = public_addresses(u.hostname)
    family, kind, proto, _, address = addresses[0]
    raw = socket.socket(family, kind, proto)
    raw.settimeout(max(.1, min(timeout, 15)))
    conn = http.client.HTTPSConnection(u.hostname, timeout=timeout)
    try:
        raw.connect(address)
        conn.sock = ssl.create_default_context().wrap_socket(raw, server_hostname=u.hostname)
        path = u.path + ('?' + u.query if u.query else '')
        headers = {'Accept': call['accept'], 'Accept-Encoding': 'identity', 'User-Agent': 'rhize-agent-reach-public/1', 'Content-Type': 'application/json'}
        conn.request('POST' if call['body'] is not None else 'GET', path, body=call['body'], headers=headers)
        response = conn.getresponse()
        require(not 300 <= response.status < 400, 'redirect_denied')
        require(response.status != 429, 'rate_limited')
        require(response.status == 200, 'http_' + str(response.status))
        require(response.getheader('Content-Encoding', 'identity') == 'identity', 'encoded_response_denied')
        body = response.read(MAX_BODY + 1)
        require(len(body) <= MAX_BODY, 'provider_output_limit')
        return body.decode('utf-8', errors='strict')
    finally:
        conn.close()
        raw.close()


def public_addresses(host):
    addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    def safe(value):
        ip = ipaddress.ip_address(value)
        return ip.is_global and not ip.is_multicast and not (ip.version == 6 and
                (ip.ipv4_mapped or ip.sixtofour or ip.teredo or ip in ipaddress.ip_network('64:ff9b::/96')))
    require(addresses and all(safe(a[4][0]) for a in addresses), 'broker_private_address')
    return addresses


def bounded_request(call, timeout):
    value = dict(call, body=call['body'].decode() if call['body'] else None)
    result = subprocess.run([sys.executable, '-I', str(Path(__file__).resolve()), '--http'],
                            input=json.dumps(value).encode(), capture_output=True,
                            env={'PATH': '/usr/bin:/bin'}, timeout=max(.1, timeout))
    require(result.returncode == 0, 'broker_failed')
    answer = json.loads(result.stdout)
    require('body' in answer, answer.get('error', 'broker_failed'))
    return answer['body']


def identity():
    manifest = json.loads((CONTEXT / 'provenance.json').read_text())
    for name, expected in manifest['runtime_files'].items():
        require(name in ('Dockerfile', 'worker.py', 'adapters.py', 'LICENSE'), 'invalid_runtime_manifest')
        require(hashlib.sha256((CONTEXT / name).read_bytes()).hexdigest() == expected, 'runtime_changed')
    require(set(manifest['runtime_files']) == {'Dockerfile', 'worker.py', 'adapters.py', 'LICENSE'}, 'invalid_runtime_manifest')
    digest = hashlib.sha256()
    for name in ('Dockerfile', 'worker.py', 'adapters.py', 'LICENSE', 'provenance.json'):
        path = CONTEXT / name
        require(path.is_file() and not path.is_symlink(), 'invalid_runtime_file')
        digest.update(name.encode() + b'\0' + path.read_bytes())
    return digest.hexdigest()


def docker_binary():
    binary = shutil.which('docker')
    require(binary is not None, 'docker_required')
    return str(Path(binary).resolve())


def docker_env():
    # Local Docker Desktop only; no remote contexts or inherited provider credentials.
    require(DOCKER_CONFIG is not None, 'docker_environment_missing')
    return {'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': '/nonexistent',
            'DOCKER_CONFIG': DOCKER_CONFIG,
            'DOCKER_HOST': 'unix://' + str(Path.home() / '.docker/run/docker.sock')}


def image_id(binary, tag):
    result = subprocess.run([binary, 'image', 'inspect', tag, '--format', '{{.Id}}'], env=docker_env(), capture_output=True, timeout=10)
    value = result.stdout.decode().strip()
    require(result.returncode == 0 and re.fullmatch(r'sha256:[a-f0-9]{64}', value), 'run_setup_first')
    return value


def receipt(digest):
    path = Path.home() / '.local/share/rhize/ad-research/images' / (digest + '.json')
    require(not any(p.is_symlink() for p in [path, *path.parents]), 'invalid_image_receipt')
    return path


def runtime_args(binary, image, name):
    return [binary, 'run', '--rm', '--name', name, '--pull', 'never', '--network', 'none', '--read-only',
            '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--user', '65534:65534',
            '--pids-limit', '32', '--memory', '128m', '--memory-swap', '128m', '--cpus', '1',
            '--log-driver', 'none', '--entrypoint', 'python', '-i', image, '-I', '/app/worker.py']


def send(proc, value, deadline):
    pending = json.dumps(value, ensure_ascii=False).encode('utf-8') + b'\n'
    require(len(pending) <= 2 * MAX_BODY, 'protocol_limit')
    while pending:
        remaining = deadline - time.monotonic()
        require(remaining > 0 and select.select([], [proc.stdin], [], max(0, remaining))[1], 'worker_timeout')
        try:
            pending = pending[os.write(proc.stdin.fileno(), pending):]
        except BlockingIOError:
            continue


def run(task):
    calls = plan(task)
    binary, digest = docker_binary(), identity()
    installed = receipt(digest)
    require(installed.is_file(), 'run_setup_first')
    image = json.loads(installed.read_text())['image']
    require(image_id(binary, image) == image, 'image_changed')
    name = 'rhize-reach-' + str(uuid.uuid4())
    proc = subprocess.Popen(runtime_args(binary, image, name), env=docker_env(), stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True)
    selector = selectors.DefaultSelector()
    os.set_blocking(proc.stdin.fileno(), False)
    selector.register(proc.stdout, selectors.EVENT_READ)
    deadline, pending, seen, total = time.monotonic() + DEADLINE, b'', set(), 0
    try:
        send(proc, task, deadline)
        while time.monotonic() < deadline:
            if not selector.select(max(.01, deadline - time.monotonic())):
                raise ValueError('worker_timeout')
            chunk = os.read(proc.stdout.fileno(), 8192)
            require(bool(chunk), 'worker_incomplete')
            pending += chunk
            total += len(chunk)
            require(total <= MAX_OUTPUT, 'worker_output_limit')
            while b'\n' in pending:
                line, pending = pending.split(b'\n', 1)
                message = json.loads(line)
                require(isinstance(message, dict), 'invalid_worker_message')
                if set(message) == {'fetch'}:
                    index = message['fetch']
                    require(type(index) is int and 0 <= index < len(calls) and index not in seen, 'invalid_fetch')
                    seen.add(index)
                    body = bounded_request(calls[index], deadline - time.monotonic())
                    require(time.monotonic() < deadline, 'worker_timeout')
                    send(proc, {'body': body}, deadline)
                else:
                    error = message.get('error')
                    if error not in ('provider_error', 'unrecognized_provider_response', 'platform_blocked', 'not_found', 'unsupported_operation', 'provider_parse_error', 'protocol_limit', 'invalid_response'):
                        error = 'invalid_worker_message'
                    require(set(message) == {'items'} and isinstance(message['items'], list), error)
                    require(len(seen) == len(calls) and len(message['items']) <= task['limit'], 'incomplete_result')
                    require(not pending, 'trailing_worker_output')
                    proc.stdin.close()
                    require(proc.wait(timeout=max(.1, deadline-time.monotonic())) == 0, 'worker_failed')
                    require(not proc.stdout.read(MAX_OUTPUT + 1), 'trailing_worker_output')
                    return select_items(message['items'], task['operation'])
        raise ValueError('worker_timeout')
    finally:
        selector.close()
        try:
            subprocess.run([binary, 'rm', '-f', name], env=docker_env(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=5)
            if not proc.stdin.closed:
                proc.stdin.close()
            proc.stdout.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('setup', help='Build the pinned public-adapter image (Docker Desktop required).')
    collect = sub.add_parser('collect')
    collect.add_argument('--host', required=True, choices=('claude', 'codex'))
    collect.add_argument('--operation', required=True, choices=OPERATIONS)
    collect.add_argument('--query', default='')
    collect.add_argument('--target', default='')
    collect.add_argument('--limit', type=int, default=5)
    args = vars(parser.parse_args())
    command = args.pop('command')
    run_id = str(uuid.uuid4())
    try:
        if command == 'setup':
            tag = 'rhize-agent-reach:' + identity()
            subprocess.run([docker_binary(), 'build', '--network', 'none', '-t', tag, str(CONTEXT)], env=docker_env(), check=True, timeout=180)
            value = {'ok': True, 'image': image_id(docker_binary(), tag), 'source_sha256': identity()}
            path = receipt(identity())
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd, temporary = tempfile.mkstemp(prefix='.image-', dir=path.parent)
            try:
                with os.fdopen(fd, 'w') as output:
                    json.dump(value, output)
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temporary, path)
            finally:
                Path(temporary).unlink(missing_ok=True)
            print(json.dumps(value))
            return 0
        collected = run(args)
        result = {'schema': 1, 'run_id': run_id, **args, 'provider': 'agent-reach-public', 'status': 'retrieved',
                  'captured_at': dt.datetime.now(dt.timezone.utc).isoformat(), **collected,
                  'source_sha256': identity(), 'untrusted_data': True, 'truncated': None,
                  'coverage': 'Public sample only. GitHub comments limited to first50; V2EX replies firstpage; search/reader may truncate. No complete thread, population, popularity or trend claim; reader-service redirects are outside local observation.'}
        print(json.dumps(result, ensure_ascii=True))
        return 0
    except Exception as exc:
        error = str(exc)[:120] if isinstance(exc, ValueError) else type(exc).__name__
        print(json.dumps({'schema': 1, 'run_id': run_id, **args, 'provider': 'agent-reach-public',
                          'captured_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'untrusted_data': True,
                          'status': 'unavailable', 'items': [], 'error': error}))
        return 2


if __name__ == '__main__':
    if sys.argv[1:] == ['--http']:
        try:
            raw = sys.stdin.buffer.read(65537)
            require(len(raw) <= 65536, 'request_limit')
            value = json.loads(raw)
            value['body'] = value['body'].encode() if value['body'] else None
            print(json.dumps({'body': request(value, 15)}))
        except Exception as exc:
            print(json.dumps({'error': str(exc)[:120] if isinstance(exc, ValueError) else type(exc).__name__}))
    else:
        def interrupted(signum, frame):
            raise KeyboardInterrupt()
        signal.signal(signal.SIGTERM, interrupted)
        with tempfile.TemporaryDirectory(prefix='rhize-docker-config-') as DOCKER_CONFIG:
            sys.exit(main())
