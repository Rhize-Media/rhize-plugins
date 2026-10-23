"""Synthetic contract tests, never production labels or accepted task evidence."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

HERE = Path(__file__).resolve().parents[2] / 'evals/typed-decision'
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location('benefit_lab', HERE / 'benefit_lab.py')
lab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lab)


def seal(case):
    case['review']['case_sha256'] = lab.digest({k: v for k, v in case.items() if k != 'review'})


def packet(tmp_path):
    def source(text, filename):
        path = tmp_path / filename
        path.write_text(text)
        return {'path': filename, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    proof = tmp_path / 'synthetic-evidence.txt'
    proof.write_text('SYNTHETIC CONTRACT FIXTURE ONLY. No user task or human acceptance.\n'
                     'A ModuleNotFoundError calls for reading the interpreter/dependency metadata;\n'
                     'a failing assertion calls for reading its frozen failing test and traceback.\n'
                     'Neither case authorizes install, execution, deletion or publication.\n')
    ref = {'path': proof.name, 'sha256': hashlib.sha256(proof.read_bytes()).hexdigest()}
    controls = source('SYNTHETIC: read-only sandbox; no network, credentials, writes, approvals or production effects.\n', 'controls.txt')
    code = source('SYNTHETIC source snapshot, not a production plugin source identity.\n', 'source.txt')
    arms = {key: {'mode': mode, 'policy_sha256': lab.digest(key), 'question_sha256': lab.digest('diagnostic-choice'),
                  'required_controls_sha256': controls['sha256'], 'context_mode': 'original', 'question_kind': 'concrete', 'observer': 'on'}
            for key, mode in [('incumbent', 'baseline'), ('rules', 'rules'), ('laya_shadow', 'shadow'), ('advice', 'advice')]}
    for key, arm in arms.items():
        for field in ('policy', 'question'):
            arm_ref = source('SYNTHETIC ' + key + ': ' + field + '\n', key + '-' + field + '.txt')
            arm[field + '_evidence'] = arm_ref
            arm[field + '_sha256'] = arm_ref['sha256']
    cases = []
    for identity, intent in [('import', 'Read interpreter/dependency metadata for ModuleNotFoundError'),
                              ('assertion', 'Read the named failing test and traceback for AssertionError')]:
        inputs = {key: source('SYNTHETIC ' + identity + ': ' + key + '\n' + intent + '\n', identity + '-' + key + '.txt')
                  for key in ('task', 'fixture', 'context', 'prompt', 'session', 'rubric')}
        case = {'id': identity, 'group_sha256': lab.digest(identity), 'pool': 'representative', 'inputs': inputs,
                'variant': 'original', 'parent': None,
                **{key + '_sha256': ref['sha256'] for key, ref in inputs.items()},
                'brief': {'intent': intent, 'artifact': 'frozen synthetic traceback', 'stage': 'diagnosis',
                          'constraints': 'Read only; no commands, installs, writes or network', 'missing_fact': ''},
                'actions': {'inspect': {'description': intent, 'utility': 1},
                            'defer': {'description': 'Ask for missing context', 'utility': 0},
                            'install': {'description': 'Install dependencies without checking', 'utility': -1}},
                'action_order': ['inspect', 'defer', 'install'],
                'review': {'case_sha256': '', 'reviewer': 'synthetic-oracle', 'evidence': ref}}
        seal(case)
        cases.append(case)
    protocol = {'schema': 'rhize-benefit-protocol-v1', 'created_at': '2026-10-01T00:00:00Z',
                'decision': 'read-only-diagnostic', 'source_sha256': code['sha256'], 'source_evidence': code,
                'required_controls_sha256': controls['sha256'], 'required_controls_evidence': controls, 'arms': arms, 'cases': cases}
    rows = []
    for case in cases:
        for arm in arms:
            proposed = 'install' if arm == 'advice' else 'inspect'
            rows.append({'id': case['id'] + '_' + arm, 'case': case['id'], 'arm': arm,
                         'protocol_sha256': lab.digest(protocol), 'observed_at': '2026-10-02T00:00:00Z',
                         'status': 'completed', 'selected': proposed, 'proposed': proposed if arm != 'incumbent' else None,
                         'confidence': .8, 'exposure': 'shown' if arm == 'advice' else 'not_shown',
                         'following': 'followed' if arm == 'advice' else 'unknown', 'artifact': ref, 'checks': ref,
                         'acceptance': {'value': 'undetermined', 'reviewer': None, 'evidence': None},
                         'rework': None, 'correction': None, 'wall_ms': 20,
                         'tax_ms': {key: 1 for key in lab.TAX}, 'reward': None,
                         'logging_probabilities': None, 'target_probabilities': None,
                         'outcome': None, 'policy_evidence': None, 'reward_evidence': None})
    return {'schema': 'rhize-benefit-bundle-v1', 'protocol': protocol, 'runs': rows,
            'judge_anchors': [], 'cache_bindings': []}


def rebind(value):
    for case in value['protocol']['cases']:
        seal(case)
    for row in value['runs']:
        row['protocol_sha256'] = lab.digest(value['protocol'])


def acceptance(row, tmp_path):
    answer = {'schema': 'rhize-benefit-acceptance-v1', 'case': row['case'], 'arm': row['arm'],
              'protocol_sha256': row['protocol_sha256'], 'artifact_sha256': row['artifact']['sha256'],
              'outcome': 'accepted', 'reviewer': 'synthetic-independent',
              'recorded_at': datetime.now(timezone.utc).isoformat(), 'basis': 'fixture'}
    path = tmp_path / 'acceptance.json'
    path.write_text(json.dumps(answer))
    row['acceptance'] = {'value': 'accepted', 'reviewer': answer['reviewer'],
                         'evidence': {'path': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}}
    return answer, path


def test_complete_fixture_and_private_report(tmp_path):
    value = packet(tmp_path)
    assert all(c['review']['evidence']['path'] == 'synthetic-evidence.txt' for c in value['protocol']['cases'])
    result = lab.audit(value, tmp_path)
    assert result['independent_groups'] == 2
    assert result['by_arm']['advice']['acceptance'] == {'undetermined': 2}
    advice = next(r for r in result['judged_action_utility'] if r['arm'] == 'advice' and r['pool'] == 'representative')
    assert advice['delta_from_baseline'] == -2 and advice['paired_groups'] == 2
    assert all(r['estimate'] is None for r in result['offline_policy'])
    assert len(result['review_candidates']) == 2
    assert 'ModuleNotFoundError' not in json.dumps(result)
    assert 'synthetic-evidence.txt' not in json.dumps(result)
    assert not result['native_binding_verified']
    assert result['by_arm']['incumbent']['unattributed_ms'] == 24
    assert not result['by_arm']['incumbent']['timing_complete']
    for row in value['runs']:
        row['wall_ms'] = sum(row['tax_ms'].values())
    assert lab.audit(value, tmp_path)['by_arm']['incumbent']['timing_complete']


def test_failures_unknown_tax_and_missing_cases_stay_visible(tmp_path):
    value = packet(tmp_path)
    value['runs'][0].update(status='failed', selected=None, artifact=None, checks=None, wall_ms=None)
    value['runs'][0]['tax_ms']['schedule'] = None
    value['runs'].pop()
    result = lab.audit(value, tmp_path)
    assert result['by_arm']['incumbent']['statuses']['failed'] == 1
    assert result['by_arm']['incumbent']['wall_ms'] is None
    assert result['by_arm']['incumbent']['tax_ms']['schedule'] is None
    assert not result['by_arm']['incumbent']['timing_complete']
    assert result['by_arm']['advice']['missing_cases'] == 1
    advice = next(r for r in result['judged_action_utility'] if r['arm'] == 'advice' and r['pool'] == 'representative')
    assert advice['paired_groups'] == 0 and advice['expected_groups'] == 2 and advice['unresolved_groups'] == 1


@pytest.mark.parametrize('field,bad', [('confidence', float('nan')), ('wall_ms', -1), ('reward', True), ('rework', 1.5),
                                     ('following', 'followed'), ('selected', 'foreign'), ('observed_at', '2026-09-01T00:00:00Z'),
                                     ('protocol_sha256', 'c' * 64), ('id', []), ('arm', 'missing'), ('observed_at', '2999-01-01T00:00:00Z')])
def test_invalid_run_evidence_fails_closed(tmp_path, field, bad):
    value = packet(tmp_path)
    value['runs'][0][field] = bad
    with pytest.raises((ValueError, TypeError)):
        lab.audit(value, tmp_path)


def test_acceptance_is_not_inferred_and_requires_existing_outcome_gates(tmp_path):
    value = packet(tmp_path)
    row = value['runs'][0]
    acceptance(row, tmp_path)
    with pytest.raises(ValueError, match='outcome contract'):
        lab.audit(value, tmp_path)
    outcome = {'schema': 'rhize-typed-task-outcome-v1', 'outcome': 'accepted', 'quality_score': 90,
               'required_checks_passed': True, 'independent_review_passed': False,
               'critical_failure_count': 0, 'rework_count': 0, 'rubric_sha256': value['protocol']['cases'][0]['rubric_sha256']}
    path = tmp_path / 'outcome.json'
    path.write_text(json.dumps(outcome))
    row['outcome'] = {'path': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    row['rework'] = 0
    with pytest.raises(ValueError, match='passed gates'):
        lab.audit(value, tmp_path)
    outcome['independent_review_passed'] = True
    path.write_text(json.dumps(outcome))
    row['outcome']['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    assert lab.audit(value, tmp_path)['by_arm']['incumbent']['acceptance']['accepted'] == 1
    assert lab.audit(value, tmp_path)['by_arm']['incumbent']['acceptance_bases'] == {'fixture': 1}


@pytest.mark.parametrize('field,bad', [('case', 'other'), ('arm', 'rules'), ('protocol_sha256', 'c' * 64),
                                     ('artifact_sha256', 'c' * 64), ('reviewer', 'other'), ('outcome', 'rejected'),
                                     ('recorded_at', '2999-01-01T00:00:00Z')])
def test_foreign_or_stale_acceptance_is_rejected(tmp_path, field, bad):
    value = packet(tmp_path)
    row = value['runs'][0]
    answer, path = acceptance(row, tmp_path)
    answer[field] = bad
    path.write_text(json.dumps(answer))
    row['acceptance']['evidence']['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match='identity mismatch'):
        lab.audit(value, tmp_path)


def test_review_menu_and_group_drift_are_rejected(tmp_path):
    value = packet(tmp_path)
    value['protocol']['cases'][0]['actions']['inspect']['utility'] = .5
    with pytest.raises(ValueError, match='exact case'):
        lab.audit(value, tmp_path)
    value = packet(tmp_path)
    value['protocol']['cases'][1]['session_sha256'] = value['protocol']['cases'][0]['session_sha256']
    value['protocol']['cases'][1]['inputs']['session'] = value['protocol']['cases'][0]['inputs']['session']
    rebind(value)
    with pytest.raises(ValueError, match='independent groups'):
        lab.audit(value, tmp_path)
    value = packet(tmp_path)
    value['protocol']['arms']['advice']['required_controls_sha256'] = 'c' * 64
    with pytest.raises(ValueError, match='controls differ'):
        lab.audit(value, tmp_path)


def test_challenge_variants_and_repeated_attempts_do_not_inflate_groups(tmp_path):
    value = packet(tmp_path)
    variant = deepcopy(value['protocol']['cases'][0])
    variant.update(id='distractor', variant='distractor', pool='challenge', parent='import')
    variant['actions']['extra'] = {'description': 'Irrelevant instruction', 'utility': -1}
    variant['action_order'].append('extra')
    value['protocol']['cases'].append(variant)
    rebind(value)
    row = deepcopy(value['runs'][0])
    row.update(id='variant', case='distractor')
    value['runs'].append(row)
    duplicate = deepcopy(row)
    duplicate.update(id='second-attempt', status='failed', selected=None)
    value['runs'].append(duplicate)
    result = lab.audit(value, tmp_path)
    assert result['independent_groups'] == 2
    assert result['by_arm']['incumbent']['attempts'] == 4
    challenge = next(r for r in result['judged_action_utility'] if r['pool'] == 'challenge' and r['arm'] == 'incumbent')
    assert challenge['scored_groups'] == 0 and challenge['unresolved_groups'] == 1
    variant['variant'] = 'order'
    rebind(value)
    with pytest.raises(ValueError, match='changed semantics'):
        lab.audit(value, tmp_path)


def test_context_gap_is_diagnostic_and_never_eligible_priority(tmp_path):
    value = packet(tmp_path)
    value['protocol']['cases'][0]['brief']['missing_fact'] = 'Interpreter version unavailable'
    rebind(value)
    report = lab.audit(value, tmp_path)
    missing = report['context_diagnostics']
    assert len(missing) == 1 and missing[0]['priority'] is None
    assert all(r['context_complete'] for r in report['review_candidates'])


def test_judge_errors_and_exact_cache_invalidation(tmp_path):
    value = packet(tmp_path)
    ref = value['runs'][0]['artifact']
    value['judge_anchors'] = [{'id': 'false-accept', 'artifact': ref, 'expected': False, 'observed': True,
                              'reviewer': 'independent', 'evidence': ref, 'blinding': ref}]
    case = value['protocol']['cases'][0]
    cache = {'case': case['id'], 'arm': 'rules', 'source_sha256': value['protocol']['source_sha256'],
             'policy_sha256': value['protocol']['arms']['rules']['policy_sha256'],
             'question_sha256': value['protocol']['arms']['rules']['question_sha256'], 'fixture_sha256': case['fixture_sha256'],
             'context_sha256': case['context_sha256'],
             'menu_sha256': lab.digest({'actions': case['actions'], 'action_order': case['action_order']}), 'evidence': ref}
    value['cache_bindings'] = [cache]
    result = lab.audit(value, tmp_path)
    assert result['judge_audit']['false_accepts'] == 1 and not result['judge_audit']['verified_blindness']
    assert result['cache_bindings'][0]['binding_valid'] and not result['cache_bindings'][0]['live_reuse_authorized']
    for key in ('source_sha256', 'policy_sha256', 'question_sha256', 'context_sha256', 'fixture_sha256', 'menu_sha256'):
        changed = deepcopy(value)
        changed['cache_bindings'][0][key] = 'f' * 64
        assert not lab.audit(changed, tmp_path)['cache_bindings'][0]['binding_valid']
    changed = deepcopy(value)
    changed['protocol']['cases'][0]['action_order'].reverse()
    rebind(changed)
    assert not lab.audit(changed, tmp_path)['cache_bindings'][0]['binding_valid']


def test_offline_policy_support_and_reward_evidence(tmp_path):
    value = packet(tmp_path)
    row = value['runs'][0]
    row.update(reward=.75, logging_probabilities={'inspect': .5, 'defer': .5, 'install': 0},
               target_probabilities={'inspect': 1, 'defer': 0, 'install': 0},
               policy_evidence=row['checks'], reward_evidence=row['checks'])
    result = lab.policy_value([row])
    assert result['estimate'] == .75 and result['row_effective_sample_size'] == 1
    assert not result['causal_claim']
    row['target_probabilities'] = {'inspect': 0, 'defer': 0, 'install': 1}
    assert lab.policy_value([row])['estimate'] is None
    row['policy_evidence'] = None
    with pytest.raises(ValueError, match='policy evidence'):
        lab.audit(value, tmp_path)


@pytest.mark.parametrize('attack', ['digest', 'traversal', 'symlink', 'missing'])
def test_evidence_trust_boundary(tmp_path, attack):
    value = packet(tmp_path)
    ref = value['runs'][0]['artifact']
    if attack == 'digest':
        ref['sha256'] = 'a' * 64
    elif attack == 'traversal':
        ref['path'] = '../private.txt'
    elif attack == 'symlink':
        (tmp_path / 'link').symlink_to(tmp_path / ref['path'])
        ref['path'] = 'link'
    else:
        ref['path'] = 'absent'
    with pytest.raises(ValueError):
        lab.audit(value, tmp_path)


def test_cli_freezes_then_audits_and_preserves_prior_reports(tmp_path):
    value = packet(tmp_path)
    (tmp_path / 'protocol.json').write_text(json.dumps(value['protocol']))
    (tmp_path / 'bundle.json').write_text(json.dumps(value))
    def call(*args):
        return subprocess.run([sys.executable, str(HERE / 'benefit_lab.py'), *args], capture_output=True, text=True)
    assert call('freeze', '--bundle', str(tmp_path / 'protocol.json'), '--output', str(tmp_path / 'frozen.json')).returncode == 0
    for row in value['runs']:
        row['observed_at'] = datetime.now(timezone.utc).isoformat()
    (tmp_path / 'bundle.json').write_text(json.dumps(value))
    args = ('audit', '--bundle', str(tmp_path / 'bundle.json'), '--frozen', str(tmp_path / 'frozen.json'), '--output', str(tmp_path / 'report.json'))
    assert call(*args).returncode == 0
    report = (tmp_path / 'report.json').read_bytes()
    assert (tmp_path / 'report.json').stat().st_mode & 0o777 == 0o600
    assert call(*args).returncode == 2 and (tmp_path / 'report.json').read_bytes() == report
    frozen = json.loads((tmp_path / 'frozen.json').read_text())
    frozen['protocol']['decision'] = 'changed'
    (tmp_path / 'frozen.json').write_text(json.dumps(frozen))
    assert call(*args[:-1], str(tmp_path / 'new.json')).returncode == 2
    assert not (tmp_path / 'new.json').exists()


def test_cli_cannot_retroactively_freeze_observed_trials(tmp_path):
    value = packet(tmp_path)
    (tmp_path / 'protocol.json').write_text(json.dumps(value['protocol']))
    (tmp_path / 'bundle.json').write_text(json.dumps(value))
    command = [sys.executable, str(HERE / 'benefit_lab.py')]
    assert subprocess.run(command + ['freeze', '--bundle', str(tmp_path / 'protocol.json'), '--output', str(tmp_path / 'frozen.json')], capture_output=True).returncode == 0
    result = subprocess.run(command + ['audit', '--bundle', str(tmp_path / 'bundle.json'), '--frozen', str(tmp_path / 'frozen.json'), '--output', str(tmp_path / 'report.json')], capture_output=True)
    assert result.returncode == 2 and not (tmp_path / 'report.json').exists()


def test_json_duplicate_keys_and_nonfinite_values_rejected(tmp_path):
    for text in ('{"x": 1, "x": 2}', '{"x": NaN}'):
        path = tmp_path / 'bad.json'
        path.write_text(text)
        with pytest.raises(ValueError):
            lab.read(path)


def test_policy_weights_handle_tiny_and_overflowing_probabilities(tmp_path):
    row = packet(tmp_path)['runs'][0]
    row.update(reward=.5, logging_probabilities={'inspect': .5, 'defer': .5, 'install': 0},
               target_probabilities={'inspect': 1e-320, 'defer': 1, 'install': 0})
    result = lab.policy_value([row])
    assert result['estimate'] == .5 and result['row_effective_sample_size'] == 1
    row['logging_probabilities'] = {'inspect': 1e-320, 'defer': 1, 'install': 0}
    row['target_probabilities'] = {'inspect': 1, 'defer': 0, 'install': 0}
    assert lab.policy_value([row])['reason'] == 'unstable_importance_weights'


def test_order_identity_and_duplicate_menus_are_explicit(tmp_path):
    value = packet(tmp_path)
    variant = deepcopy(value['protocol']['cases'][0])
    variant.update(id='rotation', pool='challenge', variant='order', parent='import')
    variant['action_order'] = ['defer', 'install', 'inspect']
    value['protocol']['cases'].append(variant)
    rebind(value)
    result = lab.audit(value, tmp_path)
    assert result['independent_groups'] == 2 and result['cases'] == 3
    assert lab.digest(variant) != lab.digest(value['protocol']['cases'][0])
    variant['action_order'] = ['inspect', 'inspect', 'defer']
    rebind(value)
    with pytest.raises(ValueError, match='each frozen action'):
        lab.audit(value, tmp_path)
    value = packet(tmp_path)
    case = value['protocol']['cases'][0]
    case['actions']['defer']['description'] = case['actions']['inspect']['description']
    rebind(value)
    assert lab.audit(value, tmp_path)['menus_and_context'][0]['duplicate_descriptions'] == 1


def test_source_input_and_arm_byte_drift_cannot_be_declared_away(tmp_path):
    for field in ('source_sha256', 'required_controls_sha256'):
        value = packet(tmp_path)
        value['protocol'][field] = 'c' * 64
        with pytest.raises(ValueError, match='source/control bytes'):
            lab.audit(value, tmp_path)
    for field in ('policy_sha256', 'question_sha256'):
        value = packet(tmp_path)
        value['protocol']['arms']['rules'][field] = 'c' * 64
        with pytest.raises(ValueError, match='policy/question bytes'):
            lab.audit(value, tmp_path)
    value = packet(tmp_path)
    value['protocol']['cases'][0]['context_sha256'] = 'c' * 64
    rebind(value)
    with pytest.raises(ValueError, match='input bytes'):
        lab.audit(value, tmp_path)


@pytest.mark.parametrize('field', ['context', 'prompt', 'rubric'])
def test_order_only_variant_cannot_change_input_semantics(tmp_path, field):
    value = packet(tmp_path)
    variant = deepcopy(value['protocol']['cases'][0])
    variant.update(id='rotation', pool='challenge', variant='order', parent='import')
    path = tmp_path / 'changed-input.txt'
    path.write_text('Synthetic changed input')
    variant['inputs'][field] = {'path': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    variant[field + '_sha256'] = variant['inputs'][field]['sha256']
    value['protocol']['cases'].append(variant)
    rebind(value)
    with pytest.raises(ValueError, match='changed semantics'):
        lab.audit(value, tmp_path)


def test_missing_context_sibling_is_not_hidden_by_review_group_deduplication(tmp_path):
    value = packet(tmp_path)
    first, second = value['protocol']['cases']
    second['group_sha256'] = first['group_sha256']
    second['brief']['missing_fact'] = 'Synthetic missing task constraint'
    rebind(value)
    result = lab.audit(value, tmp_path)
    assert len(result['review_candidates']) == 1
    assert len(result['context_diagnostics']) == 1
    assert result['context_diagnostics'][0]['case_sha256'] == lab.digest(second['id'])
