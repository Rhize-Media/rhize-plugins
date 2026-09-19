"""Translate the supported registry metadata contract into inert scoped references."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

PROTOCOL = 'rhize-procedural-recall-v1'


def recall(launcher: Path, query: str, *, tenant: str, project: str, task: str | None = None,
           artifact_scope: dict | None = None) -> dict:
    """The caller supplies the installed canonical launcher, never a registry/DB path."""
    result = {'name': 'procedural-memory', 'memoryType': 'procedural', 'protocolVersion': PROTOCOL,
              'status': 'unavailable', 'reason': 'supported_metadata_read_unavailable', 'candidates': []}
    try:
        argv = ['bash', str(launcher), 'recall', query, '--json', '--top-k', '5']
        if artifact_scope:
            argv.extend(['--scope-json', json.dumps(artifact_scope)])
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=4, check=False)
        if proc.returncode != 0 or len(proc.stdout) > 131072:
            return result
        value = json.loads(proc.stdout)
        return from_response(value, tenant=tenant, project=project, task=task)
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired):
        return result


def from_response(value: dict, *, tenant: str, project: str, task: str | None = None) -> dict:
    if not isinstance(value, dict) or value.get('protocolVersion') != PROTOCOL or value.get('executionAuthorized') is not False:
        raise ValueError('unsupported procedural metadata contract')
    status = value.get('status')
    refs = value.get('references')
    if status not in {'available', 'partial', 'empty', 'unavailable'} or not isinstance(refs, list) or len(refs) > 10:
        raise ValueError('invalid procedural metadata response')
    if status in {'empty', 'unavailable'} and refs:
        raise ValueError('contradictory procedural metadata status')
    candidates = []
    for ref in refs:
        if not isinstance(ref, dict) or ref.get('executionAuthorized') is not False:
            raise ValueError('metadata cannot confer execution authority')
        # A tampered/unpromoted artifact is still visible in CLI diagnostics, but
        # is not admitted as a current memory reference.
        if ref.get('digestMatches') is not True:
            continue
        if any(not isinstance(ref.get(k), str) for k in ('sourceId','sourceRevision','kind','name','version','description','trust','health')) or not re.fullmatch(r'[0-9a-f]{64}', ref['sourceRevision']) or not isinstance(value.get('observedAt'), str) or type(ref.get('score')) not in (int, float) or not 0 <= ref['score'] <= 10000:
            raise ValueError('malformed procedural reference')
        candidates.append({
            'sourceSystem': 'procedural-memory', 'sourceId': ref['sourceId'],
            'sourceRevision': ref['sourceRevision'], 'tenant': tenant, 'project': project, 'task': task,
            'sensitivity': 'internal', 'recordedAt': value['observedAt'],
            'trustClass': 'unverified', 'retentionClass': 'session', 'contentRole': 'procedure-reference',
            'relevance': min(1.0, ref['score'] / 20),
            'provenance': [f"{ref['kind']}:{ref['name']}@{ref['version']}"],
            'content': json.dumps({k: ref[k] for k in ('kind', 'name', 'version', 'description', 'trust', 'health', 'sourceRevision', 'executionAuthorized')}, sort_keys=True),
        })
    if refs and not candidates:
        status = 'stale'
    return {'name': 'procedural-memory', 'memoryType': 'procedural', 'protocolVersion': PROTOCOL,
            'status': status, 'reason': 'metadata_reference_only', 'candidates': candidates}
