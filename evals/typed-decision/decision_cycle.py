#!/usr/bin/env python3
"""Recursive earned-authority cycle for the skill-fit decision (plan §4.6; invariants I5-I8).

An autoresearch-style loop with a fixed evaluator and a keep/discard ledger, and a sibling of (never an
edit to) pilot_cycle.py. It reads only <root> (default ~/.local/share/rhize/typed-decisions) and never
touches the workflow-v2 pilot paths under ~/.local/share/rhize/workflow-selection.

    decision_cycle.py run [--root DIR] [--now ISO] [--dry-run] [--seed S]

One run, in order:
  1. registry recovery (finishes an interrupted audited update);
  2. a fully labeled, unconsumed reserved cohort is tested once; a 'pass' while the mode is shadow or advise
     promotes skill-fit to cosign through the locked registry mutation path (actor 'cycle'). Only policy cosign-v1
     can ever be deployed, and only through a passed cohort bound to its policy/instrument/Laya hashes;
  3. in cosign, the demotion check runs and falls back to shadow when the quality, operational or
     (after the report-only window) latency trigger fires;
  4. in shadow or advise with no open cohort, a new cohort is reserved (labeling is the L2 labeler's job);
  5. report-only alternatives are scored on the scoreboard label pool with Horvitz-Thompson weights and
     session-cluster bootstrap 90% intervals. They are never deployed; a stricter router floor that beats
     both the incumbent and cosign-v1 becomes a recommendation string for code review;
  6. a cycle receipt <root>/skill-fit/cycles/<UTC timestamp>.json (0600) records every version hash, the
     actions taken and the report.

A pinned decision is report-only. --dry-run writes nothing and never calls the mutation path.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'rhize-context-manager' / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import typed_advice  # noqa: E402
import typed_promotion  # noqa: E402
from typed_decisions import advise_ledger, choice_labels, cohorts, contract, decision_registry, locked_io, records  # noqa: E402

DECISION = 'skill-fit'
RECEIPT_SCHEMA = 'rhize-typed-decision-cycle-receipt-v1'
POOL_STRATA = ('agreement', 'disagreement', 'silent_laya_pick')
SILENT_WEIGHT = 20          # silences are sampled 1 in 20 by the router
TAUS = (0.3, 0.4, 0.5)
FLOORS = (3.0, 3.5)
BOOTSTRAP_RESAMPLES = 2000
CI_LEVEL = 0.90
MIN_RECOMMEND_LABELS = 30
DEFAULT_SEED = 0            # fixed: the same data yields the same sample and the same intervals
CAVEAT = ('Report-only: nothing here is deployed. Labels are shortlist-constrained (no catalog-wide recall or '
          'silence-recovery claim); estimates are Horvitz-Thompson weighted with a session-cluster bootstrap.')


# ---------------------------------------------------------------- policies (report-only)

def _incumbent(rec):
    return rec['incumbent']['skillId'] if rec['incumbent'] else None


def _laya_ok(rec) -> bool:
    return rec['laya']['status'] == 'ok'


def _prob(rec, skill):
    """Laya's probability for `skill` ('none' included), or None when Laya did not answer or skill is unlisted."""
    if not _laya_ok(rec):
        return None
    shortlist = rec['shortlist']
    if skill == 'none':
        index = len(shortlist)
    elif skill in shortlist:
        index = shortlist.index(skill)
    else:
        return None
    return rec['laya']['probabilities'][index]


def policy_incumbent(rec):
    return _incumbent(rec)


def policy_floor(floor):
    def policy(rec):
        return _incumbent(rec) if rec['incumbent'] and rec['incumbent']['score'] >= floor else None
    return policy


def policy_cosign(rec):
    """cosign-v1; any Laya failure falls back to the incumbent exactly as the hook does (invariant I2)."""
    incumbent = _incumbent(rec)
    if incumbent is None or not _laya_ok(rec):
        return incumbent
    return incumbent if rec['laya']['choice'] == incumbent else None


def policy_cosign_tau(tau):
    def policy(rec):
        incumbent = _incumbent(rec)
        if incumbent is None or not _laya_ok(rec):
            return incumbent
        probability = _prob(rec, incumbent)
        return incumbent if probability is not None and probability >= tau else None
    return policy


def policy_veto_only(rec):
    incumbent = _incumbent(rec)
    if incumbent is not None and _laya_ok(rec) and rec['laya']['choice'] == 'none':
        return None
    return incumbent


def policy_swap(rec):
    incumbent = _incumbent(rec)
    if incumbent is not None and _laya_ok(rec) and rec['laya']['choice'] != incumbent:
        return None if rec['laya']['choice'] == 'none' else rec['laya']['choice']
    return incumbent


def policy_router_else_laya(tau):
    def policy(rec):
        incumbent = _incumbent(rec)
        if incumbent is not None:
            return incumbent
        if not _laya_ok(rec) or rec['laya']['choice'] == 'none':
            return None
        probability = _prob(rec, rec['laya']['choice'])
        return rec['laya']['choice'] if probability is not None and probability >= tau else None
    return policy


def policies() -> list:
    """(name, role, description, function). Every entry is report-only; role says how it relates to the deployment."""
    items = [('incumbent', 'baseline', 'router suggestion as shipped', policy_incumbent)]
    items += [(f'floor@{floor:g}', 'alternative', f'incumbent only when router score >= {floor:g}', policy_floor(floor))
              for floor in FLOORS]
    items += [('cosign-v1', 'deployable', 'incumbent iff Laya names the same skill (the only auto-deployable policy)',
               policy_cosign)]
    items += [(f'cosign@{tau:g}', 'alternative', f'incumbent iff its Laya probability >= {tau:g}', policy_cosign_tau(tau))
              for tau in TAUS]
    items += [('veto-only', 'alternative', 'suppress only when Laya answers none', policy_veto_only),
              ('swap', 'alternative', "show Laya's choice on disagreement", policy_swap)]
    items += [(f'router-else-laya@{tau:g}', 'alternative', f"on router silence show Laya's choice when p >= {tau:g}",
               policy_router_else_laya(tau)) for tau in TAUS]
    return items


# ---------------------------------------------------------------- Horvitz-Thompson + cluster bootstrap

def _percentile(sorted_values: list, q: float):
    if not sorted_values:
        return None
    position = q * (len(sorted_values) - 1)
    low = int(position)
    high = min(low + 1, len(sorted_values) - 1)
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (position - low)


def _interval(values: list):
    kept = sorted(v for v in values if v is not None)
    if len(kept) < len(values) / 2 or not kept:
        return None
    tail = (1 - CI_LEVEL) / 2
    return [round(_percentile(kept, tail), 6), round(_percentile(kept, 1 - tail), 6)]


def _precision_utility(hits, wrong, false_fires, lam):
    fires = hits + wrong + false_fires
    return (hits / fires) if fires > 0 else None, hits - lam * (wrong + false_fires)


def alternatives_report(recs: list, labels: list, lam: float, seed, instrument_sha256: str, mode: str,
                        resamples: int = BOOTSTRAP_RESAMPLES) -> dict:
    """Score every policy on the scoreboard label pool (cohortId None; strata agreement/disagreement/silent_laya_pick).

    weight = 1/inclusionProbability x 20 for records whose sourceStratum is 'silent_sample'. Hits, wrong and
    false fires are weighted sums; utility U = hits - lambda (wrong + false fires). Intervals are percentile
    intervals of a session-cluster bootstrap (random.Random(f'{seed}:bootstrap'), `resamples` draws).
    """
    by_key = {r['occurrenceKey']: r for r in recs}
    rows, seen, ambiguous, unmatched = [], set(), 0, 0
    for label in labels:
        key = label['occurrenceKey']
        if label['cohortId'] is not None or label['basis'] == 'harness' or label['stratum'] not in POOL_STRATA:
            continue
        if key in seen:
            continue
        seen.add(key)
        rec = by_key.get(key)
        if rec is None or rec['instrumentSha256'] != instrument_sha256:
            unmatched += 1
            continue
        if label['ambiguous']:
            ambiguous += 1
            continue
        weight = (1.0 / label['inclusionProbability']) * (SILENT_WEIGHT if rec['sourceStratum'] == 'silent_sample' else 1)
        rows.append((rec['sessionHash'], weight, rec, label))

    pol = policies()
    P = len(pol)
    base = {'status': 'ok' if rows else 'no_labels', 'caveat': CAVEAT, 'lambda': lam,
            'labels': {'used': len(rows), 'ambiguous': ambiguous, 'unmatched': unmatched,
                       'sessions': len({row[0] for row in rows}),
                       'layaRevisions': sorted({row[2]['layaRevision'] for row in rows})},
            'weights': {'silentSample': SILENT_WEIGHT},
            'bootstrap': {'unit': 'session', 'resamples': resamples, 'level': CI_LEVEL, 'seed': str(seed)},
            'alternatives': [], 'recommendations': [], 'ledger': []}
    if not rows:
        return base

    totals = [[0.0, 0.0, 0.0] for _ in range(P)]
    counts = [[0, 0, 0] for _ in range(P)]
    sessions: dict = {}
    for session, weight, rec, label in rows:
        vec = sessions.setdefault(session, [0.0] * (3 * P))
        for index, (_, _, _, fn) in enumerate(pol):
            score = contract.score_suggestion(fn(rec), label)
            slot = {'hit': 0, 'wrong': 1, 'false_fire': 2}.get(score)
            if slot is None:
                continue
            totals[index][slot] += weight
            counts[index][slot] += 1
            vec[3 * index + slot] += weight

    point = []
    for index in range(P):
        precision, utility = _precision_utility(*totals[index], lam)
        point.append((precision, utility))

    names = [p[0] for p in pol]
    inc_i, cos_i = names.index('incumbent'), names.index('cosign-v1')
    ordered = [sessions[s] for s in sorted(sessions)]
    rng = random.Random(f'{seed}:bootstrap')
    size = len(ordered)
    boot_u = [[] for _ in range(P)]
    boot_p = [[] for _ in range(P)]
    boot_dinc = [[] for _ in range(P)]
    boot_dcos = [[] for _ in range(P)]
    for _ in range(resamples):
        picks = rng.choices(range(size), k=size)
        sums = [sum(col) for col in zip(*[ordered[i] for i in picks])]
        utilities = []
        for index in range(P):
            precision, utility = _precision_utility(sums[3 * index], sums[3 * index + 1], sums[3 * index + 2], lam)
            boot_u[index].append(utility)
            boot_p[index].append(precision)
            utilities.append(utility)
        for index in range(P):
            boot_dinc[index].append(utilities[index] - utilities[inc_i])
            boot_dcos[index].append(utilities[index] - utilities[cos_i])

    alternatives = []
    for index, (name, role, description, _) in enumerate(pol):
        hits, wrong, false_fires = totals[index]
        precision, utility = point[index]
        alternatives.append({
            'name': name, 'role': role, 'status': 'report_only', 'description': description,
            'hits': round(hits, 6), 'wrong': round(wrong, 6), 'falseFires': round(false_fires, 6),
            'labeledFires': sum(counts[index]), 'precision': None if precision is None else round(precision, 6),
            'utility': round(utility, 6),
            'ci90': {'utility': _interval(boot_u[index]), 'precision': _interval(boot_p[index])},
            'deltaVsIncumbent': {'point': round(utility - point[inc_i][1], 6), 'ci90': _interval(boot_dinc[index])},
            'deltaVsCosign': {'point': round(utility - point[cos_i][1], 6), 'ci90': _interval(boot_dcos[index])}})

    recommendations, ledger = [], []
    for index, item in enumerate(alternatives):
        name = item['name']
        beats_both = utility_gt(point[index][1], point[inc_i][1]) and utility_gt(point[index][1], point[cos_i][1])
        if name == 'incumbent':
            verdict = 'baseline'
        elif name == 'cosign-v1':
            verdict = 'deployed' if mode == 'cosign' else 'pending_gate'
        elif beats_both and len(rows) >= MIN_RECOMMEND_LABELS and name.startswith('floor@'):
            floor = name.split('@', 1)[1]
            lows = [item['deltaVsIncumbent']['ci90'], item['deltaVsCosign']['ci90']]
            strength = 'supported' if all(ci and ci[0] > 0 for ci in lows) else 'tentative'
            recommendations.append(
                f'review raising the router score floor to {floor} ({strength}: utility {item["utility"]} vs incumbent '
                f'{alternatives[inc_i]["utility"]} and cosign-v1 {alternatives[cos_i]["utility"]} on {len(rows)} labels); '
                'report-only, change it through code review')
            verdict = 'recommend'
        elif beats_both:
            verdict = 'promising'
        else:
            verdict = 'discard'
        ledger.append({'candidate': name, 'verdict': verdict, 'utility': item['utility']})
    base.update({'alternatives': alternatives, 'recommendations': recommendations, 'ledger': ledger})
    return base


def utility_gt(a, b) -> bool:
    return a > b + 1e-12


# ---------------------------------------------------------------- the cycle

def _source_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _versions(entry, state, recs, registry) -> dict:
    policy_hash, instrument_hash = cohorts.deployable_hashes(entry)
    key = cohorts.current_key(entry, recs)
    latest = None
    if key is not None:
        matching = [r for r in recs if cohorts.key_of(r) == key]
        latest = max(matching, key=lambda r: locked_io.utc(r['ts']))
    scripts = REPO / 'rhize-context-manager' / 'scripts' / 'typed_decisions'
    return {'policySha256': policy_hash, 'instrumentSha256': instrument_hash,
            'layaRevision': key[2] if key else None,
            'routerSourceSha256': latest['routerSourceSha256'] if latest else None,
            'indexSha256': latest['indexSha256'] if latest else None,
            'registrySha256': hashlib.sha256(locked_io.canonical(registry).encode('utf-8')).hexdigest(),
            'registryRevision': state['revision'] if state else 0,
            'sources': {'decisionCycle': _source_sha256(Path(__file__)),
                        'cohorts': _source_sha256(scripts / 'cohorts.py'),
                        'decisionRegistry': _source_sha256(scripts / 'decision_registry.py')}}


def _try_mutate(root, registry, to_mode, reason, revision, binding, now, actions, kind):
    """Call the single mutation path; failures become recorded actions, never crashes."""
    try:
        new_state = decision_registry.mutate(root, DECISION, to_mode, actor='cycle', reason=reason,
                                             expected_revision=revision, binding=binding, now=now, registry=registry)
    except decision_registry.RegistryError as err:
        actions.append({'type': f'{kind}_failed', 'code': err.code})
        return None
    actions.append({'type': kind, 'toMode': to_mode, 'reason': reason, 'revision': new_state['revision'],
                    'cohortId': binding['cohortId'] if binding else None})
    return new_state


def run_cycle(root, now=None, dry_run: bool = False, seed=None, registry=None, advise: bool = True, probe=None) -> dict:
    root = Path(root)
    now = locked_io.utc(now)
    registry = registry if registry is not None else decision_registry.load_registry()
    seed = DEFAULT_SEED if seed is None else seed
    lock_fd = None
    if not dry_run:
        lock_fd = locked_io.try_lock(root / DECISION / 'cycle.lock')
        if lock_fd is None:
            return {'status': 'held', 'reason': 'cycle_busy', 'dryRun': False}
    try:
        result = _run(root, now, dry_run, seed, registry)
        if advise:
            result['advise'] = run_advise(root, now, dry_run, registry, probe)
        return result
    finally:
        locked_io.release_lock(lock_fd)


def _cohorts_ever_promoted(root) -> set:
    """Cohort ids that some committed mode change already bound to a cosign promotion (from audit intents)."""
    lines, _ = decision_registry.read_audit(root)
    committed = {line['revision'] for line in lines if line['phase'] == 'commit'}
    ids = set()
    for line in lines:
        if line['phase'] != 'intent' or line['revision'] not in committed or line['toMode'] != 'cosign':
            continue
        entry = ((line.get('state') or {}).get('decisions') or {}).get(DECISION) or {}
        if entry.get('cohortId'):
            ids.add(entry['cohortId'])
    return ids


def _run(root, now, dry_run, seed, registry) -> dict:
    entry = registry['decisions'][DECISION]
    actions = []
    registry_ready = True
    check = None

    if dry_run:
        lines, _ = decision_registry.read_audit(root)
        recovery = {'action': 'skipped_dry_run', 'pendingIntent': bool(lines) and lines[-1]['phase'] == 'intent'}
    else:
        try:
            recovery = decision_registry.recover(root, registry, now)
        except decision_registry.RegistryError as err:
            recovery = {'action': 'failed', 'code': err.code}
            registry_ready = False
        if recovery['action'] == 'blocked':
            registry_ready = False
    state, status = decision_registry.read_state(root, registry)
    laya_revision = records.laya_revision(root)
    mode = decision_registry.effective_mode(DECISION, registry, state, status, laya_revision)
    current = ((state or {}).get('decisions') or {}).get(DECISION)
    pinned = bool(current and current['pinned'])
    revision = state['revision'] if state else 0

    recs, invalid_records = cohorts.load_records(root)
    labels, invalid_labels = cohorts.load_labels(root)
    key = cohorts.current_key(entry, recs)
    policy_hash, instrument_hash = cohorts.deployable_hashes(entry)

    if status == 'corrupt':
        actions.append({'type': 'skipped', 'reason': 'state_corrupt'})
    elif not registry_ready:
        actions.append({'type': 'skipped', 'reason': 'registry_unavailable'})
    elif pinned:
        actions.append({'type': 'skipped', 'reason': 'pinned'})
    elif mode == 'off':
        actions.append({'type': 'skipped', 'reason': 'mode_off'})
    else:
        promoted_now = False
        flow = mode                      # what the remaining steps act on; a dry run plans without changing `mode`
        # advise and cosign are earned separately (plan §3, gates are per target mode): a skill-fit in advise
        # still reserves, evaluates and promotes cosign cohorts, exactly like shadow.
        cosign_attempts = ('shadow', 'advise')
        # 1b. a cosign state that no longer binds (policy/instrument changed by an update, or a new Laya
        # checkpoint) already reads as shadow in the hook; make the state say so, then re-gate from shadow.
        stale = decision_registry.binding_stale(DECISION, registry, current, laya_revision) if current else None
        if stale:
            if dry_run:
                actions.append({'type': 'would_demote', 'toMode': 'shadow', 'reason': stale})
            else:
                new_state = _try_mutate(root, registry, 'shadow', stale, revision, None, now, actions, 'demote')
                if new_state is not None:
                    state, revision, mode = new_state, new_state['revision'], 'shadow'
                    current = new_state['decisions'].get(DECISION)
            flow = 'shadow'
        # 2. test a fully labeled open cohort once; promote only a passed, current-key cohort
        if flow in cosign_attempts:
            applied = _cohorts_ever_promoted(root)
            for row in cohorts.cohort_table(root):
                # A passed cohort whose promotion never landed (stale revision, lock timeout) is applied now,
                # unless it already promoted once (a later demotion must not be undone by old evidence).
                retry_pass = (row['status'] == 'consumed' and row.get('verdict') == 'pass'
                              and row['cohortId'] not in applied and stale is None)
                if row['status'] != 'awaiting_evaluation' and not retry_pass:
                    continue
                cohort_key = (row['policySha256'], row['instrumentSha256'], row['layaRevision'])
                if (cohort_key != key or row['policySha256'] != policy_hash or row['instrumentSha256'] != instrument_hash
                        or row['layaRevision'] != laya_revision or laya_revision == 'unknown'):
                    # Only evidence from the checkpoint that is running now can grant authority.
                    actions.append({'type': 'skip_cohort', 'cohortId': row['cohortId'], 'reason': 'stale_key'})
                    continue
                if retry_pass:
                    result = {'status': 'consumed', 'verdict': 'pass', 'statistic': row.get('statistic'),
                              'key': {'policySha256': row['policySha256'], 'instrumentSha256': row['instrumentSha256'],
                                      'layaRevision': row['layaRevision']}}
                    actions.append({'type': 'retry_promotion', 'cohortId': row['cohortId']})
                else:
                    result = cohorts.evaluate(root, registry, row['cohortId'], now, dry_run=dry_run)
                    actions.append({'type': 'would_evaluate' if dry_run else 'evaluate', 'cohortId': row['cohortId'],
                                    'status': result['status'], 'verdict': result.get('verdict'),
                                    'statistic': result.get('statistic')})
                if result.get('verdict') != 'pass':
                    continue
                if dry_run:
                    actions.append({'type': 'would_promote', 'toMode': 'cosign', 'cohortId': row['cohortId']})
                    flow, promoted_now = 'cosign', True
                    break
                binding = {**result['key'], 'cohortId': row['cohortId']}
                new_state = _try_mutate(root, registry, 'cosign', 'gate_passed', revision, binding, now, actions, 'promote')
                if new_state is not None:
                    state, revision, mode, flow, promoted_now = new_state, new_state['revision'], 'cosign', 'cosign', True
                break
        # 3. demotion
        if flow == 'cosign' and not promoted_now:
            check = cohorts.demotion_check(root, registry, state, now)
            actions.append({'type': 'demotion_check', 'demote': check['demote'], 'reason': check['reason']})
            if check['demote']:
                if dry_run:
                    actions.append({'type': 'would_demote', 'toMode': 'shadow', 'reason': check['reason']})
                    flow = 'shadow'
                else:
                    new_state = _try_mutate(root, registry, 'shadow', check['reason'], revision, None, now,
                                            actions, 'demote')
                    if new_state is not None:
                        state, revision, mode, flow = new_state, new_state['revision'], 'shadow', 'shadow'
        # 4. reserve a new cohort while cosign is not yet earned
        if flow in cosign_attempts:
            result = cohorts.reserve(root, registry, now, seed, dry_run=dry_run)
            reserved = result['status'] in ('reserved', 'would_reserve')
            actions.append({'type': ('would_reserve' if dry_run else 'reserve') if reserved else 'reserve_held',
                            'status': result['status'],
                            **{k: result[k] for k in ('cohortId', 'attempt', 'alpha', 'reason', 'available', 'target',
                                                      'inclusionProbability') if k in result}})

    # 5. report-only alternatives and informational checks (never acted on)
    report = alternatives_report(recs, labels, entry['lambda'], seed, instrument_hash, mode)
    demotion_info = check
    if demotion_info is None and mode == 'cosign' and state is not None:
        demotion_info = cohorts.demotion_check(root, registry, state, now)

    receipt = {
        'schema': RECEIPT_SCHEMA, 'decision': DECISION, 'at': locked_io.iso(now), 'dryRun': dry_run, 'seed': str(seed),
        'versions': _versions(entry, state, recs, registry),
        'registry': {'status': status, 'revision': revision, 'mode': mode, 'pinned': pinned,
                     'since': current['since'] if current else None},
        'recovery': recovery, 'actions': actions,
        'cohorts': cohorts.cohort_table(root), 'demotion': demotion_info,
        'stats': cohorts.summarize_records(recs),
        'invalid': {'records': invalid_records, 'labels': invalid_labels},
        'report': report}
    receipt_file = None
    if not dry_run:
        receipt_file = _write_receipt(root, receipt)
    return {'status': 'ok', 'dryRun': dry_run, 'mode': mode, 'pinned': pinned,
            'actions': [a['type'] for a in actions], 'receipt': str(receipt_file) if receipt_file else None,
            'alternatives': len(report['alternatives']), 'recommendations': report['recommendations'],
            'cohorts': [{'cohortId': c['cohortId'], 'status': c['status'], 'verdict': c['verdict']}
                        for c in receipt['cohorts']],
            'full': receipt}


def _write_receipt(root, receipt: dict) -> Path:
    directory = locked_io.private_dir(Path(root) / DECISION / 'cycles')
    stamp = locked_io.utc(receipt['at']).strftime('%Y%m%dT%H%M%SZ')
    data = (json.dumps(receipt, sort_keys=True, indent=1, ensure_ascii=False) + '\n').encode('utf-8')
    for suffix in ['', *[f'_{n}' for n in range(1, 100)]]:
        path = directory / f'{stamp}{suffix}.json'
        try:
            locked_io.write_private_exclusive(path, data)
            return path
        except FileExistsError:
            continue
    raise RuntimeError('could not allocate a cycle receipt name')


# ---------------------------------------------------------------- advise (majority-baseline gate, plan §3, §8)

WORKFLOW_FIT = 'workflow-fit'               # pilot_cycle.py owns its gate
SKILL_ADVISE_POLICY = 'skill-fit-advise-v1'


def skill_advise_policy_sha256(instrument_sha256: str) -> str:
    """skill-fit has one fixed advise surface: the Node reader checks only instrument and Laya revision for it, so
    the binding's policy hash is this constant, not a per-surface question hash."""
    return hashlib.sha256((SKILL_ADVISE_POLICY + instrument_sha256).encode('utf-8')).hexdigest()


def _choice_rows(root, decision, instrument_sha, revision):
    """(policy hash, rows) for a generic decision: labelled, unambiguous cases of the current homogeneous cohort
    (the most recent record's policy, the entry's advise instrument, the running Laya revision)."""
    recs = choice_labels.read_choice_records(root, decision)
    if not recs:
        return None, []
    policy = recs[-1]['policySha256']
    labels = choice_labels.read_labels(root, decision)
    rows = []
    for rec in recs:
        label = labels.get(rec['decisionId'])
        if (label is None or label['ambiguous'] or rec['policySha256'] != policy or label['label'] not in rec['candidates']
                or rec['instrumentSha256'] != instrument_sha or rec['layaRevision'] != revision):
            continue
        rows.append({'id': rec['decisionId'], 'group': rec.get('groupSha256') or rec['decisionId'],
                     'label': label['label'], 'critical_if_wrong': rec['criticalIfWrong'], 'choice': rec['laya']['choice'],
                     'status': rec['laya']['status'], 'mode': rec['mode'], 'arm': rec['arm'], 'ts': rec['ts']})
    return policy, rows


def _skill_rows(root, instrument_sha, revision):
    recs, _ = cohorts.load_records(root)
    labels, _ = cohorts.load_labels(root)
    by_key = {}
    for label in labels:
        if label['basis'] != 'harness' and not label['ambiguous']:
            by_key.setdefault(label['occurrenceKey'], label)
    rows = []
    for rec in cohorts.gate_records(recs):
        label = by_key.get(rec['occurrenceKey'])
        if label is None or rec['instrumentSha256'] != instrument_sha or rec['layaRevision'] != revision:
            continue
        rows.append({'id': rec['occurrenceKey'], 'group': rec['sessionHash'], 'label': label['bestSkill'],
                     'critical_if_wrong': False, 'choice': rec['laya']['choice'], 'status': rec['laya']['status'],
                     'mode': rec['mode'], 'arm': rec['arm'], 'ts': rec['ts']})
    return skill_advise_policy_sha256(instrument_sha), sorted(rows, key=lambda r: (r['ts'], r['id']))


def _demote_check(root, registry, decision, cfg, critical, rows, saved, revision, now, dry_run):
    """Rolling live check of an earned advise on the latest labelled advise-arm treatment cases (plan §3.7)."""
    window = [r for r in rows if r['mode'] == 'advise' and r['arm'] == 'treatment']
    history, seen = typed_promotion.read_demotion_state(root, decision)
    latest = window[-cfg['demote']['window']:]
    ids = [r['id'] for r in latest]
    reserved = [e for e in advise_ledger.read(root, decision) if e['event'] == 'reserve' and e['cohortId'] == saved.get('cohortId')]
    outcome = typed_promotion.demotion(
        latest, len(set(ids) - seen), history, baseline=reserved[0].get('baseline') if reserved else None,
        critical=critical, window=cfg['demote']['window'], fresh_labels=cfg['demote']['freshLabels'],
        consecutive=cfg['demote']['consecutive'])
    return typed_promotion.demotion_result(
        root, registry, decision, outcome, ids, expected_revision=revision, now=now, dry_run=dry_run,
        reason='critical_miss' if outcome['reason'] == 'critical_miss' else 'gate_demote')


def _advise_one(root, registry, decision, state, status, revision_laya, now, dry_run, probe):
    entry = registry['decisions'][decision]
    cfg, critical = entry['advise'], entry['tier'] == 'critical'
    if status == 'corrupt':
        return {'status': 'held', 'reason': 'registry_state_corrupt'}
    saved = ((state or {}).get('decisions') or {}).get(decision) or {}
    mode, revision = saved.get('mode', entry['defaultMode']), state['revision'] if state else 0
    if saved.get('pinned'):
        return {'status': 'held', 'reason': 'pinned'}
    if mode in ('off', 'cosign'):
        return {'status': 'held', 'reason': 'mode_' + mode}
    if revision_laya == 'unknown':
        return {'status': 'held', 'reason': 'laya_revision_unknown'}
    instrument_sha = decision_registry.advise_instrument_sha256(cfg['instrument'])
    policy, rows = (_skill_rows(root, instrument_sha, revision_laya) if decision == DECISION
                    else _choice_rows(root, decision, instrument_sha, revision_laya))
    if mode == 'advise':
        bound = (decision_registry.effective_mode(decision, registry, state, status, revision_laya) == 'advise'
                 and saved.get('policySha256') == policy)
        if bound:
            return _demote_check(root, registry, decision, cfg, critical, rows, saved, revision, now, dry_run)
        # A stale binding already reads as shadow at runtime; say so in the state so the gate can earn it again.
        if dry_run:
            return {'status': 'held', 'reason': 'would_reset_stale_binding'}
        moved = typed_promotion.registry_mutate(root, registry, decision, 'shadow', 'binding_stale', revision, now=now)
        if moved['status'] != 'mutated':
            return {'status': 'held', 'reason': 'registry_refused', 'registry': moved}
        revision = moved['revision']
    tuning = [r['label'] for r in rows if typed_promotion.split_of(r['group']) == 'tuning']
    baseline = typed_promotion.majority(tuning)
    if baseline is None:
        return {'status': 'held', 'reason': 'no_tuning_cases', 'labelled': len(rows)}
    by_id = {r['id']: r for r in rows}

    def predict_one(case):
        row = by_id[case['id']]
        if row['status'] != 'ok':
            raise RuntimeError('laya_unavailable_when_recorded')
        return row['choice']

    probe = probe or (lambda: typed_advice.check_identity(entry.get('endpoint') or typed_advice.ENDPOINT))
    cases = [{k: r[k] for k in ('id', 'group', 'label', 'critical_if_wrong')} for r in rows]
    receipt = typed_promotion.run_attempt(
        root, decision, cases, policy_sha=policy, instrument_sha=instrument_sha, laya_revision=revision_laya,
        gate_cfg=cfg, prior={k: tuning.count(k) for k in set(tuning)}, baseline=baseline, critical=critical, now=now,
        dry_run=dry_run, predict_one=predict_one, probe=probe)
    if receipt['status'] == 'held':
        return {**receipt, 'earnedMode': 'shadow'}
    return typed_promotion.earned_result(
        root, registry, decision, receipt, policy_sha=policy, instrument_sha=instrument_sha, laya_revision=revision_laya,
        expected_revision=revision, now=now, dry_run=dry_run)


def run_advise(root, now=None, dry_run: bool = False, registry=None, probe=None) -> dict:
    """One advise pass over every decision with an `advise` entry except workflow-fit (pilot_cycle.py owns it):
    earn advise through the baseline gate, or run the rolling demotion check on an earned one. Laya's answers come
    from the stored choice records, so `probe` (Laya availability; default typed_advice.check_identity) only
    keeps an outage from consuming a cohort. Failures are recorded per decision, never raised."""
    root, now = Path(root), locked_io.utc(now)
    registry = registry if registry is not None else decision_registry.load_registry()
    state, status = decision_registry.read_state(root, registry)
    revision_laya = records.laya_revision(root)
    out = {}
    for decision, entry in registry['decisions'].items():
        if not entry.get('advise') or decision == WORKFLOW_FIT:
            continue
        try:
            out[decision] = _advise_one(root, registry, decision, state, status, revision_laya, now, dry_run, probe)
        except (decision_registry.RegistryError, OSError, ValueError) as err:
            out[decision] = {'status': 'held', 'reason': 'error', 'error': getattr(err, 'code', type(err).__name__)}
        if (out[decision].get('registry') or {}).get('status') == 'mutated':
            state, status = decision_registry.read_state(root, registry)   # a later decision sees the new revision
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Run one earned-authority cycle for skill-fit.')
    sub = parser.add_subparsers(dest='command', required=True)
    run = sub.add_parser('run', help='evaluate, promote/demote, reserve and report once')
    run.add_argument('--root', help='typed-decisions data root (default: RHIZE_TYPED_DECISIONS_ROOT or ~/.local/share/rhize/typed-decisions)')
    run.add_argument('--now', help='ISO-8601 time with timezone (default: now)')
    run.add_argument('--dry-run', action='store_true', help='compute everything, write nothing, call no mutation')
    run.add_argument('--no-advise', action='store_true', help='skip the advise pass (skill-fit cosign only)')
    run.add_argument('--seed', help='cohort sampling and bootstrap seed (default 0, so reruns on the same data agree)')
    args = parser.parse_args(argv)
    root = Path(args.root) if args.root else records.default_root()
    seed = None
    if args.seed is not None:
        seed = int(args.seed) if args.seed.lstrip('-').isdigit() else args.seed
    try:
        result = run_cycle(root, args.now, args.dry_run, seed, advise=not args.no_advise)
    except (OSError, ValueError, decision_registry.RegistryError) as err:
        print(json.dumps({'status': 'error', 'error': str(err)}, sort_keys=True))
        return 2
    summary = {key: value for key, value in result.items() if key != 'full'}
    print(json.dumps(summary, sort_keys=True, separators=(',', ':')))
    return 0


if __name__ == '__main__':
    sys.exit(main())
