#!/usr/bin/env python3
"""Bounded official Meta MCP research journal; native hosts own authentication and retrieval."""
import argparse
import importlib.util
import importlib.machinery
from contextlib import contextmanager
import csv
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import sys
import tempfile
import uuid

ROOT = Path.home() / 'Library/Application Support/Rhize Ad Research'
ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$')
MAX_RESPONSE = 8 * 1024 * 1024

class Blocked(Exception):
    pass

def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()

def ident(value):
    if not ID.fullmatch(value):
        raise Blocked('Invalid identifier')
    return value

def safe_dir(path, create=True):
    path = Path(path).expanduser()
    if '..' in path.parts:
        raise Blocked('Parent traversal is not supported')
    path = path.absolute()
    # Refuse symlinks in every existing component, including user-selected workspaces.
    for component in (path, *path.parents):
        if component.is_symlink():
            raise Blocked('Symlink paths are not supported')
    if create: path.mkdir(mode=0o700, parents=True, exist_ok=True)
    elif not path.exists(): raise Blocked('workspace_missing')
    if not path.is_dir():
        raise Blocked('Expected directory')
    return path

def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise Blocked('duplicate_json_key')
        result[key] = value
    return result


def decode(value):
    return json.loads(value, object_pairs_hook=unique_object)


def read(path):
    path = Path(path)
    if path.is_symlink() or any(part.is_symlink() for part in path.parents):
        raise Blocked('Symlink files are not supported')
    with path.open(encoding='utf-8') as f:
        raw = f.read(MAX_RESPONSE + 1)
    if len(raw.encode('utf-8')) > MAX_RESPONSE: raise Blocked('response_too_large')
    return decode(raw)

def write(path, value):
    path = Path(path)
    safe_dir(path.parent)
    if path.is_symlink():
        raise Blocked('Symlink files are not supported')
    fd, temp = tempfile.mkstemp(prefix='.write-', dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(value, f, ensure_ascii=False, sort_keys=True, indent=2)
            f.write('\n')
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)

def registry():
    return safe_dir(ROOT)

def key(client, account):
    return digest([ident(client), ident(account)])

class Lock:
    def __init__(self, client, account):
        self.path = registry() / (key(client, account) + '.lock')
    def __enter__(self):
        self.fd = os.open(self.path, os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        try:
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(self.fd)
            raise Blocked('active_collector') from None
        os.ftruncate(self.fd, 0)
        os.write(self.fd, json.dumps({'pid': os.getpid(), 'host': socket.gethostname(), 'owner': uuid.uuid4().hex, 'at': now()}).encode())
        os.fsync(self.fd)
        return self
    def __exit__(self, *_):
        fcntl.flock(self.fd, fcntl.LOCK_UN)
        os.close(self.fd)

def mapping(client, account):
    try: data = read(registry() / 'registry.json')
    except FileNotFoundError: raise Blocked('Client/account not set up') from None
    try:
        return safe_dir(data[key(client, account)]['workspace'], create=False)
    except KeyError:
        raise Blocked('Client/account not set up') from None

def run_path(workspace, run):
    return workspace / 'runs' / ident(run) / 'manifest.json'

def load_run(workspace, run_id, client, account):
    try: run = read(run_path(workspace, run_id))
    except FileNotFoundError: raise Blocked('run_not_found') from None
    if run.get('client') != client or run.get('account') != account or run.get('id') != run_id:
        raise Blocked('run_scope_mismatch')
    return run

def save_run(workspace, run):
    write(run_path(workspace, run['id']), run)

def workspaces_overlap(first, second):
    if first == second or first in second.parents or second in first.parents: return True
    if first.exists() and second.exists():
        return any(os.path.samefile(first, p) for p in (second, *second.parents)) or any(os.path.samefile(second, p) for p in first.parents)
    return False


def setup(args):
    with Lock('registry', 'global'):
        workspace = safe_dir(args.workspace)
        path = registry() / 'registry.json'
        data = read(path) if path.exists() else {}
        k = key(args.client, args.account)
        if any(other != k and workspaces_overlap(Path(value['workspace']), workspace) for other, value in data.items()):
            raise Blocked('Workspace already belongs to another client/account')
        if k in data and data[k]['workspace'] != str(workspace):
            raise Blocked('Workspace relocation is not supported')
        data[k] = {'client': args.client, 'account': args.account, 'workspace': str(workspace)}
        write(path, data)
        return data[k]

def export(args):
    workspace = mapping(args.client, args.account)
    run = load_run(workspace, args.run, args.client, args.account)
    verify_evidence(workspace, run)
    if run.get('provider') == PROVIDER and run['lifecycle'] != 'succeeded': raise Blocked('no_exportable_sample')
    if run['lifecycle'] not in ('succeeded', 'failed', 'cancelled'): raise Blocked('Run is not terminal')
    records_path = run_path(workspace, args.run).parent / 'records.json'
    if not records_path.exists(): raise Blocked('No fetched records available')
    records = read(records_path)
    output = safe_dir(args.output)
    rows = []
    for item in records:
        rows.append({k: item.get(k) for k in FIELDS + ['created_at', 'query_urls']})
        rows[-1]['source_url'] = 'https://www.facebook.com/ads/library/?id=' + str(item['ad_id']) if str(item['ad_id']).isdigit() else None
    write(output / (run['id'] + '-research.json'), {'run': {k: run.get(k) for k in ('id', 'provider', 'service', 'input', 'response_hash', 'records_hash', 'capture_host', 'capture_method', 'observed_at', 'ingested_at', 'estimated_total_count', 'pagination_supported', 'lifecycle', 'coverage', 'result', 'billing', 'block_reason', 'fetched', 'normalized', 'quarantined', 'duplicates', 'coverage_reasons', 'provider_errors')}, 'records': rows})
    csv_path = output / (run['id'] + '-research.csv')
    if csv_path.is_symlink(): raise Blocked('Symlink files are not supported')
    fd, temp = tempfile.mkstemp(prefix='.csv-', dir=output)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS + ['created_at', 'query_urls'])
            writer.writeheader()
            for row in rows:
                writer.writerow({k: ("'" + str(v) if isinstance(v, str) and v.lstrip().startswith(('=', '+', '-', '@', '\t', '\r')) else json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v) for k, v in row.items()})
            f.flush(); os.fsync(f.fileno())
        os.replace(temp, csv_path)
    finally:
        if os.path.exists(temp): os.unlink(temp)
    return {'json': str(output / (run['id'] + '-research.json')), 'csv': str(csv_path), 'records': len(rows), 'lifecycle': run['lifecycle'], 'coverage': run.get('coverage'), 'result': run.get('result'), 'billing': run.get('billing'), 'coverage_reasons': run.get('coverage_reasons', [])}

PROVIDER = 'meta-ads-mcp'
ENDPOINT = 'https://mcp.facebook.com/ads'
TOOL = 'ads_library_search'
FILTERS = {'search_terms', 'page_ids', 'countries', 'ad_active_status', 'ad_type', 'limit'}
PROVENANCE = {'advertiser_job', 'advertiser_request', 'client_conversation_id', 'scheduled_task_run'}
FIELDS = ['ad_id', 'advertiser', 'page_id', 'title', 'text', 'active_status', 'start_date',
          'end_date', 'format', 'platforms', 'observed_at', 'source_url', 'query', 'query_service', 'relevance']


def query_validate(query):
    if not isinstance(query, dict) or set(query) - FILTERS:
        raise Blocked('unsupported_query_or_pagination')
    if type(query.get('limit')) is not int or not 1 <= query['limit'] <= 50:
        raise Blocked('limit_must_be_1_to_50')
    if query.get('ad_active_status') not in ('ALL', 'ACTIVE', 'INACTIVE') or query.get('ad_type') != 'ALL':
        raise Blocked('unsupported_status_or_ad_type')
    countries = query.get('countries')
    if not isinstance(countries, list) or not 1 <= len(countries) <= 10 or any(not isinstance(c, str) or not re.fullmatch('[A-Z]{2}', c) for c in countries):
        raise Blocked('invalid_countries')
    pages, terms = query.get('page_ids'), query.get('search_terms')
    if pages is not None and (not isinstance(pages, list) or not 1 <= len(pages) <= 10 or any(not isinstance(p, str) or not re.fullmatch('[0-9]{1,32}', p) for p in pages)):
        raise Blocked('invalid_page_ids')
    if terms is not None and (not isinstance(terms, str) or not terms.strip() or len(terms) > 300):
        raise Blocked('invalid_search_terms')
    if not pages and not terms:
        raise Blocked('select_keywords_or_pages_for_bounded_research')
    return query


def plan(args):
    query = {'countries': args.countries, 'limit': args.limit, 'ad_active_status': args.status, 'ad_type': 'ALL'}
    if args.search_terms: query['search_terms'] = args.search_terms
    if args.page_ids: query['page_ids'] = args.page_ids
    query_validate(query)
    with Lock(args.client, args.account):
        workspace = mapping(args.client, args.account)
        run = {'id': uuid.uuid4().hex, 'created_at': now(), 'client': args.client, 'account': args.account,
               'provider': PROVIDER, 'tool': TOOL, 'capture_host': args.host, 'service': args.service, 'input': query,
               'input_hash': digest(query), 'lifecycle': 'planned', 'coverage': 'unknown',
               'result': 'unknown', 'billing': 'not_managed_by_plugin', 'fetched': 0, 'normalized': 0,
               'quarantined': 0, 'duplicates': 0, 'block_reason': None, 'pagination_supported': False}
        save_run(workspace, run)
        return run


def operator_status(run):
    if run.get('provider') != PROVIDER:
        return 'Historical Apify run (read-only)', ('Inspect/export retained evidence; paid provider retired' if run.get('lifecycle') in ('succeeded', 'failed', 'cancelled') else 'Non-terminal historical run: inspect retained files only; paid provider retired')
    if run.get('block_reason'):
        return 'Held: ' + run['block_reason'], 'Inspect retained response; do not overwrite or silently retry'
    if run.get('lifecycle') == 'capturing':
        return 'Response sealed; processing incomplete', 'Resume locally without a provider call; if raw write was interrupted, supply the identical inbox'
    if run.get('result') == 'unverified_empty':
        return 'No ads returned; absence unverified', 'Review query and provider coverage; this does not prove no ads exist'
    if run['lifecycle'] == 'succeeded':
        return ('Partial sample collected' if run.get('quarantined') else 'Bounded sample collected'), 'Export and review sources; not a complete inventory or performance ranking'
    return 'Awaiting native Meta MCP response', 'Use the emitted request in this host, save its exact response, then resume'


def timestamp(value):
    if value is None: return None
    if type(value) is not int or value < 0: raise ValueError('invalid_timestamp')
    return dt.datetime.fromtimestamp(value, dt.timezone.utc).isoformat()


def normalize(item, run):
    if not isinstance(item, dict): raise ValueError('invalid_ad')
    ad_id, page = item.get('id'), item.get('page_id')
    if type(ad_id) not in (str, int) or not re.fullmatch('[0-9]{1,32}', str(ad_id)):
        raise ValueError('invalid_ad_id')
    if type(page) not in (str, int) or not re.fullmatch('[0-9]{1,32}', str(page)):
        raise ValueError('invalid_page_id')
    name = item.get('page_name')
    if not isinstance(name, str) or not name.strip(): raise ValueError('invalid_page_name')
    if run['input'].get('page_ids') and str(page) not in run['input']['page_ids']:
        raise ValueError('page_filter_mismatch')
    for field in ('ad_creative_body', 'ad_creative_link_title'):
        if item.get(field) is not None and not isinstance(item[field], str): raise ValueError('invalid_creative')
    for text in (name, item.get('ad_creative_body'), item.get('ad_creative_link_title')):
        if text is not None: text.encode('utf-8')
    return {'ad_id': str(ad_id), 'advertiser': name, 'page_id': str(page),
            'title': item.get('ad_creative_link_title'), 'text': item.get('ad_creative_body'),
            'active_status': None, 'start_date': timestamp(item.get('ad_delivery_start_time')),
            'created_at': timestamp(item.get('ad_creation_time')), 'end_date': None,
            'format': None, 'platforms': None, 'observed_at': run['observed_at'],
            'source_url': 'https://www.facebook.com/ads/library/?id=' + str(ad_id),
            'query': run['input'], 'query_service': run['service'], 'relevance': 'unverified'}


def payload_from(envelope, run):
    if not isinstance(envelope, dict) or envelope.get('provider') != PROVIDER or envelope.get('tool') != TOOL:
        raise Blocked('response_provider_mismatch')
    if envelope.get('run_id') != run['id'] or envelope.get('input_hash') != run['input_hash']:
        raise Blocked('response_run_mismatch')
    if envelope.get('capture_host') != run['capture_host']:
        raise Blocked('response_host_mismatch')
    if envelope.get('capture_method') not in ('tool_serialized', 'host_transcribed'):
        raise Blocked('invalid_capture_method')
    try:
        captured = dt.datetime.fromisoformat(envelope['captured_at'].replace('Z', '+00:00'))
        if captured.tzinfo is None or not dt.datetime.fromisoformat(run['created_at']) <= captured <= dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=5):
            raise ValueError()
    except (KeyError, TypeError, ValueError):
        raise Blocked('invalid_capture_time') from None
    request = envelope.get('request')
    if not isinstance(request, dict) or set(request) - FILTERS - PROVENANCE:
        raise Blocked('unsupported_request_fields')
    if {k: v for k, v in request.items() if k in FILTERS} != run['input']:
        raise Blocked('response_query_mismatch')
    for field in PROVENANCE & request.keys():
        value = request[field]
        if field == 'scheduled_task_run':
            valid = type(value) is bool
        else:
            valid = isinstance(value, str) and 0 < len(value) <= 2000
        if not valid: raise Blocked('invalid_request_provenance')
    value = envelope.get('response')
    if not isinstance(value, dict): raise Blocked('invalid_response')
    if value.get('isError'): raise Blocked('provider_error')
    if isinstance(value.get('structuredContent'), dict):
        value = value['structuredContent']
    elif 'content' in value:
        blocks = value['content']
        if not isinstance(blocks, list) or len(blocks) != 1 or (blocks[0].get('type') if isinstance(blocks[0], dict) else None) != 'text':
            raise Blocked('invalid_response_content')
        value = decode(blocks[0]['text'])
    if isinstance(value, dict) and 'results' in value:
        value = value['results'] if isinstance(value['results'], dict) else decode(value['results'])
    if not isinstance(value, dict) or value.get('error'):
        raise Blocked('provider_error')
    if set(value) & {'paging', 'pagination', 'next', 'cursor', 'after', 'has_more'}:
        raise Blocked('unexpected_pagination')
    if set(value) - {'ads', 'estimated_total_count'}:
        raise Blocked('response_schema_drift')
    ads, total = value.get('ads'), value.get('estimated_total_count')
    if not isinstance(ads, list) or len(ads) > run['input']['limit'] or type(total) is not int or total < 0:
        raise Blocked('invalid_response_shape')
    return value


def verify_evidence(workspace, run):
    if run.get('provider') != PROVIDER: return
    if digest(run['input']) != run['input_hash']: raise Blocked('input_changed')
    directory = run_path(workspace, run['id']).parent
    for filename, field in (('response.json', 'response_hash'), ('records.json', 'records_hash')):
        expected = run.get(field)
        required = expected is not None or run['lifecycle'] == 'succeeded'
        if not required: continue
        path = directory / filename
        if not path.exists(): raise Blocked('evidence_missing:' + filename)
        if expected is None or digest(read(path)) != expected: raise Blocked('evidence_changed:' + filename)


def collect(args):
    with Lock(args.client, args.account):
        workspace = mapping(args.client, args.account)
        run = load_run(workspace, args.run, args.client, args.account)
        if run.get('provider') != PROVIDER: raise Blocked('legacy_provider_retired_read_only')
        query_validate(run['input'])
        if digest(run['input']) != run['input_hash']: raise Blocked('input_changed')
        directory = run_path(workspace, run['id']).parent
        raw = directory / 'response.json'
        terminal = run['lifecycle'] in ('succeeded', 'failed', 'cancelled')
        if terminal:
            verify_evidence(workspace, run)
            if args.response and digest(read(args.response)) != run.get('response_hash'):
                raise Blocked('immutable_response_conflict')
            args._usage_reused = True
            return {'run': run, 'operator_status': operator_status(run)[0]}
        if args.response:
            try: incoming = read(args.response)
            except FileNotFoundError: raise Blocked('response_file_not_found') from None
            incoming_hash = digest(incoming)
            if run.get('response_hash') and incoming_hash != run['response_hash']:
                raise Blocked('immutable_response_conflict')
            if raw.exists() and digest(read(raw)) != incoming_hash:
                raise Blocked('immutable_response_conflict')
            if not run.get('response_hash'):
                run.update(response_hash=incoming_hash, ingested_at=now(), lifecycle='capturing')
                save_run(workspace, run)
            if not raw.exists(): write(raw, incoming)
        if not raw.exists():
            if run.get('response_hash'): raise Blocked('evidence_missing:response.json')
            run['lifecycle'] = 'awaiting_response'
            save_run(workspace, run)
            return {'run': run, 'endpoint': ENDPOINT, 'tool': TOOL, 'request': run['input'],
                    'inbox_path': str(directory / 'inbox.json'),
                    'envelope': {'provider': PROVIDER, 'tool': TOOL, 'run_id': run['id'],
                                 'input_hash': run['input_hash'], 'capture_host': run['capture_host'],
                                 'capture_method': 'host_transcribed', 'captured_at': None,
                                 'request': run['input'], 'response': None},
                    'action': 'Call native MCP once; save envelope in inbox; resume --response INBOX_PATH',
                    'pagination': 'unsupported; never invent cursors, offsets or repeated-query pagination'}
        if not run.get('response_hash'): raise Blocked('unsealed_response')
        verify_evidence(workspace, run)
        try:
            envelope = read(raw)
            payload = payload_from(envelope, run)
            run.update(observed_at=envelope['captured_at'], capture_method=envelope['capture_method'])
            records, seen, quarantine, duplicates = [], set(), 0, 0
            for item in payload['ads']:
                try: record = normalize(item, run)
                except (ValueError, TypeError, OverflowError, OSError):
                    quarantine += 1
                    continue
                if record['ad_id'] in seen:
                    duplicates += 1
                    continue
                seen.add(record['ad_id']); records.append(record)
            reasons = ['no_pagination', 'estimated_count_not_inventory', 'relevance_unverified']
            if len(payload['ads']) >= run['input']['limit'] or payload['estimated_total_count'] > len(payload['ads']): reasons.append('capped')
            if payload['estimated_total_count'] < len(payload['ads']) or (not payload['ads'] and payload['estimated_total_count']): reasons.append('estimate_mismatch')
            if not records: reasons.append('unverified_empty')
            if quarantine: reasons.append('parse_incomplete')
        except (Blocked, ValueError, TypeError, KeyError, AttributeError) as exc:
            reason = str(exc) if isinstance(exc, Blocked) else 'invalid_response_shape'
            run.update(lifecycle='failed', coverage='unknown', result='unknown', block_reason=reason)
            save_run(workspace, run)
            raise Blocked(reason) from None
        # IO interruption leaves capturing state; resume derives the same records from sealed evidence.
        write(directory / 'records.json', records)
        run.update(lifecycle='failed' if quarantine and not records else 'succeeded',
                   coverage='sample' if records else 'unknown',
                   result='nonempty' if records else ('all_quarantined' if quarantine else 'unverified_empty'),
                   fetched=len(payload['ads']), normalized=len(records), quarantined=quarantine,
                   duplicates=duplicates, estimated_total_count=payload['estimated_total_count'],
                   coverage_reasons=reasons, records_hash=digest(records),
                   block_reason='all_quarantined' if quarantine and not records else None)
        save_run(workspace, run)
        return {'run': run, 'operator_status': operator_status(run)[0]}



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
    sub = parser.add_subparsers(dest='command', required=True)
    def scope(p, host_required=False):
        p.add_argument('--host', choices=['claude', 'codex'], required=host_required, default='unknown')
        p.add_argument('--client', required=True); p.add_argument('--account', required=True)
    p = sub.add_parser('setup'); scope(p); p.add_argument('--workspace', required=True)
    p = sub.add_parser('doctor'); scope(p)
    p = sub.add_parser('list'); scope(p)
    sub.add_parser('provider-check').add_argument('--host', choices=['claude', 'codex'], default='unknown')
    p = sub.add_parser('plan'); scope(p, host_required=True)
    p.add_argument('--service', required=True, choices=['detailing', 'ceramic-coating'])
    p.add_argument('--search-terms'); p.add_argument('--page-ids', nargs='+')
    p.add_argument('--countries', nargs='+', default=['US']); p.add_argument('--limit', type=int, default=25)
    p.add_argument('--status', choices=['ACTIVE','ALL','INACTIVE'], default='ACTIVE')
    for name in ('collect', 'resume', 'status', 'export'):
        p = sub.add_parser(name); scope(p); p.add_argument('--run', required=True)
        if name in ('collect', 'resume'): p.add_argument('--response')
        if name == 'export': p.add_argument('--output', required=True)
    a = parser.parse_args(argv)
    if sys.version_info < (3, 11):
        print(json.dumps({'error':'python_3_11_required'}), file=sys.stderr); return 2
    with usage_context(a.host, 'meta-' + a.command, 'meta-response-journal') as (metric, error_class):
        try:
            if a.command == 'setup': result = setup(a)
            elif a.command == 'provider-check':
                result = {'provider': PROVIDER, 'endpoint': ENDPOINT, 'tool': TOOL, 'limit_max': 50,
                          'pagination_supported': False, 'authentication': 'native host OAuth',
                          'live_access': 'not_checked; call the native tool with a bounded query'}
            elif a.command == 'doctor':
                result = {'python': sys.version.split()[0], 'workspace': str(mapping(a.client,a.account)),
                          'registry': str(registry()), 'provider': PROVIDER,
                          'live_access': 'not_checked_by_local_doctor', 'legacy_billing': 'preserved; not modified'}
            elif a.command == 'plan': result = plan(a)
            elif a.command in ('collect', 'resume'): result = collect(a)
            elif a.command == 'export': result = export(a)
            elif a.command == 'list':
                workspace = mapping(a.client, a.account)
                rows = []
                for path in sorted((workspace/'runs').glob('*/manifest.json')):
                    try:
                        run = load_run(workspace, path.parent.name, a.client, a.account)
                        verify_evidence(workspace, run)
                        rows.append({'id': run['id'], 'provider': run.get('provider','apify-legacy'), 'service': run.get('service'), 'operator_status': operator_status(run)[0]})
                    except (Blocked, OSError, ValueError, KeyError, TypeError) as exc:
                        rows.append({'id': path.parent.name, 'operator_status': 'Held: ' + (str(exc) if isinstance(exc, Blocked) else 'unreadable_run')})
                result = {'runs': rows}
            else:
                run = load_run(mapping(a.client,a.account), a.run, a.client, a.account)
                verify_evidence(mapping(a.client,a.account), run)
                result = {'run': run, 'operator_status': operator_status(run)[0], 'next_action': operator_status(run)[1]}
            print(json.dumps(result, ensure_ascii=False))
            try:
                status, returned, dropped = 'checked', None, None
                if a.command == 'setup': status = 'completed'
                elif a.command == 'plan': status = 'planned'
                elif a.command == 'export': status, returned = 'exported', result['records']
                elif a.command in ('collect', 'resume', 'status'):
                    run = result['run']
                    if run.get('block_reason') or run.get('lifecycle') in ('failed', 'cancelled'):
                        status = 'held'
                    elif getattr(a, '_usage_reused', False): status = 'already_terminal'
                    elif run.get('lifecycle') in ('planned', 'awaiting_response', 'capturing'): status = 'awaiting_response'
                    elif a.command != 'status':
                        status = 'empty' if not run['normalized'] else 'imported'
                        returned, dropped = run['normalized'], run['quarantined'] + run['duplicates']
                metric(status, returned=returned, dropped=dropped)
            except Exception:
                metric('completed', 'unclassified')
            return 0
        except (Blocked, OSError, KeyError, TypeError, ValueError, AttributeError, RecursionError) as exc:
            metric('held', 'validation' if isinstance(exc, Blocked) else error_class(exc))
            print(json.dumps({'error': str(exc) if isinstance(exc, Blocked) else type(exc).__name__}), file=sys.stderr)
            return 2

if __name__ == '__main__':
    raise SystemExit(main())
