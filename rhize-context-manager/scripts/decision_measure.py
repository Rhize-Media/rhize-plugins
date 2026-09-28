#!/usr/bin/env python3
"""Measure an explicitly requested check once; never infer task acceptance.

Child output is forwarded, but the private receipt contains hashes and measured
process facts only. Capture failures do not replace the child command's status.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import sys
import time
import uuid

from workflow_selection import DEFAULT_ROOT, digest, locked_update, read_json

SCHEMA = 'rhize-workflow-check-measurement-v2'
FORWARD_LIMIT = 16 * 1024 * 1024


def binding(root, receipts, identity):
    """Bind to existing capture; no prompt parsing or retrospective context."""
    from workflow_task_context import load_context, source_binding, task_root
    from decision_pilot_v2 import source_digest, validate_observation

    path = receipts / (identity + '.json')
    if path.is_symlink():
        raise ValueError('invalid_receipt')
    receipt = read_json(path)
    if receipt.get('decisionPilot') != 'shadow-v2':
        raise ValueError('not_v2')
    context = load_context(receipts, identity)
    if not context:
        raise ValueError('missing_context')
    observation_path = root / 'v2' / 'observations' / (identity + '.json')
    if observation_path.is_symlink():
        raise ValueError('invalid_observation')
    observation = read_json(observation_path)
    validate_observation(observation, receipts, identity, require_current_source=True, root=root)
    if (observation.get('opportunityId') != identity
            or observation.get('sessionHash') != receipt['sessionHash']
            or observation.get('sourceSha256') != source_digest()):
        raise ValueError('source_mismatch')
    return {'sessionHash': receipt['sessionHash'], 'sourceSha256': observation['sourceSha256'],
            'receiptSourceSha256': source_binding(receipt),
            'taskRootId': task_root(receipts, identity, context)}


def safe_binding(root, receipts, identity):
    try:
        return binding(root, receipts, identity), None
    except Exception:
        return None, 'context_binding_unavailable'


def terminate_group(process):
    complete = True
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            break
        except PermissionError:
            complete = False
            try:
                process.kill()  # Never claim descendants were reaped.
            except OSError:
                pass
            break
        if sig == signal.SIGTERM:
            # Reap an exited leader before signaling remaining descendants. Some
            # hosts deny a second signal to a group containing only that zombie.
            try:
                process.wait(timeout=0.1)
            except subprocess.TimeoutExpired:
                pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        complete = False
    return complete


def forward(sink, data):
    """Best effort only: a backpressured consumer cannot stall child monitoring."""
    fd, blocking = None, None
    try:
        if type(sink) is io.BytesIO:
            return sink.write(data) == len(data)
        fd = sink.fileno()
        blocking = os.get_blocking(fd)
        os.set_blocking(fd, False)
        return os.write(fd, data) == len(data)
    except (OSError, ValueError, AttributeError):
        return False
    finally:
        if fd is not None and blocking is not None:
            try:
                os.set_blocking(fd, blocking)
            except OSError:
                pass


def execute(command, timeout, stdout, stderr):
    started = time.monotonic()
    hashes = {'stdout': hashlib.sha256(), 'stderr': hashlib.sha256()}
    sizes = {'stdout': 0, 'stderr': 0}
    status, returncode, cleanup = 'completed', None, 'not_required'
    forwarding_gap = False
    process = None
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   stdin=subprocess.DEVNULL, start_new_session=True, close_fds=True)
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ, ('stdout', stdout))
            selector.register(process.stderr, selectors.EVENT_READ, ('stderr', stderr))
            while selector.get_map() or process.poll() is None:
                remaining = timeout - (time.monotonic() - started)
                if remaining <= 0:
                    status = 'timeout'
                    cleanup = 'completed' if terminate_group(process) else 'failed'
                    break
                for key, _ in selector.select(min(0.1, remaining)):
                    data = os.read(key.fileobj.fileno(), 65536)
                    if not data:
                        selector.unregister(key.fileobj)
                        continue
                    name, sink = key.data
                    hashes[name].update(data)
                    available = max(0, FORWARD_LIMIT - sizes[name])
                    if available:
                        forwarding_gap |= not forward(sink, data[:available])
                    sizes[name] += len(data)
            returncode = process.returncode if status == 'timeout' else process.wait(timeout=5)
    except KeyboardInterrupt:
        status = 'interrupted'
        if process:
            cleanup = 'completed' if terminate_group(process) else 'failed'
            returncode = process.returncode
    except OSError:
        status = 'launch_failed' if process is None else 'interrupted'
        if process:
            cleanup = 'completed' if terminate_group(process) else 'failed'
            returncode = process.returncode
    finally:
        if process:
            for stream in (process.stdout, process.stderr):
                if stream:
                    stream.close()
    facts = {'status': status, 'exitCode': returncode, 'cleanupStatus': cleanup,
             'durationMs': round((time.monotonic() - started) * 1000, 3),
             'stdoutSha256': hashes['stdout'].hexdigest(), 'stderrSha256': hashes['stderr'].hexdigest(),
             'outputComplete': status == 'completed',
             'forwardTruncated': forwarding_gap or any(size > FORWARD_LIMIT for size in sizes.values())}
    if status != 'completed':
        code = {'timeout': 124, 'interrupted': 130, 'launch_failed': 127}[status]
    else:
        code = returncode if returncode >= 0 else 128 - returncode
    return code, facts


def measure(command, identity, root, receipts, timeout=300, stdout=None, stderr=None):
    if not re.fullmatch('[0-9a-f]{64}', identity):
        raise ValueError('invalid opportunity id')
    if not command or not math.isfinite(timeout) or not 0 < timeout <= 900:
        raise ValueError('command and timeout in (0, 900] required')
    before, reason = safe_binding(root, receipts, identity)
    code, facts = execute(command, timeout, stdout or sys.stdout.buffer, stderr or sys.stderr.buffer)
    after, _ = safe_binding(root, receipts, identity)
    if before is not None and before != after:
        before, reason = None, 'binding_changed'
    value = {'schema': SCHEMA, 'opportunityId': identity, 'basis': 'automatic_artifact',
             'executedVariant': 'A_incumbent', 'observedAt': datetime.now(timezone.utc).isoformat(),
             'bindingStatus': 'bound' if before else 'unbound', 'reasonCode': reason,
             **(before or {'sessionHash': None, 'sourceSha256': None,
                          'receiptSourceSha256': None, 'taskRootId': None}), **facts}
    record_id = digest(uuid.uuid4().hex)
    try:
        value['measurementSourceSha256'] = digest(Path(__file__).read_bytes())
        if any(path.is_symlink() for path in (root, root / 'v2', root / 'v2/measurements')):
            raise ValueError('symlink measurement root')
        locked_update(root / 'v2' / 'measurements', record_id, lambda old: (value, True))
    except (OSError, ValueError, TypeError):
        forward(getattr(sys.stderr, 'buffer', sys.stderr),
                b'{"measurement":"unavailable","reason":"receipt_write_failed"}\n')
    return code, value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=DEFAULT_ROOT / 'pilot')
    parser.add_argument('--receipts', type=Path, default=DEFAULT_ROOT / 'receipts')
    parser.add_argument('--id', required=True)
    parser.add_argument('--timeout', type=float, default=300)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    def interrupt(_signal, _frame):
        # A second interrupt must not interrupt process-group cleanup.
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        raise KeyboardInterrupt
    previous = signal.signal(signal.SIGTERM, interrupt)
    previous_int = signal.signal(signal.SIGINT, interrupt)
    try:
        try:
            return measure(command, args.id, args.root, args.receipts, args.timeout)[0]
        except ValueError as exc:
            parser.error(str(exc))
        except KeyboardInterrupt:
            forward(sys.stderr.buffer, b'{"measurement":"unavailable","reason":"capture_interrupted"}\n')
            return 130
    finally:
        signal.signal(signal.SIGTERM, previous)
        signal.signal(signal.SIGINT, previous_int)


if __name__ == '__main__':
    raise SystemExit(main())
