#!/usr/bin/env python3
"""Daily skill-fit scoreboard (plan §4.6 outputs). Counts and hashes only: no prompt text exists to print.

    scoreboard.py render [--root DIR] [--format md|json] [--out PATH] [--now ISO]

Built from the latest cycle receipt (<root>/skill-fit/cycles/*.json: report-only alternatives, versions,
actions) plus the current registry state, records, labels, outcomes and the registry audit log. The markdown
form is short enough to append to the 08:00 autolabel summary. With no data at all it still renders.

Every metric is also reported per host (claude, codex, unknown): only the hosts in cohorts.GATE_HOSTS feed the
gate, so the per-host table is where Codex shadow evidence is visible. A keep-warm line is read from
<root>/laya-keepwarm.json (schema rhize-laya-keepwarm-v1, written by laya_keepwarm.py): last ping age, status,
latency and failures, or "keep-warm: not running" when the file is absent. The file is read defensively
(lstat, no symlinks, size cap) and anything that does not validate reads as "invalid".
"""
from __future__ import annotations

import argparse
import json
import math
import os
import stat
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE.parent) not in sys.path:
    sys.path.insert(0, str(HERE.parent))

from typed_decisions import advise_ledger, choice_labels, cohorts, contract, decision_registry, locked_io, records  # noqa: E402

SCHEMA = 'rhize-typed-decision-scoreboard-v1'
DECISION = 'skill-fit'
KEEPWARM_FILE = 'laya-keepwarm.json'
KEEPWARM_SCHEMA = 'rhize-laya-keepwarm-v1'
KEEPWARM_STATUSES = ('ok', 'timeout', 'unavailable', 'invalid', 'identity_failed', 'redirect_refused')  # laya_choice.STATUSES
MAX_KEEPWARM_BYTES = 64 * 1024


def latest_cycle_receipt(root):
    """(path, parsed receipt) of the newest cycle receipt, or (None, None)."""
    directory = Path(root) / DECISION / 'cycles'
    if not directory.is_dir() or directory.is_symlink():
        return None, None
    for path in sorted(directory.glob('*.json'), reverse=True):
        if path.is_symlink():
            continue
        try:
            receipt = locked_io.read_json_file(path)
        except (OSError, ValueError):
            continue
        if isinstance(receipt, dict) and receipt.get('schema') == 'rhize-typed-decision-cycle-receipt-v1':
            return path, receipt
    return None, None


def acceptance(recs: list, outcomes: list) -> dict:
    """Secondary signal: did the user invoke the emitted skill? Not a quality metric (see the label gate)."""
    latest = {}
    for outcome in outcomes:
        latest[outcome['occurrenceKey']] = outcome  # a re-run of the join replaces the earlier row
    by_key = {r['occurrenceKey']: r for r in recs if r['basis'] == 'live'}
    distribution = Counter()
    arms: dict = {}
    for key, outcome in latest.items():
        rec = by_key.get(key)
        if rec is None:
            continue
        distribution[outcome['outcome']] += 1
        if rec['emitted'] is None or outcome['outcome'] == 'transcript_unavailable':
            continue
        slot = arms.setdefault(rec['arm'], {'emitted': 0, 'invokedEmitted': 0})
        slot['emitted'] += 1
        slot['invokedEmitted'] += outcome['outcome'] == 'invoked_emitted'
    for slot in arms.values():
        slot['rate'] = (slot['invokedEmitted'] / slot['emitted']) if slot['emitted'] else None
    return {'note': 'secondary signal only; labels and the cohort gate decide authority',
            'joined': sum(distribution.values()), 'outcomes': dict(distribution), 'byArm': arms}


def host_breakdown(recs: list, outcomes: list) -> dict:
    """Per-host counts: records by basis, live arms and modes, Laya statuses, disagreement prevalence among fired
    records, live latency and timeout share, and joined outcomes. Every host in contract.HOSTS has a row (zeros
    when it has no records), so a consumer never has to guess whether a host is missing or merely quiet.
    """
    result = {}
    for host in contract.HOSTS:
        own = [r for r in recs if r['host'] == host]
        stats = cohorts.summarize_records(own)
        live = [r for r in own if r['basis'] == 'live']
        called = [r for r in live if r['laya']['status'] != 'skipped']
        latencies = [r['laya']['latencyMs'] for r in called
                     if r['laya']['status'] == 'ok' and r['laya']['latencyMs'] is not None]
        timeouts = sum(r['laya']['status'] == 'timeout' for r in called)
        joined = acceptance(own, outcomes)
        result[host] = {
            'gate': host in cohorts.GATE_HOSTS,
            'records': stats['total'], 'byBasis': stats['byBasis'],
            'liveArms': stats['liveArms'], 'liveModes': stats['liveModes'],
            'layaStatuses': {basis: dict(Counter(r['laya']['status'] for r in own if r['basis'] == basis))
                             for basis in ('live', 'backfill')},
            'prevalence': stats['prevalence'],
            'latency': {'n': len(latencies), 'p50': cohorts.percentile_nearest_rank(latencies, 0.5),
                        'p90': cohorts.percentile_nearest_rank(latencies, 0.9)},
            'timeouts': {'calls': len(called), 'timeouts': timeouts,
                         'share': (timeouts / len(called)) if called else None},
            'outcomes': {'joined': joined['joined'], 'counts': joined['outcomes'], 'byArm': joined['byArm']}}
    return result


def _timestamp(value, nullable=False):
    if value is None:
        if nullable:
            return None
        raise ValueError('missing timestamp')              # locked_io.utc(None) would silently mean "now"
    return locked_io.utc(value)                            # ValueError for a non-string, naive or malformed time


def _number(value, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('invalid number')
    if value < 0 or (positive and value == 0):
        raise ValueError('invalid number')
    return value


def _count(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError('invalid count')
    return value


def read_keepwarm(root, now=None) -> dict:
    """State of the Laya keep-warm loop from <root>/laya-keepwarm.json, never raising.

    {'state': 'missing'} when there is no file, {'state': 'invalid'} for anything unsafe or malformed (a symlink,
    a non-regular or oversized file, bad JSON, the wrong schema, a wrong type), else {'state': 'present', ...}
    with the file's fields plus lastPingAgeSeconds and lastActivityAgeSeconds (None when the time is unknown).
    """
    path = Path(root) / KEEPWARM_FILE
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return {'state': 'missing'}
    except OSError:
        return {'state': 'invalid'}
    if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_KEEPWARM_BYTES:
        return {'state': 'invalid'}
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                return {'state': 'invalid'}
            with os.fdopen(fd, 'rb', closefd=False) as handle:
                raw = handle.read(MAX_KEEPWARM_BYTES + 1)
        finally:
            os.close(fd)
        if len(raw) > MAX_KEEPWARM_BYTES:
            return {'state': 'invalid'}
        data = json.loads(raw.decode('utf-8'))
        if not isinstance(data, dict) or data.get('schema') != KEEPWARM_SCHEMA:
            return {'state': 'invalid'}
        status = data.get('lastStatus')
        if status is not None and status not in KEEPWARM_STATUSES:
            return {'state': 'invalid'}
        latency = data.get('lastLatencyMs')
        if latency is not None:
            _number(latency)
        moment = locked_io.utc(now)
        started = _timestamp(data.get('startedAt'))
        last_ping = _timestamp(data.get('lastPingAt'), nullable=True)
        last_activity = _timestamp(data.get('lastActivityAt'), nullable=True)
        result = {'state': 'present', 'startedAt': locked_io.iso(started),
                  'lastPingAt': None if last_ping is None else locked_io.iso(last_ping),
                  'lastPingAgeSeconds': None if last_ping is None else max(0.0, (moment - last_ping).total_seconds()),
                  'lastStatus': status, 'lastLatencyMs': latency,
                  'lastActivityAt': None if last_activity is None else locked_io.iso(last_activity),
                  'lastActivityAgeSeconds': (None if last_activity is None
                                             else max(0.0, (moment - last_activity).total_seconds())),
                  'intervalSeconds': _number(data.get('intervalSeconds'), positive=True),
                  'activeWindowHours': _number(data.get('activeWindowHours'), positive=True)}
        for name in ('consecutiveFailures', 'pings', 'ok', 'skippedIdle', 'skippedWarm'):
            result[name] = _count(data.get(name))
        return result
    except (OSError, ValueError, UnicodeDecodeError, OverflowError, RecursionError):
        return {'state': 'invalid'}


def last_mode_change(root):
    lines, _ = decision_registry.read_audit(root)
    for line in reversed(lines):
        if line['phase'] == 'commit' and line['decision'] == DECISION and line['fromMode'] != line['toMode']:
            return {k: line[k] for k in ('at', 'actor', 'fromMode', 'toMode', 'reason', 'revision')}
    return None


def advise_rows(root, registry, state, status, labels, laya_revision) -> list:
    """One row per advise-capable decision: mode, labelled n and the baseline gate's ledger (attempts, next alpha,
    last verdict with its receipt's accuracy vs baseline, CP lower bound, coverage, critical cases/misses).
    Read-only; a missing ledger or receipt reads as empty, a corrupt ledger as `ledger: invalid`."""
    rows = []
    for decision, entry in registry['decisions'].items():
        cfg = entry.get('advise')
        if not cfg:
            continue
        if decision == 'skill-fit':
            labelled = sum(1 for l in labels if l['basis'] != 'harness' and not l['ambiguous'])
        elif decision == 'workflow-fit':
            labelled = None                      # its corpus is the workflow pilot's, not under this root
        else:
            labelled = sum(1 for l in choice_labels.read_labels(root, decision).values() if not l['ambiguous'])
        row = {'decision': decision, 'tier': entry['tier'], 'labelled': labelled, 'attempts': 0,
               'nextAlpha': cohorts.alpha_for_attempt(cfg['alphaBase'], 1), 'lastVerdict': None, 'ledger': 'ok',
               'mode': decision_registry.effective_mode(decision, registry, state, status, laya_revision)}
        try:
            events = advise_ledger.read(root, decision)
        except ValueError:
            row['ledger'] = 'invalid'
            rows.append(row)
            continue
        row['attempts'] = sum(e['event'] == 'reserve' for e in events)
        row['nextAlpha'] = cohorts.alpha_for_attempt(cfg['alphaBase'], row['attempts'] + 1)
        consumed = [e for e in events if e['event'] == 'consumed']
        if consumed:
            row['lastVerdict'] = consumed[-1]['verdict']
            try:
                stats = locked_io.read_json_file(Path(root) / decision / 'advise-receipts' / (consumed[-1]['cohortId'] + '.json'))['stats']
                row.update({k: stats.get(k) for k in ('accuracy', 'baselineAccuracy', 'cpLower', 'coverage',
                                                      'criticalCases', 'criticalMisses')})
            except (OSError, ValueError, KeyError, TypeError):
                pass
        rows.append(row)
    return rows


def build(root, now=None) -> dict:
    root = Path(root)
    registry = decision_registry.load_registry()
    state, status = decision_registry.read_state(root, registry)
    mode = decision_registry.effective_mode(DECISION, registry, state, status, records.laya_revision(root))
    current = ((state or {}).get('decisions') or {}).get(DECISION)
    recs, invalid_records = cohorts.load_records(root)
    labels, invalid_labels = cohorts.load_labels(root)
    outcomes, _ = records.read(root, DECISION, 'outcomes')
    receipt_file, receipt = latest_cycle_receipt(root)
    table = cohorts.cohort_table(root)
    consumed = [row for row in table if row['status'] == 'consumed']
    stats = cohorts.summarize_records(recs)
    return {
        'schema': SCHEMA, 'decision': DECISION, 'generatedAt': locked_io.iso(now),
        'mode': {'effective': mode, 'stateStatus': status, 'default': registry['decisions'][DECISION]['defaultMode'],
                 'revision': state['revision'] if state else 0, 'pinned': bool(current and current['pinned']),
                 'since': current['since'] if current else None, 'reason': current['reason'] if current else None,
                 'cohortId': current['cohortId'] if current else None},
        'lastModeChange': last_mode_change(root),
        'lastCycle': None if receipt is None else {
            'file': receipt_file.name, 'at': receipt['at'], 'dryRun': receipt['dryRun'],
            'actions': [a['type'] for a in receipt['actions']], 'versions': receipt['versions']},
        'records': {'total': stats['total'], 'byBasis': stats['byBasis'], 'liveArms': stats['liveArms'],
                    'liveModes': stats['liveModes'], 'invalid': invalid_records},
        'labels': {'total': len(labels), 'invalid': invalid_labels},
        'cohorts': table,
        'lastVerdict': (consumed[-1] if consumed else None),
        'prevalence': stats['prevalence'],
        'alternatives': None if receipt is None else receipt['report'],
        'demotion': None if receipt is None else receipt.get('demotion'),
        'acceptance': acceptance(recs, outcomes),
        'laya': stats['laya'],
        'gateHosts': list(cohorts.GATE_HOSTS),
        'hosts': host_breakdown(recs, outcomes),
        'keepWarm': read_keepwarm(root, now),
        'advise': advise_rows(root, registry, state, status, labels, records.laya_revision(root)),
    }


def _pct(value, digits=1):
    return '-' if value is None else f'{100 * value:.{digits}f}%'


def _num(value, digits=3):
    return '-' if value is None else f'{value:.{digits}f}'


def _age(seconds):
    if seconds is None:
        return '-'
    seconds = int(seconds)
    if seconds < 120:
        return f'{seconds}s'
    if seconds < 7200:
        return f'{seconds // 60}m'
    if seconds < 2 * 86400:
        return f'{seconds / 3600:.1f}h'
    return f'{seconds / 86400:.1f}d'


def _counts(counter: dict) -> str:
    return ', '.join(f'{k} {v}' for k, v in sorted(counter.items())) or '-'


def keepwarm_line(info: dict) -> str:
    if info['state'] == 'missing':
        return '- keep-warm: not running'
    if info['state'] != 'present':
        return '- keep-warm: invalid state file (laya-keepwarm.json)'
    latency = '-' if info['lastLatencyMs'] is None else f'{info["lastLatencyMs"]:g} ms'
    return (f'- keep-warm: last ping {_age(info["lastPingAgeSeconds"])} ago, status {info["lastStatus"] or "-"}, '
            f'latency {latency}, consecutive failures {info["consecutiveFailures"]}; pings {info["pings"]} '
            f'(ok {info["ok"]}, skipped idle {info["skippedIdle"]}, skipped warm {info["skippedWarm"]}), '
            f'every {info["intervalSeconds"]:g} s within {info["activeWindowHours"]:g} h of activity, '
            f'last activity {_age(info["lastActivityAgeSeconds"])} ago')


def render_hosts(data: dict) -> list:
    lines = ['', '### Per host (gate hosts: ' + (', '.join(data['gateHosts']) or 'none') + '; other hosts are shadow evidence only)',
             '| host | records | live arms | live modes | Laya statuses (live) | disagreement/fired (live) | '
             'live p50/p90 ms | timeout share | outcomes joined |',
             '|---|---|---|---|---|---|---|---|---|']
    for host, row in data['hosts'].items():
        if host == 'unknown' and not row['records']:
            continue                                            # keep the table to the hosts that exist
        basis = f'{row["records"]} (live {row["byBasis"].get("live", 0)}, backfill {row["byBasis"].get("backfill", 0)})'
        prev = row['prevalence']['live']
        latency = row['latency']
        outcomes = row['outcomes']
        joined = f'{outcomes["joined"]}: {_counts(outcomes["counts"])}' if outcomes['joined'] else '0'
        lines.append(f'| {host}{" (gate)" if row["gate"] else ""} | {basis} | {_counts(row["liveArms"])} | '
                     f'{_counts(row["liveModes"])} | {_counts(row["layaStatuses"]["live"])} | '
                     f'{prev["disagreements"]}/{prev["fired"]} ({_pct(prev["share"])}) | '
                     f'{_num(latency["p50"], 0)}/{_num(latency["p90"], 0)} | {_pct(row["timeouts"]["share"])} | {joined} |')
    return lines


def render_md(data: dict) -> str:
    mode = data['mode']
    lines = [f'## Laya skill-fit scoreboard ({data["generatedAt"]})', '']
    pin = ', pinned (automation suspended)' if mode['pinned'] else ''
    lines.append(f'- Mode: **{mode["effective"]}**{pin} (shipped default {mode["default"]}; state {mode["stateStatus"]}, '
                 f'revision {mode["revision"]}, since {mode["since"] or "-"}, reason {mode["reason"] or "-"})')
    change = data['lastModeChange']
    lines.append('- Last mode change: ' + ('none recorded' if change is None else
                 f'{change["fromMode"]} -> {change["toMode"]} at {change["at"]} by {change["actor"]} ({change["reason"]})'))
    cycle = data['lastCycle']
    lines.append('- Last cycle: ' + ('none yet' if cycle is None else
                 f'{cycle["at"]}{" (dry run)" if cycle["dryRun"] else ""}, actions: {", ".join(cycle["actions"]) or "none"}'))
    lines.append(keepwarm_line(data['keepWarm']))
    rec = data['records']
    arms = ', '.join(f'{k} {v}' for k, v in sorted(rec['liveArms'].items())) or 'none'
    basis = ', '.join(f'{k} {v}' for k, v in sorted(rec['byBasis'].items())) or 'none'
    lines.append(f'- Records: {rec["total"]} ({basis}); live arms: {arms}; labels: {data["labels"]["total"]}')
    for name in ('live', 'backfill'):
        prev = data['prevalence'][name]
        lines.append(f'- Disagreement prevalence among fired ({name}): {prev["disagreements"]}/{prev["fired"]} ({_pct(prev["share"])})')
    lines += render_hosts(data)
    lines += ['', '### Gate (frozen single-use cohorts)']
    if not data['cohorts']:
        lines.append('No cohort reserved yet.')
    else:
        lines += ['| cohort | attempt | status | labeled | alpha | n | x | lower bound | threshold | verdict |',
                  '|---|---|---|---|---|---|---|---|---|---|']
        for row in data['cohorts']:
            stat = row['statistic'] or {}
            lines.append(f'| {row["cohortId"][:8]} | {row["attempt"]} | {row["status"]} | {row["labeled"]}/{row["reserved"]} | '
                         f'{row["alpha"]:g} | {stat.get("n", "-")} | {stat.get("x", "-")} | {_num(stat.get("bound"))} | '
                         f'{_num(stat.get("threshold"))} | {row["verdict"] or "-"} |')
    report = data['alternatives']
    lines += ['', '### Report-only alternatives (never deployed)']
    if not report or report['status'] != 'ok':
        lines.append('No scoreboard-pool labels yet.')
    else:
        lab = report['labels']
        lines.append(f'{lab["used"]} labels / {lab["sessions"]} sessions, lambda {report["lambda"]:g}, HT-weighted, '
                     f'{int(report["bootstrap"]["level"] * 100)}% session-bootstrap CI. {report["caveat"]}')
        lines += ['', '| policy | role | precision | hits | wrong | false fires | utility | utility CI | dU vs incumbent |',
                  '|---|---|---|---|---|---|---|---|---|']
        for alt in report['alternatives']:
            ci = alt['ci90']['utility']
            delta = alt['deltaVsIncumbent']
            lines.append(f'| {alt["name"]} | {alt["role"]} | {_num(alt["precision"], 2)} | {alt["hits"]:.1f} | '
                         f'{alt["wrong"]:.1f} | {alt["falseFires"]:.1f} | {alt["utility"]:.1f} | '
                         f'{"-" if not ci else f"[{ci[0]:.1f}, {ci[1]:.1f}]"} | {delta["point"]:+.1f} |')
        for text in report['recommendations']:
            lines.append(f'- Recommendation: {text}')
    acc = data['acceptance']
    lines += ['', '### Acceptance (secondary: the user invoked the emitted skill)']
    if not acc['byArm']:
        lines.append(f'No joined outcomes for emitted suggestions yet ({acc["joined"]} joined).')
    else:
        for arm, slot in sorted(acc['byArm'].items()):
            lines.append(f'- {arm}: {slot["invokedEmitted"]}/{slot["emitted"]} ({_pct(slot["rate"])})')
    lines += ['', '### Laya latency and status by prompt length']
    wrote = False
    for name in ('live', 'backfill'):
        for bucket, row in data['laya'][name].items():
            if not row['calls']:
                continue
            if not wrote:
                lines += ['| basis | bucket | calls | p50 ms | p90 ms | statuses |', '|---|---|---|---|---|---|']
                wrote = True
            statuses = ', '.join(f'{k} {v}' for k, v in sorted(row['statuses'].items()))
            lines.append(f'| {name} | {bucket} | {row["calls"]} | {_num(row["p50"], 0)} | {_num(row["p90"], 0)} | {statuses} |')
    if not wrote:
        lines.append('No Laya calls recorded yet.')
    verdict = data['lastVerdict']
    lines += ['', '### Last verdict']
    if verdict is None:
        lines.append('No cohort has been tested yet.')
    else:
        stat = verdict['statistic']
        lines.append(f'- Cohort {verdict["cohortId"][:8]} attempt {verdict["attempt"]}: **{verdict["verdict"]}** '
                     f'(x {stat["x"]}/n {stat["n"]}, lower bound {_num(stat["bound"])} vs threshold {_num(stat["threshold"])} '
                     f'at alpha {stat["alpha"]:g}; receipt {verdict["receiptSha256"][:12]})')
    demotion = data['demotion']
    if demotion and not demotion.get('skipped'):
        lat = demotion['latency']
        lines.append(f'- Demotion watch: quality n={demotion["quality"]["n"]}, operational {_pct(demotion["operational"]["share"])} '
                     f'(timeouts {_pct(demotion["operational"]["timeoutShare"])} reported separately), '
                     f'latency p90 {_num(lat["p90"], 0)} ms vs {lat["budgetMs"]} ms'
                     f'{" (report-only)" if lat["reportOnly"] else ""}')
    lines += ['', '### Advise (majority-baseline gate, one row per decision)',
              '| decision | mode | labelled | last verdict | accuracy / baseline | cp lower | coverage | critical cases / misses '
              '| attempts | next alpha |', '|---|---|---|---|---|---|---|---|---|---|']
    for row in data['advise']:
        accuracy = '-' if row.get('accuracy') is None else f'{_pct(row["accuracy"])} / {_pct(row.get("baselineAccuracy"))}'
        critical = '-' if row.get('criticalCases') is None else f'{row["criticalCases"]} / {row["criticalMisses"]}'
        lines.append(f'| {row["decision"]} | {row["mode"]} | {"-" if row["labelled"] is None else row["labelled"]} | '
                     f'{row["lastVerdict"] or "-"} | {accuracy} | {_num(row.get("cpLower"))} | {_pct(row.get("coverage"), 0)} | '
                     f'{critical} | {row["attempts"]}{" (ledger invalid)" if row["ledger"] != "ok" else ""} | {row["nextAlpha"]:g} |')
    versions = (data['lastCycle'] or {}).get('versions')
    if versions:
        lines.append(f'- Versions: policy {versions["policySha256"][:12]}, instrument {versions["instrumentSha256"][:12]}, '
                     f'Laya {versions["layaRevision"] or "-"}, registry rev {versions["registryRevision"]}')
    return '\n'.join(lines) + '\n'


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Render the skill-fit scoreboard.')
    sub = parser.add_subparsers(dest='command', required=True)
    render = sub.add_parser('render', help='render the scoreboard')
    render.add_argument('--root', help='typed-decisions data root (default: RHIZE_TYPED_DECISIONS_ROOT or ~/.local/share/rhize/typed-decisions)')
    render.add_argument('--format', choices=('md', 'json'), default='md')
    render.add_argument('--out', help='write to this file (0600) instead of stdout')
    render.add_argument('--now', help='ISO-8601 time with timezone (default: now)')
    args = parser.parse_args(argv)
    root = Path(args.root) if args.root else records.default_root()
    try:
        data = build(root, args.now)
    except (OSError, ValueError) as err:
        print(json.dumps({'status': 'error', 'error': str(err)}, sort_keys=True))
        return 2
    text = render_md(data) if args.format == 'md' else json.dumps(data, sort_keys=True, indent=1) + '\n'
    if args.out:
        locked_io.write_private_atomic(Path(args.out), text.encode('utf-8'))
        print(json.dumps({'status': 'ok', 'out': args.out, 'format': args.format}, sort_keys=True))
    else:
        sys.stdout.write(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
