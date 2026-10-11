#!/usr/bin/env python3
"""Backfill: replay real past router prompts through the CURRENT router and Laya (plan §4.5, A4).

    backfill.py run --since 2026-09-27 --cutover <ISO> [--budget N] [--log PATH] [--index PATH] [--map PATH]
                    [--transcripts DIR...] [--endpoint URL] [--budget-ms 5000] [--root DIR] [--new-manifest]

Each legacy suggestion-log row with since <= ts < cutover is matched to its transcript turn (session id plus the
sha256(prompt)[:16] context hash, repeated prompts resolved by timestamp), replayed through route_replay.js
(route-core.js: incumbent and unfloored lexical shortlist) and, when there is a shortlist, asked of the loopback
Laya server with the laya-choice-v1 instrument. One `basis: "backfill"` record per occurrence is appended to
<root>/skill-fit/records (shadow, arm none, emitted null). Prompt text lives in memory and in the stdin pipe of the
node replay process only; the printed summary holds counts, never text, paths or ids.

Frozen manifest: the first run copies the router index and skill map to <root>/skill-fit/backfill/ and records
{indexSha256, mapSha256, routerSourceSha256, instrumentSha256, layaRevision, since, cutover}. A resumed run reuses
the frozen copies and refuses (exit 3) when the router sources, the instrument, the Laya revision or the window
changed, unless --new-manifest starts a fresh evidence frame (the old frame is archived).

Resume and dedupe: occurrences already in <root>/skill-fit/records (and repeats inside the run) are skipped.
Only a Laya answer ('ok') or a deterministic skip (empty shortlist) becomes a record: a timeout, an unavailable or
unidentified server or an invalid reply says nothing about the historical prompt, so that row stays unrecorded and
the next run retries it. Five Laya failures in a row abort the run (exit 4). Explicit skill requests ("use X")
never reach Laya live, so no record is written for them. --budget caps Laya calls per run; later rows wait.

Exit codes: 0 done (or nothing to do / busy), 2 bad inputs, 3 manifest refused, 4 aborted (Laya unavailable).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from typed_decisions import contract, evidence_fs, instrument, laya_choice, records, transcripts  # noqa: E402

MANIFEST_SCHEMA = 'rhize-typed-decision-backfill-manifest-v1'
DECISION = 'skill-fit'
DEFAULT_ENDPOINT = 'http://127.0.0.1:8000'
MAX_CONFIG_BYTES = 64 * 1024 * 1024
MAX_LOG_LINE = 1 << 20
MAX_CONSECUTIVE_LAYA_FAILURES = 5
REPLAY_SCRIPT = Path(__file__).resolve().with_name('route_replay.js')
REGISTRY_PATH = Path(__file__).resolve().parents[2] / 'catalog' / 'decision-registry.json'
HEX16 = re.compile(r'[0-9a-f]{16}\Z')

EXIT_OK, EXIT_USAGE, EXIT_MANIFEST, EXIT_ABORTED = 0, 2, 3, 4


class BackfillError(Exception):
    """A bounded, non-secret failure with the process exit code to use."""

    def __init__(self, message, code=EXIT_USAGE):
        super().__init__(message)
        self.code = code


# ------------------------------------------------------------------ inputs


def is_background_observer_transcript(path, home=None) -> bool:
    """A Claude transcript written by ECC's homunculus background observer (its own headless sessions under
    ~/.local/share/ecc-homunculus[/projects/<12 hex>]). The live router skips these sessions; backfill must too."""
    slug = re.sub(r'[^a-zA-Z0-9]', '-', str(Path(home or Path.home()) / '.local' / 'share' / 'ecc-homunculus'))
    name = Path(path).parent.name
    return name == slug or re.fullmatch(re.escape(slug) + r'-projects-[0-9a-f]{12}', name) is not None

def parse_instant(value, name) -> datetime:
    """Date ('2026-09-27') or ISO timestamp carrying Z/offset, as an aware UTC datetime."""
    try:
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        raise BackfillError(f'--{name} must be a date or an ISO timestamp') from None
    if parsed.tzinfo is None:
        raise BackfillError(f'--{name} timestamp needs a timezone (Z or an offset)')
    return parsed.astimezone(timezone.utc)


def iso(moment: datetime) -> str:
    moment = moment.astimezone(timezone.utc)
    return moment.strftime('%Y-%m-%dT%H:%M:%S.') + '%03dZ' % (moment.microsecond // 1000)


def context_dir() -> Path:
    override = os.environ.get('RHIZE_CONTEXT_MANAGER_DIR')
    return Path(override) if override else Path.home() / '.claude' / 'context-manager'


def default_source(names) -> Path | None:
    for name in names:
        candidate = context_dir() / name
        if candidate.is_file():
            return candidate
    return None


def default_roots() -> list:
    home = Path.home()
    return [home / '.claude' / 'projects', home / '.codex' / 'sessions', home / '.codex' / 'archived_sessions']


def read_json_file(path, name):
    try:
        return json.loads(evidence_fs.read_regular(path, MAX_CONFIG_BYTES).decode('utf-8'))
    except (OSError, ValueError):
        raise BackfillError(f'cannot read {name}') from None


def read_rows(log_path, since: datetime, cutover: datetime):
    """(rows in the window oldest first, counts). Rows are the parsed JSON objects of hook == 'router'."""
    counts = Counter()
    rows = []
    try:
        fd = os.open(log_path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    except OSError:
        raise BackfillError('cannot read the suggestion log') from None
    with os.fdopen(fd, 'rb') as stream:
        for number, raw in enumerate(stream):
            if len(raw) > MAX_LOG_LINE:
                counts['logLinesSkipped'] += 1
                continue
            try:
                row = json.loads(raw.decode('utf-8', 'replace'))
            except ValueError:
                counts['logLinesSkipped'] += 1
                continue
            if not isinstance(row, dict):
                counts['logLinesSkipped'] += 1
                continue
            counts['logRows'] += 1
            if row.get('hook') != 'router':
                continue
            counts['routerRows'] += 1
            try:
                moment = datetime.fromisoformat(str(row.get('ts')).replace('Z', '+00:00'))
            except ValueError:
                counts['badTimestamp'] += 1
                continue
            if moment.tzinfo is None:
                counts['badTimestamp'] += 1
                continue
            moment = moment.astimezone(timezone.utc)
            if since <= moment < cutover:
                rows.append((moment, number, row))
    rows.sort(key=lambda item: (item[0], item[1]))
    counts['inWindow'] = len(rows)
    return rows, counts


# ------------------------------------------------------------------ node replay

def find_node():
    node = shutil.which('node')
    if not node:
        raise BackfillError('node is required for the router replay')
    return node


def node_hashes(node, index_path, map_path) -> dict:
    try:
        done = subprocess.run([node, str(REPLAY_SCRIPT), str(index_path), str(map_path), '--hashes'],
                              capture_output=True, text=True, timeout=60, check=True)
        value = json.loads(done.stdout)
        for key in ('indexSha256', 'routerSourceSha256'):
            if not contract.HEX64.match(value[key]):
                raise ValueError
        return value
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        raise BackfillError('route_replay.js could not read the index and map') from None


class Replayer:
    """One long-lived route_replay.js process; prompts travel over its stdin pipe only."""

    def __init__(self, node, index_path, map_path):
        self.process = subprocess.Popen([node, str(REPLAY_SCRIPT), str(index_path), str(map_path)],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                        text=True, encoding='utf-8', bufsize=1)
        self.counter = 0

    def replay(self, prompt: str) -> dict:
        self.counter += 1
        request = json.dumps({'id': self.counter, 'prompt': prompt})           # ASCII-escaped: one safe line
        try:
            self.process.stdin.write(request + '\n')
            self.process.stdin.flush()
            line = self.process.stdout.readline()
            value = json.loads(line)
        except (OSError, ValueError):
            raise BackfillError('the router replay process failed', EXIT_ABORTED) from None
        if not isinstance(value, dict) or value.get('id') != self.counter:
            raise BackfillError('the router replay process failed', EXIT_ABORTED)
        return value

    def close(self):
        try:
            self.process.stdin.close()
        except OSError:
            pass
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
        self.process.stdout.close()


# ------------------------------------------------------------------ manifest

def sha256_file(path) -> str:
    return hashlib.sha256(evidence_fs.read_regular(path, MAX_CONFIG_BYTES)).hexdigest()


def read_laya_revision(root: Path) -> str:
    try:
        value = json.loads(evidence_fs.read_regular(root / 'laya-runtime.json', 64 * 1024))['revision']
        if isinstance(value, str) and contract.REVISION.match(value):
            return value
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return 'unknown'


def read_registry_revision(root: Path) -> int:
    try:
        registry = contract.validate_registry(json.loads(evidence_fs.read_regular(REGISTRY_PATH, 1 << 20)))
        state = contract.validate_state(json.loads(evidence_fs.read_regular(root / 'registry-state.json', 1 << 20)),
                                        registry)
        return state['revision']
    except (OSError, ValueError, KeyError, TypeError):
        return 0


def frozen_paths(workdir: Path):
    return workdir / 'index.json', workdir / 'map.json', workdir / 'backfill-manifest.json'


def load_manifest(path: Path):
    try:
        manifest = json.loads(evidence_fs.read_regular(path, 1 << 20))
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        raise BackfillError('the backfill manifest is unreadable; use --new-manifest to start a new evidence frame',
                            EXIT_MANIFEST) from None
    keys = {'schema', 'createdAt', 'indexSha256', 'mapSha256', 'routerSourceSha256', 'instrumentSha256',
            'layaRevision', 'since', 'cutover'}
    if not isinstance(manifest, dict) or manifest.get('schema') != MANIFEST_SCHEMA or set(manifest) != keys:
        raise BackfillError('the backfill manifest is invalid; use --new-manifest to start a new evidence frame',
                            EXIT_MANIFEST)
    return manifest


def archive(path: Path, stamp: str) -> None:
    if path.exists() and not path.is_symlink():
        os.replace(path, path.with_name(f'{path.stem}.{stamp}{path.suffix}'))


def freeze(workdir, index_source, map_source, node, laya_revision, since, cutover, new_manifest):
    """Create the manifest and frozen copies (archiving a previous frame first); returns the manifest."""
    index_copy, map_copy, manifest_path = frozen_paths(workdir)
    if index_source is None or map_source is None:
        raise BackfillError('a first run needs the router index and skill map (--index / --map)')
    try:
        index_bytes = evidence_fs.read_regular(index_source, MAX_CONFIG_BYTES)
        map_bytes = evidence_fs.read_regular(map_source, MAX_CONFIG_BYTES)
        json.loads(index_bytes)
        json.loads(map_bytes)
    except (OSError, ValueError):
        raise BackfillError('the router index or skill map is missing or not JSON') from None
    if new_manifest:
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        for path in (index_copy, map_copy, manifest_path):
            archive(path, stamp)
    evidence_fs.write_private_atomic(index_copy, index_bytes)
    evidence_fs.write_private_atomic(map_copy, map_bytes)
    hashes = node_hashes(node, index_copy, map_copy)
    manifest = {'schema': MANIFEST_SCHEMA, 'createdAt': iso(datetime.now(timezone.utc)),
                'indexSha256': hashes['indexSha256'], 'mapSha256': hashlib.sha256(map_bytes).hexdigest(),
                'routerSourceSha256': hashes['routerSourceSha256'], 'instrumentSha256': instrument.instrument_sha256(),
                'layaRevision': laya_revision, 'since': iso(since), 'cutover': iso(cutover)}
    evidence_fs.write_private_atomic(manifest_path, (json.dumps(manifest, indent=2, sort_keys=True) + '\n').encode())
    return manifest


def verify_resume(manifest, workdir, node, laya_revision, since, cutover) -> None:
    """A resumed run reuses the frozen copies and must still match every frozen hash."""
    index_copy, map_copy, _ = frozen_paths(workdir)
    refuse = lambda why: BackfillError(f'refusing to resume: {why}; use --new-manifest to start a new evidence '  # noqa: E731
                                       'frame', EXIT_MANIFEST)
    try:
        map_ok = sha256_file(map_copy) == manifest['mapSha256']
        hashes = node_hashes(node, index_copy, map_copy)
    except OSError:
        raise refuse('the frozen index or map copy is missing') from None
    if not map_ok or hashes['indexSha256'] != manifest['indexSha256']:
        raise refuse('a frozen index or map copy was modified')
    if hashes['routerSourceSha256'] != manifest['routerSourceSha256']:
        raise refuse('routerSourceSha256 changed (route-core.js, skill-router.js or laya-instrument.js)')
    if instrument.instrument_sha256() != manifest['instrumentSha256']:
        raise refuse('instrumentSha256 changed')
    if laya_revision != manifest['layaRevision']:
        raise refuse('the Laya revision changed')
    if iso(since) != manifest['since'] or iso(cutover) != manifest['cutover']:
        raise refuse('--since/--cutover differ from the manifest')


# ------------------------------------------------------------------ records

def build_record(*, key, ts, source_stratum, session_hash, prompt_hash, length_bucket, manifest, registry_revision,
                 criteria_sha256, incumbent, shortlist, laya):
    return {
        'schema': contract.RECORD_SCHEMA, 'decision': DECISION, 'decisionId': uuid.uuid4().hex,
        'occurrenceKey': key, 'ts': ts, 'host': 'claude', 'basis': 'backfill', 'sourceStratum': source_stratum,
        'sessionHash': session_hash, 'promptHash': prompt_hash, 'promptLengthBucket': length_bucket,
        'routerSourceSha256': manifest['routerSourceSha256'], 'indexSha256': manifest['indexSha256'],
        'registryRevision': registry_revision, 'policy': contract.POLICY_COSIGN,
        'policySha256': contract.policy_sha256(), 'instrument': instrument.INSTRUMENT,
        'instrumentSha256': manifest['instrumentSha256'], 'criteriaSha256': criteria_sha256,
        'layaRevision': manifest['layaRevision'], 'mode': 'shadow', 'arm': 'none', 'propensity': None,
        'incumbent': incumbent, 'shortlist': shortlist, 'laya': laya, 'emitted': None}


SKIPPED = {'status': 'skipped', 'choice': None, 'probabilities': None, 'latencyMs': None, 'truncated': None}


# ------------------------------------------------------------------ the run

def run_backfill(root=None, since=None, cutover=None, budget=None, log=None, index=None, map_path=None,
                 transcripts_roots=None, endpoint=DEFAULT_ENDPOINT, budget_ms=5000, new_manifest=False,
                 opener=None, node=None):
    """Returns (summary of counts, exit code). Raises BackfillError for bad inputs."""
    root = Path(root) if root else records.default_root()
    if not laya_choice.is_loopback_endpoint(endpoint):
        raise BackfillError('--endpoint must be a literal loopback address (http://127.0.0.1:PORT or http://[::1]:PORT)')
    if since is None or cutover is None or not since < cutover:
        raise BackfillError('--since must be earlier than --cutover')
    if budget is not None and budget < 0:
        raise BackfillError('--budget must not be negative')
    if budget_ms <= 0:
        raise BackfillError('--budget-ms must be positive')
    log = Path(log) if log else context_dir() / 'suggestion-log.jsonl'
    node = node or find_node()
    evidence_fs.tighten(root / DECISION)
    workdir = evidence_fs.private_dir(root / DECISION / 'backfill', anchor=root)
    summary = {'status': 'started', 'since': iso(since), 'cutover': iso(cutover)}
    with evidence_fs.exclusive_lock(workdir / 'run.lock') as held:
        if not held:
            return {'status': 'busy'}, EXIT_OK
        rows, counts = read_rows(log, since, cutover)             # a bad log must not freeze a frame
        index_copy, map_copy, manifest_path = frozen_paths(workdir)
        laya_revision = read_laya_revision(root)
        manifest = None if new_manifest else load_manifest(manifest_path)
        if manifest is None:
            index_source = Path(index) if index else default_source(['skill-map.indexes.resolved.json',
                                                                      'skill-map.indexes.json'])
            map_source = Path(map_path) if map_path else default_source(['skill-map.resolved.json',
                                                                          'skill-map.static.json'])
            manifest = freeze(workdir, index_source, map_source, node, laya_revision, since, cutover, new_manifest)
            summary['manifest'] = 'created'
        else:
            verify_resume(manifest, workdir, node, laya_revision, since, cutover)
            summary['manifest'] = 'reused'

        stats = Counter(counts)
        stats.update({name: 0 for name in ('matched', 'recordsWritten', 'alreadyRecorded', 'explicitRequestsSkipped',
                                           'deferredBudget', 'notRecordedRetryLater')})
        unmatched = Counter()
        laya_statuses = Counter()
        existing, _ = records.read(root, DECISION, 'records')
        seen = {record['occurrenceKey'] for record in existing}
        registry_revision = read_registry_revision(root)
        scanner = transcripts.TranscriptScanner(transcripts_roots or default_roots())
        health_cache = workdir / 'laya-health.json'
        replayer = Replayer(node, index_copy, map_copy)
        calls = consecutive_failures = 0
        aborted = None
        try:
            for moment, _, row in rows:
                session_id, context_hash = row.get('session_id'), row.get('context_hash')
                if not isinstance(session_id, str) or not session_id:
                    unmatched['no_session_id'] += 1
                    continue
                if not isinstance(context_hash, str) or not HEX16.match(context_hash):
                    unmatched['no_context_hash'] += 1
                    continue
                ts = iso(moment)
                transcripts_for = scanner.paths().get(contract.sha256_text(session_id)) or []
                if isinstance(transcripts_for, (str, Path)):
                    transcripts_for = [transcripts_for]
                if any(is_background_observer_transcript(item) for item in transcripts_for):
                    unmatched['background_observer'] += 1  # ECC homunculus machine sessions (router skips them live)
                    continue
                match, reason = scanner.find_turn(session_id, context_hash, ts)
                if match is None:
                    unmatched[reason] += 1
                    continue
                stats['matched'] += 1
                text = match['text']                                  # memory only, never persisted
                session_hash = contract.sha256_text(session_id)
                prompt_hash = contract.sha256_text(text)
                key = contract.occurrence_key(session_hash, prompt_hash, ts)
                if key in seen:
                    stats['alreadyRecorded'] += 1
                    continue
                replay = replayer.replay(text)
                if 'error' in replay or not isinstance(replay.get('shortlist'), list):
                    stats['replayErrors'] += 1
                    continue
                if replay.get('explicit'):
                    stats['explicitRequestsSkipped'] += 1
                    continue
                stratum = 'fired' if row.get('suggested') else 'silent_sample'
                shortlist = replay['shortlist']
                incumbent = replay.get('incumbent')
                common = dict(key=key, ts=ts, source_stratum=stratum, session_hash=session_hash,
                              prompt_hash=prompt_hash, length_bucket=instrument.length_bucket(text),
                              manifest=manifest, registry_revision=registry_revision, incumbent=incumbent,
                              shortlist=shortlist)
                if not shortlist:
                    record = build_record(criteria_sha256=None, laya=dict(SKIPPED), **common)
                    laya_statuses['skipped'] += 1
                else:
                    if budget is not None and calls >= budget:
                        stats['deferredBudget'] += 1
                        continue
                    descriptions = replay.get('descriptions') or {}
                    try:
                        built = instrument.build_choice_request(
                            text, [{'skillId': sid, 'description': descriptions.get(sid)} for sid in shortlist])
                    except ValueError:
                        stats['invalidCandidates'] += 1
                        continue
                    calls += 1
                    answer = laya_choice.call_choice(built['request'], built['keyMap'], endpoint, instrument.MODEL,
                                                     budget_ms, health_cache_path=health_cache, opener=opener)
                    laya_statuses[answer['status']] += 1
                    if answer['status'] != 'ok':
                        stats['notRecordedRetryLater'] += 1
                        consecutive_failures += 1
                        if consecutive_failures >= MAX_CONSECUTIVE_LAYA_FAILURES:
                            aborted = 'laya_unavailable'
                            break
                        continue
                    consecutive_failures = 0
                    laya = {'status': 'ok', 'choice': answer['choice'], 'probabilities': answer['probabilities'],
                            'latencyMs': answer['latencyMs'], 'truncated': built['truncated']}
                    record = build_record(criteria_sha256=built['criteriaSha256'], laya=laya, **common)
                try:
                    records.append(root, DECISION, 'records', record)
                except ValueError:
                    stats['invalidRecords'] += 1
                    continue
                seen.add(key)
                stats['recordsWritten'] += 1
        finally:
            replayer.close()
        summary.update(status=f'aborted:{aborted}' if aborted else 'completed')
        summary.update({key: stats[key] for key in sorted(stats)})
        summary['unmatched'] = dict(sorted(unmatched.items()))
        summary['unmatchedTotal'] = sum(unmatched.values())
        summary['layaStatuses'] = dict(sorted(laya_statuses.items()))
        summary['layaCalls'] = calls
        return summary, EXIT_ABORTED if aborted else EXIT_OK


# ------------------------------------------------------------------ CLI

def build_parser():
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    sub = parser.add_subparsers(dest='command', required=True)
    run = sub.add_parser('run', help='replay pre-cutover router log rows and append backfill records')
    run.add_argument('--since', required=True, help='first day/instant to replay (inclusive), e.g. 2026-09-27')
    run.add_argument('--cutover', required=True, help='live-collection cutover instant (exclusive)')
    run.add_argument('--budget', type=int, default=None, help='maximum Laya calls this run (default unlimited)')
    run.add_argument('--log', default=None, help='suggestion-log.jsonl (default ~/.claude/context-manager)')
    run.add_argument('--index', default=None, help='router index (first run only; later runs use the frozen copy)')
    run.add_argument('--map', default=None, dest='map_path', help='skill map (first run only)')
    run.add_argument('--transcripts', nargs='+', default=None, metavar='DIR', help='transcript roots')
    run.add_argument('--endpoint', default=DEFAULT_ENDPOINT, help='literal loopback Laya endpoint')
    run.add_argument('--budget-ms', type=int, default=5000, help='per-call deadline covering probe and POST')
    run.add_argument('--root', default=None, help='typed-decisions root (default ~/.local/share/rhize/typed-decisions)')
    run.add_argument('--new-manifest', action='store_true', help='archive the frozen frame and start a new one')
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        summary, code = run_backfill(
            root=args.root, since=parse_instant(args.since, 'since'), cutover=parse_instant(args.cutover, 'cutover'),
            budget=args.budget, log=args.log, index=args.index, map_path=args.map_path,
            transcripts_roots=args.transcripts, endpoint=args.endpoint, budget_ms=args.budget_ms,
            new_manifest=args.new_manifest)
    except BackfillError as exc:
        print(json.dumps({'status': 'refused', 'reason': str(exc)}))
        print(str(exc), file=sys.stderr)
        return exc.code
    except Exception as exc:  # noqa: BLE001 - a bounded error type, never text from a prompt
        print(json.dumps({'status': 'failed', 'error': type(exc).__name__, 'reason': contract.safe_reason(exc)}))
        return 1
    print(json.dumps(summary, sort_keys=True))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
