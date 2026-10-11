#!/usr/bin/env python3
"""Turn skill-fit decision evidence into learn-harvest refinement candidates (plan §7 F10, §2 H as amended).

    harvest_signals.py emit --queue PRIVATE_JSONL [--root DIR] [--now ISO] [--window-days 14]
                            [--min-events 3] [--repo rhize-plugins]

`emit` reads the skill-fit records and outcomes under --root (records.read) and writes refinement-queue
candidates, one JSON object per line in the learn-harvest schema

    {"id", "ts", "source", "repo", "pattern", "est_savings", "target_skill", "status", "signal_type"}

to --queue ONLY. The file must not exist yet (it is created 0600, atomically, symlinks refused) and the live queue
(~/.claude/context-manager/refinement-queue.jsonl) is refused outright: candidates reach it only through the
learn-harvest filter and verify steps. There is no watermark: every run is idempotent over the trailing
--window-days window, `id` is sha1-12(source + pattern) and the pattern text carries no counts and no dates, so
the same finding keeps the same id from day to day and the queue's own dedupe (any status) absorbs repeats.

Signals, grouped per (signal, subtype, skill, host); a group becomes a candidate at >= --min-events events.
Signals 1-3 look at finalized records (a record with an outcome) whose ts is inside the window:

  1. routing-miss / not-shortlisted             outcome invoked_unlisted. target_skill: the invoked skill.
  2. routing-miss / suggested-but-ignored       emitted is non-null and the outcome is invoked_other_shortlisted.
                                                target_skill: the emitted (shown) skill.
  3. decision-layer / cosign-suppressed-then-invoked
                                                mode cosign, arm treatment, emitted null, and the incumbent was
                                                invoked within one user turn. target_skill: the incumbent.
  4. decision-layer / laya-timeouts             live records in the window, >= 20 Laya calls (status not
                                                'skipped') and a timeout share above 5%, one candidate per host.
                                                No outcome is needed. target_skill: null.

Candidates are review candidates, never ground truth. Records and outcomes hold hashes, ids and statuses only,
so no prompt text can reach the output; stdout is counts only.

Exit codes: 0 done, 1 unexpected failure, 2 refused or bad arguments (nothing is written in that case).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from typed_decisions import contract, locked_io, records  # noqa: E402

SOURCE = 'skill-fit-decisions'
DECISION = 'skill-fit'
DEFAULT_REPO = 'rhize-plugins'
MIN_LAYA_CALLS = 20
TIMEOUT_SHARE_PERCENT = 5          # a share strictly above this many percent of Laya calls
INVOKED = ('invoked_emitted', 'invoked_other_shortlisted', 'invoked_unlisted')
QUEUE_KEYS = ('id', 'ts', 'source', 'repo', 'pattern', 'est_savings', 'target_skill', 'status', 'signal_type')
EXIT_OK, EXIT_FAILED, EXIT_USAGE = 0, 1, 2

# Stable pattern text: the signal, subtype, host and skill only. No counts, no dates, no thresholds.
PATTERNS = {
    ('routing-miss', 'not-shortlisted'):
        'routing-miss (not-shortlisted, host {host}): {skill} was invoked soon after prompts where the router '
        'suggested another skill or none and did not shortlist it, repeatedly within the trailing window '
        '— review its tags and trigger phrases.',
    ('routing-miss', 'suggested-but-ignored'):
        'routing-miss (suggested-but-ignored, host {host}): the router suggested {skill} but the user invoked a '
        'different shortlisted skill instead, repeatedly within the trailing window — review its tags and '
        'trigger phrases, and whether the suggestion fires on the wrong prompts.',
    ('decision-layer', 'cosign-suppressed-then-invoked'):
        'decision-layer (cosign-suppressed-then-invoked, host {host}): the co-sign withheld the router suggestion '
        '{skill} (Laya disagreed or was unavailable) and the user invoked it within one turn anyway, repeatedly '
        'within the trailing window — review whether the co-sign path suppresses good suggestions for this '
        'skill.',
    ('decision-layer', 'laya-timeouts'):
        'decision-layer (laya-timeouts, host {host}): the Laya co-sign call timed out on an elevated share of '
        'live decisions in the trailing window — review keep-warm health and the latency budget.',
}


class HarvestError(Exception):
    """A bounded, non-secret refusal."""


def live_queue_path() -> Path:
    return Path.home() / '.claude' / 'context-manager' / 'refinement-queue.jsonl'


def check_queue_path(queue) -> Path:
    """The expanded queue path when it is safe to create; HarvestError otherwise.

    Refused: the live queue (by resolved path, by inode of its directory for case or symlink variants), a
    symlink (even a dangling one), and a path that already exists.
    """
    path = Path(queue).expanduser()
    live = live_queue_path()
    if os.path.realpath(path) == os.path.realpath(live):
        raise HarvestError('the live refinement queue is never written by emit')
    try:
        same_directory = os.path.samefile(path.parent, live.parent)
    except OSError:
        same_directory = False
    if same_directory and path.name.lower() == live.name.lower():
        raise HarvestError('the live refinement queue is never written by emit')
    if os.path.islink(path):
        raise HarvestError('symlinked queue path refused')
    if os.path.lexists(path):
        raise HarvestError('queue file already exists; emit writes a new private file')
    return path


def skill_ref(skill_id):
    """'<plugin>:<skill>' for a skill id (mirror of outcomes.skill_ref, kept local to avoid its heavy imports)."""
    if not isinstance(skill_id, str) or not skill_id.startswith('skill:'):
        return None
    parts = skill_id[len('skill:'):].split('/')
    if len(parts) == 2:
        plugin, name = parts
    elif len(parts) == 3:
        plugin, name = parts[1], parts[2]
    else:
        return None
    return f'{plugin}:{name}' if plugin and name else None


def target_for_id(skill_id: str) -> str:
    """Queue `target_skill` for a skill id: skill:plugin/name -> plugin/name."""
    return skill_id[len('skill:'):]


def label_for_ref(ref: str) -> tuple:
    """(pattern label, queue target_skill) for an invoked ref such as 'plugin:skill' or a bare skill name."""
    if ':' in ref:
        plugin, name = ref.split(':', 1)
        return f'skill:{plugin}/{name}', f'{plugin}/{name}'
    return f'skill:{ref}', ref


def entry_id(pattern: str) -> str:
    return hashlib.sha1((SOURCE + pattern).encode('utf-8')).hexdigest()[:12]


def candidate(signal_type, subtype, host, label, target, ts, repo) -> dict:
    pattern = PATTERNS[(signal_type, subtype)].format(host=host, skill=label)
    return {'id': entry_id(pattern), 'ts': ts, 'source': SOURCE, 'repo': repo, 'pattern': pattern,
            'est_savings': None, 'target_skill': target, 'status': 'pending', 'signal_type': signal_type}


def _dedupe_by_occurrence(recs):
    """One record per occurrenceKey, preferring a live record over a backfill replay of the same prompt."""
    chosen: dict = {}
    for rec in recs:
        key = rec['occurrenceKey']
        held = chosen.get(key)
        if held is None or (held['basis'] != 'live' and rec['basis'] == 'live'):
            chosen[key] = rec
    return list(chosen.values())


def collect(root, now, window_days=14, min_events=3, repo=DEFAULT_REPO) -> tuple:
    """(candidates, counts) for the trailing window ending at `now` (an aware datetime). Pure reads."""
    start = now - timedelta(days=window_days)
    since_day = start.strftime('%Y-%m-%d')
    recs, invalid_records = records.read(root, DECISION, 'records', since_day=since_day)
    outcomes, invalid_outcomes = records.read(root, DECISION, 'outcomes', since_day=since_day)
    in_window = _dedupe_by_occurrence(
        [rec for rec in recs if start <= locked_io.utc(rec['ts']) <= now])
    latest_outcome = {outcome['occurrenceKey']: outcome for outcome in outcomes}   # a join re-run replaces the row
    finalized = [(rec, latest_outcome[rec['occurrenceKey']]) for rec in in_window
                 if rec['occurrenceKey'] in latest_outcome]

    groups: Counter = Counter()
    for rec, outcome in finalized:
        kind, host = outcome['outcome'], rec['host']
        if outcome.get('via') == 'skill_file_read':
            # Codex evidence is a SKILL.md read, weaker than a Skill tool call: keep it a separate candidate.
            host = f'{host}, SKILL.md-read evidence'
        if kind == 'invoked_unlisted':
            label, target = label_for_ref(outcome['skillInvoked'])
            groups[('routing-miss', 'not-shortlisted', host, label, target)] += 1
        if kind == 'invoked_other_shortlisted' and rec['emitted'] is not None:
            groups[('routing-miss', 'suggested-but-ignored', host, rec['emitted'],
                    target_for_id(rec['emitted']))] += 1
        incumbent = (rec['incumbent'] or {}).get('skillId')
        if (rec['mode'] == 'cosign' and rec['arm'] == 'treatment' and rec['emitted'] is None
                and incumbent is not None and kind in INVOKED and outcome['latencyTurns'] is not None
                and outcome['latencyTurns'] <= 1
                and skill_ref(incumbent) is not None
                and outcome['skillInvoked'].lower() == skill_ref(incumbent).lower()):
            groups[('decision-layer', 'cosign-suppressed-then-invoked', host, incumbent,
                    target_for_id(incumbent))] += 1

    ts = locked_io.iso(now)
    entries = []                                   # (signal_type, subtype, queue entry)
    below = 0
    for (signal_type, subtype, host, label, target), count in groups.items():
        if count >= min_events:
            entries.append((signal_type, subtype, candidate(signal_type, subtype, host, label, target, ts, repo)))
        else:
            below += 1

    calls, timeouts = Counter(), Counter()
    for rec in in_window:
        if rec['basis'] == 'live' and rec['laya']['status'] != 'skipped':
            calls[rec['host']] += 1
            timeouts[rec['host']] += rec['laya']['status'] == 'timeout'
    for host in sorted(calls):
        if calls[host] >= MIN_LAYA_CALLS and timeouts[host] * 100 > calls[host] * TIMEOUT_SHARE_PERCENT:
            entries.append(('decision-layer', 'laya-timeouts',
                            candidate('decision-layer', 'laya-timeouts', host, None, None, ts, repo)))

    entries.sort(key=lambda row: (row[0], row[2]['pattern'], row[2]['id']))
    found = [row[2] for row in entries]
    by_signal = Counter(f'{signal_type}/{subtype}' for signal_type, subtype, _ in entries)
    counts = {'recordsRead': len(recs), 'outcomesRead': len(outcomes),
              'invalidLines': invalid_records + invalid_outcomes, 'inWindow': len(in_window),
              'finalized': len(finalized), 'groupsBelowThreshold': below, 'candidates': len(found),
              'bySignal': dict(sorted(by_signal.items()))}
    return found, counts


def emit(queue, root=None, now=None, window_days=14, min_events=3, repo=DEFAULT_REPO) -> dict:
    """Write the candidates to a new private file at `queue`; returns the counts summary."""
    if window_days <= 0 or min_events < 1 or not isinstance(repo, str) or not repo.strip():
        raise HarvestError('--window-days and --min-events must be positive and --repo non-empty')
    path = check_queue_path(queue)
    root = Path(root) if root else records.default_root()
    moment = locked_io.utc(now)
    found, counts = collect(root, moment, window_days, min_events, repo)
    data = ''.join(json.dumps(item, ensure_ascii=False) + '\n' for item in found).encode('utf-8')
    try:
        locked_io.write_private_exclusive(path, data)
    except FileExistsError:
        raise HarvestError('queue file already exists; emit writes a new private file') from None
    return {'status': 'ok', **counts}


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    sub = parser.add_subparsers(dest='command', required=True)
    run = sub.add_parser('emit', help='write review candidates to a new private JSONL file')
    run.add_argument('--queue', required=True, help='new private JSONL file (must not exist; never the live queue)')
    run.add_argument('--root', default=None, help='typed-decisions root (default: records.default_root())')
    run.add_argument('--now', default=None, help='ISO-8601 time with timezone (default: now)')
    run.add_argument('--window-days', type=int, default=14)
    run.add_argument('--min-events', type=int, default=3)
    run.add_argument('--repo', default=DEFAULT_REPO)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        summary = emit(args.queue, root=args.root, now=args.now, window_days=args.window_days,
                       min_events=args.min_events, repo=args.repo)
    except (HarvestError, ValueError) as exc:
        print(json.dumps({'status': 'refused', 'reason': contract.safe_reason(exc)}))
        return EXIT_USAGE
    except Exception as exc:  # noqa: BLE001 - a bounded error type, never evidence text
        print(json.dumps({'status': 'failed', 'error': type(exc).__name__, 'reason': contract.safe_reason(exc)}))
        return EXIT_FAILED
    print(json.dumps(summary, sort_keys=True))
    return EXIT_OK


if __name__ == '__main__':
    raise SystemExit(main())
