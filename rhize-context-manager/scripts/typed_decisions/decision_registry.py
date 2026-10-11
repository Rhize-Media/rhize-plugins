#!/usr/bin/env python3
"""The single, locked, revisioned and audited registry mutation path (plan §4.1, invariant I6).

Machine-local files under <root> (default ~/.local/share/rhize/typed-decisions):

    registry-state.json     current modes (validated by contract.validate_state)
    registry-audit.jsonl    one 'intent' line (with the full new state) and one 'commit' line per change
    registry-state.lock     exclusive fcntl lock held for the whole read-check-write

Mutation contract (`mutate`): lock -> recover any dangling intent -> read state -> reject a stale
expected revision -> apply the pin/reachability/binding rules -> validate the new state -> audit
'intent' (fsynced) -> temp file + fsync + os.replace + dir fsync -> audit 'commit'. Nothing else in the
repository writes registry-state.json; the Node hook reads it with the same read rule as `read_state`:

    missing file            -> the shipped registry defaultMode
    unreadable/corrupt/invalid, or a symlink -> 'shadow'
    ok                      -> the state entry's mode (an absent entry means the shipped defaultMode)

`recover` finishes an interrupted update from the audit log and is idempotent.

CLI:
    decision_registry.py show
    decision_registry.py set-mode <decision> <mode> --reason <slug> [--pin | --unpin]
                         [--cohort-id <hex32>] [--laya-revision <rev>]      (cosign needs --laya-revision)
    decision_registry.py recover
All commands take --root DIR. Output is one JSON object; errors exit 2.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE.parent) not in sys.path:
    sys.path.insert(0, str(HERE.parent))

from typed_decisions import cohorts, contract, instrument, locked_io, records  # noqa: E402

STATE_FILE = 'registry-state.json'
AUDIT_FILE = 'registry-audit.jsonl'
LOCK_FILE = 'registry-state.lock'
DEFAULT_REGISTRY = HERE.parents[1] / 'catalog' / 'decision-registry.json'
BINDING_KEYS = ('policySha256', 'instrumentSha256', 'layaRevision', 'cohortId')
LOCK_TIMEOUT_SECONDS = 10.0


class RegistryError(Exception):
    """A refused or failed registry operation; `code` is a stable machine-readable slug."""

    def __init__(self, code: str, message: str = ''):
        super().__init__(f'{code}: {message}' if message else code)
        self.code = code


# ---------------------------------------------------------------- read side

def load_registry(path=None) -> dict:
    """The shipped registry (or `path`), validated by contract.validate_registry."""
    target = Path(path) if path else DEFAULT_REGISTRY
    with open(target, 'rb') as stream:
        registry = json.loads(stream.read().decode('utf-8'))
    return contract.validate_registry(registry)


def state_path(root) -> Path:
    return Path(root) / STATE_FILE


def audit_path(root) -> Path:
    return Path(root) / AUDIT_FILE


def read_state(root, registry=None):
    """Return (state|None, status) with status in {'missing', 'ok', 'corrupt'} (never raises)."""
    path = state_path(root)
    try:
        state = locked_io.read_json_file(path)
    except FileNotFoundError:
        return None, 'missing'
    except (OSError, ValueError):
        return None, 'corrupt'
    try:
        contract.validate_state(state, registry if registry is not None else load_registry())
    except (ValueError, KeyError, TypeError):
        return None, 'corrupt'
    return state, 'ok'


def effective_mode(decision: str, registry: dict, state, status: str) -> str:
    """Mode in force: missing -> shipped default, corrupt -> 'shadow', ok -> state mode (default if no entry)."""
    default = registry['decisions'][decision]['defaultMode']
    if status == 'corrupt':
        return 'shadow'
    if status == 'ok' and state:
        entry = (state.get('decisions') or {}).get(decision)
        if entry:
            return entry['mode']
    return default


def read_audit(root) -> tuple[list[dict], int]:
    """(valid audit lines in order, count of invalid lines). A missing log reads as empty."""
    path = audit_path(root)
    lines, invalid = [], 0
    try:
        fd = os.open(path, os.O_RDONLY | locked_io.NOFOLLOW)
    except FileNotFoundError:
        return [], 0
    with os.fdopen(fd, 'rb') as stream:
        for raw in stream:
            try:
                lines.append(contract.validate_audit(json.loads(raw)))
            except (ValueError, UnicodeDecodeError):
                invalid += 1
    return lines, invalid


# ---------------------------------------------------------------- write side

def _append_audit(root, line: dict) -> None:
    contract.validate_audit(line)
    locked_io.append_line(audit_path(root), line)


def _write_state(root, state: dict) -> None:
    data = (json.dumps(state, separators=(',', ':'), ensure_ascii=False, sort_keys=True) + '\n').encode('utf-8')
    locked_io.write_private_atomic(state_path(root), data)


def _audit_line(phase: str, state: dict, previous_revision: int, now, actor: str, decision: str, from_mode,
                reason: str) -> dict:
    entry = state['decisions'][decision]
    line = {'schema': contract.AUDIT_SCHEMA, 'phase': phase, 'revision': state['revision'],
            'previousRevision': previous_revision, 'at': locked_io.iso(now), 'actor': actor, 'decision': decision,
            'fromMode': from_mode, 'toMode': entry['mode'], 'pinned': entry['pinned'], 'reason': reason}
    if phase == 'intent':
        line['state'] = state
    return line


def _clean_tmp_files(root) -> None:
    for tmp in Path(root).glob(f'{STATE_FILE}.*.tmp'):
        with contextlib.suppress(OSError):
            tmp.unlink()


def _recover_locked(root, registry: dict, now) -> dict:
    """Finish a dangling audit intent (caller holds the lock). Returns {'action': ..., ...}."""
    _clean_tmp_files(root)
    lines, _ = read_audit(root)
    intents = [line for line in lines if line['phase'] == 'intent']
    if not intents:
        return {'action': 'none'}
    intent = intents[-1]
    revision = intent['revision']
    if any(line['phase'] == 'commit' and line['revision'] == revision and line['decision'] == intent['decision']
           for line in lines):
        return {'action': 'none'}
    state, status = read_state(root, registry)
    if status == 'corrupt':
        return {'action': 'blocked', 'reason': 'state_corrupt', 'revision': revision}
    current = state['revision'] if state else 0
    try:
        contract.validate_state(intent['state'], registry)
    except (ValueError, KeyError, TypeError):
        return {'action': 'blocked', 'reason': 'intent_state_invalid', 'revision': revision}
    if intent['state'].get('revision') != revision:
        return {'action': 'blocked', 'reason': 'intent_state_invalid', 'revision': revision}
    commit = {**{k: v for k, v in intent.items() if k != 'state'}, 'phase': 'commit', 'actor': 'recovery',
              'at': locked_io.iso(now)}
    if current < revision:
        if current != revision - 1:
            return {'action': 'blocked', 'reason': 'revision_gap', 'revision': revision, 'stateRevision': current}
        _write_state(root, intent['state'])
        _append_audit(root, commit)
        return {'action': 'applied', 'revision': revision}
    if current == revision:
        if state != intent['state']:
            return {'action': 'blocked', 'reason': 'state_diverged', 'revision': revision}
        _append_audit(root, commit)
        return {'action': 'committed', 'revision': revision}
    return {'action': 'superseded', 'revision': revision, 'stateRevision': current}


def recover(root, registry=None, now=None) -> dict:
    """Idempotently complete an interrupted update from the audit log."""
    root = Path(root)
    if not audit_path(root).exists():
        return {'action': 'none'}
    registry = registry if registry is not None else load_registry()
    try:
        with locked_io.file_lock(root / LOCK_FILE, LOCK_TIMEOUT_SECONDS):
            return _recover_locked(root, registry, now)
    except TimeoutError:
        raise RegistryError('lock_timeout', 'another registry writer holds the lock') from None


def _check_binding(root, registry_entry: dict, actor: str, binding) -> dict:
    if not isinstance(binding, dict) or set(binding) != set(BINDING_KEYS):
        raise RegistryError('binding_required', f'cosign needs a binding with keys {list(BINDING_KEYS)}')
    try:
        policy_hash, instrument_hash = cohorts.deployable_hashes(registry_entry)
    except ValueError as err:
        raise RegistryError('policy_not_deployable', str(err)) from None
    if registry_entry['instrument'] != instrument.INSTRUMENT:
        raise RegistryError('invalid_binding', 'registry instrument is not the shipped instrument')
    if binding['policySha256'] != policy_hash:
        raise RegistryError('invalid_binding', 'policySha256 is not the deployable policy hash')
    if binding['instrumentSha256'] != instrument_hash:
        raise RegistryError('invalid_binding', 'instrumentSha256 is not the current instrument hash')
    rev = binding['layaRevision']
    if not isinstance(rev, str) or not contract.REVISION.match(rev):
        raise RegistryError('invalid_binding', 'invalid layaRevision')
    cohort_id = binding['cohortId']
    if cohort_id is None:
        if actor != 'cycle':
            return binding  # operator override through the CLI: audited with actor 'cli'
        raise RegistryError('binding_required', 'the cycle may only promote through a passed cohort')
    if not isinstance(cohort_id, str) or not contract.HEX32.match(cohort_id):
        raise RegistryError('invalid_binding', 'invalid cohortId')
    try:
        cohorts.verify_passed_cohort(root, registry_entry, binding)
    except ValueError as err:
        raise RegistryError('invalid_binding', str(err)) from None
    return binding


def mutate(root, decision: str, to_mode: str, *, actor: str, reason: str, expected_revision: int,
           pinned=None, binding=None, now=None, registry=None) -> dict:
    """THE state write path. Returns the new (committed) state.

    expected_revision is the revision the caller observed (0 when the state file was missing). Raises
    RegistryError with code: invalid_actor, invalid_reason, unknown_decision, unreachable_mode,
    state_corrupt, stale_revision, pinned, pin_forbidden, binding_required, invalid_binding,
    policy_not_deployable, no_change, lock_timeout.

    Rules: actor 'cycle' is refused for a pinned decision and may never change a pin; a mode must be in
    the registry's reachableModes (a critical tier never leaves shadow/off); cosign needs a binding
    {policySha256, instrumentSha256, layaRevision, cohortId} naming the deployable policy and the current
    instrument, and the cycle's cohortId must be a consumed 'pass' cohort of that exact key (the CLI may
    pass cohortId None as an audited manual override). A dangling audit intent is recovered first.
    """
    root = Path(root)
    registry = registry if registry is not None else load_registry()
    if actor not in ('cli', 'cycle'):
        raise RegistryError('invalid_actor', "actor must be 'cli' or 'cycle'")
    if not isinstance(reason, str) or not contract.REASON.match(reason):
        raise RegistryError('invalid_reason', 'reason must match [a-z_]{1,40}')
    if decision not in registry['decisions']:
        raise RegistryError('unknown_decision', decision)
    entry = registry['decisions'][decision]
    if to_mode not in contract.MODES:
        raise RegistryError('unreachable_mode', f'unknown mode {to_mode!r}')
    if to_mode not in entry['reachableModes'] or (entry['tier'] == 'critical' and to_mode not in ('off', 'shadow')):
        raise RegistryError('unreachable_mode', f'{decision} cannot reach {to_mode}')
    if isinstance(expected_revision, bool) or not isinstance(expected_revision, int) or expected_revision < 0:
        raise RegistryError('stale_revision', 'expected_revision must be a non-negative integer')
    if pinned is not None and not isinstance(pinned, bool):
        raise RegistryError('invalid_reason', 'pinned must be a boolean or None')
    if actor == 'cycle' and pinned is not None:
        raise RegistryError('pin_forbidden', 'only the CLI changes pins')
    if to_mode != 'cosign' and binding is not None:
        raise RegistryError('invalid_binding', 'a binding only applies to cosign')

    locked_io.private_dir(root, anchor=root)
    try:
        with locked_io.file_lock(root / LOCK_FILE, LOCK_TIMEOUT_SECONDS):
            return _mutate_locked(root, registry, entry, decision, to_mode, actor, reason, expected_revision,
                                  pinned, binding, now)
    except TimeoutError:
        raise RegistryError('lock_timeout', 'another registry writer holds the lock') from None


def _mutate_locked(root, registry, entry, decision, to_mode, actor, reason, expected_revision, pinned, binding,
                   now) -> dict:
    _recover_locked(root, registry, now)
    state, status = read_state(root, registry)
    if status == 'corrupt':
        raise RegistryError('state_corrupt', 'registry-state.json is unreadable or invalid; hooks run in shadow. '
                            'Inspect it, then remove the file to fall back to the shipped default')
    current_revision = state['revision'] if state else 0
    if expected_revision != current_revision:
        raise RegistryError('stale_revision', f'expected revision {expected_revision}, found {current_revision}')
    existing = ((state or {}).get('decisions') or {}).get(decision)
    was_pinned = bool(existing and existing['pinned'])
    if actor == 'cycle' and was_pinned:
        raise RegistryError('pinned', f'{decision} is pinned; automation is suspended')
    from_mode = existing['mode'] if existing else entry['defaultMode']
    new_pinned = was_pinned if pinned is None else pinned
    if to_mode == 'cosign':
        if binding is None and actor == 'cli' and existing and existing['mode'] == 'cosign':
            binding = {key: existing[key] for key in BINDING_KEYS}  # pin/unpin of a deployed cosign: keep its basis
        elif binding is None:
            raise RegistryError('binding_required', f'cosign needs a binding with keys {list(BINDING_KEYS)}')
        else:
            binding = _check_binding(root, entry, actor, binding)
    unchanged = (to_mode == from_mode and new_pinned == was_pinned
                 and (existing is None or to_mode != 'cosign' or all(existing[k] == binding[k] for k in BINDING_KEYS)))
    if unchanged and (existing is not None or to_mode == entry['defaultMode']):
        raise RegistryError('no_change', f'{decision} is already {to_mode} with pinned={new_pinned}')
    stamp = locked_io.iso(now)
    since = existing['since'] if existing and to_mode == from_mode else stamp
    new_entry = {'mode': to_mode, 'pinned': new_pinned, 'since': since, 'reason': reason,
                 'policySha256': binding['policySha256'] if binding else None,
                 'instrumentSha256': binding['instrumentSha256'] if binding else None,
                 'layaRevision': binding['layaRevision'] if binding else None,
                 'cohortId': binding['cohortId'] if binding else None}
    new_state = {'schemaVersion': contract.STATE_SCHEMA_VERSION, 'revision': current_revision + 1,
                 'updatedAt': stamp, 'decisions': {**((state or {}).get('decisions') or {}), decision: new_entry}}
    try:
        contract.validate_state(new_state, registry)
    except ValueError as err:
        raise RegistryError('unreachable_mode', str(err)) from None
    _append_audit(root, _audit_line('intent', new_state, current_revision, now, actor, decision, from_mode, reason))
    _write_state(root, new_state)
    _append_audit(root, _audit_line('commit', new_state, current_revision, now, actor, decision, from_mode, reason))
    return new_state


# ---------------------------------------------------------------- CLI

def _cli_show(root, registry) -> dict:
    state, status = read_state(root, registry)
    decisions = {}
    for decision_id, entry in registry['decisions'].items():
        item = ((state or {}).get('decisions') or {}).get(decision_id)
        decisions[decision_id] = {
            'tier': entry['tier'], 'defaultMode': entry['defaultMode'],
            'effectiveMode': effective_mode(decision_id, registry, state, status),
            'pinned': bool(item and item['pinned']), 'since': item['since'] if item else None,
            'reason': item['reason'] if item else None, 'cohortId': item['cohortId'] if item else None}
    lines, invalid = read_audit(root)
    pending = bool(lines) and lines[-1]['phase'] == 'intent'
    return {'root': str(root), 'status': status, 'revision': state['revision'] if state else 0,
            'decisions': decisions, 'auditLines': len(lines), 'auditInvalid': invalid, 'pendingIntent': pending}


def _cli_set_mode(args, root, registry) -> dict:
    state, status = read_state(root, registry)
    if status == 'corrupt':
        raise RegistryError('state_corrupt', 'registry-state.json is unreadable or invalid')
    binding = None
    entry = registry['decisions'].get(args.decision)
    if entry is None:
        raise RegistryError('unknown_decision', args.decision)
    already = ((state or {}).get('decisions') or {}).get(args.decision)
    pin_only = bool(already and already['mode'] == 'cosign' and not args.laya_revision and not args.cohort_id)
    if args.mode == 'cosign' and 'cosign' in entry['reachableModes'] and not pin_only:
        if not args.laya_revision:
            raise RegistryError('binding_required', 'cosign needs --laya-revision (and --cohort-id for a gated promotion)')
        try:
            policy_hash, instrument_hash = cohorts.deployable_hashes(entry)
        except ValueError as err:
            raise RegistryError('policy_not_deployable', str(err)) from None
        binding = {'policySha256': policy_hash, 'instrumentSha256': instrument_hash,
                   'layaRevision': args.laya_revision, 'cohortId': args.cohort_id}
    pinned = True if args.pin else (False if args.unpin else None)
    new_state = mutate(root, args.decision, args.mode, actor='cli', reason=args.reason,
                       expected_revision=state['revision'] if state else 0, pinned=pinned, binding=binding,
                       registry=registry)
    entry = new_state['decisions'][args.decision]
    return {'ok': True, 'revision': new_state['revision'], 'decision': args.decision, 'mode': entry['mode'],
            'pinned': entry['pinned']}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Typed-decision registry (single locked mutation path).')
    parser.add_argument('--root', help='typed-decisions data root (default: RHIZE_TYPED_DECISIONS_ROOT or ~/.local/share/rhize/typed-decisions)')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('show', help='print effective modes, pins and the state revision')
    setter = sub.add_parser('set-mode', help='change a decision mode as the operator (actor cli)')
    setter.add_argument('decision')
    setter.add_argument('mode', choices=list(contract.MODES))
    setter.add_argument('--reason', required=True, help='short slug, [a-z_]{1,40}')
    group = setter.add_mutually_exclusive_group()
    group.add_argument('--pin', action='store_true', help='suspend automatic mode changes')
    group.add_argument('--unpin', action='store_true', help='resume automatic mode changes')
    setter.add_argument('--cohort-id', help='passed cohort backing a cosign change (omit for a manual override)')
    setter.add_argument('--laya-revision', help='Laya revision the cosign change is bound to')
    sub.add_parser('recover', help='finish an interrupted update from the audit log')
    args = parser.parse_args(argv)
    root = Path(args.root) if args.root else records.default_root()
    try:
        registry = load_registry()
        if args.command == 'show':
            result = _cli_show(root, registry)
        elif args.command == 'set-mode':
            result = _cli_set_mode(args, root, registry)
        else:
            result = {'ok': True, 'recovery': recover(root, registry)}
    except RegistryError as err:
        print(json.dumps({'ok': False, 'error': err.code, 'message': str(err)}, sort_keys=True))
        return 2
    except (OSError, ValueError) as err:
        print(json.dumps({'ok': False, 'error': 'failed', 'message': str(err)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
