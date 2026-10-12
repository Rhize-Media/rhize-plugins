#!/usr/bin/env python3
"""Prospective, privacy-bounded evaluator for weekly router candidates (plan §7 F7 and F8, acceptance A3).

An autoresearch-style fixed evaluator with a keep/discard ledger. A candidate (a change to the tag catalog or to
trigger phrases) is FROZEN first, then confirmed only on router traffic recorded AFTER the freeze, which neither
the proposer nor the candidate has ever seen. Nothing here pushes, merges, opens a PR, edits the instrument,
policy, registry or gate, or runs the gate.

    real_traffic.py freeze --baseline-checkout B --candidate-checkout C --out MANIFEST [--root R] [--now T]
                           [--baseline-index P --baseline-map P --candidate-index P --candidate-map P]
                           [--mandated-skill REF ...] [--allow-dirty]
    real_traffic.py evaluate --manifest MANIFEST --root R [--transcripts DIR ...]
                           [--harness-result RESULT_JSON | --run-harness] [--candidate-checkout C]
                           --out REPORT [--now T]
    real_traffic.py dev-report --root R --baseline-checkout B [--transcripts DIR ...] --out REPORT [--top N]

freeze    records the candidate's identity (git HEAD of both checkouts, sha256 of the candidate's diff against the
          baseline, the hashes of the resolved router index and skill map of each arm), freezeAt (now), and the
          split and keep rules. It keeps private copies of both arms' index and map next to the manifest
          (<MANIFEST>.arms/) so a later evaluation replays exactly what was frozen. The manifest holds no prompt
          text. Each arm's index and map come from that checkout's rhize-context-manager/scripts/
          build_local_skill_map.py (--out-dir a temp dir) unless explicit paths are given.
evaluate  replays the confirmatory cases (records whose ts is strictly after freezeAt) through BOTH arms and
          scores them. Case types (a record is exactly one, in this order of precedence):
            labeled           a non-ambiguous skill-fit label. A route is a hit when it is in the acceptable set
                              and a false fire when it fires while the set is empty; a route outside the record's
                              original shortlist is unscorable (reported separately, never compared).
            weak positive     outcome invoked_unlisted | invoked_other_shortlisted, latencyTurns 0, via skill_tool
                              | slash_command (never skill_file_read), nearest record of that turn, skill not in
                              the mandated list. Correct = the route equals the invoked skill.
            silence negative  sourceStratum silent_sample. Any fire is bad.
          Codex records whose rollout thread_source is not "user" are excluded (first line, bounded).
          Discordant cases are those where exactly one arm is correct. KEEP needs ALL of: the routing harness
          passes, >= 10 discordant cases, a one-sided exact sign test p <= 0.05 favoring the candidate, a silence
          fire count that does not rise, and a candidate unscorable share <= 0.20. Otherwise the verdict is
          "insufficient" when fewer than 10 cases are discordant and "discard" in every other case. One line is
          appended to <root>/skill-fit/improvement/ledger.jsonl (append-only, 0600): hashes and counts only.
dev-report  baseline metrics on the data available NOW plus the top routing misses by skill (counts only), for
          proposing candidates. It makes no keep decision.

Privacy and isolation (F8). Prompt text is recovered from local transcripts in memory only (session_paths, then
the turn whose sha256 equals the record's promptHash) and reaches node through the stdin pipe of
route_replay.js, never argv. The replay child gets HOME unchanged and fresh temporary RHIZE_TYPED_DECISIONS_ROOT,
XDG_DATA_HOME, RHIZE_CONTEXT_MANAGER_DIR and RHIZE_SUGGESTION_LOG, a preloaded tripwire that aborts the child
on any socket or name lookup (route replay never calls Laya, so any network use is a defect), and no other
credentials. Reports and the ledger hold counts, hashes and verdicts: no prompt text, paths, session ids or skill
descriptions. Opaque occurrenceKeys appear in the private report only. Failures print contract.safe_reason.

Exit codes: 0 done, 1 failed, 2 bad inputs, 3 refused (a frozen file changed, or the freeze would be unsound).
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from fractions import Fraction
from math import comb
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SCRIPTS = REPO / 'rhize-context-manager' / 'scripts'
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from typed_decisions import (backfill, cohorts, contract, evidence_fs, locked_io, outcomes,  # noqa: E402
                             records, transcripts)

MANIFEST_SCHEMA = 'rhize-real-traffic-manifest-v1'
LEDGER_SCHEMA = 'rhize-real-traffic-ledger-v1'
REPORT_SCHEMA = 'rhize-real-traffic-report-v1'
DEV_REPORT_SCHEMA = 'rhize-real-traffic-dev-report-v1'
EVALUATOR = 'rhize-real-traffic-evaluator-v1'
DECISION = 'skill-fit'

EXIT_OK, EXIT_FAILED, EXIT_USAGE, EXIT_REFUSED = 0, 1, 2, 3

DEFAULT_MANDATED = ('rhize-ops:parallel-agent-optimization',)
# invoked_emitted counts too: a prompt where the user followed the (baseline) suggestion is a case the candidate
# can LOSE by rerouting it. Without it the weak lane could only ever favor the candidate (Fable final review).
WEAK_OUTCOMES = ('invoked_emitted', 'invoked_unlisted', 'invoked_other_shortlisted')
WEAK_VIA = ('skill_tool', 'slash_command')            # skill_file_read is a separate, weaker kind of evidence
MIN_DISCORDANT = 10
ALPHA = 0.05
MAX_UNSCORABLE_SHARE = 0.20
CODEX_FIRST_LINE_BYTES = 512 * 1024
CODEX_USER_SOURCE = 'user'
MAX_JSON_BYTES = 64 * 1024 * 1024
HARNESS_RUN = Path('evals') / 'skill-map-routing' / 'run.py'
HARNESS_BASELINE = Path('evals') / 'skill-map-routing' / 'baseline.json'
HARNESS_TIMEOUT_SECONDS = 1800
ARMS = ('baseline', 'candidate')
CASE_TYPES = ('labeled', 'weak', 'silence')
PRECEDENCE = ['labeled', 'weak_positive', 'silence_negative']
ROUTER_CODE_FILES = ('rhize-context-manager/hooks/lib/route-core.js', 'rhize-context-manager/hooks/skill-router.js',
                     'rhize-context-manager/hooks/lib/laya-instrument.js')
CHILD_ENV_ALLOWLIST = ('HOME', 'USER', 'LOGNAME', 'PATH', 'TMPDIR', 'LANG', 'LC_ALL', 'SHELL')
GUARD_EXIT = 97

HEX40 = re.compile(r'[0-9a-f]{40}([0-9a-f]{24})?\Z')
TS = re.compile(r'(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,6}))?Z\Z')

NETWORK_GUARD = """'use strict';
// Tripwire preloaded into every route replay child. Route replay is pure routing and never calls Laya or any
// other service, so an attempt to open a socket or resolve a name is a defect, not a degraded mode.
const net = require('net');
const dgram = require('dgram');
const dns = require('dns');
function deny() {
  process.stderr.write('network_use_denied\\n');
  process.exit(%d);
}
net.Socket.prototype.connect = deny;
net.connect = deny;
net.createConnection = deny;
require('tls').connect = deny;
dgram.createSocket = deny;
for (const name of ['http', 'https', 'http2']) {
  const mod = require(name);
  for (const fn of ['request', 'get', 'connect']) if (typeof mod[fn] === 'function') mod[fn] = deny;
}
if (typeof globalThis.fetch === 'function') globalThis.fetch = deny;
for (const name of ['lookup', 'lookupService', 'resolve', 'resolve4', 'resolve6', 'resolveAny', 'reverse']) {
  dns[name] = deny;
}
""" % GUARD_EXIT


class RealTrafficError(Exception):
    """A bounded, non-secret failure with the process exit code to use."""

    def __init__(self, message, code=EXIT_USAGE):
        super().__init__(message)
        self.code = code


# ------------------------------------------------------------------ small helpers

def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def manifest_hash(manifest: dict) -> str:
    return sha256_bytes(canonical(manifest).encode('utf-8'))


def parse_record_ts(value) -> datetime:
    """Aware UTC datetime for a contract timestamp (YYYY-MM-DDTHH:MM:SS[.ffffff]Z)."""
    match = TS.match(value) if isinstance(value, str) else None
    if not match:
        raise ValueError('invalid timestamp')
    year, month, day, hour, minute, second = (int(part) for part in match.groups()[:6])
    micro = int((match.group(7) or '0').ljust(6, '0'))
    return datetime(year, month, day, hour, minute, second, micro, tzinfo=timezone.utc)


def parse_instant(value=None) -> datetime:
    """--now: None means the clock; a date, a datetime, or an ISO timestamp carrying Z or an offset."""
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            if re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
                return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            raise RealTrafficError('--now must be a date or an ISO timestamp') from None
    if parsed.tzinfo is None:
        raise RealTrafficError('--now needs a timezone (Z or an offset)')
    return parsed.astimezone(timezone.utc)


def iso(moment: datetime) -> str:
    moment = moment.astimezone(timezone.utc)
    return moment.strftime('%Y-%m-%dT%H:%M:%S.') + '%03dZ' % (moment.microsecond // 1000)


def rate(numerator: int, denominator: int):
    return round(numerator / denominator, 6) if denominator else None


def camel(reason: str) -> str:
    head, *rest = str(reason).split('_')
    return head + ''.join(part.capitalize() for part in rest)


def norm_ref(ref: str) -> str:
    return str(ref).strip().lstrip('/').lower()


def ref_of(skill_id):
    """'plugin:skill' for a skill id, else the id itself (a stable, text-free label)."""
    return outcomes.skill_ref(skill_id) or str(skill_id)


def route_matches(route_id, invoked) -> bool:
    """True when the routed skill id is the invoked 'plugin:skill' (or bare skill name)."""
    have = outcomes.skill_ref(route_id)
    if have is None:
        return False
    have, want = norm_ref(have), norm_ref(invoked)
    return have == want if ':' in want else have.split(':', 1)[1] == want


def ref_listed(ref, listed) -> bool:
    want = norm_ref(ref)
    for item in listed:
        item = norm_ref(item)
        if want == item or (':' not in want and item.split(':', 1)[-1] == want):
            return True
    return False


def find_node(node=None) -> str:
    found = node or shutil.which('node')
    if not found:
        raise RealTrafficError('node is required for the router replay')
    return found


# ------------------------------------------------------------------ git identity

def _git(checkout, *args) -> bytes:
    env = dict(os.environ, GIT_OPTIONAL_LOCKS='0', GIT_TERMINAL_PROMPT='0')
    try:
        done = subprocess.run(['git', '-C', str(checkout), '-c', 'core.excludesFile=/dev/null', *args],
                              capture_output=True, timeout=300, check=True, env=env)
    except (OSError, subprocess.SubprocessError):
        raise RealTrafficError('git could not read a checkout') from None
    return done.stdout


def git_head(checkout) -> str:
    head = _git(checkout, 'rev-parse', 'HEAD').decode('ascii', 'replace').strip()
    if not HEX40.match(head):
        raise RealTrafficError('git returned an unexpected HEAD')
    return head


def git_dirty(checkout) -> bool:
    return bool(_git(checkout, 'status', '--porcelain=v1', '--untracked-files=all').strip())


def git_diff_identity(checkout, base_head):
    """(sha256 of the checkout's diff against base_head, number of changed files)."""
    diff = _git(checkout, 'diff', '--no-ext-diff', '--no-textconv', '--no-color', '--no-renames', '--binary',
                '--full-index', '--src-prefix=a/', '--dst-prefix=b/', base_head, '--')
    names = _git(checkout, 'diff', '--no-renames', '--name-only', '-z', base_head, '--')
    return sha256_bytes(diff), len([name for name in names.split(b'\0') if name])


def router_code_sha(checkout):
    """sha256 over the router source files of a checkout, or None when they are not all present."""
    parts = []
    for relative in ROUTER_CODE_FILES:
        try:
            parts.append(evidence_fs.read_regular(Path(checkout) / relative, MAX_JSON_BYTES))
        except (OSError, ValueError):
            return None
    return sha256_bytes(b''.join(parts))


# ------------------------------------------------------------------ resolved index and map per arm

def build_arm_artifacts(checkout, out_dir, extra_args=(), python=None, timeout=600):
    """Run THIS checkout's build_local_skill_map.py with --out-dir pointing at out_dir; (index path, map path).

    The script resolves its static artifact, tag catalog and router inputs from its own checkout, so each arm is
    built from its own code and catalog. `extra_args` pass straight through (hermetic tests give it explicit
    --installed-plugins and friends). Its console output is discarded: it names local paths.
    """
    script = Path(checkout) / 'rhize-context-manager' / 'scripts' / 'build_local_skill_map.py'
    if not script.is_file():
        raise RealTrafficError('the checkout has no build_local_skill_map.py')
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        done = subprocess.run([python or sys.executable, str(script), '--out-dir', str(out_dir), *extra_args],
                              capture_output=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        raise RealTrafficError('build_local_skill_map.py could not run') from None
    index, skill_map = out_dir / 'skill-map.indexes.resolved.json', out_dir / 'skill-map.resolved.json'
    if done.returncode != 0 or not index.is_file() or not skill_map.is_file():
        raise RealTrafficError('build_local_skill_map.py did not produce a resolved index and map')
    return index, skill_map


def arm_sources(checkout, explicit_index, explicit_map, workdir, name, extra_args=()):
    """(index bytes, map bytes) for one arm: explicit files when given, else that checkout's own build."""
    if (explicit_index is None) != (explicit_map is None):
        raise RealTrafficError(f'give both the {name} index and the {name} map, or neither')
    if explicit_index is not None:
        index_path, map_path = Path(explicit_index), Path(explicit_map)
    else:
        index_path, map_path = build_arm_artifacts(checkout, Path(workdir) / name, extra_args)
    try:
        index_bytes = evidence_fs.read_regular(index_path, MAX_JSON_BYTES)
        map_bytes = evidence_fs.read_regular(map_path, MAX_JSON_BYTES)
        json.loads(index_bytes)
        json.loads(map_bytes)
    except (OSError, ValueError):
        raise RealTrafficError(f'the {name} index or map is missing or not JSON') from None
    return index_bytes, map_bytes


# ------------------------------------------------------------------ manifest

def default_rule(mandated=None) -> dict:
    return {
        'split': {'confirmatory': 'record ts strictly after freezeAt', 'dev': 'record ts at or before freezeAt'},
        'precedence': list(PRECEDENCE),
        'weakPositive': {'outcomes': list(WEAK_OUTCOMES), 'latencyTurns': 0, 'via': list(WEAK_VIA),
                         'mandatedSkills': sorted({norm_ref(item) for item in
                                                   (DEFAULT_MANDATED if mandated is None else mandated)})},
        'codexThreadSource': CODEX_USER_SOURCE,
        'keep': {'harnessMustPass': True, 'minDiscordant': MIN_DISCORDANT, 'alpha': ALPHA,
                 'silenceFireCountMayNotRise': True, 'maxUnscorableShare': MAX_UNSCORABLE_SHARE},
    }


MANIFEST_KEYS = {'schema', 'evaluator', 'freezeAt', 'baseline', 'candidate', 'diffSha256', 'diffFiles', 'rule',
                 'replay', 'arms', 'corpusAtFreeze', 'local'}
ARM_KEYS = {'head', 'dirty', 'indexSha256', 'mapSha256', 'routerCodeSha256'}


def validate_manifest(manifest) -> dict:
    """Shape check of a manifest read from disk; every failure is a bounded reason."""
    def bad(why):
        return RealTrafficError(f'the manifest is invalid ({why})', EXIT_REFUSED)

    if not isinstance(manifest, dict) or set(manifest) != MANIFEST_KEYS:
        raise bad('keys')
    if manifest['schema'] != MANIFEST_SCHEMA or manifest['evaluator'] != EVALUATOR:
        raise bad('schema')
    try:
        parse_record_ts(manifest['freezeAt'])
    except ValueError:
        raise bad('freezeAt') from None
    for name in ARMS:
        arm = manifest[name]
        if not isinstance(arm, dict) or set(arm) != ARM_KEYS or not HEX40.match(str(arm['head'])) \
                or not isinstance(arm['dirty'], bool) or not contract.HEX64.match(str(arm['indexSha256'])) \
                or not contract.HEX64.match(str(arm['mapSha256'])) \
                or (arm['routerCodeSha256'] is not None and not contract.HEX64.match(str(arm['routerCodeSha256']))):
            raise bad(name)
    if not contract.HEX64.match(str(manifest['diffSha256'])) or not isinstance(manifest['diffFiles'], int):
        raise bad('diff')
    rule = manifest['rule']
    fixed = default_rule()
    if not isinstance(rule, dict) or set(rule) != set(fixed):
        raise bad('rule')
    for key in ('split', 'precedence', 'codexThreadSource'):
        if rule[key] != fixed[key]:
            raise bad('rule differs from this evaluator')
    weak = rule['weakPositive']
    if not isinstance(weak, dict) or {k: v for k, v in weak.items() if k != 'mandatedSkills'} != \
            {k: v for k, v in fixed['weakPositive'].items() if k != 'mandatedSkills'}:
        raise bad('weak positive rule differs from this evaluator')
    mandated = weak.get('mandatedSkills')
    if not isinstance(mandated, list) or any(not isinstance(item, str) or not contract.SKILL_REF.match(item)
                                             for item in mandated):
        raise bad('mandated skills')
    keep = rule['keep']
    if not isinstance(keep, dict) or set(keep) != set(fixed['keep']) or keep['harnessMustPass'] is not True \
            or keep['silenceFireCountMayNotRise'] is not True:
        raise bad('keep rule')
    if isinstance(keep['minDiscordant'], bool) or not isinstance(keep['minDiscordant'], int) \
            or keep['minDiscordant'] < 1 or isinstance(keep['alpha'], bool) \
            or not isinstance(keep['alpha'], (int, float)) or not 0 < keep['alpha'] <= 0.5 \
            or isinstance(keep['maxUnscorableShare'], bool) \
            or not isinstance(keep['maxUnscorableShare'], (int, float)) or not 0 <= keep['maxUnscorableShare'] <= 1:
        raise bad('keep thresholds')
    arms, replay, local, corpus = manifest['arms'], manifest['replay'], manifest['local'], manifest['corpusAtFreeze']
    if not isinstance(arms, dict) or set(arms) != {'dir'} or not isinstance(arms['dir'], str) \
            or arms['dir'] != Path(arms['dir']).name or arms['dir'] in ('', '.', '..'):
        raise bad('arms')
    if not isinstance(replay, dict) or set(replay) != {'routerSourceSha256'} \
            or not contract.HEX64.match(str(replay['routerSourceSha256'])):
        raise bad('replay')
    if not isinstance(local, dict) or set(local) != {'baselineCheckout', 'candidateCheckout'}:
        raise bad('local')
    if not isinstance(corpus, dict) or set(corpus) != {'records', 'labels', 'outcomes'}:
        raise bad('corpusAtFreeze')
    return manifest


def load_manifest(path) -> dict:
    try:
        data = evidence_fs.read_regular(path, 1 << 20)
        manifest = json.loads(data.decode('utf-8'))
    except (OSError, ValueError):
        raise RealTrafficError('the manifest is missing or unreadable', EXIT_REFUSED) from None
    return validate_manifest(manifest)


def arm_paths(manifest, manifest_path, name):
    base = Path(manifest_path).resolve().parent / manifest['arms']['dir'] / name
    return base / 'index.json', base / 'map.json'


def freeze(baseline_checkout, candidate_checkout, out, root=None, now=None, baseline_index=None, baseline_map=None,
           candidate_index=None, candidate_map=None, mandated=None, allow_dirty=False, node=None,
           build_args=()) -> dict:
    """Freeze a candidate; writes the manifest (0600, never overwritten) and <out>.arms/. Returns the manifest."""
    node = find_node(node)
    baseline_checkout, candidate_checkout = Path(baseline_checkout).resolve(), Path(candidate_checkout).resolve()
    for checkout in (baseline_checkout, candidate_checkout):
        if not checkout.is_dir():
            raise RealTrafficError('a checkout directory does not exist')
    out = Path(out)
    arms_dir = out.with_name(out.name + '.arms')
    if out.exists() or out.is_symlink() or arms_dir.exists() or arms_dir.is_symlink():
        raise RealTrafficError('refusing to overwrite a frozen manifest', EXIT_REFUSED)
    freeze_at = parse_instant(now)
    root = Path(root) if root else records.default_root()
    recs, _ = cohorts.load_records(root)
    labels, _ = cohorts.load_labels(root)
    outs, _ = records.read(root, DECISION, 'outcomes')
    newest = max((parse_record_ts(rec['ts']) for rec in recs), default=None)
    if newest is not None and newest > freeze_at:
        raise RealTrafficError('freezeAt must not precede an existing record', EXIT_REFUSED)

    heads = {name: git_head(path) for name, path in zip(ARMS, (baseline_checkout, candidate_checkout))}
    dirty = {name: git_dirty(path) for name, path in zip(ARMS, (baseline_checkout, candidate_checkout))}
    if any(dirty.values()) and not allow_dirty:
        raise RealTrafficError('a checkout has uncommitted changes, commit them or pass --allow-dirty', EXIT_REFUSED)
    diff_sha, diff_files = git_diff_identity(candidate_checkout, heads['baseline'])
    code = {name: router_code_sha(path) for name, path in zip(ARMS, (baseline_checkout, candidate_checkout))}
    if code['baseline'] != code['candidate']:
        raise RealTrafficError('the candidate changes router code, this evaluator covers index and map changes only',
                               EXIT_REFUSED)

    workdir = Path(tempfile.mkdtemp(prefix='rt-freeze-'))
    created_arms = False
    try:
        sources = {
            'baseline': arm_sources(baseline_checkout, baseline_index, baseline_map, workdir, 'baseline', build_args),
            'candidate': arm_sources(candidate_checkout, candidate_index, candidate_map, workdir, 'candidate',
                                     build_args)}
        evidence_fs.private_dir(arms_dir)
        created_arms = True
        manifest = {'schema': MANIFEST_SCHEMA, 'evaluator': EVALUATOR, 'freezeAt': iso(freeze_at)}
        router_source = None
        for name in ARMS:
            index_bytes, map_bytes = sources[name]
            index_copy, map_copy = arms_dir / name / 'index.json', arms_dir / name / 'map.json'
            evidence_fs.write_private_atomic(index_copy, index_bytes)
            evidence_fs.write_private_atomic(map_copy, map_bytes)
            hashes = replay_hashes(node, index_copy, map_copy)
            router_source = router_source or hashes['routerSourceSha256']
            manifest[name] = {'head': heads[name], 'dirty': dirty[name], 'indexSha256': hashes['indexSha256'],
                              'mapSha256': sha256_bytes(map_bytes), 'routerCodeSha256': code[name]}
        manifest.update({
            'diffSha256': diff_sha, 'diffFiles': diff_files, 'rule': default_rule(mandated),
            'replay': {'routerSourceSha256': router_source}, 'arms': {'dir': arms_dir.name},
            'corpusAtFreeze': {'records': len(recs), 'labels': len(labels), 'outcomes': len(outs)},
            'local': {'baselineCheckout': str(baseline_checkout), 'candidateCheckout': str(candidate_checkout)}})
        validate_manifest(manifest)
        try:
            locked_io.write_private_exclusive(out, (json.dumps(manifest, indent=2, sort_keys=True) + '\n').encode())
        except FileExistsError:
            raise RealTrafficError('refusing to overwrite a frozen manifest', EXIT_REFUSED) from None
        return manifest
    except BaseException:
        if created_arms:
            shutil.rmtree(arms_dir, ignore_errors=True)
        raise
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def replay_hashes(node, index_path, map_path) -> dict:
    """indexSha256 and routerSourceSha256 as route_replay.js computes them, run in the same isolated environment."""
    workdir = Path(tempfile.mkdtemp(prefix='rt-hash-'))
    try:
        guard = workdir / 'network-guard.js'
        guard.write_text(NETWORK_GUARD, encoding='utf-8')
        done = subprocess.run([node, '--require', str(guard), str(backfill.REPLAY_SCRIPT), str(index_path),
                               str(map_path), '--hashes'], capture_output=True, text=True, timeout=60, check=True,
                              env=child_env(workdir), cwd=str(workdir))
        value = json.loads(done.stdout)
        for key in ('indexSha256', 'routerSourceSha256'):
            if not contract.HEX64.match(value[key]):
                raise ValueError('bad hash')
        return {key: value[key] for key in ('indexSha256', 'routerSourceSha256')}
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        raise RealTrafficError('route_replay.js could not read an index and map') from None
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def verify_arms(manifest, manifest_path, node) -> dict:
    """Check the frozen copies against the manifest hashes; {arm: (index path, map path)}."""
    found = {}
    for name in ARMS:
        index_path, map_path = arm_paths(manifest, manifest_path, name)
        try:
            map_sha = sha256_bytes(evidence_fs.read_regular(map_path, MAX_JSON_BYTES))
            evidence_fs.read_regular(index_path, MAX_JSON_BYTES)
        except (OSError, ValueError):
            raise RealTrafficError(f'a frozen {name} file is missing', EXIT_REFUSED) from None
        hashes = replay_hashes(node, index_path, map_path)
        if map_sha != manifest[name]['mapSha256'] or hashes['indexSha256'] != manifest[name]['indexSha256']:
            raise RealTrafficError(f'a frozen {name} file was modified', EXIT_REFUSED)
        if hashes['routerSourceSha256'] != manifest['replay']['routerSourceSha256']:
            raise RealTrafficError('the router source changed since the freeze', EXIT_REFUSED)
        found[name] = (index_path, map_path)
    return found


# ------------------------------------------------------------------ replay (prompt text never leaves memory)

class ArmReplayer(backfill.Replayer):
    """One long-lived route_replay.js process in an isolated environment; prompts travel over stdin only."""

    def __init__(self, node, index_path, map_path, env, cwd, guard):
        self.process = subprocess.Popen(
            [node, '--require', str(guard), str(backfill.REPLAY_SCRIPT), str(index_path), str(map_path)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding='utf-8',
            bufsize=1, env=env, cwd=str(cwd))
        self.counter = 0


def child_env(workdir) -> dict:
    """HOME and the basics unchanged, every writable location redirected to fresh temp dirs, nothing else."""
    workdir = Path(workdir)
    env = {key: os.environ[key] for key in CHILD_ENV_ALLOWLIST if key in os.environ}
    context = workdir / 'context-manager'
    for name in ('typed-decisions', 'xdg-data', 'context-manager'):
        (workdir / name).mkdir(mode=0o700, exist_ok=True)
    env.update({'RHIZE_TYPED_DECISIONS_ROOT': str(workdir / 'typed-decisions'),
                'XDG_DATA_HOME': str(workdir / 'xdg-data'),
                'RHIZE_CONTEXT_MANAGER_DIR': str(context),
                'RHIZE_SUGGESTION_LOG': str(context / 'suggestion-log.jsonl')})
    return env


@contextlib.contextmanager
def replay_session(arms, node):
    """Yield {arm: replayer} for {arm: (index path, map path)}; temp dirs and processes are cleaned up."""
    workdir = Path(tempfile.mkdtemp(prefix='rt-replay-'))
    replayers = {}
    try:
        guard = workdir / 'network-guard.js'
        guard.write_text(NETWORK_GUARD, encoding='utf-8')
        env = child_env(workdir)
        for name, (index_path, map_path) in arms.items():
            replayers[name] = ArmReplayer(node, index_path, map_path, env, workdir, guard)
        yield replayers
    finally:
        for replayer in replayers.values():
            with contextlib.suppress(Exception):
                replayer.close()
        shutil.rmtree(workdir, ignore_errors=True)


def route_of(reply):
    """(route skill id or None, ok). A malformed reply is not a route."""
    if not isinstance(reply, dict) or 'error' in reply or 'incumbent' not in reply:
        return None, False
    incumbent = reply['incumbent']
    if incumbent is None:
        return None, True
    skill_id = incumbent.get('skillId') if isinstance(incumbent, dict) else None
    return (skill_id, True) if isinstance(skill_id, str) else (None, False)


# ------------------------------------------------------------------ transcripts

def codex_thread_source(path):
    """thread_source of a Codex rollout from its FIRST line only (bounded), or None when it cannot be read."""
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
    except OSError:
        return None
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return None
        data = b''
        while len(data) <= CODEX_FIRST_LINE_BYTES and b'\n' not in data:
            chunk = os.read(fd, CODEX_FIRST_LINE_BYTES + 1 - len(data))
            if not chunk:
                break
            data += chunk
    except OSError:
        return None
    finally:
        os.close(fd)
    line, newline, _ = data.partition(b'\n')
    if len(line) > CODEX_FIRST_LINE_BYTES or (not newline and len(data) > CODEX_FIRST_LINE_BYTES):
        return None
    try:
        first = json.loads(line.decode('utf-8'))
    except ValueError:
        return None
    if not isinstance(first, dict) or first.get('type') != 'session_meta':
        return None
    payload = first.get('payload') if isinstance(first.get('payload'), dict) else {}
    value = payload.get('thread_source', first.get('thread_source'))
    return value if isinstance(value, str) else None


def recover_text(case, scanner):
    """(prompt text | None, exclusion reason | None). The text is held in memory by the caller only."""
    paths = scanner.paths().get(case['session'], [])
    if not paths:
        return None, 'transcript_unavailable'
    codex_paths = [path for path in paths if transcripts.is_codex_path(path)]
    if case['host'] == 'codex' or codex_paths:
        if not codex_paths:
            return None, 'codex_unverified'
        for path in codex_paths:
            source = codex_thread_source(path)
            if source is None:
                return None, 'codex_unverified'
            if source != CODEX_USER_SOURCE:
                return None, 'codex_non_user'
    match, reason = scanner.find_turn_by_hash(case['session'], case['prompt'], case['ts'])
    if match is None:
        return None, reason or 'context_missing'
    return match['text'], None


# ------------------------------------------------------------------ cases

def weak_ref(outcome, mandated):
    """The invoked 'plugin:skill' of an outcome that makes a weak positive, else None."""
    if not isinstance(outcome, dict) or outcome.get('outcome') not in WEAK_OUTCOMES:
        return None
    if outcome.get('via') not in WEAK_VIA or outcome.get('latencyTurns') != 0:
        return None
    ref = outcome.get('skillInvoked')
    if not isinstance(ref, str) or not ref.strip() or ref_listed(ref, mandated):
        return None
    return ref.strip().lstrip('/')


def label_rank(label):
    return (1 if label['basis'] == 'human_adjudicated' else 0, label['labeledAt'])


def select_cases(root, after=None, mandated=DEFAULT_MANDATED):
    """(cases, counts) for the records of `root`; only records with ts strictly after `after` when it is given.

    A case holds keys, hashes and ids, never text. A record is at most one case: labeled, else weak positive,
    else silence negative.
    """
    recs, _ = cohorts.load_records(root)
    labels, _ = cohorts.load_labels(root)
    outs, _ = records.read(Path(root), DECISION, 'outcomes')
    label_by, outcome_by = {}, {}
    for label in labels:
        current = label_by.get(label['occurrenceKey'])
        if current is None or label_rank(label) >= label_rank(current):
            label_by[label['occurrenceKey']] = label
    for outcome in outs:
        current = outcome_by.get(outcome['occurrenceKey'])
        if current is None or outcome['joinedAt'] >= current['joinedAt']:
            outcome_by[outcome['occurrenceKey']] = outcome
    counts = Counter()
    cases, weak_by_turn = [], {}
    for rec in sorted(recs, key=lambda item: (parse_record_ts(item['ts']), item['decisionId'])):
        if after is not None and not parse_record_ts(rec['ts']) > after:
            continue
        counts['records'] += 1
        base = {'key': rec['occurrenceKey'], 'session': rec['sessionHash'], 'prompt': rec['promptHash'],
                'ts': rec['ts'], 'host': rec['host'], 'shortlist': tuple(rec['shortlist'])}
        label = label_by.get(rec['occurrenceKey'])
        if label is not None:
            if label['ambiguous']:
                counts['ambiguousLabel'] += 1
                continue
            cases.append(dict(base, type='labeled', acceptable=frozenset(label['acceptable']),
                              best=label['bestSkill']))
            continue
        outcome = outcome_by.get(rec['occurrenceKey'])
        ref = weak_ref(outcome, mandated)
        if ref is not None:
            turn = (rec['sessionHash'], rec['promptHash'], norm_ref(ref), outcome['via'])
            if turn in weak_by_turn:                    # the same turn recorded twice: the nearest (latest) wins
                counts['weakDuplicate'] += 1
            weak_by_turn[turn] = dict(base, type='weak', invoked=ref)
            continue
        if rec['sourceStratum'] == 'silent_sample':
            cases.append(dict(base, type='silence'))
        else:
            counts['notACase'] += 1
    cases.extend(weak_by_turn.values())
    cases.sort(key=lambda item: (item['session'], item['ts'], item['key']))
    return cases, counts


def labeled_status(route, shortlist, acceptable) -> str:
    if route is None:
        return 'silentCorrect' if not acceptable else 'miss'
    if route not in shortlist:
        return 'unscorable'
    if route in acceptable:
        return 'hit'
    return 'falseFire' if not acceptable else 'wrong'


def score_case(case, route):
    """(status, correct). correct is None when the case is not comparable (an unscorable labeled route)."""
    if case['type'] == 'labeled':
        status = labeled_status(route, case['shortlist'], case['acceptable'])
        return status, None if status == 'unscorable' else status in ('hit', 'silentCorrect')
    if case['type'] == 'weak':
        if route is None:
            return 'silent', False
        ok = route_matches(route, case['invoked'])
        return ('recalled' if ok else 'wrong'), ok
    return ('fire', False) if route is not None else ('quiet', True)


LABELED_STATUSES = ('hit', 'silentCorrect', 'falseFire', 'wrong', 'miss', 'unscorable')
WEAK_STATUSES = ('recalled', 'wrong', 'silent')
SILENCE_STATUSES = ('fire', 'quiet')
STATUSES = {'labeled': LABELED_STATUSES, 'weak': WEAK_STATUSES, 'silence': SILENCE_STATUSES}


def empty_tally() -> dict:
    tally = {kind: {'total': 0, **{status: 0 for status in STATUSES[kind]}} for kind in CASE_TYPES}
    tally['labeled']['noFit'] = 0
    return tally


def add_to_tally(tally, case, status):
    block = tally[case['type']]
    block['total'] += 1
    block[status] += 1
    if case['type'] == 'labeled' and not case['acceptable']:
        block['noFit'] += 1


def type_metrics(tally) -> dict:
    labeled, weak, silence = tally['labeled'], tally['weak'], tally['silence']
    return {
        'labeled': {'hitRate': rate(labeled['hit'], labeled['total']),
                    'falseFireRate': rate(labeled['falseFire'], labeled['noFit']),
                    'unscorableShare': rate(labeled['unscorable'], labeled['total'])},
        'weak': {'recall': rate(weak['recalled'], weak['total'])},
        'silence': {'fireRate': rate(silence['fire'], silence['total'])}}


def replay_cases(cases, scanner, replayers, counts):
    """Recover each case's prompt in memory, replay it through every arm, keep ONLY the routes.

    Returns [{'case': case, 'routes': {arm: skill id | None}}]. The prompt text exists as a local variable for the
    duration of one iteration; it is never stored, logged or passed anywhere but the replay stdin pipes.
    """
    scored = []
    for case in cases:
        text, reason = recover_text(case, scanner)
        if text is None:
            counts[camel(reason)] += 1
            continue
        routes, ok = {}, True
        try:
            for name, replayer in replayers.items():
                route, valid = route_of(replayer.replay(text))
                routes[name] = route
                ok = ok and valid
        except backfill.BackfillError:
            raise RealTrafficError('the router replay process failed', EXIT_FAILED) from None
        finally:
            del text
        if not ok:
            counts['replayError'] += 1
            continue
        scored.append({'case': case, 'routes': routes})
    return scored


# ------------------------------------------------------------------ statistics and the keep rule

def sign_test(wins: int, losses: int) -> dict:
    """One-sided exact sign test: P(X >= wins) for X ~ Binomial(wins + losses, 1/2), as an exact fraction."""
    n = wins + losses
    tail = sum(comb(n, k) for k in range(wins, n + 1))
    exact = Fraction(tail, 2 ** n)
    return {'n': n, 'wins': wins, 'tail': tail, 'exact': exact, 'pValue': float(exact)}


def decide(*, harness_status, discordant, wins, losses, baseline_fires, candidate_fires, candidate_unscorable,
           candidate_labeled, rule) -> dict:
    """The frozen keep rule. verdict is keep | insufficient | discard | blocked; blockers name every unmet condition.

    `blocked` (not final) means the harness gave no pass/fail answer (not_run, unavailable, invalid_result,
    candidate_mismatch): an infrastructure gap is never turned into a permanent discard.
    """
    keep = rule['keep']
    test = sign_test(wins, losses)
    significant = test['exact'] <= Fraction(str(keep['alpha'])) and wins > losses
    unscorable_ok = (candidate_labeled == 0 or
                     Fraction(candidate_unscorable, candidate_labeled) <= Fraction(str(keep['maxUnscorableShare'])))
    checks = [('harness', harness_status == 'pass'),
              ('minDiscordant', discordant >= keep['minDiscordant']),
              ('signTest', significant),
              ('silenceFireCount', candidate_fires <= baseline_fires),
              ('unscorableShare', unscorable_ok)]
    blockers = [name for name, ok in checks if not ok]
    if not blockers:
        verdict = 'keep'
    elif harness_status not in ('pass', 'fail'):
        verdict = 'blocked'
    elif discordant < keep['minDiscordant']:
        verdict = 'insufficient'
    else:
        verdict = 'discard'
    return {'verdict': verdict, 'blockers': blockers, 'signTest': {
        'n': test['n'], 'wins': wins, 'pValue': test['pValue'], 'alpha': keep['alpha']}}


# ------------------------------------------------------------------ harness status

def harness_from_result(path, manifest) -> str:
    """pass | fail | invalid_result | candidate_mismatch from a small JSON written after run.py --check."""
    try:
        data = json.loads(evidence_fs.read_regular(path, 64 * 1024).decode('utf-8'))
    except (OSError, ValueError):
        return 'invalid_result'
    if not isinstance(data, dict):
        return 'invalid_result'
    bound = data.get('candidateDiffSha256')
    if bound is not None and bound != manifest['diffSha256']:
        return 'candidate_mismatch'
    code = data.get('exitCode', data.get('exit_code'))
    if isinstance(code, int) and not isinstance(code, bool):
        return 'pass' if code == 0 else 'fail'
    if isinstance(data.get('passed'), bool):
        return 'pass' if data['passed'] else 'fail'
    if data.get('status') in ('pass', 'fail'):
        return data['status']
    return 'invalid_result'


def run_harness(candidate_checkout, timeout=HARNESS_TIMEOUT_SECONDS) -> str:
    """Run the routing harness gate on the candidate; 'pass' (exit 0), 'fail', or 'unavailable'."""
    out = Path(tempfile.mkdtemp(prefix='rt-harness-'))
    try:
        done = subprocess.run([sys.executable, str(HARNESS_RUN), '--checkout', str(candidate_checkout),
                               '--check', str(HARNESS_BASELINE), '--out', str(out)],
                              capture_output=True, timeout=timeout, cwd=str(REPO))
        return 'pass' if done.returncode == 0 else 'fail'
    except (OSError, subprocess.SubprocessError):
        return 'unavailable'
    finally:
        shutil.rmtree(out, ignore_errors=True)


def resolve_harness(manifest, harness_result, run_flag, candidate_checkout, runner) -> str:
    if harness_result is not None and run_flag:
        raise RealTrafficError('give --harness-result or --run-harness, not both')
    if harness_result is not None:
        return harness_from_result(harness_result, manifest)
    if not run_flag:
        return 'not_run'
    checkout = Path(candidate_checkout or manifest['local']['candidateCheckout'])
    try:
        if git_head(checkout) != manifest['candidate']['head']:
            return 'candidate_mismatch'
        diff_sha, _ = git_diff_identity(checkout, manifest['baseline']['head'])
    except RealTrafficError:
        return 'unavailable'
    if diff_sha != manifest['diffSha256']:
        return 'candidate_mismatch'
    return (runner or run_harness)(checkout)


# ------------------------------------------------------------------ outputs

def append_ledger(root, line: dict) -> None:
    """Append one JSON line to <root>/skill-fit/improvement/ledger.jsonl: 0600, private dirs, symlinks refused."""
    root = Path(root)
    try:
        directory = records.private_dir(root / DECISION / 'improvement', anchor=root)
    except ValueError:
        raise RealTrafficError('a symlinked path under the root was refused', EXIT_REFUSED) from None
    evidence_fs.tighten(root / DECISION)
    evidence_fs.tighten(directory)
    payload = (json.dumps(line, separators=(',', ':'), sort_keys=True) + '\n').encode('utf-8')
    path = directory / 'ledger.jsonl'
    with locked_io.file_lock(directory / 'ledger.lock'):
        try:
            fd = os.open(path, os.O_RDWR | os.O_APPEND | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        except OSError:
            raise RealTrafficError('the ledger path was refused (symlink or unwritable)', EXIT_REFUSED) from None
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise RealTrafficError('the ledger is not a regular file', EXIT_REFUSED)
            if stat.S_IMODE(info.st_mode) & 0o077:
                os.fchmod(fd, 0o600)
            if info.st_size and os.pread(fd, 1, info.st_size - 1) != b'\n':
                payload = b'\n' + payload                      # terminate a torn final line from an earlier crash
            os.write(fd, payload)
            os.fsync(fd)
        finally:
            os.close(fd)


def write_report(path, report: dict) -> None:
    try:
        evidence_fs.write_private_atomic(Path(path), (json.dumps(report, indent=2, sort_keys=True) + '\n').encode())
    except ValueError:
        raise RealTrafficError('the report path was refused', EXIT_REFUSED) from None


def make_scanner(transcripts_roots, scanner=None):
    return scanner or transcripts.TranscriptScanner(transcripts_roots or backfill.default_roots())


# ------------------------------------------------------------------ evaluate

def evaluate(manifest_path, root, transcripts_roots=None, harness_result=None, run_harness_flag=False,
             candidate_checkout=None, now=None, node=None, scanner=None, replay_factory=None, harness_runner=None):
    """Confirm a frozen candidate on traffic recorded after the freeze. Returns (report, ledger line)."""
    node = find_node(node)
    manifest = load_manifest(manifest_path)
    mhash = manifest_hash(manifest)
    freeze_at = parse_record_ts(manifest['freezeAt'])
    arms = verify_arms(manifest, manifest_path, node)
    harness_status = resolve_harness(manifest, harness_result, run_harness_flag, candidate_checkout, harness_runner)
    rule = manifest['rule']
    cases, counts = select_cases(Path(root), after=freeze_at, mandated=rule['weakPositive']['mandatedSkills'])
    scanner = make_scanner(transcripts_roots, scanner)
    factory = replay_factory or replay_session
    with factory(arms, node) as replayers:
        scored = replay_cases(cases, scanner, replayers, counts)

    tally = {name: empty_tally() for name in ARMS}
    wins = losses = 0
    by_type = {kind: {'candidateWins': 0, 'baselineWins': 0} for kind in CASE_TYPES}
    discordant_cases, not_comparable = [], 0
    for item in scored:
        case, correct = item['case'], {}
        for name in ARMS:
            status, correct[name] = score_case(case, item['routes'][name])
            add_to_tally(tally[name], case, status)
        if correct['baseline'] is None or correct['candidate'] is None:
            not_comparable += 1
        elif correct['baseline'] != correct['candidate']:
            winner = 'candidate' if correct['candidate'] else 'baseline'
            wins, losses = wins + (winner == 'candidate'), losses + (winner == 'baseline')
            by_type[case['type']][winner + 'Wins'] += 1
            discordant_cases.append({'occurrenceKey': case['key'], 'type': case['type'], 'winner': winner})
    verdict = decide(harness_status=harness_status, discordant=wins + losses, wins=wins, losses=losses,
                     baseline_fires=tally['baseline']['silence']['fire'],
                     candidate_fires=tally['candidate']['silence']['fire'],
                     candidate_unscorable=tally['candidate']['labeled']['unscorable'],
                     candidate_labeled=tally['candidate']['labeled']['total'], rule=rule)
    excluded = {key: counts[key] for key in sorted(counts) if key != 'records'}
    ledger_line = {
        'schema': LEDGER_SCHEMA, 'manifestSha256': mhash, 'freezeAt': manifest['freezeAt'],
        'evaluatedAt': iso(parse_instant(now)),
        'cases': {'recordsAfterFreeze': counts['records'], 'scored': len(scored),
                  'byType': {kind: sum(1 for item in scored if item['case']['type'] == kind) for kind in CASE_TYPES},
                  'notComparable': not_comparable, 'excluded': excluded},
        'counts': tally,
        'discordant': {'total': wins + losses, 'candidateWins': wins, 'baselineWins': losses, 'byType': by_type},
        'signTest': verdict['signTest'],
        'harness': {'status': harness_status}, 'blockers': verdict['blockers'], 'verdict': verdict['verdict']}
    report = dict(ledger_line, schema=REPORT_SCHEMA, ledgerSchema=LEDGER_SCHEMA)
    report['metrics'] = {name: type_metrics(tally[name]) for name in ARMS}
    report['discordantCases'] = discordant_cases
    report['replay'] = {'promptTransport': 'stdin', 'networkGuard': True, 'tempEnvironment': True}
    return report, ledger_line


def run_evaluate(args) -> dict:
    report, ledger_line = evaluate(args.manifest, args.root, args.transcripts, args.harness_result,
                                   args.run_harness, args.candidate_checkout, args.now)
    append_ledger(args.root, ledger_line)
    write_report(args.out, report)
    return {'status': 'completed', 'verdict': report['verdict'], 'blockers': report['blockers'],
            'discordant': report['discordant']['total'], 'pValue': report['signTest']['pValue'],
            'harness': report['harness']['status'], 'manifestSha256': report['manifestSha256']}


# ------------------------------------------------------------------ dev report

def top_list(counter, limit):
    return [dict(skill=skill, **detail) for skill, detail in
            sorted(counter.items(), key=lambda item: (-item[1]['total'], item[0]))[:limit]]


def dev_report(root, baseline_checkout, transcripts_roots=None, baseline_index=None, baseline_map=None,
               mandated=None, top=10, now=None, node=None, scanner=None, replay_factory=None, build_args=()) -> dict:
    """Baseline metrics on the data available now; no keep decision. Counts and skill ids only."""
    node = find_node(node)
    baseline_checkout = Path(baseline_checkout).resolve()
    mandated = DEFAULT_MANDATED if mandated is None else mandated
    workdir = Path(tempfile.mkdtemp(prefix='rt-dev-'))
    try:
        index_bytes, map_bytes = arm_sources(baseline_checkout, baseline_index, baseline_map, workdir, 'baseline',
                                             build_args)
        index_path, map_path = workdir / 'index.json', workdir / 'map.json'
        index_path.write_bytes(index_bytes)
        map_path.write_bytes(map_bytes)
        hashes = replay_hashes(node, index_path, map_path)
        cases, counts = select_cases(Path(root), after=None, mandated=mandated)
        scanner = make_scanner(transcripts_roots, scanner)
        with (replay_factory or replay_session)({'baseline': (index_path, map_path)}, node) as replayers:
            scored = replay_cases(cases, scanner, replayers, counts)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    tally = empty_tally()
    missed, false_fires = {}, {}

    def bump(table, skill, field):
        entry = table.setdefault(skill, {'total': 0})
        entry['total'] += 1
        entry[field] = entry.get(field, 0) + 1

    for item in scored:
        case, route = item['case'], item['routes']['baseline']
        status, _ = score_case(case, route)
        add_to_tally(tally, case, status)
        if case['type'] == 'labeled' and status in ('miss', 'wrong'):
            bump(missed, norm_ref(ref_of(case['best'])), 'silent' if status == 'miss' else 'misrouted')
        elif case['type'] == 'weak' and status in ('silent', 'wrong'):
            bump(missed, norm_ref(case['invoked']), 'silent' if status == 'silent' else 'misrouted')
        elif status == 'falseFire' or (case['type'] == 'silence' and status == 'fire'):
            bump(false_fires, norm_ref(ref_of(route)), 'fires')
    return {
        'schema': DEV_REPORT_SCHEMA, 'generatedAt': iso(parse_instant(now)),
        'note': 'baseline metrics for proposing candidates; no keep decision is made here',
        'baseline': {'head': git_head(baseline_checkout) if (baseline_checkout / '.git').exists() else None,
                     'indexSha256': hashes['indexSha256'], 'mapSha256': sha256_bytes(map_bytes)},
        'cases': {'records': counts['records'], 'scored': len(scored),
                  'byType': {kind: sum(1 for item in scored if item['case']['type'] == kind) for kind in CASE_TYPES},
                  'excluded': {key: counts[key] for key in sorted(counts) if key != 'records'}},
        'counts': tally, 'metrics': type_metrics(tally),
        'topMisses': top_list(missed, top), 'topFalseFires': top_list(false_fires, top)}


def run_dev_report(args) -> dict:
    report = dev_report(args.root, args.baseline_checkout, args.transcripts, args.baseline_index, args.baseline_map,
                        args.mandated_skill, args.top, args.now)
    write_report(args.out, report)
    return {'status': 'completed', 'cases': report['cases']['scored'], 'topMisses': len(report['topMisses'])}


def run_freeze(args) -> dict:
    manifest = freeze(args.baseline_checkout, args.candidate_checkout, args.out, args.root, args.now,
                      args.baseline_index, args.baseline_map, args.candidate_index, args.candidate_map,
                      args.mandated_skill, args.allow_dirty)
    return {'status': 'frozen', 'manifestSha256': manifest_hash(manifest), 'freezeAt': manifest['freezeAt'],
            'diffFiles': manifest['diffFiles']}


# ------------------------------------------------------------------ CLI

def build_parser():
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    sub = parser.add_subparsers(dest='command', required=True)

    freeze_p = sub.add_parser('freeze', help='freeze a candidate: identity, hashes, freezeAt and rules')
    freeze_p.add_argument('--baseline-checkout', required=True)
    freeze_p.add_argument('--candidate-checkout', required=True)
    freeze_p.add_argument('--out', required=True, help='manifest path (never overwritten); arms go to <out>.arms/')
    freeze_p.add_argument('--root', default=None, help='typed-decisions root (default ~/.local/share/rhize/...)')
    freeze_p.add_argument('--now', default=None, help='freezeAt (default: the clock)')
    for arm in ARMS:
        freeze_p.add_argument(f'--{arm}-index', default=None, help=f'explicit resolved router index for the {arm}')
        freeze_p.add_argument(f'--{arm}-map', default=None, help=f'explicit resolved skill map for the {arm}')
    freeze_p.add_argument('--mandated-skill', action='append', default=None, metavar='REF',
                          help='plugin:skill whose invocation is mandated, not chosen (repeatable; replaces the '
                               'default rhize-ops:parallel-agent-optimization)')
    freeze_p.add_argument('--allow-dirty', action='store_true', help='record a checkout with uncommitted changes')
    freeze_p.set_defaults(func=run_freeze)

    evaluate_p = sub.add_parser('evaluate', help='confirm a frozen candidate on traffic recorded after the freeze')
    evaluate_p.add_argument('--manifest', required=True)
    evaluate_p.add_argument('--root', required=True)
    evaluate_p.add_argument('--transcripts', nargs='+', default=None, metavar='DIR')
    group = evaluate_p.add_mutually_exclusive_group()
    group.add_argument('--harness-result', default=None, metavar='RESULT_JSON',
                       help='JSON from run.py --check: {"exitCode": N} (optionally with candidateDiffSha256)')
    group.add_argument('--run-harness', action='store_true',
                       help='run evals/skill-map-routing/run.py --checkout C --check baseline.json now')
    evaluate_p.add_argument('--candidate-checkout', default=None,
                            help='override the candidate path recorded in the manifest (--run-harness)')
    evaluate_p.add_argument('--out', required=True)
    evaluate_p.add_argument('--now', default=None)
    evaluate_p.set_defaults(func=run_evaluate)

    dev_p = sub.add_parser('dev-report', help='baseline metrics and top routing misses; makes no keep decision')
    dev_p.add_argument('--root', required=True)
    dev_p.add_argument('--baseline-checkout', required=True)
    dev_p.add_argument('--baseline-index', default=None)
    dev_p.add_argument('--baseline-map', default=None)
    dev_p.add_argument('--transcripts', nargs='+', default=None, metavar='DIR')
    dev_p.add_argument('--mandated-skill', action='append', default=None, metavar='REF')
    dev_p.add_argument('--top', type=int, default=10)
    dev_p.add_argument('--out', required=True)
    dev_p.add_argument('--now', default=None)
    dev_p.set_defaults(func=run_dev_report)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        summary = args.func(args)
    except RealTrafficError as exc:
        print(json.dumps({'status': 'refused', 'reason': contract.safe_reason(exc)}))
        return exc.code
    except Exception as exc:  # noqa: BLE001 - a bounded error type, never text from a prompt or a transcript
        print(json.dumps({'status': 'failed', 'error': type(exc).__name__, 'reason': contract.safe_reason(exc)}))
        return EXIT_FAILED
    print(json.dumps(summary, sort_keys=True))
    return EXIT_OK


if __name__ == '__main__':
    raise SystemExit(main())
