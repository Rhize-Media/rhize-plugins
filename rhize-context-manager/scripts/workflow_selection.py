#!/usr/bin/env python3
"""Bounded workflow opportunity/decision capture shared by Claude and Codex.

No model, registry execution, transcript scan or Stop continuation. Receipts are
observations; a suggestion never establishes selection, execution or correctness.
"""
from __future__ import annotations
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import shlex
import tempfile
import time
from datetime import datetime, timezone

SCHEMA = 'rhize-workflow-selection-v1'
MAX_INPUT = 65536
MAX_RECEIPT = 131072
DEFAULT_ROOT = Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share'))) / 'rhize/workflow-selection'


def digest(value):
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def binding(variant):
    return {'local-draft': 'content-engine-local', 'cms-draft': 'content-engine'}.get(variant)


def read_json(path, maximum=MAX_RECEIPT):
    if path.stat().st_size > maximum:
        raise ValueError('oversized JSON')
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError('expected object')
    return value


def locked_update(root, identity, update):
    if not re.fullmatch(r'[0-9a-f]{64}', identity):
        raise ValueError('invalid opportunity id')
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if root.is_symlink():
        raise ValueError('receipt root cannot be a symlink')
    path = root / (identity + '.json')
    flags = os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(root / (identity + '.lock'), flags, 0o600)
    with os.fdopen(fd, 'r+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if path.is_symlink():
            raise ValueError('receipt cannot be a symlink')
        old = read_json(path) if path.exists() else None
        value, changed = update(old)
        if changed:
            data = json.dumps(value, sort_keys=True, indent=2) + '\n'
            if len(data.encode()) > MAX_RECEIPT:
                raise ValueError('receipt size budget exceeded')
            handle, temporary = tempfile.mkstemp(prefix='.receipt-', dir=root)
            try:
                with os.fdopen(handle, 'w') as stream:
                    stream.write(data); stream.flush(); os.fsync(stream.fileno())
                os.replace(temporary, path)
            finally:
                if os.path.exists(temporary): os.unlink(temporary)
        return value, changed


def opportunity(payload, host, root, config):
    prompt = payload.get('prompt')
    session = payload.get('session_id') or payload.get('thread_id')
    if not isinstance(prompt, str) or not isinstance(session, str) or not prompt or len(prompt) > 16384:
        return None, False
    native_turn = payload.get('turn_id') or payload.get('turnId') or payload.get('prompt_id') or payload.get('event_id')
    task = str(native_turn or digest(prompt))
    identity = digest(host + ':' + session + ':' + task)
    if not native_turn:
        base = identity
        def slot(index):
            if index is None:
                return {'current': base, 'sequence': 0}, True
            previous = root / (index['current'] + '.json')
            if previous.exists() and read_json(previous).get('terminalStatus') is not None:
                sequence = index['sequence'] + 1
                return {'current': digest(base + ':' + str(sequence)), 'sequence': sequence}, True
            return index, False
        index, _ = locked_update(root / 'identities', base, slot)
        identity = index['current']
    if (root / (identity + '.json')).exists():
        return locked_update(root, identity, lambda old: (old, False))
    classification = {'eligible': None, 'workflow': None, 'variant': None, 'reason': 'awaiting_agent_scope_decision'}
    started = time.monotonic()
    result = {'schemaVersion': SCHEMA, 'opportunityId': identity, 'host': host,
              'sessionHash': digest(session), 'taskHash': digest(task), 'identityMode': 'native-turn' if native_turn else 'prompt-fallback', 'promptHash': digest(prompt),
              'observedAt': datetime.now(timezone.utc).isoformat(), 'variant': 'B-agent-decision-v1',
              'classification': classification, 'recommendation': None, 'selection': None,
              'events': [], 'terminalStatus': None, 'capabilityStatus': 'not_requested',
              'selectorDigest': digest(Path(__file__).read_bytes())}
    # Present the canonical entrypoint, not a guessed task classification.
    # The current task agent has the conversation/authorization context.
    result['catalog'] = {'content': 'procedural-memory:rhize-content-engine',
                         'general': 'procedural-memory:procedural-memory'}
    result['recommendation'] = 'consult_catalog_before_substantial_work'
    result['capabilityStatus'] = 'lookup_not_requested'
    result['lookupDurationMs'] = round((time.monotonic() - started) * 1000, 3)
    return locked_update(root, identity, lambda old: (old, False) if old else (result, True))


def hook_message(receipt):
    return ("Workflow selection checkpoint before substantial work. For RHIZE resource articles, consult "
            "procedural-memory:rhize-content-engine; for other repeatable multi-step work use "
            "procedural-memory:procedural-memory recall --json. Decide from the user's full request: reuse, adapt, "
            "no_match, unavailable, candidate, or skip for a simple/non-workflow task. Do not infer publishing "
            "permission or invent a matching workflow. Record the choice before composition with "
            f"python3 {shlex.quote(str(Path(__file__).resolve()))} decide --id {receipt['opportunityId']} (see the skill), then record "
            "actual execution, validation and capture separately. This checkpoint grants no execution authority.")


def decide(root, args):
    def update(old):
        if old is None:
            raise ValueError('opportunity not found')
        selected = {'decision': args.decision, 'workflow': args.workflow, 'variant': args.variant,
                    'reason': args.reason, 'runId': getattr(args, 'run_id', None), 'sourceSha256': getattr(args, 'source_sha256', None), 'at': datetime.now(timezone.utc).isoformat(), 'basis': 'operator_selection'}
        if args.decision in {'reuse', 'adapt'} and (not args.workflow or not args.variant):
            raise ValueError('reuse/adapt requires workflow and variant')
        if args.decision in {'reuse', 'adapt'} and (not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', selected['runId'] or '') or not re.fullmatch(r'[0-9a-f]{64}', selected['sourceSha256'] or '')):
            raise ValueError('reuse/adapt requires --run-id and --source-sha256 of the selected artifact')
        if args.decision == 'skip' and (args.workflow or args.variant):
            raise ValueError('skip cannot select a workflow or variant')
        if args.decision in {'reuse', 'adapt'} and args.workflow == 'rhize-content-engine' and args.variant not in {'local-draft', 'cms-draft'}:
            raise ValueError('unsupported Content Engine execution variant')
        if old['terminalStatus'] is not None: raise ValueError('terminal receipt is sealed')
        if old['selection'] is not None:
            prior = {k:v for k,v in old['selection'].items() if k != 'at'}
            current = {k:v for k,v in selected.items() if k != 'at'}
            if prior != current: raise ValueError('selection already recorded; create a new opportunity for changed intent')
            return old, False
        old['selection'] = selected
        old['classification'] = {'eligible': args.decision != 'skip', 'workflow': args.workflow, 'variant': args.variant, 'reason': args.reason}
        # A decision records operator intent; runtime preflight remains authoritative.
        if args.decision in {'reuse', 'adapt'}:
            old['capabilityStatus'] = 'metadata_launcher_unconfigured'
        if args.decision in {'reuse', 'adapt'} and getattr(args, 'config', None) and args.config.is_file():
            config = read_json(args.config)
            launcher = config.get('proceduralLauncher')
            if launcher and Path(launcher).is_absolute():
                from memory_context.procedural_adapter import recall
                adapter = recall(Path(launcher), binding(args.variant) or args.workflow, tenant='local', project='workflow-selection')
                old['capabilityStatus'] = adapter['status']
                old['references'] = adapter['candidates']
            else:
                old['capabilityStatus'] = 'metadata_launcher_unconfigured'
        return old, True
    return locked_update(root, args.id, update)[0]


def record(root, args):
    evidence = Path(args.evidence)
    if evidence.stat().st_size > 16 * 1024 * 1024: raise ValueError('evidence too large')
    with evidence.open('rb') as stream: raw = stream.read(16 * 1024 * 1024 + 1)
    if len(raw) > 16 * 1024 * 1024: raise ValueError('evidence too large')
    if args.event == 'capture' and args.status == 'passed':
        receipt = json.loads(raw)
        if not isinstance(receipt, dict) or receipt.get('schemaVersion') not in {1, 2}:
            raise ValueError('capture requires the canonical benchmark writer receipt')
        if receipt.get('afterCount', 0) != receipt.get('beforeCount', 0) + 1 or not re.fullmatch(r'[0-9a-f]{64}', receipt.get('rowSha256', '')) or not receipt.get('capturedAt'):
            raise ValueError('invalid benchmark append receipt')
    event = {'event': args.event, 'status': args.status, 'evidenceSha256': digest(raw),
             'at': datetime.now(timezone.utc).isoformat(), 'basis': 'operator_reported_with_file_digest'}
    def update(old):
        if old is None or old['selection'] is None: raise ValueError('selection must precede execution events')
        if old['terminalStatus'] is not None: raise ValueError('terminal receipt is sealed')
        selected = old['selection']
        if selected['decision'] not in {'reuse', 'adapt'}:
            raise ValueError('execution stages require a selected workflow')
        if getattr(args, 'run_id', None) != selected['runId'] or getattr(args, 'source_sha256', None) != selected['sourceSha256']:
            raise ValueError('stage evidence must match the selected run and source digest')
        event.update({k: selected[k] for k in ('workflow', 'variant', 'runId', 'sourceSha256')})
        latest = next((e for e in reversed(old['events']) if e['event'] == event['event']), None)
        if latest and all(latest.get(k) == event[k] for k in ('event','status','evidenceSha256')):
            return old, False
        old['events'].append(event)
        return old, True
    return locked_update(root, args.id, update)[0]


def finish(root, args):
    evidence_hash = None
    if args.status in {'failed', 'partial', 'unavailable'}:
        if not getattr(args, 'evidence', None) or not getattr(args, 'reason', None):
            raise ValueError('failed/partial/unavailable outcomes require reason and actual evidence')
        evidence = Path(args.evidence)
        if evidence.stat().st_size > 16 * 1024 * 1024: raise ValueError('evidence too large')
        evidence_hash = digest(evidence.read_bytes())
    def update(old):
        if old is None: raise ValueError('opportunity not found')
        if args.status == 'skipped' and (not old['selection'] or old['selection']['decision'] not in {'skip', 'no_match', 'candidate'}):
            raise ValueError('skipped requires an explicit skip/no_match/candidate decision')
        if args.status == 'completed':
            if not old['selection'] or old['selection']['decision'] not in {'reuse', 'adapt'}:
                raise ValueError('completed requires a selected workflow')
            latest = {e['event']: e['status'] for e in old['events']}
            stages = {stage for stage, status in latest.items() if status == 'passed'}
            if not {'execution', 'validation', 'capture'} <= stages:
                raise ValueError('completed requires execution, validation and capture evidence')
        if old['terminalStatus']:
            if old['terminalStatus'] != args.status: raise ValueError('terminal status is immutable')
            return old, False
        old['terminalStatus'] = args.status
        old['outcomeReason'] = getattr(args, 'reason', None)
        old['outcomeEvidenceSha256'] = evidence_hash
        old['finishedAt'] = datetime.now(timezone.utc).isoformat()
        return old, True
    return locked_update(root, args.id, update)[0]


def report(root):
    """Whole-opportunity denominator, including unmatched/unfinished cases."""
    counts = {'opportunities': 0, 'eligible': 0, 'recommended': 0, 'selected': 0,
              'decided': 0, 'executed': 0, 'validated': 0, 'captured': 0, 'unfinished': 0, 'invalid': 0, 'fallbackIdentity': 0, 'unclassified': 0}
    by_host = {}
    by_decision = {k: 0 for k in ('reuse', 'adapt', 'no_match', 'unavailable', 'candidate', 'skip')}
    paths = sorted(root.glob('*.json'))
    for path in paths[:10000]:
        try:
            value = read_json(path)
            if value.get('schemaVersion') != SCHEMA: raise ValueError('unknown receipt')
            counts['opportunities'] += 1
            counts['fallbackIdentity'] += value.get('identityMode') == 'prompt-fallback'
            counts['unclassified'] += value['classification']['eligible'] is None
            counts['eligible'] += value['classification']['eligible'] is True
            counts['recommended'] += bool(value.get('references'))
            selection = value['selection']
            counts['decided'] += selection is not None
            if selection is not None:
                by_decision[selection['decision']] += 1
                counts['selected'] += selection['decision'] in {'reuse', 'adapt'} and bool(selection['workflow'] and selection['variant'])
            latest = {e['event']:e['status'] for e in value['events']}
            passed = {stage for stage,status in latest.items() if status == 'passed'}
            for stage, key in [('execution','executed'), ('validation','validated'), ('capture','captured')]:
                counts[key] += stage in passed
            counts['unfinished'] += value['terminalStatus'] is None
            by_host[value['host']] = by_host.get(value['host'], 0) + 1
        except (ValueError, KeyError, TypeError, OSError):
            counts['invalid'] += 1
    return {'schemaVersion': SCHEMA, 'status': 'available' if root.is_dir() else 'unavailable', 'reason': 'receipt_inventory' if root.is_dir() else 'receipt_root_missing', 'counts': counts if root.is_dir() else None, 'opportunitiesByHost': by_host, 'decisions': by_decision,
            'truncated': len(paths) > 10000, 'claimScope': 'observations and operator-reported evidence; no causal benefit'}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root', type=Path, default=DEFAULT_ROOT / 'receipts')
    sub = ap.add_subparsers(dest='command', required=True)
    hp = sub.add_parser('hook'); hp.add_argument('--host', choices=['claude','codex','unknown'], default='unknown')
    hp.add_argument('--router-bridge', action='store_true')
    hp.add_argument('--config', type=Path, default=DEFAULT_ROOT / 'config.json')
    sub.add_parser('report')
    begin = sub.add_parser('begin', help='Explicit opportunity for hosts without native turn IDs')
    begin.add_argument('--host', choices=['claude','codex'], required=True)
    begin.add_argument('--session', required=True); begin.add_argument('--turn', required=True)
    begin.add_argument('--prompt', required=True)
    dp = sub.add_parser('decide'); dp.add_argument('--id', required=True)
    dp.add_argument('--decision', choices=['reuse','adapt','no_match','unavailable','candidate','skip'], required=True)
    dp.add_argument('--workflow'); dp.add_argument('--variant'); dp.add_argument('--reason', choices=['existing_workflow','scope_mismatch','capability_missing','no_suitable_workflow','repeatable_steps_observed','simple_or_nonworkflow_task'], required=True)
    dp.add_argument('--run-id'); dp.add_argument('--source-sha256')
    dp.add_argument('--config', type=Path, default=DEFAULT_ROOT / 'config.json')
    rp = sub.add_parser('record'); rp.add_argument('--id', required=True); rp.add_argument('--event', choices=['execution','validation','capture'], required=True)
    rp.add_argument('--status', choices=['passed','failed','partial','unavailable'], required=True); rp.add_argument('--evidence', required=True)
    rp.add_argument('--run-id', required=True); rp.add_argument('--source-sha256', required=True)
    fp = sub.add_parser('finish'); fp.add_argument('--id', required=True); fp.add_argument('--status', choices=['completed','failed','partial','skipped','unavailable'], required=True)
    fp.add_argument('--reason', choices=['gate_failed','transport_failed','capability_missing','operator_stopped','no_suitable_workflow'])
    fp.add_argument('--evidence')
    sp = sub.add_parser('status'); sp.add_argument('--id', required=True)
    args = ap.parse_args()
    try:
        if args.command == 'hook':
            if not args.config.is_file(): return 0
            config = read_json(args.config)
            if config.get('schemaVersion') != 1 or config.get('enabled') is not True: return 0
            raw = sys.stdin.buffer.read(MAX_INPUT + 1)
            if len(raw) > MAX_INPUT: raise ValueError('hook input budget exceeded')
            payload = json.loads(raw)
            if not isinstance(payload, dict): raise ValueError('invalid hook input')
            host = args.host
            if host == 'unknown':
                host = 'codex' if payload.get('thread_id') or os.environ.get('CODEX_THREAD_ID') or os.environ.get('PLUGIN_ROOT') else 'claude' if os.environ.get('CLAUDE_CODE_ENTRYPOINT') else 'unknown'
            receipt, fresh = opportunity(payload, host, args.root, config)
            message = hook_message(receipt) if receipt and fresh else None
            output = {'hookSpecificOutput': {'hookEventName': 'UserPromptSubmit', 'additionalContext': message}} if message else None
            if args.router_bridge:
                print(json.dumps({'handled': bool(receipt), 'hookOutput': output}))
            elif output:
                print(json.dumps(output))
        elif args.command == 'begin':
            value, _ = opportunity({'prompt': args.prompt, 'session_id': args.session, 'turn_id': args.turn}, args.host, args.root, {})
            print(json.dumps(value))
        elif args.command == 'report': print(json.dumps(report(args.root)))
        elif args.command == 'decide': print(json.dumps(decide(args.root, args)))
        elif args.command == 'record': print(json.dumps(record(args.root, args)))
        elif args.command == 'finish': print(json.dumps(finish(args.root, args)))
        else:
            if not re.fullmatch(r'[0-9a-f]{64}', args.id): raise ValueError('invalid id')
            print(json.dumps(read_json(args.root / (args.id + '.json'))))
        return 0
    except Exception as exc:
        if args.command == 'hook':
            print(json.dumps({'systemMessage': 'Rhize workflow discovery/capture is unavailable; continue the task and record the gap.'}))
            return 0
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
