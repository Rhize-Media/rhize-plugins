"""Gate scope (plan §7 F6): only GATE_HOSTS records feed the cohort pool, the cohort key, the unavailability share
and every demotion window. Codex records accumulate shadow evidence and must never reach the Claude gate."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from typed_decision_testkit import (  # noqa: E402
    ALT1, INC, LAYA_REV, disagreements, label_cohort, make_label, make_record, small_registry, write_labels,
    write_records)
from typed_decisions import cohorts, contract, decision_registry as reg, records  # noqa: E402

SKILL = 'skill-fit'
T_RESERVE = '2026-10-11T00:00:00Z'
NOW = '2026-10-12T12:00:00Z'


@pytest.fixture(autouse=True)
def _runtime_pin(monkeypatch):
    """Roots without a laya-runtime.json read as running the fixtures' checkpoint (LAYA_REV); a real pin file wins."""
    real = records.laya_revision

    def pinned(root=None):
        value = real(root)
        base = Path(root) if root is not None else records.default_root()
        return LAYA_REV if value == 'unknown' and not (base / 'laya-runtime.json').exists() else value

    monkeypatch.setattr(records, 'laya_revision', pinned)


@pytest.fixture
def root(tmp_path):
    path = tmp_path / 'typed-decisions'
    path.mkdir(mode=0o700)
    (path / 'laya-runtime.json').write_text(json.dumps({'revision': LAYA_REV}))
    return path


@pytest.fixture
def registry():
    return small_registry()


def codex(rec):
    """The same record as written by a Codex session."""
    rec = copy.deepcopy(rec)
    rec['host'] = 'codex'
    return contract.validate_record(rec)


def codex_records(n, start, **kwargs):
    return [codex(make_record(start + k, **kwargs)) for k in range(n)]


def go_cosign(root, registry, since='2026-10-01T00:00:00Z'):
    entry = reg.load_registry()['decisions'][SKILL]
    policy_hash, instrument_hash = cohorts.deployable_hashes(entry)
    binding = {'policySha256': policy_hash, 'instrumentSha256': instrument_hash, 'layaRevision': LAYA_REV,
               'cohortId': None}
    return reg.mutate(root, SKILL, 'cosign', actor='cli', reason='manual_override', expected_revision=0,
                      binding=binding, now=since, registry=registry)


def cosign_state(root, registry):
    return reg.read_state(root, registry)[0]


def label_all(root, recs, *, wrong):
    labels = []
    for index, rec in enumerate(recs):
        labels.append(make_label(rec, acceptable=[ALT1] if index < wrong else [INC], inclusion=0.5))
    write_labels(root, labels)


def cosign_disagreements(start, n, **kwargs):
    return [make_record(start + k, mode='cosign', ts=f'2026-10-{5 + k % 6:02d}T10:{k % 60:02d}:05.000Z', **kwargs)
            for k in range(n)]


# ---------------------------------------------------------------- the constant and the helpers

def test_gate_hosts_is_claude_only():
    assert cohorts.GATE_HOSTS == ('claude',)
    assert cohorts.is_gate_record(make_record(1)) and not cohorts.is_gate_record(codex(make_record(1)))
    assert not cohorts.is_gate_record({'host': 'unknown'}) and not cohorts.is_gate_record({})


def test_backfill_records_are_gate_records():
    backfill = make_record(1, basis='backfill')
    assert backfill['host'] == 'claude' and cohorts.is_gate_record(backfill)
    mixed = [backfill, codex(make_record(2)), make_record(3)]
    assert cohorts.gate_records(mixed) == [mixed[0], mixed[2]]


def test_current_key_ignores_newer_codex_records():
    entry = reg.load_registry()['decisions'][SKILL]
    claude = make_record(1, ts='2026-10-10T10:00:05.000Z')
    newer_codex = codex(make_record(2, ts='2026-10-11T10:00:05.000Z', laya_revision='feedbeef0001'))
    assert cohorts.current_key(entry, [claude, newer_codex]) == cohorts.key_of(claude)
    assert cohorts.current_key(entry, [newer_codex]) is None


# ---------------------------------------------------------------- reserve

def test_a_codex_record_never_enters_a_cohort_pool(root, registry):
    claude = disagreements(30)
    machine = codex_records(60, 1000)                       # newer and more numerous, all disagreements
    write_records(root, claude + machine)
    result = cohorts.reserve(root, registry, T_RESERVE, 1)
    assert result['status'] == 'reserved' and result['eligible'] == 30 and result['selectable'] == 30
    event = cohorts.cohort_ledger(root)[result['cohortId']]['reserve']
    codex_keys = {r['occurrenceKey'] for r in machine}
    claude_keys = {r['occurrenceKey'] for r in claude}
    assert set(event['occurrenceKeys']) <= claude_keys and not set(event['occurrenceKeys']) & codex_keys


def test_codex_disagreements_cannot_fill_a_short_pool(root, registry):
    write_records(root, disagreements(10) + codex_records(100, 1000))      # target 20: only 10 gate cases exist
    result = cohorts.reserve(root, registry, T_RESERVE, 1, dry_run=True)
    assert result['status'] == 'held' and result['reason'] == 'insufficient_disagreements'
    assert result['eligible'] == 10 and result['available'] == 10


def test_codex_only_evidence_reserves_nothing(root, registry):
    write_records(root, codex_records(60, 0))
    assert cohorts.reserve(root, registry, T_RESERVE, 1) == {'status': 'held', 'reason': 'no_records'}
    assert cohorts.cohort_ledger(root) == {}


def test_a_newer_codex_record_under_another_laya_revision_does_not_move_the_key(root, registry):
    claude = disagreements(30)
    drift = codex_records(3, 1000, laya_revision='feedbeef0001', ts='2026-10-11T10:00:05.000Z')
    write_records(root, claude + drift)
    result = cohorts.reserve(root, registry, T_RESERVE, 1)
    assert result['status'] == 'reserved' and result['key']['layaRevision'] == LAYA_REV


def test_codex_unavailability_cannot_hold_the_gate(root, registry):
    claude = disagreements(30)
    # inside the cohort's time window, so a host-blind share would be 80/110 and hold the gate
    outage = [codex(make_record(1000 + k, status='unavailable', ts=f'2026-10-10T00:{k % 30:02d}:35.000Z'))
              for k in range(80)]
    write_records(root, claude + outage)
    result = cohorts.reserve(root, registry, T_RESERVE, 1)
    assert result['status'] == 'reserved'
    event = cohorts.cohort_ledger(root)[result['cohortId']]['reserve']
    by_key = {r['occurrenceKey']: r for r in claude}
    label_cohort(root, event, by_key, not_hit=len(event['occurrenceKeys']) - 1)
    verdict = cohorts.evaluate(root, registry, event['cohortId'], '2026-10-11T06:00:00Z')
    assert verdict['verdict'] == 'pass' and verdict['holdReasons'] == []


def test_unavailable_stats_and_availability_count_gate_hosts_only():
    claude = [make_record(k, status='ok') for k in range(8)] + [make_record(100 + k, status='unavailable') for k in range(2)]
    machine = codex_records(40, 1000, status='unavailable') + codex_records(10, 2000, status='timeout')
    key = cohorts.key_of(claude[0])
    tmin, tmax = cohorts.utc('2026-10-01T00:00:00Z'), cohorts.utc('2026-10-31T00:00:00Z')
    stats = cohorts.unavailable_stats(claude + machine, key, tmin, tmax)
    assert (stats['total'], stats['unavailable']) == (10, 2) and stats['share'] == pytest.approx(0.2)
    assert cohorts.unavailable_stats(machine, key, tmin, tmax) == {'total': 0, 'unavailable': 0, 'share': 0.0}
    availability, uncovered = cohorts.cohort_availability(claude + machine, claude, key, None)
    assert availability['total'] == 10 and availability['unavailable'] == 2 and not uncovered


def test_backfill_evidence_still_feeds_the_gate(root, registry):
    backfill = [make_record(10 + k, basis='backfill') for k in range(30)]
    machine = codex_records(40, 1000)
    write_records(root, backfill + machine)
    result = cohorts.reserve(root, registry, T_RESERVE, 1, dry_run=True)
    # backfill rows are shuffled in as before; a Codex row never is. The run log is absent, so every backfill row
    # is excluded as uncovered - which is the existing, host-independent rule - not because of Codex.
    assert result['status'] == 'held' and result['reason'] == 'insufficient_disagreements'
    assert result['eligible'] == 0 and result['backfillExcluded'] == 30


# ---------------------------------------------------------------- demotion

def test_codex_labels_never_enter_the_quality_window(root, registry):
    go_cosign(root, registry)
    machine = [codex(r) for r in cosign_disagreements(0, 14)]
    write_records(root, machine)
    label_all(root, machine, wrong=0)                        # would demote on quality if they counted (n=14, x=0)
    check = cohorts.demotion_check(root, registry, cosign_state(root, registry), NOW)
    assert not check['demote'] and check['quality']['n'] == 0 and check['quality']['x'] == 0


def test_codex_labels_cannot_mask_a_claude_quality_demotion(root, registry):
    go_cosign(root, registry)
    claude = cosign_disagreements(0, 12)
    machine = [codex(r) for r in cosign_disagreements(100, 30)]
    write_records(root, claude + machine)
    label_all(root, claude, wrong=0)                         # incumbent right in 12/12: demote
    label_all(root, machine, wrong=30)                       # incumbent wrong in all Codex cases: would block
    check = cohorts.demotion_check(root, registry, cosign_state(root, registry), NOW)
    assert check['demote'] and check['reason'] == 'demoted_quality' and check['quality']['n'] == 12


def test_codex_outages_never_enter_the_operational_window(root, registry):
    go_cosign(root, registry)
    healthy = [make_record(k, mode='cosign', choice=INC, ts=f'2026-10-11T{8 + k % 12:02d}:{k % 60:02d}:05.000Z')
               for k in range(30)]
    outage = [codex(make_record(100 + k, mode='cosign', status='unavailable', choice=INC,
                                ts=f'2026-10-11T{8 + k % 12:02d}:{k % 60:02d}:35.000Z')) for k in range(40)]
    write_records(root, healthy + outage)
    check = cohorts.demotion_check(root, registry, cosign_state(root, registry), NOW)
    operational = check['operational']
    assert not check['demote'] and (operational['total'], operational['failures']) == (30, 0)
    assert operational['timeouts'] == 0 and not operational['trigger']


def test_a_claude_outage_still_demotes_with_codex_noise_around_it(root, registry):
    go_cosign(root, registry)
    ok = [make_record(k, mode='cosign', choice=INC, ts=f'2026-10-11T{8 + k % 12:02d}:{k % 60:02d}:05.000Z') for k in range(22)]
    bad = [make_record(100 + k, mode='cosign', status='unavailable', choice=INC,
                       ts=f'2026-10-11T{8 + k % 12:02d}:{k % 60:02d}:35.000Z') for k in range(5)]
    machine = [codex(make_record(200 + k, mode='cosign', choice=INC, ts=f'2026-10-11T{8 + k % 12:02d}:{k % 60:02d}:50.000Z'))
               for k in range(200)]
    write_records(root, ok + bad + machine)
    check = cohorts.demotion_check(root, registry, cosign_state(root, registry), NOW)
    assert check['demote'] and check['reason'] == 'demoted_operational'
    assert (check['operational']['total'], check['operational']['failures']) == (27, 5)


def test_codex_latency_never_enters_the_latency_window(root, registry):
    go_cosign(root, registry, since='2026-09-01T00:00:00Z')            # long past the report-only period
    fast = [make_record(k, mode='cosign', choice=INC, latency=60.0,
                        ts=f'2026-10-11T{8 + k % 12:02d}:{k % 60:02d}:05.000Z') for k in range(25)]
    slow_codex = [codex(make_record(100 + k, mode='cosign', choice=INC, latency=950.0,
                                    ts=f'2026-10-11T{8 + k % 12:02d}:{k % 60:02d}:35.000Z')) for k in range(40)]
    write_records(root, fast + slow_codex)
    check = cohorts.demotion_check(root, registry, cosign_state(root, registry), NOW)
    latency = check['latency']
    assert latency['n'] == 25 and latency['p90'] == 60.0 and not latency['breach'] and not check['demote']


def test_a_slow_claude_window_still_demotes_on_latency(root, registry):
    go_cosign(root, registry, since='2026-09-01T00:00:00Z')
    slow = [make_record(k, mode='cosign', choice=INC, latency=900.0,
                        ts=f'2026-10-11T{8 + k % 12:02d}:{k % 60:02d}:05.000Z') for k in range(25)]
    fast_codex = [codex(make_record(100 + k, mode='cosign', choice=INC, latency=30.0,
                                    ts=f'2026-10-11T{8 + k % 12:02d}:{k % 60:02d}:35.000Z')) for k in range(200)]
    write_records(root, slow + fast_codex)
    check = cohorts.demotion_check(root, registry, cosign_state(root, registry), NOW)
    assert check['demote'] and check['reason'] == 'demoted_latency' and check['latency']['n'] == 25
