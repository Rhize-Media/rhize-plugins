"""Prefix-capable transcript scanner for the typed-decision evidence pipeline (plan §4.5).

Reuses pilot_autolabel's `transcript_message` (Claude and Codex line layouts) and `choose_match`
(repeated identical prompts are resolved by timestamp) without editing them. Everything read from a
transcript stays in memory: callers get text and context back, and nothing here writes any of it.

    find_turn(session_id, prompt_prefix16, observed_at, roots) -> (match | None, reason)
        match = {'text', 'prior', 'timestamp', 'path', 'line', 'transcriptRef'}; reason is None on success or one
        of 'transcript_unavailable' | 'context_missing' | 'context_ambiguous'.
    session_index(roots) -> {sha256(session_id): transcript Path}
    skill_invocations(path, after_ts) -> [{'skillRef', 'via', 'ts', 'userTurnsAfter'}]
        via is 'skill_tool' (an assistant `Skill` tool_use, input.skill) or 'slash_command' (a user turn carrying
        a <command-name>/plugin:skill</command-name> marker).

Reads are bounded: a transcript larger than MAX_TRANSCRIPT_BYTES is 'transcript_unavailable', lines are
streamed, and a single line larger than MAX_LINE_BYTES is skipped. Symlinks are never followed. Claude
transcripts are fully supported; Codex transcripts can be searched for turns but have no skill-invocation
parser, so skill_invocations() reports them as unavailable.
"""
from __future__ import annotations

import bisect
import hashlib
import json
import os
import re
import stat
import sys
from collections import OrderedDict, deque
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pilot_autolabel as auto  # noqa: E402

MAX_TRANSCRIPT_BYTES = 64 * 1024 * 1024
MAX_LINE_BYTES = 8 * 1024 * 1024
PRIOR_TURNS = auto.PRIOR_TURNS
UUID = auto.TranscriptIndex.UUID
COMMAND_NAME = re.compile(r'<command-name>\s*/?([^<\s]{1,160})\s*</command-name>')
HEX = re.compile(r'[0-9a-f]{4,64}\Z')
# Claude Code's own slash commands are not skills; a bare command name in this set is never reported.
BUILTIN_COMMANDS = frozenset((
    'add-dir', 'agents', 'bug', 'clear', 'compact', 'config', 'context', 'cost', 'doctor', 'effort', 'exit',
    'export', 'fast', 'feedback', 'help', 'hooks', 'ide', 'init', 'login', 'logout', 'mcp', 'memory', 'model',
    'output-style', 'permissions', 'plugin', 'plugins', 'pr-comments', 'privacy-settings', 'quit',
    'release-notes', 'reload-plugins', 'resume', 'review', 'rewind', 'security-review', 'skills', 'status',
    'statusline', 'tasks', 'terminal-setup', 'theme', 'todos', 'upgrade', 'usage', 'vim'))


class TranscriptError(Exception):
    """A transcript cannot be used; `reason` is the bounded, non-secret cause."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _iso_to_epoch(value):
    return auto._timestamp(value)  # noqa: SLF001 - the shared timestamp parser, deliberately not forked


# ------------------------------------------------------------------ discovery

def session_paths(roots) -> dict:
    """{sha256(session_id): [transcript paths]} for every <...>-<uuid>.jsonl under the roots (no symlinks)."""
    found: dict = {}
    for base in roots:
        base = Path(base)
        if base.is_symlink() or not base.is_dir():
            continue
        for folder, dirs, files in os.walk(base, followlinks=False):
            dirs.sort()
            for name in sorted(files):
                if not name.endswith('.jsonl'):
                    continue
                match = UUID.search(name[:-len('.jsonl')])
                path = Path(folder) / name
                if match and not path.is_symlink():
                    found.setdefault(sha256_text(match.group(1)), []).append(path)
    return found


def session_index(roots) -> dict:
    """{sha256(session_id): transcript path}; a session with several files maps to the first in path order."""
    return {key: paths[0] for key, paths in session_paths(roots).items()}


def is_codex_path(path) -> bool:
    return Path(path).name.startswith('rollout-')


# ------------------------------------------------------------------ parsing

class Parsed:
    """The lightweight, in-memory view of one transcript file."""

    def __init__(self, path, size):
        self.path, self.size = Path(path), size
        self.sha256 = None
        self.codex = is_codex_path(path)
        self.turns: list = []          # user-typed turns: line, timestamp, epoch, text, hash, human, prior
        self.invocations: list = []    # line, timestamp, epoch, ref, via


def _lines(handle, digest):
    """Yield raw lines (bytes) with a hard per-line cap, feeding every byte read into `digest`."""
    while True:
        raw = handle.readline(MAX_LINE_BYTES + 1)
        if not raw:
            return
        digest.update(raw)
        if len(raw) > MAX_LINE_BYTES and not raw.endswith(b'\n'):
            while True:
                rest = handle.readline(MAX_LINE_BYTES)
                digest.update(rest)
                if not rest or rest.endswith(b'\n'):
                    break
            yield None
            continue
        yield raw


def _skill_uses(record):
    """Skill refs of the assistant `Skill` tool_use blocks in one transcript record."""
    if record.get('type') != 'assistant' or record.get('isSidechain') or record.get('isMeta'):
        return
    message = record.get('message')
    content = message.get('content') if isinstance(message, dict) else None
    if not isinstance(content, list):
        return
    for part in content:
        if isinstance(part, dict) and part.get('type') == 'tool_use' and part.get('name') == 'Skill':
            ref = part.get('input', {}).get('skill') if isinstance(part.get('input'), dict) else None
            if isinstance(ref, str) and ref.strip():
                yield ref.strip().lstrip('/')


def parse_transcript(path) -> Parsed:
    """Stream one transcript. Raises TranscriptError('transcript_unavailable') when it cannot be read."""
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
    except OSError:
        raise TranscriptError('transcript_unavailable') from None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_TRANSCRIPT_BYTES:
            raise TranscriptError('transcript_unavailable')
        handle = os.fdopen(fd, 'rb')
    except BaseException:
        os.close(fd)
        raise
    parsed = Parsed(path, info.st_size)
    digest = hashlib.sha256()
    prior: deque = deque(maxlen=PRIOR_TURNS * 2)
    with handle:
        for number, raw in enumerate(_lines(handle, digest), 1):
            if raw is None:
                continue
            try:
                record = json.loads(raw.decode('utf-8', 'replace'))
            except ValueError:
                continue
            if not isinstance(record, dict):
                continue
            if record.get('type') == 'session_meta':
                parsed.codex = True
            stamp = record.get('timestamp')
            epoch = _iso_to_epoch(stamp)
            for ref in _skill_uses(record):
                parsed.invocations.append({'line': number, 'timestamp': stamp, 'epoch': epoch, 'ref': ref,
                                           'via': 'skill_tool'})
            role, text = auto.transcript_message(record)
            if role != 'user' or not text:
                continue
            boiler = any(marker in text for marker in auto.BOILERPLATE)
            parsed.turns.append({'line': number, 'timestamp': stamp, 'epoch': epoch, 'text': text,
                                 'hash': sha256_text(text), 'human': not boiler,
                                 'prior': list(prior)[-PRIOR_TURNS:]})
            command = None if boiler else COMMAND_NAME.search(text)
            if command:
                parsed.invocations.append({'line': number, 'timestamp': stamp, 'epoch': epoch,
                                           'ref': command.group(1), 'via': 'slash_command'})
            if not boiler and not auto.LEAK.search(text):
                prior.append({'role': 'user', 'text': text, 'stamp': epoch})
    parsed.sha256 = digest.hexdigest()
    return parsed


# ------------------------------------------------------------------ turn lookup

class TranscriptScanner:
    """Finds a session's transcript by hash and parses each file once (a small LRU keeps recent sessions)."""

    def __init__(self, roots, cache_size=8):
        self.roots = [Path(root) for root in roots]
        self.cache_size = max(1, cache_size)
        self._paths = None
        self._cache: OrderedDict = OrderedDict()

    def paths(self) -> dict:
        if self._paths is None:
            self._paths = session_paths(self.roots)
        return self._paths

    def parsed(self, path):
        """Parsed transcript, or the failure reason string."""
        key = str(path)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        try:
            value = parse_transcript(path)
        except TranscriptError as exc:
            value = exc.reason
        self._cache[key] = value
        while len(self._cache) > self.cache_size:
            self._cache.popitem(last=False)
        return value

    def _matches(self, session_hash, wanted):
        """(matches, issues) for the user turns whose full hash satisfies `wanted(hash)`."""
        matches, issues = [], []
        for path in self.paths().get(session_hash, []):
            parsed = self.parsed(path)
            if isinstance(parsed, str):
                issues.append(parsed)
                continue
            for turn in parsed.turns:
                if wanted(turn['hash']):
                    matches.append({'text': turn['text'], 'prior': turn['prior'], 'timestamp': turn['timestamp'],
                                    'path': str(path), 'line': turn['line'],
                                    'transcriptRef': {'path': str(path), 'line': turn['line']}})
        return matches, issues

    def _resolve(self, session_hash, wanted, observed_at):
        if session_hash not in self.paths():
            return None, 'transcript_unavailable'
        matches, issues = self._matches(session_hash, wanted)
        if not matches:
            return None, 'transcript_unavailable' if issues else 'context_missing'
        return auto.choose_match(matches, observed_at)

    def find_turn(self, session_id, prompt_prefix16, observed_at):
        if not isinstance(session_id, str) or not session_id:
            return None, 'transcript_unavailable'
        prefix = str(prompt_prefix16 or '').lower()
        if not HEX.match(prefix):
            return None, 'context_missing'
        return self._resolve(sha256_text(session_id), lambda value: value.startswith(prefix), observed_at)

    def find_turn_by_hash(self, session_hash, prompt_hash, observed_at):
        """Same lookup for callers that hold only the stored hashes (records keep sessionHash and promptHash)."""
        return self._resolve(session_hash, lambda value: value == prompt_hash, observed_at)


def find_turn(session_id, prompt_prefix16, observed_at, roots, scanner=None):
    """Locate the user turn of `session_id` whose sha256 starts with `prompt_prefix16`.

    `observed_at` (the router hook's own clock) picks between repeated identical prompts. Pass a shared
    `scanner` when looking up many turns so each transcript is parsed once.
    """
    return (scanner or TranscriptScanner(roots)).find_turn(session_id, prompt_prefix16, observed_at)


# ------------------------------------------------------------------ skill invocations

def invocations_in(parsed, after_epoch=None, after_line=None, until_epoch=None, max_user_turns=None) -> list:
    """Skill invocations of a Parsed transcript after an anchor, with the user turns between anchor and use.

    The anchor is a transcript line (exact, when the prompt turn was located) or an epoch second. A
    slash-command turn counts as the user turn it is, so a command typed right after the prompt has
    userTurnsAfter 1 while a Skill tool_use in the response to the prompt itself has 0.
    """
    if parsed.codex:
        raise TranscriptError('transcript_unavailable')
    human = [turn for turn in parsed.turns if turn['human']]
    lines = [turn['line'] for turn in human]
    if after_line is not None:
        before = bisect.bisect_right(lines, after_line)
    elif after_epoch is not None:
        before = sum(1 for turn in human if turn['epoch'] is not None and turn['epoch'] <= after_epoch)
    else:
        before = 0
    found = []
    for item in parsed.invocations:
        if after_line is not None:
            if item['line'] <= after_line:
                continue
        elif after_epoch is not None and (item['epoch'] is None or item['epoch'] <= after_epoch):
            continue
        if until_epoch is not None and (item['epoch'] is None or item['epoch'] > until_epoch):
            continue
        ref = item['ref']
        if item['via'] == 'slash_command' and ':' not in ref and ref.lower() in BUILTIN_COMMANDS:
            continue
        turns = bisect.bisect_right(lines, item['line']) - before
        if max_user_turns is not None and turns > max_user_turns:
            continue
        found.append({'skillRef': ref, 'via': item['via'], 'ts': item['timestamp'], 'userTurnsAfter': max(turns, 0)})
    return found


def skill_invocations(path, after_ts=None, after_line=None, until_ts=None, max_user_turns=None) -> list:
    """Skill invocations in a Claude transcript after `after_ts` (ISO string or epoch seconds).

    Raises TranscriptError('transcript_unavailable') for an unreadable, oversized or Codex transcript.
    """
    def epoch(value):
        if value is None or isinstance(value, (int, float)):
            return value
        return _iso_to_epoch(value)

    parsed = parse_transcript(path)
    return invocations_in(parsed, epoch(after_ts), after_line, epoch(until_ts), max_user_turns)


def utc_iso(epoch_seconds: float) -> str:
    return datetime.fromtimestamp(epoch_seconds, timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
