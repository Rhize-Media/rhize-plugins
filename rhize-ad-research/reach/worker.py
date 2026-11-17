"""Disposable parser worker. Network operations are indexes into the sealed parent plan."""
import importlib.util
import json
import sys
import signal

# Bound container lifetime even if the coordinating process is killed.
signal.alarm(50)

spec = importlib.util.spec_from_file_location('adapters', '/app/adapters.py')
adapters = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapters)


def receive():
    line = sys.stdin.buffer.readline(2 * 1024 * 1024 + 1)
    if not line.endswith(b'\n') or len(line) > 2 * 1024 * 1024:
        raise ValueError('protocol_limit')
    return json.loads(line)


def fetch(index):
    print(json.dumps({'fetch': index}), flush=True)
    value = receive()
    if set(value) != {'body'} or not isinstance(value['body'], str):
        raise ValueError('invalid_response')
    return value['body']


def collect(task):
    op = task['operation']
    body = fetch(0)
    if op.endswith('search') and op != 'github-search' or op == 'exa-read':
        payloads = [s[5:].strip() for s in body.splitlines() if s.startswith('data:')] or [body]
        value = json.loads(payloads[-1])
        result = value.get('result') or {}
        if 'error' in value or result.get('isError'):
            raise ValueError('provider_error')
        text = '\n'.join(c.get('text', '') for c in result.get('content', []) if c.get('type') == 'text')
        items = adapters._parse_exa_text(text)
        if not items:
            raise ValueError('unrecognized_provider_response')
        return items[:task['limit']]
    if op == 'jina-read':
        if adapters._is_antibot_page(body.encode()):
            raise ValueError('platform_blocked')
        if not body.strip() or 'Markdown Content:' not in body:
            raise ValueError('unrecognized_provider_response')
        return [adapters._parse_jina(task['target'], body)]
    value = json.loads(body)
    if op == 'github-search':
        if not isinstance(value.get('items'), list):
            raise ValueError('unrecognized_provider_response')
        return [adapters._repo_item(r) for r in value['items'][:task['limit']]]
    if op == 'github-read':
        if '/issues/' not in task['target'] and '/pull/' not in task['target']:
            return [adapters._repo_item(value, fetch(1))]
        comments = json.loads(fetch(1))
        if not isinstance(comments, list):
            raise ValueError('unrecognized_provider_response')
        text = '\n\n'.join([value.get('body') or ''] + [c.get('body') or '' for c in comments])
        return [adapters.make_item(title=value.get('title'), url=value.get('html_url'),
                                  published_at=value.get('created_at'), text=text)]
    if op == 'v2ex-hot':
        if not isinstance(value, list):
            raise ValueError('unrecognized_provider_response')
        return [adapters._topic_item(t) for t in value[:task['limit']]]
    if op == 'v2ex-read':
        if not isinstance(value, list) or not value:
            raise ValueError('not_found')
        replies = json.loads(fetch(1))
        if not isinstance(replies, list):
            raise ValueError('unrecognized_provider_response')
        text = '\n\n'.join([value[0].get('content') or ''] + [r.get('content') or '' for r in replies])
        return [adapters._topic_item(value[0], text=text)]
    raise ValueError('unsupported_operation')


try:
    task = receive()
    rows = collect(task)
    # Public bodies are evidence, never commands; minimize profile/raw metadata.
    rows = [{k: v for k, v in row.items() if k not in ('raw', 'author')} for row in rows]
    print(json.dumps({'items': rows}), flush=True)
except Exception as exc:
    print(json.dumps({'error': str(exc)[:100] if isinstance(exc, ValueError) else 'provider_parse_error'}), flush=True)
    sys.exit(1)
