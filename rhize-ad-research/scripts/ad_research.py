#!/usr/bin/env python3
"""Local, fail-closed collection journal for the Ad Library research spike."""
import argparse
import csv
import datetime as dt
import fcntl
import hashlib
import http.client
import json
import os
import pwd
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import uuid
from decimal import Decimal, InvalidOperation

ACTOR = 'JJghSZmShuco4j9gJ'
BUILD = 'vx9ZhrSrrahpCBZrI'
BUILD_NUMBER = '0.0.410'
ROOT = Path.home() / 'Library/Application Support/Rhize Ad Research'
ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$')
MAX_RESPONSE = 8 * 1024 * 1024

class Blocked(Exception):
    pass

class HTTPFailure(Blocked):
    def __init__(self, status):
        self.status = status
        super().__init__('provider_http_' + str(status))

def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()

def ident(value):
    if not ID.fullmatch(value):
        raise Blocked('Invalid identifier')
    return value

def money(value):
    try:
        n = Decimal(str(value))
        if not n.is_finite() or n < 0:
            raise ValueError()
        return n
    except (InvalidOperation, ValueError):
        raise Blocked('Invalid nonnegative monetary amount') from None

def safe_dir(path):
    path = Path(path).expanduser()
    if '..' in path.parts:
        raise Blocked('Parent traversal is not supported')
    path = path.absolute()
    # Refuse symlinks in every existing component, including user-selected workspaces.
    for component in (path, *path.parents):
        if component.is_symlink():
            raise Blocked('Symlink paths are not supported')
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not path.is_dir():
        raise Blocked('Expected directory')
    return path

def read(path):
    path = Path(path)
    if path.is_symlink() or any(part.is_symlink() for part in path.parents):
        raise Blocked('Symlink files are not supported')
    with path.open(encoding='utf-8') as f:
        return json.load(f)

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
    data = read(registry() / 'registry.json')
    try:
        return safe_dir(data[key(client, account)]['workspace'])
    except KeyError:
        raise Blocked('Client/account not set up') from None

def ledger_path(client, account):
    return registry() / (key(client, account) + '.json')

def ledger(client, account):
    p = ledger_path(client, account)
    return read(p) if p.exists() else {'runs': {}, 'grant': None}

def save_ledger(client, account, data):
    write(ledger_path(client, account), data)

def run_path(workspace, run):
    return workspace / 'runs' / ident(run) / 'manifest.json'

def load_run(workspace, run_id, client, account):
    run = read(run_path(workspace, run_id))
    if run.get('client') != client or run.get('account') != account or run.get('id') != run_id:
        raise Blocked('run_scope_mismatch')
    return run

def save_run(workspace, run):
    write(run_path(workspace, run['id']), run)

def input_contains(actual, expected):
    if isinstance(expected, dict):
        if not isinstance(actual, dict): return False
        extra = set(actual) - set(expected)
        if extra and not (set(expected) == {'url'} and extra == {'method'} and actual['method'] == 'GET'): return False
        return all(k in actual and input_contains(actual[k], v) for k, v in expected.items())
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) == len(expected) and all(input_contains(a, b) for a, b in zip(actual, expected))
    return type(actual) is type(expected) and actual == expected

def validate_url(value):
    try:
        u = urllib.parse.urlsplit(value)
        if u.scheme != 'https' or u.hostname not in ('facebook.com', 'www.facebook.com') or u.username or u.password or u.port not in (None, 443) or u.fragment:
            raise ValueError()
        if u.path.rstrip('/') == '/ads/library':
            allowed = {'active_status', 'ad_type', 'country', 'is_targeted_country', 'media_type', 'search_type', 'view_all_page_id', 'q', 'content_languages[0]', 'publisher_platforms[0]', 'publisher_platforms[1]'}
            pairs = urllib.parse.parse_qsl(u.query, keep_blank_values=True, strict_parsing=True)
            if not pairs or any(k not in allowed for k, _ in pairs) or len({k for k, _ in pairs}) != len(pairs):
                raise ValueError()
        elif not re.fullmatch(r'/[A-Za-z0-9.][A-Za-z0-9._-]{0,99}/?', u.path) or u.query:
            raise ValueError()
        return value
    except ValueError:
        raise Blocked('Invalid Facebook Page or Library URL') from None

def clean_url(value):
    if not isinstance(value, str):
        return None
    try:
        u = urllib.parse.urlsplit(value)
        if u.scheme not in ('https', 'http') or not u.hostname or u.username or u.password:
            return None
        q = [(k, v) for k, v in urllib.parse.parse_qsl(u.query) if not re.search(r'(token|secret|signature|credential|auth|^utm_|^fbclid$|^expires$|^x-amz-)', k, re.I)]
        return urllib.parse.urlunsplit((u.scheme, u.netloc, u.path, urllib.parse.urlencode(q), ''))
    except ValueError:
        return None

def token():
    value = os.environ.get('RHIZE_APIFY_TOKEN')
    if value:
        return value
    try:
        p = subprocess.run(['security', 'find-generic-password', '-a', os.environ.get('USER', ''), '-s', 'Rhize Ad Research Apify Token', '-w'], capture_output=True, text=True, timeout=10, check=True)
        return p.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        raise Blocked('Provider credential unavailable') from None

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise Blocked('Provider redirect refused')

class Transport:
    def request(self, method, path, payload=None, authenticated=True):
        if not path.startswith('/v2/') or '\n' in path:
            raise Blocked('Invalid provider path')
        headers = {'Accept': 'application/json'}
        if authenticated:
            headers['Authorization'] = 'Bearer ' + token()
        body = None
        if payload is not None:
            headers['Content-Type'] = 'application/json'
            body = json.dumps(payload, separators=(',', ':')).encode()
        req = urllib.request.Request('https://api.apify.com' + path, data=body, headers=headers, method=method)
        try:
            with urllib.request.build_opener(NoRedirect).open(req, timeout=30) as response:
                raw = response.read(MAX_RESPONSE + 1)
                if len(raw) > MAX_RESPONSE:
                    raise Blocked('Provider response too large')
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            raise HTTPFailure(exc.code) from None
        except (urllib.error.URLError, OSError, ValueError, http.client.HTTPException) as exc:
            # Do not include provider text, URL, headers, or credential in error output.
            raise Blocked('Provider request failed: ' + type(exc).__name__) from None

def provider_check(transport, authenticated=False):
    actor = transport.request('GET', '/v2/acts/' + ACTOR, authenticated=False)['data']
    build = transport.request('GET', '/v2/actor-builds/' + BUILD, authenticated=False)['data']
    schema = json.loads(build['inputSchema'])
    prices = actor['pricingInfos']
    try:
        dated = [(dt.datetime.fromisoformat(p['startedAt'].replace('Z', '+00:00')), p) for p in prices]
        current = dt.datetime.now(dt.timezone.utc)
        if not dated or any(t.tzinfo is None or t > current for t, _ in dated):
            raise ValueError()
        effective = max(dated, key=lambda x: x[0])[1]
    except (KeyError, TypeError, ValueError):
        raise Blocked('schema_change') from None
    if actor['id'] != ACTOR or build['id'] != BUILD or build['actId'] != ACTOR or build['buildNumber'] != BUILD_NUMBER or effective['pricingModel'] != 'PAY_PER_EVENT' or effective.get('isPPEPlatformUsagePaidByUser', False):
        raise Blocked('schema_change')
    props = schema['properties']
    expected = {'startUrls', 'resultsLimit', 'activeStatus', 'sorting', 'onlyTotal', 'includeAboutPage', 'isDetailsPerAd', 'enrichWithEcommerceData'}
    if not expected.issubset(props) or 'startUrls' not in schema.get('required', []):
        raise Blocked('schema_change')
    events = effective.get('pricingPerEvent', {}).get('actorChargeEvents', {})
    if set(events) != {'apify-default-dataset-item', 'ecommerce-enrichment'} or not events['apify-default-dataset-item'].get('isPrimaryEvent'):
        raise Blocked('schema_change')
    tiers = events['apify-default-dataset-item'].get('eventTieredPricingUsd', {})
    if set(tiers) != {'FREE', 'BRONZE', 'SILVER', 'GOLD', 'PLATINUM', 'DIAMOND'}:
        raise Blocked('schema_change')
    rates = [money(v['tieredEventPriceUsd']) for v in tiers.values()]
    if min(rates) <= 0:
        raise Blocked('schema_change')
    result = {'minimum_published_unit_price_usd': str(min(rates)), 'maximum_published_unit_price_usd': str(max(rates)), 'minimum_charge_usd': str(money(effective['minimalMaxTotalChargeUsd'])), 'actor_id': ACTOR, 'build_id': BUILD, 'build_number': BUILD_NUMBER, 'schema_hash': digest(schema), 'pricing_hash': digest(prices), 'pricing_model': effective['pricingModel'], 'checked_at': now(), 'paid_limit_qualified': False}
    if authenticated:
        user = transport.request('GET', '/v2/users/me')['data']
        result['authenticated_account_id'] = user['id']
        usage = transport.request('GET', '/v2/users/me/usage/monthly')['data']
        result['usage_baseline'] = {k: usage[k] for k in ('usageCycle', 'totalUsageCreditsUsdAfterVolumeDiscount')}
    return result

def grant_validate(g, client, account):
    required = ('grantor', 'issued_at', 'expires_at', 'source_reference', 'client', 'account', 'cumulative_usd', 'billable_units', 'covered_cost_classes', 'provider_use_decision', 'retention_decision', 'collector', 'mode')
    if not isinstance(g, dict) or any(not g.get(x) for x in required) or g['client'] != client or g['account'] != account or g['mode'] != 'spike':
        raise Blocked('Invalid or out-of-scope spike authority')
    try:
        issued = dt.datetime.fromisoformat(g['issued_at'].replace('Z', '+00:00'))
        expiry = dt.datetime.fromisoformat(g['expires_at'].replace('Z', '+00:00'))
        if issued.tzinfo is None or expiry.tzinfo is None or issued > dt.datetime.now(dt.timezone.utc) or expiry <= dt.datetime.now(dt.timezone.utc):
            raise ValueError()
    except (TypeError, ValueError):
        raise Blocked('expired_authority') from None
    if g['provider_use_decision'] != 'allowed' or g['retention_decision'] != 'metadata_links_only':
        raise Blocked('provider_policy_not_approved')
    money(g.get('ancillary_usd'))
    if not isinstance(g['billable_units'], int) or isinstance(g['billable_units'], bool) or g['billable_units'] < 1 or money(g['cumulative_usd']) <= 0:
        raise Blocked('Invalid grant limits')
    if not isinstance(g['covered_cost_classes'], list) or 'actor_events' not in g['covered_cost_classes'] or 'all_in' in g['covered_cost_classes']:
        raise Blocked('Unsupported cost coverage')
    return g

def setup(args):
    with Lock('registry', 'global'):
        workspace = safe_dir(args.workspace)
        path = registry() / 'registry.json'
        data = read(path) if path.exists() else {}
        k = key(args.client, args.account)
        if any(other != k and value['workspace'] == str(workspace) for other, value in data.items()):
            raise Blocked('Workspace already belongs to another client/account')
        if k in data and data[k]['workspace'] != str(workspace):
            raise Blocked('Workspace relocation is not supported')
        data[k] = {'client': args.client, 'account': args.account, 'workspace': str(workspace)}
        write(path, data)
        return data[k]

def plan(args):
    with Lock(args.client, args.account):
        workspace = mapping(args.client, args.account)
        urls = [validate_url(x) for x in args.urls]
        if args.results_limit < 1 or not urls or money(args.max_charge) <= 0:
            raise Blocked('Invalid collection limits')
        input_data = {'startUrls': [{'url': x} for x in urls], 'resultsLimit': args.results_limit, 'activeStatus': 'active', 'sorting': 'relevancy_monthly_grouped', 'onlyTotal': False, 'includeAboutPage': False, 'isDetailsPerAd': False, 'enrichWithEcommerceData': False}
        run = {'id': uuid.uuid4().hex, 'created_at': now(), 'client': args.client, 'account': args.account, 'actor_id': ACTOR, 'build_id': BUILD, 'input': input_data, 'input_hash': digest(input_data), 'max_charge_usd': str(money(args.max_charge)), 'unit_ceiling': args.results_limit * len(urls), 'lifecycle': 'planned', 'coverage': 'unknown', 'result': 'unknown', 'billing': 'pending', 'block_reason': None, 'fetched': 0, 'normalized': 0, 'quarantined': 0}
        save_run(workspace, run)
        return run

def operator_status(run):
    lifecycle = run['lifecycle']
    if lifecycle == 'submission_unknown': return 'Submission unknown', 'Reconcile; never resubmit automatically'
    if run.get('block_reason'): return 'Held: ' + run['block_reason'], 'Resolve named block; review/export existing data'
    if lifecycle in ('running', 'submitting'): return 'In progress', 'Resume existing job'
    if lifecycle in ('failed', 'cancelled'): return lifecycle.capitalize(), 'Inspect retained data and reason'
    if lifecycle == 'planned': return 'Ready to collect if unblocked', 'Review scope and authority'
    if run['coverage'] != 'complete': return 'Partial/capped', 'Review coverage limitations'
    return 'Research collected', 'Begin human review'

def submit_run(workspace, run, data, transport):
    """Reserve and journal before the sole paid POST. Never retry it."""
    if run['id'] in data['runs']:
        raise Blocked('Existing intent must be resumed, never resubmitted')
    if digest(run['input']) != run['input_hash']:
        raise Blocked('input_changed')
    grant = grant_validate(data.get('grant') or {}, run['client'], run['account'])
    if grant['collector'] != pwd.getpwuid(os.getuid()).pw_name:
        raise Blocked('collector_mismatch')
    inp = run['input']
    fixed = {'activeStatus': 'active', 'sorting': 'relevancy_monthly_grouped', 'onlyTotal': False, 'includeAboutPage': False, 'isDetailsPerAd': False, 'enrichWithEcommerceData': False}
    if not isinstance(inp, dict) or set(inp) != set(fixed) | {'startUrls', 'resultsLimit'} or any(type(inp.get(k)) is not type(v) or inp[k] != v for k, v in fixed.items()) or not isinstance(inp['resultsLimit'], int) or isinstance(inp['resultsLimit'], bool) or inp['resultsLimit'] < 1 or not isinstance(inp['startUrls'], list) or not inp['startUrls']:
        raise Blocked('input_changed')
    for url in inp['startUrls']:
        if not isinstance(url, dict) or set(url) != {'url'}: raise Blocked('input_changed')
        validate_url(url['url'])
    if run['unit_ceiling'] != inp['resultsLimit'] * len(inp['startUrls']): raise Blocked('input_changed')
    # An approved spike needs independent documentation of the limit semantics and
    # a conservative unit-price floor; metadata alone is not paid-limit qualification.
    policy = grant.get('spike_limit_policy') or {}
    if not policy.get('source_reference'):
        raise Blocked('unverified_provider_limit')
    check = provider_check(transport, True)
    floor = money(check['minimum_published_unit_price_usd'])
    if money(run['max_charge_usd']) < money(check['minimum_charge_usd']):
        raise Blocked('charge_limit_below_provider_minimum')
    if check.get('authenticated_account_id') != run['account']:
        raise Blocked('auth_account_mismatch')
    if check['schema_hash'] != policy.get('schema_hash') or check['pricing_hash'] != policy.get('pricing_hash'):
        raise Blocked('schema_change')
    charges = Decimal('0'); units = 0
    for prior in data['runs'].values():
        if prior.get('provider_run_id') and not prior.get('collection_finalized'):
            raise Blocked('collection_incomplete')
        if prior.get('collection_block'):
            raise Blocked('provider_collection_unqualified')
        if prior.get('billing') != 'reconciled':
            raise Blocked('billing_unknown')
        charges += money(prior['actual_charge_usd']); units += prior['charged_units']
    # Whole events can be charged across a charge threshold. Reserve the documented
    # maximum overshoot as well as the charge-limited units.
    reserved_units = int((money(run['max_charge_usd']) / floor).to_integral_value(rounding='ROUND_CEILING')) + 1
    reservation = money(run['max_charge_usd']) + 1 * money(check['maximum_published_unit_price_usd'])
    if units + reserved_units > grant['billable_units']:
        raise Blocked('budget_exhausted')
    if grant.get('per_run_usd') and money(run['max_charge_usd']) > money(grant['per_run_usd']):
        raise Blocked('budget_exhausted')
    baseline = grant.get('usage_baseline') or {}
    usage = transport.request('GET', '/v2/users/me/usage/monthly')['data']
    if not baseline.get('usageCycle') or baseline['usageCycle'] != usage.get('usageCycle') or 'totalUsageCreditsUsdAfterVolumeDiscount' not in usage:
        raise Blocked('billing_unknown')
    current_usage = money(usage['totalUsageCreditsUsdAfterVolumeDiscount'])
    baseline_usage = money(baseline.get('totalUsageCreditsUsdAfterVolumeDiscount'))
    if current_usage < baseline_usage: raise Blocked('billing_unknown')
    delta = current_usage - baseline_usage
    ancillary = money(grant['ancillary_usd'])
    unclassified = max(Decimal(0), delta - charges)
    if unclassified > ancillary: raise Blocked('unexplained_account_usage')
    if max(delta, charges) + reservation + ancillary - unclassified > money(grant['cumulative_usd']):
        raise Blocked('budget_exhausted')
    intent = {'input_hash': run['input_hash'], 'created_at': now(), 'lifecycle': 'submitting', 'billing': 'pending', 'reservation_usd': str(reservation), 'reserved_units': reserved_units, 'minimum_unit_price_usd': str(floor), 'maximum_unit_price_usd': check['maximum_published_unit_price_usd'], 'provider_run_id': None}
    data['runs'][run['id']] = intent
    save_ledger(run['client'], run['account'], data)
    run.update(lifecycle='submitting', submitted_at=intent['created_at'], reserved_units=reserved_units, block_reason=None)
    save_run(workspace, run)
    try:
        response = transport.request('POST', '/v2/acts/' + ACTOR + '/runs?build=' + BUILD_NUMBER + '&timeout=120&memory=1024&maxTotalChargeUsd=' + urllib.parse.quote(run['max_charge_usd']), run['input'])['data']
        if response.get('actId') != ACTOR or response.get('buildId') != BUILD or response.get('userId') != run['account']:
            raise Blocked('provider_identity_mismatch')
        provider_id = ident(response['id'])
        if any(v.get('provider_run_id') == provider_id for k, v in data['runs'].items() if k != run['id']):
            raise Blocked('provider_id_already_bound')
    except HTTPFailure as exc:
        if exc.status in (400, 401, 402, 403, 404, 422, 429):
            intent.update(lifecycle='failed', billing='reconciled', actual_charge_usd='0', charged_units=0, rejection_status=exc.status)
            save_ledger(run['client'], run['account'], data)
            run.update(lifecycle='failed', billing='reconciled', actual_charge_usd='0', charged_units=0, block_reason='provider_rejected_' + str(exc.status))
            save_run(workspace, run)
            raise Blocked('provider_rejected_' + str(exc.status)) from None
        intent.update(lifecycle='submission_unknown', billing='unknown')
        save_ledger(run['client'], run['account'], data)
        run.update(lifecycle='submission_unknown', billing='unknown', block_reason='unresolved_submission')
        save_run(workspace, run)
        raise Blocked('unresolved_submission') from None
    except (Blocked, KeyError, TypeError, AttributeError, ValueError, http.client.HTTPException):
        intent.update(lifecycle='submission_unknown', billing='unknown')
        save_ledger(run['client'], run['account'], data)
        run.update(lifecycle='submission_unknown', billing='unknown', block_reason='unresolved_submission')
        save_run(workspace, run)
        raise Blocked('unresolved_submission') from None
    intent.update(provider_run_id=provider_id, lifecycle='running')
    save_ledger(run['client'], run['account'], data)
    run.update(provider_run_id=provider_id, lifecycle='running')
    save_run(workspace, run)
    return run

def reconcile_submission(workspace, run, data, transport):
    intent = data['runs'].get(run['id'])
    if not intent:
        raise Blocked('No existing submission intent')
    if intent.get('provider_run_id'):
        run.update(provider_run_id=intent['provider_run_id'])
        save_run(workspace, run)
        return run
    history = transport.request('GET', '/v2/acts/' + ACTOR + '/runs?limit=1000&desc=true')['data']
    items = history.get('items'); total = history.get('total')
    if not isinstance(items, list) or not isinstance(total, int) or total > len(items):
        raise Blocked('unresolved_submission')
    try:
        submitted = dt.datetime.fromisoformat(intent['created_at'].replace('Z', '+00:00'))
        start = submitted - dt.timedelta(minutes=2)
        end = submitted + dt.timedelta(minutes=10)
        if digest(run['input']) != intent['input_hash']: raise ValueError()
    except (KeyError, TypeError, ValueError):
        raise Blocked('unresolved_submission') from None
    bound = {v.get('provider_run_id') for k, v in data['runs'].items() if k != run['id']}
    matches = []
    for item in items:
        try:
            candidate = ident(item['id'])
            at = dt.datetime.fromisoformat(item['startedAt'].replace('Z', '+00:00'))
            if candidate in bound or at < start or at > end or item.get('actId') != ACTOR or item.get('buildId') != BUILD:
                continue
        except (KeyError, TypeError, ValueError, Blocked):
            continue
        detail = transport.request('GET', '/v2/actor-runs/' + candidate)['data']
        try:
            options = detail.get('options') or {}
            if detail.get('actId') != ACTOR or detail.get('buildId') != BUILD or detail.get('userId') != run['account'] or money(options.get('maxTotalChargeUsd')) != money(run['max_charge_usd']) or options.get('timeoutSecs') != 120 or options.get('memoryMbytes') != 1024:
                continue
            store = ident(detail['defaultKeyValueStoreId'])
        except (KeyError, TypeError, ValueError, Blocked):
            continue
        inp = transport.request('GET', '/v2/key-value-stores/' + store + '/records/INPUT')
        if input_contains(inp, run['input']):
            matches.append(candidate)
    if len(matches) != 1:
        raise Blocked('unresolved_submission')
    intent.update(provider_run_id=matches[0], lifecycle='running', billing='pending')
    save_ledger(run['client'], run['account'], data)
    run.update(provider_run_id=matches[0], lifecycle='running', billing='pending', block_reason=None)
    save_run(workspace, run)
    return run

def resume_run(workspace, run, data, transport):
    run = reconcile_submission(workspace, run, data, transport)
    provider = transport.request('GET', '/v2/actor-runs/' + ident(run['provider_run_id']))['data']
    if provider.get('actId') != ACTOR or provider.get('buildId') != BUILD or provider.get('userId') != run['account']:
        raise Blocked('provider_identity_mismatch')
    state = provider.get('status')
    if state in ('READY', 'RUNNING', 'ABORTING', 'TIMING-OUT'):
        return run
    statuses = {'SUCCEEDED': 'succeeded', 'FAILED': 'failed', 'TIMED-OUT': 'failed', 'ABORTED': 'cancelled'}
    if state not in statuses:
        raise Blocked('Unknown provider run state')
    run['lifecycle'] = statuses[state]
    run['provider_status'] = state
    intent = data['runs'][run['id']]
    intent['collection_finalized'] = False
    intent['lifecycle'] = run['lifecycle']
    counts = provider.get('chargedEventCounts')
    if counts == {} and money(provider.get('usageTotalUsd')) == 0:
        counts = {'apify-default-dataset-item': 0}
    # Actual owner-wide total is authoritative; never sum it with event charges.
    if 'usageTotalUsd' not in provider or not isinstance(counts, dict) or not isinstance(counts.get('apify-default-dataset-item'), int) or any(v for k, v in counts.items() if k != 'apify-default-dataset-item'):
        run.update(billing='unknown', block_reason='billing_unknown')
        intent['billing'] = 'unknown'
    else:
        actual = money(provider['usageTotalUsd'])
        count = counts['apify-default-dataset-item']
        floor = money(intent.get('minimum_unit_price_usd'))
        ceiling = money(intent.get('maximum_unit_price_usd'))
        if actual > money(intent['reservation_usd']) or count > intent['reserved_units'] or count < 0 or not count * floor - Decimal('0.000000001') <= actual <= count * ceiling + Decimal('0.000000001'):
            run.update(billing='unknown', block_reason='billing_overrun')
            intent['billing'] = 'unknown'
        else:
            intent.update(billing='reconciled', actual_charge_usd=str(actual), charged_units=count)
            run.update(billing='reconciled', actual_charge_usd=str(actual), charged_units=count, minimum_unit_price_usd=str(floor), maximum_unit_price_usd=str(ceiling))
    save_ledger(run['client'], run['account'], data)
    if provider.get('defaultDatasetId'):
        run['dataset_id'] = ident(provider['defaultDatasetId'])
    save_run(workspace, run)
    if run.get('dataset_id'):
        return paginate(workspace, run, transport)
    return run

def normalize(item, run):
    if not isinstance(item, dict):
        return None
    ad_id = item.get('ad_archive_id') or item.get('adArchiveID') or item.get('adArchiveId')
    advertiser = item.get('page_name') or item.get('pageName')
    if not isinstance(ad_id, (str, int)) or not str(ad_id) or not isinstance(advertiser, str) or not advertiser.strip():
        return None
    snapshot = item.get('snapshot') if isinstance(item.get('snapshot'), dict) else {}
    body = snapshot.get('body') if isinstance(snapshot.get('body'), dict) else {}
    text = body.get('text') if isinstance(body.get('text'), str) else None
    source = 'https://www.facebook.com/ads/library/?id=' + str(ad_id) if str(ad_id).isdigit() else None
    return {'ad_id': str(ad_id), 'advertiser': advertiser, 'page_id': item.get('page_id') or item.get('pageId'), 'active_status': item.get('is_active'), 'start_date': item.get('start_date') or item.get('startDate'), 'end_date': item.get('end_date') or item.get('endDate'), 'format': snapshot.get('display_format'), 'platforms': item.get('publisher_platforms'), 'observed_at': run.get('observed_at'), 'query_urls': [x['url'] for x in run['input']['startUrls']], 'source_url': source, 'text': text}

def paginate(workspace, run, transport):
    """Save each immutable provider page before advancing its cursor."""
    if run['lifecycle'] not in ('succeeded', 'failed', 'cancelled'):
        raise Blocked('Provider run is not terminal')
    dataset = ident(run['dataset_id'])
    run['coverage'] = 'pagination_incomplete'
    data = ledger(run['client'], run['account'])
    if run['id'] in data['runs']:
        data['runs'][run['id']]['collection_finalized'] = False
        save_ledger(run['client'], run['account'], data)
    save_run(workspace, run)
    directory = run_path(workspace, run['id']).parent
    metadata = transport.request('GET', '/v2/datasets/' + dataset)['data']
    total = metadata.get('itemCount')
    if not isinstance(total, int) or total < 0:
        raise Blocked('Dataset count unavailable')
    offset = run.get('offset', 0)
    while offset < total:
        limit = min(100, total - offset)
        page_path = directory / 'pages' / (str(offset) + '.json')
        page = read(page_path) if page_path.exists() else transport.request('GET', '/v2/datasets/' + dataset + '/items?offset=' + str(offset) + '&limit=' + str(limit) + '&format=json')
        if not isinstance(page, list) or not page or len(page) > limit:
            raise Blocked('Dataset pagination incomplete')
        if not page_path.exists(): write(page_path, page)
        offset += len(page)
        run['offset'] = offset
        run['coverage'] = 'pagination_incomplete'
        save_run(workspace, run)
    run.setdefault('observed_at', now())
    records, quarantined, duplicates, seen = [], 0, 0, set()
    provider_errors = []
    for file in sorted((directory / 'pages').glob('*.json'), key=lambda x: int(x.stem)) if (directory / 'pages').exists() else []:
        for item in read(file):
            if isinstance(item, dict) and item.get('error'):
                code = item['error'] if isinstance(item['error'], str) and re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', item['error']) else 'provider_error'
                provider_errors.append(code)
                continue
            record = normalize(item, run)
            if record is None:
                quarantined += 1
            elif record['ad_id'] not in seen:
                records.append(record); seen.add(record['ad_id'])
            else:
                duplicates += 1
    write(directory / 'records.json', records)
    run.update(fetched=total, normalized=len(records), quarantined=quarantined, duplicates=duplicates)
    run['provider_errors'] = provider_errors
    run['coverage_reasons'] = []
    if provider_errors:
        run['coverage_reasons'].append('provider_error')
        run['block_reason'] = 'provider_result_error'
        data = ledger(run['client'], run['account'])
        if run['id'] in data['runs']:
            data['runs'][run['id']]['collection_block'] = 'provider_result_error'
            save_ledger(run['client'], run['account'], data)
    if not records and not provider_errors and not quarantined:
        run['coverage_reasons'].append('unverified_empty')
    if quarantined: run['coverage_reasons'].append('parse_incomplete')
    if total >= run['input']['resultsLimit'] or (run['billing'] == 'reconciled' and money(run['max_charge_usd']) - money(run['actual_charge_usd']) < money(run.get('maximum_unit_price_usd'))): run['coverage_reasons'].append('capped')
    if run['billing'] == 'reconciled' and run.get('charged_units') != total:
        run['coverage_reasons'].append('count_mismatch')
        run.update(billing='unknown', block_reason='count_mismatch')
        data = ledger(run['client'], run['account'])
        if run['id'] in data['runs']:
            data['runs'][run['id']]['billing'] = 'unknown'
            save_ledger(run['client'], run['account'], data)
    if run['lifecycle'] != 'succeeded': run['coverage_reasons'].append('provider_' + run['lifecycle'])
    if run['billing'] != 'reconciled': run['coverage_reasons'].append('billing_unknown')
    if run['lifecycle'] != 'succeeded':
        run['coverage'] = 'pagination_incomplete'
    elif provider_errors:
        run['coverage'] = 'provider_error'
    elif quarantined:
        run['coverage'] = 'parse_incomplete'
    elif run['billing'] != 'reconciled' or 'count_mismatch' in run['coverage_reasons'] or 'unverified_empty' in run['coverage_reasons']:
        run['coverage'] = 'unknown'
    elif 'capped' in run['coverage_reasons']:
        run['coverage'] = 'capped'
    else:
        run['coverage'] = 'complete'
    run['result'] = 'nonempty' if records else 'unknown'
    data = ledger(run['client'], run['account'])
    if run['id'] in data['runs']:
        intent = data['runs'][run['id']]
        holds = [reason for reason in run['coverage_reasons'] if reason != 'capped']
        if holds:
            intent['collection_block'] = holds[0]
            run['block_reason'] = holds[0]
        elif intent.get('collection_block') not in ('provider_error', 'provider_result_error'):
            intent.pop('collection_block', None)
            run['block_reason'] = None
        intent['collection_finalized'] = True
    save_run(workspace, run)
    save_ledger(run['client'], run['account'], data)
    return run

def export(args):
    workspace = mapping(args.client, args.account)
    run = load_run(workspace, args.run, args.client, args.account)
    if run['lifecycle'] not in ('succeeded', 'failed', 'cancelled'): raise Blocked('Run is not terminal')
    records_path = run_path(workspace, args.run).parent / 'records.json'
    if not records_path.exists(): raise Blocked('No fetched records available')
    records = read(records_path)
    output = safe_dir(args.output)
    rows = []
    for item in records:
        rows.append({k: item.get(k) for k in ('ad_id', 'advertiser', 'page_id', 'active_status', 'start_date', 'end_date', 'format', 'platforms', 'observed_at', 'query_urls', 'source_url', 'text')})
        rows[-1]['source_url'] = 'https://www.facebook.com/ads/library/?id=' + str(item['ad_id']) if str(item['ad_id']).isdigit() else None
    write(output / 'research.json', {'run': {k: run.get(k) for k in ('id', 'lifecycle', 'coverage', 'result', 'billing', 'block_reason', 'fetched', 'normalized', 'quarantined', 'duplicates', 'coverage_reasons', 'provider_errors')}, 'records': rows})
    csv_path = output / 'research.csv'
    if csv_path.is_symlink(): raise Blocked('Symlink files are not supported')
    fd, temp = tempfile.mkstemp(prefix='.csv-', dir=output)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['ad_id', 'advertiser', 'page_id', 'active_status', 'start_date', 'end_date', 'format', 'platforms', 'observed_at', 'query_urls', 'source_url', 'text'])
            writer.writeheader()
            for row in rows:
                writer.writerow({k: ("'" + str(v) if isinstance(v, str) and v.lstrip().startswith(('=', '+', '-', '@', '\t', '\r')) else v) for k, v in row.items()})
            f.flush(); os.fsync(f.fileno())
        os.replace(temp, csv_path)
    finally:
        if os.path.exists(temp): os.unlink(temp)
    return {'json': str(output / 'research.json'), 'csv': str(csv_path), 'records': len(rows), 'lifecycle': run['lifecycle'], 'coverage': run['coverage'], 'result': run['result'], 'billing': run['billing'], 'coverage_reasons': run.get('coverage_reasons', [])}

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    def scope(p):
        p.add_argument('--client', required=True); p.add_argument('--account', required=True)
    p = sub.add_parser('setup'); scope(p); p.add_argument('--workspace', required=True)
    p = sub.add_parser('doctor'); scope(p)
    p = sub.add_parser('list'); scope(p)
    p = sub.add_parser('provider-check'); p.add_argument('--authenticated', action='store_true')
    p = sub.add_parser('grant-import'); scope(p); p.add_argument('--file', required=True)
    p = sub.add_parser('plan'); scope(p); p.add_argument('--urls', nargs='+', required=True); p.add_argument('--results-limit', type=int, required=True); p.add_argument('--max-charge', required=True)
    for name in ('collect', 'status', 'resume', 'export'):
        p = sub.add_parser(name); scope(p); p.add_argument('--run', required=True)
        if name == 'export': p.add_argument('--output', required=True)
    a = parser.parse_args(argv)
    try:
        if a.command == 'setup': result = setup(a)
        elif a.command == 'doctor':
            workspace = mapping(a.client, a.account)
            data = ledger(a.client, a.account)
            result = {'python': sys.version.split()[0], 'workspace': str(workspace), 'registry': str(registry()), 'grant_present': bool(data.get('grant')), 'journaled_runs': len(data['runs']), 'unreconciled_runs': [k for k, v in data['runs'].items() if v.get('billing') != 'reconciled'], 'provider_access': 'not_checked_by_doctor', 'live_qualification': 'requires_review_of_provider_evidence'}
        elif a.command == 'list':
            workspace = mapping(a.client, a.account)
            runs_dir = workspace / 'runs'
            result = {'runs': []}
            if runs_dir.exists():
                for manifest in sorted(runs_dir.glob('*/manifest.json')):
                    run = load_run(workspace, manifest.parent.name, a.client, a.account)
                    state, action = operator_status(run)
                    result['runs'].append({'id': run['id'], 'lifecycle': run['lifecycle'], 'operator_status': state, 'next_action': action})
        elif a.command == 'provider-check': result = provider_check(Transport(), a.authenticated)
        elif a.command == 'grant-import':
            with Lock(a.client, a.account):
                mapping(a.client, a.account)
                g = grant_validate(read(a.file), a.client, a.account)
                l = ledger(a.client, a.account)
                if l['runs']: raise Blocked('Grant replacement after journaled runs is not supported')
                l['grant'] = g; save_ledger(a.client, a.account, l)
                result = {'imported': True, 'grant': g}
        elif a.command == 'plan': result = plan(a)
        elif a.command == 'export': result = export(a)
        else:
            workspace = mapping(a.client, a.account)
            run = load_run(workspace, a.run, a.client, a.account)
            if a.command in ('collect', 'resume'):
                with Lock(a.client, a.account):
                    run = load_run(workspace, a.run, a.client, a.account)
                    data = ledger(a.client, a.account)
                    try:
                        if a.command == 'collect':
                            if run['lifecycle'] != 'planned': raise Blocked('Existing job must be resumed')
                            run = submit_run(workspace, run, data, Transport())
                        else:
                            run = resume_run(workspace, run, data, Transport())
                    except Blocked as exc:
                        run = load_run(workspace, a.run, a.client, a.account)
                        run['block_reason'] = re.sub(r'[^a-z0-9]+', '_', str(exc).lower()).strip('_')
                        save_run(workspace, run)
                        raise
            status, action = operator_status(run)
            result = {'run': run, 'operator_status': status, 'next_action': action}
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (Blocked, OSError, KeyError, TypeError, ValueError, AttributeError, http.client.HTTPException) as exc:
        # Exception text can contain data from a provider or filesystem: only controlled messages are exposed.
        message = str(exc) if isinstance(exc, Blocked) else type(exc).__name__
        print(json.dumps({'error': message}), file=sys.stderr)
        return 2

if __name__ == '__main__':
    raise SystemExit(main())
