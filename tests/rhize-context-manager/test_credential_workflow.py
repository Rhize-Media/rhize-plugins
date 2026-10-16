"""Bounded credential policy activation, mirrored identities and independent hard deny."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from typed_decision_testkit import SCRIPTS
from typed_decisions import cohorts, contract, decision_registry as registry, instrument

REPO = SCRIPTS.parents[1]


def credential_binding():
    entry = registry.load_registry()['decisions']['workflow-fit']
    policy, question = cohorts.deployable_hashes(entry)
    return {'policySha256': policy, 'instrumentSha256': question, 'layaRevision': 'fixture-known', 'cohortId': None}


def runtime(root):
    root.mkdir(mode=0o700)
    (root / 'laya-runtime.json').write_text(json.dumps({'revision': 'fixture-known'}))


def node_mode(root):
    script = "delete process.env.RHIZE_LAYA_ENDPOINT;const r=require('./rhize-context-manager/hooks/lib/decision-registry.js');console.log(r.readDecisionConfig('workflow-fit',{statePath:process.argv[1],layaRuntimePath:process.argv[2]}).mode)"
    result = subprocess.run(['node', '-e', script, str(root / registry.STATE_FILE), str(root / 'laya-runtime.json')],
                            cwd=REPO, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_mirrored_credential_policy_and_instrument_identities():
    expected = credential_binding()
    script = "const p=require('./rhize-context-manager/hooks/lib/typed-decisions.js');const i=require('./rhize-context-manager/hooks/lib/laya-instrument.js');console.log(JSON.stringify([p.policySha256('credential-cli-v1'),i.instrumentSha256('credential-cli-v1')]))"
    result = subprocess.run(['node', '-e', script], cwd=REPO, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [expected['policySha256'], expected['instrumentSha256']]


def test_known_source_bound_manual_activation_and_stale_runtime_fallback(tmp_path):
    root = tmp_path / 'state'; runtime(root)
    shipped = registry.load_registry()
    state = registry.mutate(root, 'workflow-fit', 'cosign', actor='cli', reason='fixture_only',
                            expected_revision=0, binding=credential_binding())
    assert registry.effective_mode('workflow-fit', shipped, state, 'ok', 'fixture-known') == 'cosign'
    assert node_mode(root) == 'cosign'
    assert registry.effective_mode('workflow-fit', shipped, state, 'ok', 'changed') == 'shadow'
    state['decisions']['workflow-fit']['instrumentSha256'] = 'f' * 64
    assert registry.effective_mode('workflow-fit', shipped, state, 'ok', 'fixture-known') == 'shadow'


@pytest.mark.parametrize('revision,cohort', [(None, None), ('unknown', None), ('fixture-known', 'a' * 32)])
def test_both_runtime_readers_refuse_unbound_or_cohort_based_credential_authority(tmp_path, revision, cohort):
    root = tmp_path / 'state'; runtime(root)
    shipped = registry.load_registry()
    state = registry.mutate(root, 'workflow-fit', 'cosign', actor='cli', reason='fixture_only',
                            expected_revision=0, binding=credential_binding())
    state['decisions']['workflow-fit'].update(layaRevision=revision, cohortId=cohort)
    (root / registry.STATE_FILE).write_text(json.dumps(state))
    loaded, status = registry.read_state(root, shipped)
    assert status == 'corrupt'
    assert registry.effective_mode('workflow-fit', shipped, loaded, status, 'fixture-known') == 'shadow'
    assert registry.effective_mode('workflow-fit', shipped, state, 'ok', None) == 'shadow'
    assert node_mode(root) == 'shadow'


@pytest.mark.parametrize('actor,cohort,revision', [('cycle', None, 'fixture-known'),
    ('cli', 'a' * 32, 'fixture-known'), ('cli', None, 'unknown')])
def test_cycle_cohort_reuse_and_unknown_checkpoint_refused(tmp_path, actor, cohort, revision):
    root = tmp_path / 'state'; runtime(root)
    if revision == 'unknown': (root / 'laya-runtime.json').unlink()
    binding = {**credential_binding(), 'cohortId': cohort, 'layaRevision': revision}
    with pytest.raises(registry.RegistryError, match='invalid_binding'):
        registry.mutate(root, 'workflow-fit', 'cosign', actor=actor, reason='fixture_only',
                        expected_revision=0, binding=binding)
    assert not (root / registry.STATE_FILE).exists()


def test_cli_requires_existing_explicit_manual_override(tmp_path):
    root = tmp_path / 'state'; runtime(root)
    args = [sys.executable, str(SCRIPTS / 'typed_decisions/decision_registry.py'), '--root', str(root),
            'set-mode', 'workflow-fit', 'cosign', '--reason', 'fixture_only', '--laya-revision', 'fixture-known']
    refused = subprocess.run(args, capture_output=True, text=True, timeout=10)
    assert refused.returncode == 2 and json.loads(refused.stdout)['error'] == 'binding_required'
    accepted = subprocess.run(args + ['--manual-override', '--pin'], capture_output=True, text=True, timeout=10)
    assert accepted.returncode == 0 and json.loads(accepted.stdout)['pinned'] is True


@pytest.mark.parametrize('key,value', [('tier', 'critical'), ('defaultMode', 'cosign'),
    ('holdback', 0.1), ('lambda', 1), ('gates', {}), ('instrument', 'laya-choice-v1')])
def test_policy_boundaries_are_not_generic_workflow_authority(key, value):
    shipped = copy.deepcopy(registry.load_registry())
    shipped['decisions']['workflow-fit'][key] = value
    with pytest.raises(ValueError): contract.validate_registry(shipped)


def test_gui_guard_source_unchanged_and_native_events_packaged():
    assert hashlib.sha256((REPO / 'rhize-devflow/scripts/credential_guard.py').read_bytes()).hexdigest() == '3d8238dcf0fb62297b334278d62e9e406c43f91c58b030da8266edb91bd8a3eb'
    hooks = json.loads((REPO / 'rhize-context-manager/hooks/hooks.json').read_text())['hooks']
    for event, name in [('UserPromptSubmit', 'credential-workflow-prompt.js'), ('PreToolUse', 'credential-workflow.js')]:
        assert any(name in h['command'] for group in hooks[event] for h in group['hooks'])


def test_pilot_contract_is_capability_scoped():
    from workflow_selection import hook_message
    message = hook_message({'decisionPilot': 'shadow-v2', 'opportunityId': 'a' * 64})
    assert 'content/general measurement pilot' in message
    assert 'bounded active policy' in message
    assert 'never grants permissions or clears the credential GUI hard deny' in message
    assert 'Arm A remains authoritative; Laya is shadow-only' not in message
