"""advise-v1 cohort ledger: reserve precedes consumed, attempts are per decision, case ids are single use."""
from __future__ import annotations

import json
import stat
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'rhize-context-manager/scripts'))
from typed_decisions import advise_ledger as ledger  # noqa: E402

D = 'workflow-fit'
POLICY, INSTRUMENT, REV = 'a' * 64, 'b' * 64, 'rev-1'


def reserve(cohort='1' * 32, attempt=1, ids=('c1', 'c2'), policy=POLICY, rev=REV, **extra):
    return {'event': 'reserve', 'cohortId': cohort, 'decision': D, 'policySha256': policy,
            'instrumentSha256': INSTRUMENT, 'layaRevision': rev, 'attempt': attempt, 'alpha': 0.1,
            'caseIds': sorted(ids), 'ts': '2026-10-16T00:00:00Z', **extra}


def consumed(cohort='1' * 32, attempt=1, verdict='pass', policy=POLICY, rev=REV):
    return {'event': 'consumed', 'cohortId': cohort, 'decision': D, 'policySha256': policy,
            'instrumentSha256': INSTRUMENT, 'layaRevision': rev, 'attempt': attempt, 'alpha': 0.1,
            'verdict': verdict, 'receiptSha256': 'c' * 64, 'ts': '2026-10-16T00:01:00Z'}


def binding(cohort='1' * 32, **changes):
    return {'cohortId': cohort, 'policySha256': POLICY, 'instrumentSha256': INSTRUMENT, 'layaRevision': REV, **changes}


def test_append_is_private_and_readable(tmp_path):
    root = tmp_path / 'store'
    ledger.append(root, D, reserve())
    ledger.append(root, D, consumed())
    path = root / D / 'advise-cohorts.jsonl'
    assert stat.S_IMODE(path.stat().st_mode) == 0o600 and stat.S_IMODE((root / D).stat().st_mode) == 0o700
    assert [e['event'] for e in ledger.read(root, D)] == ['reserve', 'consumed']
    assert ledger.read(root, 'other-decision') == []


def test_consumed_needs_a_prior_reserve_and_only_one_consumed(tmp_path):
    with pytest.raises(ValueError, match='prior reserve'):
        ledger.append(tmp_path, D, consumed())
    ledger.append(tmp_path, D, reserve())
    ledger.append(tmp_path, D, consumed())
    with pytest.raises(ValueError, match='already consumed'):
        ledger.append(tmp_path, D, consumed(verdict='hold'))
    assert len(ledger.read(tmp_path, D)) == 2


def test_consumed_must_match_its_reserve(tmp_path):
    ledger.append(tmp_path, D, reserve())
    with pytest.raises(ValueError, match='policySha256 differs'):
        ledger.append(tmp_path, D, consumed(policy='d' * 64))
    with pytest.raises(ValueError, match='layaRevision differs'):
        ledger.append(tmp_path, D, consumed(rev='rev-2'))


def test_attempts_count_per_decision_across_policies_and_revisions(tmp_path):
    assert ledger.next_attempt(tmp_path, D) == 1
    ledger.append(tmp_path, D, reserve())
    assert ledger.next_attempt(tmp_path, D) == 2           # reserved but never consumed still counts
    with pytest.raises(ValueError, match='next attempt'):
        ledger.append(tmp_path, D, reserve(cohort='2' * 32, attempt=1, ids=('c9',)))
    ledger.append(tmp_path, D, reserve(cohort='2' * 32, attempt=2, ids=('c9',), policy='e' * 64, rev='rev-2'))
    assert ledger.next_attempt(tmp_path, D) == 3
    assert ledger.next_attempt(tmp_path, 'procedure-pick') == 1


def test_reserved_case_ids_can_never_be_reused(tmp_path):
    ledger.append(tmp_path, D, reserve(ids=('c1', 'c2')))
    ledger.append(tmp_path, D, consumed())
    assert ledger.consumed_case_ids(tmp_path, D) == {'c1', 'c2'}
    with pytest.raises(ValueError, match='already reserved'):
        ledger.append(tmp_path, D, reserve(cohort='2' * 32, attempt=2, ids=('c2', 'c3')))
    with pytest.raises(ValueError, match='cohort already reserved'):
        ledger.append(tmp_path, D, reserve(attempt=2, ids=('c3',)))
    assert ledger.consumed_case_ids(tmp_path, 'other-decision') == set()


@pytest.mark.parametrize('bad', [
    {'cohortId': 'xyz'}, {'policySha256': 'short'}, {'attempt': 0}, {'attempt': True}, {'alpha': 0}, {'alpha': 1.5},
    {'ts': 'yesterday'}, {'caseIds': []}, {'caseIds': ['b', 'a']}, {'caseIds': ['a', 'a']}, {'extra': 1},
    {'decision': 'procedure-pick'}, {'layaRevision': 'bad rev'}, {'event': 'other'}])
def test_reserve_shape_is_validated(tmp_path, bad):
    with pytest.raises(ValueError):
        ledger.append(tmp_path, D, {**reserve(), **bad})
    assert ledger.read(tmp_path, D) == []


def test_consumed_shape_is_validated(tmp_path):
    ledger.append(tmp_path, D, reserve())
    for bad in ({'verdict': 'maybe'}, {'receiptSha256': 'x'}, {'caseIds': ['c1']}):
        with pytest.raises(ValueError):
            ledger.append(tmp_path, D, {**consumed(), **bad})
    missing = consumed(); del missing['verdict']
    with pytest.raises(ValueError):
        ledger.append(tmp_path, D, missing)


def test_verify_pass_accepts_only_a_matching_pass(tmp_path):
    ledger.append(tmp_path, D, reserve())
    with pytest.raises(ValueError, match='no consumed'):
        ledger.verify_pass(tmp_path, D, binding())                      # reserved, not consumed
    ledger.append(tmp_path, D, consumed())
    assert ledger.verify_pass(tmp_path, D, binding()) is None
    for name, value in (('policySha256', 'd' * 64), ('instrumentSha256', 'd' * 64), ('layaRevision', 'rev-2'),
                        ('cohortId', '9' * 32)):
        with pytest.raises(ValueError):
            ledger.verify_pass(tmp_path, D, binding(**{name: value}))
    with pytest.raises(ValueError):
        ledger.verify_pass(tmp_path, D, {'cohortId': '1' * 32})
    with pytest.raises(ValueError, match='no consumed'):
        ledger.verify_pass(tmp_path, 'procedure-pick', binding())
    ledger.append(tmp_path, D, reserve(cohort='2' * 32, attempt=2, ids=('c7',)))
    ledger.append(tmp_path, D, consumed(cohort='2' * 32, attempt=2, verdict='hold'))
    with pytest.raises(ValueError, match='did not pass'):
        ledger.verify_pass(tmp_path, D, binding(cohort='2' * 32))


def test_symlinked_store_paths_are_refused(tmp_path):
    real = tmp_path / 'real'; real.mkdir()
    root = tmp_path / 'store'; root.mkdir()
    (root / D).symlink_to(real)
    with pytest.raises(ValueError):
        ledger.append(root, D, reserve())
    other = tmp_path / 'store2'
    (other / D).mkdir(parents=True)
    (other / D / 'advise-cohorts.jsonl').symlink_to(real / 'target.jsonl')
    with pytest.raises(OSError):
        ledger.append(other, D, reserve())
    assert not (real / 'target.jsonl').exists()


def test_a_torn_line_is_skipped_but_an_invalid_event_fails_closed(tmp_path):
    ledger.append(tmp_path, D, reserve())
    path = tmp_path / D / 'advise-cohorts.jsonl'
    with open(path, 'a') as stream:
        stream.write('{"event": "consu')                                # crash mid-append
    ledger.append(tmp_path, D, consumed())
    assert [e['event'] for e in ledger.read(tmp_path, D)] == ['reserve', 'consumed']
    with open(path, 'a') as stream:
        stream.write(json.dumps({'event': 'consumed', 'cohortId': 'nope'}) + '\n')
    with pytest.raises(ValueError):
        ledger.read(tmp_path, D)
    with pytest.raises(ValueError):
        ledger.verify_pass(tmp_path, D, binding())


def test_invalid_decision_names_are_refused(tmp_path):
    for name in ('../x', 'A', 'x'):
        with pytest.raises(ValueError):
            ledger.read(tmp_path, name)
