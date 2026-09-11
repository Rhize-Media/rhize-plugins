"""Read-only doctor probes. Return aggregate facts, never raw output or credentials."""
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import urllib.error
import urllib.request
from urllib.parse import urlsplit


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def command(argv):
    result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            timeout=5, check=False)
    return result.returncode, result.stdout


def cli(home, name, args, cwd=None, executable=None):
    # Node-based tools must use their explicit shim; never ambient npm/npx/node.
    candidates = [home / '.local/share/mise/shims' / name]
    if name == 'rtk':
        candidates += [home / '.local/bin/rtk']
        if executable:
            candidates.insert(0, Path(executable))
    for path in candidates:
        if path.is_file() and os.access(path, os.X_OK):
            shims = str(home / '.local/share/mise/shims')
            environment = dict(os.environ, PATH=shims + ':/usr/bin:/bin')
            result = subprocess.run([str(path)] + args, stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL, timeout=8, env=environment, cwd=cwd)
            return result.returncode, result.stdout
    raise FileNotFoundError(name)


def epoch(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError('invalid_epoch')
    return value / 1000


def credential_expiry(home, execute=command):
    code, raw = execute(['/usr/bin/security', 'find-generic-password', '-s', 'Claude Code-credentials', '-w'])
    if code:
        return 'NOT_RUN', 'blocked_credential', {}
    oauth = json.loads(raw).get('claudeAiOauth', {})
    now = datetime.now(timezone.utc).timestamp()
    facts = {}
    for key in ('expiresAt', 'refreshTokenExpiresAt'):
        if oauth.get(key) is not None:
            value = epoch(oauth[key])
            facts[key] = datetime.fromtimestamp(value, timezone.utc).isoformat()
            facts[key + '_hours_remaining'] = round((value - now) / 3600, 3)
    # An access-token expiry is not the lifetime of a refreshable login.
    if oauth.get('refreshTokenExpiresAt') is not None:
        expiring = epoch(oauth['refreshTokenExpiresAt']) <= now + 8 * 86400
        return ('PROBLEM', 'refresh_credential_expiring', facts) if expiring else ('OK', 'refresh_expiry_measured', facts)
    if not oauth.get('refreshToken') and oauth.get('expiresAt') is not None:
        expiring = epoch(oauth['expiresAt']) <= now + 8 * 86400
        return ('PROBLEM', 'credential_expiring', facts) if expiring else ('OK', 'expiry_measured', facts)
    return 'NOT_RUN', 'refresh_expiry_unknown', facts


def capture(home, window_start, maximum_age_hours=24):
    directory = home / '.claude-mem'
    health_path = directory / 'observer-health.json'
    health = json.loads(health_path.read_text())
    now = datetime.now(timezone.utc).timestamp()
    window = datetime.fromisoformat(window_start.replace('Z', '+00:00')).timestamp()
    failures = health.get('consecutiveFailures')
    if type(failures) is not int or failures < 0:
        raise ValueError('invalid_failures')
    facts = {'consecutive_failures':failures, 'health_file_age_hours':round((now - health_path.stat().st_mtime) / 3600, 3)}
    for key in ('lastSuccessAt', 'lastErrorAt', 'failingSinceAt'):
        value = health.get(key)
        facts[key] = None if value is None else datetime.fromtimestamp(epoch(value), timezone.utc).isoformat()
        if value is not None and epoch(value) > now:
            raise ValueError('future_source_time')
    database = (directory / 'claude-mem.db').resolve()
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True, timeout=2) as conn:
        conn.execute('PRAGMA query_only=ON')
        # No content columns or user prompt text are selected.
        observations, latest = conn.execute('SELECT count(*), max(created_at_epoch) FROM observations WHERE created_at_epoch >= ?', (window * 1000,)).fetchone()
        sessions = conn.execute('SELECT count(*) FROM sdk_sessions WHERE started_at_epoch >= ?', (window * 1000,)).fetchone()[0]
        active_recently = conn.execute('SELECT count(*) FROM sdk_sessions WHERE started_at_epoch >= ?', ((now - maximum_age_hours * 3600) * 1000,)).fetchone()[0]
    facts.update(observations_in_window=observations, sessions_in_window=sessions,
                 recent_sessions=active_recently, window_start=window_start,
                 latest_observation_at=None if latest is None else datetime.fromtimestamp(epoch(latest), timezone.utc).isoformat())
    if latest is not None and epoch(latest) > now:
        raise ValueError('future_observation')
    if not sessions:
        return 'NOT_RUN', 'no_sessions_in_window', facts
    if not observations:
        return 'PROBLEM', 'no_capture_despite_sessions', facts
    if active_recently and now - epoch(latest) > maximum_age_hours * 3600:
        return 'PROBLEM', 'capture_evidence_stale', facts
    last_event = max([epoch(health[k]) for k in ('lastSuccessAt','lastErrorAt') if health.get(k) is not None] or [0])
    if active_recently and now - last_event > maximum_age_hours * 3600:
        return 'PROBLEM', 'capture_telemetry_stale', facts
    if failures:
        return 'PROBLEM', 'capture_errors_recorded', facts
    return 'OK', 'capture_persisted', facts


def probe(spec, context):
    home, repo, kind = Path(context['home']), Path(context['repo']), spec['kind']
    try:
        if kind == 'http':
            url = spec['params']['url']
            parsed = urlsplit(url)
            if parsed.scheme != 'http' or parsed.hostname not in {'127.0.0.1','localhost'} or parsed.username or parsed.password or not parsed.port:
                return 'NOT_RUN', 'nonlocal_probe_refused', {}
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
            with opener.open(url, timeout=4) as response:
                status = response.status
            return ('OK' if status == 200 else 'PROBLEM'), 'http_measured', {'http_status':status}
        if kind == 'rtk':
            code, raw = cli(home, 'rtk', ['--version'], executable=context.get('rtk_bin'))
            match = re.search(rb'\b\d+\.\d+\.\d+\b', raw[:2048])
            if code or not match:
                return 'NOT_RUN', 'invalid_cli_measurement', {'exit_code':code}
            return 'OK', 'cli_available', {'version':match.group().decode(), 'compression_effectiveness':'not_measured'}
        if kind == 'claude_mem':
            return capture(home, context['window_start'], spec['params'].get('maximum_age_hours', 24))
        if kind == 'credentials':
            return credential_expiry(home)
        if kind == 'codegraph':
            if not (repo / '.codegraph').is_dir():
                return 'NOT_RUN', 'index_not_configured', {}
            # Current status is measured from the opted-in repository, never an inferred version.
            code, raw = cli(home, 'codegraph', ['status'], cwd=repo)
            if code:
                return 'NOT_RUN', 'codegraph_status_failed', {'exit_code':code}
            if b'Index is up to date' not in raw:
                return 'PROBLEM', 'index_not_current', {}
            return 'OK', 'index_current', {}
        if kind == 'openwolf':
            return 'NOT_RUN', 'health_contract_unavailable' if (repo / '.wolf').exists() else 'not_configured', {}
        if kind == 'adapters':
            return 'NOT_RUN', 'supported_read_contract_unavailable', {'episodic':'unavailable', 'procedural':'unavailable'}
        if kind == 'harness':
            return 'NOT_RUN', 'host_skill_not_exercised', {}
        return 'NOT_RUN', 'unsupported_probe', {}
    except FileNotFoundError:
        return 'NOT_RUN', 'missing_executable_or_source', {}
    except PermissionError:
        return 'NOT_RUN', 'permission_denied', {}
    except subprocess.TimeoutExpired:
        return 'NOT_RUN', 'timeout', {}
    except urllib.error.HTTPError as error:
        return 'PROBLEM', 'http_error', {'http_status':error.code}
    except urllib.error.URLError as error:
        if isinstance(error.reason, PermissionError):
            return 'NOT_RUN', 'permission_denied', {}
        if isinstance(error.reason, TimeoutError):
            return 'NOT_RUN', 'timeout', {}
        return 'PROBLEM', 'endpoint_unreachable', {}
    except (ValueError, TypeError, KeyError, sqlite3.Error):
        return 'NOT_RUN', 'malformed_source', {}
    except OSError:
        return 'NOT_RUN', 'source_unavailable', {}
