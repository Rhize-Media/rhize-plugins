#!/usr/bin/env python3
"""Daily skill-fit scoreboard (plan §4.6 outputs). Counts and hashes only: no prompt text exists to print.

    scoreboard.py render [--root DIR] [--format md|json] [--out PATH] [--now ISO]

Built from the latest cycle receipt (<root>/skill-fit/cycles/*.json: report-only alternatives, versions,
actions) plus the current registry state, records, labels, outcomes and the registry audit log. The markdown
form is short enough to append to the 08:00 autolabel summary. With no data at all it still renders.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE.parent) not in sys.path:
    sys.path.insert(0, str(HERE.parent))

from typed_decisions import cohorts, decision_registry, locked_io, records  # noqa: E402

SCHEMA = 'rhize-typed-decision-scoreboard-v1'
DECISION = 'skill-fit'


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


def last_mode_change(root):
    lines, _ = decision_registry.read_audit(root)
    for line in reversed(lines):
        if line['phase'] == 'commit' and line['decision'] == DECISION and line['fromMode'] != line['toMode']:
            return {k: line[k] for k in ('at', 'actor', 'fromMode', 'toMode', 'reason', 'revision')}
    return None


def build(root, now=None) -> dict:
    root = Path(root)
    registry = decision_registry.load_registry()
    state, status = decision_registry.read_state(root, registry)
    mode = decision_registry.effective_mode(DECISION, registry, state, status)
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
    }


def _pct(value, digits=1):
    return '-' if value is None else f'{100 * value:.{digits}f}%'


def _num(value, digits=3):
    return '-' if value is None else f'{value:.{digits}f}'


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
    rec = data['records']
    arms = ', '.join(f'{k} {v}' for k, v in sorted(rec['liveArms'].items())) or 'none'
    basis = ', '.join(f'{k} {v}' for k, v in sorted(rec['byBasis'].items())) or 'none'
    lines.append(f'- Records: {rec["total"]} ({basis}); live arms: {arms}; labels: {data["labels"]["total"]}')
    for name in ('live', 'backfill'):
        prev = data['prevalence'][name]
        lines.append(f'- Disagreement prevalence among fired ({name}): {prev["disagreements"]}/{prev["fired"]} ({_pct(prev["share"])})')
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
