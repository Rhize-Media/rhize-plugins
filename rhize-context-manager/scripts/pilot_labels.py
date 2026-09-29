#!/usr/bin/env python3
"""Versioned taxonomy labels for the v2 workflow pilot. Labels never authorize execution.

This module sits outside the collection source digest on purpose: changing it does not
orphan live observations. It stores labels beside, never inside, the legacy human label store.
Stored labels are immutable except for the documented supersession (see supersession_reason): a
family-derived AI choice may be replaced by an explicitly judged one, and any AI label by a human
label. The replaced record is archived, never deleted, and a human label is never replaced. An archive is
pending until the replacement is stored and committed after it; only committed archives are counted.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from workflow_selection import DEFAULT_ROOT, digest, locked_update, read_json
from decision_pilot import inventory
from decision_pilot_v2 import NORMALIZATION, canonical, ensure_root, joined, validate_observation
from pilot_routing import CHOICES

LABEL_SCHEMA = 'rhize-workflow-taxonomy-label-v1'
TAXONOMY_VERSION = 'rhize-workflow-taxonomy-v1'
# The reviewed 2026-09-28 proposal used identical enums; the alias is lossless.
TAXONOMY_ALIASES = {'rhize-workflow-taxonomy-proposal-2026-09-28-v1': TAXONOMY_VERSION}
BATCH_SCHEMA = 'rhize-ai-taxonomy-annotations-v1'
POLICY_SCHEMA = 'rhize-pilot-label-policy-v1'
HUMAN, AI = 'human_adjudicated', 'ai_model_reviewed'
BASES = (HUMAN, AI)
FAMILIES = ('feature_delivery', 'defect_resolution', 'code_health', 'platform_operations', 'content_growth',
            'research_analysis', 'knowledge_management', 'coordination', 'direct_response')
PHASES = ('triage', 'research', 'plan_design', 'implement', 'review', 'validate', 'release_operate',
          'not_applicable')
AREAS = ('frontend_ui', 'backend_api', 'database_data', 'infrastructure_delivery', 'automation_integrations',
         'security_identity', 'tests_quality', 'content_seo', 'documentation_knowledge')
STRATA = ('routine', 'elevated', 'critical')
RISK_FLAGS = ('security_privacy', 'financial', 'data_integrity', 'production_availability',
              'external_communication', 'authorization_boundary', 'safety_compliance')
FAMILY_MAP = 'derived:family-map-v1'
FAMILY_TO_CHOICE = {'content_growth': 'content', 'direct_response': 'none'}  # every other family: general
CHOICE_BASES = ('explicit', FAMILY_MAP)
# Research scores the routing choice itself, so it only accepts choices someone judged directly.
# A family-derived choice is kept for coverage and comparison but is not a routing target.
RESEARCH_CHOICE_BASES = ('explicit',)
REVIEW_VERDICTS = frozenset({'accept', 'revise'})
LABEL_KEYS = frozenset({'schema', 'opportunityId', 'sourceSha256', 'taxonomyVersion', 'basis', 'family', 'phase',
                        'areas', 'stratum', 'riskFlags', 'choice', 'choiceBasis', 'reviewer', 'reviewEvidenceSha256'})
LABEL_DIR = 'v2/taxonomy-labels'
# Replaced labels are moved here, never deleted; load_labels/export/report ignore this directory.
SUPERSEDED_DIR = 'v2/taxonomy-labels-superseded'
POLICY_FILE = 'label-policy.json'
POLICY_HISTORY = 'label-policy-history.jsonl'
MAX_BATCH = 32 * 1024 * 1024
# Richer categories need slice coverage, not a larger flat count: the 200-label floor stays and
# these gates hold until the corpus can say something per routing class, family and risk level.
GATES = {'minimumLabelsPerRoutingChoice': 15, 'minimumEvaluableFamilies': 4, 'minimumFamilyLabels': 15,
         'minimumNonRoutineLabels': 20, 'minimumCriticalLabelsForClaims': 20}
HEX = re.compile('[0-9a-f]{64}')
IDENTITY = re.compile('[A-Za-z0-9_-]{1,64}')


def derived_choice(family):
    return FAMILY_TO_CHOICE.get(family, 'general')


def _distinct(values, allowed, lowest, highest):
    return (isinstance(values, list) and lowest <= len(values) <= highest and len(set(values)) == len(values)
            and all(value in allowed for value in values))


def validate_label(value):
    if not isinstance(value, dict) or set(value) != LABEL_KEYS:
        raise ValueError('requires taxonomy label contract')
    if value['schema'] != LABEL_SCHEMA or value['taxonomyVersion'] != TAXONOMY_VERSION:
        raise ValueError('unsupported taxonomy label version')
    if not all(isinstance(value[key], str) and HEX.fullmatch(value[key])
               for key in ('opportunityId', 'sourceSha256', 'reviewEvidenceSha256')):
        raise ValueError('opportunity, source and review evidence digests required')
    if value['basis'] not in BASES:
        raise ValueError('invalid label basis')
    if value['family'] not in FAMILIES or value['phase'] not in PHASES or value['stratum'] not in STRATA:
        raise ValueError('invalid family, phase or stratum')
    if value['family'] == 'direct_response' and value['phase'] != 'not_applicable':
        raise ValueError('direct_response requires phase not_applicable')
    if value['areas'] != ['not_applicable'] and not _distinct(value['areas'], AREAS, 1, len(AREAS)):
        raise ValueError('areas must be distinct known areas or sole not_applicable')
    if not _distinct(value['riskFlags'], RISK_FLAGS, 0, len(RISK_FLAGS)):
        raise ValueError('risk flags must be distinct known flags')
    if value['choice'] not in CHOICES or value['choiceBasis'] not in CHOICE_BASES:
        raise ValueError('invalid routing choice or choice basis')
    if value['choiceBasis'] == FAMILY_MAP and value['choice'] != derived_choice(value['family']):
        raise ValueError('derived choice does not match the family map')
    if not isinstance(value['reviewer'], str) or not IDENTITY.fullmatch(value['reviewer']):
        raise ValueError('bounded reviewer identity required')
    return value


def bind(root, receipts, identity):
    ensure_root(root)
    path = root / 'v2/observations' / (identity + '.json')
    if path.is_symlink():
        raise ValueError('symlink observation refused')
    if not path.is_file():
        raise ValueError('no_v2_observation')
    observation = read_json(path)
    validate_observation(observation, receipts, identity, require_current_source=True, root=root)
    if observation['disposition']['eligible'] is not True:
        raise ValueError('only eligible routing decisions can receive labels')
    return observation


def supersession_reason(old, record):
    """Why `record` may replace the stored `old` label, or None when the old label stays immutable.

    Only an AI label can ever be replaced: by a human label, or by a label whose routing choice was
    judged explicitly when the old one was merely derived from its family. A human label, and an AI
    label whose choice was already judged directly, are never replaced.
    """
    if old.get('basis') != AI:
        return None
    if record['basis'] == HUMAN:
        return 'ai_to_human'
    if old.get('choiceBasis') == FAMILY_MAP and record['choiceBasis'] == 'explicit':
        return 'derived_to_explicit_choice'
    return None


def _same_record(old, record):
    return {k: v for k, v in old.items() if k != 'importedAt'} == record


def _archive_path(root, old):
    return root / SUPERSEDED_DIR / (old['opportunityId'] + '-' + old['evidenceSha256'][:16] + '.json')


ARCHIVE_MARKS = ('supersededBy', 'supersededReason', 'supersededAt', 'supersededState')


def _replacement_of(record):
    return {'evidenceSha256': record['evidenceSha256'], 'reviewEvidenceSha256': record['reviewEvidenceSha256'],
            'basis': record['basis'], 'choice': record['choice'], 'choiceBasis': record['choiceBasis'],
            'reviewer': record['reviewer']}


def _archive_superseded(root, old, record, reason):
    """Preserve the replaced label as a PENDING archive; commit_archive() marks it committed only once
    the replacement is stored. Safe to repeat after a crash: a pending archive is re-validated against the
    replacement being applied now and rewritten when it names a different one."""
    directory = root / SUPERSEDED_DIR
    if directory.is_symlink():
        raise ValueError('symlink superseded store refused')
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = _archive_path(root, old)
    if path.is_symlink():
        raise ValueError('symlink superseded record refused')
    replacement = _replacement_of(record)
    if path.exists():
        kept = read_json(path)
        if {k: v for k, v in kept.items() if k not in ARCHIVE_MARKS} != old:
            raise ValueError('superseded_archive_conflict')
        if kept.get('supersededState') == 'committed':
            raise ValueError('superseded_archive_conflict')
        if kept.get('supersededBy') == replacement and kept.get('supersededReason') == reason \
                and kept.get('supersededState') == 'pending':
            return path
    archived = {**old, 'supersededBy': replacement, 'supersededReason': reason, 'supersededState': 'pending',
                'supersededAt': datetime.now(timezone.utc).isoformat()}
    _private_write(path, json.dumps(archived, sort_keys=True, indent=2) + '\n', prefix='.superseded-')
    return path


def commit_archive(path):
    """Mark a pending archive committed: the replacement it names is now the stored label."""
    kept = read_json(path)
    if kept.get('supersededState') == 'committed':
        return
    _private_write(path, json.dumps({**kept, 'supersededState': 'committed'}, sort_keys=True, indent=2) + '\n',
                   prefix='.superseded-')


def reconcile_superseded(root):
    """Commit pending archives whose replacement is the stored label (a crash between replace and commit).

    A pending archive whose old label is still the stored one belongs to an unfinished replacement and is left alone.
    """
    directory = root / SUPERSEDED_DIR
    if directory.is_symlink():
        raise ValueError('symlink superseded store refused')
    if not directory.is_dir():
        return 0
    healed = 0
    for path in sorted(directory.glob('*.json')):
        if path.is_symlink():
            continue
        kept = read_json(path)
        if kept.get('supersededState') == 'committed':
            continue
        active = root / LABEL_DIR / (str(kept.get('opportunityId')) + '.json')
        if active.is_file() and not active.is_symlink() \
                and read_json(active).get('evidenceSha256') == (kept.get('supersededBy') or {}).get('evidenceSha256'):
            commit_archive(path)
            healed += 1
    return healed


def record_label(root, receipts, value, evidence_sha256, dry_run=False, supersede=False):
    """Validate, bind and store one label; identical re-imports are idempotent.

    A stored label is immutable unless `supersede` is set and supersession_reason() allows the
    replacement; the replaced record is then moved to SUPERSEDED_DIR with the reason.
    """
    validate_label(value)
    if not isinstance(evidence_sha256, str) or not HEX.fullmatch(evidence_sha256):
        raise ValueError('evidence digest required')
    observation = bind(root, receipts, value['opportunityId'])
    if value['sourceSha256'] != observation['sourceSha256']:
        raise ValueError('label must bind the exact collection source')
    if value['choice'] == 'content' and 'content_creation' in observation['request']['state'].get('exclusions', []):
        raise ValueError('label_contradicts_exclusions')
    record = {**value, 'evidenceSha256': evidence_sha256}
    store = root / LABEL_DIR
    existing = store / (value['opportunityId'] + '.json')
    if existing.is_symlink():
        raise ValueError('symlink label refused')
    if existing.is_file():
        old = read_json(existing)
        if _same_record(old, record):
            return 'already_recorded'
        if not supersede or supersession_reason(old, record) is None:
            raise ValueError('immutable label already exists')
        if dry_run:
            return 'would_supersede'
    elif dry_run:
        return 'would_record'

    outcome, archives = [], []

    def update(old):
        if old is not None:
            if _same_record(old, record):
                outcome.append('already_recorded')
                return old, False
            reason = supersession_reason(old, record) if supersede else None
            if reason is None:
                raise ValueError('immutable label already exists')
            archives.append(_archive_superseded(root, old, record, reason))
            outcome.append('superseded')
        else:
            outcome.append('recorded')
        return {**record, 'importedAt': datetime.now(timezone.utc).isoformat()}, True
    locked_update(store, value['opportunityId'], update)
    if archives:
        commit_archive(archives[0])
    return outcome[0]


def import_file(root, receipts, identity, evidence, supersede=False):
    if evidence.is_symlink():
        raise ValueError('symlink evidence refused')
    raw = evidence.read_bytes()
    value = read_json(evidence)
    if value.get('opportunityId') != identity:
        raise ValueError('evidence must bind the exact opportunity')
    status = record_label(root, receipts, value, digest(raw), supersede=supersede)
    if supersede:
        reconcile_superseded(root)
    return {'status': status, 'opportunityId': identity, 'basis': value['basis']}


def batch_label(record):
    """Convert one reviewed AI annotation into an ai_model_reviewed label, or name why not."""
    if record.get('schema') != BATCH_SCHEMA:
        return None, 'unsupported_schema'
    if record.get('status') != 'labeled':
        return None, 'status_' + str(record.get('status'))
    if TAXONOMY_ALIASES.get(record.get('taxonomyVersion'), record.get('taxonomyVersion')) != TAXONOMY_VERSION:
        return None, 'taxonomy_version'
    if record.get('humanAdjudicated') is not False or record.get('basis') != 'ai_generated_model_reviewed':
        return None, 'basis_mismatch'
    review = record.get('review') or {}
    if review.get('verdict') not in REVIEW_VERDICTS or review.get('actuallyRan') is not True:
        return None, 'not_model_reviewed'
    reviewer = 'ai-review-' + re.sub('[^A-Za-z0-9_-]', '-', str(review.get('observedModel') or 'unknown'))
    family = record.get('family')
    explicit = record.get('choice')
    if explicit is not None and explicit not in CHOICES:
        return None, 'invalid_choice'
    return {'schema': LABEL_SCHEMA, 'opportunityId': record.get('opportunityId'),
            'sourceSha256': record.get('sourceSha256'), 'taxonomyVersion': TAXONOMY_VERSION, 'basis': AI,
            'family': family, 'phase': record.get('phase'), 'areas': record.get('areas'),
            'stratum': record.get('stratum'), 'riskFlags': record.get('riskFlags'),
            'choice': explicit or derived_choice(family), 'choiceBasis': 'explicit' if explicit else FAMILY_MAP,
            'reviewer': reviewer[:64],
            'reviewEvidenceSha256': digest(canonical(record))}, None


def import_batch(root, receipts, annotations, dry_run=False, supersede=False):
    if annotations.is_symlink():
        raise ValueError('symlink annotations refused')
    if annotations.stat().st_size > MAX_BATCH:
        raise ValueError('annotation batch too large')
    raw = annotations.read_bytes()
    records = json.loads(raw)
    if not isinstance(records, list):
        raise ValueError('annotation batch must be a list')
    if not dry_run:
        reconcile_superseded(root)
    outcomes, skipped, dispositions = Counter(), Counter(), []
    for record in records:
        value, reason = batch_label(record) if isinstance(record, dict) else (None, 'malformed_record')
        identity = record.get('opportunityId') if isinstance(record, dict) else None
        if value is None:
            skipped[reason] += 1
            dispositions.append({'opportunityId': identity, 'result': 'not_a_label' if str(reason).startswith('status_')
                                 else 'skipped', 'reason': reason})
            continue
        try:
            result = record_label(root, receipts, value, digest(raw), dry_run=dry_run, supersede=supersede)
        except ValueError as exc:
            skipped[str(exc)] += 1
            dispositions.append({'opportunityId': identity, 'result': 'skipped', 'reason': str(exc)})
            continue
        outcomes[result] += 1
        dispositions.append({'opportunityId': identity, 'result': result, 'reason': None})
    return {'status': 'dry_run' if dry_run else 'imported', 'batchSha256': digest(raw), 'records': len(records),
            'results': dict(sorted(outcomes.items())), 'skipped': dict(sorted(skipped.items())), 'basis': AI,
            'supersede': supersede, 'dispositions': dispositions}


def load_policy(root):
    path = root / POLICY_FILE
    if path.is_symlink():
        raise ValueError('symlink policy refused')
    if not path.is_file():
        return {'schema': POLICY_SCHEMA, 'acceptedBases': [HUMAN], 'default': True}
    value = read_json(path)
    bases = value.get('acceptedBases')
    if (value.get('schema') != POLICY_SCHEMA or not isinstance(bases, list) or HUMAN not in bases
            or len(set(bases)) != len(bases) or any(base not in BASES for base in bases)):
        raise ValueError('invalid label policy')
    return value


def _private_write(path, data, prefix='.policy-'):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    handle, temporary = tempfile.mkstemp(prefix=prefix, dir=path.parent)
    try:
        with os.fdopen(handle, 'w') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except BaseException:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise


def set_policy(root, accept_ai, reason, actor):
    """Record who changed which label bases count for research, and why. Revocable."""
    if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 500:
        raise ValueError('a bounded reason is required')
    if not isinstance(actor, str) or not IDENTITY.fullmatch(actor):
        raise ValueError('bounded actor identity required')
    if root.is_symlink() or (root / POLICY_FILE).is_symlink() or (root / POLICY_HISTORY).is_symlink():
        raise ValueError('symlink policy refused')
    previous = load_policy(root)
    value = {'schema': POLICY_SCHEMA, 'acceptedBases': [HUMAN, AI] if accept_ai else [HUMAN],
             'reason': reason.strip(), 'setBy': actor, 'setAt': datetime.now(timezone.utc).isoformat()}
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(root / POLICY_HISTORY, os.O_CREAT | os.O_APPEND | os.O_WRONLY | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'a') as stream:
        stream.write(json.dumps({'previous': previous, 'next': value}, sort_keys=True) + '\n')
    _private_write(root / POLICY_FILE, json.dumps(value, sort_keys=True, indent=2) + '\n')
    return value


def load_labels(root):
    store = root / LABEL_DIR
    if store.is_symlink():
        raise ValueError('symlink label store refused')
    if not store.is_dir():
        return []
    labels = []
    for identity, value in inventory(store):
        stored = {k: v for k, v in value.items() if k not in {'evidenceSha256', 'importedAt'}}
        try:
            validate_label(stored)
        except ValueError:
            raise ValueError('taxonomy_label_contract_changed')
        if identity != value['opportunityId'] or not HEX.fullmatch(str(value.get('evidenceSha256'))):
            raise ValueError('taxonomy_label_contract_changed')
        labels.append(value)
    return labels


def taxonomy_coverage(rows):
    """Slice coverage for rows carrying family, routing_choice and stratum."""
    families = Counter(row['family'] for row in rows)
    choices = Counter(row['routing_choice'] for row in rows)
    strata = Counter(row['stratum'] for row in rows)
    evaluable = sorted(f for f, n in families.items() if n >= GATES['minimumFamilyLabels'])
    sparse_choices = [c for c in CHOICES if choices[c] < GATES['minimumLabelsPerRoutingChoice']]
    non_routine = strata['elevated'] + strata['critical']
    reasons = []
    if sparse_choices: reasons.append('insufficient_routing_class_coverage')
    if len(evaluable) < GATES['minimumEvaluableFamilies']: reasons.append('insufficient_family_coverage')
    if non_routine < GATES['minimumNonRoutineLabels']: reasons.append('insufficient_risk_coverage')
    return {'families': dict(sorted(families.items())), 'routingChoices': dict(sorted(choices.items())),
            'strata': dict(sorted(strata.items())), 'evaluableFamilies': evaluable,
            'sparseFamilies': [f for f in FAMILIES if families[f] < GATES['minimumFamilyLabels']],
            'sparseRoutingChoices': sparse_choices, 'nonRoutineLabels': non_routine,
            'criticalClaimsSupported': strata['critical'] >= GATES['minimumCriticalLabelsForClaims'],
            'gates': dict(GATES), 'holdReasons': reasons}


def export_cases(root, receipts, bases, choice_bases=RESEARCH_CHOICE_BASES):
    """Eligible, bound taxonomy-labeled v2 cases whose label and choice basis the caller accepts."""
    labels = {label['opportunityId']: label for label in load_labels(root)}
    cases = []
    for row in joined(root, receipts):
        label = labels.get(row['id'])
        if not label or label['basis'] not in bases or label['choiceBasis'] not in choice_bases:
            continue
        if row['bucket'] != 'eligible' or not row['observation']:
            continue
        observation, context = row['observation'], row['context']
        if label['sourceSha256'] != observation['sourceSha256']:
            raise ValueError('taxonomy_label_binding_changed')
        request = observation['request']
        input_sha = digest(canonical({'state': request['state'], 'questions': request['questions']}))
        keys = ['session:' + row['receipt']['sessionHash'], 'task:' + context['taskRootId'],
                'input:' + input_sha, 'prompt:' + row['receipt']['promptHash']]
        cases.append({'case_id': row['id'], 'group_id': input_sha, 'grouping_keys': sorted(keys),
            'normalization_version': NORMALIZATION, 'cohort_version': 'workflow-pilot-v2',
            'collection_source_sha256': observation['sourceSha256'], 'input_sha256': input_sha,
            'task_family': context['domain'], 'host': row['receipt']['host'],
            'decision_type': 'workflow_fit', 'stratum': label['stratum'], 'label_source': label['reviewEvidenceSha256'],
            'adjudicated': True, 'label_basis': label['basis'], 'label_schema': LABEL_SCHEMA,
            'taxonomy_version': label['taxonomyVersion'], 'family': label['family'], 'phase': label['phase'],
            'areas': label['areas'], 'risk_flags': label['riskFlags'], 'choice_basis': label['choiceBasis'],
            'state': request['state'], 'questions': request['questions'],
            'candidate_ids': list(CHOICES), 'routing_choice': label['choice'], 'arm_a_choice': row['armA'],
            'labels': {f'c{i}': choice == label['choice'] for i, choice in enumerate(CHOICES)},
            **({'arm_a': {f'c{i}': choice == row['armA'] for i, choice in enumerate(CHOICES)}} if row['armA'] else {})})
    if len({c['collection_source_sha256'] for c in cases}) > 1:
        raise ValueError('mixed_collection_sources')
    return cases


def write_cases(root, receipts, output, bases):
    cases = export_cases(root, receipts, bases)
    if not cases:
        return {'status': 'held', 'reason': 'no_accepted_taxonomy_labels', 'count': 0}
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(output, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'w') as stream:
        for case in cases:
            stream.write(json.dumps(case, sort_keys=True) + '\n')
    return {'status': 'exported', 'count': len(cases), 'sha256': digest(output.read_bytes()),
            'labelBasis': dict(sorted(Counter(c['label_basis'] for c in cases).items()))}


def superseded_count(root):
    """Committed supersessions only: a pending archive is an unfinished replacement, not a supersession."""
    directory = root / SUPERSEDED_DIR
    if directory.is_symlink():
        raise ValueError('symlink superseded store refused')
    if not directory.is_dir():
        return 0
    return sum(1 for path in directory.glob('*.json')
               if not path.is_symlink() and read_json(path).get('supersededState') == 'committed')


def report(root):
    policy = load_policy(root)
    labels = load_labels(root)
    accepted = [label for label in labels if label['basis'] in policy['acceptedBases']]
    scored = [label for label in accepted if label['choiceBasis'] in RESEARCH_CHOICE_BASES]
    rows = [{'family': l['family'], 'routing_choice': l['choice'], 'stratum': l['stratum']} for l in scored]
    count = lambda key, values: dict(sorted(Counter(v[key] for v in values).items()))
    return {'schema': 'rhize-taxonomy-label-report-v1', 'taxonomyVersion': TAXONOMY_VERSION, 'policy': policy,
            'labels': len(labels), 'superseded': superseded_count(root), 'byBasis': count('basis', labels),
            'accepted': len(accepted),
            'byFamily': count('family', accepted), 'byPhase': count('phase', accepted),
            'byStratum': count('stratum', accepted), 'byChoice': count('choice', accepted),
            'byChoiceBasis': count('choiceBasis', accepted), 'researchUsable': len(scored),
            'researchChoiceBases': list(RESEARCH_CHOICE_BASES), 'coverage': taxonomy_coverage(rows),
            'researchFloor': 200,
            'claimScope': 'label coverage only; ai_model_reviewed labels are model judgments, not human ground truth'}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root', type=Path, default=DEFAULT_ROOT / 'pilot')
    ap.add_argument('--receipts', type=Path, default=DEFAULT_ROOT / 'receipts')
    sub = ap.add_subparsers(dest='command', required=True)
    sp = sub.add_parser('import'); sp.add_argument('--id', required=True); sp.add_argument('--evidence', type=Path, required=True)
    sp.add_argument('--supersede', action='store_true',
                    help='allow the documented replacement of a derived-choice AI label; the old record is archived')
    sp = sub.add_parser('import-batch'); sp.add_argument('--annotations', type=Path, required=True)
    sp.add_argument('--dry-run', action='store_true')
    sp.add_argument('--supersede', action='store_true',
                    help='allow the documented replacement of derived-choice AI labels; old records are archived')
    sub.add_parser('report')
    sp = sub.add_parser('export'); sp.add_argument('--out', type=Path, required=True)
    sp = sub.add_parser('policy'); psub = sp.add_subparsers(dest='action', required=True)
    psub.add_parser('show')
    pp = psub.add_parser('set'); pp.add_argument('--accept-ai', action='store_true')
    pp.add_argument('--reason', required=True); pp.add_argument('--actor', required=True)
    args = ap.parse_args()
    try:
        if args.command == 'import':
            if not HEX.fullmatch(args.id):
                raise ValueError('invalid opportunity id')
            result = import_file(args.root, args.receipts, args.id, args.evidence, supersede=args.supersede)
        elif args.command == 'import-batch':
            result = import_batch(args.root, args.receipts, args.annotations, dry_run=args.dry_run, supersede=args.supersede)
        elif args.command == 'report':
            result = report(args.root)
        elif args.command == 'export':
            result = write_cases(args.root, args.receipts, args.out, load_policy(args.root)['acceptedBases'])
        elif args.action == 'show':
            result = load_policy(args.root)
        else:
            result = set_policy(args.root, args.accept_ai, args.reason, args.actor)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({'status': 'unavailable', 'reason': type(exc).__name__, 'detail': str(exc)}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
