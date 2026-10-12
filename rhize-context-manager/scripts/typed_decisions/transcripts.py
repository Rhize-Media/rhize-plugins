"""Prefix-capable transcript scanner for the typed-decision evidence pipeline (plan §4.5).

Reuses pilot_autolabel's `transcript_message` (Claude and Codex line layouts) and `choose_match`
(repeated identical prompts are resolved by timestamp) without editing them. Everything read from a
transcript stays in memory: callers get text and context back, and nothing here writes any of it.

    find_turn(session_id, prompt_prefix16, observed_at, roots) -> (match | None, reason)
        match = {'text', 'prior', 'timestamp', 'path', 'line', 'transcriptRef'}; reason is None on success or one
        of 'transcript_unavailable' | 'context_missing' | 'context_ambiguous'.
    session_index(roots) -> {sha256(session_id): transcript Path}
    skill_invocations(path, after_ts) -> [{'skillRef', 'via', 'ts', 'userTurnsAfter'}]
        via is 'skill_tool' (an assistant `Skill` tool_use, input.skill), 'slash_command' (a user turn carrying
        a <command-name>/plugin:skill</command-name> marker) or 'skill_file_read' (a Codex command that only reads a
        skill's SKILL.md; see "Codex skill reads" below).
    codex_thread_source(path) -> str | None
        session_meta.payload.thread_source of a Codex rollout (first line only, bounded).

Reads are bounded: a transcript larger than MAX_TRANSCRIPT_BYTES is 'transcript_unavailable', lines are
streamed, and a single line larger than MAX_LINE_BYTES is skipped. Symlinks are never followed.

Codex skill reads (plan §7 F3). Codex loads a skill by reading `.../skills/<skill>/SKILL.md`. Current rollouts record
each command as an `event_msg` / `item_completed` CommandExecution with Codex's own `parsed_cmd`: a `read` entry
counts when its path is a SKILL.md under a plugin root (below) or a user skill folder (`~/.agents/skills`,
`~/.codex/skills`, `~/.claude/skills[/synced/<id>]`, which yield a bare `<skill>` ref) and the command exited with
the integer 0. In such a rollout the coexisting `function_call` lines are ignored, since they carry no exit code.
Older rollouts carry only the shell `function_call`, which counts when, and only when, all of these hold:
  * the response_item payload type is exactly `function_call` and the tool is a shell or exec tool;
  * the command is read-shaped: cat, sed (only with -n), head, tail, nl, bat or less, optionally behind a leading
    `cd X &&`, optionally piped into head/tail, with no redirection, substitution or globbing;
  * it names a SKILL.md under a plugin root: `<home>/.codex/plugins/cache/<mkt>/<plugin>/<ver>/skills/<skill>/`,
    `<home>/.claude/plugins/cache/<mkt>/<plugin>/<ver>/skills/<skill>/` or
    `<home>/.claude/plugins/marketplaces/<mkt>/<plugin>/skills/<skill>/` (a dev checkout never matches).
`custom_tool_call` (apply_patch), edits, grep, git, `sed -i` and `$skill` mentions never count. Several reads of
one skill in one command count once. The ref is `<plugin>:<skill>`. This is a separate, weaker evidence type from a
`Skill` tool call (reading a file is not the same as the host loading the skill), hence its own `via`.
"""
from __future__ import annotations

import bisect
import hashlib
import json
import os
import posixpath
import re
import shlex
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


# ------------------------------------------------------------------ Codex rollouts

MAX_META_LINE_BYTES = 512 * 1024      # the session_meta line carries the base instructions, so it is large
MAX_ARGUMENTS_CHARS = 256 * 1024      # a read command is short; anything bigger is not one
THREAD_SOURCE = re.compile(r'[A-Za-z0-9_.-]{1,64}\Z')


def codex_thread_source(path, max_bytes=MAX_META_LINE_BYTES):
    """session_meta.payload.thread_source of a Codex rollout ('user', 'subagent', 'guardian_review', ...) or None.

    Only the first line is read, at most `max_bytes` of it, through a no-follow descriptor. None means unknown:
    an unreadable, non-regular or non-Codex file, an over-long or malformed first line, or a rollout that predates
    the field. Callers that must keep machine-driven threads out of the evidence treat None as "not a user thread".
    """
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
    except OSError:
        return None
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return None
        with os.fdopen(fd, 'rb', closefd=False) as handle:
            raw = handle.readline(max_bytes + 1)
    except OSError:
        return None
    finally:
        os.close(fd)
    if not raw or (len(raw) > max_bytes and not raw.endswith(b'\n')):
        return None
    try:
        return _thread_source_of(json.loads(raw.decode('utf-8', 'replace')))
    except ValueError:
        return None


def _thread_source_of(record):
    if not isinstance(record, dict) or record.get('type') != 'session_meta':
        return None
    payload = record.get('payload')
    value = payload.get('thread_source') if isinstance(payload, dict) else None
    return value if isinstance(value, str) and THREAD_SOURCE.match(value) else None


# ------------------------------------------------------------------ Codex skill reads

CODEX_SHELL_TOOLS = frozenset(('exec_command', 'shell', 'shell_command', 'container.exec', 'local_shell', 'bash'))
READ_COMMANDS = frozenset(('cat', 'sed', 'head', 'tail', 'nl', 'bat', 'less'))
PIPE_COMMANDS = frozenset(('head', 'tail'))
SHELLS = frozenset(('bash', 'sh', 'zsh', 'dash'))
SYSTEM_BINS = frozenset(('/bin', '/usr/bin', '/usr/local/bin', '/opt/homebrew/bin'))
SHELL_FLAG = re.compile(r'-[a-z]{0,3}c\Z')
SED_SHORT_FLAGS = frozenset(('-n', '-E', '-r', '-s', '-nE', '-En', '-nr', '-rn', '-ns', '-sn'))
SED_LONG_FLAGS = frozenset(('--quiet', '--silent', '--regexp-extended', '--separate'))
# The only sed programs treated as reads: print/quit/line-number commands behind line, `$` or /regex/ addresses.
# Anything else (s///w, w, e, y, a/i/c, branching, ...) is not read-shaped, whatever the -n flag says.
_SED_ADDRESS = r'(?:\d+|\$|/(?:[^/\\]|\\.)*/I?)'
_SED_COMMAND = r'[pPq=]'
_SED_STEP = (rf'\s*(?:{_SED_ADDRESS}(?:\s*,\s*{_SED_ADDRESS})?)?\s*!?\s*'
             rf'(?:{_SED_COMMAND}|\{{\s*{_SED_COMMAND}(?:\s*;\s*{_SED_COMMAND})*\s*;?\s*\}})')
SED_READ_PROGRAM = re.compile(rf'{_SED_STEP}(?:\s*;{_SED_STEP})*\s*;?\s*\Z')
MAX_SED_PROGRAM_CHARS = 512
PUNCTUATION = frozenset('();<>|&')
HOME_PREFIXES = ('~/', '$HOME/', '${HOME}/')
HOME_MARK = '/~home'
STDERR_NOISE = re.compile(r'(?<=\s)2>\s*(?:/dev/null|&1)(?=\s|$|[;&|])')
UNSAFE_PATH_CHARS = frozenset('$*?[]{}`\\')
_NAME = r'[A-Za-z0-9_.-]+'
_HOME = r'/(?:[^/]+/)*?'
SKILL_FILE_PATTERNS = tuple(re.compile(pattern) for pattern in (
    rf'{_HOME}\.codex/plugins/cache/(?P<mkt>{_NAME})/(?P<plugin>{_NAME})/(?P<ver>{_NAME})/skills/(?P<skill>{_NAME})/SKILL\.md\Z',
    rf'{_HOME}\.claude/plugins/cache/(?P<mkt>{_NAME})/(?P<plugin>{_NAME})/(?P<ver>{_NAME})/skills/(?P<skill>{_NAME})/SKILL\.md\Z',
    rf'{_HOME}\.claude/plugins/marketplaces/(?P<mkt>{_NAME})/(?P<plugin>{_NAME})/skills/(?P<skill>{_NAME})/SKILL\.md\Z'))


def _executable(token):
    """The command name of a token (bare, or an absolute path under a system bin directory), else ''."""
    if '/' not in token:
        return token
    return posixpath.basename(token) if posixpath.dirname(token) in SYSTEM_BINS else ''


def _tokens(script):
    """Shell-like tokens; unquoted operators come back as their own tokens. Raises ValueError on bad quoting."""
    lexer = shlex.shlex(script, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = ''
    return list(lexer)


def _resolve(token, base):
    """Absolute, normalized path for a command word, or None when it is not a plain literal path."""
    for prefix in HOME_PREFIXES:
        if token.startswith(prefix):
            token = HOME_MARK + token[len(prefix) - 1:]
            break
    if not token or '\0' in token or any(char in UNSAFE_PATH_CHARS for char in token):
        return None
    if not token.startswith('/'):
        if not base:
            return None
        token = base.rstrip('/') + '/' + token
    return posixpath.normpath(token)


def _sed_program_ok(text):
    """A read-only sed program that actually prints lines (p/P); `q` or `=` alone print no instructions."""
    return (len(text) <= MAX_SED_PROGRAM_CHARS and SED_READ_PROGRAM.match(text) is not None
            and re.search(r'[pP]', text) is not None)


def _sed_files(args):
    """File words of a `sed -n` invocation, or None when it is not the read-only form."""
    quiet, scripted, positional, index = False, False, [], 0
    while index < len(args):
        arg = args[index]
        if arg == '--':
            positional.extend(args[index + 1:])
            break
        if arg == '-e':
            if index + 1 >= len(args) or not _sed_program_ok(args[index + 1]):
                return None
            scripted, index = True, index + 1
        elif arg in SED_SHORT_FLAGS:
            quiet = quiet or 'n' in arg[1:]
        elif arg in SED_LONG_FLAGS:
            quiet = quiet or arg in ('--quiet', '--silent')
        elif arg.startswith('-') and len(arg) > 1:
            return None                                    # -i, --in-place, -f, -z, unknown: not the read form
        else:
            positional.append(arg)
        index += 1
    if not quiet:
        return None
    if not scripted:
        if not positional or not _sed_program_ok(positional[0]):
            return None
        positional = positional[1:]
    return positional


COUNT = re.compile(r'\+?\d{1,9}\Z')
READ_FLAGS = {                  # the only options under which these commands still just print the file
    'cat': frozenset(('-n', '-b', '-s')),
    'nl': frozenset(('-ba', '-b', '-a', '-n', '-nln', '-nrn', '-nrz')),
    'bat': frozenset(('-p', '-pp', '--plain', '--paging=never', '--style=plain', '--color=never')),
    'less': frozenset(),
}


def _count_flag(arg, rest):
    """How many words a head/tail count option consumes (1 or 2), or 0 when `arg` is not one."""
    if arg in ('-n', '-c'):
        return 2 if rest and COUNT.match(rest[0]) else 0
    if re.match(r'-[nc]\+?\d{1,9}\Z', arg) or re.match(r'-\d{1,9}\Z', arg) \
            or re.match(r'--(?:lines|bytes)=\+?\d{1,9}\Z', arg):
        return 1
    return 0


def _plain_words(name, args):
    """File words of cat/head/tail/nl/bat/less, or None when any option is outside the print-the-file set
    (e.g. --help or --version, which print no skill instructions)."""
    words, index, options = [], 0, True
    while index < len(args):
        arg = args[index]
        if options and arg == '--':
            options = False
        elif options and arg.startswith('-') and arg != '-':
            if name in ('head', 'tail'):
                used = _count_flag(arg, args[index + 1:])
                if not used:
                    return None
                index += used
                continue
            if arg not in READ_FLAGS.get(name, frozenset()):
                return None
        else:
            words.append(arg)
        index += 1
    return words


def _read_words(argv):
    """The argument words of a read-shaped command (candidate file paths), or None when it is not one."""
    name = _executable(argv[0])
    if name not in READ_COMMANDS:
        return None
    if name == 'sed':
        return _sed_files(argv[1:])
    return _plain_words(name, argv[1:])


def _pipelines(tokens):
    """[(joiner, [argv, ...])] for `a | b && c ; d`, or None for anything with other shell syntax."""
    result, pipe, argv, joiner = [], [], [], None
    for token in tokens:
        if token == '|' or token in ('&&', ';'):
            if not argv:
                return None
            pipe.append(argv)
            argv = []
            if token != '|':
                result.append((joiner, pipe))
                pipe, joiner = [], token
        elif set(token) <= PUNCTUATION or '`' in token:
            return None
        else:
            argv.append(token)
    if not argv:
        return None
    pipe.append(argv)
    result.append((joiner, pipe))
    return result


def _shell_wrapped(script):
    """Inner script of `bash -lc '<script>'` (the only shell-wrapper form Codex emits), else None."""
    try:
        tokens = _tokens(script)
    except ValueError:
        return None
    if len(tokens) == 3 and _executable(tokens[0]) in SHELLS and SHELL_FLAG.match(tokens[1]):
        return tokens[2]
    return None


def _quoted_words(script):
    """[(value, contexts)] per shell word, where contexts[i] is the quoting of value[i]: None (unquoted), "'",
    '"' or '\\\\' (backslash-escaped). Unquoted whitespace and operators end a word, as in `_tokens`."""
    words, chars, ctxs, quote, in_word, index = [], [], [], None, False, 0

    def end():
        nonlocal chars, ctxs, in_word
        if in_word:
            words.append((''.join(chars), ctxs))
        chars, ctxs, in_word = [], [], False

    while index < len(script):
        char = script[index]
        if quote == "'":
            if char == "'":
                quote = None
            else:
                chars.append(char)
                ctxs.append("'")
        elif quote == '"':
            if char == '"':
                quote = None
            elif char == '\\' and index + 1 < len(script) and script[index + 1] in '"\\$`':
                index += 1
                chars.append(script[index])
                ctxs.append('\\')
            else:
                chars.append(char)
                ctxs.append('"')
        elif char in ("'", '"'):
            quote, in_word = char, True
        elif char == '\\' and index + 1 < len(script):
            index += 1
            chars.append(script[index])
            ctxs.append('\\')
            in_word = True
        elif char.isspace() or char in PUNCTUATION:
            end()
        else:
            chars.append(char)
            ctxs.append(None)
            in_word = True
        index += 1
    end()
    return words


def _unexpanded_words(script):
    """Whole words whose leading ~ / $HOME / ${HOME} the shell would NOT expand to the home directory. `~` expands
    only when unquoted; `$HOME`/`${HOME}` only when every character of it is unquoted or every one is inside double
    quotes. Judged per complete word, so concatenated fragments (`'$HOME'/x`, `"~"/x`, `\\~/x`) are literals too."""
    literal = set()
    for value, ctxs in _quoted_words(script):
        if value.startswith('~'):
            if ctxs[0] is not None:
                literal.add(value)
            continue
        for prefix in ('${HOME}', '$HOME'):
            if value.startswith(prefix):
                head = set(ctxs[:len(prefix)])
                if head not in ({None}, {'"'}):
                    literal.add(value)
                break
    return literal


def codex_skill_reads(command, workdir=None, _depth=0) -> list:
    """Distinct `<plugin>:<skill>` refs read by a read-shaped Codex shell command ([] for any other command).

    `command` is the exec tool's `cmd`/`command` value: a string, or an argv list (possibly the
    `["bash", "-lc", "<script>"]` wrapper). `workdir` is the call's working directory, used only to resolve
    relative paths. The whole command must be read-shaped: one stray non-read command rejects all of it.
    """
    if isinstance(command, list):
        if not command or len(command) > 64 or not all(isinstance(item, str) for item in command):
            return []
        if len(command) == 3 and _executable(command[0]) in SHELLS and SHELL_FLAG.match(command[1]):
            script = command[2]
        else:
            script = shlex.join(command)
    elif isinstance(command, str):
        script = command
    else:
        return []
    script = script.strip()
    if not script or len(script) > 16 * 1024 or '\n' in script or '\r' in script:
        return []
    script = STDERR_NOISE.sub('', script)
    inner = _shell_wrapped(script) if _depth < 2 else None
    if inner is not None:
        return codex_skill_reads(inner, workdir, _depth + 1)
    try:
        pipelines = _pipelines(_tokens(script))
    except ValueError:
        return []
    if pipelines is None:
        return []
    literal = _unexpanded_words(script)
    base = _resolve(workdir, None) if isinstance(workdir, str) and workdir else None
    refs = []
    for index, (_, pipe) in enumerate(pipelines):
        head = pipe[0]
        if _executable(head[0]) == 'cd':
            # Only a leading `cd X &&` is allowed; its target becomes the base for relative paths.
            if index != 0 or len(pipe) != 1 or len(head) != 2 or len(pipelines) < 2 or pipelines[1][0] != '&&':
                return []
            if head[1] in literal:
                return []                   # cd into a quoted ~ / '$HOME' path fails, so the && read never runs
            base = _resolve(head[1], base)
            continue
        words = _read_words(head)
        if words is None or any(_executable(stage[0]) not in PIPE_COMMANDS for stage in pipe[1:]):
            return []
        for word in words:
            if word in literal:
                continue                    # a quoted ~ or single-quoted $HOME is a literal, not the home directory
            path = _resolve(word, base)
            for pattern in SKILL_FILE_PATTERNS:
                match = pattern.match(path) if path else None
                if match:
                    ref = f'{match.group("plugin")}:{match.group("skill")}'
                    if ref not in refs:
                        refs.append(ref)
                    break
    return refs


def _codex_shell_command(payload):
    """(command, workdir) of a Codex shell/exec `function_call` payload, else None."""
    if not isinstance(payload, dict) or payload.get('type') != 'function_call':
        return None
    name = payload.get('name')
    if not isinstance(name, str) or name.removeprefix('functions.') not in CODEX_SHELL_TOOLS:
        return None
    raw = payload.get('arguments')
    if isinstance(raw, str):
        if len(raw) > MAX_ARGUMENTS_CHARS:
            return None
        try:
            raw = json.loads(raw)
        except ValueError:
            return None
    if not isinstance(raw, dict):
        return None
    command = raw['cmd'] if 'cmd' in raw else raw.get('command')
    workdir = raw.get('workdir')
    return command, (workdir if isinstance(workdir, str) else None)


# Skill folders whose SKILL.md is a user- or host-level skill rather than a plugin's: the ref is the bare skill name
# (outcomes.py resolves a bare name through the record's shortlist when it is unique there). Codex's own generated
# memory skills (~/.codex/memories/skills) are not router targets and never count.
BARE_SKILL_PATTERNS = tuple(re.compile(pattern) for pattern in (
    rf'{_HOME}\.agents/skills/(?P<skill>{_NAME})/SKILL\.md\Z',
    rf'{_HOME}\.codex/skills/(?P<skill>{_NAME})/SKILL\.md\Z',
    rf'{_HOME}\.claude/skills/(?:synced/{_NAME}/)?(?P<skill>{_NAME})/SKILL\.md\Z'))


def skill_ref_for_path(path):
    """'plugin:skill' (plugin roots) or 'skill' (user/host skill folders) for an absolute SKILL.md path, else None."""
    if not path:
        return None
    for pattern in SKILL_FILE_PATTERNS:
        match = pattern.match(path)
        if match:
            return f'{match.group("plugin")}:{match.group("skill")}'
    for pattern in BARE_SKILL_PATTERNS:
        match = pattern.match(path)
        if match:
            return match.group('skill')
    return None


def _item_cwd(item):
    cwd = item.get('cwd')
    if isinstance(cwd, str) and cwd.startswith('file://'):
        cwd = cwd[len('file://'):]
    return cwd if isinstance(cwd, str) and cwd.startswith('/') else None


def _is_command_execution(record) -> bool:
    """True for a current-layout Codex `event_msg` / `item_completed` line whose item is a CommandExecution."""
    payload = record.get('payload') if record.get('type') == 'event_msg' else None
    item = payload.get('item') if isinstance(payload, dict) and payload.get('type') == 'item_completed' else None
    return isinstance(item, dict) and item.get('type') == 'CommandExecution'


def codex_executed_skill_reads(record) -> list:
    """Skill refs from a Codex `item_completed` CommandExecution: Codex's own parsed_cmd entries of type 'read' whose
    path is a SKILL.md under a skill root. The command must have exited 0: a non-zero exit (a missing file, a
    permission error, one failing file of `cat A B`) proves no specific read succeeded, so it never counts, whatever
    output it produced (Codex final review). The exit code is the whole command's, so `cat A; true` still counts A.
    search and list_files entries never count."""
    if record.get('type') != 'event_msg':
        return []
    payload = record.get('payload')
    item = payload.get('item') if isinstance(payload, dict) and payload.get('type') == 'item_completed' else None
    if not isinstance(item, dict) or item.get('type') != 'CommandExecution':
        return []
    exit_code = item.get('exit_code')
    if type(exit_code) is not int or exit_code != 0:      # an int 0 only: no bool, no 0.0, no '0'
        return []
    parsed = item.get('parsed_cmd')
    if not isinstance(parsed, list):
        return []
    base, refs = _item_cwd(item), []
    for entry in parsed[:64]:
        if not isinstance(entry, dict) or entry.get('type') != 'read':
            continue
        ref = skill_ref_for_path(_resolve(entry.get('path') or '', base)) if isinstance(entry.get('path'), str) else None
        if ref and ref not in refs:
            refs.append(ref)
    return refs


def codex_skill_file_reads(record) -> list:
    """Skill refs read by one Codex rollout line: a legacy shell `function_call`, or a current-layout
    `item_completed` CommandExecution (see codex_executed_skill_reads)."""
    if record.get('type') == 'event_msg':
        return codex_executed_skill_reads(record)
    if record.get('type') != 'response_item':
        return []
    call = _codex_shell_command(record.get('payload'))
    return codex_skill_reads(call[0], call[1]) if call else []


# ------------------------------------------------------------------ parsing

class Parsed:
    """The lightweight, in-memory view of one transcript file."""

    def __init__(self, path, size):
        self.path, self.size = Path(path), size
        self.sha256 = None
        self.codex = is_codex_path(path)
        self.thread_source = None      # Codex only: session_meta.payload.thread_source of the first line
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
    # A rollout that records CommandExecution completions also persists each command's `function_call`; only the
    # completion knows the exit code, so legacy function_call reads count only in rollouts without completions.
    executed_layout, legacy_reads = False, []
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
                if number == 1:
                    parsed.thread_source = _thread_source_of(record)
            stamp = record.get('timestamp')
            epoch = _iso_to_epoch(stamp)
            if parsed.codex:
                # A Codex rollout has no `Skill` tool and no slash-command marker: its only skill evidence is a
                # read-shaped shell call on a SKILL.md. `$skill` mentions in user turns are deliberately ignored.
                executed_layout = executed_layout or _is_command_execution(record)
                for ref in codex_skill_file_reads(record):
                    entry = {'line': number, 'timestamp': stamp, 'epoch': epoch, 'ref': ref, 'via': 'skill_file_read'}
                    parsed.invocations.append(entry)
                    if record.get('type') == 'response_item':
                        legacy_reads.append(entry)
            else:
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
            command = None if boiler or parsed.codex else COMMAND_NAME.search(text)
            if command:
                parsed.invocations.append({'line': number, 'timestamp': stamp, 'epoch': epoch,
                                           'ref': command.group(1), 'via': 'slash_command'})
            if not boiler and not auto.LEAK.search(text):
                prior.append({'role': 'user', 'text': text, 'stamp': epoch})
    if executed_layout and legacy_reads:
        legacy = {id(entry) for entry in legacy_reads}
        parsed.invocations = [entry for entry in parsed.invocations if id(entry) not in legacy]
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
    """Skill invocations in a Claude or Codex transcript after `after_ts` (ISO string or epoch seconds).

    Raises TranscriptError('transcript_unavailable') for an unreadable or oversized transcript. Which Codex
    threads may be joined (user threads only) is the caller's decision: see `codex_thread_source`.
    """
    def epoch(value):
        if value is None or isinstance(value, (int, float)):
            return value
        return _iso_to_epoch(value)

    parsed = parse_transcript(path)
    return invocations_in(parsed, epoch(after_ts), after_line, epoch(until_ts), max_user_turns)


def utc_iso(epoch_seconds: float) -> str:
    return datetime.fromtimestamp(epoch_seconds, timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
