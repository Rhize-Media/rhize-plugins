"""Typed-decision contract: validators, identities and frozen scoring rules (plan §4.1, §4.4).

Coordinator-owned. Lanes import from here and never redefine these rules. Stdlib only (the
plugin runtime has no jsonschema); the JSON Schemas in rhize-context-manager/schemas/ document
the same shapes and are checked against the shared fixtures when jsonschema is importable.

Every validator raises ValueError(<reason>) and returns the validated object unchanged.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone

from typed_decisions.instrument import INSTRUMENT, LENGTH_BUCKETS, canonical_json, sha256_hex

RECORD_SCHEMA = 'rhize-typed-decision-record-v1'
LABEL_SCHEMA = 'rhize-typed-decision-label-v1'
OUTCOME_SCHEMA = 'rhize-typed-decision-outcome-v1'
COHORT_SCHEMA = 'rhize-typed-decision-cohort-v1'
AUDIT_SCHEMA = 'rhize-typed-decision-registry-audit-v1'
CHOICE_RECORD_SCHEMA = 'rhize-typed-choice-record-v1'
CHOICE_OUTCOME_SCHEMA = 'rhize-typed-choice-outcome-v1'
CHOICE_SHOWN_SCHEMA = 'rhize-typed-choice-shown-v1'
REGISTRY_SCHEMA_VERSION = 1
STATE_SCHEMA_VERSION = 1

DECISIONS = ('skill-fit', 'workflow-fit', 'procedure-pick', 'devflow-next-action', 'browser-qa-selection',
             'model-routing', 'gsd-directive', 'check-relaxation', 'credential-procedure')
CREDENTIAL_DECISION = 'credential-procedure'
ADVISE_DECISIONS = tuple(d for d in DECISIONS if d != CREDENTIAL_DECISION)  # the credential decision is manual-only
RECORDED_DECISIONS = ('skill-fit',)
MODES = ('off', 'shadow', 'advise', 'cosign')
EARNED_MODES = ('advise', 'cosign')
TIERS = ('advisory', 'workflow', 'critical')
HOSTS = ('claude', 'codex', 'unknown')
BASES = ('live', 'backfill')
SOURCE_STRATA = ('fired', 'silent_sample')
ARMS = ('treatment', 'holdback', 'none')
LAYA_STATUSES = ('ok', 'timeout', 'unavailable', 'invalid', 'identity_failed', 'redirect_refused', 'skipped')
LABEL_BASES = ('ai_model_reviewed', 'human_adjudicated', 'harness')
OUTCOMES = ('invoked_emitted', 'invoked_other_shortlisted', 'invoked_unlisted', 'none_invoked',
            'transcript_unavailable')
OUTCOME_VIA = ('skill_tool', 'slash_command', 'skill_file_read')
COHORT_EVENTS = ('reserve', 'labeled', 'consumed')
VERDICTS = ('pass', 'fail', 'held')
AUDIT_PHASES = ('intent', 'commit')
AUDIT_ACTORS = ('cli', 'cycle', 'recovery')

POLICY_COSIGN = 'cosign-v1'
POLICY_CREDENTIAL = 'credential-cli-v1'
POLICY_ADVISE = 'advise-v1'  # the baseline gate earns it; typed_advice binds its own per-surface hash
POLICIES = {POLICY_COSIGN: 'emit the incumbent router suggestion iff laya.status == "ok" and laya.choice '
                           '== incumbent.skillId; otherwise emit no router suggestion',
            POLICY_CREDENTIAL: 'emit only a fixed allowed credential CLI procedure selected by Laya; '
                               'otherwise retain deterministic CLI-first guidance; never grant permissions or clear a deny',
            POLICY_ADVISE: "show Laya's choice as an advisory line next to the unchanged incumbent output when earned; "
                           'never suppress or alter the incumbent'}
ADVISE_GATE = 'majority-baseline'
ADVISE_INSTRUMENTS = ('typed-advice-v1', 'laya-choice-v1')
MIN_CRITICAL_ADVISE_CASES = 10
MAX_SHORTLIST = 5
MAX_RECORD_BYTES = 4096

HEX64 = re.compile(r'[0-9a-f]{64}\Z')
HEX32 = re.compile(r'[0-9a-f]{32}\Z')
TS = re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z\Z')
SKILL_ID = re.compile(r'skill:[A-Za-z0-9_.\-/]+\Z')
REVISION = re.compile(r'[A-Za-z0-9._-]{1,80}\Z')
MODEL_ID = re.compile(r'[A-Za-z0-9._:/-]{1,80}\Z')
SKILL_REF = re.compile(r'[A-Za-z0-9_.:/-]{1,160}\Z')
STRATUM = re.compile(r'[a-z_]{1,40}\Z')


SAFE_REASON = re.compile(r"[A-Za-z0-9 _.:()/,'=<>-]{1,160}\Z")


def safe_reason(exc: BaseException) -> str | None:
    """An exception message fit for a counts-only summary: our own short reasons pass, anything that could
    carry free text (prompt or transcript fragments, paths with spaces in odd places) is dropped."""
    message = str(exc)
    return message if SAFE_REASON.match(message) else None


def policy_sha256(policy: str = POLICY_COSIGN) -> str:
    if policy not in POLICIES:
        raise ValueError('unknown policy')
    return sha256_hex(canonical_json({'policy': policy, 'rule': POLICIES[policy]}))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def minute_of(ts: str) -> str:
    """UTC 'YYYY-MM-DDTHH:MM' for an ISO-8601 timestamp with Z or an explicit offset."""
    if not isinstance(ts, str):
        raise ValueError('invalid timestamp')
    try:
        value = datetime.fromisoformat(ts.replace('Z', '+00:00'))
    except ValueError:
        raise ValueError('invalid timestamp') from None
    if value.tzinfo is None:
        raise ValueError('timestamp must carry a timezone')
    return value.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M')


def occurrence_key(session_hash: str, prompt_hash: str, ts: str) -> str:
    """Stable identity of one router-hook run (live record ts or legacy log row ts)."""
    _hex64(session_hash, 'sessionHash')
    _hex64(prompt_hash, 'promptHash')
    return sha256_text(f'{session_hash}:{prompt_hash}:{minute_of(ts)}')


def arm_for(session_hash: str, prompt_hash: str, holdback: float) -> str:
    """Deterministic arm: 'holdback' when the hash bucket falls below holdback x 10000."""
    _hex64(session_hash, 'sessionHash')
    _hex64(prompt_hash, 'promptHash')
    if isinstance(holdback, bool) or not isinstance(holdback, (int, float)) or not 0 <= holdback <= 0.5:
        raise ValueError('invalid holdback')
    bucket = int(sha256_text(f'{session_hash}:{prompt_hash}')[:8], 16) % 10000
    return 'holdback' if bucket < round(holdback * 10000) else 'treatment'


def is_disagreement(record: dict) -> bool:
    """The only stratum where cosign-v1 and the incumbent differ."""
    incumbent = record.get('incumbent')
    laya = record.get('laya') or {}
    return bool(incumbent) and laya.get('status') == 'ok' and laya.get('choice') != incumbent['skillId']


def score_suggestion(suggestion, label: dict):
    """Frozen scoring rule (plan §4.4). Returns 'hit' | 'wrong' | 'false_fire' | 'silent' | None.

    None means the label is ambiguous and must be excluded from gates.
    """
    if label.get('ambiguous'):
        return None
    if suggestion is None:
        return 'silent'
    acceptable = label.get('acceptable') or []
    if suggestion in acceptable:
        return 'hit'
    if not acceptable:
        return 'false_fire'
    return 'wrong'


# ---------------------------------------------------------------- helpers

def _hex64(value, field):
    if not isinstance(value, str) or not HEX64.match(value):
        raise ValueError(f'invalid {field}')


def _keys(obj, expected, name):
    if not isinstance(obj, dict):
        raise ValueError(f'{name} must be an object')
    if set(obj) != set(expected):
        missing = sorted(set(expected) - set(obj))
        extra = sorted(set(obj) - set(expected))
        raise ValueError(f'{name} keys mismatch (missing={missing}, extra={extra})')


def _enum(value, allowed, field):
    if value not in allowed:
        raise ValueError(f'invalid {field}')


def _ts(value, field):
    if not isinstance(value, str) or not TS.match(value):
        raise ValueError(f'invalid {field}')


def _number(value, field, lo=None, hi=None, nullable=False):
    if value is None and nullable:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'invalid {field}')
    if (lo is not None and value < lo) or (hi is not None and value > hi):
        raise ValueError(f'invalid {field}')


def _int(value, field, lo=None, nullable=False):
    if value is None and nullable:
        return
    if isinstance(value, bool) or not isinstance(value, int) or (lo is not None and value < lo):
        raise ValueError(f'invalid {field}')


def _skill(value, field):
    if not isinstance(value, str) or not SKILL_ID.match(value):
        raise ValueError(f'invalid {field}')


def _skill_list(value, field, max_items):
    if not isinstance(value, list) or len(value) > max_items or len(set(value)) != len(value):
        raise ValueError(f'invalid {field}')
    for item in value:
        _skill(item, field)


# ---------------------------------------------------------------- records

RECORD_KEYS = ('schema', 'decision', 'decisionId', 'occurrenceKey', 'ts', 'host', 'basis', 'sourceStratum',
               'sessionHash', 'promptHash', 'promptLengthBucket', 'routerSourceSha256', 'indexSha256',
               'registryRevision', 'policy', 'policySha256', 'instrument', 'instrumentSha256', 'criteriaSha256',
               'layaRevision', 'mode', 'arm', 'propensity', 'incumbent', 'shortlist', 'laya', 'emitted')
LAYA_KEYS = ('status', 'choice', 'probabilities', 'latencyMs', 'truncated')


def validate_record(record: dict) -> dict:
    _keys(record, RECORD_KEYS, 'record')
    if record['schema'] != RECORD_SCHEMA:
        raise ValueError('invalid schema')
    _enum(record['decision'], RECORDED_DECISIONS, 'decision')
    if not isinstance(record['decisionId'], str) or not HEX32.match(record['decisionId']):
        raise ValueError('invalid decisionId')
    for field in ('occurrenceKey', 'sessionHash', 'promptHash', 'routerSourceSha256', 'indexSha256',
                  'policySha256', 'instrumentSha256'):
        _hex64(record[field], field)
    if record['occurrenceKey'] != occurrence_key(record['sessionHash'], record['promptHash'], record['ts']):
        raise ValueError('occurrenceKey mismatch')
    _ts(record['ts'], 'ts')
    _enum(record['host'], HOSTS, 'host')
    _enum(record['basis'], BASES, 'basis')
    _enum(record['sourceStratum'], SOURCE_STRATA, 'sourceStratum')
    _enum(record['promptLengthBucket'], LENGTH_BUCKETS, 'promptLengthBucket')
    _int(record['registryRevision'], 'registryRevision', lo=0)
    _enum(record['policy'], tuple(POLICIES), 'policy')
    if record['policySha256'] != policy_sha256(record['policy']):
        raise ValueError('policySha256 mismatch')
    if record['instrument'] != INSTRUMENT:
        raise ValueError('invalid instrument')
    if not isinstance(record['layaRevision'], str) or not REVISION.match(record['layaRevision']):
        raise ValueError('invalid layaRevision')
    _enum(record['mode'], ('shadow', 'advise', 'cosign'), 'mode')
    if (record['mode'] == 'advise') != (record['policy'] == POLICY_ADVISE):
        raise ValueError('advise-v1 is the policy of advise records only')
    _enum(record['arm'], ARMS, 'arm')
    if record['basis'] == 'backfill':
        if record['arm'] != 'none' or record['propensity'] is not None or record['mode'] != 'shadow':
            raise ValueError('backfill records are shadow, arm none, propensity null')
        if record['emitted'] is not None:
            raise ValueError('backfill records never emit')
    else:
        if record['arm'] == 'none':
            raise ValueError('live records carry an arm')
        _number(record['propensity'], 'propensity', 0, 1)
    incumbent = record['incumbent']
    if incumbent is not None:
        _keys(incumbent, ('skillId', 'score'), 'incumbent')
        _skill(incumbent['skillId'], 'incumbent.skillId')
        _number(incumbent['score'], 'incumbent.score', 0)
    elif record['basis'] == 'live':
        raise ValueError('live records require an incumbent')
    shortlist = record['shortlist']
    _skill_list(shortlist, 'shortlist', MAX_SHORTLIST)
    if incumbent is not None and incumbent['skillId'] not in shortlist:
        raise ValueError('incumbent must be in shortlist')
    laya = record['laya']
    _keys(laya, LAYA_KEYS, 'laya')
    _enum(laya['status'], LAYA_STATUSES, 'laya.status')
    if laya['status'] == 'ok':
        if laya['choice'] != 'none' and laya['choice'] not in shortlist:
            raise ValueError('laya.choice must be a shortlist id or none')
        probs = laya['probabilities']
        if not isinstance(probs, list) or len(probs) != len(shortlist) + 1:
            raise ValueError('laya.probabilities must align with shortlist + none')
        for p in probs:
            _number(p, 'laya.probabilities', 0, 1)
        if record['criteriaSha256'] is None:
            raise ValueError('criteriaSha256 required when Laya answered')
    else:
        if laya['choice'] is not None or laya['probabilities'] is not None:
            raise ValueError('laya.choice/probabilities only when status ok')
    if record['criteriaSha256'] is not None:
        _hex64(record['criteriaSha256'], 'criteriaSha256')
    if laya['status'] == 'skipped':
        if laya['latencyMs'] is not None or laya['truncated'] is not None or record['criteriaSha256'] is not None:
            raise ValueError('skipped Laya calls carry no latency/truncation/criteria')
    else:
        if not shortlist:
            raise ValueError('a Laya call needs a shortlist')
        _number(laya['latencyMs'], 'laya.latencyMs', 0, nullable=True)
        if not isinstance(laya['truncated'], bool):
            raise ValueError('invalid laya.truncated')
    emitted = record['emitted']
    if emitted is not None:
        if incumbent is None or emitted != incumbent['skillId']:
            raise ValueError('emitted must be the incumbent or null')
    if (record['basis'] == 'live' and record['mode'] == 'cosign' and record['arm'] == 'treatment'
            and laya['status'] == 'ok' and laya['choice'] != incumbent['skillId'] and emitted is not None):
        raise ValueError('cosign treatment must suppress on disagreement')
    if len(json.dumps(record, separators=(',', ':'), ensure_ascii=False).encode('utf-8')) > MAX_RECORD_BYTES:
        raise ValueError('record too large')
    return record


# ---------------------------------------------------------------- labels

LABEL_KEYS = ('schema', 'decisionId', 'occurrenceKey', 'basis', 'cohortId', 'stratum', 'inclusionProbability',
              'candidates', 'acceptable', 'bestSkill', 'unlistedBetter', 'ambiguous', 'annotators', 'reviewer',
              'evidenceSha256', 'labeledAt')


def validate_label(label: dict) -> dict:
    _keys(label, LABEL_KEYS, 'label')
    if label['schema'] != LABEL_SCHEMA:
        raise ValueError('invalid schema')
    if not isinstance(label['decisionId'], str) or not HEX32.match(label['decisionId']):
        raise ValueError('invalid decisionId')
    _hex64(label['occurrenceKey'], 'occurrenceKey')
    _enum(label['basis'], LABEL_BASES, 'basis')
    if label['cohortId'] is not None and (not isinstance(label['cohortId'], str) or not HEX32.match(label['cohortId'])):
        raise ValueError('invalid cohortId')
    if not isinstance(label['stratum'], str) or not STRATUM.match(label['stratum']):
        raise ValueError('invalid stratum')
    if label['basis'] == 'harness':
        if label['inclusionProbability'] is not None or label['cohortId'] is not None:
            raise ValueError('harness labels carry no cohort or inclusion probability')
    else:
        _number(label['inclusionProbability'], 'inclusionProbability', 0, 1)
        if label['inclusionProbability'] == 0:
            raise ValueError('invalid inclusionProbability')
    _skill_list(label['candidates'], 'candidates', MAX_SHORTLIST)
    _skill_list(label['acceptable'], 'acceptable', MAX_SHORTLIST)
    if set(label['acceptable']) - set(label['candidates']):
        raise ValueError('acceptable must be a subset of candidates')
    best = label['bestSkill']
    if best == 'none':
        if label['acceptable']:
            raise ValueError('bestSkill none requires an empty acceptable set')
    else:
        _skill(best, 'bestSkill')
        if best not in label['acceptable']:
            raise ValueError('bestSkill must be acceptable')
    for field in ('unlistedBetter', 'ambiguous'):
        if not isinstance(label[field], bool):
            raise ValueError(f'invalid {field}')
    annotators = label['annotators']
    if not isinstance(annotators, list) or len(annotators) > 4 or any(
            not isinstance(a, str) or not MODEL_ID.match(a) for a in annotators):
        raise ValueError('invalid annotators')
    if label['reviewer'] is not None and (not isinstance(label['reviewer'], str) or not MODEL_ID.match(label['reviewer'])):
        raise ValueError('invalid reviewer')
    if label['evidenceSha256'] is not None:
        _hex64(label['evidenceSha256'], 'evidenceSha256')
    _ts(label['labeledAt'], 'labeledAt')
    return label


# ---------------------------------------------------------------- outcomes

OUTCOME_KEYS = ('schema', 'decisionId', 'occurrenceKey', 'outcome', 'skillInvoked', 'via', 'latencyTurns',
                'joinedAt', 'transcriptSha256')


def validate_outcome(outcome: dict) -> dict:
    _keys(outcome, OUTCOME_KEYS, 'outcome')
    if outcome['schema'] != OUTCOME_SCHEMA:
        raise ValueError('invalid schema')
    if not isinstance(outcome['decisionId'], str) or not HEX32.match(outcome['decisionId']):
        raise ValueError('invalid decisionId')
    _hex64(outcome['occurrenceKey'], 'occurrenceKey')
    _enum(outcome['outcome'], OUTCOMES, 'outcome')
    invoked = outcome['outcome'] in ('invoked_emitted', 'invoked_other_shortlisted', 'invoked_unlisted')
    if invoked:
        if not isinstance(outcome['skillInvoked'], str) or not SKILL_REF.match(outcome['skillInvoked']):
            raise ValueError('invalid skillInvoked')
        _enum(outcome['via'], OUTCOME_VIA, 'via')
        _int(outcome['latencyTurns'], 'latencyTurns', lo=0)
    elif outcome['skillInvoked'] is not None or outcome['via'] is not None or outcome['latencyTurns'] is not None:
        raise ValueError('non-invocation outcomes carry no skill, via or latency')
    _ts(outcome['joinedAt'], 'joinedAt')
    if outcome['transcriptSha256'] is not None:
        _hex64(outcome['transcriptSha256'], 'transcriptSha256')
    elif outcome['outcome'] != 'transcript_unavailable':
        raise ValueError('transcriptSha256 required unless transcript_unavailable')
    return outcome


# ---------------------------------------------------------------- cohorts

COHORT_COMMON = ('schema', 'event', 'cohortId', 'decision', 'at')
COHORT_RESERVE = COHORT_COMMON + ('policy', 'policySha256', 'instrumentSha256', 'layaRevision', 'lambda', 'alpha',
                                  'attempt', 'target', 'stratum', 'occurrenceKeys')
COHORT_LABELED = COHORT_COMMON + ('counts',)
COHORT_CONSUMED = COHORT_COMMON + ('verdict', 'statistic', 'receiptSha256')
COUNT_KEYS = ('labeled', 'ambiguous', 'hit', 'notHit')
STATISTIC_KEYS = ('n', 'x', 'bound', 'threshold', 'alpha')


def validate_cohort_event(event: dict) -> dict:
    if not isinstance(event, dict):
        raise ValueError('cohort event must be an object')
    _enum(event.get('event'), COHORT_EVENTS, 'event')
    expected = {'reserve': COHORT_RESERVE, 'labeled': COHORT_LABELED, 'consumed': COHORT_CONSUMED}[event['event']]
    _keys(event, expected, 'cohort event')
    if event['schema'] != COHORT_SCHEMA:
        raise ValueError('invalid schema')
    if not isinstance(event['cohortId'], str) or not HEX32.match(event['cohortId']):
        raise ValueError('invalid cohortId')
    _enum(event['decision'], RECORDED_DECISIONS, 'decision')
    _ts(event['at'], 'at')
    if event['event'] == 'reserve':
        _enum(event['policy'], (POLICY_COSIGN, POLICY_CREDENTIAL), 'policy')  # cohorts are never advise
        if event['policySha256'] != policy_sha256(event['policy']):
            raise ValueError('policySha256 mismatch')
        _hex64(event['instrumentSha256'], 'instrumentSha256')
        if not isinstance(event['layaRevision'], str) or not REVISION.match(event['layaRevision']):
            raise ValueError('invalid layaRevision')
        _number(event['lambda'], 'lambda', 0)
        if event['lambda'] == 0:
            raise ValueError('invalid lambda')
        _number(event['alpha'], 'alpha', 0, 0.5)
        if event['alpha'] == 0:
            raise ValueError('invalid alpha')
        _int(event['attempt'], 'attempt', lo=1)
        _int(event['target'], 'target', lo=1)
        if event['stratum'] != 'disagreement':
            raise ValueError('gate cohorts sample the disagreement stratum')
        keys = event['occurrenceKeys']
        if not isinstance(keys, list) or len(keys) != len(set(keys)) or len(keys) < event['target']:
            raise ValueError('invalid occurrenceKeys')
        for key in keys:
            _hex64(key, 'occurrenceKeys')
    elif event['event'] == 'labeled':
        counts = event['counts']
        _keys(counts, COUNT_KEYS, 'counts')
        for key in COUNT_KEYS:
            _int(counts[key], f'counts.{key}', lo=0)
        if counts['labeled'] != counts['ambiguous'] + counts['hit'] + counts['notHit']:
            raise ValueError('counts do not add up')
    else:
        _enum(event['verdict'], VERDICTS, 'verdict')
        stat = event['statistic']
        _keys(stat, STATISTIC_KEYS, 'statistic')
        _int(stat['n'], 'statistic.n', lo=0)
        _int(stat['x'], 'statistic.x', lo=0)
        if stat['x'] > stat['n']:
            raise ValueError('statistic.x exceeds n')
        for key in ('bound', 'threshold', 'alpha'):
            _number(stat[key], f'statistic.{key}', 0, 1, nullable=key == 'bound')
        _hex64(event['receiptSha256'], 'receiptSha256')
    return event


# ---------------------------------------------------------------- generic choice records (typed_advice.py)

CHOICE_RECORD_KEYS = ('schema', 'decision', 'decisionId', 'ts', 'mode', 'arm', 'tier', 'policySha256',
                      'instrumentSha256', 'layaRevision', 'candidates', 'criticalIfWrong', 'requestSha256', 'files',
                      'laya')
CHOICE_RECORD_OPTIONAL = ('groupSha256',)   # session-like split unit; records written before it existed lack it
CHOICE_LAYA_KEYS = ('status', 'choice', 'probabilities', 'latencyMs')
CHOICE_LAYA_STATUSES = ('ok', 'timeout', 'unavailable', 'invalid', 'identity_failed', 'redirect_refused')
CHOICE_OUTCOME_KEYS = ('schema', 'decision', 'decisionId', 'chosen', 'followed', 'ts')
CHOICE_SHOWN_KEYS = ('schema', 'decision', 'decisionId', 'recommendation', 'policySha256', 'ts')
CANDIDATE_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}\Z')
MAX_CHOICE_CANDIDATES = 16
MAX_CHOICE_FILES = 20


def validate_choice_record(record: dict) -> dict:
    """The write-once record typed_advice.advise() stores at <root>/<decision>/choice/<decisionId>.json."""
    _keys({k: v for k, v in record.items() if k not in CHOICE_RECORD_OPTIONAL} if isinstance(record, dict) else record,
          CHOICE_RECORD_KEYS, 'choice record')
    if 'groupSha256' in record:
        _hex64(record['groupSha256'], 'groupSha256')
    if record['schema'] != CHOICE_RECORD_SCHEMA:
        raise ValueError('invalid schema')
    _enum(record['decision'], ADVISE_DECISIONS, 'decision')
    if not isinstance(record['decisionId'], str) or not HEX32.match(record['decisionId']):
        raise ValueError('invalid decisionId')
    _ts(record['ts'], 'ts')
    _enum(record['mode'], ('shadow', 'advise'), 'mode')
    _enum(record['arm'], ('treatment', 'holdback'), 'arm')
    _enum(record['tier'], TIERS, 'tier')
    for field in ('policySha256', 'instrumentSha256', 'requestSha256'):
        _hex64(record[field], field)
    if not isinstance(record['layaRevision'], str) or not REVISION.match(record['layaRevision']):
        raise ValueError('invalid layaRevision')
    candidates = record['candidates']
    if (not isinstance(candidates, list) or not 2 <= len(candidates) <= MAX_CHOICE_CANDIDATES
            or len(set(candidates)) != len(candidates)
            or any(not isinstance(c, str) or not CANDIDATE_ID.match(c) for c in candidates)):
        raise ValueError('invalid candidates')
    if not isinstance(record['criticalIfWrong'], bool):
        raise ValueError('invalid criticalIfWrong')
    _int(record['files'], 'files', lo=0)
    if record['files'] > MAX_CHOICE_FILES:
        raise ValueError('invalid files')
    laya = record['laya']
    _keys(laya, CHOICE_LAYA_KEYS, 'laya')
    _enum(laya['status'], CHOICE_LAYA_STATUSES, 'laya.status')
    _number(laya['latencyMs'], 'laya.latencyMs', 0, nullable=True)
    if laya['status'] == 'ok':
        probs = laya['probabilities']
        if laya['choice'] not in candidates:
            raise ValueError('laya.choice must be a candidate')
        if not isinstance(probs, dict) or set(probs) != set(candidates):
            raise ValueError('laya.probabilities must cover every candidate')
        for p in probs.values():
            _number(p, 'laya.probabilities', 0, 1)
    elif laya['choice'] is not None or laya['probabilities'] is not None:
        raise ValueError('laya.choice/probabilities only when status ok')
    return record


def validate_choice_outcome(outcome: dict) -> dict:
    """What the agent actually chose, stored write-once at <root>/<decision>/outcome/<decisionId>.json."""
    _keys(outcome, CHOICE_OUTCOME_KEYS, 'choice outcome')
    if outcome['schema'] != CHOICE_OUTCOME_SCHEMA:
        raise ValueError('invalid schema')
    _enum(outcome['decision'], ADVISE_DECISIONS, 'decision')
    if not isinstance(outcome['decisionId'], str) or not HEX32.match(outcome['decisionId']):
        raise ValueError('invalid decisionId')
    if not isinstance(outcome['chosen'], str) or not CANDIDATE_ID.match(outcome['chosen']):
        raise ValueError('invalid chosen')
    if not isinstance(outcome['followed'], bool):
        raise ValueError('invalid followed')
    _ts(outcome['ts'], 'ts')
    return outcome


def validate_choice_shown(shown: dict) -> dict:
    """Marker that a recommendation was actually returned to the agent: <root>/<decision>/shown/<decisionId>.json."""
    _keys(shown, CHOICE_SHOWN_KEYS, 'choice shown marker')
    if shown['schema'] != CHOICE_SHOWN_SCHEMA:
        raise ValueError('invalid schema')
    _enum(shown['decision'], ADVISE_DECISIONS, 'decision')
    if not isinstance(shown['decisionId'], str) or not HEX32.match(shown['decisionId']):
        raise ValueError('invalid decisionId')
    if not isinstance(shown['recommendation'], str) or not CANDIDATE_ID.match(shown['recommendation']):
        raise ValueError('invalid recommendation')
    _hex64(shown['policySha256'], 'policySha256')
    _ts(shown['ts'], 'ts')
    return shown


# ---------------------------------------------------------------- registry and state

REGISTRY_ENTRY_KEYS = ('tier', 'defaultMode', 'reachableModes', 'incumbent', 'deployablePolicy', 'instrument',
                       'holdback', 'latencyBudgetMs', 'lambda', 'endpoint', 'model', 'gates')
COSIGN_ONLY_KEYS = ('deployablePolicy', 'instrument', 'holdback', 'latencyBudgetMs', 'lambda', 'endpoint', 'model',
                    'gates')
PROMOTE_GATE_KEYS = ('cohortSize', 'maxPerSession', 'alphaBase', 'maxAmbiguousShare', 'maxUnavailableShare')
DEMOTE_GATE_KEYS = ('minLabeled', 'alpha', 'maxUnavailableShare', 'operationalWindowDays', 'latencyReportOnlyDays')
ADVISE_KEYS = ('policy', 'gate', 'instrument', 'holdback', 'minCohort', 'minCriticalCases', 'alphaBase',
               'minCoverage', 'demote')
ADVISE_DEMOTE_KEYS = ('freshLabels', 'window', 'consecutive')
LOOPBACK_ENDPOINTS = ('http://127.0.0.1:8000', 'http://[::1]:8000')
ENDPOINT = re.compile(r'http://(127\.0\.0\.1|\[::1\]):(\d{1,5})\Z')


def validate_advise_config(advise, tier) -> dict:
    """The per-decision `advise` gate config (plan 2026-10-16 §3): the baseline gate that earns mode advise."""
    _keys(advise, ADVISE_KEYS, 'advise')
    if advise['policy'] != POLICY_ADVISE:
        raise ValueError('invalid advise.policy')
    if advise['gate'] != ADVISE_GATE:
        raise ValueError('invalid advise.gate')
    _enum(advise['instrument'], ADVISE_INSTRUMENTS, 'advise.instrument')
    _number(advise['holdback'], 'advise.holdback', 0, 0.5)
    _int(advise['minCohort'], 'advise.minCohort', lo=20)
    _int(advise['minCriticalCases'], 'advise.minCriticalCases', lo=0)
    _number(advise['alphaBase'], 'advise.alphaBase', 0, 0.2)
    if advise['alphaBase'] == 0:
        raise ValueError('invalid advise.alphaBase')
    _number(advise['minCoverage'], 'advise.minCoverage', 0, 1)
    demote = advise['demote']
    _keys(demote, ADVISE_DEMOTE_KEYS, 'advise.demote')
    _int(demote['freshLabels'], 'advise.demote.freshLabels', lo=5)
    _int(demote['window'], 'advise.demote.window', lo=20)
    _int(demote['consecutive'], 'advise.demote.consecutive', lo=1)
    if tier == 'critical' and advise['minCriticalCases'] < MIN_CRITICAL_ADVISE_CASES:
        raise ValueError('critical advise needs minCriticalCases >= 10')
    return advise


def validate_registry(registry: dict) -> dict:
    _keys(registry, ('schemaVersion', 'decisions'), 'registry')
    if registry['schemaVersion'] != REGISTRY_SCHEMA_VERSION:
        raise ValueError('invalid schemaVersion')
    decisions = registry['decisions']
    if not isinstance(decisions, dict) or not decisions:
        raise ValueError('invalid decisions')
    for decision_id, entry in decisions.items():
        _enum(decision_id, DECISIONS, 'decision id')
        # `advise` is optional (absent == null) so registries written before advise existed still validate.
        body = {k: v for k, v in entry.items() if k != 'advise'} if isinstance(entry, dict) else entry
        _keys(body, REGISTRY_ENTRY_KEYS, f'registry entry {decision_id}')
        _enum(entry['tier'], TIERS, 'tier')
        reachable = entry['reachableModes']
        if not isinstance(reachable, list) or not reachable or len(set(reachable)) != len(reachable):
            raise ValueError('invalid reachableModes')
        for mode in reachable:
            _enum(mode, MODES, 'reachableModes')
        _enum(entry['defaultMode'], reachable, 'defaultMode')
        if entry['defaultMode'] in EARNED_MODES:
            raise ValueError('invalid defaultMode')  # an earned mode needs a binding, so it is never a default
        if entry['tier'] == 'critical' and 'cosign' in reachable:
            raise ValueError('critical decisions never reach cosign')
        # The credential policy belongs to one manual-only decision; it is keyed on the policy, not on workflow-fit.
        credential = entry.get('deployablePolicy') == POLICY_CREDENTIAL
        if credential and (decision_id != CREDENTIAL_DECISION or entry['tier'] != 'workflow'):
            raise ValueError('the credential policy belongs to the workflow-tier credential-procedure decision')
        if decision_id == CREDENTIAL_DECISION and (not credential or 'advise' in reachable):
            raise ValueError('credential-procedure is manual-only credential guidance and never reaches advise')
        if 'cosign' in reachable:
            if not credential and (decision_id != 'skill-fit' or entry['tier'] != 'advisory'):
                raise ValueError('only advisory decisions may reach cosign')
            _enum(entry['deployablePolicy'], (POLICY_COSIGN, POLICY_CREDENTIAL), 'deployablePolicy')
            if entry['instrument'] != (POLICY_CREDENTIAL if credential else INSTRUMENT):
                raise ValueError('cosign requires its shipped policy instrument')
            endpoint_match = ENDPOINT.match(entry['endpoint']) if isinstance(entry['endpoint'], str) else None
            if not endpoint_match or not 1 <= int(endpoint_match.group(2)) <= 65535:
                raise ValueError('endpoint must be a literal loopback http address')
            if entry['model'] != 'typed-decisions':
                raise ValueError('invalid model')
            _number(entry['holdback'], 'holdback', 0, 0.5)
            _int(entry['latencyBudgetMs'], 'latencyBudgetMs', lo=100)
            if entry['latencyBudgetMs'] > 5000:
                raise ValueError('invalid latencyBudgetMs')
            if credential:
                if (entry['defaultMode'] != 'shadow' or entry['holdback'] != 0 or entry['lambda'] is not None
                        or entry['gates'] is not None or entry['incumbent'] != 'credential-cli-first'):
                    raise ValueError('credential workflow requires shadow default and manual-only fixed guidance')
            else:
                _number(entry['lambda'], 'lambda', 0)
                if entry['lambda'] == 0:
                    raise ValueError('invalid lambda')
                gates = entry['gates']
                _keys(gates, ('promote', 'demote'), 'gates')
                _keys(gates['promote'], PROMOTE_GATE_KEYS, 'gates.promote')
                _keys(gates['demote'], DEMOTE_GATE_KEYS, 'gates.demote')
                _int(gates['promote']['cohortSize'], 'cohortSize', lo=20)
                _int(gates['promote']['maxPerSession'], 'maxPerSession', lo=1)
                _number(gates['promote']['alphaBase'], 'alphaBase', 0, 0.2)
                for key in ('maxAmbiguousShare', 'maxUnavailableShare'):
                    _number(gates['promote'][key], key, 0, 1)
                _int(gates['demote']['minLabeled'], 'minLabeled', lo=10)
                _number(gates['demote']['alpha'], 'demote.alpha', 0, 0.5)
                _number(gates['demote']['maxUnavailableShare'], 'demote.maxUnavailableShare', 0, 1)
                _int(gates['demote']['operationalWindowDays'], 'operationalWindowDays', lo=1)
                _int(gates['demote']['latencyReportOnlyDays'], 'latencyReportOnlyDays', lo=0)
        else:
            for key in COSIGN_ONLY_KEYS:
                if entry[key] is not None:
                    raise ValueError(f'{key} must be null unless cosign is reachable')
        advise = entry.get('advise')
        if ('advise' in reachable) != (advise is not None):
            raise ValueError('advise is reachable if and only if it is configured')
        if advise is not None:
            validate_advise_config(advise, entry['tier'])
        if not isinstance(entry['incumbent'], str) or not REVISION.match(entry['incumbent']):
            raise ValueError('invalid incumbent')
    return registry


STATE_ENTRY_KEYS = ('mode', 'pinned', 'since', 'reason', 'policySha256', 'instrumentSha256', 'layaRevision',
                    'cohortId')
REASON = re.compile(r'[a-z_]{1,40}\Z')


def validate_state(state: dict, registry: dict) -> dict:
    """Validate machine-local registry state against the shipped registry."""
    _keys(state, ('schemaVersion', 'revision', 'updatedAt', 'decisions'), 'state')
    if state['schemaVersion'] != STATE_SCHEMA_VERSION:
        raise ValueError('invalid schemaVersion')
    _int(state['revision'], 'revision', lo=1)
    _ts(state['updatedAt'], 'updatedAt')
    if not isinstance(state['decisions'], dict):
        raise ValueError('invalid decisions')
    for decision_id, entry in state['decisions'].items():
        if decision_id not in registry['decisions']:
            raise ValueError('unknown decision in state')
        _keys(entry, STATE_ENTRY_KEYS, f'state entry {decision_id}')
        _enum(entry['mode'], registry['decisions'][decision_id]['reachableModes'], 'mode')
        if not isinstance(entry['pinned'], bool):
            raise ValueError('invalid pinned')
        _ts(entry['since'], 'since')
        if not isinstance(entry['reason'], str) or not REASON.match(entry['reason']):
            raise ValueError('invalid reason')
        for field in ('policySha256', 'instrumentSha256'):
            if entry[field] is not None:
                _hex64(entry[field], field)
        if entry['layaRevision'] is not None and (not isinstance(entry['layaRevision'], str)
                                                  or not REVISION.match(entry['layaRevision'])):
            raise ValueError('invalid layaRevision')
        if entry['cohortId'] is not None and (not isinstance(entry['cohortId'], str) or not HEX32.match(entry['cohortId'])):
            raise ValueError('invalid cohortId')
        if (entry['mode'] == 'cosign' and registry['decisions'][decision_id].get('deployablePolicy') == POLICY_CREDENTIAL
                and (entry['layaRevision'] in (None, 'unknown') or entry['cohortId'] is not None)):
            raise ValueError('credential cosign requires a known checkpoint and manual-only basis')
        if entry['mode'] in EARNED_MODES and (entry['policySha256'] is None or entry['instrumentSha256'] is None):
            raise ValueError(f"{entry['mode']} state must bind policy and instrument hashes")
        # shortcut: a hand-written cosign state may still omit layaRevision (the Node router suites build such
        # states); every mutate-written state binds one. Tighten once those fixtures pin a runtime revision.
        if entry['mode'] == 'advise' and entry['layaRevision'] is None:
            raise ValueError('advise state must bind the Laya revision')
    return state


AUDIT_KEYS_COMMIT = ('schema', 'phase', 'revision', 'previousRevision', 'at', 'actor', 'decision', 'fromMode',
                     'toMode', 'pinned', 'reason')
AUDIT_KEYS_INTENT = AUDIT_KEYS_COMMIT + ('state',)


def validate_audit(line: dict) -> dict:
    if not isinstance(line, dict):
        raise ValueError('audit line must be an object')
    _enum(line.get('phase'), AUDIT_PHASES, 'phase')
    _keys(line, AUDIT_KEYS_INTENT if line['phase'] == 'intent' else AUDIT_KEYS_COMMIT, 'audit line')
    if line['schema'] != AUDIT_SCHEMA:
        raise ValueError('invalid schema')
    _int(line['revision'], 'revision', lo=1)
    _int(line['previousRevision'], 'previousRevision', lo=0)
    if line['revision'] != line['previousRevision'] + 1:
        raise ValueError('revision must increment by one')
    _ts(line['at'], 'at')
    _enum(line['actor'], AUDIT_ACTORS, 'actor')
    _enum(line['decision'], DECISIONS, 'decision')
    if line['fromMode'] is not None:
        _enum(line['fromMode'], MODES, 'fromMode')
    _enum(line['toMode'], MODES, 'toMode')
    if not isinstance(line['pinned'], bool):
        raise ValueError('invalid pinned')
    if not isinstance(line['reason'], str) or not REASON.match(line['reason']):
        raise ValueError('invalid reason')
    if line['phase'] == 'intent' and not isinstance(line['state'], dict):
        raise ValueError('intent lines carry the full new state')
    return line
