"""Private JSONL storage for typed-decision records, labels, outcomes and cohort events.

Contract module (coordinator-owned). Layout (plan §4.4):

    <root>/<decision>/<kind>/<YYYY-MM-DD>.jsonl      kind in records | labels | outcomes | cohorts

<root> defaults to ~/.local/share/rhize/typed-decisions and can be overridden with
RHIZE_TYPED_DECISIONS_ROOT (tests). Directories are 0700, files 0600, symlinks are refused, and
every appended object is validated by typed_decisions.contract first. The UTC day comes from the
object's own timestamp (ts / labeledAt / joinedAt / at). The Node hook writes records with the
same layout (hooks/lib/typed-decisions.js recordsPath()).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from typed_decisions import contract

KINDS = {
    'records': (contract.validate_record, 'ts'),
    'labels': (contract.validate_label, 'labeledAt'),
    'outcomes': (contract.validate_outcome, 'joinedAt'),
    'cohorts': (contract.validate_cohort_event, 'at'),
}
MAX_LINE_BYTES = 1 << 20


def default_root() -> Path:
    override = os.environ.get('RHIZE_TYPED_DECISIONS_ROOT')
    if override:
        return Path(override)
    return Path.home() / '.local' / 'share' / 'rhize' / 'typed-decisions'


def _safe_dir(path: Path) -> Path:
    for parent in [path, *path.parents]:
        if parent.is_symlink():
            raise ValueError('symlinked typed-decision path refused')
        if parent == parent.parent:
            break
    # mkdir(parents=True, mode=...) applies the mode to the leaf only; create every missing level
    # ourselves so intermediate directories are private too (umask can only narrow 0700).
    missing = []
    probe = path
    while not probe.exists():
        missing.append(probe)
        probe = probe.parent
    for directory in reversed(missing):
        try:
            directory.mkdir(mode=0o700)
        except FileExistsError:
            pass
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError('symlinked typed-decision path refused')
    return path


def kind_dir(root: Path, decision: str, kind: str) -> Path:
    if decision not in contract.RECORDED_DECISIONS or kind not in KINDS:
        raise ValueError('unknown decision or kind')
    return _safe_dir(Path(root) / decision / kind)


def append(root: Path, decision: str, kind: str, obj: dict) -> Path:
    """Validate and append one object; returns the file written."""
    validator, ts_field = KINDS[kind]
    validator(obj)
    if obj.get('decision', decision) != decision:
        raise ValueError('decision mismatch')
    day = contract.minute_of(obj[ts_field])[:10]
    path = kind_dir(root, decision, kind) / f'{day}.jsonl'
    line = (json.dumps(obj, separators=(',', ':'), ensure_ascii=False, sort_keys=True) + '\n').encode('utf-8')
    if len(line) > MAX_LINE_BYTES:
        raise ValueError('line too large')
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(path, flags, 0o600)
    try:
        os.write(fd, line)
    finally:
        os.close(fd)
    return path


def read(root: Path, decision: str, kind: str, since_day: str | None = None) -> tuple[list[dict], int]:
    """Return (valid objects in file/line order, count of invalid or unreadable lines).

    Invalid lines are skipped, never repaired. A missing directory reads as empty.
    """
    validator, _ = KINDS[kind]
    base = Path(root) / decision / kind
    if not base.exists():
        return [], 0
    if base.is_symlink():
        raise ValueError('symlinked typed-decision path refused')
    items, invalid = [], 0
    for path in sorted(base.glob('*.jsonl')):
        if path.is_symlink() or (since_day and path.stem < since_day):
            continue
        with open(path, 'rb') as stream:
            for raw in stream:
                if len(raw) > MAX_LINE_BYTES:
                    invalid += 1
                    continue
                try:
                    items.append(validator(json.loads(raw)))
                except (ValueError, UnicodeDecodeError):
                    invalid += 1
    return items, invalid


def dedupe_by_occurrence(items: list[dict]) -> list[dict]:
    """Keep the first object per occurrenceKey (input order), e.g. before any split or sample."""
    seen, out = set(), []
    for item in items:
        key = item.get('occurrenceKey')
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out
