"""Append-only cohort ledger for the majority-baseline (advise-v1) gate (plan §3.5, §11).

One file per decision: <root>/<decision>/advise-cohorts.jsonl. A promotion cohort is `reserve`d (with its
case ids) before it is evaluated and `consumed` by exactly one verdict. Attempts are counted per decision
across every policy and Laya revision, and a reserved case id can never be reserved again. Appends run under
an exclusive lock; dirs are 0700, the file is 0600, symlinks are refused.

Stdlib only, Python 3.9 compatible.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from typed_decisions import locked_io

LEDGER_FILE = 'advise-cohorts.jsonl'
LOCK_FILE = 'advise-cohorts.lock'
LOCK_TIMEOUT_SECONDS = 10.0

_HEX32 = re.compile(r'[0-9a-f]{32}\Z')
_HEX64 = re.compile(r'[0-9a-f]{64}\Z')
_DECISION = re.compile(r'[a-z][a-z0-9-]{1,40}\Z')
_REVISION = re.compile(r'[A-Za-z0-9._-]{1,80}\Z')
_COMMON = {'event', 'cohortId', 'decision', 'policySha256', 'instrumentSha256', 'layaRevision', 'attempt', 'alpha', 'ts'}
_FIELDS = {'reserve': _COMMON | {'caseIds'}, 'consumed': _COMMON | {'verdict', 'receiptSha256'}}
_OPTIONAL = {'reserve': {'baseline'}, 'consumed': set()}
BINDING_KEYS = ('cohortId', 'policySha256', 'instrumentSha256', 'layaRevision')


def _ledger_path(root, decision) -> Path:
    if not isinstance(decision, str) or not _DECISION.match(decision):
        raise ValueError('invalid decision')
    return Path(root) / decision / LEDGER_FILE


def _check(event, decision) -> None:
    if not isinstance(event, dict) or event.get('event') not in _FIELDS:
        raise ValueError('event must be reserve or consumed')
    kind = event['event']
    keys = set(event)
    if not _FIELDS[kind] <= keys <= _FIELDS[kind] | _OPTIONAL[kind]:
        raise ValueError(f'{kind} event has the wrong fields')
    if event['decision'] != decision:
        raise ValueError('event decision does not match the ledger')
    if not isinstance(event['cohortId'], str) or not _HEX32.match(event['cohortId']):
        raise ValueError('cohortId must be 32 hex characters')
    for name in ('policySha256', 'instrumentSha256'):
        if not isinstance(event[name], str) or not _HEX64.match(event[name]):
            raise ValueError(f'{name} must be 64 hex characters')
    if not isinstance(event['layaRevision'], str) or not _REVISION.match(event['layaRevision']):
        raise ValueError('invalid layaRevision')
    attempt = event['attempt']
    if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
        raise ValueError('attempt must be an integer >= 1')
    alpha = event['alpha']
    if isinstance(alpha, bool) or not isinstance(alpha, (int, float)) or not 0 < alpha <= 1:
        raise ValueError('alpha must be in (0, 1]')
    locked_io.utc(event['ts'])
    if kind == 'reserve':
        ids = event['caseIds']
        if (not isinstance(ids, list) or not ids or any(not isinstance(i, str) or not i for i in ids)
                or ids != sorted(set(ids))):
            raise ValueError('caseIds must be a nonempty sorted list of unique strings')
        if 'baseline' in event and (not isinstance(event['baseline'], str) or not event['baseline']):
            raise ValueError('baseline must be a nonempty string')
    else:
        if event['verdict'] not in ('pass', 'hold'):
            raise ValueError("verdict must be 'pass' or 'hold'")
        if not isinstance(event['receiptSha256'], str) or not _HEX64.match(event['receiptSha256']):
            raise ValueError('receiptSha256 must be 64 hex characters')


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


def next_attempt(root, decision) -> int:
    """1 + the cohorts ever reserved for this decision (any policy, any Laya revision, consumed or not)."""
    return 1 + sum(event['event'] == 'reserve' for event in read(root, decision))


def consumed_case_ids(root, decision) -> set:
    """Case ids in any reserved cohort: they can never be reserved again."""
    return {case_id for event in read(root, decision) if event['event'] == 'reserve' for case_id in event['caseIds']}


def append(root, decision, event) -> dict:
    """Validate and append one event under the exclusive lock; returns the event.

    reserve: new cohortId, attempt == next_attempt, caseIds disjoint from every earlier reserve.
    consumed: needs a prior reserve of the same cohortId (same decision, policy, instrument, revision, attempt,
    alpha) and at most one consumed per cohort.
    """
    _check(event, decision)
    directory = locked_io.private_dir(_ledger_path(root, decision).parent, anchor=Path(root))
    with locked_io.file_lock(directory / LOCK_FILE, LOCK_TIMEOUT_SECONDS):
        events = read(root, decision)
        reserved = {e['cohortId']: e for e in events if e['event'] == 'reserve'}
        if event['event'] == 'reserve':
            if event['cohortId'] in reserved:
                raise ValueError('cohort already reserved')
            if event['attempt'] != 1 + len(reserved):
                raise ValueError('attempt must be the next attempt for this decision')
            if set(event['caseIds']) & {i for e in reserved.values() for i in e['caseIds']}:
                raise ValueError('case ids already reserved by an earlier cohort')
        else:
            prior = reserved.get(event['cohortId'])
            if prior is None:
                raise ValueError('consumed needs a prior reserve of the same cohort')
            if any(e['event'] == 'consumed' and e['cohortId'] == event['cohortId'] for e in events):
                raise ValueError('cohort already consumed')
            for name in ('policySha256', 'instrumentSha256', 'layaRevision', 'attempt', 'alpha'):
                if prior[name] != event[name]:
                    raise ValueError(f'consumed {name} differs from its reserve')
        locked_io.append_line(directory / LEDGER_FILE, event)
    return event


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
