"""Codex skill-invocation parser and the Codex side of the outcome join (plan §7 F3, §8; acceptance test A5).

Invented rollouts in the layout Codex writes (session_meta first, then response_item lines), temp directories only.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import sys
import uuid
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / 'rhize-context-manager' / 'scripts'
FIX = REPO / 'tests' / 'rhize-context-manager' / 'fixtures' / 'typed-decisions'
sys.path.insert(0, str(SCRIPTS))

from typed_decisions import contract, outcomes, records, transcripts  # noqa: E402

try:
    import jsonschema
except ImportError:                                         # pragma: no cover - the stdlib validators are canonical
    jsonschema = None

HOME = '/Users/jim'
CODEX_SKILL = f'{HOME}/.codex/plugins/cache/rhize-plugins/rhize-ops/0.9.0/skills/cross-model-handoff/SKILL.md'
CACHE_SKILL = f'{HOME}/.claude/plugins/cache/rhize-plugins/seo-aeo-geo/1.4.0/skills/seo-site-audit/SKILL.md'
MARKET_SKILL = f'{HOME}/.claude/plugins/marketplaces/rhize-plugins/rhize-devflow/skills/ship/SKILL.md'
DEV_SKILL = f'{HOME}/dev-local/RHIZE/rhize-plugins/rhize-ops/skills/cross-model-handoff/SKILL.md'
SEO = 'skill:seo-aeo-geo/seo-site-audit'
GEO = 'skill:seo-aeo-geo/aeo-geo-optimization'
SHIP = 'skill:rhize-devflow/ship'
HANDOFF = 'skill:rhize-ops/cross-model-handoff'
T0 = '2026-10-11T21:00:00.000Z'
NOW = outcomes.datetime.fromisoformat('2026-10-12T00:00:00+00:00')


def sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def at(seconds, base='2026-10-11T21:00:'):
    return f'{base}{seconds:02d}.000Z'


# ---------------------------------------------------------------- rollout line builders

def meta(session, thread_source='user', when=T0):
    payload = {'id': session, 'timestamp': when, 'cwd': f'{HOME}/dev-local/client', 'originator': 'codex_cli_rs',
               'cli_version': '0.130.0', 'source': 'cli', 'model_provider': 'openai',
               'base_instructions': {'text': 'You are a coding agent. ' * 200}}
    if thread_source is not None:
        payload['thread_source'] = thread_source
    return {'timestamp': when, 'type': 'session_meta', 'payload': payload}


def user_turn(text, when):
    return {'timestamp': when, 'type': 'response_item',
            'payload': {'type': 'message', 'role': 'user', 'content': [{'type': 'input_text', 'text': text}]}}


def developer_note(text, when):
    return {'timestamp': when, 'type': 'response_item',
            'payload': {'type': 'message', 'role': 'developer', 'content': [{'type': 'input_text', 'text': text}]}}


def assistant_text(text, when):
    return {'timestamp': when, 'type': 'response_item',
            'payload': {'type': 'message', 'role': 'assistant', 'content': [{'type': 'output_text', 'text': text}]}}


def exec_call(cmd, when, workdir=f'{HOME}/dev-local/client', name='exec_command'):
    arguments = {'cmd': cmd, 'workdir': workdir, 'yield_time_ms': 1000, 'max_output_tokens': 4000}
    return {'timestamp': when, 'type': 'response_item',
            'payload': {'type': 'function_call', 'name': name, 'arguments': json.dumps(arguments),
                        'call_id': 'call_' + uuid.uuid4().hex[:12]}}


def shell_call(argv, when, workdir=f'{HOME}/dev-local/client'):
    return {'timestamp': when, 'type': 'response_item',
            'payload': {'type': 'function_call', 'name': 'shell',
                        'arguments': json.dumps({'command': argv, 'workdir': workdir, 'timeout_ms': 10000}),
                        'call_id': 'call_' + uuid.uuid4().hex[:12]}}


def patch_call(target, when):
    patch = f'*** Begin Patch\n*** Update File: {target}\n@@\n-old\n+new\n*** End Patch\n'
    return {'timestamp': when, 'type': 'response_item',
            'payload': {'type': 'custom_tool_call', 'status': 'completed', 'name': 'apply_patch', 'input': patch,
                        'call_id': 'call_' + uuid.uuid4().hex[:12]}}


def call_output(text, when):
    return {'timestamp': when, 'type': 'response_item',
            'payload': {'type': 'function_call_output', 'call_id': 'call_x', 'output': text}}


def noise(when):
    """Lines Codex writes around the conversation that carry no skill evidence."""
    return [{'timestamp': when, 'type': 'turn_context', 'payload': {'cwd': HOME, 'model': 'gpt-5-codex'}},
            {'timestamp': when, 'type': 'event_msg', 'payload': {'type': 'token_count', 'info': None}},
            {'timestamp': when, 'type': 'response_item',
             'payload': {'type': 'reasoning', 'summary': [], 'encrypted_content': 'gAAAA'}}]


def write_rollout(tmp_path, session, rows, name=None):
    path = tmp_path / 'sessions' / '2026' / '10' / '11' / (name or f'rollout-2026-10-11T21-00-00-{session}.jsonl')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(json.dumps(row) for row in rows) + '\n')
    return path


def new_session():
    return str(uuid.uuid4())


def refs_of(path, **kwargs):
    return [(item['skillRef'], item['via'], item['userTurnsAfter']) for item in transcripts.skill_invocations(path, **kwargs)]


# ---------------------------------------------------------------- the command parser

READ_CASES = [
    ('cat string', f'cat {CODEX_SKILL}', ['rhize-ops:cross-model-handoff']),
    ('sed -n', f"sed -n '1,220p' {CODEX_SKILL}", ['rhize-ops:cross-model-handoff']),
    ('sed -n regex range', f"sed -n '/^---$/,/^---$/p' {CODEX_SKILL}", ['rhize-ops:cross-model-handoff']),
    ('sed -n -e', f"sed -n -e '1,5p' {CODEX_SKILL}", ['rhize-ops:cross-model-handoff']),
    ('head', f'head -n 80 {CACHE_SKILL}', ['seo-aeo-geo:seo-site-audit']),
    ('tail', f'tail -n +1 {MARKET_SKILL}', ['rhize-devflow:ship']),
    ('nl piped to tail', f'nl -ba {CODEX_SKILL} | tail -n 40', ['rhize-ops:cross-model-handoff']),
    ('bat', f'bat --plain {CODEX_SKILL}', ['rhize-ops:cross-model-handoff']),
    ('less', f'less {CODEX_SKILL}', ['rhize-ops:cross-model-handoff']),
    ('cat piped to head', f'cat {CODEX_SKILL} | head -n 60', ['rhize-ops:cross-model-handoff']),
    ('leading cd', f'cd {HOME}/dev-local/client && cat {CODEX_SKILL}', ['rhize-ops:cross-model-handoff']),
    ('cd into the plugin dir, relative path',
     f'cd {HOME}/.codex/plugins/cache/rhize-plugins/rhize-ops/0.9.0 && cat skills/cross-model-handoff/SKILL.md',
     ['rhize-ops:cross-model-handoff']),
    ('tilde', '/bin/cat ~/.codex/plugins/cache/rhize-plugins/rhize-ops/0.9.0/skills/cross-model-handoff/SKILL.md',
     ['rhize-ops:cross-model-handoff']),
    ('$HOME', 'cat $HOME/.claude/plugins/marketplaces/rhize-plugins/rhize-devflow/skills/ship/SKILL.md',
     ['rhize-devflow:ship']),
    ('stderr noise', f'cat {CODEX_SKILL} 2>/dev/null', ['rhize-ops:cross-model-handoff']),
    ('two files, two skills', f'cat {CODEX_SKILL} {CACHE_SKILL}',
     ['rhize-ops:cross-model-handoff', 'seo-aeo-geo:seo-site-audit']),
    ('same skill twice in one command counts once', f'cat {CODEX_SKILL} {CODEX_SKILL}', ['rhize-ops:cross-model-handoff']),
    ('same skill, two plugin roots, counts once',
     f'cat {CODEX_SKILL} {HOME}/.claude/plugins/cache/rhize-plugins/rhize-ops/0.8.0/skills/cross-model-handoff/SKILL.md',
     ['rhize-ops:cross-model-handoff']),
    ('read segments joined by &&', f"sed -n '1,40p' {CODEX_SKILL} && head -n 40 {MARKET_SKILL}",
     ['rhize-ops:cross-model-handoff', 'rhize-devflow:ship']),
    ('argv list', ['cat', CODEX_SKILL], ['rhize-ops:cross-model-handoff']),
    ('argv sed -n', ['sed', '-n', '1,200p', CODEX_SKILL], ['rhize-ops:cross-model-handoff']),
    ('bash -lc wrapper', ['bash', '-lc', f"sed -n '1,200p' {CODEX_SKILL}"], ['rhize-ops:cross-model-handoff']),
    ('bash -lc wrapper with cd', ['bash', '-lc', f'cd {HOME} && cat {CACHE_SKILL}'], ['seo-aeo-geo:seo-site-audit']),
    ('bash -lc inside a string', f'bash -lc "cat {CODEX_SKILL}"', ['rhize-ops:cross-model-handoff']),
]

NOT_READS = [
    ('sed -i', f"sed -i 's/old/new/' {CODEX_SKILL}"),
    ('sed -i with a backup suffix', f"sed -i.bak 's/old/new/' {CODEX_SKILL}"),
    ('sed without -n', f"sed 's/old/new/' {CODEX_SKILL}"),
    ('sed -n that writes', f"sed -n 's/a/b/w /tmp/out' {CODEX_SKILL}"),
    ('sed -n that executes', f"sed -n '1e echo hi' {CODEX_SKILL}"),
    ('argv sed -i', ['sed', '-i', 's/a/b/', CODEX_SKILL]),
    ('grep', f'grep -n description {CODEX_SKILL}'),
    ('rg', f'rg -n description {CODEX_SKILL}'),
    ('git', f'git show HEAD:{CODEX_SKILL}'),
    ('git diff', f'git diff -- {CODEX_SKILL}'),
    ('cp', f'cp {CODEX_SKILL} /tmp/copy.md'),
    ('echo of the path', f'echo {CODEX_SKILL}'),
    ('ls of the skill directory', f'ls {os.path.dirname(CODEX_SKILL)}'),
    ('python reading it', f"python3 -c \"print(open('{CODEX_SKILL}').read())\""),
    ('redirect', f'cat {CODEX_SKILL} > /tmp/skill.md'),
    ('append redirect', f'cat {CODEX_SKILL} >> /tmp/skill.md'),
    ('input redirect', 'cat < /etc/hosts'),
    ('pipe into a non-head/tail command', f'cat {CODEX_SKILL} | grep name'),
    ('pipe into a shell', f'cat {CODEX_SKILL} | sh'),
    ('read joined to a write', f'cat {CODEX_SKILL} && rm -rf /tmp/x'),
    ('read joined to another command', f'cat {CODEX_SKILL}; ls'),
    ('or-chain', f'cat {CODEX_SKILL} || true'),
    ('background', f'cat {CODEX_SKILL} &'),
    ('command substitution', f'cat $(echo {CODEX_SKILL})'),
    ('backticks', f'cat `echo {CODEX_SKILL}`'),
    ('glob', f'cat {HOME}/.codex/plugins/cache/*/*/*/skills/*/SKILL.md'),
    ('variable in the path', f'cat {HOME}/.codex/plugins/cache/$MKT/rhize-ops/0.9.0/skills/x/SKILL.md'),
    ('dot-dot escape', f'cat {HOME}/.codex/plugins/cache/rhize-plugins/rhize-ops/0.9.0/skills/../../../x/SKILL.md'),
    ('multi-line script', f'cat {CODEX_SKILL}\nrm x'),
    ('cd not leading', f'ls && cd {HOME} && cat {CODEX_SKILL}'),
    ('cd joined with a semicolon', f'cd {HOME}; cat {CODEX_SKILL}'),
    ('env prefix', f'FOO=1 cat {CODEX_SKILL}'),
    ('relative path without a cd or workdir', 'cat skills/cross-model-handoff/SKILL.md'),
    ('dev checkout', f'cat {DEV_SKILL}'),
    ('dev checkout via sed -n', f"sed -n '1,80p' {DEV_SKILL}"),
    ('not under skills/', f'cat {HOME}/.codex/plugins/cache/rhize-plugins/rhize-ops/0.9.0/commands/handoff.md'),
    ('nested SKILL.md under references', f'cat {os.path.dirname(CODEX_SKILL)}/references/SKILL.md'),
    ('SKILL.md lookalike', f'cat {CODEX_SKILL}.bak'),
    ('cache path without a version directory', f'cat {HOME}/.codex/plugins/cache/rhize-plugins/skills/x/SKILL.md'),
    ('/tmp', 'cat /tmp/skills/cross-model-handoff/SKILL.md'),
    ('quote left open', f"cat '{CODEX_SKILL}"),
    ('empty', ''),
    ('whitespace', '   '),
    ('not a string or list', None),
    ('a number', 5),
    ('empty argv', []),
    ('non-string argv', [1, 2]),
]


@pytest.mark.parametrize('command,expected', [(case[1], case[2]) for case in READ_CASES], ids=[case[0] for case in READ_CASES])
def test_read_shaped_commands_on_plugin_skill_files_count(command, expected):
    assert transcripts.codex_skill_reads(command) == expected


@pytest.mark.parametrize('command', [case[1] for case in NOT_READS], ids=[case[0] for case in NOT_READS])
def test_everything_else_never_counts(command):
    assert transcripts.codex_skill_reads(command) == []


def test_workdir_resolves_relative_paths_and_a_cd_overrides_it():
    plugin_dir = f'{HOME}/.codex/plugins/cache/rhize-plugins/rhize-ops/0.9.0'
    assert transcripts.codex_skill_reads('cat skills/cross-model-handoff/SKILL.md', workdir=plugin_dir) == [
        'rhize-ops:cross-model-handoff']
    assert transcripts.codex_skill_reads('cat skills/cross-model-handoff/SKILL.md', workdir=f'{HOME}/dev-local') == []
    assert transcripts.codex_skill_reads(f'cd {plugin_dir} && cat skills/cross-model-handoff/SKILL.md',
                                         workdir='/tmp') == ['rhize-ops:cross-model-handoff']
    assert transcripts.codex_skill_reads('cat skills/x/SKILL.md', workdir='relative/dir') == []


def test_refs_are_valid_outcome_skill_refs():
    for _, command, expected in READ_CASES:
        for ref in transcripts.codex_skill_reads(command):
            assert contract.SKILL_REF.match(ref)


# ---------------------------------------------------------------- rollout lines

def test_only_function_call_lines_count_in_a_realistic_rollout(tmp_path):
    session = new_session()
    rows = [meta(session), *noise(at(0)),
            developer_note('<hook_prompt>workflow checkpoint</hook_prompt>', at(0)),
            user_turn('hand this to codex for a second opinion', at(1)),
            assistant_text('Reading the skill first.', at(2)),
            exec_call(f"sed -n '1,220p' {CODEX_SKILL}", at(3)),
            call_output('---\nname: cross-model-handoff\n---', at(4)),
            shell_call(['bash', '-lc', f'cd {HOME} && cat {CACHE_SKILL}'], at(5)),
            call_output('...', at(6)),
            exec_call(f'cat {MARKET_SKILL} | head -n 30', at(7))]
    path = write_rollout(tmp_path, session, rows)
    assert refs_of(path, after_ts=at(1)) == [('rhize-ops:cross-model-handoff', 'skill_file_read', 0),
                                             ('seo-aeo-geo:seo-site-audit', 'skill_file_read', 0),
                                             ('rhize-devflow:ship', 'skill_file_read', 0)]
    found = transcripts.skill_invocations(path)
    assert [item['ts'] for item in found] == [at(3), at(5), at(7)]


def test_rollout_negatives_are_not_misread(tmp_path):
    session = new_session()
    rows = [meta(session), *noise(at(0)),
            user_turn(f'please use $rhize-ops:cross-model-handoff and $seo-aeo-geo:seo-site-audit', at(1)),
            user_turn('<command-message>ship</command-message>\n<command-name>/rhize-devflow:ship</command-name>', at(2)),
            patch_call(CODEX_SKILL, at(3)),
            exec_call(f"sed -i 's/old/new/' {CODEX_SKILL}", at(4)),
            exec_call(f'grep -rn handoff {CODEX_SKILL}', at(5)),
            exec_call(f'git diff -- {CODEX_SKILL}', at(6)),
            exec_call(f'cat {DEV_SKILL}', at(7)),
            shell_call(['sed', '-i', 's/a/b/', CODEX_SKILL], at(8)),
            call_output(f'path is {CODEX_SKILL}', at(9)),
            assistant_text(f'I would read {CODEX_SKILL}', at(10)),
            # a Claude-only Skill tool_use in a Codex file is not a Codex invocation
            {'type': 'assistant', 'timestamp': at(11), 'message': {'role': 'assistant', 'content': [
                {'type': 'tool_use', 'id': 'toolu_1', 'name': 'Skill', 'input': {'skill': 'seo-aeo-geo:seo-site-audit'}}]}},
            # a payload type that is not function_call, even with a shell-looking body
            {'timestamp': at(12), 'type': 'response_item', 'payload': {
                'type': 'local_shell_call', 'status': 'completed', 'action': {'type': 'exec', 'command': ['cat', CODEX_SKILL]}}},
            # a function_call that is not a shell tool
            {'timestamp': at(13), 'type': 'response_item', 'payload': {
                'type': 'function_call', 'name': 'read_mcp_resource', 'arguments': json.dumps({'command': f'cat {CODEX_SKILL}'}),
                'call_id': 'call_z'}},
            # a function_call line type that is not a response_item
            {'timestamp': at(14), 'type': 'event_msg', 'payload': {
                'type': 'function_call', 'name': 'exec_command', 'arguments': json.dumps({'cmd': f'cat {CODEX_SKILL}'})}},
            # malformed arguments
            {'timestamp': at(15), 'type': 'response_item', 'payload': {
                'type': 'function_call', 'name': 'exec_command', 'arguments': '{not json', 'call_id': 'call_y'}},
            {'timestamp': at(16), 'type': 'response_item', 'payload': {
                'type': 'function_call', 'name': 'exec_command', 'arguments': json.dumps(['cat', CODEX_SKILL]),
                'call_id': 'call_w'}}]
    path = write_rollout(tmp_path, session, rows)
    assert refs_of(path) == []
    parsed = transcripts.parse_transcript(path)
    assert parsed.codex and parsed.invocations == []
    # the $-mentions and the pasted slash command are still ordinary, searchable user turns
    assert [turn['text'][:20] for turn in parsed.turns if turn['human']] == ['please use $rhize-op', '<command-message>shi']


def test_each_call_counts_but_one_call_counts_once_per_skill(tmp_path):
    session = new_session()
    rows = [meta(session), user_turn('go', at(1)),
            exec_call(f'cat {CODEX_SKILL} {CODEX_SKILL}', at(2)),
            exec_call(f'cat {CODEX_SKILL}', at(3)),
            exec_call(f'cat {CODEX_SKILL} {CACHE_SKILL}', at(4))]
    path = write_rollout(tmp_path, session, rows)
    assert [ref for ref, _, _ in refs_of(path)] == ['rhize-ops:cross-model-handoff', 'rhize-ops:cross-model-handoff',
                                                    'rhize-ops:cross-model-handoff', 'seo-aeo-geo:seo-site-audit']


def test_workdir_of_the_call_is_honoured_in_a_rollout(tmp_path):
    session = new_session()
    plugin_dir = f'{HOME}/.codex/plugins/cache/rhize-plugins/rhize-ops/0.9.0'
    rows = [meta(session), user_turn('go', at(1)),
            exec_call('cat skills/cross-model-handoff/SKILL.md', at(2), workdir=plugin_dir),
            exec_call('cat skills/cross-model-handoff/SKILL.md', at(3), workdir=f'{HOME}/dev-local/client')]
    assert refs_of(write_rollout(tmp_path, session, rows), after_ts=at(1)) == [
        ('rhize-ops:cross-model-handoff', 'skill_file_read', 0)]


def test_anchor_and_turn_semantics_match_the_claude_path(tmp_path):
    session = new_session()
    rows = [meta(session),
            exec_call(f'cat {CACHE_SKILL}', at(0)),                  # before the prompt: never counted
            user_turn('first prompt', at(10)),
            exec_call(f'cat {CODEX_SKILL}', at(12)),                 # same turn: 0 user turns after
            user_turn('follow up one', at(20)),
            user_turn('follow up two', at(30)),
            exec_call(f'cat {MARKET_SKILL}', at(40))]                # two user turns after the prompt
    path = write_rollout(tmp_path, session, rows)
    parsed = transcripts.parse_transcript(path)
    anchor_line = next(turn['line'] for turn in parsed.turns if turn['text'] == 'first prompt')
    got = transcripts.invocations_in(parsed, after_line=anchor_line)
    assert [(i['skillRef'], i['userTurnsAfter']) for i in got] == [('rhize-ops:cross-model-handoff', 0), ('rhize-devflow:ship', 2)]
    got = transcripts.invocations_in(parsed, after_epoch=transcripts._iso_to_epoch(at(10)), max_user_turns=1)
    assert [i['skillRef'] for i in got] == ['rhize-ops:cross-model-handoff']
    got = transcripts.invocations_in(parsed, after_line=anchor_line, until_epoch=transcripts._iso_to_epoch(at(15)))
    assert [i['skillRef'] for i in got] == ['rhize-ops:cross-model-handoff']


def test_codex_turns_stay_searchable(tmp_path):
    session = new_session()
    path = write_rollout(tmp_path, session, [meta(session), user_turn('codex prompt', at(1))])
    match, reason = transcripts.find_turn(session, sha('codex prompt')[:16], at(1), [tmp_path / 'sessions'])
    assert reason is None and match['text'] == 'codex prompt' and match['path'] == str(path)


def test_oversized_arguments_and_commands_are_ignored(tmp_path):
    session = new_session()
    huge = 'cat ' + CODEX_SKILL + ' ' + 'x' * (transcripts.MAX_ARGUMENTS_CHARS + 10)
    rows = [meta(session), user_turn('go', at(1)), exec_call(huge, at(2)),
            exec_call('cat ' + CODEX_SKILL + ' ' + 'y' * 17000, at(3)), exec_call(f'cat {CODEX_SKILL}', at(4))]
    assert refs_of(write_rollout(tmp_path, session, rows), after_ts=at(1)) == [
        ('rhize-ops:cross-model-handoff', 'skill_file_read', 0)]


# ---------------------------------------------------------------- thread source

@pytest.mark.parametrize('source', ['user', 'subagent', 'guardian_review', 'automation', 'agent_created_thread'])
def test_thread_source_is_read_from_the_first_line(tmp_path, source):
    session = new_session()
    path = write_rollout(tmp_path, session, [meta(session, source), user_turn('hi', at(1))])
    assert transcripts.codex_thread_source(path) == source
    parsed = transcripts.parse_transcript(path)
    assert parsed.codex and parsed.thread_source == source


def test_thread_source_is_none_when_unknown(tmp_path):
    session = new_session()
    path = write_rollout(tmp_path, session, [meta(session, None), user_turn('hi', at(1))])
    assert transcripts.codex_thread_source(path) is None and transcripts.parse_transcript(path).thread_source is None
    # not a session_meta first line
    other = write_rollout(tmp_path, new_session(), [user_turn('hi', at(1)), meta(session, 'user')])
    assert transcripts.codex_thread_source(other) is None and transcripts.parse_transcript(other).thread_source is None
    # a non-string or unsafe value
    for value in (5, ['user'], {'a': 1}, 'user\nx', 'x' * 200, ''):
        row = meta(session, 'user')
        row['payload']['thread_source'] = value
        path = write_rollout(tmp_path, new_session(), [row])
        assert transcripts.codex_thread_source(path) is None, value
    # garbage and a Claude transcript
    bad = tmp_path / 'bad.jsonl'
    bad.write_text('{not json\n')
    assert transcripts.codex_thread_source(bad) is None
    claude = tmp_path / 'claude.jsonl'
    claude.write_text(json.dumps({'type': 'user', 'timestamp': T0, 'message': {'role': 'user', 'content': 'hi'}}) + '\n')
    assert transcripts.codex_thread_source(claude) is None
    assert transcripts.codex_thread_source(tmp_path / 'missing.jsonl') is None
    assert transcripts.codex_thread_source(tmp_path) is None
    empty = tmp_path / 'empty.jsonl'
    empty.write_text('')
    assert transcripts.codex_thread_source(empty) is None


def test_thread_source_read_is_bounded_and_never_follows_links(tmp_path):
    session = new_session()
    path = write_rollout(tmp_path, session, [meta(session, 'user'), user_turn('hi', at(1))])
    first_line_size = len(path.read_bytes().split(b'\n', 1)[0]) + 1
    assert transcripts.codex_thread_source(path, max_bytes=first_line_size) == 'user'
    assert transcripts.codex_thread_source(path, max_bytes=first_line_size - 10) is None        # first line too long
    link = tmp_path / 'link.jsonl'
    link.symlink_to(path)
    assert transcripts.codex_thread_source(link) is None
    fifo = tmp_path / 'fifo.jsonl'
    os.mkfifo(fifo)
    assert transcripts.codex_thread_source(fifo) is None                                           # not a regular file


def test_thread_source_of_a_later_session_meta_line_is_ignored(tmp_path):
    session = new_session()
    later = meta(session, 'user')
    path = write_rollout(tmp_path, session, [meta(session, 'subagent'), user_turn('hi', at(1)), later])
    assert transcripts.parse_transcript(path).thread_source == 'subagent'


# ---------------------------------------------------------------- the outcome join

def live_record(session, prompt, *, ts=T0, shortlist=(SEO, GEO), emitted=SEO, host='codex'):
    record = copy.deepcopy(json.loads((FIX / 'records.json').read_text())['valid']['live-shadow-agree'])
    record.update(decisionId=uuid.uuid4().hex, host=host, sessionHash=sha(session), promptHash=sha(prompt), ts=ts,
                  shortlist=list(shortlist), emitted=emitted)
    record['incumbent'] = {'skillId': shortlist[0], 'score': 5}
    record['laya'] = {'status': 'ok', 'choice': shortlist[0], 'latencyMs': 40, 'truncated': False,
                      'probabilities': [0.5] + [0.5 / len(shortlist)] * len(shortlist)}
    record['occurrenceKey'] = contract.occurrence_key(record['sessionHash'], record['promptHash'], ts)
    return contract.validate_record(record)


def run_join(tmp_path, root, **kwargs):
    return outcomes.join(root=root, transcripts_roots=[tmp_path / 'sessions'], now=kwargs.pop('now', NOW), **kwargs)


def outcome_map(root):
    items, invalid = records.read(root, 'skill-fit', 'outcomes')
    assert invalid == 0
    return {item['decisionId']: item for item in items}


def codex_world(tmp_path, root, name, rows_after, *, thread_source='user', shortlist=(SEO, GEO), emitted=SEO,
                host='codex', prompt=None):
    """One record plus its rollout: session_meta, the prompt turn at T0, then `rows_after`."""
    session = new_session()
    prompt = prompt or f'prompt for {name}'
    write_rollout(tmp_path, session, [meta(session, thread_source), user_turn(prompt, T0), *rows_after])
    record = live_record(session, prompt, shortlist=shortlist, emitted=emitted, host=host)
    records.append(root, 'skill-fit', 'records', record)
    return record, session


def test_a_codex_user_thread_is_joined_through_skill_file_reads(tmp_path):
    root = tmp_path / 'root'
    cases = {}
    cases['emitted'], emitted_session = codex_world(
        tmp_path, root, 'emitted', [exec_call(f"sed -n '1,200p' {CACHE_SKILL}", at(8))])
    cases['other'], _ = codex_world(
        tmp_path, root, 'other', [assistant_text('hmm', at(5)), user_turn('now ship it', at(30)),
                                  exec_call(f'cat {MARKET_SKILL}', at(40))], shortlist=(SEO, SHIP))
    cases['unlisted'], _ = codex_world(tmp_path, root, 'unlisted', [exec_call(f'cat {CODEX_SKILL}', at(8))])
    cases['none'], _ = codex_world(tmp_path, root, 'none', [assistant_text('done', at(5))])
    cases['mention-only'], _ = codex_world(
        tmp_path, root, 'mention', [exec_call(f'grep -n x {CACHE_SKILL}', at(8)), assistant_text('done', at(9))],
        prompt='use $seo-aeo-geo:seo-site-audit now')
    cases['edit-only'], _ = codex_world(tmp_path, root, 'edit', [patch_call(CACHE_SKILL, at(8)),
                                                                 exec_call(f"sed -i 's/a/b/' {CACHE_SKILL}", at(9))])
    cases['dev-checkout'], _ = codex_world(tmp_path, root, 'dev', [exec_call(f'cat {DEV_SKILL}', at(8))])
    cases['late'], _ = codex_world(tmp_path, root, 'late', [exec_call(f'cat {CACHE_SKILL}', '2026-10-11T21:31:00.000Z')])
    summary, code = run_join(tmp_path, root)
    assert code == 0 and summary['written'] == 8 and summary['pendingWindow'] == 0
    got = outcome_map(root)

    def result(name):
        return got[cases[name]['decisionId']]
    for name, expected in (('emitted', 'invoked_emitted'), ('other', 'invoked_other_shortlisted'),
                           ('unlisted', 'invoked_unlisted'), ('none', 'none_invoked'),
                           ('mention-only', 'none_invoked'), ('edit-only', 'none_invoked'),
                           ('dev-checkout', 'none_invoked'), ('late', 'none_invoked')):
        assert result(name)['outcome'] == expected, name
    emitted = result('emitted')
    assert (emitted['skillInvoked'], emitted['via'], emitted['latencyTurns']) == (
        'seo-aeo-geo:seo-site-audit', 'skill_file_read', 0)
    other = result('other')
    assert (other['skillInvoked'], other['via'], other['latencyTurns']) == ('rhize-devflow:ship', 'skill_file_read', 1)
    unlisted = result('unlisted')
    assert (unlisted['skillInvoked'], unlisted['via']) == ('rhize-ops:cross-model-handoff', 'skill_file_read')
    rollout = next((tmp_path / 'sessions').rglob(f'*{emitted_session}.jsonl'))
    assert emitted['transcriptSha256'] == hashlib.sha256(rollout.read_bytes()).hexdigest()
    assert result('none')['via'] is None and result('none')['transcriptSha256']
    assert summary['outcomes'] == {'invoked_emitted': 1, 'invoked_other_shortlisted': 1, 'invoked_unlisted': 1,
                                   'none_invoked': 5}


@pytest.mark.parametrize('thread_source', ['subagent', 'guardian_review', 'automation', 'agent_created_thread', None])
def test_a_codex_thread_that_is_not_a_user_thread_is_unavailable(tmp_path, thread_source):
    root = tmp_path / 'root'
    record, _ = codex_world(tmp_path, root, 'machine', [exec_call(f'cat {CACHE_SKILL}', at(8))],
                            thread_source=thread_source)
    summary, code = run_join(tmp_path, root)
    assert code == 0 and summary['written'] == 1
    outcome = outcome_map(root)[record['decisionId']]
    assert outcome['outcome'] == 'transcript_unavailable'
    assert outcome['skillInvoked'] is None and outcome['via'] is None and outcome['latencyTurns'] is None
    assert outcome['transcriptSha256'] is None
    assert summary['outcomes'] == {'transcript_unavailable': 1}


def test_claude_and_codex_sessions_join_in_one_run_and_unmatched_sessions_are_still_counted(tmp_path):
    root = tmp_path / 'root'
    codex_record, _ = codex_world(tmp_path, root, 'codex', [exec_call(f'cat {CACHE_SKILL}', at(8))])
    machine_record, _ = codex_world(tmp_path, root, 'machine', [exec_call(f'cat {CACHE_SKILL}', at(8))],
                                    thread_source='subagent')
    claude_session = new_session()
    claude_path = tmp_path / 'sessions' / '-proj' / f'{claude_session}.jsonl'
    claude_path.parent.mkdir(parents=True)
    claude_path.write_text('\n'.join(json.dumps(row) for row in [
        {'type': 'user', 'timestamp': T0, 'message': {'role': 'user', 'content': 'claude prompt'}},
        {'type': 'assistant', 'timestamp': at(8), 'message': {'role': 'assistant', 'content': [
            {'type': 'tool_use', 'id': 'toolu_1', 'name': 'Skill', 'input': {'skill': 'seo-aeo-geo:seo-site-audit'}}]}}]) + '\n')
    claude_record = live_record(claude_session, 'claude prompt', host='claude')
    records.append(root, 'skill-fit', 'records', claude_record)
    missing_record = live_record(new_session(), 'nobody wrote this transcript', host='codex')
    records.append(root, 'skill-fit', 'records', missing_record)
    summary, code = run_join(tmp_path, root)
    assert code == 0 and summary['written'] == 4
    got = outcome_map(root)
    assert (got[codex_record['decisionId']]['outcome'], got[codex_record['decisionId']]['via']) == (
        'invoked_emitted', 'skill_file_read')
    assert (got[claude_record['decisionId']]['outcome'], got[claude_record['decisionId']]['via']) == (
        'invoked_emitted', 'skill_tool')
    assert got[machine_record['decisionId']]['outcome'] == 'transcript_unavailable'
    assert got[missing_record['decisionId']]['outcome'] == 'transcript_unavailable'
    assert summary['outcomes'] == {'invoked_emitted': 2, 'transcript_unavailable': 2}


def test_the_join_is_idempotent_for_codex_records(tmp_path):
    root = tmp_path / 'root'
    codex_world(tmp_path, root, 'one', [exec_call(f'cat {CACHE_SKILL}', at(8))])
    first, _ = run_join(tmp_path, root)
    second, _ = run_join(tmp_path, root)
    assert first['written'] == 1 and second['written'] == 0 and second['alreadyJoined'] == 1


def test_a_record_waits_for_its_window_like_any_other(tmp_path):
    root = tmp_path / 'root'
    codex_world(tmp_path, root, 'open', [exec_call(f'cat {CACHE_SKILL}', at(8))])
    summary, _ = run_join(tmp_path, root, now=outcomes.datetime.fromisoformat('2026-10-11T21:10:00+00:00'))
    assert summary['pendingWindow'] == 1 and summary['written'] == 0


# ---------------------------------------------------------------- the contract

def test_skill_file_read_is_a_valid_outcome_via():
    assert contract.OUTCOME_VIA == ('skill_tool', 'slash_command', 'skill_file_read')
    base = json.loads((FIX / 'outcomes.json').read_text())['valid']['invoked-emitted']
    outcome = {**base, 'via': 'skill_file_read', 'skillInvoked': 'rhize-ops:cross-model-handoff'}
    assert contract.validate_outcome(outcome) == outcome
    with pytest.raises(ValueError):
        contract.validate_outcome({**outcome, 'via': 'file_read'})
    with pytest.raises(ValueError):
        contract.validate_outcome({**base, 'via': None})
    with pytest.raises(ValueError):                       # a non-invocation outcome still carries no via
        contract.validate_outcome({**json.loads((FIX / 'outcomes.json').read_text())['valid']['none-invoked'],
                                   'via': 'skill_file_read'})


@pytest.mark.skipif(jsonschema is None, reason='jsonschema not installed; the stdlib validators are canonical')
def test_the_outcome_json_schema_enum_matches_the_contract():
    schema = json.loads((REPO / 'rhize-context-manager' / 'schemas' / 'typed-decision-outcome-v1.schema.json').read_text())
    validator = jsonschema.Draft202012Validator(schema)
    base = json.loads((FIX / 'outcomes.json').read_text())['valid']['invoked-emitted']
    for via in contract.OUTCOME_VIA:
        validator.validate({**base, 'via': via})
    with pytest.raises(jsonschema.ValidationError):
        validator.validate({**base, 'via': 'file_read'})
    enum = next(option['enum'] for option in schema['properties']['via']['anyOf'] if 'enum' in option)
    assert tuple(enum) == contract.OUTCOME_VIA


# ---------------------------------------------------------------- final-review hardening (Codex A, real layouts)

PLUGIN_SKILL = '/Users/jim/.codex/plugins/cache/rhize-plugins/rhize-ops/0.30.0/skills/delegate-to-teammate/SKILL.md'


def _executed(parsed_cmd, exit_code=0, output='# Skill\n', cwd='file:///Users/jim/dev/project'):
    return {'timestamp': '2026-10-11T12:00:00.000Z', 'type': 'event_msg',
            'payload': {'type': 'item_completed', 'thread_id': 't', 'turn_id': 'u',
                        'item': {'type': 'CommandExecution', 'command': ['/bin/zsh', '-lc', 'x'],
                                 'cwd': cwd, 'parsed_cmd': parsed_cmd, 'exit_code': exit_code,
                                 'aggregated_output': output}}}


@pytest.mark.parametrize('parsed_cmd,kwargs,expected', [
    ([{'type': 'read', 'cmd': 'sed -n 1,200p X', 'name': 'SKILL.md', 'path': PLUGIN_SKILL}], {}, ['rhize-ops:delegate-to-teammate']),
    ([{'type': 'read', 'path': '~/.agents/skills/analytics-tracking/SKILL.md'}], {}, ['analytics-tracking']),
    ([{'type': 'read', 'path': '/Users/jim/.claude/skills/synced/8b0da063/deep-research/SKILL.md'}], {}, ['deep-research']),
    ([{'type': 'read', 'path': PLUGIN_SKILL}, {'type': 'search', 'query': 'x', 'path': 'src'}], {}, ['rhize-ops:delegate-to-teammate']),
    ([{'type': 'read', 'path': PLUGIN_SKILL}], {'exit_code': 1, 'output': ''}, []),          # failed, printed nothing
    ([{'type': 'read', 'path': PLUGIN_SKILL}], {'exit_code': 1, 'output': 'cat: X: No such file or directory\n'}, []),
    ([{'type': 'read', 'path': PLUGIN_SKILL}], {'exit_code': 2, 'output': '# Skill\n'}, []),  # output, but non-zero
    ([{'type': 'read', 'path': PLUGIN_SKILL}], {'exit_code': None}, []),                      # unknown exit
    ([{'type': 'read', 'path': PLUGIN_SKILL}], {'exit_code': '0'}, []),                       # not an integer
    ([{'type': 'read', 'path': PLUGIN_SKILL}], {'exit_code': False}, []),                     # bool is not 0
    ([{'type': 'read', 'path': PLUGIN_SKILL}], {'exit_code': 0.0}, []),                       # float is not 0
    ([{'type': 'read', 'path': PLUGIN_SKILL}], {'exit_code': -0.0}, []),
    ([{'type': 'search', 'query': 'SKILL.md', 'path': '/Users/jim/.codex/plugins/cache'}], {}, []),
    ([{'type': 'list_files', 'path': 'skills'}], {}, []),
    ([{'type': 'read', 'path': '/Users/jim/.codex/memories/skills/foo/SKILL.md'}], {}, []),  # Codex memory skills
    ([{'type': 'read', 'path': '/Users/jim/dev/rhize-plugins/rhize-ops/skills/x/SKILL.md'}], {}, []),  # dev checkout
    ([{'type': 'unknown', 'cmd': f'sed -i s/a/b/ {PLUGIN_SKILL}'}], {}, []),
    ([{'type': 'read', 'path': '.agents/skills/local-skill/SKILL.md'}], {'cwd': 'file:///Users/jim'}, ['local-skill']),
])
def test_codex_executed_reads_use_codex_parsed_cmd(parsed_cmd, kwargs, expected):
    assert transcripts.codex_skill_file_reads(_executed(parsed_cmd, **kwargs)) == expected


@pytest.mark.parametrize('command,expected', [
    (f'cat --help {PLUGIN_SKILL}', []),
    (f'cat --version {PLUGIN_SKILL}', []),
    (f"sed -n 'q' {PLUGIN_SKILL}", []),
    (f"sed -n '=' {PLUGIN_SKILL}", []),
    (f"sed -n '1,200p' {PLUGIN_SKILL}", ['rhize-ops:delegate-to-teammate']),
    (f'head -n 40 {PLUGIN_SKILL}', ['rhize-ops:delegate-to-teammate']),
    (f'tail --bogus {PLUGIN_SKILL}', []),
    ("cat '$HOME/.codex/plugins/cache/rhize-plugins/rhize-ops/0.30.0/skills/delegate-to-teammate/SKILL.md'", []),
    ('cat "~/.codex/plugins/cache/rhize-plugins/rhize-ops/0.30.0/skills/delegate-to-teammate/SKILL.md"', []),
    ('cat "$HOME/.codex/plugins/cache/rhize-plugins/rhize-ops/0.30.0/skills/delegate-to-teammate/SKILL.md"',
     ['rhize-ops:delegate-to-teammate']),
    # Concatenated fragments are judged as one word (Codex final review): the quoted prefix stays literal.
    ("cat '$HOME'/.codex/plugins/cache/rhize-plugins/rhize-ops/0.30.0/skills/delegate-to-teammate/SKILL.md", []),
    ("cat '${HOME}'/.codex/plugins/cache/rhize-plugins/rhize-ops/0.30.0/skills/delegate-to-teammate/SKILL.md", []),
    ("cat '$'HOME/.codex/plugins/cache/rhize-plugins/rhize-ops/0.30.0/skills/delegate-to-teammate/SKILL.md", []),
    ('cat "~"/.codex/plugins/cache/rhize-plugins/rhize-ops/0.30.0/skills/delegate-to-teammate/SKILL.md', []),
    ("cat '~'/.codex/plugins/cache/rhize-plugins/rhize-ops/0.30.0/skills/delegate-to-teammate/SKILL.md", []),
    ('cat \\~/.codex/plugins/cache/rhize-plugins/rhize-ops/0.30.0/skills/delegate-to-teammate/SKILL.md', []),
    ('cat \\$HOME/.codex/plugins/cache/rhize-plugins/rhize-ops/0.30.0/skills/delegate-to-teammate/SKILL.md', []),
    ('cat "$HOME"/.codex/plugins/cache/rhize-plugins/rhize-ops/0.30.0/skills/delegate-to-teammate/SKILL.md',
     ['rhize-ops:delegate-to-teammate']),
    ('cat ~/".codex/plugins/cache/rhize-plugins/rhize-ops/0.30.0/skills/delegate-to-teammate/SKILL.md"',
     ['rhize-ops:delegate-to-teammate']),
    # A leading cd into a literal (quoted) home path fails, so the && read never runs.
    ("cd '$HOME/.codex/plugins/cache/rhize-plugins/rhize-ops/0.30.0/skills/delegate-to-teammate' && cat SKILL.md", []),
    ('cd "~/.codex/plugins/cache/rhize-plugins/rhize-ops/0.30.0" && cat skills/delegate-to-teammate/SKILL.md', []),
    ('cd "$HOME/.codex/plugins/cache/rhize-plugins/rhize-ops/0.30.0" && cat skills/delegate-to-teammate/SKILL.md',
     ['rhize-ops:delegate-to-teammate']),
])
def test_legacy_shell_reads_reject_help_non_printing_sed_and_quoted_home(command, expected):
    assert transcripts.codex_skill_reads(command) == expected


# ---------------------------------------------------------------- Fable final review: dual-line rollouts

def _completion(path, when, exit_code, cmd=None):
    return {'timestamp': when, 'type': 'event_msg',
            'payload': {'type': 'item_completed', 'thread_id': 't', 'turn_id': 'u',
                        'item': {'type': 'CommandExecution', 'command': ['/bin/zsh', '-lc', cmd or f'cat {path}'],
                                 'cwd': f'file://{HOME}/dev-local/client',
                                 'parsed_cmd': [{'type': 'read', 'path': path}], 'exit_code': exit_code,
                                 'aggregated_output': '# Skill\n' if exit_code == 0 else 'cat: No such file\n'}}}


@pytest.mark.parametrize('exit_code,expected', [(1, []), (0, ['rhize-ops:cross-model-handoff'])])
def test_a_rollout_with_completions_ignores_the_coexisting_function_call(tmp_path, exit_code, expected):
    """Codex persists both the shell function_call and its CommandExecution completion; only the completion knows the
    exit code, so a failed read (a stale version directory after a plugin upgrade) never counts and a successful read
    counts once."""
    session = new_session()
    rows = [meta(session), user_turn('hand this to the other model', at(1)),
            shell_call(['bash', '-lc', f'cat {CODEX_SKILL}'], at(2)),
            _completion(CODEX_SKILL, at(3), exit_code)]
    parsed = transcripts.parse_transcript(write_rollout(tmp_path, session, rows))
    assert [item['ref'] for item in parsed.invocations] == expected
    assert all(item['line'] == 4 for item in parsed.invocations)       # from the completion line, not the call


def test_a_legacy_rollout_without_completions_still_counts_function_call_reads(tmp_path):
    session = new_session()
    rows = [meta(session), user_turn('hand this to the other model', at(1)),
            shell_call(['bash', '-lc', f'cat {CODEX_SKILL}'], at(2)), call_output('# Skill', at(3))]
    parsed = transcripts.parse_transcript(write_rollout(tmp_path, session, rows))
    assert [(item['ref'], item['line']) for item in parsed.invocations] == [('rhize-ops:cross-model-handoff', 3)]


def test_any_completion_line_switches_the_whole_rollout_to_completion_evidence(tmp_path):
    session = new_session()
    other = f'{HOME}/.codex/plugins/cache/rhize-plugins/seo-aeo-geo/1.0.0/skills/seo-site-audit/SKILL.md'
    rows = [meta(session), user_turn('first', at(1)),
            shell_call(['bash', '-lc', f'cat {CODEX_SKILL}'], at(2)),          # no completion recorded for this one
            user_turn('second', at(3)),
            _completion(other, at(4), 0, cmd='ls')]
    parsed = transcripts.parse_transcript(write_rollout(tmp_path, session, rows))
    assert [item['ref'] for item in parsed.invocations] == ['seo-aeo-geo:seo-site-audit']
