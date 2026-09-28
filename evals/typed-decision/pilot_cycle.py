#!/usr/bin/env python3
"""Run one bounded development search when a reviewed workflow corpus changes.

Never consumes holdout, labels cases, changes a live candidate, or runs an agent.
"""
from __future__ import annotations
import argparse
import fcntl
import importlib.util
import json
import os
import re
import tempfile
from collections import Counter
from pathlib import Path
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'rhize-context-manager/scripts'))
from decision_pilot import export_cases, inventory, DEFAULT_ROOT, read_json, locked_update, digest
import pilot_labels


def candidates():
    result = [{'id': 'baseline', 'model': 'typed-decisions', 'instructions': {}, 'abstain_below': 0.0}]
    templates = [
        {},
        {f'c{i}': {'content': 'Is this specifically a RHIZE resource article task? A mention of research alone is insufficient.',
                  'general': 'Does this task call for an existing repeatable executable workflow rather than a simple explanation?',
                  'none': 'Should this task proceed without consulting either workflow family? Catalog match is a separate question.'}[choice]
         for i, choice in enumerate(('content', 'general', 'none'))}]
    for wording, instructions in enumerate(templates):
        for threshold in (.65, .8):
            result.append({'id': f'wording-{wording}-threshold-{threshold}', 'model': 'typed-decisions',
                           'instructions': instructions, 'abstain_below': threshold})
    return result


def private_write(path, value):
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(value, stream, sort_keys=True, indent=2)


def legacy_cycle(root, receipts, research_root, minimum=200, deadline=180, run=subprocess.run):
    if minimum < 20 or minimum > 10000 or not 1 <= deadline <= 1800:
        raise ValueError('invalid research bounds')
    labels = inventory(root / 'labels')
    if len(labels) < minimum:
        return {'status': 'held', 'reason': 'insufficient_human_labels', 'labels': len(labels), 'required': minimum}
    research_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if research_root.is_symlink() or root.is_symlink():
        raise ValueError('symlink research root refused')
    # Same lock as background inference: live pending observations remain durable.
    fd = os.open(root / 'worker.lock', os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {'status': 'held', 'reason': 'inference_busy'}
        evaluator = Path(__file__).with_name('research.py')
        evaluator_hash = digest(evaluator.read_bytes())
        key = digest(json.dumps({'labels': labels, 'candidates': candidates(), 'evaluator': evaluator_hash,
                                 'coordinator': digest(Path(__file__).read_bytes())}, sort_keys=True))
        run_dir = research_root / key
        if run_dir.is_symlink(): raise ValueError('symlink attempt refused')
        if run_dir.exists():
            status = run_dir / 'status.json'
            return {'status': 'unchanged', 'previous': read_json(status) if status.is_file() else {'status': 'interrupted'}, 'runId': key}
        run_dir.mkdir(mode=0o700)
        state = {'status': 'started', 'runId': key, 'evaluatorSha256': evaluator_hash, 'at': time.time()}
        def finish(value):
            private_write(run_dir / 'status.json', value)
            return value
        try:
            exported = export_cases(root, receipts, run_dir / 'cases.jsonl')
            if exported['status'] != 'exported':
                return finish({**state, 'status': 'held', 'reason': exported['reason']})
            if exported['count'] < minimum:
                return finish({**state, 'status': 'held', 'reason': 'insufficient_bound_labels', 'labels': exported['count']})
            # Stable group split across successive corpora: held-out groups never become training cases.
            spec = importlib.util.spec_from_file_location('typed_research', evaluator)
            module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
            rows = module.read_jsonl(run_dir / 'cases.jsonl')
            manifest = module.prepare_corpus(rows, 'workflow-pilot-v1', run_dir / 'split')
            count = manifest['split_counts']['train'] + manifest['split_counts']['validation']
            options = candidates()
            if count * len(options) > 2400:
                return finish({**state, 'status': 'held', 'reason': 'request_budget_exceeded', 'requests': count * len(options)})
            private_write(run_dir / 'candidates.json', options)
            command = [sys.executable, str(evaluator), '--phase', 'search', '--manifest', str(run_dir / 'split/manifest.json'),
                       '--train', str(run_dir / 'split/train.jsonl'), '--validation', str(run_dir / 'split/validation.jsonl'),
                       '--candidates', str(run_dir / 'candidates.json'), '--ledger', str(run_dir / 'ledger.jsonl')]
            started = time.monotonic()
            completed = run(command, capture_output=True, text=True, timeout=deadline)
            if completed.returncode:
                return finish({**state, 'status': 'failed', 'reason': 'evaluator_failed', 'exitCode': completed.returncode})
            if digest(evaluator.read_bytes()) != evaluator_hash:
                raise ValueError('evaluator changed during search')
            ledger = module.read_ledger(run_dir / 'ledger.jsonl')
            kept = [row for row in ledger if row['status'] == 'keep']
            if not kept:
                raise ValueError('no kept candidate receipt')
            winner = kept[-1]
            selected = next(c for c in options if module.digest(c) == winner['candidate_sha256'])
            private_write(run_dir / 'frozen-candidate.json', [selected])
            return finish({**state, 'status': 'review_required', 'candidateId': selected['id'],
                           'candidateSha256': winner['candidate_sha256'], 'corpusSha256': exported['sha256'],
                           'releaseEligible': manifest['release_eligible'], 'holdout': 'not_run', 'promotion': 'not_performed',
                           'wallMs': round((time.monotonic() - started) * 1000)})
        except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
            return finish({**state, 'status': 'failed', 'reason': type(exc).__name__})


COHORT = 'workflow-pilot-v2'
NORMALIZATION = 'workflow-input-v2'
GROUP_PATTERN = re.compile(r'(session|parent|task|input|template|prompt):[0-9a-f]{64}\Z')
SPLITS = ('train', 'validation', 'holdout')


def grouping(rows, assignments):
    """Connect all duplicate identities; immutable past splits constrain new links."""
    parent = {}
    def find(key):
        parent.setdefault(key, key)
        root = key
        while parent[root] != root:
            root = parent[root]
        while parent[key] != key:
            old = parent[key]; parent[key] = root; key = old
        return root
    def union(keys):
        base = find(keys[0])
        for key in keys[1:]:
            parent[find(key)] = base
    for record in assignments:
        if (record.get('cohort') != COHORT or record.get('normalization') != NORMALIZATION
                or record.get('split') not in SPLITS):
            raise ValueError('invalid_split_assignment')
        keys = record.get('keys')
        if (not isinstance(keys, list) or not keys or any(not isinstance(k, str)
                or not GROUP_PATTERN.fullmatch(k) or k.split(':')[1] == '0' * 64 for k in keys)):
            raise ValueError('invalid_grouping_keys')
        union(keys)
    for row in rows:
        keys = row.get('grouping_keys')
        if (not isinstance(keys, list) or not keys or len(keys) > 40
                or any(not isinstance(k, str) or not GROUP_PATTERN.fullmatch(k)
                       or k.split(':')[1] == '0' * 64 for k in keys)):
            raise ValueError('invalid_grouping_keys')
        union(keys)
    components = {}
    for key in parent:
        components.setdefault(find(key), set()).add(key)
    previous = {}
    for record in assignments:
        previous.setdefault(find(record['keys'][0]), set()).add(record['split'])
    if any(len(values) > 1 for values in previous.values()):
        raise ValueError('cross_split_bridge')
    mapping, records = {}, []
    for keys in components.values():
        keys = sorted(keys)
        group_id = digest(json.dumps(keys, separators=(',', ':')))
        bucket = int(digest(COHORT + ':' + group_id)[:8], 16) % 4
        old = previous.get(find(keys[0]), set())
        split = next(iter(old)) if old else ('train' if bucket < 2 else 'validation' if bucket == 2 else 'holdout')
        records.append({'cohort': COHORT, 'normalization': NORMALIZATION, 'keys': keys, 'split': split})
        for key in keys:
            mapping[key] = (group_id, split)
    grouped = [{**row, 'group_id': mapping[row['grouping_keys'][0]][0]} for row in rows]
    split_map = {row['group_id']: mapping[row['grouping_keys'][0]][1] for row in grouped}
    return grouped, split_map, records


def diversity(rows):
    groups = Counter(row['group_id'] for row in rows)
    families = Counter(row['task_family'] for row in rows)
    result = {'labels': len(rows), 'groups': len(groups), 'domains': dict(sorted(families.items())),
              'hosts': dict(sorted(Counter(row['host'] for row in rows).items())),
              'largestGroupShare': max(groups.values(), default=0) / len(rows) if rows else 0}
    reasons = []
    if len(groups) < 20: reasons.append('insufficient_independent_groups')
    if len(families) < 2: reasons.append('insufficient_domains')
    if any(count < 20 for count in families.values()): reasons.append('insufficient_domain_labels')
    if result['largestGroupShare'] > .2: reasons.append('group_concentration')
    return {**result, 'holdReasons': reasons}


def file_fingerprint(path):
    """Bounded opaque identity also distinguishes missing/corrupt input repairs."""
    if path.is_symlink():
        return {'status': 'symlink_refused'}
    try:
        with path.open('rb') as stream:
            raw = stream.read(16 * 1024 * 1024 + 1)
        if len(raw) > 16 * 1024 * 1024:
            raise ValueError('input_fingerprint_too_large')
        return {'status': 'present', 'sha256': digest(raw)}
    except FileNotFoundError:
        return {'status': 'missing'}
    except OSError as exc:
        return {'status': 'unreadable', 'errorType': type(exc).__name__}


def bound_input_fingerprint(root, receipts):
    directories = {'receipts': receipts, 'context': receipts.parent / 'task-context',
                   'context_holds': receipts.parent / 'task-context-holds',
                   'consultations': receipts.parent / 'consultations',
                   **{name: root / 'v2' / name for name in ('observations', 'results', 'outcomes')}}
    result = {}
    for name, directory in directories.items():
        if directory.is_symlink():
            result[name] = {'status': 'symlink_refused'}
            continue
        paths = sorted(directory.glob('*.json'))
        if len(paths) > 10000:
            raise ValueError('input_inventory_ceiling')
        result[name] = {digest(path.name): file_fingerprint(path) for path in paths}
    return digest(json.dumps(result, sort_keys=True))


def legacy_manifest_fingerprint(research_root):
    paths = sorted(research_root.glob('*/split/manifest.json'))
    if len(paths) > 10000:
        raise ValueError('legacy_manifest_ceiling')
    return digest(json.dumps({digest(str(path.relative_to(research_root))): file_fingerprint(path)
                              for path in paths}, sort_keys=True))


def legacy_holdout_keys(research_root):
    """Only unchanged session/prompt identities compare across collection versions."""
    keys = set()
    for manifest in research_root.glob('*/split/manifest.json'):
        try:
            if manifest.is_symlink(): raise ValueError('symlink manifest')
            value = read_json(manifest)
            membership = value.get('holdout_grouping_keys')
            if (not isinstance(membership, list) or any(not isinstance(k, str)
                    or not GROUP_PATTERN.fullmatch(k) or k.split(':')[1] == '0' * 64 for k in membership)):
                raise ValueError('invalid membership')
            comparable = {k for k in membership if k.startswith(('session:', 'prompt:'))}
            if not comparable and value.get('split_counts', {}).get('holdout') != 0:
                raise ValueError('missing comparable membership')
            keys.update(comparable)
        except (OSError, ValueError, TypeError):
            raise ValueError('legacy_holdout_membership_unavailable') from None
    return keys


def cycle(root, receipts, research_root, minimum=200, deadline=180, run=subprocess.run):
    """Automatic v2 development only. Original v1 experiments remain untouched."""
    if type(minimum) is not int or type(deadline) is not int or not 200 <= minimum <= 10000 or not 1 <= deadline <= 1800:
        raise ValueError('automatic research requires at least 200 labels')
    if root.is_symlink() or research_root.is_symlink():
        raise ValueError('symlink research root refused')
    version_root = research_root / COHORT
    if version_root.is_symlink(): raise ValueError('symlink cohort root refused')
    version_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    def held(reason, **facts):
        value = {'status': 'held', 'cohort': COHORT, 'reason': reason, **facts}
        directory = version_root / 'holds'
        if directory.is_symlink(): raise ValueError('symlink hold directory refused')
        directory.mkdir(exist_ok=True, mode=0o700)
        path = directory / (digest(json.dumps(value, sort_keys=True)) + '.json')
        if not path.exists():
            try: private_write(path, value)
            except FileExistsError:
                if read_json(path) != value: raise ValueError('conflicting hold receipt')
        return value
    # Legacy human labels and versioned taxonomy labels are separate answer keys; never merged.
    labels = inventory(root / 'v2/labels')
    taxonomy_labels = pilot_labels.load_labels(root)
    policy = pilot_labels.load_policy(root) if taxonomy_labels else None
    if taxonomy_labels:
        bases = list(policy['acceptedBases'])
        usable = [label for label in taxonomy_labels if label['basis'] in bases
                  and label['choiceBasis'] in pilot_labels.RESEARCH_CHOICE_BASES]
        label_facts = {'labelSchema': pilot_labels.LABEL_SCHEMA, 'acceptedBases': bases,
                       'labelBasis': dict(sorted(Counter(label['basis'] for label in usable).items())),
                       'taxonomyLabels': len(taxonomy_labels),
                       'derivedChoiceLabels': sum(label['choiceBasis'] not in pilot_labels.RESEARCH_CHOICE_BASES
                                                  for label in taxonomy_labels if label['basis'] in bases)}
        if labels:
            return held('mixed_label_schemas', labels=len(labels), **label_facts)
        labels = usable
        if len(labels) < minimum:
            return held('insufficient_accepted_labels', labels=len(labels), required=minimum, **label_facts)
    else:
        label_facts = {'labelBasis': {'human_adjudicated': len(labels)}}
        if len(labels) < minimum:
            return held('insufficient_human_labels', labels=len(labels), required=minimum, **label_facts)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(root / 'worker.lock', os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'w') as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: return held('inference_busy')
        evaluator = Path(__file__).with_name('research.py')
        decoder = REPO / 'rhize-context-manager/scripts/pilot_routing.py'
        preflight_key = digest(json.dumps({'labels': labels, 'minimum': minimum, 'deadline': deadline,
            **({'labelPolicy': policy} if policy else {}),
            'boundInputSha256': bound_input_fingerprint(root, receipts),
            'sources': {str(path.relative_to(REPO)): digest(path.read_bytes()) if path.is_file() else None
                        for path in (evaluator, decoder, Path(__file__),
                                     REPO / 'rhize-context-manager/scripts/decision_pilot.py',
                                     REPO / 'rhize-context-manager/scripts/decision_pilot_v2.py',
                                     REPO / 'rhize-context-manager/scripts/pilot_labels.py',
                                     REPO / 'rhize-context-manager/scripts/workflow_task_context.py',
                                     REPO / 'rhize-context-manager/scripts/workflow_selection.py')}}, sort_keys=True))
        failures = version_root / 'preflight-failures'
        if failures.is_symlink(): raise ValueError('symlink failure directory refused')
        failure_path = failures / (preflight_key + '.json')
        if failure_path.is_file():
            return {'status': 'unchanged', 'previous': read_json(failure_path), 'runId': preflight_key}
        try:
            spec = importlib.util.spec_from_file_location('typed_research', evaluator)
            module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
            with tempfile.TemporaryDirectory(prefix='.export-', dir=version_root) as temporary:
                exported_path = Path(temporary) / 'cases.jsonl'
                exported = (pilot_labels.write_cases(root, receipts, exported_path, bases) if policy
                            else export_cases(root, receipts, exported_path, cohort='v2'))
                if exported['status'] != 'exported':
                    return held(exported['reason'], labels=len(labels), required=minimum, **label_facts)
                rows = module.read_jsonl(exported_path)
                corpus_bytes = exported_path.read_bytes()
        except (OSError, ValueError, KeyError, TypeError) as exc:
            if isinstance(exc, ValueError) and str(exc) == 'mixed_collection_sources':
                return held('mixed_collection_source')
            if isinstance(exc, ValueError) and str(exc) == 'label_contradicts_exclusions':
                return held('label_contradicts_exclusions', labels=len(labels), required=minimum, **label_facts)
            failure = {'status': 'failed', 'cohort': COHORT, 'reason': 'invalid_bound_corpus',
                       'errorType': type(exc).__name__, 'runId': preflight_key}
            try:
                failures.mkdir(exist_ok=True, mode=0o700)
                private_write(failure_path, failure)
            except OSError:
                failure['persistence'] = 'unavailable'
            return failure
        if len(rows) < minimum: return held('insufficient_bound_labels', labels=len(rows), required=minimum, **label_facts)
        if any(row.get('cohort_version') != COHORT for row in rows): return held('mixed_cohort')
        if any(row.get('normalization_version') != NORMALIZATION for row in rows): return held('mixed_normalization')
        if any(row.get('task_family') not in {'content', 'software', 'operations', 'general'}
               or row.get('host') not in {'claude', 'codex'} for row in rows):
            return held('invalid_coverage_metadata')
        sources = {row.get('collection_source_sha256') for row in rows}
        if len(sources) != 1 or any(not isinstance(s, str) or not re.fullmatch('[0-9a-f]{64}', s) for s in sources):
            return held('mixed_collection_source')
        config = {'minimum': minimum, 'deadline': deadline, 'minimumGroups': 20, 'minimumDomains': 2,
                  'minimumDomainLabels': 20, 'maximumGroupShare': .2, 'normalization': NORMALIZATION}
        if policy:
            config.update({'labelSchema': pilot_labels.LABEL_SCHEMA, 'taxonomyVersion': pilot_labels.TAXONOMY_VERSION,
                           'acceptedBases': bases, 'researchChoiceBases': list(pilot_labels.RESEARCH_CHOICE_BASES),
                           'labelPolicySha256': digest(json.dumps(policy, sort_keys=True)),
                           'taxonomyGates': dict(pilot_labels.GATES)})
        used_bases = dict(sorted(Counter(row.get('label_basis', 'human_adjudicated') for row in rows).items()))
        versions = {'evaluator': digest(evaluator.read_bytes()), 'scorer': digest(decoder.read_bytes()),
                    'coordinator': digest(Path(__file__).read_bytes())}
        legacy_sha = legacy_manifest_fingerprint(research_root)
        key = digest(json.dumps({'legacyMembershipSha256': legacy_sha, 'corpus': digest(corpus_bytes), 'cohort': COHORT, 'source': next(iter(sources)),
                                 'config': config, 'versions': versions, 'candidates': candidates()}, sort_keys=True))
        run_dir = version_root / key
        if run_dir.is_symlink(): raise ValueError('symlink attempt refused')
        if run_dir.exists():
            status = run_dir / 'status.json'
            return {'status': 'unchanged', 'runId': key,
                    'previous': read_json(status) if status.is_file() else {'status': 'interrupted'}}
        run_dir.mkdir(mode=0o700)
        state = {'status': 'started', 'cohort': COHORT, 'runId': key, 'versions': versions,
                 'sourceSha256': next(iter(sources)), 'legacyMembershipSha256': legacy_sha,
                 'config': config, 'labelBasis': used_bases, 'at': time.time(),
                 **({'claimScope': 'exploratory: includes model-reviewed labels; no human-accuracy, holdout or promotion claim'}
                    if set(used_bases) != {'human_adjudicated'} else {})}
        private_write(run_dir / 'started.json', state)
        def finish(value):
            private_write(run_dir / 'status.json', value)
            return value
        try:
            old_keys = legacy_holdout_keys(research_root)
            if any(old_keys.intersection(row['grouping_keys']) for row in rows):
                return finish({**state, 'status': 'held', 'reason': 'legacy_holdout_overlap'})
            assignment_dir = version_root / 'assignments'
            assignments = [value for _, value in inventory(assignment_dir)]
            rows, split_map, records = grouping(rows, assignments)
            coverage = diversity(rows)
            if policy:
                taxonomy = pilot_labels.taxonomy_coverage(rows)
                coverage = {**coverage, 'taxonomy': taxonomy,
                            'holdReasons': coverage['holdReasons'] + taxonomy['holdReasons']}
            if coverage['holdReasons']:
                return finish({**state, 'status': 'held', 'reason': 'insufficient_diversity', 'coverage': coverage})
            assignment_dir.mkdir(exist_ok=True, mode=0o700)
            for record in records:
                path = assignment_dir / (digest(json.dumps(record, sort_keys=True)) + '.json')
                if not path.exists(): private_write(path, record)
            manifest = module.prepare_corpus(rows, COHORT, run_dir / 'split', split_assignments=split_map)
            count = manifest['split_counts']['train'] + manifest['split_counts']['validation']
            options = candidates()
            if count * len(options) > 2400:
                return finish({**state, 'status': 'held', 'reason': 'request_budget_exceeded', 'requests': count * len(options)})
            private_write(run_dir / 'candidates.json', options)
            command = [sys.executable, str(evaluator), '--phase', 'search', '--manifest', str(run_dir / 'split/manifest.json'),
                       '--train', str(run_dir / 'split/train.jsonl'), '--validation', str(run_dir / 'split/validation.jsonl'),
                       '--candidates', str(run_dir / 'candidates.json'), '--ledger', str(run_dir / 'ledger.jsonl')]
            if legacy_manifest_fingerprint(research_root) != legacy_sha:
                return finish({**state, 'status': 'held', 'reason': 'legacy_metadata_changed'})
            started = time.monotonic()
            completed = run(command, capture_output=True, text=True, timeout=deadline)
            if completed.returncode:
                return finish({**state, 'status': 'failed', 'reason': 'evaluator_failed', 'exitCode': completed.returncode})
            if legacy_manifest_fingerprint(research_root) != legacy_sha:
                raise ValueError('legacy_metadata_changed_during_search')
            if digest(evaluator.read_bytes()) != versions['evaluator'] or digest(decoder.read_bytes()) != versions['scorer']:
                raise ValueError('evaluator_or_scorer_changed')
            kept = [row for row in module.read_ledger(run_dir / 'ledger.jsonl') if row['status'] == 'keep']
            if not kept: raise ValueError('no_kept_candidate_receipt')
            winner = kept[-1]
            selected = next(c for c in options if module.digest(c) == winner['candidate_sha256'])
            private_write(run_dir / 'frozen-candidate.json', [selected])
            return finish({**state, 'status': 'review_required', 'candidateId': selected['id'],
                           'candidateSha256': winner['candidate_sha256'], 'corpusSha256': exported['sha256'],
                           'releaseEligible': False, 'coverage': coverage, 'holdout': 'not_run', 'promotion': 'not_performed',
                           'wallMs': round((time.monotonic() - started) * 1000)})
        except ValueError as exc:
            reason = str(exc)
            if reason in {'cross_split_bridge', 'legacy_holdout_overlap', 'legacy_holdout_membership_unavailable'}:
                return finish({**state, 'status': 'held', 'reason': reason})
            return finish({**state, 'status': 'failed', 'reason': 'ValueError'})
        except (OSError, KeyError, TypeError, StopIteration, subprocess.TimeoutExpired) as exc:
            return finish({**state, 'status': 'failed', 'reason': type(exc).__name__})


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root', type=Path, default=DEFAULT_ROOT / 'pilot')
    ap.add_argument('--receipts', type=Path, default=DEFAULT_ROOT / 'receipts')
    ap.add_argument('--research-root', type=Path, required=True)
    ap.add_argument('--minimum-labels', type=int, default=200)
    ap.add_argument('--deadline-seconds', type=int, default=180)
    args = ap.parse_args()
    try:
        result = cycle(args.root, args.receipts, args.research_root, args.minimum_labels, args.deadline_seconds)
    except (OSError, ValueError, TypeError) as exc:
        invalid_bounds = not 200 <= args.minimum_labels <= 10000 or not 1 <= args.deadline_seconds <= 1800
        result = {'status': 'failed', 'reason': 'invalid_research_bounds' if invalid_bounds else 'coordinator_contract_failure',
                  'errorType': type(exc).__name__}
    print(json.dumps(result, sort_keys=True))
    return 1 if result['status'] == 'failed' else 0


if __name__ == '__main__':
    raise SystemExit(main())
