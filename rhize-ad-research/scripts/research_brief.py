#!/usr/bin/env python3
"""Validate and render host-captured research. No retrieval or session access."""
import argparse
import importlib.util
import importlib.machinery
from contextlib import contextmanager
import csv
import datetime as dt
import io
import ipaddress
import json
import os
import re
import stat
import sys
import uuid
import unicodedata
from pathlib import Path
from urllib.parse import urlsplit

MAX_BYTES = 262144
PROVIDERS = {'native-web', 'public-http', 'official-mcp', 'agent-reach-public'}
PURPOSES = {'customer', 'content', 'competitive', 'product', 'technical', 'topics'}


class Invalid(ValueError):
    pass


def require(ok, reason):
    if not ok:
        raise Invalid(reason)


def fields(value, names):
    require(isinstance(value, dict) and set(value) == set(names.split()), 'invalid_fields')


def text(value, limit=2000):
    require(isinstance(value, str) and 0 < len(value) <= limit, 'invalid_text')
    require(not any((unicodedata.category(c) in {'Cc', 'Cf', 'Cs'} and c not in '\n\t') or c in '\u2028\u2029' for c in value), 'invalid_control_character')
    # Pattern checks are not DLP; callers must minimize personal/confidential data.
    require(not re.search(r'(?i)(bearer\s+\S+|(?:sk-|ghp_|github_pat_)[A-Za-z0-9_-]{12,}|(?:password|api[_-]?key|cookie)\s*[:=]\s*\S+)', value), 'credential_like_content')
    return value


def items(value, cap):
    require(isinstance(value, list) and len(value) <= cap, 'invalid_list')
    return value


def public_url(value):
    text(value, 2048)
    require(value.isascii() and not re.search(r'[\s\\<>"`?#]', value), 'invalid_url')
    try:
        u = urlsplit(value)
        require(u.scheme == 'https' and u.hostname and not u.username and not u.password
                and u.port is None and not u.query and not u.fragment, 'noncanonical_public_url')
        host = u.hostname
        require(u.netloc == host and host == host.lower() and not host.endswith('.'), 'noncanonical_public_url')
        require('.' in host and not host.endswith(('.local', '.internal', '.localhost', '.test', '.lan', '.home.arpa', '.corp', '.intranet'))
                and host not in {'localhost', 'metadata.google.internal'}, 'private_url')
        try:
            require(ipaddress.ip_address(host).is_global, 'private_url')
        except ValueError as exc:
            if isinstance(exc, Invalid):
                raise
            require(bool(re.fullmatch(r'[a-z0-9.-]+', host)) and bool(re.fullmatch(r'[a-z]{2,63}|xn--[a-z0-9-]+', host.rsplit('.', 1)[-1])), 'invalid_hostname')
    except (ValueError, TypeError) as exc:
        if isinstance(exc, Invalid):
            raise
        raise Invalid('invalid_url') from None
    return value


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value, 'duplicate_json_key')
        value[key] = item
    return value


def validate(value):
    fields(value, 'schema run_id host purpose question queries window captured_at capture_method sources findings limitations')
    require(type(value['schema']) is int and value['schema'] == 1, 'unsupported_schema')
    require(isinstance(value['run_id'], str), 'invalid_run_id')
    try:
        require(str(uuid.UUID(value['run_id'])) == value['run_id'], 'invalid_run_id')
        captured = dt.datetime.fromisoformat(value['captured_at'].replace('Z', '+00:00'))
        require(captured.utcoffset() is not None, 'missing_timezone')
    except Invalid:
        raise
    except (ValueError, TypeError, AttributeError):
        raise Invalid('invalid_run_identity_or_time') from None
    require(value['host'] in ('claude', 'codex'), 'unsupported_host')
    require(isinstance(value['purpose'], str) and value['purpose'] in PURPOSES, 'unsupported_purpose')
    require(value['capture_method'] in ('host_transcribed', 'tool_serialized'), 'invalid_capture_method')
    text(value['question'], 500)
    for query in items(value['queries'], 10):
        text(query, 500)
    fields(value['window'], 'start end')
    try:
        dates = [dt.date.fromisoformat(value['window'][key]) for key in ('start', 'end')]
        require(dates[0] <= dates[1], 'reversed_window')
    except Invalid:
        raise
    except (ValueError, TypeError):
        raise Invalid('invalid_window') from None
    sources, urls = {}, set()
    for source in items(value['sources'], 20):
        fields(source, 'id provider url title published_at status summary coverage')
        sid = text(source['id'], 80)
        require(bool(re.fullmatch(r'[A-Za-z0-9_-]+', sid)) and sid not in sources, 'duplicate_or_invalid_source_id')
        require(isinstance(source['provider'], str) and source['provider'] in PROVIDERS, 'provider_not_qualified')
        url = public_url(source['url'])
        require(url not in urls, 'duplicate_source_url')
        urls.add(url)
        text(source['title'], 300)
        require(source['status'] in ('retrieved', 'unavailable'), 'invalid_source_status')
        if source['published_at'] is not None:
            try:
                dt.date.fromisoformat(source['published_at'])
            except (ValueError, TypeError):
                raise Invalid('invalid_source_date') from None
        if source['status'] == 'retrieved':
            text(source['summary'])
        else:
            require(source['summary'] is None, 'unavailable_summary')
        text(source['coverage'], 500)
        sources[sid] = source
    for finding in items(value['findings'], 10):
        fields(finding, 'claim source_ids')
        text(finding['claim'])
        refs = items(finding['source_ids'], 20)
        require(bool(refs) and all(isinstance(ref, str) for ref in refs), 'missing_citations')
        require(len(refs) == len(set(refs)), 'duplicate_citation')
        require(all(ref in sources and sources[ref]['status'] == 'retrieved' for ref in refs), 'unavailable_citation')
    require(bool(value['limitations']), 'missing_limitations')
    for limitation in items(value['limitations'], 20):
        text(limitation, 1000)
    return value


def markdown(text_value):
    return re.sub(r'([\\`*_{}\[\]()<>#+.!|~-])', r'\\\1', text_value).replace('\n', ' ')


def render(value, output_format):
    validate(value)
    if output_format == 'json':
        return json.dumps(value, ensure_ascii=False, indent=2) + '\n'
    if output_format == 'csv':
        out = io.StringIO(newline='')
        writer = csv.writer(out)
        writer.writerow(['id', 'provider', 'url', 'title', 'published_at', 'status', 'summary', 'coverage'])
        for source in value['sources']:
            row = [source[k] or '' for k in ('id', 'provider', 'url', 'title', 'published_at', 'status', 'summary', 'coverage')]
            writer.writerow(["'" + cell if cell.lstrip().startswith(('=', '+', '-', '@')) else cell for cell in row])
        return out.getvalue()
    require(output_format == 'markdown', 'invalid_format')
    lines = ['# Research brief', '', markdown(value['question']), '',
             f"Run: {value['run_id']} | Host: {value['host']} | Capture: {value['capture_method']}",
             f"Window: {value['window']['start']} to {value['window']['end']} | Captured: {value['captured_at']}",
             '', 'Host-captured evidence; validation does not attest retrieval, truth or completeness.', '', '## Findings', '']
    for finding in value['findings']:
        lines.append('- ' + markdown(finding['claim']) + ' [' + ', '.join(finding['source_ids']) + ']')
    if not value['findings']:
        lines.append('Insufficient evidence for findings.')
    lines += ['', '## Sources', '']
    for source in value['sources']:
        lines += [f"- {source['id']}: {markdown(source['title'])} — <{source['url']}>",
                  f"  {source['status']}; {markdown(source['coverage'])}"]
    lines += ['', '## Limitations', ''] + ['- ' + markdown(x) for x in value['limitations']]
    return '\n'.join(lines) + '\n'



@contextmanager
def usage_context(host, operation, provider):
    # Optional sibling loaded by exact path: -I excludes the script directory from imports.
    noop = (lambda *args, **kwargs: None, lambda exc: 'unclassified')
    try:
        path = Path(__file__).resolve().with_name('usage_telemetry.py')
        if path.is_symlink():
            raise ValueError('telemetry_module_symlink')
        class SourceOnlyLoader(importlib.machinery.SourceFileLoader):
            def get_code(self, fullname):
                return self.source_to_code(self.get_data(self.path), self.path)
        loader = SourceOnlyLoader('rhize_ad_usage', str(path))
        spec = importlib.util.spec_from_file_location('rhize_ad_usage', path, loader=loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        context = module.measure(host, operation, provider)
        classify = module.classify
        update = context.__enter__()
    except Exception:
        yield noop
        return
    def safe_update(*args, **kwargs):
        try:
            update(*args, **kwargs)
        except Exception:
            pass
    def safe_classify(exc):
        try:
            return classify(exc)
        except Exception:
            return 'unclassified'
    try:
        yield safe_update, safe_classify
    finally:
        try:
            context.__exit__(*sys.exc_info())
        except Exception:
            pass

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--host', choices=['claude', 'codex'], default='unknown', help='Invoking host, independent of evidence collector.')
    parser.add_argument('--format', choices=['json', 'csv', 'markdown'], default='markdown')
    args = parser.parse_args(argv)
    with usage_context(args.host, 'brief-' + args.format, 'offline-renderer') as (metric, error_class):
        try:
            # This command reads one explicitly supplied local evidence file, not host/session configuration.
            fd = os.open(args.input, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, 'rb') as stream:
                require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), 'input_not_regular')
                raw = stream.read(MAX_BYTES + 1)
            require(len(raw) <= MAX_BYTES, 'input_too_large')
            value = json.loads(raw, object_pairs_hook=unique_object)
            print(render(value, args.format), end='')
            sys.stdout.flush()
            try:
                metric('rendered', returned=sum(s['status'] == 'retrieved' for s in value['sources']))
            except Exception:
                metric('rendered', 'unclassified')
            return 0
        except BrokenPipeError:
            metric('output_failed', 'broken_pipe')
            return 2
        except (OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
            metric('held', 'validation' if isinstance(exc, Invalid) else error_class(exc))
            reason = str(exc) if isinstance(exc, Invalid) else 'invalid_or_unreadable_evidence'
            print(json.dumps({'status': 'held', 'reason': reason}), file=sys.stderr)
            return 2


if __name__ == '__main__':
    raise SystemExit(main())
