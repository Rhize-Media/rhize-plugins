"""Registry mutation path: lock, revision, audit intent/commit, recovery, pins, reachability, binding (plan §4.1, A6)."""
from __future__ import annotations

import copy
import json
import multiprocessing
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from typed_decision_testkit import (  # noqa: E402
    LAYA_REV, SCRIPTS, disagreements, fixture, passed_cohort, small_registry)
from typed_decisions import cohorts, contract, decision_registry as reg, instrument, locked_io, records  # noqa: E402

SKILL = 'skill-fit'
NOW = '2026-10-11T20:00:00Z'
CLI = SCRIPTS / 'typed_decisions' / 'decision_registry.py'


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
    return tmp_path / 'typed-decisions'


def binding(cohort_id=None, layaRevision=LAYA_REV):
    entry = reg.load_registry()['decisions'][SKILL]
    policy_hash, instrument_hash = cohorts.deployable_hashes(entry)
    return {'policySha256': policy_hash, 'instrumentSha256': instrument_hash, 'layaRevision': layaRevision,
            'cohortId': cohort_id}


def assert_files_valid(root, private_root=True):
    """Every state and audit line validates against the contract; modes are private.

    private_root=False when records.append (coordinator code) created the root: its mkdir(parents=True,
    mode=0o700) only applies the mode to the leaf directory.
    """
    registry = reg.load_registry()
    state, status = reg.read_state(root, registry)
    assert status == 'ok'
    contract.validate_state(state, registry)
    lines, invalid = reg.read_audit(root)
    assert invalid == 0
    for line in lines:
        contract.validate_audit(line)
    if private_root:
        assert stat.S_IMODE(os.stat(root).st_mode) == 0o700
    for name in (reg.STATE_FILE, reg.AUDIT_FILE, reg.LOCK_FILE):
        assert stat.S_IMODE(os.stat(root / name).st_mode) == 0o600
    return state, lines


class Crash(BaseException):
    """Simulated process death: not caught by `except Exception` in the code under test."""


# ---------------------------------------------------------------- read rule

def test_default_registry_is_valid_and_missing_state_uses_default(root):
    registry = reg.load_registry()
    state, status = reg.read_state(root, registry)
    assert (state, status) == (None, 'missing')
    assert reg.effective_mode(SKILL, registry, state, status) == 'shadow'
    assert reg.effective_mode('workflow-fit', registry, state, status) == 'shadow'


def test_corrupt_state_is_effective_shadow_even_when_it_said_cosign(root):
    reg.mutate(root, SKILL, 'cosign', actor='cli', reason='manual_override', expected_revision=0, binding=binding())
    registry = reg.load_registry()
    state, status = reg.read_state(root, registry)
    assert status == 'ok' and reg.effective_mode(SKILL, registry, state, status) == 'cosign'
    for damage in (b'{not json', b'[]', json.dumps({**state, 'revision': 0}).encode(),
                   json.dumps({**state, 'decisions': {'bogus': {}}}).encode(), b''):
        (root / reg.STATE_FILE).write_bytes(damage)
        state2, status2 = reg.read_state(root, registry)
        assert (state2, status2) == (None, 'corrupt')
        assert reg.effective_mode(SKILL, registry, state2, status2) == 'shadow'


def test_symlinked_state_file_is_corrupt(root, tmp_path):
    root.mkdir()
    real = tmp_path / 'elsewhere.json'
    real.write_text(json.dumps(fixture('registry.json')['validStates']['cosign']))
    os.symlink(real, root / reg.STATE_FILE)
    assert reg.read_state(root, reg.load_registry()) == (None, 'corrupt')


def test_mutate_refuses_to_write_over_corrupt_state(root):
    root.mkdir()
    (root / reg.STATE_FILE).write_text('garbage')
    with pytest.raises(reg.RegistryError) as err:
        reg.mutate(root, SKILL, 'off', actor='cli', reason='manual_off', expected_revision=0)
    assert err.value.code == 'state_corrupt'
    assert (root / reg.STATE_FILE).read_text() == 'garbage'


# ---------------------------------------------------------------- happy path and validation

def test_mutate_writes_validated_state_and_paired_audit_lines(root):
    state = reg.mutate(root, SKILL, 'off', actor='cli', reason='manual_off', expected_revision=0, now=NOW)
    assert state['revision'] == 1 and state['decisions'][SKILL]['mode'] == 'off'
    again = reg.mutate(root, SKILL, 'shadow', actor='cli', reason='back_to_shadow', expected_revision=1, now=NOW)
    assert again['revision'] == 2
    on_disk, lines = assert_files_valid(root)
    assert on_disk == again
    assert [(l['phase'], l['revision'], l['actor'], l['fromMode'], l['toMode']) for l in lines] == [
        ('intent', 1, 'cli', 'shadow', 'off'), ('commit', 1, 'cli', 'shadow', 'off'),
        ('intent', 2, 'cli', 'off', 'shadow'), ('commit', 2, 'cli', 'off', 'shadow')]
    assert lines[0]['state'] == state and 'state' not in lines[1]


def test_stale_revision_is_rejected_and_changes_nothing(root):
    reg.mutate(root, SKILL, 'off', actor='cli', reason='manual_off', expected_revision=0)
    before = (root / reg.STATE_FILE).read_bytes()
    audit_before = (root / reg.AUDIT_FILE).read_bytes()
    with pytest.raises(reg.RegistryError) as err:
        reg.mutate(root, SKILL, 'shadow', actor='cli', reason='stale_try', expected_revision=0)
    assert err.value.code == 'stale_revision'
    assert (root / reg.STATE_FILE).read_bytes() == before
    assert (root / reg.AUDIT_FILE).read_bytes() == audit_before


def test_no_op_mutation_is_refused(root):
    with pytest.raises(reg.RegistryError) as err:
        reg.mutate(root, SKILL, 'shadow', actor='cli', reason='same_again', expected_revision=0)
    assert err.value.code == 'no_change'
    reg.mutate(root, SKILL, 'off', actor='cli', reason='manual_off', expected_revision=0)
    with pytest.raises(reg.RegistryError) as err:
        reg.mutate(root, SKILL, 'off', actor='cli', reason='off_again', expected_revision=1)
    assert err.value.code == 'no_change'


@pytest.mark.parametrize('kwargs,code', [
    ({'actor': 'recovery'}, 'invalid_actor'), ({'actor': 'hook'}, 'invalid_actor'),
    ({'reason': 'Has Spaces'}, 'invalid_reason'), ({'reason': ''}, 'invalid_reason'),
    ({'decision': 'agent-brief-skill'}, 'unknown_decision'), ({'to_mode': 'turbo'}, 'unreachable_mode'),
])
def test_invalid_arguments_are_refused_before_any_write(root, kwargs, code):
    args = {'decision': SKILL, 'to_mode': 'off', 'actor': 'cli', 'reason': 'manual_off'}
    args.update(kwargs)
    with pytest.raises(reg.RegistryError) as err:
        reg.mutate(root, args['decision'], args['to_mode'], actor=args['actor'], reason=args['reason'],
                   expected_revision=0)
    assert err.value.code == code
    assert not (root / reg.STATE_FILE).exists() and not (root / reg.AUDIT_FILE).exists()


# ---------------------------------------------------------------- reachability

def test_unreachable_modes_are_refused(root):
    for mode in ('off', 'cosign'):
        with pytest.raises(reg.RegistryError) as err:
            reg.mutate(root, 'workflow-fit', mode, actor='cli', reason='nope', expected_revision=0,
                       binding=binding() if mode == 'cosign' else None)
        assert err.value.code == 'unreachable_mode'
    with pytest.raises(reg.RegistryError) as err:
        reg.mutate(root, 'workflow-fit', 'shadow', actor='cli', reason='same', expected_revision=0)
    assert err.value.code == 'no_change'


def test_critical_tier_never_leaves_shadow_or_off(root):
    registry = copy.deepcopy(reg.load_registry())
    entry = registry['decisions']['workflow-fit']
    entry['tier'], entry['reachableModes'] = 'critical', ['off', 'shadow']
    contract.validate_registry(registry)
    state = reg.mutate(root, 'workflow-fit', 'off', actor='cli', reason='manual_off', expected_revision=0,
                       registry=registry)
    assert state['decisions']['workflow-fit']['mode'] == 'off'
    with pytest.raises(reg.RegistryError) as err:
        reg.mutate(root, 'workflow-fit', 'cosign', actor='cli', reason='nope', expected_revision=1,
                   binding=binding(), registry=registry)
    assert err.value.code == 'unreachable_mode'
    # even a registry that wrongly lists cosign for a critical decision cannot be used to reach it
    bad = copy.deepcopy(registry)
    bad['decisions']['workflow-fit']['reachableModes'] = ['off', 'shadow', 'cosign']
    with pytest.raises(reg.RegistryError) as err:
        reg.mutate(root, 'workflow-fit', 'cosign', actor='cli', reason='nope', expected_revision=1,
                   binding=binding(), registry=bad)
    assert err.value.code == 'unreachable_mode'


# ---------------------------------------------------------------- cosign binding

def test_cosign_without_binding_is_refused(root):
    for actor in ('cli', 'cycle'):
        with pytest.raises(reg.RegistryError) as err:
            reg.mutate(root, SKILL, 'cosign', actor=actor, reason='gate_passed', expected_revision=0)
        assert err.value.code == 'binding_required'
    with pytest.raises(reg.RegistryError) as err:
        reg.mutate(root, SKILL, 'cosign', actor='cli', reason='manual_override', expected_revision=0,
                   binding={'policySha256': binding()['policySha256']})
    assert err.value.code == 'binding_required'
    assert not (root / reg.STATE_FILE).exists()


def test_binding_must_name_the_deployable_policy_and_current_instrument(root):
    wrong_policy = {**binding(), 'policySha256': 'a' * 64}
    wrong_instrument = {**binding(), 'instrumentSha256': 'b' * 64}
    bad_revision = {**binding(), 'layaRevision': 'has space'}
    for bad, code in ((wrong_policy, 'invalid_binding'), (wrong_instrument, 'invalid_binding'),
                      (bad_revision, 'invalid_binding')):
        with pytest.raises(reg.RegistryError) as err:
            reg.mutate(root, SKILL, 'cosign', actor='cli', reason='manual_override', expected_revision=0, binding=bad)
        assert err.value.code == code
    with pytest.raises(reg.RegistryError) as err:
        reg.mutate(root, SKILL, 'shadow', actor='cli', reason='pin_it', expected_revision=0, pinned=True,
                   binding=binding())
    assert err.value.code == 'invalid_binding'


def test_cli_may_override_with_a_null_cohort_but_the_cycle_may_not(root):
    with pytest.raises(reg.RegistryError) as err:
        reg.mutate(root, SKILL, 'cosign', actor='cycle', reason='gate_passed', expected_revision=0, binding=binding())
    assert err.value.code == 'binding_required'
    state = reg.mutate(root, SKILL, 'cosign', actor='cli', reason='manual_override', expected_revision=0,
                       binding=binding(), now=NOW)
    entry = state['decisions'][SKILL]
    assert entry['mode'] == 'cosign' and entry['cohortId'] is None and entry['layaRevision'] == LAYA_REV
    assert entry['policySha256'] == contract.policy_sha256() and entry['instrumentSha256'] == instrument.instrument_sha256()
    assert_files_valid(root)


def test_cycle_promotion_needs_a_passed_cohort_of_the_same_key(root):
    registry = small_registry()
    recs = disagreements(25)
    event, verdict = passed_cohort(root, registry, recs)
    good = binding(event['cohortId'])
    # unknown cohort, wrong Laya revision, mismatching hashes: all refused
    for bad in ({**good, 'cohortId': 'c' * 32}, {**good, 'layaRevision': 'other-rev'}):
        with pytest.raises(reg.RegistryError) as err:
            reg.mutate(root, SKILL, 'cosign', actor='cycle', reason='gate_passed', expected_revision=0,
                       binding=bad, registry=registry)
        assert err.value.code == 'invalid_binding'
    state = reg.mutate(root, SKILL, 'cosign', actor='cycle', reason='gate_passed', expected_revision=0,
                       binding=good, registry=registry, now=NOW)
    assert state['decisions'][SKILL]['cohortId'] == event['cohortId']
    _, lines = assert_files_valid(root, private_root=False)
    assert lines[-1]['actor'] == 'cycle' and lines[-1]['reason'] == 'gate_passed'


def test_cycle_cannot_promote_on_a_failed_or_open_cohort(root):
    registry = small_registry()
    recs = disagreements(25)
    records_written = [records.append(root, SKILL, 'records', r) for r in recs]
    assert records_written
    result = cohorts.reserve(root, registry, '2026-10-11T00:00:00Z', 1)
    with pytest.raises(reg.RegistryError) as err:       # reserved but never consumed
        reg.mutate(root, SKILL, 'cosign', actor='cycle', reason='gate_passed', expected_revision=0,
                   binding=binding(result['cohortId']), registry=registry)
    assert err.value.code == 'invalid_binding'


# ---------------------------------------------------------------- pins

def test_pin_blocks_the_cycle_but_not_the_cli(root):
    reg.mutate(root, SKILL, 'shadow', actor='cli', reason='manual_pin', expected_revision=0, pinned=True, now=NOW)
    state, _ = reg.read_state(root, reg.load_registry())
    assert state['decisions'][SKILL]['pinned'] is True
    with pytest.raises(reg.RegistryError) as err:
        reg.mutate(root, SKILL, 'off', actor='cycle', reason='demoted_quality', expected_revision=1)
    assert err.value.code == 'pinned'
    after = reg.mutate(root, SKILL, 'off', actor='cli', reason='manual_off', expected_revision=1)
    assert after['decisions'][SKILL]['mode'] == 'off' and after['decisions'][SKILL]['pinned'] is True  # pin kept
    unpinned = reg.mutate(root, SKILL, 'off', actor='cli', reason='resume_auto', expected_revision=2, pinned=False)
    assert unpinned['decisions'][SKILL]['pinned'] is False
    again = reg.mutate(root, SKILL, 'shadow', actor='cycle', reason='demoted_quality', expected_revision=3)
    assert again['decisions'][SKILL]['mode'] == 'shadow'
    assert_files_valid(root)


def test_the_cycle_can_never_change_a_pin(root):
    with pytest.raises(reg.RegistryError) as err:
        reg.mutate(root, SKILL, 'off', actor='cycle', reason='demoted_quality', expected_revision=0, pinned=False)
    assert err.value.code == 'pin_forbidden'


def test_pinning_a_deployed_cosign_keeps_its_basis(root):
    reg.mutate(root, SKILL, 'cosign', actor='cli', reason='manual_override', expected_revision=0,
               binding=binding(), now=NOW)
    pinned = reg.mutate(root, SKILL, 'cosign', actor='cli', reason='manual_pin', expected_revision=1, pinned=True,
                        now='2026-10-12T00:00:00Z')
    entry = pinned['decisions'][SKILL]
    assert entry['pinned'] and entry['mode'] == 'cosign' and entry['since'] == NOW
    assert entry['layaRevision'] == LAYA_REV and entry['policySha256'] == contract.policy_sha256()


# ---------------------------------------------------------------- concurrency

def _race(root_str, kind, barrier, queue):
    """Both racers observed revision 1 (cosign): the operator pins while the cycle demotes."""
    try:
        barrier.wait(10)
        if kind == 'cli_pin':
            reg.mutate(Path(root_str), SKILL, 'cosign', actor='cli', reason='manual_pin', expected_revision=1,
                       pinned=True)
        else:
            reg.mutate(Path(root_str), SKILL, 'shadow', actor='cycle', reason='demoted_quality', expected_revision=1)
        queue.put((kind, 'ok'))
    except reg.RegistryError as err:
        queue.put((kind, err.code))


def test_concurrent_cli_and_cycle_writes_with_the_same_expected_revision_have_exactly_one_winner(root):
    ctx = multiprocessing.get_context('fork')
    for round_number in range(4):
        target = root / f'round-{round_number}'
        reg.mutate(target, SKILL, 'cosign', actor='cli', reason='manual_override', expected_revision=0,
                   binding=binding())
        barrier, queue = ctx.Barrier(2), ctx.Queue()
        procs = [ctx.Process(target=_race, args=(str(target), kind, barrier, queue)) for kind in ('cli_pin', 'cycle_demote')]
        for proc in procs:
            proc.start()
        results = dict(queue.get(timeout=30) for _ in procs)
        for proc in procs:
            proc.join(30)
            assert proc.exitcode == 0
        assert sorted(results.values()) == ['ok', 'stale_revision'], results
        state, lines = assert_files_valid(target)
        assert state['revision'] == 2
        assert [(l['phase'], l['revision']) for l in lines] == [('intent', 1), ('commit', 1), ('intent', 2), ('commit', 2)]
        winner = next(kind for kind, code in results.items() if code == 'ok')
        entry = state['decisions'][SKILL]
        assert (entry['pinned'], entry['mode']) == ((True, 'cosign') if winner == 'cli_pin' else (False, 'shadow'))


def test_concurrent_writers_that_expect_the_same_revision_cannot_both_win_even_for_the_same_change(root):
    ctx = multiprocessing.get_context('fork')
    target = root / 'same-change'
    barrier, queue = ctx.Barrier(4), ctx.Queue()

    def racer(index):
        try:
            barrier.wait(10)
            reg.mutate(target, SKILL, 'off', actor='cli', reason=f'racer_{"abcd"[index]}', expected_revision=0)
            queue.put('ok')
        except reg.RegistryError as err:
            queue.put(err.code)
    procs = [ctx.Process(target=racer, args=(i,)) for i in range(4)]
    for proc in procs:
        proc.start()
    results = sorted(queue.get(timeout=30) for _ in procs)
    for proc in procs:
        proc.join(30)
    assert results == ['ok', 'stale_revision', 'stale_revision', 'stale_revision']
    assert assert_files_valid(target)[0]['revision'] == 1


def test_cli_and_library_writers_serialize_on_the_same_lock(root):
    holder = locked_io.try_lock(root / reg.LOCK_FILE)
    try:
        assert holder is not None
        monkey_timeout = reg.LOCK_TIMEOUT_SECONDS
        reg.LOCK_TIMEOUT_SECONDS = 0.2
        try:
            with pytest.raises(reg.RegistryError) as err:
                reg.mutate(root, SKILL, 'off', actor='cli', reason='manual_off', expected_revision=0)
            assert err.value.code == 'lock_timeout'
        finally:
            reg.LOCK_TIMEOUT_SECONDS = monkey_timeout
    finally:
        locked_io.release_lock(holder)
    assert reg.mutate(root, SKILL, 'off', actor='cli', reason='manual_off', expected_revision=0)['revision'] == 1


# ---------------------------------------------------------------- interrupted update and recovery

def test_crash_before_the_state_replace_is_recovered_from_the_audit_intent(root, monkeypatch):
    reg.mutate(root, SKILL, 'off', actor='cli', reason='manual_off', expected_revision=0, now=NOW)

    def die(*_args):
        raise Crash()
    monkeypatch.setattr(locked_io, 'replace_file', die)
    with pytest.raises(Crash):
        reg.mutate(root, SKILL, 'shadow', actor='cli', reason='back_to_shadow', expected_revision=1, now=NOW)
    monkeypatch.undo()

    state, status = reg.read_state(root, reg.load_registry())
    assert status == 'ok' and state['revision'] == 1 and state['decisions'][SKILL]['mode'] == 'off'
    lines, _ = reg.read_audit(root)
    assert lines[-1]['phase'] == 'intent' and lines[-1]['revision'] == 2

    result = reg.recover(root, now='2026-10-11T21:00:00Z')
    assert result == {'action': 'applied', 'revision': 2}
    state, lines = assert_files_valid(root)
    assert state['revision'] == 2 and state['decisions'][SKILL]['mode'] == 'shadow'
    assert (lines[-1]['phase'], lines[-1]['actor'], lines[-1]['revision']) == ('commit', 'recovery', 2)
    assert reg.recover(root) == {'action': 'none'}        # idempotent
    assert len(reg.read_audit(root)[0]) == 4


def test_crash_on_the_very_first_update_recovers_from_a_missing_state_file(root, monkeypatch):
    monkeypatch.setattr(locked_io, 'replace_file', lambda *_a: (_ for _ in ()).throw(Crash()))
    with pytest.raises(Crash):
        reg.mutate(root, SKILL, 'off', actor='cli', reason='manual_off', expected_revision=0)
    monkeypatch.undo()
    assert reg.read_state(root, reg.load_registry()) == (None, 'missing')
    assert reg.recover(root)['action'] == 'applied'
    state, _ = assert_files_valid(root)
    assert state['revision'] == 1 and state['decisions'][SKILL]['mode'] == 'off'


def test_crash_after_the_replace_only_needs_the_missing_commit(root, monkeypatch):
    original = reg._append_audit

    def flaky(root_arg, line):
        if line['phase'] == 'commit':
            raise Crash()
        return original(root_arg, line)
    monkeypatch.setattr(reg, '_append_audit', flaky)
    with pytest.raises(Crash):
        reg.mutate(root, SKILL, 'off', actor='cli', reason='manual_off', expected_revision=0, now=NOW)
    monkeypatch.undo()
    state, _ = reg.read_state(root, reg.load_registry())
    assert state['revision'] == 1                     # the replace happened
    assert reg.read_audit(root)[0][-1]['phase'] == 'intent'
    assert reg.recover(root) == {'action': 'committed', 'revision': 1}
    _, lines = assert_files_valid(root)
    assert [l['phase'] for l in lines] == ['intent', 'commit'] and lines[-1]['actor'] == 'recovery'
    assert reg.recover(root) == {'action': 'none'}


def test_the_next_mutation_recovers_a_dangling_intent_first(root, monkeypatch):
    monkeypatch.setattr(locked_io, 'replace_file', lambda *_a: (_ for _ in ()).throw(Crash()))
    with pytest.raises(Crash):
        reg.mutate(root, SKILL, 'off', actor='cli', reason='manual_off', expected_revision=0)
    monkeypatch.undo()
    with pytest.raises(reg.RegistryError) as err:     # revision 1 now exists, so a caller still on 0 is stale
        reg.mutate(root, SKILL, 'shadow', actor='cli', reason='stale_try', expected_revision=0)
    assert err.value.code == 'stale_revision'
    state = reg.mutate(root, SKILL, 'shadow', actor='cli', reason='back_to_shadow', expected_revision=1)
    assert state['revision'] == 2
    _, lines = assert_files_valid(root)
    assert [(l['phase'], l['revision']) for l in lines] == [
        ('intent', 1), ('commit', 1), ('intent', 2), ('commit', 2)]


def test_a_torn_audit_line_does_not_poison_later_lines(root):
    reg.mutate(root, SKILL, 'off', actor='cli', reason='manual_off', expected_revision=0)
    with open(root / reg.AUDIT_FILE, 'ab') as stream:
        stream.write(b'{"schema":"rhize-typed-decision-registry-aud')      # crash mid-line, no newline
    reg.mutate(root, SKILL, 'shadow', actor='cli', reason='back_to_shadow', expected_revision=1)
    lines, invalid = reg.read_audit(root)
    assert invalid == 1 and [(l['phase'], l['revision']) for l in lines] == [
        ('intent', 1), ('commit', 1), ('intent', 2), ('commit', 2)]


def test_recover_refuses_to_guess_when_state_and_audit_disagree(root, monkeypatch):
    reg.mutate(root, SKILL, 'off', actor='cli', reason='manual_off', expected_revision=0)
    monkeypatch.setattr(locked_io, 'replace_file', lambda *_a: (_ for _ in ()).throw(Crash()))
    with pytest.raises(Crash):
        reg.mutate(root, SKILL, 'shadow', actor='cli', reason='back_to_shadow', expected_revision=1)
    monkeypatch.undo()
    (root / reg.STATE_FILE).unlink()                      # state lost: revision 0 vs an intent for revision 2
    assert reg.recover(root)['action'] == 'blocked'
    assert reg.read_state(root, reg.load_registry()) == (None, 'missing')
    (root / reg.STATE_FILE).write_text('garbage')
    assert reg.recover(root) == {'action': 'blocked', 'reason': 'state_corrupt', 'revision': 2}


def test_recover_on_an_untouched_root_does_nothing(root, tmp_path):
    assert reg.recover(root) == {'action': 'none'}
    assert not root.exists()


# ---------------------------------------------------------------- CLI

def run_cli(root, *args):
    proc = subprocess.run([sys.executable, str(CLI), '--root', str(root), *args], capture_output=True, text=True,
                          timeout=60, env={**os.environ, 'HOME': str(root.parent / 'home')})
    return proc.returncode, json.loads(proc.stdout)


def test_cli_show_set_mode_pin_and_recover(root):
    root.mkdir(mode=0o700, parents=True)
    (root / 'laya-runtime.json').write_text(json.dumps({'revision': LAYA_REV}))   # the CLI runs in a subprocess
    code, out = run_cli(root, 'show')
    assert code == 0 and out['status'] == 'missing' and out['decisions'][SKILL]['effectiveMode'] == 'shadow'
    code, out = run_cli(root, 'set-mode', SKILL, 'off', '--reason', 'manual_off', '--pin')
    assert (code, out['mode'], out['pinned'], out['revision']) == (0, 'off', True, 1)
    code, out = run_cli(root, 'show')
    assert out['status'] == 'ok' and out['decisions'][SKILL]['effectiveMode'] == 'off' and out['decisions'][SKILL]['pinned']
    code, out = run_cli(root, 'set-mode', SKILL, 'shadow', '--reason', 'resume', '--unpin')
    assert (code, out['mode'], out['pinned']) == (0, 'shadow', False)
    code, out = run_cli(root, 'set-mode', SKILL, 'cosign', '--reason', 'manual_override')
    assert code == 2 and out['error'] == 'binding_required'
    code, out = run_cli(root, 'set-mode', SKILL, 'cosign', '--reason', 'manual_override', '--laya-revision', LAYA_REV)
    assert code == 2 and out['error'] == 'binding_required'            # omission never grants authority
    code, out = run_cli(root, 'set-mode', SKILL, 'cosign', '--reason', 'manual_override', '--laya-revision', LAYA_REV,
                        '--manual-override')
    assert (code, out['mode']) == (0, 'cosign')
    code, out = run_cli(root, 'set-mode', SKILL, 'cosign', '--reason', 'manual_pin', '--pin')
    assert (code, out['pinned']) == (0, True)
    code, out = run_cli(root, 'set-mode', 'workflow-fit', 'cosign', '--reason', 'nope', '--laya-revision', LAYA_REV)
    assert code == 2 and out['error'] == 'unreachable_mode'
    code, out = run_cli(root, 'set-mode', SKILL, 'off', '--reason', 'BAD REASON')
    assert code == 2 and out['error'] == 'invalid_reason'
    code, out = run_cli(root, 'recover')
    assert (code, out['recovery']['action']) == (0, 'none')
    assert_files_valid(root)


def test_cli_pin_and_unpin_are_mutually_exclusive(root):
    proc = subprocess.run([sys.executable, str(CLI), '--root', str(root), 'set-mode', SKILL, 'off', '--reason', 'x',
                           '--pin', '--unpin'], capture_output=True, text=True, timeout=60)
    assert proc.returncode == 2 and 'not allowed' in proc.stderr


def test_a_binding_must_name_the_running_checkpoint(root):
    root.mkdir(mode=0o700, parents=True)
    (root / 'laya-runtime.json').write_text(json.dumps({'revision': 'other-rev'}))
    with pytest.raises(reg.RegistryError) as err:
        reg.mutate(root, SKILL, 'cosign', actor='cli', reason='manual_override', expected_revision=0, binding=binding())
    assert err.value.code == 'invalid_binding'


def test_a_blocked_recovery_stops_every_mutation(root):
    reg.mutate(root, SKILL, 'off', actor='cli', reason='manual_off', expected_revision=0)
    state = reg.read_state(root)[0]
    # a dangling intent two revisions ahead of the state (revision gap): recovery is blocked
    bogus = json.loads(json.dumps(state))
    bogus['revision'] = 3
    line = {'schema': contract.AUDIT_SCHEMA, 'phase': 'intent', 'revision': 3, 'previousRevision': 2,
            'at': '2026-10-11T00:00:00Z', 'actor': 'cli', 'decision': SKILL, 'fromMode': 'shadow', 'toMode': 'off',
            'pinned': False, 'reason': 'diverged', 'state': bogus}
    locked_io.append_line(reg.audit_path(root), line)
    assert reg.recover(root)['action'] == 'blocked'
    with pytest.raises(reg.RegistryError) as err:
        reg.mutate(root, SKILL, 'shadow', actor='cli', reason='resume', expected_revision=1)
    assert err.value.code == 'recovery_blocked'
