#!/usr/bin/env python3
"""Read-only, development-only task benefit audits. No providers, execution or promotion."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re

from task_trials import outcome_from_file


HEX = re.compile(r'[0-9a-f]{64}\Z')
NAME = re.compile(r'[a-zA-Z0-9_-]{1,80}\Z')
TAX = ('prepare', 'schedule', 'queue', 'health', 'forward', 'decode', 'record', 'task')
VARIANTS = {'original', 'order', 'distractor', 'paraphrase', 'urgency', 'no_correct_action'}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def exact(value, fields):
    if not isinstance(value, dict) or set(value) != set(fields.split()):
        raise ValueError('unexpected evidence fields')


def number(value, low=0, high=float('inf'), nullable=True):
    if value is None and nullable:
        return
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError('invalid finite metric')


def sha(value, nullable=False):
    if value is None and nullable:
        return
    if not isinstance(value, str) or not HEX.fullmatch(value):
        raise ValueError('invalid SHA-256')


def name(value):
    if not isinstance(value, str) or not NAME.fullmatch(value):
        raise ValueError('invalid opaque identifier')


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError('invalid timestamp')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None or result.utcoffset().total_seconds() != 0:
        raise ValueError('timestamp must be UTC')
    return result


def brief_complete(case):
    brief = case['brief']
    return all(brief[key].strip() for key in ('intent', 'artifact', 'stage', 'constraints')) and not brief['missing_fact'].strip()


def read(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError('input must be a bounded regular file')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate JSON key')
            result[key] = value
        return result
    return json.loads(path.read_text(), object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def evidence(root, reference):
    """Verify bytes without printing private paths or including evidence text in reports."""
    if reference is None:
        return False
    exact(reference, 'path sha256')
    sha(reference['sha256'])
    relative = Path(reference['path'])
    if relative.is_absolute() or not relative.parts or any(p in ('.', '..') for p in relative.parts):
        raise ValueError('evidence must stay inside its private bundle')
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError('symlink evidence is forbidden')
    if not current.is_file() or current.stat().st_size > 4 * 1024 * 1024:
        raise ValueError('evidence unavailable or oversized')
    if hashlib.sha256(current.read_bytes()).hexdigest() != reference['sha256']:
        raise ValueError('evidence digest mismatch')
    return True


def protocol(value, root):
    exact(value, 'schema created_at decision source_sha256 required_controls_sha256 source_evidence required_controls_evidence arms cases')
    if value['schema'] != 'rhize-benefit-protocol-v1':
        raise ValueError('unsupported prospective protocol')
    created = timestamp(value['created_at'])
    if created > datetime.now(timezone.utc):
        raise ValueError('future protocol')
    name(value['decision'])
    sha(value['source_sha256'])
    sha(value['required_controls_sha256'])
    for field in ('source', 'required_controls'):
        if not evidence(root, value[field + '_evidence']) or value[field + '_evidence']['sha256'] != value[field + '_sha256']:
            raise ValueError('protocol source/control bytes do not match binding')
    arms = value['arms']
    if not isinstance(arms, dict) or not 2 <= len(arms) <= 12:
        raise ValueError('protocol needs 2..12 frozen arms')
    for key, arm in arms.items():
        name(key)
        exact(arm, 'mode policy_sha256 question_sha256 required_controls_sha256 context_mode question_kind observer policy_evidence question_evidence')
        if arm['mode'] not in ('baseline', 'rules', 'shadow', 'advice', 'holdback'):
            raise ValueError('invalid development arm')
        if (arm['context_mode'] not in ('original', 'brief') or arm['question_kind'] not in ('broad', 'concrete')
                or arm['observer'] not in ('on', 'off')):
            raise ValueError('invalid frozen experimental factors')
        for field in ('policy_sha256', 'question_sha256', 'required_controls_sha256'):
            sha(arm[field])
        for field in ('policy', 'question'):
            if not evidence(root, arm[field + '_evidence']) or arm[field + '_evidence']['sha256'] != arm[field + '_sha256']:
                raise ValueError('arm policy/question bytes do not match binding')
        if arm['required_controls_sha256'] != value['required_controls_sha256']:
            raise ValueError('mandatory controls differ between arms')
    if sum(a['mode'] == 'baseline' for a in arms.values()) != 1:
        raise ValueError('exactly one incumbent baseline required')
    cases = value['cases']
    if not isinstance(cases, list) or not 1 <= len(cases) <= 2400:
        raise ValueError('invalid case count')
    indexed, group_identity = {}, {}
    for case in cases:
        exact(case, 'id group_sha256 task_sha256 fixture_sha256 context_sha256 prompt_sha256 '
                    'session_sha256 rubric_sha256 pool variant parent brief actions action_order review inputs')
        name(case['id'])
        if case['id'] in indexed:
            raise ValueError('duplicate case identity')
        for field in ('group_sha256', 'task_sha256', 'fixture_sha256', 'context_sha256',
                      'prompt_sha256', 'session_sha256', 'rubric_sha256'):
            sha(case[field])
        exact(case['inputs'], 'task fixture context prompt session rubric')
        for field, reference in case['inputs'].items():
            if not evidence(root, reference) or reference['sha256'] != case[field + '_sha256']:
                raise ValueError('case input bytes do not match binding')
        if case['pool'] not in ('representative', 'challenge') or case['variant'] not in VARIANTS:
            raise ValueError('invalid sampling pool or variant')
        if case['variant'] != 'original' and case['pool'] != 'challenge':
            raise ValueError('variants belong in the challenge pool')
        brief = case['brief']
        exact(brief, 'intent artifact stage constraints missing_fact')
        if any(not isinstance(v, str) or len(v) > 2000 for v in brief.values()):
            raise ValueError('brief fields must be bounded strings')
        actions = case['actions']
        if not isinstance(actions, dict) or not 1 <= len(actions) <= 30:
            raise ValueError('invalid frozen menu')
        order = case['action_order']
        if not isinstance(order, list) or len(order) != len(actions) or any(not isinstance(k, str) for k in order) or set(order) != set(actions):
            raise ValueError('order must contain each frozen action exactly once')
        for action, item in actions.items():
            name(action)
            exact(item, 'description utility')
            if not isinstance(item['description'], str) or not item['description'].strip() or len(item['description']) > 2000:
                raise ValueError('invalid action description')
            number(item['utility'], -1, 1, nullable=False)
        exact(case['review'], 'case_sha256 reviewer evidence')
        name(case['review']['reviewer'])
        if case['review']['case_sha256'] != digest({k: v for k, v in case.items() if k != 'review'}):
            raise ValueError('review does not bind exact case/menu/utility')
        if not evidence(root, case['review']['evidence']):
            raise ValueError('review evidence required')
        indexed[case['id']] = case
        # Shared task/session/prompt identities cannot be presented as independent groups.
        for field in ('task_sha256', 'session_sha256', 'prompt_sha256'):
            key = (field, case[field])
            if key in group_identity and group_identity[key] != case['group_sha256']:
                raise ValueError('related cases split across independent groups')
            group_identity[key] = case['group_sha256']
    for case in cases:
        parent = indexed.get(case['parent'])
        if case['variant'] == 'original':
            if case['parent'] is not None:
                raise ValueError('original case cannot have a parent')
        elif (parent is None or parent['variant'] != 'original'
              or any(case[k] != parent[k] for k in ('group_sha256', 'task_sha256', 'fixture_sha256', 'session_sha256'))):
            raise ValueError('variant must retain original task/group binding')
        if case['variant'] == 'order' and any(case[k] != parent[k] for k in ('actions', 'brief', 'context_sha256', 'prompt_sha256', 'rubric_sha256')):
            raise ValueError('order variant changed semantics')
    return indexed


def runs(value, frozen, root):
    if not isinstance(value, list) or len(value) > 10000:
        raise ValueError('invalid run count')
    cases = {c['id']: c for c in frozen['cases']}
    seen, acceptance_bases = set(), {}
    for row in value:
        exact(row, 'id case arm protocol_sha256 observed_at status selected proposed confidence '
                   'exposure following artifact checks acceptance rework correction wall_ms tax_ms '
                   'reward logging_probabilities target_probabilities outcome policy_evidence reward_evidence')
        name(row['id'])
        if row['id'] in seen or row['case'] not in cases or row['arm'] not in frozen['arms']:
            raise ValueError('duplicate or foreign run identity')
        seen.add(row['id'])
        observed = timestamp(row['observed_at'])
        if row['protocol_sha256'] != digest(frozen) or not timestamp(frozen['created_at']) <= observed <= datetime.now(timezone.utc):
            raise ValueError('run is not bound to prospective protocol')
        if row['status'] not in ('completed', 'failed', 'incomplete'):
            raise ValueError('invalid run status')
        case = cases[row['case']]
        for field in ('selected', 'proposed'):
            if row[field] is not None and (not isinstance(row[field], str) or row[field] not in case['actions']):
                raise ValueError('action outside frozen menu')
        number(row['confidence'], 0, 1)
        if row['exposure'] not in ('shown', 'holdback', 'not_shown', 'unknown') or row['following'] not in ('followed', 'overrode', 'unknown'):
            raise ValueError('invalid advice exposure')
        if row['following'] != 'unknown' and (row['exposure'] != 'shown' or row['proposed'] is None or row['selected'] is None
                or (row['selected'] == row['proposed']) != (row['following'] == 'followed')):
            raise ValueError('following contradicts observed actions')
        if frozen['arms'][row['arm']]['mode'] in ('baseline', 'shadow', 'holdback') and row['exposure'] == 'shown':
            raise ValueError('nonintervention arm exposed advice')
        for field in ('artifact', 'checks', 'correction', 'outcome', 'policy_evidence', 'reward_evidence'):
            evidence(root, row[field])
        acceptance = row['acceptance']
        exact(acceptance, 'value reviewer evidence')
        if acceptance['value'] not in ('accepted', 'rejected', 'undetermined'):
            raise ValueError('invalid explicit acceptance')
        present = evidence(root, acceptance['evidence'])
        if acceptance['value'] != 'undetermined':
            name(acceptance['reviewer'])
            if not present:
                raise ValueError('explicit acceptance needs reviewer evidence')
            answer = read(root / acceptance['evidence']['path'])
            exact(answer, 'schema case arm protocol_sha256 artifact_sha256 outcome reviewer recorded_at basis')
            expected_artifact = row['artifact']['sha256'] if row['artifact'] else None
            if (answer['schema'] != 'rhize-benefit-acceptance-v1' or answer['case'] != row['case']
                    or answer['arm'] != row['arm'] or answer['protocol_sha256'] != row['protocol_sha256']
                    or answer['artifact_sha256'] != expected_artifact or answer['outcome'] != acceptance['value']
                    or answer['reviewer'] != acceptance['reviewer']
                    or answer['basis'] not in ('human', 'independent_model', 'fixture')
                    or not observed <= timestamp(answer['recorded_at']) <= datetime.now(timezone.utc)):
                raise ValueError('acceptance evidence identity mismatch')
            acceptance_bases[row['id']] = answer['basis']
        elif acceptance['reviewer'] is not None or present:
            raise ValueError('unknown acceptance cannot carry an adjudication')
        if acceptance['value'] == 'accepted' and (row['status'] != 'completed' or row['artifact'] is None or row['checks'] is None):
            raise ValueError('accepted task needs completed artifact/check evidence')
        if row['outcome'] is not None:
            outcome, _ = outcome_from_file(root / row['outcome']['path'], acceptance['value'])
            if outcome['rubric_sha256'] != case['rubric_sha256'] or outcome['rework_count'] != row['rework']:
                raise ValueError('outcome rubric/rework mismatch')
        elif acceptance['value'] == 'accepted':
            raise ValueError('accepted task needs existing task outcome contract')
        if row['rework'] is not None and (type(row['rework']) is not int or row['rework'] < 0):
            raise ValueError('invalid rework count')
        number(row['wall_ms'])
        if not isinstance(row['tax_ms'], dict) or set(row['tax_ms']) != set(TAX):
            raise ValueError('all disjoint timing stages required, unknowns null')
        for item in row['tax_ms'].values():
            number(item)
        if row['wall_ms'] is not None and sum(x for x in row['tax_ms'].values() if x is not None) > row['wall_ms'] + .001:
            raise ValueError('overlapping timing components exceed wall time')
        number(row['reward'], 0, 1)
        if row['reward'] is not None and row['reward_evidence'] is None:
            raise ValueError('reward needs source evidence')
        for field in ('logging_probabilities', 'target_probabilities'):
            probabilities = row[field]
            if probabilities is None:
                continue
            if not isinstance(probabilities, dict) or set(probabilities) != set(case['actions']):
                raise ValueError('policy distribution must cover exact frozen menu')
            for item in probabilities.values():
                number(item, 0, 1, nullable=False)
            if not math.isclose(sum(probabilities.values()), 1, abs_tol=1e-8):
                raise ValueError('policy probabilities must sum to one')
            if row['policy_evidence'] is None:
                raise ValueError('propensities need logging/target policy evidence')
    return acceptance_bases


def policy_value(rows):
    """Self-normalized IPS diagnostic; logging probabilities are operator evidence, not inferred."""
    if not rows or any(r['selected'] is None or r['reward'] is None or r['logging_probabilities'] is None
                       or r['target_probabilities'] is None for r in rows):
        return {'status': 'held', 'reason': 'missing_rewards_actions_or_propensities', 'estimate': None}
    if any(any(p > 0 and r['logging_probabilities'][a] <= 0 for a, p in r['target_probabilities'].items())
           or r['logging_probabilities'][r['selected']] <= 0 for r in rows):
        return {'status': 'held', 'reason': 'target_policy_lacks_logged_support', 'estimate': None}
    weights = [r['target_probabilities'][r['selected']] / r['logging_probabilities'][r['selected']] for r in rows]
    if any(not math.isfinite(w) for w in weights):
        return {'status': 'held', 'reason': 'unstable_importance_weights', 'estimate': None}
    scale = max(weights)
    weights = [w / scale for w in weights] if scale else weights
    total = sum(weights)
    return {'status': 'descriptive' if total else 'held', 'reason': 'operator_reported_logging_policy',
            'estimate': sum(w * r['reward'] for w, r in zip(weights, rows)) / total if total else None,
            'row_effective_sample_size': (total / math.sqrt(sum(w * w for w in weights))) ** 2 if total else 0,
            'causal_claim': False}


def audit(packet, root):
    exact(packet, 'schema protocol runs judge_anchors cache_bindings')
    if packet['schema'] != 'rhize-benefit-bundle-v1':
        raise ValueError('unsupported development bundle')
    frozen = packet['protocol']
    cases = protocol(frozen, root)
    acceptance_bases = runs(packet['runs'], frozen, root)
    rows = packet['runs']
    by_arm, review_queue, grouped = {}, {}, defaultdict(list)
    diagnostics = [{'case_sha256': digest(c['id']), 'group_sha256': c['group_sha256'],
                    'pool': c['pool'], 'context_complete': False, 'reasons': ['context_gap'], 'priority': None}
                   for c in cases.values() if not brief_complete(c)]
    for arm in frozen['arms']:
        selected = [r for r in rows if r['arm'] == arm]
        wall = [r['wall_ms'] for r in selected]
        totals = {stage: sum(r['tax_ms'][stage] for r in selected) if selected and all(r['tax_ms'][stage] is not None for r in selected) else None for stage in TAX}
        wall_total = sum(wall) if wall and all(x is not None for x in wall) else None
        residual = max(0, wall_total - sum(totals.values())) if wall_total is not None and all(x is not None for x in totals.values()) else None
        by_arm[arm] = {'attempts': len(selected), 'statuses': dict(Counter(r['status'] for r in selected)),
                       'missing_cases': len(set(cases) - {r['case'] for r in selected}),
                       'acceptance': dict(Counter(r['acceptance']['value'] for r in selected)),
                       'acceptance_bases': dict(Counter(acceptance_bases[r['id']] for r in selected if r['id'] in acceptance_bases)),
                       'exposure': dict(Counter(r['exposure'] for r in selected)),
                       'following': dict(Counter(r['following'] for r in selected)),
                       'wall_ms': wall_total, 'unattributed_ms': residual,
                       'tax_ms': totals, 'timing_complete': residual is not None and residual <= .001,
                       'missing_artifacts': sum(r['artifact'] is None for r in selected),
                       'missing_checks': sum(r['checks'] is None for r in selected)}
        proposals = [cases[r['case']]['actions'][r['proposed']]['utility'] for r in selected if r['proposed'] is not None]
        by_arm[arm]['proposal_diagnostics'] = {'n': len(proposals), 'positive_judged_utility': sum(v > 0 for v in proposals),
                                              'basis': 'frozen rubric; no executed-task outcome attribution'}
        for row in selected:
            case = cases[row['case']]
            utility = case['actions'][row['selected']]['utility'] if row['selected'] is not None else None
            best = max(a['utility'] for a in case['actions'].values())
            regret = best - utility if utility is not None else None
            grouped[case['id'], arm].append(utility)
            reasons = [key for key, condition in (('correction', row['correction'] is not None), ('rework', row['rework']),
                       ('overrode', row['following'] == 'overrode'), ('regret', regret is not None and regret > 0),
                       ('unresolved_action', row['selected'] is None), ('nonterminal_or_failed', row['status'] != 'completed')) if condition]
            complete = brief_complete(case)
            if reasons and complete:
                item = {'case_sha256': digest(case['id']), 'group_sha256': case['group_sha256'],
                        'pool': case['pool'], 'context_complete': complete, 'reasons': reasons,
                        'priority': regret * (1 - row['confidence']) if complete and regret is not None and row['confidence'] is not None else None}
                key = (case['pool'], case['group_sha256'])
                previous = review_queue.get(key)
                if previous is not None:
                    item['reasons'] = sorted(set(item['reasons'] + previous['reasons']))
                if previous is None or (item['priority'] or 0) > (previous['priority'] or 0):
                    review_queue[key] = item
                else:
                    previous['reasons'] = item['reasons']
    utility = []
    baseline = next(k for k, v in frozen['arms'].items() if v['mode'] == 'baseline')
    for pool in ('representative', 'challenge'):
        expected = defaultdict(list)
        for case in cases.values():
            if case['pool'] == pool:
                expected[case['group_sha256']].append(case['id'])
        for arm in frozen['arms']:
            values, pairs = [], []
            for identities in expected.values():
                items = [grouped.get((identity, arm), []) for identity in identities]
                if any(not items_for_case or any(x is None for x in items_for_case) for items_for_case in items):
                    continue
                score = sum(sum(v) / len(v) for v in items) / len(items)
                values.append(score)
                control = [grouped.get((identity, baseline), []) for identity in identities]
                if all(v and all(x is not None for x in v) for v in control):
                    pairs.append(score - sum(sum(v) / len(v) for v in control) / len(control))
            utility.append({'pool': pool, 'arm': arm, 'scored_groups': len(values),
                            'expected_groups': len(expected), 'unresolved_groups': len(expected) - len(values),
                            'evaluated_action': 'selected_executed',
                            'mean_judged_utility': sum(values) / len(values) if values else None,
                            'paired_groups': len(pairs), 'delta_from_baseline': sum(pairs) / len(pairs) if pairs else None})
    anchors = packet['judge_anchors']
    if not isinstance(anchors, list) or len(anchors) > 2400:
        raise ValueError('invalid judge anchors')
    anchor_ids = set()
    for anchor in anchors:
        exact(anchor, 'id artifact expected observed reviewer evidence blinding')
        name(anchor['id'])
        name(anchor['reviewer'])
        if anchor['id'] in anchor_ids or type(anchor['expected']) is not bool or type(anchor['observed']) is not bool:
            raise ValueError('duplicate or invalid judge anchor')
        anchor_ids.add(anchor['id'])
        if not all(evidence(root, anchor[k]) for k in ('artifact', 'evidence', 'blinding')):
            raise ValueError('anchor requires artifact, independent answer and blinding evidence')
    caches = packet['cache_bindings']
    if not isinstance(caches, list) or len(caches) > 2400:
        raise ValueError('invalid cache bindings')
    cache_report = []
    for cache in caches:
        exact(cache, 'case arm source_sha256 policy_sha256 question_sha256 context_sha256 fixture_sha256 menu_sha256 evidence')
        if cache['case'] not in cases or cache['arm'] not in frozen['arms']:
            raise ValueError('foreign cache binding')
        case = cases[cache['case']]
        valid = (cache['source_sha256'] == frozen['source_sha256']
                 and cache['policy_sha256'] == frozen['arms'][cache['arm']]['policy_sha256']
                 and cache['question_sha256'] == frozen['arms'][cache['arm']]['question_sha256']
                 and cache['fixture_sha256'] == case['fixture_sha256']
                 and cache['context_sha256'] == case['context_sha256']
                 and cache['menu_sha256'] == digest({'actions': case['actions'], 'action_order': case['action_order']}))
        if not evidence(root, cache['evidence']):
            raise ValueError('cache evidence required')
        cache_report.append({'case_sha256': digest(cache['case']), 'binding_valid': valid,
                             'live_reuse_authorized': False})
    menus = []
    for case in cases.values():
        descriptions = [a['description'].strip().casefold() for a in case['actions'].values()]
        menus.append({'case_sha256': digest(case['id']), 'duplicate_descriptions': len(descriptions) - len(set(descriptions)),
                      'acceptable_actions': sum(a['utility'] > 0 for a in case['actions'].values()),
                      'variant': case['variant'], 'pool': case['pool'],
                      'context_complete': brief_complete(case)})
    return {'schema': 'rhize-benefit-report-v1', 'protocol_sha256': digest(frozen), 'bundle_sha256': digest(packet),
            'basis': 'operator_supplied_development_evidence', 'live_authority': 'unchanged',
            'native_binding_verified': False, 'prospective_chronology_basis': 'operator_supplied_timestamps',
            'cases': len(cases), 'independent_groups': len({c['group_sha256'] for c in cases.values()}),
            'by_arm': by_arm, 'judged_action_utility': utility,
            'review_candidates': sorted(review_queue.values(), key=lambda r: (r['priority'] is None, -(r['priority'] or 0), r['case_sha256'])),
            'context_diagnostics': diagnostics,
            'menus_and_context': menus, 'cache_bindings': cache_report,
            'judge_audit': {'anchors': len(anchors), 'disagreements': sum(a['expected'] != a['observed'] for a in anchors),
                            'false_accepts': sum(not a['expected'] and a['observed'] for a in anchors),
                            'verified_blindness': False},
            'offline_policy': [{'pool': pool, 'arm': arm, **policy_value([r for r in rows if r['arm'] == arm and cases[r['case']]['pool'] == pool])}
                               for pool in ('representative', 'challenge') for arm in frozen['arms']],
            'claim_scope': 'development diagnostics; judged utility is not task acceptance or causal benefit; no promotion'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('freeze', 'audit'))
    parser.add_argument('--bundle', type=Path, required=True, help='protocol JSON for freeze; bundle JSON for audit')
    parser.add_argument('--frozen', type=Path, help='independently preserved protocol; required for audit')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.output.exists() or args.output.is_symlink():
            raise ValueError('output already exists')
        value = read(args.bundle)
        if args.command == 'freeze':
            if args.frozen:
                raise ValueError('freeze does not accept an existing protocol')
            protocol(value, args.bundle.resolve().parent)
            result = {'schema': 'rhize-frozen-benefit-protocol-v1', 'protocol': value, 'protocol_sha256': digest(value),
                      'frozen_at': datetime.now(timezone.utc).isoformat()}
        else:
            if args.frozen is None:
                raise ValueError('audit needs separately frozen protocol')
            frozen = read(args.frozen)
            exact(frozen, 'schema protocol protocol_sha256 frozen_at')
            if (frozen['schema'] != 'rhize-frozen-benefit-protocol-v1' or frozen['protocol_sha256'] != digest(frozen['protocol'])
                    or frozen['protocol_sha256'] != digest(value['protocol'])):
                raise ValueError('frozen protocol drift')
            sealed_at = timestamp(frozen['frozen_at'])
            if not timestamp(frozen['protocol']['created_at']) <= sealed_at <= datetime.now(timezone.utc) or any(timestamp(r['observed_at']) < sealed_at for r in value['runs']):
                raise ValueError('trial predates separately frozen protocol')
            result = audit(value, args.bundle.resolve().parent)
        encoded = json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + '\n'
        with os.fdopen(os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as handle:
            handle.write(encoded)
        print(json.dumps({'status': 'completed', 'report_sha256': hashlib.sha256(encoded.encode()).hexdigest(),
                          'claim_scope': 'development only; no execution or promotion'}))
        return 0
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
        print(json.dumps({'status': 'unavailable', 'reason_code': type(exc).__name__}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
