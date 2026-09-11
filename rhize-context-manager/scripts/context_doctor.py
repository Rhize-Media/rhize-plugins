#!/usr/bin/env python3
"""Deterministic context-stack pilot. Python 3.9+, standard library only."""
import argparse
from datetime import datetime, timezone, timedelta
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time
import uuid

SCHEMA = 1
MAX_OUTPUT = 64 * 1024
HERE = Path(__file__).resolve().parent
OUTCOMES = {'OK', 'PROBLEM', 'NOT_RUN'}
KINDS = {'http', 'rtk', 'claude_mem', 'codegraph', 'credentials', 'openwolf', 'adapters', 'harness'}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError('timestamp_must_be_text')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('timezone_required')
    return parsed


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def validate_uuid(value):
    if not isinstance(value, str) or str(uuid.UUID(value)) != value:
        raise ValueError('invalid_run_id')


def source_digest():
    return digest({name: hashlib.sha256((HERE / name).read_bytes()).hexdigest()
                   for name in ('context_doctor.py', 'context_doctor_probes.py',
                                'context_doctor_monitor.py')})


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError('symlink_output_refused')
    path.parent.chmod(0o700)
    fd, temporary = tempfile.mkstemp(prefix='.pending-', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'w') as handle:
            json.dump(value, handle, sort_keys=True, indent=2, allow_nan=False)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_json(path):
    with Path(path).open('rb') as handle:
        raw = handle.read(MAX_OUTPUT + 1)
    if len(raw) > MAX_OUTPUT:
        raise ValueError('oversized_document')
    return json.loads(raw, parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonfinite')))


def validate_config(config, check_review=True):
    if not isinstance(config, dict) or set(config) != {'schema_version', 'probes'} or type(config['schema_version']) is not int or config['schema_version'] != SCHEMA:
        raise ValueError('unsupported_config')
    probes = config['probes']
    if not isinstance(probes, list) or not 1 <= len(probes) <= 16:
        raise ValueError('invalid_probe_count')
    ids = set()
    for spec in probes:
        if set(spec) - {'id', 'kind', 'required', 'timeout_seconds', 'params', 'owner', 'review_by'}:
            raise ValueError('unknown_config_fields')
        if not re.fullmatch(r'[a-z][a-z0-9_]{0,39}', spec['id']) or spec['id'] in ids:
            raise ValueError('invalid_probe_id')
        ids.add(spec['id'])
        if spec['kind'] not in KINDS or type(spec['required']) is not bool:
            raise ValueError('invalid_probe')
        timeout = spec['timeout_seconds']
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 30:
            raise ValueError('invalid_deadline')
        if not isinstance(spec['params'], dict):
            raise ValueError('invalid_parameters')
        allowed = {'http': {'url'}, 'claude_mem': {'maximum_age_hours'}}.get(spec['kind'], set())
        if set(spec['params']) != allowed:
            raise ValueError('invalid_parameters')
        if spec['kind'] == 'claude_mem':
            age = spec['params']['maximum_age_hours']
            if type(age) not in (int, float) or not math.isfinite(age) or not 0 < age <= 168:
                raise ValueError('invalid_freshness_bound')
        if not spec['required']:
            if not spec.get('owner') or (check_review and timestamp(spec['review_by']) <= timestamp(utc_now())):
                raise ValueError('optional_probe_review_due')
    if not any(p['required'] for p in probes) or sum(p['timeout_seconds'] for p in probes) > 90:
        raise ValueError('invalid_run_budget')
    return config


def summarize(rows):
    problems = sum(r['outcome'] == 'PROBLEM' for r in rows)
    missing = sum(r['required'] and r['outcome'] == 'NOT_RUN' for r in rows)
    optional = sum(not r['required'] and r['outcome'] == 'NOT_RUN' for r in rows)
    if problems and missing:
        headline = 'Problems detected; coverage incomplete'
    elif problems:
        headline = 'Problems detected'
    elif missing:
        headline = 'Coverage incomplete'
    elif optional:
        headline = 'Required checks passed; optional coverage incomplete'
    else:
        headline = 'Required checks passed'
    return {'headline': headline, 'problems': problems, 'mandatory_not_run': missing,
            'optional_not_run': optional, 'mandatory_total': sum(r['required'] for r in rows),
            'mandatory_measured': sum(r['required'] and r['outcome'] != 'NOT_RUN' for r in rows)}


def validate_evidence(row, spec, context, started, finished):
    fields = {'run_id', 'probe_id', 'config_digest', 'observed_at', 'outcome', 'reason', 'facts'}
    if not isinstance(row, dict) or set(row) != fields:
        raise ValueError('invalid_fields')
    if (row['run_id'], row['probe_id'], row['config_digest']) != (
            context['run_id'], spec['id'], context['config_digest']):
        raise ValueError('evidence_identity_mismatch')
    if not timestamp(started) <= timestamp(row['observed_at']) <= timestamp(finished):
        raise ValueError('evidence_time_mismatch')
    if row['outcome'] not in OUTCOMES or not re.fullmatch(r'[a-z][a-z0-9_]{0,79}', row['reason']):
        raise ValueError('invalid_outcome')
    if not isinstance(row['facts'], dict) or len(json.dumps(row['facts'], allow_nan=False)) > 16000:
        raise ValueError('invalid_facts')
    return row


def collect_probe(spec, context, worker=None):
    started = utc_now()
    payload = {'spec': spec, 'context': context, 'requested_at': started}
    command = worker or [sys.executable, str(HERE / 'context_doctor.py'), 'probe']
    reason, row, code, process = None, None, None, None
    try:
        with tempfile.TemporaryFile() as output:
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=output,
                                       stderr=subprocess.DEVNULL, start_new_session=True)
            process.communicate(json.dumps(payload).encode(), timeout=spec['timeout_seconds'])
            code = process.returncode
            if code:
                reason = 'nonzero_exit'
            else:
                output.seek(0)
                raw = output.read(MAX_OUTPUT + 1)
                if len(raw) > MAX_OUTPUT:
                    reason = 'oversized_output'
                else:
                    row = validate_evidence(json.loads(raw), spec, context, started, utc_now())
    except FileNotFoundError:
        reason = 'missing_executable'
    except subprocess.TimeoutExpired:
        reason = 'timeout'
    except (ValueError, TypeError, KeyError, UnicodeError):
        reason = 'malformed_output'
    except OSError:
        reason = 'launch_failure'
    finally:
        if process is not None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
    if reason:
        row = {'run_id': context['run_id'], 'probe_id': spec['id'],
               'config_digest': context['config_digest'], 'observed_at': utc_now(),
               'outcome': 'NOT_RUN', 'reason': reason, 'facts': {}}
    row.update(required=spec['required'], started_at=started, completed_at=utc_now(), exit_code=code)
    return row


def validate_report(report):
    expected = {'schema_version', 'run_id', 'status', 'started_at', 'completed_at', 'repo',
                'config', 'config_digest', 'source_digest', 'probes', 'summary', 'delta',
                'procedure_run_id', 'monitor'}
    if not isinstance(report, dict) or set(report) != expected:
        raise ValueError('invalid_report_fields')
    if type(report['schema_version']) is not int or report['schema_version'] != SCHEMA or report['status'] != 'completed':
        raise ValueError('not_completed')
    validate_uuid(report['run_id'])
    if not timestamp(report['started_at']) <= timestamp(report['completed_at']) <= timestamp(utc_now()):
        raise ValueError('invalid_run_time')
    config = validate_config(report['config'], check_review=False)
    # Historical optional expiry does not invalidate a completed historical measurement.
    if config.get('schema_version') != SCHEMA or digest(config) != report['config_digest']:
        raise ValueError('config_mismatch')
    specs = {p['id']: p for p in config['probes']}
    rows = report['probes']
    if len(specs) != len(config['probes']) or len(rows) != len(specs):
        raise ValueError('probe_set_mismatch')
    if {r['probe_id'] for r in rows} != set(specs):
        raise ValueError('probe_set_mismatch')
    context = {'run_id': report['run_id'], 'config_digest': report['config_digest']}
    for row in rows:
        if set(row) != {'run_id','probe_id','config_digest','observed_at','outcome','reason','facts',
                        'required','started_at','completed_at','exit_code'}:
            raise ValueError('invalid_probe_fields')
        if row['required'] is not specs[row['probe_id']]['required']:
            raise ValueError('mandatory_mismatch')
        if not timestamp(report['started_at']) <= timestamp(row['started_at']) <= timestamp(row['completed_at']) <= timestamp(report['completed_at']):
            raise ValueError('invalid_probe_time')
        validate_evidence({k:v for k,v in row.items() if k not in {'required','started_at','completed_at','exit_code'}},
                          specs[row['probe_id']], context, row['started_at'], row['completed_at'])
        if row['outcome'] != 'NOT_RUN' and row['exit_code'] != 0:
            raise ValueError('exit_status_mismatch')
    if report['summary'] != summarize(rows):
        raise ValueError('summary_mismatch')
    delta = report['delta']
    if not isinstance(delta, dict) or set(delta) != {'baseline_run_id','baseline_digest','status','changes'}:
        raise ValueError('invalid_delta')
    if delta['baseline_run_id'] is None:
        if delta != report_delta(None, rows):
            raise ValueError('invalid_first_run_delta')
    else:
        validate_uuid(delta['baseline_run_id'])
        if not re.fullmatch('[0-9a-f]{64}', delta['baseline_digest']):
            raise ValueError('invalid_baseline_digest')
        if delta['status'] != ('changed' if delta['changes'] else 'unchanged'):
            raise ValueError('invalid_delta_status')
    return report


def prior_report(state, config_hash, revision, repo, before):
    candidates = []
    for path in Path(state).glob('*/report.json'):
        try:
            report = validate_report(load_json(path))
            if (report['config_digest'], report['source_digest'], report['repo']) == (config_hash, revision, repo) and timestamp(report['completed_at']) < timestamp(before):
                candidates.append(report)
        except (OSError, ValueError, TypeError, KeyError):
            continue
    return max(candidates, key=lambda r: timestamp(r['completed_at'])) if candidates else None


def report_delta(previous, rows):
    if previous is None:
        return {'baseline_run_id': None, 'baseline_digest': None, 'status': 'no_compatible_baseline', 'changes': []}
    old = {r['probe_id']: r for r in previous['probes']}
    changes = [{'probe_id':r['probe_id'], 'before':old[r['probe_id']]['outcome'],
                'after':r['outcome'], 'reason':r['reason']} for r in rows
               if (r['outcome'], r['reason']) != (old[r['probe_id']]['outcome'], old[r['probe_id']]['reason'])]
    return {'baseline_run_id':previous['run_id'], 'baseline_digest':digest(previous), 'status':'changed' if changes else 'unchanged',
            'changes':changes}


def render(report, previous=None):
    validate_report(report)
    if report['delta']['baseline_run_id'] is not None:
        if previous is None:
            raise ValueError('baseline_required_for_render')
        validate_report(previous)
        if (previous['config_digest'],previous['source_digest'],previous['repo']) != (report['config_digest'],report['source_digest'],report['repo']):
            raise ValueError('incompatible_baseline')
        if timestamp(previous['completed_at']) >= timestamp(report['started_at']):
            raise ValueError('baseline_not_prior')
        if report['delta'] != report_delta(previous,report['probes']):
            raise ValueError('delta_mismatch')
    lines = [report['summary']['headline'], 'Run: ' + report['run_id'],
             'Observed: ' + report['completed_at'], '', '| Probe | Outcome | Required | Reason |',
             '|---|---|---|---|']
    for row in report['probes']:
        lines.append('| {probe_id} | {outcome} | {required} | {reason} |'.format(**row))
    lines += ['', 'Delta: ' + report['delta']['status']]
    for change in report['delta']['changes']:
        lines.append('{probe_id}: {before} -> {after} ({reason})'.format(**change))
    return '\n'.join(lines)


def watch(state, max_age_hours, max_runtime_seconds, expected_repo=None, expected_config=None):
    now, reasons, completed, unfinished = timestamp(utc_now()), [], [], []
    incompatible = []
    for attempt in Path(state).glob('*/started.json'):
        try:
            started = load_json(attempt)
            if timestamp(started['started_at']) > now:
                raise ValueError('future_attempt')
            path = attempt.parent / 'report.json'
            if path.exists():
                report = validate_report(load_json(path))
                if report['run_id'] != started['run_id'] or report['started_at'] != started['started_at']:
                    raise ValueError('attempt_mismatch')
                if expected_repo is not None and report['repo'] != expected_repo:
                    incompatible.append('scope_mismatch')
                    continue
                if expected_config is not None and report['config_digest'] != expected_config:
                    incompatible.append('config_mismatch')
                    continue
                completed.append(report)
            elif (now - timestamp(started['started_at'])).total_seconds() > max_runtime_seconds:
                unfinished.append(timestamp(started['started_at']))
        except (OSError, ValueError, TypeError, KeyError):
            reasons.append('invalid_evidence')
    latest = max(completed, key=lambda r: timestamp(r['completed_at'])) if completed else None
    if any(latest is None or started > timestamp(latest['completed_at']) for started in unfinished):
        reasons.append('unfinished_run')
    if latest is None:
        reasons.extend(incompatible)
        reasons.append('missing_completion')
    elif (now - timestamp(latest['completed_at'])).total_seconds() > max_age_hours * 3600:
        reasons.append('overdue_evidence')
    return {'schema_version':SCHEMA, 'observed_at':now.isoformat(),
            'outcome':'PROBLEM' if reasons else 'OK', 'reasons':sorted(set(reasons)),
            'last_completed_run_id':latest['run_id'] if latest else None}


def run(args):
    from context_doctor_monitor import check_in
    state = Path(args.state_dir).expanduser()
    if state.is_symlink():
        raise ValueError('symlink_state_refused')
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    state.chmod(0o700)
    run_id, started = str(uuid.uuid4()), utc_now()
    directory = state / run_id
    atomic_json(directory / 'started.json', {'schema_version':SCHEMA, 'run_id':run_id, 'started_at':started})
    monitor_start = check_in(args.monitor_config, run_id, 'in_progress')
    try:
        config = validate_config(load_json(args.config))
        config_hash, revision, repo = digest(config), source_digest(), str(Path(args.repo).resolve())
        previous = prior_report(state, config_hash, revision, repo, started)
        window = previous['completed_at'] if previous else (timestamp(started) - timedelta(days=7)).isoformat()
        context = {'run_id':run_id, 'config_digest':config_hash, 'repo':repo,
                   'home':str(Path(args.home).expanduser().resolve()), 'window_start':window,
                   'rtk_bin':args.rtk_bin}
        rows = [collect_probe(spec, context) for spec in config['probes']]
        report = {'schema_version':SCHEMA, 'run_id':run_id, 'status':'completed',
                  'started_at':started, 'completed_at':utc_now(), 'repo':repo,
                  'config':config, 'config_digest':config_hash, 'source_digest':revision,
                  'probes':rows, 'summary':summarize(rows), 'delta':report_delta(previous, rows),
                  'procedure_run_id':os.environ.get('RHIZE_ARTIFACT_RUN_ID') or os.environ.get('RHIZE_RUN_ID'),
                  'monitor':{'status':'configured' if args.monitor_config else 'disabled'}}
        validate_report(report)
        atomic_json(directory / 'report.json', report)
        unhealthy = bool(report['summary']['problems'] or report['summary']['mandatory_not_run'])
        delivery = check_in(args.monitor_config, run_id, 'error' if unhealthy else 'ok')
        atomic_json(directory / 'delivery.json', {'run_id':run_id, 'observed_at':utc_now(),
                                                'start':monitor_start, 'completion':delivery})
        print(render(report, previous))
        print('Monitor HTTP: ' + delivery['status'])
        print('Artifact: ' + str(directory / 'report.json'))
        return 2 if delivery['status'] == 'failed' else (1 if unhealthy else 0)
    except (OSError, ValueError, TypeError, KeyError) as error:
        atomic_json(directory / 'failure.json', {'schema_version':SCHEMA, 'run_id':run_id,
                    'outcome':'NOT_RUN', 'reason':'runner_contract_failure', 'error_type':type(error).__name__,
                    'observed_at':utc_now()})
        check_in(args.monitor_config, run_id, 'error')
        print('NOT_RUN: runner_contract_failure (' + type(error).__name__ + ')', file=sys.stderr)
        return 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    invocation = commands.add_parser('run')
    invocation.add_argument('--repo', required=True)
    invocation.add_argument('--home', default=os.environ.get('HOME'))
    invocation.add_argument('--config', default=str(HERE / 'context-doctor.config.json'))
    invocation.add_argument('--state-dir')
    invocation.add_argument('--rtk-bin', default=os.environ.get('RHIZE_RTK_BIN'))
    invocation.add_argument('--monitor-config')
    display = commands.add_parser('render')
    display.add_argument('report')
    watcher = commands.add_parser('watch')
    watcher.add_argument('--state-dir', required=True)
    watcher.add_argument('--repo', required=True)
    watcher.add_argument('--config', default=str(HERE / 'context-doctor.config.json'))
    watcher.add_argument('--max-age-hours', type=float, required=True)
    watcher.add_argument('--max-runtime-seconds', type=float, default=600)
    commands.add_parser('probe')
    args = parser.parse_args(argv)
    if args.command == 'run':
        if not args.home:
            parser.error('--home or HOME is required')
        if args.rtk_bin and not Path(args.rtk_bin).is_absolute():
            parser.error('--rtk-bin must be an absolute executable path')
        args.state_dir = args.state_dir or str(Path(args.home) / '.claude/context-manager/doctor/v1')
        return run(args)
    if args.command == 'probe':
        from context_doctor_probes import probe
        request = json.loads(sys.stdin.buffer.read(MAX_OUTPUT + 1))
        outcome, reason, facts = probe(request['spec'], request['context'])
        print(json.dumps({'run_id':request['context']['run_id'], 'probe_id':request['spec']['id'],
                          'config_digest':request['context']['config_digest'], 'observed_at':utc_now(),
                          'outcome':outcome, 'reason':reason, 'facts':facts}, allow_nan=False))
        return 0
    if args.command == 'render':
        report = load_json(args.report)
        validate_report(report)
        baseline = report['delta']['baseline_run_id']
        previous = load_json(Path(args.report).parent.parent / baseline / 'report.json') if baseline else None
        print(render(report,previous))
        return 0
    if not 0 < args.max_age_hours <= 8760 or not 0 < args.max_runtime_seconds <= 3600:
        parser.error('watch bounds must be finite positive values within one year / one hour')
    config_hash = digest(validate_config(load_json(args.config)))
    result = watch(args.state_dir, args.max_age_hours, args.max_runtime_seconds,
                   str(Path(args.repo).resolve()), config_hash)
    print(json.dumps(result, indent=2))
    return int(result['outcome'] != 'OK')


if __name__ == '__main__':
    raise SystemExit(main())
