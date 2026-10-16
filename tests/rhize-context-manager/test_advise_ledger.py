"""advise-v1 cohort ledger: open/reserve precede consumed, attempts are per decision, groups and case ids are single use."""
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


G = {name: ledger.group_hash(name) for name in ('g1', 'g2', 'g3', 'g4', 'g7', 'g9')}


def reserve(cohort='1' * 32, attempt=1, ids=('c1', 'c2'), policy=POLICY, rev=REV, groups=None, **extra):
    groups = groups if groups is not None else [G['g' + i[1:]] if 'g' + i[1:] in G else ledger.group_hash(i) for i in ids]
    return {'event': 'reserve', 'cohortId': cohort, 'decision': D, 'policySha256': policy,
            'instrumentSha256': INSTRUMENT, 'layaRevision': rev, 'attempt': attempt, 'alpha': 0.1,
            'caseIds': sorted(ids), 'groups': sorted(groups), 'ts': '2026-10-16T00:00:00Z', **extra}


def opened(cohort='1' * 32, attempt=1, policy=POLICY, rev=REV, **extra):
    return {'event': 'open', 'cohortId': cohort, 'decision': D, 'policySha256': policy,
            'instrumentSha256': INSTRUMENT, 'layaRevision': rev, 'attempt': attempt, 'alpha': 0.1,
            'openedAt': '2026-10-16T00:00:00Z', 'rule': ledger.OPEN_RULE, 'ts': '2026-10-16T00:00:00Z', **extra}


def abandoned(cohort='1' * 32, attempt=1, policy=POLICY, rev=REV):
    return {'event': 'abandoned', 'cohortId': cohort, 'decision': D, 'policySha256': policy,
            'instrumentSha256': INSTRUMENT, 'layaRevision': rev, 'attempt': attempt, 'alpha': 0.1,
            'reason': 'binding_changed', 'ts': '2026-10-16T00:00:30Z'}


def consumed(cohort='1' * 32, attempt=1, verdict='pass', policy=POLICY, rev=REV, **extra):
    return {'event': 'consumed', 'cohortId': cohort, 'decision': D, 'policySha256': policy,
            'instrumentSha256': INSTRUMENT, 'layaRevision': rev, 'attempt': attempt, 'alpha': 0.1,
            'verdict': verdict, 'receiptSha256': 'c' * 64, 'ts': '2026-10-16T00:01:00Z', **extra}


def live_end(names=('g1', 'g2'), **kwargs):
    """consumed fields for an open cohort: one case per group."""
    return {'caseIds': sorted('case-' + n for n in names), 'groups': sorted(ledger.group_hash(n) for n in names), **kwargs}


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
        ledger.append(tmp_path, D, reserve(cohort='2' * 32, attempt=1, ids=('c9',), groups=[G['g9']]))
    ledger.append(tmp_path, D, reserve(cohort='2' * 32, attempt=2, ids=('c9',), groups=[G['g9']], policy='e' * 64, rev='rev-2'))
    assert ledger.next_attempt(tmp_path, D) == 3
    assert ledger.next_attempt(tmp_path, 'procedure-pick') == 1


def test_reserved_case_ids_can_never_be_reused(tmp_path):
    ledger.append(tmp_path, D, reserve(ids=('c1', 'c2')))
    ledger.append(tmp_path, D, consumed())
    assert ledger.consumed_case_ids(tmp_path, D) == {'c1', 'c2'}
    with pytest.raises(ValueError, match='already used'):
        ledger.append(tmp_path, D, reserve(cohort='2' * 32, attempt=2, ids=('c2', 'c3')))     # groups g2 reused
    with pytest.raises(ValueError, match='already reserved'):
        ledger.append(tmp_path, D, reserve(cohort='2' * 32, attempt=2, ids=('c2',), groups=[G['g9']]))   # case id reused
    with pytest.raises(ValueError, match='cohort already reserved'):
        ledger.append(tmp_path, D, reserve(attempt=2, ids=('c3',), groups=[G['g3']]))
    assert ledger.consumed_case_ids(tmp_path, 'other-decision') == set()


@pytest.mark.parametrize('bad', [
    {'cohortId': 'xyz'}, {'groups': []}, {'groups': ['g1']}, {'groups': [G['g1']]}, {'policySha256': 'short'}, {'attempt': 0}, {'attempt': True}, {'alpha': 0}, {'alpha': 1.5},
    {'ts': 'yesterday'}, {'caseIds': []}, {'caseIds': ['b', 'a']}, {'caseIds': ['a', 'a']}, {'extra': 1},
    {'decision': 'procedure-pick'}, {'layaRevision': 'bad rev'}, {'event': 'other'}])
def test_reserve_shape_is_validated(tmp_path, bad):
    with pytest.raises(ValueError):
        ledger.append(tmp_path, D, {**reserve(), **bad})
    assert ledger.read(tmp_path, D) == []


def test_consumed_shape_is_validated(tmp_path):
    ledger.append(tmp_path, D, reserve())
    for bad in ({'verdict': 'maybe'}, {'receiptSha256': 'x'}, {'caseIds': ['c1']}, {'extra': 1}, {'groups': [G['g1']]}):
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
    ledger.append(tmp_path, D, reserve(cohort='2' * 32, attempt=2, ids=('c7',), groups=[G['g7']]))
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


# ---- group is the statistical unit; live cohorts (open ... consumed / abandoned)

def test_a_group_can_be_in_only_one_cohort_whatever_the_case_ids(tmp_path):
    ledger.append(tmp_path, D, reserve(ids=('c1', 'c2')))
    with pytest.raises(ValueError, match='groups already used'):
        ledger.append(tmp_path, D, reserve(cohort='2' * 32, attempt=2, ids=('other',), groups=[G['g1']]))
    assert ledger.used_groups(tmp_path, D) == {G['g1'], G['g2']}


def test_a_cohort_holds_one_case_per_group(tmp_path):
    with pytest.raises(ValueError, match='one case per group'):
        ledger.append(tmp_path, D, reserve(ids=('c1', 'c2'), groups=[G['g1']]))
    ledger.append(tmp_path, D, opened())
    with pytest.raises(ValueError, match='one case per group'):
        ledger.append(tmp_path, D, consumed(caseIds=['a', 'b'], groups=[G['g1']]))


def test_open_then_consumed_carries_its_cases_and_spends_groups_and_an_attempt(tmp_path):
    ledger.append(tmp_path, D, opened())
    assert ledger.open_cohort(tmp_path, D)['cohortId'] == '1' * 32 and ledger.next_attempt(tmp_path, D) == 2
    assert ledger.used_groups(tmp_path, D) == set()                      # nothing is selected yet
    with pytest.raises(ValueError, match='caseIds and groups'):
        ledger.append(tmp_path, D, consumed())                           # an open cohort names what it used
    ledger.append(tmp_path, D, consumed(**live_end()))
    assert ledger.open_cohort(tmp_path, D) is None
    assert ledger.used_groups(tmp_path, D) == {ledger.group_hash('g1'), ledger.group_hash('g2')}
    assert ledger.consumed_case_ids(tmp_path, D) == {'case-g1', 'case-g2'}
    assert ledger.verify_pass(tmp_path, D, binding()) is None            # the registry accepts an open-born pass
    ledger.append(tmp_path, D, opened(cohort='2' * 32, attempt=2))
    with pytest.raises(ValueError, match='groups already used'):
        ledger.append(tmp_path, D, consumed(cohort='2' * 32, attempt=2, **live_end(('g2', 'g3'))))
    ledger.append(tmp_path, D, consumed(cohort='2' * 32, attempt=2, **live_end(('g3', 'g4'))))


def test_a_reserved_cohort_is_consumed_without_caseids(tmp_path):
    ledger.append(tmp_path, D, reserve())
    with pytest.raises(ValueError, match='without caseIds'):
        ledger.append(tmp_path, D, consumed(**live_end(('g3',))))


def test_only_one_cohort_is_open_at_a_time_and_abandoning_keeps_the_attempt_spent(tmp_path):
    ledger.append(tmp_path, D, opened())
    with pytest.raises(ValueError, match='already open'):
        ledger.append(tmp_path, D, opened(cohort='2' * 32, attempt=2))
    ledger.append(tmp_path, D, abandoned())
    assert ledger.open_cohort(tmp_path, D) is None and ledger.next_attempt(tmp_path, D) == 2
    with pytest.raises(ValueError, match='already abandoned'):
        ledger.append(tmp_path, D, consumed(**live_end()))
    with pytest.raises(ValueError, match='already abandoned'):
        ledger.append(tmp_path, D, abandoned())
    with pytest.raises(ValueError, match='no consumed'):
        ledger.verify_pass(tmp_path, D, binding())
    ledger.append(tmp_path, D, opened(cohort='2' * 32, attempt=2, policy='e' * 64))
    ledger.append(tmp_path, D, consumed(cohort='2' * 32, attempt=2, policy='e' * 64, **live_end()))


def test_abandon_needs_a_matching_open_cohort(tmp_path):
    with pytest.raises(ValueError, match='prior open'):
        ledger.append(tmp_path, D, abandoned())
    ledger.append(tmp_path, D, reserve())
    with pytest.raises(ValueError, match='prior open'):
        ledger.append(tmp_path, D, abandoned())
    ledger.append(tmp_path, D, opened(cohort='2' * 32, attempt=2))
    with pytest.raises(ValueError, match='policySha256 differs'):
        ledger.append(tmp_path, D, abandoned(cohort='2' * 32, attempt=2, policy='d' * 64))
    ledger.append(tmp_path, D, consumed(cohort='2' * 32, attempt=2, **live_end(('g3', 'g4'))))
    with pytest.raises(ValueError, match='already consumed'):
        ledger.append(tmp_path, D, abandoned(cohort='2' * 32, attempt=2))


@pytest.mark.parametrize('bad', [{'rule': 'latest-record'}, {'openedAt': 'soon'}, {'extra': 1}, {'caseIds': ['a']}])
def test_open_shape_is_validated(tmp_path, bad):
    with pytest.raises(ValueError):
        ledger.append(tmp_path, D, {**opened(), **bad})
    assert ledger.read(tmp_path, D) == []
