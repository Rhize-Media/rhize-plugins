#!/usr/bin/env python3
"""Join skill-fit decision records to what happened next in the session transcript (plan §4.5, A4).

    outcomes.py join [--root DIR] [--transcripts DIR...] [--window-minutes 30] [--turns 3]

For every record without an outcome (matched by decisionId) whose window has closed, the session transcript is
located through sha256(session_id) (records keep only sessionHash), the prompt turn is anchored by promptHash,
and the `Skill` tool_use events and skill slash commands after it are collected within the window (minutes after
the record) AND the next N user turns. The outcome is the first match in this order:

    invoked_emitted            the emitted skill was invoked (never for records with emitted null)
    invoked_other_shortlisted  another shortlisted skill was invoked
    invoked_unlisted           some other skill or command was invoked
    none_invoked               nothing was invoked in the window
    transcript_unavailable     no readable Claude transcript for the session

`plugin:skill` references are normalized to skill ids through the record's own shortlist (a bare name matches when
it is unique there); skillInvoked keeps the plugin:skill form. Windows that have not closed yet are left for a
later run. The join is idempotent (one outcome per decisionId) and prints counts only. Outcomes are a secondary
signal; the transcript is read in memory and no text is stored (transcriptSha256 is the hash of the file bytes read).

Exit codes: 0 done, 2 bad inputs or no transcripts under the roots (nothing is written in that case).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pilot_autolabel as auto  # noqa: E402
from typed_decisions import contract, evidence_fs, records, transcripts  # noqa: E402

DECISION = 'skill-fit'
EXIT_OK, EXIT_USAGE = 0, 2


class OutcomesError(Exception):
    """A bounded, non-secret failure."""


def skill_ref(skill_id):
    """'<plugin>:<skill>' for a skill id (Python mirror of route-core.js formatSkillRef), else None."""
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


def _norm(ref: str) -> str:
    return ref.strip().lstrip('/').lower()


def resolver(record):
    """ref -> (canonical plugin:skill, is_emitted) for the record's shortlisted skills, or None."""
    emitted = record.get('emitted')
    entries = []
    for skill_id in record['shortlist']:
        ref = skill_ref(skill_id)
        if ref:
            entries.append((ref, skill_id == emitted))
    by_ref = {_norm(ref): (ref, is_emitted) for ref, is_emitted in entries}
    by_name: dict = {}
    for ref, is_emitted in entries:
        by_name.setdefault(_norm(ref).split(':', 1)[1], []).append((ref, is_emitted))

    def resolve(raw):
        key = _norm(raw)
        if key in by_ref:
            return by_ref[key]
        if ':' not in key and len(by_name.get(key, [])) == 1:
            return by_name[key][0]
        return None
    return resolve


def classify(record, invocations):
    """(outcome, invocation | None, canonical skillInvoked | None) for one record's in-window invocations."""
    resolve = resolver(record)
    usable = [item for item in invocations if contract.SKILL_REF.match(item['skillRef'])]
    resolved = [(item, resolve(item['skillRef'])) for item in usable]
    for item, hit in resolved:
        if hit and hit[1]:
            return 'invoked_emitted', item, hit[0]
    for item, hit in resolved:
        if hit:
            return 'invoked_other_shortlisted', item, hit[0]
    if usable:
        return 'invoked_unlisted', usable[0], usable[0]['skillRef'].lstrip('/')
    return 'none_invoked', None, None


def anchor_for(parsed, prompt_hash, record_epoch):
    """The transcript line of the prompt turn nearest the record time (within tolerance), else None."""
    best = None
    for turn in parsed.turns:
        if turn['hash'] != prompt_hash or turn['epoch'] is None:
            continue
        gap = abs(turn['epoch'] - record_epoch)
        if gap <= auto.TIMESTAMP_TOLERANCE_SECONDS and (best is None or gap < best[0]):
            best = (gap, turn['line'])
    return best[1] if best else None


def join(root=None, transcripts_roots=None, window_minutes=30, turns=3, now=None, scanner=None):
    """Append one outcome per record that lacks one. Returns (summary of counts, exit code)."""
    root = Path(root) if root else records.default_root()
    if window_minutes <= 0 or turns < 0:
        raise OutcomesError('--window-minutes must be positive and --turns not negative')
    now = now or datetime.now(timezone.utc)
    scanner = scanner or transcripts.TranscriptScanner(transcripts_roots or default_roots())
    evidence_fs.tighten(root / DECISION)
    with evidence_fs.exclusive_lock(root / DECISION / 'join' / 'run.lock') as held:
        if not held:
            return {'status': 'busy'}, EXIT_OK
        recs, _ = records.read(root, DECISION, 'records')
        outcomes, _ = records.read(root, DECISION, 'outcomes')
        joined = {outcome['decisionId'] for outcome in outcomes}
        pending = [record for record in recs if record['decisionId'] not in joined]
        summary = Counter(records=len(recs), alreadyJoined=len(recs) - len(pending), pendingWindow=0, written=0)
        if pending and not scanner.paths():
            raise OutcomesError('no transcripts found under the given roots; nothing was written')
        window = timedelta(minutes=window_minutes)
        due = []
        for record in pending:
            moment = datetime.fromisoformat(record['ts'].replace('Z', '+00:00'))
            if now < moment + window:
                summary['pendingWindow'] += 1
            else:
                due.append((record['sessionHash'], moment, record))
        due.sort(key=lambda item: (item[0], item[1], item[2]['decisionId']))
        by_outcome = Counter()
        joined_at = transcripts.utc_iso(now.timestamp())
        for session_hash, moment, record in due:
            outcome = outcome_for(record, moment, scanner, window_minutes, turns, joined_at)
            records.append(root, DECISION, 'outcomes', outcome)
            by_outcome[outcome['outcome']] += 1
            summary['written'] += 1
        result = dict(summary)
        result['status'] = 'completed'
        result['outcomes'] = dict(sorted(by_outcome.items()))
        return result, EXIT_OK


def outcome_for(record, moment, scanner, window_minutes, turns, joined_at):
    base = {'schema': contract.OUTCOME_SCHEMA, 'decisionId': record['decisionId'],
            'occurrenceKey': record['occurrenceKey'], 'joinedAt': joined_at}
    unavailable = {**base, 'outcome': 'transcript_unavailable', 'skillInvoked': None, 'via': None,
                   'latencyTurns': None, 'transcriptSha256': None}
    paths = scanner.paths().get(record['sessionHash'], [])
    epoch = moment.timestamp()
    chosen = None
    for path in paths:
        parsed = scanner.parsed(path)
        if isinstance(parsed, str) or parsed.codex:
            continue
        line = anchor_for(parsed, record['promptHash'], epoch)
        if line is not None:
            chosen = (parsed, line)
            break
        chosen = chosen or (parsed, None)
    if chosen is None:
        return unavailable
    parsed, line = chosen
    found = transcripts.invocations_in(parsed, after_epoch=epoch, after_line=line,
                                       until_epoch=epoch + window_minutes * 60, max_user_turns=turns)
    kind, item, ref = classify(record, found)
    return {**base, 'outcome': kind, 'skillInvoked': ref, 'via': item['via'] if item else None,
            'latencyTurns': item['userTurnsAfter'] if item else None, 'transcriptSha256': parsed.sha256}


def default_roots():
    home = Path.home()
    return [home / '.claude' / 'projects', home / '.codex' / 'sessions', home / '.codex' / 'archived_sessions']


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    sub = parser.add_subparsers(dest='command', required=True)
    run = sub.add_parser('join', help='append an outcome for every record that lacks one')
    run.add_argument('--root', default=None, help='typed-decisions root (default ~/.local/share/rhize/typed-decisions)')
    run.add_argument('--transcripts', nargs='+', default=None, metavar='DIR', help='transcript roots')
    run.add_argument('--window-minutes', type=int, default=30)
    run.add_argument('--turns', type=int, default=3, help='user turns after the prompt that still count')
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        summary, code = join(root=args.root, transcripts_roots=args.transcripts, window_minutes=args.window_minutes,
                             turns=args.turns)
    except OutcomesError as exc:
        print(json.dumps({'status': 'refused', 'reason': str(exc)}))
        return EXIT_USAGE
    except Exception as exc:  # noqa: BLE001 - a bounded error type, never transcript text
        print(json.dumps({'status': 'failed', 'error': type(exc).__name__, 'reason': contract.safe_reason(exc)}))
        return 1
    print(json.dumps(summary, sort_keys=True))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
