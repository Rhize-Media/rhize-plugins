"""Registry support for mode `advise` (plan 2026-10-16 §2-§4): catalog, validators, bindings, ledgers, staleness."""
from __future__ import annotations

import copy
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / 'rhize-context-manager' / 'scripts'
SCHEMAS = REPO / 'rhize-context-manager' / 'schemas'
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from typed_decision_testkit import LAYA_REV, disagreements, passed_cohort, small_registry  # noqa: E402
from typed_decisions import advise_ledger, cohorts, contract, decision_registry as reg, instrument  # noqa: E402
import typed_advice  # noqa: E402

try:
    import jsonschema
except ImportError:
    jsonschema = None

SKILL, WORKFLOW, CRITICAL = 'skill-fit', 'workflow-fit', 'devflow-next-action'
REV = 'rev-advise-1'
ADVISE_V1 = contract.policy_sha256('advise-v1')
POLICY = 'a' * 64
NOW = '2026-10-16T12:00:00Z'
LEGACY_ONLY = (SKILL, WORKFLOW)
NEW_DECISIONS = ('procedure-pick', 'devflow-next-action', 'browser-qa-selection', 'model-routing', 'gsd-directive',
                 'check-relaxation')


@pytest.fixture
def catalog():
    return reg.load_registry()


@pytest.fixture
def root(tmp_path):
    path = tmp_path / 'typed-decisions'
    path.mkdir(mode=0o700)
    (path / 'laya-runtime.json').write_text(json.dumps({'revision': REV}))
    return path


def advise_decisions(registry):
    return {d: e for d, e in registry['decisions'].items() if e.get('advise') is not None}


def instrument_hash(registry, decision):
    return reg.advise_instrument_sha256(registry['decisions'][decision]['advise']['instrument'])


def binding(registry, decision, cohort_id=None, *, policy=POLICY, rev=REV):
    return {'policySha256': policy, 'instrumentSha256': instrument_hash(registry, decision), 'layaRevision': rev,
            'cohortId': cohort_id}


def groups(cohort, count):
    return sorted(advise_ledger.group_hash(f'{cohort}-{i}') for i in range(count))


def write_cohort(root, registry, decision, *, cohort='1' * 32, verdict='pass', consume=True, policy=POLICY, rev=REV):
    base = {'cohortId': cohort, 'decision': decision, 'policySha256': policy,
            'instrumentSha256': instrument_hash(registry, decision), 'layaRevision': rev, 'attempt': 1, 'alpha': 0.1}
    advise_ledger.append(root, decision, {'event': 'reserve', **base, 'caseIds': ['case-1', 'case-2'], 'ts': NOW,
                                          'groups': groups(cohort, 2)})
    if consume:
        advise_ledger.append(root, decision, {'event': 'consumed', **base, 'verdict': verdict,
                                              'receiptSha256': 'c' * 64, 'ts': NOW})
    return cohort


# ---------------------------------------------------------------- catalog

def test_every_catalog_decision_validates_and_ships_shadow(catalog):
    contract.validate_registry(catalog)
    assert set(catalog['decisions']) == set(contract.DECISIONS)
    for decision, entry in catalog['decisions'].items():
        assert entry['defaultMode'] == 'shadow', decision
        assert ('advise' in entry['reachableModes']) == (entry.get('advise') is not None), decision


def test_catalog_values_follow_the_plan(catalog):
    d = catalog['decisions']
    assert d[SKILL]['reachableModes'] == ['off', 'shadow', 'advise', 'cosign']
    assert d[SKILL]['advise']['instrument'] == 'laya-choice-v1' and d[SKILL]['deployablePolicy'] == 'cosign-v1'
    assert d[SKILL]['gates']['promote']['cohortSize'] == 60  # the cosign gate config is unchanged
    assert d[WORKFLOW]['tier'] == 'workflow' and d[WORKFLOW]['reachableModes'] == ['shadow', 'advise']
    assert d[WORKFLOW]['advise']['instrument'] == 'typed-advice-v1'
    for decision in ('procedure-pick', 'browser-qa-selection', 'model-routing'):
        assert d[decision]['tier'] == 'advisory' and d[decision]['reachableModes'] == ['off', 'shadow', 'advise']
    for decision in ('devflow-next-action', 'gsd-directive', 'check-relaxation'):
        assert d[decision]['tier'] == 'critical' and d[decision]['reachableModes'] == ['off', 'shadow', 'advise']
        assert d[decision]['advise']['minCriticalCases'] >= 10
    for decision, entry in advise_decisions(catalog).items():
        advise = entry['advise']
        assert advise['policy'] == 'advise-v1' and advise['gate'] == 'majority-baseline'
        assert advise['minCohort'] == 30 and advise['alphaBase'] == 0.10 and advise['minCoverage'] == 0.9
        assert advise['demote'] == {'freshLabels': 10, 'window': 30, 'consecutive': 2}
        assert advise['holdback'] == (0.15 if entry['tier'] == 'critical' else 0.10)
        if decision != SKILL:
            assert all(entry[k] is None for k in contract.COSIGN_ONLY_KEYS), decision


def test_typed_advice_tiers_and_holdbacks_match_the_catalog(catalog):
    adviseable = advise_decisions(catalog)
    assert typed_advice.TIERS == {d: e['tier'] for d, e in adviseable.items()}
    assert set(contract.ADVISE_DECISIONS) == set(adviseable)
    for decision, entry in adviseable.items():
        assert typed_advice.HOLDBACK[entry['tier']] == entry['advise']['holdback'], decision


def test_credential_procedure_is_manual_only_and_never_advises(catalog):
    entry = catalog['decisions']['credential-procedure']
    assert (entry['tier'], entry['defaultMode'], entry['reachableModes']) == ('workflow', 'shadow', ['off', 'shadow', 'cosign'])
    assert entry['deployablePolicy'] == entry['instrument'] == contract.POLICY_CREDENTIAL
    assert entry['holdback'] == 0 and entry['lambda'] is None and entry['gates'] is None and entry['advise'] is None
    assert catalog['decisions'][WORKFLOW]['deployablePolicy'] is None   # workflow-fit is the content/general advise decision
    for change in ({'reachableModes': ['off', 'shadow', 'cosign', 'advise']}, {'incumbent': 'other'},
                   {'defaultMode': 'cosign'}, {'holdback': 0.1}, {'tier': 'advisory'}, {'tier': 'critical'},
                   {'gates': {}}, {'lambda': 1}, {'instrument': 'laya-choice-v1'}):
        with pytest.raises(ValueError):
            contract.validate_registry(mutated(catalog, 'credential-procedure', lambda e, c=change: e.update(c)))
    # the policy is keyed on the decision: neither workflow-fit nor skill-fit may borrow it
    for decision in (WORKFLOW, SKILL):
        with pytest.raises(ValueError, match='credential'):
            contract.validate_registry(mutated(catalog, decision, lambda e: e.update(deployablePolicy=contract.POLICY_CREDENTIAL)))


def test_credential_cosign_is_cli_only_known_revision_and_cohort_free(root, catalog):
    ledger_cohort = write_cohort(root, catalog, SKILL)  # an advise pass for another decision is no authority here
    entry = catalog['decisions']['credential-procedure']
    policy, instrument_hash_ = cohorts.deployable_hashes(entry)
    good = {'policySha256': policy, 'instrumentSha256': instrument_hash_, 'layaRevision': REV, 'cohortId': None}
    for actor, change in (('cycle', {}), ('cli', {'cohortId': ledger_cohort}), ('cli', {'layaRevision': 'unknown'})):
        with pytest.raises(reg.RegistryError) as err:
            reg.mutate(root, 'credential-procedure', 'cosign', actor=actor, reason='fixture_only', expected_revision=0,
                       binding={**good, **change})
        assert err.value.code in ('invalid_binding', 'binding_required')
    with pytest.raises(reg.RegistryError) as err:
        reg.mutate(root, 'credential-procedure', 'advise', actor='cli', reason='fixture_only', expected_revision=0,
                   binding=binding(catalog, SKILL))
    assert err.value.code == 'unreachable_mode'
    state = reg.mutate(root, 'credential-procedure', 'cosign', actor='cli', reason='fixture_only', expected_revision=0,
                       binding=good)
    assert reg.effective_mode('credential-procedure', catalog, state, 'ok', REV) == 'cosign'
    assert reg.effective_mode('credential-procedure', catalog, state, 'ok', 'changed') == 'shadow'


def test_advise_instrument_hashes(catalog):
    assert reg.advise_instrument_sha256('typed-advice-v1') == typed_advice.INSTRUMENT_SHA256
    assert reg.advise_instrument_sha256('laya-choice-v1') == instrument.instrument_sha256()
    with pytest.raises(ValueError):
        reg.advise_instrument_sha256('other')


# ---------------------------------------------------------------- registry validator

def mutated(catalog, decision, fn):
    value = copy.deepcopy(catalog)
    fn(value['decisions'][decision])
    return value


def test_critical_never_reaches_cosign_and_needs_ten_critical_cases(catalog):
    with pytest.raises(ValueError, match='never reach cosign'):
        contract.validate_registry(mutated(catalog, CRITICAL, lambda e: e.update(
            reachableModes=['off', 'shadow', 'advise', 'cosign'])))
    for cases, ok in ((9, False), (10, True), (25, True)):
        registry = mutated(catalog, CRITICAL, lambda e, c=cases: e['advise'].update(minCriticalCases=c))
        if ok:
            contract.validate_registry(registry)
        else:
            with pytest.raises(ValueError, match='minCriticalCases'):
                contract.validate_registry(registry)
    # a non-critical tier may leave minCriticalCases at 0
    contract.validate_registry(mutated(catalog, WORKFLOW, lambda e: e['advise'].update(minCriticalCases=0)))


def test_advise_is_reachable_if_and_only_if_configured(catalog):
    for decision, fn in ((CRITICAL, lambda e: e.update(advise=None)),
                         (CRITICAL, lambda e: e.update(reachableModes=['off', 'shadow'])),
                         (SKILL, lambda e: e.update(reachableModes=['off', 'shadow', 'cosign']))):
        with pytest.raises(ValueError, match='advise is reachable'):
            contract.validate_registry(mutated(catalog, decision, fn))
    # `advise` may be absent altogether (a registry written before advise existed)
    legacy = mutated(catalog, WORKFLOW, lambda e: (e.pop('advise'), e.update(reachableModes=['shadow'])))
    contract.validate_registry(legacy)


def test_an_earned_mode_is_never_a_default(catalog):
    for mode in ('advise', 'cosign'):
        with pytest.raises(ValueError, match='defaultMode'):
            contract.validate_registry(mutated(catalog, SKILL, lambda e, m=mode: e.update(defaultMode=m)))


@pytest.mark.parametrize('change', [
    {'policy': 'cosign-v1'}, {'gate': 'cosign-disagreement'}, {'instrument': 'nope'}, {'holdback': 0.6},
    {'holdback': -0.1}, {'minCohort': 19}, {'minCriticalCases': -1}, {'alphaBase': 0}, {'alphaBase': 0.21},
    {'minCoverage': 1.1}, {'minCoverage': -0.1}, {'extra': 1}, {'demote': {'freshLabels': 4, 'window': 30, 'consecutive': 2}},
    {'demote': {'freshLabels': 10, 'window': 19, 'consecutive': 2}},
    {'demote': {'freshLabels': 10, 'window': 30, 'consecutive': 0}}, {'demote': {'freshLabels': 10}},
    {'minCohort': True}, {'alphaBase': float('nan')}])
def test_invalid_advise_configs_are_rejected(catalog, change):
    with pytest.raises(ValueError):
        contract.validate_registry(mutated(catalog, WORKFLOW, lambda e: e['advise'].update(change)))


# ---------------------------------------------------------------- state validator

def state_with(registry, decision, **entry_fields):
    entry = {'mode': 'advise', 'pinned': False, 'since': NOW, 'reason': 'gate_pass', 'policySha256': POLICY,
             'instrumentSha256': instrument_hash(registry, decision), 'layaRevision': REV, 'cohortId': '1' * 32}
    entry.update(entry_fields)
    return {'schemaVersion': 1, 'revision': 1, 'updatedAt': NOW, 'decisions': {decision: entry}}


def test_a_legacy_state_with_only_the_original_decisions_still_validates(catalog):
    entry = {'mode': 'shadow', 'pinned': True, 'since': NOW, 'reason': 'manual_pin', 'policySha256': None,
             'instrumentSha256': None, 'layaRevision': None, 'cohortId': None}
    legacy = {'schemaVersion': 1, 'revision': 3, 'updatedAt': NOW, 'decisions': {d: dict(entry) for d in LEGACY_ONLY}}
    contract.validate_state(legacy, catalog)
    cosign = state_with(catalog, SKILL, mode='cosign', instrumentSha256=instrument.instrument_sha256(),
                        policySha256=contract.policy_sha256())
    contract.validate_state(cosign, catalog)
    contract.validate_state(state_with(catalog, SKILL), catalog)


@pytest.mark.parametrize('mode,field', [('advise', 'policySha256'), ('advise', 'instrumentSha256'),
                                        ('advise', 'layaRevision'), ('cosign', 'policySha256'),
                                        ('cosign', 'instrumentSha256')])
def test_earned_state_must_bind_its_hashes(catalog, mode, field):
    state = state_with(catalog, SKILL, mode=mode, **{field: None})
    with pytest.raises(ValueError, match='must bind'):
        contract.validate_state(state, catalog)


def test_cosign_state_without_a_laya_revision_stays_valid_for_now(catalog):
    # see the shortcut note in contract.validate_state; mutate() always writes a revision for both earned modes
    state = state_with(catalog, SKILL, mode='cosign', layaRevision=None, policySha256=contract.policy_sha256(),
                       instrumentSha256=instrument.instrument_sha256())
    contract.validate_state(state, catalog)


def test_state_modes_must_be_reachable(catalog):
    with pytest.raises(ValueError, match='invalid mode'):
        contract.validate_state(state_with(catalog, WORKFLOW, mode='off'), catalog)
    with pytest.raises(ValueError, match='invalid mode'):
        contract.validate_state(state_with(catalog, CRITICAL, mode='cosign'), catalog)
    contract.validate_state(state_with(catalog, CRITICAL), catalog)
    contract.validate_state(state_with(catalog, CRITICAL, cohortId=None), catalog)  # audited CLI override


# ---------------------------------------------------------------- mutate

def test_advise_requires_a_binding_and_other_modes_refuse_one(root, catalog):
    for actor in ('cli', 'cycle'):
        with pytest.raises(reg.RegistryError) as err:
            reg.mutate(root, WORKFLOW, 'advise', actor=actor, reason='gate_pass', expected_revision=0)
        assert err.value.code == 'binding_required'
    with pytest.raises(reg.RegistryError) as err:
        reg.mutate(root, WORKFLOW, 'advise', actor='cli', reason='manual_override', expected_revision=0,
                   binding={'policySha256': POLICY})
    assert err.value.code == 'binding_required'
    with pytest.raises(reg.RegistryError) as err:
        reg.mutate(root, WORKFLOW, 'shadow', actor='cli', reason='nope', expected_revision=0, pinned=True,
                   binding=binding(catalog, WORKFLOW))
    assert err.value.code == 'invalid_binding' and 'advise or cosign' in str(err.value)
    assert not (root / reg.STATE_FILE).exists()


@pytest.mark.parametrize('change', [
    {'instrumentSha256': 'b' * 64}, {'policySha256': 'nothex'}, {'policySha256': 'A' * 64}, {'layaRevision': 'has space'},
    {'layaRevision': 'other-rev'}, {'cohortId': 'xyz'}])
def test_advise_binding_must_name_the_current_instrument_policy_hash_and_checkpoint(root, catalog, change):
    bad = {**binding(catalog, WORKFLOW), **change}
    with pytest.raises(reg.RegistryError) as err:
        reg.mutate(root, WORKFLOW, 'advise', actor='cli', reason='manual_override', expected_revision=0, binding=bad)
    assert err.value.code == 'invalid_binding'


def test_cli_may_override_with_a_null_cohort_but_the_cycle_may_not(root, catalog):
    with pytest.raises(reg.RegistryError) as err:
        reg.mutate(root, WORKFLOW, 'advise', actor='cycle', reason='gate_pass', expected_revision=0,
                   binding=binding(catalog, WORKFLOW))
    assert err.value.code == 'binding_required'
    state = reg.mutate(root, WORKFLOW, 'advise', actor='cli', reason='manual_override', expected_revision=0,
                       binding=binding(catalog, WORKFLOW), now=NOW)
    entry = state['decisions'][WORKFLOW]
    assert entry['mode'] == 'advise' and entry['cohortId'] is None and entry['layaRevision'] == REV
    assert entry['instrumentSha256'] == typed_advice.INSTRUMENT_SHA256 and entry['policySha256'] == POLICY
    contract.validate_state(state, catalog)


def test_cycle_advise_needs_a_consumed_pass_in_the_advise_ledger(root, catalog):
    def attempt(cohort_id):
        return reg.mutate(root, WORKFLOW, 'advise', actor='cycle', reason='gate_pass', expected_revision=0,
                          binding=binding(catalog, WORKFLOW, cohort_id), now=NOW)

    with pytest.raises(reg.RegistryError) as err:           # no ledger at all
        attempt('1' * 32)
    assert err.value.code == 'invalid_binding'
    write_cohort(root, catalog, WORKFLOW, cohort='2' * 32, consume=False)
    with pytest.raises(reg.RegistryError) as err:           # reserved, never consumed
        attempt('2' * 32)
    assert err.value.code == 'invalid_binding'
    advise_ledger.append(root, WORKFLOW, {
        'event': 'reserve', 'cohortId': '3' * 32, 'decision': WORKFLOW, 'policySha256': POLICY,
        'instrumentSha256': instrument_hash(catalog, WORKFLOW), 'layaRevision': REV, 'attempt': 2, 'alpha': 0.05,
        'caseIds': ['case-9'], 'groups': groups('3' * 32, 1), 'ts': NOW})
    advise_ledger.append(root, WORKFLOW, {
        'event': 'consumed', 'cohortId': '3' * 32, 'decision': WORKFLOW, 'policySha256': POLICY,
        'instrumentSha256': instrument_hash(catalog, WORKFLOW), 'layaRevision': REV, 'attempt': 2, 'alpha': 0.05,
        'verdict': 'hold', 'receiptSha256': 'c' * 64, 'ts': NOW})
    with pytest.raises(reg.RegistryError) as err:           # consumed with a hold verdict
        attempt('3' * 32)
    assert err.value.code == 'invalid_binding'
    write_cohort_pass = {'event': 'reserve', 'cohortId': '4' * 32, 'decision': WORKFLOW, 'policySha256': POLICY,
                         'instrumentSha256': instrument_hash(catalog, WORKFLOW), 'layaRevision': REV, 'attempt': 3,
                         'alpha': 0.025, 'caseIds': ['case-10'], 'groups': groups('4' * 32, 1), 'ts': NOW}
    advise_ledger.append(root, WORKFLOW, write_cohort_pass)
    advise_ledger.append(root, WORKFLOW, {**{k: v for k, v in write_cohort_pass.items() if k not in ('caseIds', 'groups')},
                                          'event': 'consumed', 'verdict': 'pass', 'receiptSha256': 'd' * 64})
    with pytest.raises(reg.RegistryError) as err:           # a pass for another policy hash does not carry over
        reg.mutate(root, WORKFLOW, 'advise', actor='cycle', reason='gate_pass', expected_revision=0,
                   binding=binding(catalog, WORKFLOW, '4' * 32, policy='e' * 64))
    assert err.value.code == 'invalid_binding'
    state = attempt('4' * 32)
    assert state['decisions'][WORKFLOW]['cohortId'] == '4' * 32
    contract.validate_state(state, catalog)
    lines, invalid = reg.read_audit(root)
    assert invalid == 0 and lines[-1]['actor'] == 'cycle' and lines[-1]['toMode'] == 'advise'


def test_a_critical_decision_reaches_advise_but_never_cosign(root, catalog):
    write_cohort(root, catalog, CRITICAL)
    state = reg.mutate(root, CRITICAL, 'advise', actor='cycle', reason='gate_pass', expected_revision=0,
                       binding=binding(catalog, CRITICAL, '1' * 32), now=NOW)
    assert state['decisions'][CRITICAL]['mode'] == 'advise'
    with pytest.raises(reg.RegistryError) as err:
        reg.mutate(root, CRITICAL, 'cosign', actor='cli', reason='nope', expected_revision=1,
                   binding=binding(catalog, CRITICAL))
    assert err.value.code == 'unreachable_mode'
    bad = copy.deepcopy(catalog)
    bad['decisions'][CRITICAL]['reachableModes'].append('cosign')   # a wrongly edited registry cannot grant it either
    with pytest.raises(reg.RegistryError) as err:
        reg.mutate(root, CRITICAL, 'cosign', actor='cli', reason='nope', expected_revision=1,
                   binding=binding(catalog, CRITICAL), registry=bad)
    assert err.value.code == 'unreachable_mode'
    # a demotion needs no binding and clears it
    down = reg.mutate(root, CRITICAL, 'shadow', actor='cycle', reason='critical_miss', expected_revision=1, now=NOW)
    assert down['decisions'][CRITICAL]['mode'] == 'shadow' and down['decisions'][CRITICAL]['cohortId'] is None


def test_a_cosign_cohort_never_authorizes_advise(root):
    registry = small_registry()
    (root / 'laya-runtime.json').write_text(json.dumps({'revision': LAYA_REV}))
    event, _ = passed_cohort(root, registry, disagreements(25))
    cosign_binding = {'policySha256': contract.policy_sha256(), 'instrumentSha256': instrument.instrument_sha256(),
                      'layaRevision': LAYA_REV, 'cohortId': event['cohortId']}
    # the same cohort is a valid cosign authority ...
    cohorts.verify_passed_cohort(root, registry['decisions'][SKILL], cosign_binding)
    # ... and no authority for advise: its ledger is separate
    with pytest.raises(reg.RegistryError) as err:
        reg.mutate(root, SKILL, 'advise', actor='cycle', reason='gate_pass', expected_revision=0, registry=registry,
                   binding={**cosign_binding, 'instrumentSha256': instrument_hash(registry, SKILL)})
    assert err.value.code == 'invalid_binding'


def test_an_advise_cohort_never_authorizes_cosign(root):
    registry = small_registry()
    (root / 'laya-runtime.json').write_text(json.dumps({'revision': LAYA_REV}))
    advise_binding = binding(registry, SKILL, '5' * 32, rev=LAYA_REV)
    write_cohort(root, registry, SKILL, cohort='5' * 32, rev=LAYA_REV)
    advise_ledger.verify_pass(root, SKILL, advise_binding)
    cosign_binding = {'policySha256': contract.policy_sha256(), 'instrumentSha256': instrument.instrument_sha256(),
                      'layaRevision': LAYA_REV, 'cohortId': '5' * 32}
    with pytest.raises(ValueError):
        cohorts.verify_passed_cohort(root, registry['decisions'][SKILL], cosign_binding)
    with pytest.raises(reg.RegistryError) as err:
        reg.mutate(root, SKILL, 'cosign', actor='cycle', reason='gate_passed', expected_revision=0, registry=registry,
                   binding=cosign_binding)
    assert err.value.code == 'invalid_binding'
    # skill fit can hold advise from the advise ledger ...
    state = reg.mutate(root, SKILL, 'advise', actor='cycle', reason='gate_pass', expected_revision=0,
                       registry=registry, binding=advise_binding, now=NOW)
    assert state['decisions'][SKILL]['mode'] == 'advise'


def test_a_pinned_decision_refuses_the_cycle_for_advise(root, catalog):
    reg.mutate(root, WORKFLOW, 'shadow', actor='cli', reason='manual_pin', expected_revision=0, pinned=True, now=NOW)
    write_cohort(root, catalog, WORKFLOW)
    with pytest.raises(reg.RegistryError) as err:
        reg.mutate(root, WORKFLOW, 'advise', actor='cycle', reason='gate_pass', expected_revision=1,
                   binding=binding(catalog, WORKFLOW, '1' * 32))
    assert err.value.code == 'pinned'
    # the cycle may not demote a pinned advise either; the operator can
    reg.mutate(root, WORKFLOW, 'advise', actor='cli', reason='manual_override', expected_revision=1,
               binding=binding(catalog, WORKFLOW))
    with pytest.raises(reg.RegistryError) as err:
        reg.mutate(root, WORKFLOW, 'shadow', actor='cycle', reason='demoted_quality', expected_revision=2)
    assert err.value.code == 'pinned'


def test_pinning_a_deployed_advise_keeps_its_basis(root, catalog):
    reg.mutate(root, WORKFLOW, 'advise', actor='cli', reason='manual_override', expected_revision=0,
               binding=binding(catalog, WORKFLOW), now=NOW)
    pinned = reg.mutate(root, WORKFLOW, 'advise', actor='cli', reason='manual_pin', expected_revision=1, pinned=True,
                        now='2026-10-17T00:00:00Z')
    entry = pinned['decisions'][WORKFLOW]
    assert entry['pinned'] and entry['mode'] == 'advise' and entry['since'] == NOW
    assert entry['policySha256'] == POLICY and entry['layaRevision'] == REV
    with pytest.raises(reg.RegistryError) as err:           # nothing changed
        reg.mutate(root, WORKFLOW, 'advise', actor='cli', reason='manual_pin', expected_revision=2, pinned=True)
    assert err.value.code == 'no_change'


def test_cli_sets_advise_with_an_explicit_override(root, catalog, capsys):
    base = ['--root', str(root), 'set-mode', WORKFLOW, 'advise', '--reason', 'manual_override']
    assert reg.main(base) == 2                                       # no binding at all
    assert reg.main(base + ['--laya-revision', REV, '--policy-sha256', POLICY]) == 2   # ungated needs confirmation
    assert reg.main(base + ['--laya-revision', REV, '--manual-override']) == 2         # advise needs a policy hash
    capsys.readouterr()
    assert reg.main(base + ['--laya-revision', REV, '--policy-sha256', POLICY, '--manual-override']) == 0
    assert json.loads(capsys.readouterr().out)['mode'] == 'advise'
    assert reg.main(['--root', str(root), 'set-mode', WORKFLOW, 'advise', '--reason', 'manual_pin', '--pin']) == 0
    assert reg.main(['--root', str(root), 'show']) == 0
    shown = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert shown['decisions'][WORKFLOW]['effectiveMode'] == 'advise' and shown['decisions'][WORKFLOW]['pinned']


# ---------------------------------------------------------------- staleness (Python reader)

def test_advise_state_is_shadow_when_the_instrument_or_laya_revision_changed(catalog):
    good = state_with(catalog, SKILL, policySha256=ADVISE_V1)
    assert reg.effective_mode(SKILL, catalog, good, 'ok', REV) == 'advise'
    assert reg.effective_mode(SKILL, catalog, good, 'ok', None) == 'advise'   # revision unknown to the caller
    assert reg.binding_stale(SKILL, catalog, good['decisions'][SKILL], 'newer-rev') == 'laya_revision_changed'
    assert reg.effective_mode(SKILL, catalog, good, 'ok', 'newer-rev') == 'shadow'
    stale = state_with(catalog, SKILL, instrumentSha256='f' * 64, policySha256=ADVISE_V1)
    assert reg.binding_stale(SKILL, catalog, stale['decisions'][SKILL], REV) == 'binding_stale'
    assert reg.effective_mode(SKILL, catalog, stale, 'ok', REV) == 'shadow'
    # an instrument change in the registry itself also invalidates the earned state
    moved = mutated(catalog, SKILL, lambda e: e['advise'].update(instrument='typed-advice-v1'))
    assert reg.effective_mode(SKILL, moved, good, 'ok', REV) == 'shadow'
    # skill-fit alone binds the advise-v1 contract hash (its one surface is the Node router) ...
    for wrong in ('9' * 64, contract.policy_sha256('cosign-v1'), POLICY):
        bad = state_with(catalog, SKILL, policySha256=wrong)
        assert reg.binding_stale(SKILL, catalog, bad['decisions'][SKILL], REV) == 'binding_stale'
        assert reg.effective_mode(SKILL, catalog, bad, 'ok', REV) == 'shadow'
    # ... every other decision's advise policy hash is the surface's to check: any bound hash is fine here
    other_policy = state_with(catalog, WORKFLOW, policySha256='9' * 64)
    assert reg.effective_mode(WORKFLOW, catalog, other_policy, 'ok', REV) == 'advise'
    # cosign staleness is unchanged
    cosign = state_with(catalog, SKILL, mode='cosign', policySha256='9' * 64,
                        instrumentSha256=instrument.instrument_sha256())
    assert reg.effective_mode(SKILL, catalog, cosign, 'ok', REV) == 'shadow'


def test_typed_advice_reads_what_the_registry_wrote(root, catalog):
    """The surface and the registry agree on the binding: mutate -> typed_advice.effective_mode."""
    policy = typed_advice.policy_sha256(WORKFLOW, 'which workflow?', 'content|general|none')
    reg.mutate(root, WORKFLOW, 'advise', actor='cli', reason='manual_override', expected_revision=0,
               binding=binding(catalog, WORKFLOW, policy=policy), now=NOW)
    assert typed_advice.effective_mode(WORKFLOW, policy, root) == 'advise'
    assert typed_advice.effective_mode(WORKFLOW, '0' * 64, root) == 'shadow'
    (root / 'laya-runtime.json').write_text(json.dumps({'revision': 'newer-rev'}))
    assert typed_advice.effective_mode(WORKFLOW, policy, root) == 'shadow'


def test_typed_advice_records_validate_against_the_contract(root, catalog):
    candidates = [{'id': 'content', 'criterion': 'marketing content'}, {'id': 'general', 'criterion': 'anything else'},
                  {'id': 'none', 'criterion': 'no workflow applies'}]
    answer = {'status': 'ok', 'choice': 'content', 'probabilities': {'content': 0.6, 'general': 0.3, 'none': 0.1},
              'latencyMs': 12.5}
    result = typed_advice.advise(WORKFLOW, 'write a blog post', candidates, 'key-1', critical_if_wrong=False,
                                 question='which workflow?', policy='content|general|none', store=root,
                                 call=lambda *a, **k: answer)
    record = typed_advice.load(WORKFLOW, result['decisionId'], store=root)
    assert contract.validate_choice_record(record) is record
    assert typed_advice.record_outcome(WORKFLOW, result['decisionId'], 'general', store=root)
    outcome = typed_advice.load(WORKFLOW, result['decisionId'], kind='outcome', store=root)
    assert contract.validate_choice_outcome(outcome)['followed'] is False
    failed = typed_advice.advise(WORKFLOW, 'another request', candidates, 'key-2', critical_if_wrong=True,
                                 question='which workflow?', policy='content|general|none', store=root,
                                 call=lambda *a, **k: {'status': 'timeout', 'choice': None, 'probabilities': None,
                                                       'latencyMs': 1500.0})
    contract.validate_choice_record(typed_advice.load(WORKFLOW, failed['decisionId'], store=root))


@pytest.mark.parametrize('change', [
    {'schema': 'x'}, {'decision': 'nope'}, {'mode': 'cosign'}, {'arm': 'none'}, {'candidates': ['only-one']},
    {'candidates': ['a', 'a']}, {'files': 21}, {'files': True}, {'requestSha256': 'abc'}, {'extra': 1}, {'groupSha256': 'nothex'},
    {'laya': {'status': 'ok', 'choice': 'zzz', 'probabilities': {'a': 1.0, 'b': 0.0}, 'latencyMs': 1}},
    {'laya': {'status': 'ok', 'choice': 'a', 'probabilities': {'a': 1.0}, 'latencyMs': 1}},
    {'laya': {'status': 'timeout', 'choice': 'a', 'probabilities': None, 'latencyMs': 1}},
    {'laya': {'status': 'bogus', 'choice': None, 'probabilities': None, 'latencyMs': 1}}])
def test_invalid_choice_records_are_rejected(change):
    record = {'schema': contract.CHOICE_RECORD_SCHEMA, 'decision': WORKFLOW, 'decisionId': '1' * 32, 'ts': NOW,
              'mode': 'advise', 'arm': 'treatment', 'tier': 'workflow', 'policySha256': POLICY,
              'instrumentSha256': typed_advice.INSTRUMENT_SHA256, 'layaRevision': REV, 'candidates': ['a', 'b'],
              'criticalIfWrong': False, 'requestSha256': 'b' * 64, 'files': 0,
              'laya': {'status': 'ok', 'choice': 'a', 'probabilities': {'a': 0.7, 'b': 0.3}, 'latencyMs': 3}}
    contract.validate_choice_record(record)
    with pytest.raises(ValueError):
        contract.validate_choice_record({**record, **change})


def test_invalid_choice_outcomes_are_rejected():
    outcome = {'schema': contract.CHOICE_OUTCOME_SCHEMA, 'decision': WORKFLOW, 'decisionId': '1' * 32,
               'chosen': 'a', 'followed': True, 'ts': NOW}
    contract.validate_choice_outcome(outcome)
    for change in ({'schema': 'x'}, {'chosen': ''}, {'followed': 1}, {'decisionId': 'z'}, {'extra': 1}):
        with pytest.raises(ValueError):
            contract.validate_choice_outcome({**outcome, **change})


# ---------------------------------------------------------------- JSON schemas vs contract

def schema(name):
    return json.loads((SCHEMAS / f'{name}.schema.json').read_text())


def test_json_schemas_agree_with_the_contract_constants():
    registry = schema('decision-registry-v1')
    entry = registry['properties']['decisions']['additionalProperties']
    assert registry['properties']['decisions']['propertyNames']['enum'] == list(contract.DECISIONS)
    assert entry['properties']['reachableModes']['items']['enum'] == list(contract.MODES)
    assert entry['properties']['defaultMode']['enum'] == ['off', 'shadow']
    assert entry['properties']['tier']['enum'] == list(contract.TIERS)
    assert set(entry['required']) == set(contract.REGISTRY_ENTRY_KEYS) and 'advise' in entry['properties']
    advise = registry['$defs']['advise']
    assert advise['required'] == list(contract.ADVISE_KEYS) == list(advise['properties'])
    assert advise['properties']['instrument']['enum'] == list(contract.ADVISE_INSTRUMENTS)
    assert advise['properties']['demote']['required'] == list(contract.ADVISE_DEMOTE_KEYS)
    state = schema('decision-registry-state-v1')
    assert state['properties']['decisions']['propertyNames']['enum'] == list(contract.DECISIONS)
    assert state['properties']['decisions']['additionalProperties']['properties']['mode']['enum'] == list(contract.MODES)
    assert set(state['properties']['decisions']['additionalProperties']['required']) == set(contract.STATE_ENTRY_KEYS)
    for branch in schema('decision-registry-audit-v1')['oneOf']:
        assert branch['properties']['decision']['enum'] == list(contract.DECISIONS)
        assert branch['properties']['toMode']['enum'] == list(contract.MODES)
        assert branch['properties']['fromMode']['anyOf'][0]['enum'] == list(contract.MODES)
    record, outcome = schema('typed-choice-record-v1'), schema('typed-choice-outcome-v1')
    assert set(record['required']) == set(contract.CHOICE_RECORD_KEYS)
    assert set(record['properties']) == set(contract.CHOICE_RECORD_KEYS) | set(contract.CHOICE_RECORD_OPTIONAL)
    assert record['properties']['laya']['required'] == list(contract.CHOICE_LAYA_KEYS)
    assert record['properties']['laya']['properties']['status']['enum'] == list(contract.CHOICE_LAYA_STATUSES)
    assert record['properties']['decision']['enum'] == list(contract.ADVISE_DECISIONS)
    assert record['properties']['schema']['const'] == contract.CHOICE_RECORD_SCHEMA
    assert set(outcome['required']) == set(contract.CHOICE_OUTCOME_KEYS) == set(outcome['properties'])
    assert outcome['properties']['schema']['const'] == contract.CHOICE_OUTCOME_SCHEMA
    shown = schema('typed-choice-shown-v1')
    assert set(shown['required']) == set(contract.CHOICE_SHOWN_KEYS) == set(shown['properties'])
    assert shown['properties']['schema']['const'] == contract.CHOICE_SHOWN_SCHEMA
    assert shown['properties']['decision']['enum'] == list(contract.ADVISE_DECISIONS)


@pytest.mark.skipif(jsonschema is None, reason='jsonschema not installed; stdlib validators are canonical')
def test_json_schemas_accept_the_catalog_and_advise_states(catalog):
    registry_schema = jsonschema.Draft202012Validator(schema('decision-registry-v1'))
    registry_schema.validate(catalog)
    for decision, fn in ((CRITICAL, lambda e: e['advise'].update(minCriticalCases=9)),
                         (CRITICAL, lambda e: e.update(reachableModes=['off', 'shadow', 'advise', 'cosign'])),
                         (CRITICAL, lambda e: e.update(advise=None))):
        with pytest.raises(jsonschema.ValidationError):
            registry_schema.validate(mutated(catalog, decision, fn))
    state_schema = jsonschema.Draft202012Validator(schema('decision-registry-state-v1'))
    state_schema.validate(state_with(catalog, SKILL))
    with pytest.raises(jsonschema.ValidationError):
        state_schema.validate(state_with(catalog, SKILL, layaRevision=None))


# ---------------------------------------------------------------- Python / Node reader parity

HOOK_LIB = REPO / 'rhize-context-manager' / 'hooks' / 'lib' / 'decision-registry.js'


@pytest.mark.skipif(shutil.which('node') is None, reason='node is not installed')
def test_python_effective_mode_and_the_node_reader_agree_on_skill_fit_advise_states(tmp_path, catalog):
    node_script = ("const r = require(process.argv[1]);"
                   "const c = r.readDecisionConfig('skill-fit', {statePath: process.argv[2], layaRuntimePath: process.argv[3]});"
                   "process.stdout.write(c.mode);")
    runtime = tmp_path / 'laya-runtime.json'
    runtime.write_text(json.dumps({'revision': REV}))
    instrument_sha = instrument_hash(catalog, SKILL)
    cases = {
        'bound': {}, 'cosign policy': {'policySha256': contract.policy_sha256('cosign-v1')},
        'other policy': {'policySha256': '9' * 64}, 'old fixed hash': {'policySha256': 'b' * 64},
        'other instrument': {'instrumentSha256': 'f' * 64}, 'other revision': {'layaRevision': 'other-rev'}}
    for name, change in cases.items():
        state = state_with(catalog, SKILL, **{'policySha256': ADVISE_V1, 'instrumentSha256': instrument_sha, **change})
        state['decisions'] = {SKILL: state['decisions'][SKILL]}
        path = tmp_path / (name.replace(' ', '-') + '.json')
        path.write_text(json.dumps(state))
        node = subprocess.run(['node', '-e', node_script, str(HOOK_LIB), str(path), str(runtime)],
                              capture_output=True, text=True, timeout=30).stdout
        assert node == reg.effective_mode(SKILL, catalog, state, 'ok', REV), name
    bound = state_with(catalog, SKILL, policySha256=ADVISE_V1)       # the control: both readers do say advise
    (tmp_path / 'ok.json').write_text(json.dumps(bound))
    ok = subprocess.run(['node', '-e', node_script, str(HOOK_LIB), str(tmp_path / 'ok.json'), str(runtime)],
                        capture_output=True, text=True, timeout=30).stdout
    assert ok == reg.effective_mode(SKILL, catalog, bound, 'ok', REV) == 'advise'
