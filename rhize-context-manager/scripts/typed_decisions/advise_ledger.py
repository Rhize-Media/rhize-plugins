"""Append-only cohort ledger for the majority-baseline (advise-v1) gate (plan §3.5, §11, §12).

One file per decision: <root>/<decision>/advise-cohorts.jsonl. The statistical unit is the group (session):
a group can appear in at most one cohort of a decision, whatever the attempt. Two ways in:
  - `open`: a live, prospective cohort. Opened BEFORE any eligible record exists; its cases are the earliest
    record per group created after `openedAt`. Its single `consumed` event carries the cases and groups used.
    A binding change `abandoned`s it (the attempt, and its alpha, stay spent).
  - `reserve`: a replay cohort (workflow-fit corpus): case ids and groups frozen before Laya is called.
Every cohort ends in exactly one `consumed` verdict or an `abandoned`. Attempts are counted per decision
across every policy and Laya revision (open and reserve both spend one). Appends run under an exclusive
lock; dirs are 0700, the file is 0600, symlinks are refused.

Stdlib only, Python 3.9 compatible.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

from typed_decisions import locked_io
from typed_decisions.contract import HEX32, HEX64, REVISION

LEDGER_FILE = 'advise-cohorts.jsonl'
LOCK_FILE = 'advise-cohorts.lock'
LOCK_TIMEOUT_SECONDS = 10.0

_DECISION = re.compile(r'[a-z][a-z0-9-]{1,40}\Z')
_COMMON = {'event', 'cohortId', 'decision', 'policySha256', 'instrumentSha256', 'layaRevision', 'attempt', 'alpha', 'ts'}
_FIELDS = {'open': _COMMON | {'openedAt', 'rule'}, 'reserve': _COMMON | {'caseIds', 'groups'},
           'consumed': _COMMON | {'verdict', 'receiptSha256'}, 'abandoned': _COMMON | {'reason'}}
_OPTIONAL = {'open': set(), 'reserve': {'baseline'}, 'consumed': {'caseIds', 'groups'}, 'abandoned': set()}
BINDING_KEYS = ('cohortId', 'policySha256', 'instrumentSha256', 'layaRevision')
OPEN_RULE = 'earliest-record-per-promotion-group-after-open'
_REASON = re.compile(r'[a-z_]{1,40}\Z')


def group_hash(group) -> str:
    """The stored form of a group id: sha256 hex of its string."""
    return hashlib.sha256(str(group).encode('utf-8')).hexdigest()


def _ledger_path(root, decision) -> Path:
    if not isinstance(decision, str) or not _DECISION.match(decision):
        raise ValueError('invalid decision')
    return Path(root) / decision / LEDGER_FILE


def _check(event, decision) -> None:
    if not isinstance(event, dict) or event.get('event') not in _FIELDS:
        raise ValueError('event must be open, reserve, consumed or abandoned')
    kind = event['event']
    keys = set(event)
    if not _FIELDS[kind] <= keys <= _FIELDS[kind] | _OPTIONAL[kind]:
        raise ValueError(f'{kind} event has the wrong fields')
    if event['decision'] != decision:
        raise ValueError('event decision does not match the ledger')
    if not isinstance(event['cohortId'], str) or not HEX32.match(event['cohortId']):
        raise ValueError('cohortId must be 32 hex characters')
    for name in ('policySha256', 'instrumentSha256'):
        if not isinstance(event[name], str) or not HEX64.match(event[name]):
            raise ValueError(f'{name} must be 64 hex characters')
    if not isinstance(event['layaRevision'], str) or not REVISION.match(event['layaRevision']):
        raise ValueError('invalid layaRevision')
    attempt = event['attempt']
    if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
        raise ValueError('attempt must be an integer >= 1')
    alpha = event['alpha']
    if isinstance(alpha, bool) or not isinstance(alpha, (int, float)) or not 0 < alpha <= 1:
        raise ValueError('alpha must be in (0, 1]')
    locked_io.utc(event['ts'])
    if kind == 'open':
        locked_io.utc(event['openedAt'])
        if event['rule'] != OPEN_RULE:
            raise ValueError('unknown cohort selection rule')
    elif kind == 'abandoned':
        if not isinstance(event['reason'], str) or not _REASON.match(event['reason']):
            raise ValueError('invalid abandon reason')
    elif kind == 'reserve':
        _sorted_unique(event['caseIds'], 'caseIds')
        _hex_list(event['groups'], 'groups')
        _one_per_group(event)
        if 'baseline' in event and (not isinstance(event['baseline'], str) or not event['baseline']):
            raise ValueError('baseline must be a nonempty string')
    else:
        if event['verdict'] not in ('pass', 'hold'):
            raise ValueError("verdict must be 'pass' or 'hold'")
        if not isinstance(event['receiptSha256'], str) or not HEX64.match(event['receiptSha256']):
            raise ValueError('receiptSha256 must be 64 hex characters')
        if ('caseIds' in event) != ('groups' in event):
            raise ValueError('consumed carries caseIds and groups together')
        if 'caseIds' in event:
            _sorted_unique(event['caseIds'], 'caseIds')
            _hex_list(event['groups'], 'groups')
            _one_per_group(event)


def _sorted_unique(ids, name) -> None:
    if not isinstance(ids, list) or not ids or any(not isinstance(i, str) or not i for i in ids) or ids != sorted(set(ids)):
        raise ValueError(f'{name} must be a nonempty sorted list of unique strings')


def _hex_list(values, name) -> None:
    _sorted_unique(values, name)
    if any(not HEX64.match(v) for v in values):
        raise ValueError(f'{name} must be sha256 hex strings')


def _one_per_group(event) -> None:
    if len(event['groups']) != len(event['caseIds']):
        raise ValueError('a cohort holds exactly one case per group')


def read(root, decision) -> list:
    """All ledger events of `decision`, oldest first ([] when none). A torn (non-JSON) line is skipped; a parsed
    line with an invalid shape raises, so a corrupt ledger never silently grants a pass."""
    try:
        fd = os.open(_ledger_path(root, decision), os.O_RDONLY | locked_io.NOFOLLOW)
    except FileNotFoundError:
        return []
    with os.fdopen(fd, 'rb') as stream:
        raw = stream.read()
    events = []
    for line in raw.decode('utf-8', 'replace').splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        _check(event, decision)
        events.append(event)
    return events


def _cohorts(events) -> dict:
    """{cohortId: opening event} of every open or reserve event."""
    return {e['cohortId']: e for e in events if e['event'] in ('open', 'reserve')}


def _ended(events) -> set:
    return {e['cohortId'] for e in events if e['event'] in ('consumed', 'abandoned')}


def next_attempt(root, decision) -> int:
    """1 + the cohorts ever opened or reserved for this decision (any policy, any Laya revision, ended or not)."""
    return 1 + len(_cohorts(read(root, decision)))


def open_cohort(root, decision):
    """The active (opened, not yet consumed or abandoned) live cohort of `decision`, or None."""
    events = read(root, decision)
    ended = _ended(events)
    live = [e for e in events if e['event'] == 'open' and e['cohortId'] not in ended]
    return live[-1] if live else None


def used_groups(root, decision) -> set:
    """Group hashes (see group_hash) in any reserve or consumed event: they can never be in another cohort."""
    return _used_groups(read(root, decision))


def _used_groups(events) -> set:
    return {g for e in events if e['event'] in ('reserve', 'consumed') for g in e.get('groups', ())}


def consumed_case_ids(root, decision) -> set:
    """Case ids in any reserved or consumed cohort: they can never be used again."""
    return {i for e in read(root, decision) if e['event'] in ('reserve', 'consumed') for i in e.get('caseIds', ())}


def append(root, decision, event) -> dict:
    """Validate and append one event under the exclusive lock; returns the event.

    open: new cohortId, attempt == next_attempt, no other cohort open.
    reserve: new cohortId, attempt == next_attempt, groups and caseIds disjoint from every earlier cohort.
    consumed: needs a prior open or reserve of the same cohortId (same decision, policy, instrument, revision,
    attempt, alpha), at most one end per cohort; an open cohort's consumed names its caseIds and groups, which
    must be disjoint from every earlier cohort.
    abandoned: needs a prior open of the same cohort (same fields) that has not ended.
    """
    _check(event, decision)
    directory = locked_io.private_dir(_ledger_path(root, decision).parent, anchor=Path(root))
    with locked_io.file_lock(directory / LOCK_FILE, LOCK_TIMEOUT_SECONDS):
        events = read(root, decision)
        cohorts, ended = _cohorts(events), _ended(events)
        if event['event'] in ('open', 'reserve'):
            if event['cohortId'] in cohorts:
                raise ValueError('cohort already reserved')
            if event['attempt'] != 1 + len(cohorts):
                raise ValueError('attempt must be the next attempt for this decision')
            if event['event'] == 'open':
                if any(e['event'] == 'open' and e['cohortId'] not in ended for e in events):
                    raise ValueError('an advise cohort is already open')
            else:
                _disjoint(events, event)
        else:
            prior = cohorts.get(event['cohortId'])
            if prior is None or (event['event'] == 'abandoned' and prior['event'] != 'open'):
                raise ValueError('%s needs a prior %s of the same cohort' % (
                    event['event'], 'open' if event['event'] == 'abandoned' else 'reserve'))
            if event['cohortId'] in ended:
                raise ValueError('cohort already %s' % ('consumed' if any(
                    e['event'] == 'consumed' and e['cohortId'] == event['cohortId'] for e in events) else 'abandoned'))
            for name in ('policySha256', 'instrumentSha256', 'layaRevision', 'attempt', 'alpha'):
                if prior[name] != event[name]:
                    raise ValueError(f'{event["event"]} {name} differs from its {prior["event"]}')
            if event['event'] == 'consumed':
                if prior['event'] == 'open':
                    if 'caseIds' not in event:
                        raise ValueError('an open cohort is consumed with its caseIds and groups')
                    _disjoint(events, event)
                elif 'caseIds' in event:
                    raise ValueError('a reserved cohort is consumed without caseIds')
        locked_io.append_line(directory / LEDGER_FILE, event)
    return event


def _disjoint(events, event) -> None:
    if set(event['groups']) & _used_groups(events):
        raise ValueError('groups already used by an earlier cohort')
    if set(event['caseIds']) & {i for e in events if e['event'] in ('reserve', 'consumed') for i in e.get('caseIds', ())}:
        raise ValueError('case ids already reserved by an earlier cohort')


def verify_pass(root, decision, binding) -> None:
    """Return None when binding['cohortId'] has a consumed 'pass' whose policy, instrument and Laya revision equal
    the binding's; raise ValueError otherwise (no cohort, not consumed, hold, or any mismatch)."""
    if not isinstance(binding, dict) or any(not isinstance(binding.get(k), str) for k in BINDING_KEYS):
        raise ValueError('binding needs cohortId, policySha256, instrumentSha256 and layaRevision')
    consumed = [e for e in read(root, decision) if e['event'] == 'consumed' and e['cohortId'] == binding['cohortId']]
    if not consumed:
        raise ValueError('no consumed advise cohort for this binding')
    event = consumed[0]
    if event['verdict'] != 'pass':
        raise ValueError('advise cohort did not pass')
    for name in BINDING_KEYS[1:]:
        if event[name] != binding[name]:
            raise ValueError(f'advise cohort {name} differs from the binding')
