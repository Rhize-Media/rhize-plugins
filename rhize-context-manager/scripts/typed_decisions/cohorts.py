"""Frozen single-use statistical gate for skill-fit authority (plan §4.6, invariant I7/I8).

A cohort is reserved once under a frozen policy (`reserve`), labeled elsewhere (L2 labeler), and tested
exactly once (`evaluate`). The test is the one-sided exact Clopper-Pearson lower bound on p, the share of
disagreement cases in which the incumbent suggestion is not a hit, against 1/(1+lambda). Attempt k spends
alpha_base * 2**-(k-1). `demotion_check` is the reverse test for a deployed `cosign` mode.

Ledger events live in <root>/skill-fit/cohorts/<day>.jsonl (typed_decisions.records). Sidecars:
  <root>/skill-fit/cohort-meta/<cohortId>.json   inclusion probability of the reservation (labeler input)
  <root>/skill-fit/receipts/<cohortId>.json      full receipt; its sha256 is in the consumed event

Stdlib only. Never reads or writes outside <root>.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
from collections import Counter
from datetime import timedelta
from pathlib import Path

from typed_decisions import contract, instrument, records
from typed_decisions.locked_io import (
    canonical, file_lock, iso, read_json_file, utc, write_private_atomic, write_private_exclusive)

DECISION = 'skill-fit'
GATE_STRATUM = 'disagreement'
FAIL_SCORES = ('wrong', 'false_fire')
OPERATIONAL_FAILURES = ('unavailable', 'invalid', 'identity_failed', 'redirect_refused')
QUALITY_WINDOW_DAYS = 14
# A demotion costs a whole new cohort (and halves the next alpha), so operational and latency triggers
# need a minimum sample; an outage still trips them within hours at ~150 fires a day.
MIN_OPERATIONAL_RECORDS = 20
MIN_ALPHA = 1e-9
META_SCHEMA = 'rhize-typed-decision-cohort-meta-v1'
RECEIPT_SCHEMA = 'rhize-typed-decision-cohort-receipt-v1'


# ---------------------------------------------------------------- exact binomial bounds

def _log_pmf(k: int, n: int, p: float) -> float:
    return (math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)
            + k * math.log(p) + (n - k) * math.log1p(-p))


def _upper_tail(x: int, n: int, p: float) -> float:
    """P(X >= x) for X ~ Binomial(n, p)."""
    if x <= 0:
        return 1.0
    if x > n or p <= 0.0:
        return 0.0
    if p >= 1.0:
        return 1.0
    return min(1.0, math.fsum(math.exp(_log_pmf(k, n, p)) for k in range(x, n + 1)))


def _lower_tail(x: int, n: int, p: float) -> float:
    """P(X <= x) for X ~ Binomial(n, p)."""
    if x < 0 or p >= 1.0 and x < n:
        return 0.0
    if x >= n or p <= 0.0:
        return 1.0
    return min(1.0, math.fsum(math.exp(_log_pmf(k, n, p)) for k in range(0, x + 1)))


def _check_counts(x, n, alpha):
    if isinstance(x, bool) or isinstance(n, bool) or not isinstance(x, int) or not isinstance(n, int):
        raise ValueError('x and n must be integers')
    if n < 0 or not 0 <= x <= n:
        raise ValueError('need 0 <= x <= n')
    if isinstance(alpha, bool) or not isinstance(alpha, (int, float)) or not 0 < alpha < 1:
        raise ValueError('alpha must be in (0, 1)')


def cp_lower(x: int, n: int, alpha: float) -> float:
    """One-sided exact Clopper-Pearson lower confidence bound at level 1-alpha: the p with P(X>=x|p)=alpha."""
    _check_counts(x, n, alpha)
    if x == 0:
        return 0.0
    lo, hi = 0.0, 1.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if _upper_tail(x, n, mid) < alpha:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-13:
            break
    return (lo + hi) / 2


def cp_upper(x: int, n: int, alpha: float) -> float:
    """One-sided exact Clopper-Pearson upper confidence bound at level 1-alpha: the p with P(X<=x|p)=alpha."""
    _check_counts(x, n, alpha)
    if x == n:
        return 1.0
    lo, hi = 0.0, 1.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if _lower_tail(x, n, mid) > alpha:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-13:
            break
    return (lo + hi) / 2


clopper_pearson_lower = cp_lower
clopper_pearson_upper = cp_upper


def alpha_for_attempt(alpha_base: float, k: int) -> float:
    """Alpha spending: attempt k (1-based) tests at alpha_base * 2**-(k-1); the total stays below 2*alpha_base."""
    if isinstance(k, bool) or not isinstance(k, int) or k < 1:
        raise ValueError('attempt must be an integer >= 1')
    return alpha_base * 2.0 ** -(k - 1)


def threshold_for(lam: float) -> float:
    """co-sign improves utility exactly when p > 1/(1+lambda)."""
    return 1.0 / (1.0 + lam)


# ---------------------------------------------------------------- shared readers

def skill_dir(root) -> Path:
    return Path(root) / DECISION


def meta_path(root, cohort_id: str) -> Path:
    return skill_dir(root) / 'cohort-meta' / f'{cohort_id}.json'


def receipt_path(root, cohort_id: str) -> Path:
    return skill_dir(root) / 'receipts' / f'{cohort_id}.json'


def load_records(root) -> tuple[list[dict], int]:
    """All valid skill-fit records (live + backfill), first-per-occurrence."""
    items, invalid = records.read(Path(root), DECISION, 'records')
    return records.dedupe_by_occurrence(items), invalid


def load_labels(root) -> tuple[list[dict], int]:
    return records.read(Path(root), DECISION, 'labels')


def key_of(obj: dict) -> tuple[str, str, str]:
    """The (policySha256, instrumentSha256, layaRevision) evidence key of a record or reserve event."""
    return obj['policySha256'], obj['instrumentSha256'], obj['layaRevision']


def deployable_hashes(entry: dict) -> tuple[str, str]:
    policy = entry.get('deployablePolicy')
    if policy != contract.POLICY_COSIGN:
        raise ValueError('only cosign-v1 is deployable')
    return contract.policy_sha256(policy), instrument.instrument_sha256()


def current_key(entry: dict, recs: list[dict]):
    """Evidence key of the most recent record that matches the deployable policy and instrument."""
    policy_hash, instrument_hash = deployable_hashes(entry)
    best, best_t = None, None
    for rec in recs:
        if rec['policySha256'] != policy_hash or rec['instrumentSha256'] != instrument_hash:
            continue
        t = utc(rec['ts'])
        if best_t is None or t >= best_t:
            best, best_t = rec, t
    return None if best is None else key_of(best)


def cohort_ledger(root) -> dict:
    """cohortId -> {'reserve': event, 'labeled': event|None, 'consumed': event|None}, in reservation order.

    The first event of each kind wins; events for unknown cohorts are ignored.
    """
    events, _ = records.read(Path(root), DECISION, 'cohorts')
    ledger: dict = {}
    for event in events:
        if event['event'] == 'reserve':
            ledger.setdefault(event['cohortId'], {'reserve': event, 'labeled': None, 'consumed': None})
    for event in events:
        item = ledger.get(event['cohortId'])
        if item is None or event['event'] == 'reserve':
            continue
        if item[event['event']] is None:
            item[event['event']] = event
    return ledger


def cohort_labels(labels: list[dict], reserve: dict) -> dict:
    """occurrenceKey -> first label tagged with this cohort, restricted to the reserved keys."""
    wanted = set(reserve['occurrenceKeys'])
    found: dict = {}
    for label in labels:
        if label['cohortId'] == reserve['cohortId'] and label['occurrenceKey'] in wanted:
            found.setdefault(label['occurrenceKey'], label)
    return found


def cohort_progress(root, cohort_id: str, ledger: dict | None = None, labels: list[dict] | None = None) -> dict:
    ledger = ledger if ledger is not None else cohort_ledger(root)
    item = ledger.get(cohort_id)
    if item is None:
        return {'reserved': 0, 'labeled': 0, 'complete': False}
    labels = labels if labels is not None else load_labels(root)[0]
    found = cohort_labels(labels, item['reserve'])
    reserved = len(item['reserve']['occurrenceKeys'])
    return {'reserved': reserved, 'labeled': len(found), 'complete': len(found) == reserved}


def cohort_table(root) -> list[dict]:
    """Compact per-cohort status rows (hashes and counts only) for the cycle receipt and scoreboard."""
    ledger = cohort_ledger(root)
    labels = load_labels(root)[0] if ledger else []
    rows = []
    for cohort_id, item in ledger.items():
        reserve, consumed = item['reserve'], item['consumed']
        progress = cohort_progress(root, cohort_id, ledger, labels)
        rows.append({
            'cohortId': cohort_id, 'attempt': reserve['attempt'], 'alpha': reserve['alpha'],
            'lambda': reserve['lambda'], 'target': reserve['target'], 'reservedAt': reserve['at'],
            'policySha256': reserve['policySha256'], 'instrumentSha256': reserve['instrumentSha256'],
            'layaRevision': reserve['layaRevision'],
            'status': 'consumed' if consumed else ('awaiting_evaluation' if progress['complete'] else 'awaiting_labels'),
            'labeled': progress['labeled'], 'reserved': progress['reserved'],
            'verdict': consumed['verdict'] if consumed else None,
            'statistic': consumed['statistic'] if consumed else None,
            'consumedAt': consumed['at'] if consumed else None,
            'receiptSha256': consumed['receiptSha256'] if consumed else None})
    return rows


def verify_passed_cohort(root, entry: dict, binding: dict) -> None:
    """Raise ValueError unless binding.cohortId names a consumed 'pass' cohort of this exact policy,
    instrument and Laya revision (used by the registry mutation path before it grants cosign)."""
    item = cohort_ledger(root).get(binding['cohortId'])
    if item is None or item['consumed'] is None:
        raise ValueError('cohort is not consumed')
    reserve, consumed = item['reserve'], item['consumed']
    if consumed['verdict'] != 'pass':
        raise ValueError('cohort did not pass')
    policy_hash, instrument_hash = deployable_hashes(entry)
    if reserve['policy'] != entry['deployablePolicy'] or reserve['policySha256'] != policy_hash:
        raise ValueError('cohort policy is not the deployable policy')
    if reserve['instrumentSha256'] != instrument_hash:
        raise ValueError('cohort instrument is not the current instrument')
    if (binding['policySha256'], binding['instrumentSha256'], binding['layaRevision']) != key_of(reserve):
        raise ValueError('binding does not match the cohort key')


# ---------------------------------------------------------------- reserve

def _held(reason: str, **extra) -> dict:
    return {'status': 'held', 'reason': reason, **extra}


def reserve(root, registry: dict, now, seed, dry_run: bool = False) -> dict:
    """Freeze a new gate cohort of disagreement cases, or hold without writing anything.

    Candidates: deduped records (live + backfill) that are disagreements, are not listed in any earlier
    reserve event, and carry the most recent (policySha256, instrumentSha256, layaRevision) key. They are
    shuffled with random.Random(seed) (after sorting by occurrenceKey, so file order is irrelevant) and
    taken greedily with at most gates.promote.maxPerSession per session until cohortSize cases are chosen.
    """
    root = Path(root)
    entry = registry['decisions'][DECISION]
    gates = entry['gates']['promote']
    target, cap = gates['cohortSize'], gates['maxPerSession']

    def attempt_reserve():
        recs, _ = load_records(root)
        key = current_key(entry, recs)
        if key is None:
            return _held('no_records')
        ledger = cohort_ledger(root)
        same_key = [c for c in ledger.values() if key_of(c['reserve']) == key]
        open_cohorts = [c['reserve']['cohortId'] for c in same_key if c['consumed'] is None]
        if open_cohorts:
            return _held('open_cohort', cohortId=open_cohorts[0])
        attempt = 1 + sum(1 for c in same_key if c['consumed'] is not None)
        alpha = alpha_for_attempt(gates['alphaBase'], attempt)
        if alpha < MIN_ALPHA:
            return _held('alpha_exhausted', attempt=attempt)
        already = {k for c in ledger.values() for k in c['reserve']['occurrenceKeys']}
        pool = [r for r in recs if key_of(r) == key and contract.is_disagreement(r)
                and r['occurrenceKey'] not in already]
        sessions = Counter(r['sessionHash'] for r in pool)
        selectable = sum(min(count, cap) for count in sessions.values())
        if selectable < target:
            return _held('insufficient_disagreements', available=selectable, eligible=len(pool), target=target)
        order = sorted(pool, key=lambda r: r['occurrenceKey'])
        random.Random(seed).shuffle(order)
        taken, per_session = [], Counter()
        for rec in order:
            if per_session[rec['sessionHash']] >= cap:
                continue
            per_session[rec['sessionHash']] += 1
            taken.append(rec['occurrenceKey'])
            if len(taken) == target:
                break
        taken.sort()
        inclusion = min(1.0, target / len(pool))
        cohort_id = hashlib.sha256(canonical({
            'decision': DECISION, 'attempt': attempt, 'key': list(key), 'keys': taken,
            'seed': str(seed)}).encode('utf-8')).hexdigest()[:32]
        event = {'schema': contract.COHORT_SCHEMA, 'event': 'reserve', 'cohortId': cohort_id, 'decision': DECISION,
                 'at': iso(now), 'policy': contract.POLICY_COSIGN, 'policySha256': key[0],
                 'instrumentSha256': key[1], 'layaRevision': key[2], 'lambda': entry['lambda'], 'alpha': alpha,
                 'attempt': attempt, 'target': target, 'stratum': GATE_STRATUM, 'occurrenceKeys': taken}
        contract.validate_cohort_event(event)
        result = {'status': 'reserved', 'cohortId': cohort_id, 'attempt': attempt, 'alpha': alpha,
                  'target': target, 'inclusionProbability': inclusion, 'eligible': len(pool),
                  'selectable': selectable, 'key': {'policySha256': key[0], 'instrumentSha256': key[1],
                                                     'layaRevision': key[2]}}
        if dry_run:
            return {**result, 'status': 'would_reserve'}
        meta = {'schema': META_SCHEMA, 'cohortId': cohort_id, 'decision': DECISION, 'attempt': attempt,
                'target': target, 'eligible': len(pool), 'selectable': selectable,
                'inclusionProbability': inclusion, 'reservedAt': event['at']}
        # Sidecar first: an orphan sidecar is harmless, a reservation without one would starve the labeler.
        write_private_atomic(meta_path(root, cohort_id),
                             (canonical(meta) + '\n').encode('utf-8'))
        records.append(root, DECISION, 'cohorts', event)
        return result

    if dry_run:
        return attempt_reserve()
    with file_lock(skill_dir(root) / 'cohorts.lock'):
        return attempt_reserve()


def read_cohort_meta(root, cohort_id: str):
    """Sidecar for a cohort (None when absent or unreadable)."""
    try:
        meta = read_json_file(meta_path(root, cohort_id))
    except (OSError, ValueError):
        return None
    return meta if isinstance(meta, dict) and meta.get('cohortId') == cohort_id else None


# ---------------------------------------------------------------- availability

def unavailable_stats(recs: list[dict], key, tmin, tmax) -> dict:
    """Share of Laya calls that were not 'ok' among records with the cohort key inside [tmin, tmax].

    'skipped' records never called Laya and are not counted either way.
    """
    total = bad = 0
    for rec in recs:
        if key_of(rec) != key or rec['laya']['status'] == 'skipped':
            continue
        if not tmin <= utc(rec['ts']) <= tmax:
            continue
        total += 1
        bad += rec['laya']['status'] != 'ok'
    return {'total': total, 'unavailable': bad, 'share': (bad / total) if total else 0.0}


# ---------------------------------------------------------------- evaluate

def _sha256_json(value) -> str:
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def evaluate(root, registry: dict, cohort_id: str, now, dry_run: bool = False) -> dict:
    """Test a fully labeled cohort exactly once.

    Returns {'status': 'consumed', 'verdict': 'pass'|'fail'|'held', ...} after writing the receipt, a
    'labeled' event and a 'consumed' event; {'status': 'held', 'reason': 'incomplete'|...} (nothing written)
    when labels or records are missing; {'status': 'refused', 'reason': 'already_consumed'} when the cohort
    was already tested. dry_run computes the verdict without any write or lock.
    """
    root = Path(root)

    def run():
        ledger = cohort_ledger(root)
        item = ledger.get(cohort_id)
        if item is None:
            return _held('unknown_cohort')
        if item['consumed'] is not None:
            return {'status': 'refused', 'reason': 'already_consumed', 'verdict': item['consumed']['verdict']}
        reserve_event = item['reserve']
        entry = registry['decisions'][DECISION]
        gates = entry['gates']['promote']
        keys = reserve_event['occurrenceKeys']
        found = cohort_labels(load_labels(root)[0], reserve_event)
        missing = [k for k in keys if k not in found]
        if missing:
            return _held('incomplete', labeled=len(found), reserved=len(keys))
        recs, _ = load_records(root)
        by_key = {r['occurrenceKey']: r for r in recs}
        cohort_recs = [by_key.get(k) for k in keys]
        if any(r is None or not r['incumbent'] for r in cohort_recs):
            return _held('missing_records', reserved=len(keys))

        existing_receipt = None
        path = receipt_path(root, cohort_id)
        if path.exists():
            existing_receipt = _load_existing_receipt(path, cohort_id)
        if existing_receipt is not None:
            receipt_bytes, receipt = existing_receipt
        else:
            receipt = _build_receipt(reserve_event, gates, entry, cohort_recs, recs, found, registry, now)
            receipt_bytes = (canonical(receipt) + '\n').encode('utf-8')
        receipt_sha = hashlib.sha256(receipt_bytes).hexdigest()
        result = {'status': 'consumed', 'cohortId': cohort_id, 'verdict': receipt['verdict'],
                  'statistic': receipt['statistic'], 'counts': receipt['counts'], 'receiptSha256': receipt_sha,
                  'holdReasons': receipt['holdReasons'], 'attempt': reserve_event['attempt'],
                  'key': {'policySha256': reserve_event['policySha256'],
                          'instrumentSha256': reserve_event['instrumentSha256'],
                          'layaRevision': reserve_event['layaRevision']}}
        if dry_run:
            return {**result, 'status': 'would_consume'}
        if existing_receipt is None:
            try:
                write_private_exclusive(path, receipt_bytes)
            except FileExistsError:           # an unreadable receipt from somewhere else: never overwrite it
                return _held('receipt_conflict')
        result['receiptPath'] = str(path)
        at = iso(now)
        if item['labeled'] is None:
            records.append(root, DECISION, 'cohorts', {
                'schema': contract.COHORT_SCHEMA, 'event': 'labeled', 'cohortId': cohort_id, 'decision': DECISION,
                'at': at, 'counts': receipt['counts']})
        records.append(root, DECISION, 'cohorts', {
            'schema': contract.COHORT_SCHEMA, 'event': 'consumed', 'cohortId': cohort_id, 'decision': DECISION,
            'at': at, 'verdict': receipt['verdict'], 'statistic': receipt['statistic'], 'receiptSha256': receipt_sha})
        return result

    if dry_run:
        return run()
    with file_lock(skill_dir(root) / 'cohorts.lock'):
        return run()


def _load_existing_receipt(path: Path, cohort_id: str):
    """Reuse a receipt left by a crash between the receipt write and the consumed event."""
    try:
        raw = path.read_bytes()
        receipt = json.loads(raw.decode('utf-8'))
    except (OSError, ValueError):
        return None
    if not isinstance(receipt, dict) or receipt.get('schema') != RECEIPT_SCHEMA or receipt.get('cohortId') != cohort_id:
        return None
    return raw, receipt


def _build_receipt(reserve_event, gates, entry, cohort_recs, all_recs, found, registry, now) -> dict:
    keys = reserve_event['occurrenceKeys']
    labeled = len(keys)
    ambiguous = hit = not_hit = wrong = false_fire = 0
    label_digest = []
    for rec, key in zip(cohort_recs, keys):
        label = found[key]
        score = contract.score_suggestion(rec['incumbent']['skillId'], label)
        label_digest.append([key, score, sorted(label['acceptable'])])
        if score is None:
            ambiguous += 1
        elif score == 'hit':
            hit += 1
        else:
            not_hit += 1
            wrong += score == 'wrong'
            false_fire += score == 'false_fire'
    n, x = hit + not_hit, not_hit
    counts = {'labeled': labeled, 'ambiguous': ambiguous, 'hit': hit, 'notHit': not_hit}
    key = key_of(reserve_event)
    times = [utc(r['ts']) for r in cohort_recs]
    unavailable = unavailable_stats(all_recs, key, min(times), max(times))
    ambiguous_share = ambiguous / labeled if labeled else 0.0
    threshold = threshold_for(reserve_event['lambda'])
    alpha = reserve_event['alpha']
    hold_reasons = []
    if ambiguous_share > gates['maxAmbiguousShare']:
        hold_reasons.append('ambiguity')
    if unavailable['share'] > gates['maxUnavailableShare']:
        hold_reasons.append('laya_unavailable')
    if n == 0:
        hold_reasons.append('no_unambiguous_labels')
    if hold_reasons:
        verdict, bound = 'held', None
    else:
        bound = cp_lower(x, n, alpha)
        verdict = 'pass' if bound > threshold else 'fail'
    statistic = {'n': n, 'x': x, 'bound': bound, 'threshold': threshold, 'alpha': alpha}
    return {
        'schema': RECEIPT_SCHEMA, 'cohortId': reserve_event['cohortId'], 'decision': DECISION,
        'evaluatedAt': iso(now), 'reservedAt': reserve_event['at'],
        'policy': reserve_event['policy'], 'policySha256': key[0], 'instrumentSha256': key[1],
        'layaRevision': key[2], 'registrySha256': _sha256_json(registry),
        'routerSourceSha256': sorted({r['routerSourceSha256'] for r in cohort_recs}),
        'indexSha256': sorted({r['indexSha256'] for r in cohort_recs}),
        'criteriaSha256': sorted({r['criteriaSha256'] for r in cohort_recs if r['criteriaSha256']}),
        'attempt': reserve_event['attempt'], 'alpha': alpha, 'lambda': reserve_event['lambda'],
        'target': reserve_event['target'], 'occurrenceKeysSha256': _sha256_json(sorted(keys)),
        'labelsSha256': _sha256_json(label_digest),
        'counts': counts, 'wrong': wrong, 'falseFire': false_fire,
        'ambiguousShare': ambiguous_share, 'maxAmbiguousShare': gates['maxAmbiguousShare'],
        'unavailable': {**unavailable, 'max': gates['maxUnavailableShare'],
                        'window': [iso(min(times)), iso(max(times))]},
        'statistic': statistic, 'verdict': verdict, 'holdReasons': hold_reasons,
    }


# ---------------------------------------------------------------- demotion

def percentile_nearest_rank(values: list[float], q: float):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(q * len(ordered)) - 1)]


def demotion_check(root, registry: dict, state, now) -> dict:
    """Should a deployed `cosign` fall back to `shadow`? Read-only.

    quality     - labeled LIVE cosign-mode disagreements whose record is in the last 14 days (and since the
                  promotion): demote when n >= minLabeled and the one-sided CP *upper* bound at demote.alpha
                  is below 1/(1+lambda), i.e. we are confident the incumbent was right more often than not.
    operational - share of live Laya calls (since the promotion, last operationalWindowDays) ending
                  unavailable/invalid/identity_failed/redirect_refused above demote.maxUnavailableShare.
                  Timeouts are reported separately and do not trip it.
    latency     - p90 of ok live calls above latencyBudgetMs; report-only for latencyReportOnlyDays after
                  the promotion 'since', afterwards it demotes ('demoted_latency').
    Returns {'demote': bool, 'reason': slug|None, 'quality': {...}, 'operational': {...}, 'latency': {...}}.
    """
    root = Path(root)
    entry = registry['decisions'][DECISION]
    gates = entry['gates']['demote']
    current = ((state or {}).get('decisions') or {}).get(DECISION)
    if not current or current['mode'] != 'cosign':
        return {'demote': False, 'reason': None, 'skipped': 'not_cosign'}
    now = utc(now)
    since = utc(current['since'])
    threshold = threshold_for(entry['lambda'])
    recs, _ = load_records(root)
    labels, _ = load_labels(root)
    by_key = {r['occurrenceKey']: r for r in recs}

    # (a) quality
    window_start = max(now - timedelta(days=QUALITY_WINDOW_DAYS), since)
    seen, n, x, ambiguous = set(), 0, 0, 0
    for label in labels:
        key = label['occurrenceKey']
        rec = by_key.get(key)
        if label['basis'] == 'harness' or key in seen or rec is None:
            continue
        if rec['basis'] != 'live' or rec['mode'] != 'cosign' or not contract.is_disagreement(rec):
            continue
        if not window_start <= utc(rec['ts']) <= now:
            continue
        seen.add(key)
        score = contract.score_suggestion(rec['incumbent']['skillId'], label)
        if score is None:
            ambiguous += 1
            continue
        n += 1
        x += score in FAIL_SCORES
    upper = cp_upper(x, n, gates['alpha']) if n else None
    quality = {'n': n, 'x': x, 'ambiguous': ambiguous, 'upperBound': upper, 'threshold': threshold,
               'alpha': gates['alpha'], 'minLabeled': gates['minLabeled'],
               'trigger': bool(n >= gates['minLabeled'] and upper is not None and upper < threshold)}

    # (b) operational and (c) latency share one window of live calls since the promotion
    ops_start = max(now - timedelta(days=gates['operationalWindowDays']), since)
    live = [r for r in recs if r['basis'] == 'live' and r['laya']['status'] != 'skipped'
            and ops_start <= utc(r['ts']) <= now]
    total = len(live)
    failures = sum(r['laya']['status'] in OPERATIONAL_FAILURES for r in live)
    timeouts = sum(r['laya']['status'] == 'timeout' for r in live)
    share = failures / total if total else 0.0
    operational = {'total': total, 'failures': failures, 'share': share, 'max': gates['maxUnavailableShare'],
                   'timeouts': timeouts, 'timeoutShare': (timeouts / total) if total else 0.0,
                   'minRecords': MIN_OPERATIONAL_RECORDS,
                   'trigger': bool(total >= MIN_OPERATIONAL_RECORDS and share > gates['maxUnavailableShare'])}

    latencies = [r['laya']['latencyMs'] for r in live
                 if r['laya']['status'] == 'ok' and r['laya']['latencyMs'] is not None]
    p90 = percentile_nearest_rank(latencies, 0.9)
    p50 = percentile_nearest_rank(latencies, 0.5)
    report_only = now < since + timedelta(days=gates['latencyReportOnlyDays'])
    breach = bool(p90 is not None and len(latencies) >= MIN_OPERATIONAL_RECORDS and p90 > entry['latencyBudgetMs'])
    latency = {'n': len(latencies), 'p50': p50, 'p90': p90, 'budgetMs': entry['latencyBudgetMs'],
               'breach': breach, 'reportOnly': report_only, 'reportOnlyUntil': iso(since + timedelta(
                   days=gates['latencyReportOnlyDays'])), 'trigger': breach and not report_only}

    reason = None
    if quality['trigger']:
        reason = 'demoted_quality'
    elif operational['trigger']:
        reason = 'demoted_operational'
    elif latency['trigger']:
        reason = 'demoted_latency'
    return {'demote': reason is not None, 'reason': reason, 'quality': quality, 'operational': operational,
            'latency': latency, 'since': current['since']}


# ---------------------------------------------------------------- summaries (counts only)

def summarize_records(recs: list[dict]) -> dict:
    """Counts, disagreement prevalence and Laya latency/status per promptLengthBucket. No text exists to leak."""
    live = [r for r in recs if r['basis'] == 'live']
    summary = {'total': len(recs), 'byBasis': dict(Counter(r['basis'] for r in recs)),
               'liveArms': dict(Counter(r['arm'] for r in live)), 'liveModes': dict(Counter(r['mode'] for r in live)),
               'prevalence': {}, 'laya': {}}
    for basis in ('live', 'backfill'):
        own = [r for r in recs if r['basis'] == basis]
        fired = [r for r in own if r['incumbent'] and r['laya']['status'] == 'ok']
        disagreements = sum(contract.is_disagreement(r) for r in fired)
        summary['prevalence'][basis] = {'fired': len(fired), 'disagreements': disagreements,
                                        'share': (disagreements / len(fired)) if fired else None}
        table = {}
        for bucket in instrument.LENGTH_BUCKETS:
            called = [r for r in own if r['promptLengthBucket'] == bucket and r['laya']['status'] != 'skipped']
            latencies = [r['laya']['latencyMs'] for r in called
                         if r['laya']['status'] == 'ok' and r['laya']['latencyMs'] is not None]
            table[bucket] = {'calls': len(called),
                             'statuses': dict(Counter(r['laya']['status'] for r in called)),
                             'p50': percentile_nearest_rank(latencies, 0.5),
                             'p90': percentile_nearest_rank(latencies, 0.9)}
        summary['laya'][basis] = table
    return summary
